"""퍼널 빌더 CLI.

    python cli.py build funnel_input.yaml [--model MODEL] [--no-ai-label] [--out DIR]

입력 YAML 하나로 outputs/<slug>/ 에 산출물 5종을 만든다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from generator import FunnelGenerator, write_outputs
from schema import load_input

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import LLMError  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = BASE_DIR / "outputs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="강의·전자책 판매 퍼널 생성기 (랜딩 + 이메일 5통 + 리드매그넷 목차)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="YAML 입력으로 퍼널 산출물을 만든다")
    build.add_argument("input", help="입력 YAML 경로 (예: funnel_input.yaml)")
    build.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Claude 모델 ID (기본: {DEFAULT_MODEL})"
    )
    build.add_argument(
        "--no-ai-label",
        action="store_true",
        help="AI 생성물 표시를 끈다. 인공지능기본법 표시 의무를 직접 처리할 때만 쓴다.",
    )
    build.add_argument(
        "--out", default=str(DEFAULT_OUT), help=f"산출물 상위 폴더 (기본: {DEFAULT_OUT})"
    )
    build.add_argument(
        "--dry-run",
        action="store_true",
        help="Claude 를 부르지 않고 예시 콘텐츠로 산출물 형태만 만든다 (API 비용 없음)",
    )
    return parser


def cmd_build(args: argparse.Namespace) -> int:
    data = load_input(args.input)
    print(f"[1/3] 입력 확인: {data.product_name} ({data.price_text})")
    if not data.proof:
        print("      proof 가 비어 있어 랜딩의 증거 섹션은 생성하지 않습니다.")

    if args.dry_run:
        from sample_content import fake_ask

        print("[2/3] 모의 실행 — Claude 를 부르지 않고 예시 콘텐츠로 만듭니다 (비용 없음)")
        generator = FunnelGenerator(
            data, model="dry-run", ask_fn=fake_ask, ai_label=not args.no_ai_label
        )
    else:
        print(f"[2/3] 섹션 생성 중 (모델 {args.model}) — 헤드라인 → 본문 → FAQ → 목차 → 이메일")
        generator = FunnelGenerator(data, model=args.model, ai_label=not args.no_ai_label)
    result = generator.build()

    out_dir = write_outputs(result, Path(args.out))
    print(f"[3/3] 산출물 5종을 만들었습니다: {out_dir}")
    for name in ("landing.html", "emails/", "lead_magnet_outline.md",
                 "copy_variants.json", "build_report.md"):
        print(f"      - {name}")

    if result.warnings:
        names = ", ".join(section.name for section in result.warnings)
        print(f"\n⚠ 금지 문구가 남은 섹션이 있습니다: {names}")
        print("  build_report.md 를 열어 해당 부분을 직접 고친 뒤 발행하세요.")
        return 2

    print("\n금지 문구 검사를 모두 통과했습니다. 발행 전 사람이 한 번 읽어보세요.")
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
    except RuntimeError as exc:  # API 키 누락 등 설정 문제
        print(f"설정 오류: {exc}", file=sys.stderr)
    except ValueError as exc:  # pydantic ValidationError 포함
        print(f"입력이 올바르지 않습니다:\n{exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
