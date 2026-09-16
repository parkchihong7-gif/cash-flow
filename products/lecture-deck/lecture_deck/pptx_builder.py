"""deck.pptx 조립 — python-pptx.

규격
    16:9 (13.333in × 7.5in)
    본문 맑은 고딕, 제목 36~40pt / 본문 18pt
    도형은 python-pptx 기본 도형만. 외부 이미지에 의존하지 않는다.

디자인 원칙
    - 제목·마무리 슬라이드는 진한 배경, 본문은 밝은 배경 (샌드위치 구조)
    - 제목 밑줄이나 장식용 색 띠를 쓰지 않는다. AI가 만든 티가 나는 대표 요소다
    - 반복 모티프 하나: 개념 슬라이드의 번호 원

한글 글꼴은 `a:ea` (eastAsia) 를 따로 지정해야 적용된다. python-pptx 가 그 속성을
노출하지 않으므로 :func:`_set_korean_font` 에서 XML 을 건드린다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from lecture_deck.generator import DeckResult, Slide  # noqa: E402
from lecture_deck.schema import STYLES  # noqa: E402

__all__ = ["build_pptx", "load_palette", "BODY_FONT", "SLIDE_WIDTH", "SLIDE_HEIGHT"]

BASE_DIR = Path(__file__).resolve().parents[1]
PALETTES_PATH = BASE_DIR / "templates" / "palettes.json"

BODY_FONT = "맑은 고딕"

#: 16:9.
SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)

MARGIN = Inches(0.9)
CONTENT_WIDTH = SLIDE_WIDTH - MARGIN * 2


def load_palette(style: str) -> dict[str, str]:
    """스타일 이름으로 색상 팔레트를 읽는다."""
    palettes = json.loads(PALETTES_PATH.read_text(encoding="utf-8"))
    if style not in palettes:
        raise ValueError(
            f"모르는 스타일입니다: {style} (가능: {', '.join(STYLES)})"
        )
    return palettes[style]


def _rgb(hex_value: str) -> RGBColor:
    return RGBColor.from_string(hex_value.lstrip("#").upper())


def _set_korean_font(run, name: str = BODY_FONT) -> None:
    """한글이 지정한 글꼴로 나오게 eastAsia 속성까지 설정한다."""
    run.font.name = name
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        element = rpr.find(qn(tag))
        if element is None:
            element = rpr.makeelement(qn(tag), {})
            rpr.append(element)
        element.set("typeface", name)


def _fill_background(slide, color: str) -> None:
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(color)


def _textbox(
    slide, left, top, width, height, *, anchor=MSO_ANCHOR.TOP,
):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = frame.margin_right = 0
    frame.margin_top = frame.margin_bottom = 0
    return frame


def _write(
    frame, lines: list[str], *, size: float, color: str, bold: bool = False,
    align=PP_ALIGN.LEFT, space_after: float = 10, line_spacing: float = 1.25,
    first: bool = True,
) -> None:
    """텍스트 프레임에 줄을 쓴다. 첫 문단은 기존 것을 재사용한다."""
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if (first and index == 0) else frame.add_paragraph()
        paragraph.alignment = align
        paragraph.space_after = Pt(space_after)
        paragraph.line_spacing = line_spacing
        run = paragraph.add_run()
        run.text = line
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = _rgb(color)
        _set_korean_font(run)


def _add_slide(presentation):
    """빈 레이아웃(6번)에 슬라이드를 추가한다. 자리 표시자를 쓰지 않는다."""
    return presentation.slides.add_slide(presentation.slide_layouts[6])


def _add_note(slide, text: str) -> None:
    slide.notes_slide.notes_text_frame.text = text


def _number_badge(slide, number: int, left, top, palette: dict[str, str],
                  size=Inches(0.62)) -> None:
    """개념 슬라이드의 번호 원. 이 덱의 반복 모티프."""
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, size, size)
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(palette["accent"])
    shape.line.fill.background()
    shape.shadow.inherit = False

    frame = shape.text_frame
    frame.margin_left = frame.margin_right = 0
    frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    paragraph = frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.CENTER
    run = paragraph.add_run()
    run.text = str(number)
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = _rgb(palette["on_accent"])
    _set_korean_font(run)


def _card(slide, left, top, width, height, palette: dict[str, str]):
    """본문을 얹을 연한 패널. 테두리 줄무늬 대신 배경 톤으로 구분한다."""
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(palette["panel_bg"])
    shape.line.fill.background()
    shape.shadow.inherit = False
    shape.adjustments[0] = 0.04
    return shape


def _footer(slide, text: str, palette: dict[str, str], on_dark: bool = False) -> None:
    frame = _textbox(
        slide, MARGIN, SLIDE_HEIGHT - Inches(0.62), CONTENT_WIDTH, Inches(0.3)
    )
    _write(
        frame, [text], size=10,
        color=palette["muted_on_dark"] if on_dark else palette["muted"],
        space_after=0,
    )


# ------------------------------------------------------------------ 슬라이드
def _render_cover(presentation, slide: Slide, palette, deck) -> None:
    s = _add_slide(presentation)
    _fill_background(s, palette["dark_bg"])

    frame = _textbox(s, MARGIN, Inches(2.5), CONTENT_WIDTH, Inches(2.2))
    _write(frame, [slide.title], size=44, color=palette["ink_on_dark"], bold=True,
           space_after=18, line_spacing=1.15)
    _write(frame, [slide.subtitle], size=18, color=palette["muted_on_dark"],
           space_after=0, first=False)

    _footer(s, deck.generated_at.strftime("%Y년 %m월"), palette, on_dark=True)
    _add_note(s, slide.note)


def _render_section(presentation, slide: Slide, palette, deck, label: str) -> None:
    """모듈 표지 — 진한 배경에 번호와 제목만."""
    s = _add_slide(presentation)
    _fill_background(s, palette["dark_bg"])

    frame = _textbox(s, MARGIN, Inches(2.2), CONTENT_WIDTH, Inches(0.6))
    _write(frame, [label], size=14, color=palette["muted_on_dark"], bold=True,
           space_after=0)

    frame = _textbox(s, MARGIN, Inches(2.9), CONTENT_WIDTH, Inches(1.6))
    _write(frame, [slide.title], size=40, color=palette["ink_on_dark"], bold=True,
           space_after=14, line_spacing=1.15)

    if slide.body:
        frame = _textbox(s, MARGIN, Inches(4.5), CONTENT_WIDTH, Inches(1.4))
        _write(frame, slide.body, size=18, color=palette["muted_on_dark"], space_after=6)

    _footer(s, slide.subtitle, palette, on_dark=True)
    _add_note(s, slide.note)


def _render_content(presentation, slide: Slide, palette, deck, badge: int | None) -> None:
    """개념·실습·요약·개요 — 밝은 배경에 제목 + 카드 본문."""
    s = _add_slide(presentation)
    _fill_background(s, palette["light_bg"])

    title_left = MARGIN
    if badge is not None:
        _number_badge(s, badge, MARGIN, Inches(0.78), palette)
        title_left = MARGIN + Inches(0.92)

    frame = _textbox(s, title_left, Inches(0.8), CONTENT_WIDTH - Inches(0.92), Inches(1.0))
    _write(frame, [slide.title], size=36, color=palette["ink"], bold=True,
           space_after=0, line_spacing=1.1)

    if slide.body:
        card_top = Inches(2.1)
        card_height = Inches(0.62) * len(slide.body) + Inches(0.9)
        _card(s, MARGIN, card_top, CONTENT_WIDTH, card_height, palette)

        frame = _textbox(
            s, MARGIN + Inches(0.6), card_top + Inches(0.45),
            CONTENT_WIDTH - Inches(1.2), card_height - Inches(0.9),
        )
        _write(frame, slide.body, size=20, color=palette["ink"], space_after=12,
               line_spacing=1.2)

    _footer(s, deck.data.course_title, palette)
    _add_note(s, slide.note)


def _render_closing(presentation, slide: Slide, palette, deck) -> None:
    s = _add_slide(presentation)
    _fill_background(s, palette["dark_bg"])

    frame = _textbox(s, MARGIN, Inches(1.9), CONTENT_WIDTH, Inches(1.2))
    _write(frame, [slide.title], size=40, color=palette["ink_on_dark"], bold=True,
           space_after=0, line_spacing=1.15)

    if slide.body:
        frame = _textbox(s, MARGIN, Inches(3.4), CONTENT_WIDTH, Inches(2.4))
        _write(frame, slide.body, size=20, color=palette["muted_on_dark"],
               space_after=14)

    _footer(s, deck.data.course_title, palette, on_dark=True)
    _add_note(s, slide.note)


def build_pptx(deck: DeckResult, out_path: str | Path) -> Path:
    """덱을 pptx 로 쓴다.

    Args:
        deck: 조립된 덱.
        out_path: 저장할 .pptx 경로.

    Returns:
        만들어진 파일 경로.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    palette = load_palette(deck.data.style)
    presentation = Presentation()
    presentation.slide_width = SLIDE_WIDTH
    presentation.slide_height = SLIDE_HEIGHT

    concept_index = 0
    for slide in deck.slides:
        if slide.kind == "cover":
            _render_cover(presentation, slide, palette, deck)
        elif slide.kind == "module":
            concept_index = 0
            _render_section(
                presentation, slide, palette, deck,
                f"모듈 {slide.module_number}",
            )
        elif slide.kind in {"closing", "ai_notice"}:
            _render_closing(presentation, slide, palette, deck)
        elif slide.kind == "concept":
            concept_index += 1
            _render_content(presentation, slide, palette, deck, concept_index)
        else:  # instructor, agenda, practice, summary
            _render_content(presentation, slide, palette, deck, None)

    core = presentation.core_properties
    core.title = deck.data.course_title
    core.subject = deck.data.audience
    core.author = deck.data.instructor or "미상"
    core.keywords = ", ".join(
        m.get("title", "") for m in deck.curriculum.modules[:5]
    )

    presentation.save(str(out_path))
    return out_path
