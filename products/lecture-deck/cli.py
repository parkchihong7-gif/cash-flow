"""강의 슬라이드 생성기 CLI.

    python cli.py build deck_input.yaml          # 커리큘럼 확인 후 진행 여부를 물어봅니다
    python cli.py build deck_input.yaml --yes    # 물어보지 않고 끝까지
    python cli.py build deck_input.yaml --dry-run

흐름
    커리큘럼 생성 → (사람 확인) → 모듈별 슬라이드 → pptx·docx·json 렌더
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lecture_deck import docx_builder, pptx_builder  # noqa: E402
from lecture_deck.generator import DeckGenerator, DeckResult, assemble_deck  # noqa: E402
from lecture_deck.schema import (  # noqa: E402
    MAX_BODY_LINES, MAX_LINE_CHARS, NOTE_MIN_CHARS, load_input,
)
from shared.ai_label import add_text_label  # noqa: E402
from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import LLMError  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = BASE_DIR / "outputs"


# ------------------------------------------------------------------ 산출물
def write_curriculum(deck: DeckResult, out_dir: Path, ai_label: bool = True) -> Path:
    """curriculum.md — 모듈별 목표·시간·실습·평가 기준."""
    data = deck.data
    lines = [
        f"# {data.course_title} 커리큘럼",
        "",
        f"- 수강생: {data.audience}",
        f"- 전체 시간: {data.duration_text} ({data.total_minutes}분)",
        f"- 모듈: {len(deck.curriculum.modules)}개",
        f"- 슬라이드: {deck.slide_count}장",
        "",
        "> 초안입니다. 강의 전에 반드시 강사가 읽고 고치세요.",
        "",
        "| # | 모듈 | 시간 | 학습 목표 |",
        "|---|---|---|---|",
    ]
    for index, module in enumerate(deck.curriculum.modules, start=1):
        lines.append(
            f"| {index} | {module.get('title', '')} | {module.get('minutes', 0)}분 | "
            f"{module.get('goal', '')} |"
        )

    total = deck.curriculum.total_minutes
    if total != data.total_minutes:
        lines += [
            "",
            f"> ⚠ 모듈 시간 합계가 {total}분으로 목표 {data.total_minutes}분과 다릅니다. "
            "쉬는 시간을 감안했거나 배분이 어긋난 것이니 확인하세요.",
        ]

    lines.append("")
    for index, module in enumerate(deck.curriculum.modules, start=1):
        lines += [
            f"## {index}. {module.get('title', '')}",
            "",
            f"**학습 목표** — {module.get('goal', '')}",
            "",
            f"**소요 시간** — {module.get('minutes', 0)}분",
            "",
            "**핵심 개념**",
            "",
        ]
        lines += [f"- {concept}" for concept in module.get("concepts", [])]
        lines += [
            "",
            "**실습 과제**",
            "",
            module.get("practice", ""),
            "",
            "**평가 기준**",
            "",
            module.get("assessment", ""),
            "",
        ]

    lines += [
        "## 강의 전 확인",
        "",
        "- [ ] 모듈 시간 합계가 실제 강의 시간과 맞는가 (쉬는 시간 포함)",
        "- [ ] 실습 과제를 그 시간 안에 끝낼 수 있는가",
        "- [ ] 슬라이드의 `[강사가 채울 곳]` 표시를 모두 처리했는가",
        "- [ ] 발표자 노트를 읽어 보고 내 말투로 고쳤는가",
        "",
    ]

    text = "\n".join(lines)
    if ai_label:
        text = add_text_label(text) + "\n"

    path = out_dir / "curriculum.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_outline_json(deck: DeckResult, out_dir: Path) -> Path:
    """deck_outline.json — 다른 도구에서 재활용할 수 있는 슬라이드 목록."""
    payload = {
        "course_title": deck.data.course_title,
        "audience": deck.data.audience,
        "total_minutes": deck.data.total_minutes,
        "style": deck.data.style,
        "generated_at": deck.generated_at.isoformat(),
        "model": deck.model,
        "limits": {
            "max_body_lines": MAX_BODY_LINES,
            "max_line_chars": MAX_LINE_CHARS,
            "note_min_chars": NOTE_MIN_CHARS,
        },
        "modules": deck.curriculum.modules,
        "slides": [
            {
                "index": index,
                "kind": slide.kind,
                "module": slide.module_number,
                "title": slide.title,
                "subtitle": slide.subtitle,
                "body": slide.body,
                "note": slide.note,
            }
            for index, slide in enumerate(deck.slides, start=1)
        ],
    }
    path = out_dir / "deck_outline.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


# ------------------------------------------------------------------ 실행
def _confirm_curriculum(deck_generator: DeckGenerator, curriculum, assume_yes: bool) -> bool:
    """커리큘럼을 보여 주고 계속할지 묻는다. --yes 면 건너뛴다."""
    print()
    print("  ── 커리큘럼 ──────────────────────────────")
    for index, module in enumerate(curriculum.modules, start=1):
        print(f"  {index}. {module.get('title', '')}  ({module.get('minutes', 0)}분)")
        print(f"     목표: {module.get('goal', '')}")
        concepts = ", ".join(module.get("concepts", []))
        if concepts:
            print(f"     개념: {concepts}")
    total = curriculum.total_minutes
    target = deck_generator.data.total_minutes
    mark = "" if total == target else f"  ⚠ 목표 {target}분과 다릅니다"
    print(f"  ─────────────────────── 합계 {total}분{mark}")
    print()

    if assume_yes:
        return True

    try:
        answer = input("  이 커리큘럼으로 슬라이드를 만들까요? [Y/n] ").strip().lower()
    except EOFError:
        # 터미널이 아닌 곳(대시보드 등)에서 실행되면 묻지 않고 진행한다
        print("  (입력을 받을 수 없어 그대로 진행합니다)")
        return True
    return answer in ("", "y", "yes", "ㅇ")


def cmd_build(args: argparse.Namespace) -> int:
    data = load_input(args.input)
    print(f"[1/3] 커리큘럼 설계: {data.course_title} "
          f"({data.duration_text}, {data.style} 스타일)")

    if args.dry_run:
        from lecture_deck.sample_content import fake_ask

        print("      모의 실행 — Claude 를 부르지 않습니다 (비용 없음)")
        generator = DeckGenerator(data, model="dry-run", ask_fn=fake_ask)
    else:
        generator = DeckGenerator(data, model=args.model)

    curriculum = generator.build_curriculum()
    if not curriculum.modules:
        print("오류: 커리큘럼을 만들지 못했습니다.", file=sys.stderr)
        return 1

    if not _confirm_curriculum(generator, curriculum, args.yes):
        print("중단했습니다. deck_input.yaml 의 모듈을 고쳐 다시 실행하세요.")
        return 0

    print(f"[2/3] 슬라이드 집필 — 모듈 {len(curriculum.modules)}개")
    module_slides: dict[int, list] = {}
    failures: list[int] = []
    warnings: list[str] = []
    previous_summary = ""

    for index in range(1, len(curriculum.modules) + 1):
        result = generator.write_module(curriculum, index, previous_summary)
        if not result.ok:
            print(f"      {index}번 모듈 실패 ({result.attempts}회 시도): {result.error}")
            failures.append(index)
            continue

        module_slides[index] = result.slides
        summary = next((s for s in result.slides if s.kind == "summary"), None)
        previous_summary = " / ".join(summary.body) if summary else ""

        note = ""
        if result.banned:
            note = f"  ⚠ 금지 문구: {', '.join(result.banned)}"
            warnings.append(f"{index}번 모듈 금지 문구 {', '.join(result.banned)}")
        print(f"      {index}번 모듈 슬라이드 {len(result.slides)}장 "
              f"({result.attempts}회 시도){note}")

    if failures:
        print(f"\n⚠ 실패한 모듈: {', '.join(str(n) for n in failures)}")
        print("  deck_input.yaml 의 해당 모듈 제목을 바꿔 다시 실행해 보세요.")
        return 1

    deck = assemble_deck(data, curriculum, module_slides, generator.model)
    deck.warnings.extend(warnings)

    out_dir = Path(args.out) / data.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[3/3] 렌더링 — 슬라이드 {deck.slide_count}장")
    write_curriculum(deck, out_dir, ai_label=not args.no_ai_label)
    pptx_builder.build_pptx(deck, out_dir / "deck.pptx")
    docx_builder.build_worksheet(deck, out_dir / "worksheet.docx")
    write_outline_json(deck, out_dir)
    for name in ("curriculum.md", "deck.pptx", "worksheet.docx", "deck_outline.json"):
        print(f"      {name}")

    empty_notes = sum(1 for slide in deck.slides if not slide.note.strip())
    overflowing = sum(1 for slide in deck.slides if slide.overflows)

    print()
    print(f"{'✓' if not overflowing else '⚠'} 본문 규칙 "
          f"({MAX_BODY_LINES}줄·{MAX_LINE_CHARS}자): "
          f"{'전부 통과' if not overflowing else f'{overflowing}장 위반'}")
    print(f"{'✓' if not empty_notes else '⚠'} 발표자 노트: "
          f"{'빈 슬라이드 없음' if not empty_notes else f'{empty_notes}장 비어 있음'}")

    if deck.warnings:
        print()
        for item in deck.warnings:
            print(f"⚠ {item}")

    print()
    print("PowerPoint 에서 열어 발표자 노트를 읽고 본인 말투로 고치세요.")
    if args.dry_run:
        print("※ 모의 실행 결과입니다. 본문은 예시 콘텐츠이므로 그대로 쓰지 마세요.")
    return 2 if (deck.warnings or overflowing or empty_notes) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="강의 커리큘럼 → 슬라이드 pptx + 발표자 노트 (강의 전 강사 검수 필수)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="커리큘럼과 슬라이드를 만듭니다")
    build.add_argument("input", help="입력 YAML 경로 (예: deck_input.yaml)")
    build.add_argument("--yes", "-y", action="store_true",
                       help="커리큘럼 확인 단계를 건너뜁니다")
    build.add_argument("--model", default=DEFAULT_MODEL,
                       help=f"Claude 모델 (기본: {DEFAULT_MODEL})")
    build.add_argument("--no-ai-label", action="store_true",
                       help="AI 생성물 표시를 끕니다")
    build.add_argument("--out", default=str(DEFAULT_OUT),
                       help=f"산출물 상위 폴더 (기본: {DEFAULT_OUT})")
    build.add_argument("--dry-run", action="store_true",
                       help="Claude 를 부르지 않고 예시 콘텐츠로 (비용 없음)")
    return parser


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
