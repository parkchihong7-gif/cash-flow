"""연예인 착용템 쇼츠 기획 CLI.

    python cli.py build shorts_input.yaml              # 기획서 만들기 (Claude 1회)
    python cli.py build shorts_input.yaml --dry-run    # Claude 없이 모양만 (비용 0원)
    python cli.py check outputs/<폴더>                 # 기획서 다시 검사
    python cli.py approve outputs/<폴더> --name 홍길동  # 사람 승인 (영상 만들기 전 필수)

종료 코드: 0 문제 없음 · 2 볼 것이 있음(경고·막음) · 1 실패.
연예인 얼굴·방송 화면은 고를 수 없게 만들었다. 출처가 없으면 이름도 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from celeb_shorts.generator import Planner                          # noqa: E402
from celeb_shorts.output import (                                    # noqa: E402
    OUTPUT_FILES, ApprovalRefused, approve, write_outputs,
)
from celeb_shorts.rules import Issue, review_input, review_plan      # noqa: E402
from celeb_shorts.schema import PlanDraft, ShortsInput, slugify      # noqa: E402
from shared.config import DEFAULT_MODEL                              # noqa: E402
from shared.llm import LLMError                                      # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = BASE_DIR / "outputs"


def load_input(path: Path) -> ShortsInput:
    if not path.is_file():
        raise FileNotFoundError(f"입력 파일이 없습니다: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return ShortsInput.model_validate(raw)


def _print_issues(issues: list[Issue], notes: list[str]) -> None:
    for note in notes:
        print(f"  · {note}")
    for issue in issues:
        print(f"  {issue.line()}")


def cmd_build(args: argparse.Namespace) -> int:
    data = load_input(Path(args.input))
    review = review_input(data)

    print(f"[1/3] 입력 읽기 — 아이템 {len(data.items)}개 · {data.duration_sec}초 · "
          f"이름 {'씀' if review.name_allowed else '안 씀'}")
    _print_issues(review.issues, review.notes)
    if review.blocked:
        print("\n입력부터 고쳐야 합니다. 기획서를 만들지 않았습니다.")
        return 1

    if args.dry_run:
        from celeb_shorts.sample_content import fake_ask
        planner, model = Planner("dry-run", fake_ask), "dry-run"
        print("[2/3] 모의 실행 — Claude 를 부르지 않습니다 (비용 없음)")
    else:
        planner, model = Planner(args.model), args.model
        print(f"[2/3] 모델 {args.model} 로 기획합니다. 호출 1회.")
    plan, issues, notes = planner.run(review)
    notes = review.notes + notes

    print("[3/3] 파일 쓰기")
    slug = args.slug or slugify(f"{data.celebrity if review.name_allowed else ''} {data.occasion}".strip()
                                or plan.title)
    out_dir = write_outputs(Path(args.out) / slug, review, plan, issues, notes,
                            dry_run=args.dry_run, ai_label_on=not args.no_ai_label, model=model)
    for name in OUTPUT_FILES:
        print(f"  ✓ {name}")
    print(f"  → {out_dir}")

    print()
    _print_issues(issues, [])
    blocked = any(i.level == "block" for i in issues)
    print()
    if blocked:
        print("⛔ 막음이 있어 이대로는 승인할 수 없습니다. plan.md 의 '검사 결과' 를 보세요.")
    else:
        print("다음 순서")
        print("  1. plan.md 를 읽고 자막·내레이션을 내 말투로 고치세요")
        print("  2. checklist.md 를 하나씩 확인하세요")
        print(f"  3. python cli.py approve {out_dir} --name 승인자이름")
    if args.dry_run:
        print("\n※ 모의 실행 결과입니다. 승인할 수 없습니다.")
    return 2 if issues else 0


def cmd_check(args: argparse.Namespace) -> int:
    path = Path(args.folder) / "plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    review = review_input(ShortsInput.model_validate(payload["input"]))
    _, issues, notes = review_plan(PlanDraft.model_validate(payload["plan"]), review)
    _print_issues(issues, notes)
    if not issues:
        print("문제 없음")
    return 2 if issues else 0


def cmd_approve(args: argparse.Namespace) -> int:
    try:
        result = approve(Path(args.folder), args.name or "")
    except ApprovalRefused as exc:
        print(f"승인하지 않았습니다.\n{exc}")
        return 1
    print(f"승인했습니다 — {result['by']} · {result['at']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="연예인 착용템 쇼츠 기획")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="기획서 만들기")
    build.add_argument("input", nargs="?", default=str(BASE_DIR / "shorts_input.yaml"))
    build.add_argument("--dry-run", action="store_true", help="Claude 없이 예시로")
    build.add_argument("--model", default=DEFAULT_MODEL)
    build.add_argument("--out", default=str(DEFAULT_OUT))
    build.add_argument("--slug", default="")
    build.add_argument("--no-ai-label", action="store_true",
                       help="본문 끝 AI 표시를 뺀다 (plan.json 의 표시 기록은 남는다)")
    build.set_defaults(func=cmd_build)

    check = sub.add_parser("check", help="기획서 다시 검사")
    check.add_argument("folder")
    check.set_defaults(func=cmd_check)

    approve_p = sub.add_parser("approve", help="사람 승인")
    approve_p.add_argument("folder")
    approve_p.add_argument("--name", required=True)
    approve_p.set_defaults(func=cmd_approve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValidationError, ValueError, LLMError) as exc:
        print(f"실패: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
