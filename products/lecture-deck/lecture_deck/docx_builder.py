"""worksheet.docx — 수강생용 실습지.

모듈마다 빈칸 문제 3개와 체크리스트를 넣는다. 강의 중에 손으로 쓰는 종이라
여백을 넉넉히 두고 글자를 크게 잡는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from lecture_deck.generator import DeckResult  # noqa: E402
from shared.ai_label import LABELS, add_metadata  # noqa: E402

__all__ = ["build_worksheet"]

BODY_FONT = "맑은 고딕"
_INK = RGBColor(0x1A, 0x1A, 0x1A)
_MUTED = RGBColor(0x6B, 0x72, 0x80)

#: 손으로 답을 쓸 밑줄.
BLANK = "＿" * 18


def _set_korean_font(target, name: str = BODY_FONT) -> None:
    element = target._element
    rpr = element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attribute in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attribute), name)


def _fix_settings_zoom(path: Path) -> None:
    """python-docx 기본 템플릿의 스키마 위반을 고친다 (w:zoom 에 w:percent 누락)."""
    import shutil
    import zipfile
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            archive.extractall(work)

        settings = work / "word" / "settings.xml"
        if not settings.is_file():
            return
        text = settings.read_text(encoding="utf-8")
        fixed = text.replace('<w:zoom w:val="bestFit"/>', '<w:zoom w:percent="100"/>')
        if fixed == text:
            return
        settings.write_text(fixed, encoding="utf-8")

        rebuilt = work / "rebuilt.docx"
        with zipfile.ZipFile(rebuilt, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                archive.write(work / name, name)
        shutil.move(str(rebuilt), str(path))


def _paragraph(document, text: str, *, size: float = 11, bold: bool = False,
               color: RGBColor = _INK, space_after: int = 8, align=None):
    paragraph = document.add_paragraph()
    if align is not None:
        paragraph.alignment = align
    paragraph.paragraph_format.space_after = Pt(space_after)
    paragraph.paragraph_format.line_spacing = 1.5
    run = paragraph.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    _set_korean_font(run)
    return paragraph


def build_worksheet(deck: DeckResult, out_path: str | Path) -> Path:
    """실습지를 만든다. 모듈마다 빈칸 문제 3개 + 체크리스트."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(11)
    normal.font.color.rgb = _INK
    _set_korean_font(normal)
    normal.paragraph_format.line_spacing = 1.5

    for name, size in (("Heading 1", 18), ("Heading 2", 13)):
        style = document.styles[name]
        style.font.name = BODY_FONT
        style.font.size = Pt(size)
        style.font.color.rgb = _INK
        style.font.bold = True
        _set_korean_font(style)

    section = document.sections[0]
    for attribute in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, attribute, Cm(2.5))

    # 표지
    document.add_heading(f"{deck.data.course_title} 실습지", level=1)
    _paragraph(document, f"{deck.data.audience} · {deck.data.duration_text}",
               size=10, color=_MUTED, space_after=18)
    _paragraph(document, "이름: ＿＿＿＿＿＿＿＿＿＿    날짜: ＿＿＿＿＿＿＿＿",
               size=11, space_after=6)
    _paragraph(
        document,
        "강의를 들으면서 빈칸을 채우세요. 모듈이 끝날 때마다 체크리스트를 확인합니다.",
        size=10, color=_MUTED, space_after=20,
    )

    for index, module in enumerate(deck.curriculum.modules, start=1):
        document.add_heading(f"모듈 {index}. {module.get('title', '')}", level=2)
        _paragraph(document, f"목표 — {module.get('goal', '')}", size=10,
                   color=_MUTED, space_after=4)
        _paragraph(document, f"시간 {module.get('minutes', 0)}분", size=10,
                   color=_MUTED, space_after=12)

        _paragraph(document, "빈칸 채우기", size=11, bold=True, space_after=8)
        concepts = module.get("concepts", [])
        for number in range(1, 4):
            concept = concepts[number - 1] if number <= len(concepts) else ""
            hint = f" (힌트: {concept})" if concept else ""
            _paragraph(document, f"{number}. {BLANK}{hint}", size=11, space_after=14)

        _paragraph(document, "실습", size=11, bold=True, space_after=6)
        _paragraph(document, module.get("practice", ""), size=11, space_after=6)
        for _ in range(2):
            _paragraph(document, BLANK * 2, size=11, space_after=12)

        _paragraph(document, "확인", size=11, bold=True, space_after=6)
        for item in (
            module.get("assessment", "배운 것을 설명할 수 있다"),
            "막힌 부분을 적어 두었다",
            "다음 모듈로 넘어갈 준비가 되었다",
        ):
            _paragraph(document, f"☐ {item}", size=11, space_after=4)

        document.add_paragraph()

    # 마무리
    document.add_heading("내일부터 할 것", level=2)
    _paragraph(document, "오늘 배운 것 중 내일 바로 할 한 가지를 적으세요.",
               size=10, color=_MUTED, space_after=10)
    for _ in range(3):
        _paragraph(document, BLANK * 2, size=11, space_after=14)

    document.add_paragraph()
    _paragraph(document, LABELS["ko"], size=9, color=_MUTED, space_after=2,
               align=WD_ALIGN_PARAGRAPH.LEFT)
    _paragraph(document, "초안을 생성형 AI로 작성한 뒤 강사가 검수·수정했습니다.",
               size=9, color=_MUTED)

    core = document.core_properties
    core.title = f"{deck.data.course_title} 실습지"
    core.subject = deck.data.audience
    core.author = deck.data.instructor or "미상"

    document.save(str(out_path))
    _fix_settings_zoom(out_path)
    add_metadata(out_path, tool="lecture-deck")
    return out_path
