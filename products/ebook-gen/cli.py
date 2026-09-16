"""전자책 원고 생성기 CLI — 3단계 워크플로우.

    1) python cli.py outline "주제" --audience "타깃" --pages 40
       → outputs/<slug>/outline.yaml          ← 여기서 손으로 고칩니다

    2) python cli.py write outputs/<slug>/outline.yaml
       → outputs/<slug>/chapters/ch01.md ...  ← 여기서도 손으로 고칩니다

    3) python cli.py build outputs/<slug>/
       → ebook.docx / sales_copy.md / cover_brief.md

각 단계에 `--dry-run` 을 붙이면 Claude 를 부르지 않고 예시 콘텐츠로 만듭니다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ebook_gen import docx_builder  # noqa: E402
from ebook_gen.generator import (  # noqa: E402
    EbookGenerator, parse_chapter_markdown, render_chapter_markdown,
)
from ebook_gen.schema import LENGTH_TOLERANCE, Outline, load_outline, save_outline  # noqa: E402
from shared import banned_phrases  # noqa: E402
from shared.ai_label import add_text_label  # noqa: E402
from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import LLMError  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = BASE_DIR / "outputs"


def _generator(args: argparse.Namespace) -> EbookGenerator:
    if args.dry_run:
        from ebook_gen.sample_content import fake_ask

        print("      모의 실행 — Claude 를 부르지 않습니다 (비용 없음)")
        return EbookGenerator(model="dry-run", ask_fn=fake_ask)
    return EbookGenerator(model=args.model)


# ------------------------------------------------------------------ 1단계
#: --input YAML 에 쓸 수 있는 항목.
OUTLINE_KEYS = ("topic", "audience", "pages", "author", "evidence")

#: --pages 를 아무 데서도 안 주면 쓰는 값.
DEFAULT_PAGES = 40


def _outline_args(args: argparse.Namespace) -> dict:
    """--input YAML 과 명령행 인자를 합친다. 명령행으로 준 값이 항상 이긴다."""
    from_file: dict = {}
    if args.input:
        path = Path(args.input)
        if not path.is_file():
            raise FileNotFoundError(f"입력 파일이 없습니다: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{path} 의 최상위는 키-값 매핑이어야 합니다")
        unknown = set(raw) - set(OUTLINE_KEYS)
        if unknown:
            raise ValueError(f"{path} 에 모르는 항목이 있습니다: {', '.join(sorted(unknown))}")
        from_file = {key: value for key, value in raw.items() if value not in (None, "", [])}

    # 명령행에서 실제로 준 값만 골라낸다 (안 주면 argparse 가 None 을 넣는다)
    from_args = {
        key: getattr(args, key)
        for key in OUTLINE_KEYS
        if getattr(args, key, None) not in (None, "", [])
    }

    values = {**from_file, **from_args}
    values.setdefault("pages", DEFAULT_PAGES)
    values.setdefault("author", "")
    values.setdefault("evidence", [])

    missing = [name for name in ("topic", "audience") if not values.get(name)]
    if missing:
        raise ValueError(
            f"{', '.join(missing)} 가 필요합니다. "
            "--input 으로 YAML 을 주거나 인자로 지정하세요.\n"
            '예: python cli.py outline "주제" --audience "대상" --pages 40'
        )
    return values


def cmd_outline(args: argparse.Namespace) -> int:
    values = _outline_args(args)
    print(f"[1단계] 목차 설계: {values['topic']}")
    generator = _generator(args)
    outline, warning = generator.build_outline(
        topic=values["topic"], audience=values["audience"], pages=values["pages"],
        author=values["author"], evidence=values["evidence"],
    )
    if warning:
        print(f"      ⚠ {warning}")

    out_dir = Path(args.out) / outline.slug
    path = save_outline(outline, out_dir / "outline.yaml")

    print(f"      챕터 {len(outline.chapters)}개 · 목표 {outline.target_chars:,}자 "
          f"(약 {outline.estimated_pages}쪽)")
    print(f"      → {path}")
    print()
    print("다음: outline.yaml 을 열어 제목·챕터를 손보신 뒤")
    print(f"      python cli.py write {path}")
    return 0


# ------------------------------------------------------------------ 2단계
def cmd_write(args: argparse.Namespace) -> int:
    outline_path = Path(args.outline)
    outline = load_outline(outline_path)
    out_dir = outline_path.parent
    chapters_dir = out_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    only = set(args.only or [])
    targets = [c for c in outline.chapters if not only or c.number in only]
    print(f"[2단계] 원고 집필: {outline.title} — 챕터 {len(targets)}개")

    generator = _generator(args)
    previous_summary = ""
    failures: list[int] = []
    warnings: list[str] = []
    total_chars = 0

    for plan in outline.chapters:
        path = chapters_dir / plan.filename

        if plan not in targets:
            # 이번에 안 쓰는 챕터라도 앞 챕터 요약은 이어져야 한다
            if path.is_file():
                try:
                    previous_summary = parse_chapter_markdown(
                        path.read_text(encoding="utf-8"), plan
                    ).summary_text
                except ValueError:
                    previous_summary = plan.key_message
            continue

        if path.is_file() and not args.overwrite and not only:
            print(f"      {plan.number:2}장 건너뜀 (이미 있음) — 다시 쓰려면 --overwrite")
            try:
                previous_summary = parse_chapter_markdown(
                    path.read_text(encoding="utf-8"), plan
                ).summary_text
            except ValueError:
                previous_summary = plan.key_message
            continue

        result = generator.write_chapter(outline, plan, previous_summary)
        if not result.ok:
            print(f"      {plan.number:2}장 실패 ({result.attempts}회 시도): {result.error}")
            failures.append(plan.number)
            continue

        draft = result.draft
        path.write_text(
            render_chapter_markdown(draft, ai_label=not args.no_ai_label),
            encoding="utf-8",
        )
        total_chars += draft.char_count
        previous_summary = draft.summary_text

        note = ""
        if result.banned:
            note = f"  ⚠ 금지 문구: {', '.join(result.banned)}"
            warnings.append(f"{plan.number}장 금지 문구 {', '.join(result.banned)}")
        elif result.length_off:
            note = "  ⚠ 분량 이탈"
            warnings.append(f"{plan.number}장 분량 {draft.char_count:,}자 "
                            f"(목표 {plan.target_chars:,}자)")
        print(f"      {plan.number:2}장 완료 {draft.char_count:,}자 "
              f"({result.attempts}회 시도){note}")

    print()
    if failures:
        print(f"⚠ 실패한 챕터: {', '.join(str(n) for n in failures)}")
        print(f"  해당 챕터만 다시: python cli.py write {outline_path} "
              f"--only {' '.join(str(n) for n in failures)}")
        return 1

    if total_chars:
        low = int(outline.target_chars * (1 - LENGTH_TOLERANCE))
        high = int(outline.target_chars * (1 + LENGTH_TOLERANCE))
        mark = "✓" if low <= total_chars <= high else "⚠"
        print(f"{mark} 총 {total_chars:,}자 (목표 {outline.target_chars:,}자, "
              f"허용 {low:,}~{high:,}자)")
    if warnings:
        print("⚠ 확인 필요:")
        for item in warnings:
            print(f"  - {item}")

    print()
    print(f"다음: chapters/ 안의 원고를 읽고 고치신 뒤")
    print(f"      python cli.py build {out_dir}")
    return 2 if warnings else 0


# ------------------------------------------------------------------ 3단계
def _write_sales_copy(outline: Outline, data: dict, out_dir: Path,
                      ai_label: bool) -> tuple[Path, list[str]]:
    lines = [
        f"# 판매용 소개글 — {outline.title}",
        "",
        "## 소개글 (크몽·인스타 본문)",
        "",
        str(data.get("intro", "")).strip(),
        "",
        "## 목차 요약",
        "",
        str(data.get("toc_summary", "")).strip(),
        "",
        "## 이런 분께 맞습니다",
        "",
    ]
    lines += [f"- {item}" for item in data.get("for_whom", [])]
    lines += ["", "## 이런 분께는 맞지 않습니다", ""]
    lines += [f"- {item}" for item in data.get("not_for_whom", [])]
    lines += ["", "## 가격 제안 3안", "",
              "| 플랜 | 가격 | 구성 | 왜 이 가격인가 |", "|---|---|---|---|"]
    for plan in data.get("pricing", []):
        includes = "<br>".join(plan.get("includes", []))
        lines.append(
            f"| {plan.get('plan', '')} | {int(plan.get('price', 0)):,}원 | "
            f"{includes} | {plan.get('reason', '')} |"
        )
    lines += [
        "",
        "## 올리기 전에",
        "",
        "- [ ] 성과를 단정하는 표현이 없는지 다시 읽었다",
        "- [ ] 목차 요약이 실제 목차와 일치한다",
        "- [ ] 가격과 구성이 실제로 드릴 수 있는 것과 같다",
        "- [ ] 환불 정책과 사업자 정보를 상세페이지에 넣었다",
        "",
    ]
    text = "\n".join(lines)
    if ai_label:
        text = add_text_label(text) + "\n"

    path = out_dir / "sales_copy.md"
    path.write_text(text, encoding="utf-8")
    return path, banned_phrases.check(text)


def _write_cover_brief(outline: Outline, data: dict, out_dir: Path,
                       ai_label: bool) -> Path:
    lines = [
        f"# 표지 디자인 지시서 — {outline.title}",
        "",
        f"- 부제: {outline.subtitle}",
        f"- 독자: {outline.audience}",
        f"- 저자: {outline.author or '(표지에 넣을 이름을 정하세요)'}",
        "",
        "## 컨셉",
        "",
        str(data.get("concept", "")).strip(),
        "",
        "## 분위기 키워드",
        "",
        ", ".join(data.get("mood", [])),
        "",
        "## 색",
        "",
        "| 이름 | 코드 | 쓰는 곳 |",
        "|---|---|---|",
    ]
    for color in data.get("colors", []):
        lines.append(
            f"| {color.get('name', '')} | `{color.get('hex', '')}` | {color.get('use', '')} |"
        )
    lines += [
        "", "## 타이포그래피", "", str(data.get("typography", "")).strip(),
        "", "## 배치", "", str(data.get("layout", "")).strip(),
        "", "## 이미지 생성 프롬프트", "",
        "이미지 생성 도구에 그대로 넣으세요. 글자는 나중에 따로 얹습니다.",
        "", "```", str(data.get("image_prompt", "")).strip(), "```",
        "", "## 피해야 할 것", "",
    ]
    lines += [f"- {item}" for item in data.get("avoid", [])]
    lines += [
        "",
        "## 확인",
        "",
        "- [ ] 썸네일 크기(200px 폭)로 줄였을 때 제목이 읽힌다",
        "- [ ] 생성한 이미지에 글자가 섞여 있지 않다",
        "- [ ] 쓰는 글꼴의 라이선스가 상업적 사용을 허용한다",
        "",
    ]
    text = "\n".join(lines)
    if ai_label:
        text = add_text_label(text) + "\n"

    path = out_dir / "cover_brief.md"
    path.write_text(text, encoding="utf-8")
    return path


def cmd_build(args: argparse.Namespace) -> int:
    out_dir = Path(args.directory)
    outline = load_outline(out_dir / "outline.yaml")
    chapters_dir = out_dir / "chapters"

    print(f"[3단계] docx 조립: {outline.title}")

    drafts = []
    missing = []
    for plan in outline.chapters:
        path = chapters_dir / plan.filename
        if not path.is_file():
            missing.append(plan.filename)
            continue
        drafts.append(parse_chapter_markdown(path.read_text(encoding="utf-8"), plan))

    if missing:
        print(f"오류: 원고가 없습니다 — {', '.join(missing)}", file=sys.stderr)
        print(f"      python cli.py write {out_dir / 'outline.yaml'}", file=sys.stderr)
        return 1

    total_chars = sum(draft.char_count for draft in drafts)
    model = "dry-run" if args.dry_run else args.model
    docx_path = docx_builder.build_docx(
        outline, drafts, out_dir / "ebook.docx", model=model
    )
    print(f"      {docx_path.name} — 챕터 {len(drafts)}개 · {total_chars:,}자")

    generator = _generator(args)
    sales_path, banned = _write_sales_copy(
        outline, generator.sales_copy(outline), out_dir, not args.no_ai_label
    )
    cover_path = _write_cover_brief(
        outline, generator.cover_brief(outline), out_dir, not args.no_ai_label
    )
    print(f"      {sales_path.name}")
    print(f"      {cover_path.name}")

    low = int(outline.target_chars * (1 - LENGTH_TOLERANCE))
    high = int(outline.target_chars * (1 + LENGTH_TOLERANCE))
    in_range = low <= total_chars <= high

    print()
    print(f"{'✓' if in_range else '⚠'} 분량 {total_chars:,}자 "
          f"(목표 {outline.target_chars:,}자, 허용 {low:,}~{high:,}자)")
    if banned:
        print(f"⚠ 판매글에 금지 문구가 남았습니다: {', '.join(banned)}")
    print()
    print("Word 에서 열어 전체 선택(Ctrl+A) 후 F9 를 누르면 목차 쪽 번호가 채워집니다.")
    if args.dry_run:
        print("※ 모의 실행 결과입니다. 본문은 예시 콘텐츠이므로 그대로 쓰지 마세요.")
    return 2 if (banned or not in_range) else 0


# ------------------------------------------------------------------ 진입점
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="전자책 원고 생성기 — 목차 → 원고 → docx 3단계 (사람 검수 전제)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Claude 모델 (기본: {DEFAULT_MODEL})")
        sp.add_argument("--no-ai-label", action="store_true",
                        help="AI 생성물 표시를 끕니다")
        sp.add_argument("--dry-run", action="store_true",
                        help="Claude 를 부르지 않고 예시 콘텐츠로 (비용 없음)")

    one = sub.add_parser("outline", help="1단계: 주제로 목차를 만듭니다")
    one.add_argument("topic", nargs="?", help="전자책 주제 (--input 을 쓰면 생략)")
    one.add_argument("--input", help="topic·audience·pages 가 담긴 YAML 경로")
    one.add_argument("--audience", help="누가 읽는 책인지 한 줄")
    one.add_argument("--pages", type=int, help="목표 쪽수 (10~80, 기본 40)")
    one.add_argument("--author", default="", help="표지에 넣을 저자명")
    one.add_argument("--evidence", nargs="*", default=[],
                     help="참고할 사실 자료. 없으면 생략하세요")
    one.add_argument("--out", default=str(DEFAULT_OUT),
                     help=f"산출물 상위 폴더 (기본: {DEFAULT_OUT})")
    common(one)

    two = sub.add_parser("write", help="2단계: 목차로 챕터 원고를 씁니다")
    two.add_argument("outline", help="outline.yaml 경로")
    two.add_argument("--only", nargs="*", type=int, metavar="N",
                     help="이 챕터만 다시 씁니다. 예: --only 3 7")
    two.add_argument("--overwrite", action="store_true",
                     help="이미 있는 원고도 다시 씁니다")
    common(two)

    three = sub.add_parser("build", help="3단계: 원고를 docx 로 조립합니다")
    three.add_argument("directory", help="outputs/<slug>/ 폴더 경로")
    common(three)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = {"outline": cmd_outline, "write": cmd_write, "build": cmd_build}[args.command]
    try:
        return handler(args)
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
