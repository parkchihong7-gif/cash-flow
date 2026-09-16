"""크몽 상세페이지 카피 생성기 CLI.

    python cli.py build service_input.yaml
    python cli.py build service_input.yaml --dry-run

산출물 5종을 만들고 등록 전 점검 결과를 보여 준다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kmong_copy.generator import KmongGenerator  # noqa: E402
from kmong_copy.schema import load_input  # noqa: E402
from kmong_copy.writers import write_outputs  # noqa: E402
from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import LLMError  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = BASE_DIR / "outputs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="크몽 상세페이지·패키지·문의 응답 초안 생성기 (등록 전 판매자 검수 필수)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="등록 자료 5종을 만듭니다")
    build.add_argument("input", help="입력 YAML 경로 (예: service_input.yaml)")
    build.add_argument("--model", default=DEFAULT_MODEL,
                       help=f"Claude 모델 (기본: {DEFAULT_MODEL})")
    build.add_argument("--no-ai-label", action="store_true",
                       help="AI 생성물 표시를 끕니다")
    build.add_argument("--out", default=str(DEFAULT_OUT),
                       help=f"산출물 상위 폴더 (기본: {DEFAULT_OUT})")
    build.add_argument("--dry-run", action="store_true",
                       help="Claude 를 부르지 않고 예시 콘텐츠로 (비용 없음)")
    return parser


def cmd_build(args: argparse.Namespace) -> int:
    data = load_input(args.input)
    print(f"[1/2] 카피 생성: {data.service_name} ({data.category})")
    print(f"      가격 {data.price_text('BASIC')} / {data.price_text('STANDARD')} "
          f"/ {data.price_text('PREMIUM')} · 기본 {data.turnaround_days}일")
    if not data.has_proof:
        print("      실적 자료가 없어 성과 자리는 '사례 준비 중'으로 둡니다.")

    if args.dry_run:
        from kmong_copy.sample_content import fake_ask

        print("      모의 실행 — Claude 를 부르지 않습니다 (비용 없음)")
        generator = KmongGenerator(data, model="dry-run", ask_fn=fake_ask)
    else:
        print(f"      모델 {args.model} — 상세페이지 → 패키지·제목 → 문의 응답")
        generator = KmongGenerator(data, model=args.model)

    result = generator.build()

    print("[2/2] 산출물 쓰기")
    out_dir, passed = write_outputs(result, Path(args.out), ai_label=not args.no_ai_label)
    for name in ("detail_page.md", "packages.json", "title_variants.json",
                 "inquiry_scripts.md", "compliance_report.md"):
        print(f"      {name}")

    print()
    for section in result.sections.values():
        marks = []
        if section.banned:
            marks.append(f"금지 문구 {', '.join(section.banned)}")
        if section.contact:
            marks.append("외부 연락처 " + ", ".join(sorted({f.label for f in section.contact})))
        if section.length_fixes:
            marks.append(f"길이 {len(section.length_fixes)}건 자동 보정")
        status = " · ".join(marks) if marks else "통과"
        print(f"  {section.name:9} {section.attempts}회 시도 — {status}")

    print()
    if passed:
        print("✓ 등록 전 점검을 통과했습니다.")
    else:
        print("⚠ 확인이 필요합니다. compliance_report.md 를 열어 ⚠️ 항목을 고치세요.")

    print()
    print("등록 순서는 README 의 '크몽 등록 순서 매핑표'를 보세요.")
    print("포트폴리오 이미지와 환불 정책은 판매자가 직접 채워야 합니다.")
    if args.dry_run:
        print("※ 모의 실행 결과입니다. 본문은 예시 콘텐츠이므로 그대로 쓰지 마세요.")
    return 0 if passed else 2


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
