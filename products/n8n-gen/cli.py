"""n8n 워크플로 JSON 생성기 CLI.

    python cli.py "매일 9시에 구글시트를 읽어 Claude로 요약해 슬랙에 보내줘"
    python cli.py "..." --dry-run            # Claude 없이 검증기만
    python cli.py --examples --dry-run       # 예시 5개를 한 번에
    python cli.py --request-file request.txt # 파일에 적은 요구를 처리 (대시보드가 쓰는 방식)
    python cli.py "..." --push               # n8n REST API 로 생성까지
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from n8n_gen.assembler import assemble  # noqa: E402
from n8n_gen.generator import PlanGenerator  # noqa: E402
from n8n_gen.pusher import N8nNotConfigured, push_workflow  # noqa: E402
from n8n_gen.validator import validate  # noqa: E402
from n8n_gen.writers import write_outputs  # noqa: E402
from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import LLMError  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = BASE_DIR / "outputs"
EXAMPLES_PATH = BASE_DIR / "templates" / "examples.txt"


def read_requests(path: Path) -> list[str]:
    """요구가 한 줄에 하나씩 적힌 파일을 읽는다.

    빈 줄과 `#` 로 시작하는 줄은 설명으로 보고 건너뛴다.
    `templates/examples.txt` 와 대시보드용 `request.txt` 가 같은 형식이다.
    """
    if not path.is_file():
        raise FileNotFoundError(f"요구 파일이 없습니다: {path}")
    requests = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not requests:
        raise ValueError(
            f"{path.name} 에 요구가 한 줄도 없습니다. "
            "`#` 없이 한 줄에 하나씩 적어주세요."
        )
    return requests


def load_examples() -> list[str]:
    """`templates/examples.txt` 에서 예시 요구를 읽는다."""
    return read_requests(EXAMPLES_PATH)


def build_one(request: str, args: argparse.Namespace) -> tuple[bool, Path | None]:
    """요구 하나를 처리한다. (검증 통과 여부, 산출물 폴더) 를 돌려준다."""
    if args.dry_run:
        from n8n_gen.sample_content import fake_ask

        generator = PlanGenerator(model="dry-run", ask_fn=fake_ask)
    else:
        generator = PlanGenerator(model=args.model)

    plan = generator.build(request)
    workflow = assemble(plan)
    result = validate(workflow.workflow)

    out_dir = write_outputs(
        plan, workflow, result, Path(args.out), request,
        generator.model, datetime.now().astimezone(),
        ai_label=not args.no_ai_label,
    )

    mark = "✓" if result.ok else "✗"
    print(f"  {mark} {plan.workflow_name} — 노드 {len(workflow.placements)}개"
          f"{f' ({generator.attempts}회 시도)' if generator.attempts > 1 else ''}")
    if not result.ok:
        print(result.report())
    for issue in result.warnings:
        print(f"    ! {issue}")
    if workflow.unsupported:
        print(f"    ⚠ 대체한 항목 {len(workflow.unsupported)}건 — plan.md 를 보세요")
    print(f"    → {out_dir}")

    return result.ok, out_dir


def cmd_build(args: argparse.Namespace) -> int:
    if args.examples:
        requests = load_examples()
    elif args.request_file:
        requests = read_requests(Path(args.request_file))
    else:
        requests = [args.request]

    if args.dry_run:
        print("모의 실행 — Claude 를 부르지 않습니다 (비용 없음)")
    elif not args.examples:
        print(f"모델 {args.model} 로 계획을 만듭니다")

    print(f"요구 {len(requests)}건 처리")
    print()

    results = []
    for index, request in enumerate(requests, start=1):
        if len(requests) > 1:
            print(f"[{index}/{len(requests)}] {request[:50]}")
        ok, out_dir = build_one(request, args)
        results.append((ok, out_dir, request))
        print()

    passed = sum(1 for ok, _, _ in results if ok)
    print(f"검증 통과 {passed}/{len(results)}건")

    if args.push:
        print()
        if passed < len(results):
            print("검증에 실패한 워크플로가 있어 --push 를 건너뜁니다.", file=sys.stderr)
            return 2
        for _, out_dir, _ in results:
            workflow = json.loads((out_dir / "workflow.json").read_text(encoding="utf-8"))
            pushed = push_workflow(workflow)
            print(f"  n8n 에 생성했습니다: {pushed.name} → {pushed.url}")
        print("  비활성 상태로 만들었습니다. n8n 에서 credential 을 연결한 뒤 켜세요.")

    print()
    print("n8n 에서 Import from File 로 workflow.json 을 가져오세요.")
    print("납품하실 때는 setup_guide.md 를 함께 주시면 됩니다.")
    if args.dry_run:
        print("※ 모의 실행 결과입니다. 계획 내용은 예시입니다.")
    return 0 if passed == len(results) else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="자연어 자동화 요구 → n8n workflow.json (납품 전 사람 검수 필수)",
    )
    parser.add_argument("request", nargs="?", help="자동화 요구를 한 문장으로")
    parser.add_argument("--examples", action="store_true",
                        help=f"{EXAMPLES_PATH.name} 의 예시를 전부 처리합니다")
    parser.add_argument("--request-file", default="",
                        help="요구가 한 줄에 하나씩 적힌 파일 (대시보드가 쓰는 방식)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Claude 를 부르지 않고 예시 계획으로 검증기만 돌립니다")
    parser.add_argument("--push", action="store_true",
                        help="N8N_URL·N8N_API_KEY 가 있으면 n8n 에 워크플로를 만듭니다")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Claude 모델 (기본: {DEFAULT_MODEL})")
    parser.add_argument("--no-ai-label", action="store_true",
                        help="AI 생성물 표시를 끕니다")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help=f"산출물 상위 폴더 (기본: {DEFAULT_OUT})")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.request and not args.examples and not args.request_file:
        build_parser().print_help()
        print('\n예: python cli.py "매일 9시에 시트를 읽어 슬랙에 보내줘" --dry-run',
              file=sys.stderr)
        return 1

    try:
        return cmd_build(args)
    except FileNotFoundError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    except N8nNotConfigured as exc:
        print(f"n8n 설정이 없습니다:\n{exc}", file=sys.stderr)
    except LLMError as exc:
        print(f"생성 실패: {exc}", file=sys.stderr)
    except RuntimeError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"계획을 만들지 못했습니다:\n{exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
