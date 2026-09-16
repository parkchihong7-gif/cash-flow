"""ebook.docx 조립 — python-docx.

서식 규격 (사양 고정값)
    본문      맑은 고딕 10.5pt, 줄간격 1.5
    여백      상하좌우 2.5cm
    페이지    A4
    푸터      가운데 페이지 번호

구성
    표지 → 목차(필드) → 서문 → 챕터(Heading1/2, 체크리스트는 표) → AI 활용 고지

한글 글꼴은 `w:eastAsia` 속성을 따로 지정해야 적용된다. python-docx 가 그 속성을
직접 노출하지 않으므로 :func:`_set_korean_font` 에서 XML 을 건드린다.
"""

from __future__ import annotations

import sys
import shutil
import zipfile
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ebook_gen.generator import ChapterDraft  # noqa: E402
from ebook_gen.schema import Outline  # noqa: E402
from shared.ai_label import LABELS, add_metadata  # noqa: E402

__all__ = ["build_docx", "BODY_FONT", "BODY_SIZE_PT", "LINE_SPACING", "MARGIN_CM"]

#: 사양 고정값.
BODY_FONT = "맑은 고딕"
BODY_SIZE_PT = 10.5
LINE_SPACING = 1.5
MARGIN_CM = 2.5

_INK = RGBColor(0x1A, 0x1A, 0x1A)
_MUTED = RGBColor(0x6B, 0x72, 0x80)
_ACCENT = RGBColor(0x1F, 0x5E, 0xFF)


def _fix_settings_zoom(path: Path) -> None:
    """python-docx 기본 템플릿의 스키마 위반을 고친다.

    기본 `word/settings.xml` 에 `<w:zoom w:val="bestFit"/>` 가 들어 있는데
    OOXML 스키마는 `w:percent` 를 필수로 요구한다. Word 는 눈감아 주지만
    엄격한 뷰어·변환기에서 문제가 될 수 있어 `w:percent="100"` 으로 바꾼다.
    """
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
            for name in names:  # 원본 순서를 유지한다
                archive.write(work / name, name)
        shutil.move(str(rebuilt), str(path))


def _set_korean_font(run_or_style, name: str = BODY_FONT) -> None:
    """한글이 지정한 글꼴로 나오게 eastAsia 속성까지 설정한다."""
    element = run_or_style._element
    rpr = element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attribute in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attribute), name)


def _field(paragraph, instruction: str, placeholder: str = "") -> None:
    """Word 필드를 넣는다 (목차·페이지 번호).

    필드는 문서를 열었을 때 계산되므로 placeholder 로 안내 문구를 넣어둔다.
    """
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = placeholder
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for node in (begin, instr, separate, text, end):
        run._r.append(node)


def _page_break(document) -> None:
    document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _configure_styles(document) -> None:
    """본문·제목 스타일을 사양대로 맞춘다."""
    normal = document.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(BODY_SIZE_PT)
    normal.font.color.rgb = _INK
    _set_korean_font(normal)

    paragraph_format = normal.paragraph_format
    paragraph_format.line_spacing = LINE_SPACING
    paragraph_format.space_after = Pt(6)

    for name, size, color, before, after in (
        ("Heading 1", 18, _INK, 18, 10),
        ("Heading 2", 13, _INK, 14, 6),
        ("Title", 30, _INK, 0, 12),
    ):
        style = document.styles[name]
        style.font.name = BODY_FONT
        style.font.size = Pt(size)
        style.font.color.rgb = color
        style.font.bold = True
        _set_korean_font(style)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.line_spacing = 1.2


def _configure_page(section) -> None:
    section.top_margin = Cm(MARGIN_CM)
    section.bottom_margin = Cm(MARGIN_CM)
    section.left_margin = Cm(MARGIN_CM)
    section.right_margin = Cm(MARGIN_CM)


def _add_page_number_footer(section) -> None:
    """푸터 가운데에 페이지 번호."""
    paragraph = section.footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _field(paragraph, " PAGE ", "1")
    for run in paragraph.runs:
        run.font.size = Pt(9)
        run.font.color.rgb = _MUTED
        _set_korean_font(run)


def _paragraph(document, text: str, *, size: float = BODY_SIZE_PT,
               color: RGBColor = _INK, bold: bool = False,
               align=None, space_after: int = 6, italic: bool = False):
    paragraph = document.add_paragraph()
    if align is not None:
        paragraph.alignment = align
    paragraph.paragraph_format.space_after = Pt(space_after)
    run = paragraph.add_run(text)
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.bold = bold
    run.italic = italic
    _set_korean_font(run)
    return paragraph


def _add_cover(document, outline: Outline) -> None:
    for _ in range(4):
        document.add_paragraph()

    _paragraph(document, outline.title, size=30, bold=True,
               align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)
    if outline.subtitle:
        _paragraph(document, outline.subtitle, size=13, color=_MUTED,
                   align=WD_ALIGN_PARAGRAPH.CENTER, space_after=40)

    for _ in range(6):
        document.add_paragraph()

    if outline.author:
        _paragraph(document, outline.author, size=12, bold=True,
                   align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
    _paragraph(document, date.today().strftime("%Y년 %m월"), size=10, color=_MUTED,
               align=WD_ALIGN_PARAGRAPH.CENTER)
    _page_break(document)


def _add_toc(document) -> None:
    document.add_heading("목차", level=1)
    _paragraph(
        document,
        "목차 번호가 보이지 않으면 본문을 전체 선택(Ctrl+A)한 뒤 F9 를 누르세요. "
        "Word 가 쪽 번호를 계산합니다.",
        size=9, color=_MUTED, italic=True, space_after=12,
    )
    paragraph = document.add_paragraph()
    _field(paragraph, r' TOC \o "1-2" \h \z \u ', "목차를 업데이트하세요 (F9)")
    _page_break(document)


def _add_preface(document, outline: Outline) -> None:
    document.add_heading("서문", level=1)
    for block in outline.preface.split("\n\n"):
        if block.strip():
            _paragraph(document, block.strip())
    _page_break(document)


def _add_checklist_table(document, items: list[str]) -> None:
    """체크리스트를 표로. 첫 칸은 체크 박스 자리."""
    table = document.add_table(rows=len(items) + 1, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.columns[0].width = Cm(1.2)
    table.columns[1].width = Cm(14.0)

    header = table.rows[0].cells
    for cell, text in zip(header, ("확인", "할 일")):
        cell.text = ""
        run = cell.paragraphs[0].add_run(text)
        run.bold = True
        run.font.size = Pt(9.5)
        run.font.color.rgb = _MUTED
        _set_korean_font(run)

    for index, item in enumerate(items, start=1):
        cells = table.rows[index].cells
        cells[0].text = ""
        box = cells[0].paragraphs[0].add_run("☐")
        box.font.size = Pt(11)
        _set_korean_font(box)
        cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        cells[1].text = ""
        run = cells[1].paragraphs[0].add_run(item)
        run.font.size = Pt(BODY_SIZE_PT)
        _set_korean_font(run)

    # 표 아래 여백
    for row in table.rows:
        for cell in row.cells:
            cell.width = Cm(1.2) if cell is row.cells[0] else Cm(14.0)
    document.add_paragraph()


def _add_chapter(document, draft: ChapterDraft) -> None:
    plan = draft.plan
    document.add_heading(f"{plan.number}장. {plan.title}", level=1)
    _paragraph(document, plan.key_message, size=11, color=_ACCENT, bold=True,
               space_after=14)

    if draft.intro_case:
        _paragraph(document, draft.intro_case)

    for section in draft.sections:
        document.add_heading(section["subheading"], level=2)
        for block in section["body"].split("\n\n"):
            if block.strip():
                _paragraph(document, block.strip())

    if draft.checklist:
        document.add_heading("실행 체크리스트", level=2)
        _add_checklist_table(document, draft.checklist)

    if draft.summary:
        document.add_heading("요약", level=2)
        for index, line in enumerate(draft.summary, start=1):
            _paragraph(document, f"{index}. {line}", space_after=4)

    _page_break(document)


def _add_ai_notice(document, outline: Outline, model: str) -> None:
    """마지막 AI 활용 고지 페이지 (인공지능기본법 제31조)."""
    document.add_heading("AI 활용 고지", level=1)
    _paragraph(document, LABELS["ko"], size=11, bold=True, space_after=14)
    for block in (
        "이 전자책의 원고는 생성형 AI(Claude)로 초안을 작성한 뒤 저자가 검토·수정하여 "
        "완성했습니다. 목차 구성과 각 장의 구조는 저자가 결정했고, 사례와 수치는 "
        "저자가 확인했습니다.",
        "인공지능기본법 제31조(인공지능 생성물의 표시)에 따라 이 사실을 밝힙니다. "
        "AI가 만든 문장에는 사실과 다른 내용이 섞일 수 있으므로, 읽으시면서 "
        "본인 상황에 맞는지 확인하시기 바랍니다.",
        "이 책의 내용은 정보 제공을 목적으로 하며, 개별 상황에 대한 전문적인 조언을 "
        "대신하지 않습니다. 실행 결과는 독자의 상황에 따라 다를 수 있습니다.",
    ):
        _paragraph(document, block)

    document.add_paragraph()
    _paragraph(document, f"생성 도구: {model}", size=9, color=_MUTED, space_after=2)
    _paragraph(document, f"작성일: {date.today().isoformat()}", size=9, color=_MUTED)


def build_docx(
    outline: Outline,
    drafts: list[ChapterDraft],
    out_path: str | Path,
    model: str = "claude",
) -> Path:
    """전자책 docx 를 만들고 AI 메타데이터까지 기록한다.

    Args:
        outline: 목차.
        drafts: 챕터 원고. 번호 순으로 들어온다.
        out_path: 저장할 .docx 경로.
        model: 고지 페이지에 적을 생성 도구 이름.

    Returns:
        만들어진 파일 경로.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    document = Document()
    _configure_styles(document)
    _configure_page(document.sections[0])
    _add_page_number_footer(document.sections[0])

    _add_cover(document, outline)
    _add_toc(document)
    _add_preface(document, outline)
    for draft in sorted(drafts, key=lambda d: d.plan.number):
        _add_chapter(document, draft)
    _add_ai_notice(document, outline, model)

    core = document.core_properties
    core.title = outline.title
    core.subject = outline.subtitle or outline.topic
    core.author = outline.author or "미상"
    core.keywords = ", ".join(c.title for c in outline.chapters[:5])

    document.save(str(out_path))
    _fix_settings_zoom(out_path)

    # core properties 의 comments 에 AI 생성물 표시를 남긴다 (인공지능기본법 제31조)
    add_metadata(out_path, tool="ebook-gen")
    return out_path
