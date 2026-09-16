"""후킹 대본 생성기 CLI.

    python cli.py build script_input.yaml
    python cli.py build --topic "주제" --format shorts --duration 30 --audience "대상"
    python cli.py build script_input.yaml --hook-index 2
    python cli.py build --batch topics.txt --format shorts --duration 30 --audience "대상"

`--dry-run` 을 붙이면 Claude 를 부르지 않고 예시 콘텐츠로 산출물 형태만 만든다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hook_script.generator import ScriptGenerator, write_outputs  # noqa: E402
from hook_script.schema import DURATION_RANGE, ScriptInput, load_input  # noqa: E402

from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import LLMError  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = BASE_DIR / "outputs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="롱폼·쇼츠·릴스 대본 초안 생성기 (발행 전 사람 검수 필수)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="대본 산출물 5종을 만든다")
    build.add_argument("input", nargs="?", help="입력 YAML 경로 (생략 시 아래 인자로 직접 지정)")

    direct = build.add_argument_group("YAML 대신 직접 지정")
    direct.add_argument("--topic", help="주제")
    direct.add_argument("--format", choices=["long", "shorts", "reels"], help="포맷")
    direct.add_argument("--duration", type=int, help="길이(초). 쇼츠·릴스 15~60, 롱폼 300~1200")
    direct.add_argument("--audience", help="시청자 한 줄 설명")
    direct.add_argument("--tone", choices=["정보형", "스토리형", "반전형"], default="정보형")
    direct.add_argument("--cta", choices=["구독", "링크", "댓글"], default="구독")

    build.add_argument(
        "--batch", metavar="FILE",
        help="주제가 한 줄에 하나씩 적힌 파일. 각 주제로 한 편씩 만든다",
    )
    build.add_argument(
        "--hook-index", type=int, default=1, metavar="N",
        help="쓸 후크 번호 (1부터). 기본 1 = 강도 1위",
    )
    build.add_argument("--chapters", type=int, default=6, help="롱폼 챕터 수 (5~7, 기본 6)")
    build.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude 모델 (기본: {DEFAULT_MODEL})")
    build.add_argument("--no-ai-label", action="store_true", help="AI 생성물 표시를 끈다")
    build.add_argument("--out", default=str(DEFAULT_OUT), help=f"산출물 상위 폴더 (기본: {DEFAULT_OUT})")
    build.add_argument(
        "--dry-run", action="store_true",
        help="Claude 를 부르지 않고 예시 콘텐츠로 만든다 (API 비용 없음)",
    )
    return parser


def _inputs_from_args(args: argparse.Namespace) -> list[ScriptInput]:
    """YAML / 직접 지정 / 배치 중 하나로 입력 목록을 만든다."""
    if args.batch:
        path = Path(args.batch)
        if not path.is_file():
            raise FileNotFoundError(f"배치 파일이 없습니다: {path}")
        topics = [
            line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if not topics:
            raise ValueError(f"{path} 에 주제가 없습니다. 한 줄에 하나씩 적으세요.")

        if args.input:  # YAML 을 기본값 삼아 주제만 갈아 끼운다
            base = load_input(args.input)
            return [base.model_copy(update={"topic": topic}) for topic in topics]

        missing = [n for n, v in
                   [("--format", args.format), ("--duration", args.duration),
                    ("--audience", args.audience)] if not v]
        if missing:
            raise ValueError(
                f"--batch 를 쓰려면 {', '.join(missing)} 를 지정하거나 입력 YAML 을 함께 주세요."
            )
        return [
            ScriptInput(topic=topic, format=args.format, duration_sec=args.duration,
                        audience=args.audience, tone=args.tone, cta=args.cta)
            for topic in topics
        ]

    if args.input:
        return [load_input(args.input)]

    missing = [n for n, v in
               [("--topic", args.topic), ("--format", args.format),
                ("--duration", args.duration), ("--audience", args.audience)] if not v]
    if missing:
        raise ValueError(
            "입력 YAML 경로를 주거나 " + ", ".join(missing) + " 를 지정하세요.\n"
            "예: python cli.py build --topic \"주제\" --format shorts "
            "--duration 30 --audience \"대상\""
        )
    return [ScriptInput(topic=args.topic, format=args.format, duration_sec=args.duration,
                        audience=args.audience, tone=args.tone, cta=args.cta)]


def _build_one(data: ScriptInput, args: argparse.Namespace, index: int, total: int) -> int:
    prefix = f"[{index}/{total}] " if total > 1 else ""
    low, high = DURATION_RANGE[data.format]
    print(f"{prefix}{data.topic} — {data.format_label} {data.duration_sec}초 (허용 {low}~{high})")

    if args.dry_run:
        from hook_script.sample_content import fake_ask

        generator = ScriptGenerator(
            data, model="dry-run", ask_fn=fake_ask, ai_label=not args.no_ai_label,
            hook_index=args.hook_index - 1, chapters=args.chapters,
        )
        print("      모의 실행 — Claude 를 부르지 않습니다 (비용 없음)")
    else:
        generator = ScriptGenerator(
            data, model=args.model, ai_label=not args.no_ai_label,
            hook_index=args.hook_index - 1, chapters=args.chapters,
        )
        print(f"      생성 중 (모델 {args.model}) — 후크 10개 → 본문 → 제목 → 체크리스트")

    result = generator.build()
    out_dir = write_outputs(result, Path(args.out))

    hook = result.chosen_hook
    print(f"      후크 {result.hook_index + 1}번 사용: {hook.get('text', '')}")
    print(f"      산출물: {out_dir}")

    if result.warnings:
        names = ", ".join(s.name for s in result.warnings)
        print(f"      ⚠ 확인 필요: {names} — checklist.md 를 보세요")
        return 2
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    if args.hook_index < 1:
        raise ValueError("--hook-index 는 1 이상이어야 합니다 (1 = 강도 1위)")

    inputs = _inputs_from_args(args)
    codes = [_build_one(data, args, i, len(inputs)) for i, data in enumerate(inputs, 1)]

    print()
    if any(code == 2 for code in codes):
        print("⚠ 일부 대본에 확인이 필요합니다. 각 폴더의 checklist.md 를 여세요.")
        return 2
    print(f"{len(inputs)}편을 만들었습니다.")
    print("촬영 전에 checklist.md 의 '사람이 반드시 추가할 것' 3가지를 반드시 채우세요.")
    if args.dry_run:
        print("※ 모의 실행 결과입니다. 본문은 예시 콘텐츠이므로 그대로 쓰지 마세요.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return cmd_build(args)
    except FileNotFoundError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    except LLMError as exc:
        print(f"생성 실패: {exc}", file=sys.stderr)
    except RuntimeError as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"입력이 올바르지 않습니다:\n{exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
