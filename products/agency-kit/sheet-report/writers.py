"""보고서 쓰기 — 마크다운과 워드.

같은 내용을 두 벌 만든다.
    `.md`   메신저에 붙여 넣거나 노션에 옮기기 좋다
    `.docx` 사장님께 파일로 드리거나 인쇄하기 좋다

**숫자는 집계에서 그대로 온다.** 여기서 다시 계산하지 않는다.
서식만 입히는 곳이다.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from shared import ai_label                                          # noqa: E402

__all__ = ["report_markdown", "write_markdown", "write_docx", "write_all"]


def _won(value: int) -> str:
    return f"{int(value):,}원"


def _arrow(value: int) -> str:
    return "▲" if value > 0 else ("▼" if value < 0 else "―")


def report_markdown(aggregate, narration, title: str = "", source: str = "") -> str:
    """보고서 본문."""
    label = {"week": "주간", "month": "월간", "quarter": "분기"}.get(aggregate.period, "기간")
    heading = title or f"{label} 매출 보고서"

    lines: list[str] = []
    lines.append(f"# {heading}")
    lines.append("")
    lines.append(f"**{aggregate.start} ~ {aggregate.end}** ({aggregate.days}일)")
    lines.append("")
    if source:
        lines.append(f"- 자료: {source}")
    lines.append(f"- 만든 날: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # ── 한눈에
    lines.append("## 한눈에")
    lines.append("")
    lines.append("| | 이번 기간 | 직전 기간 | 증감 |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| 매출 | {_won(aggregate.total)} | {_won(aggregate.prev_total)} | "
                 f"{_arrow(aggregate.delta)} {_won(abs(aggregate.delta))} "
                 f"({aggregate.delta_ratio:+.1f}%) |")
    lines.append(f"| 건수 | {aggregate.count:,}건 | | |")
    lines.append(f"| 평균 단가 | {_won(aggregate.average)} | | |")
    lines.append("")

    # ── 상위 5
    if aggregate.top:
        lines.append(f"## {aggregate.group_column} 상위 {len(aggregate.top)}")
        lines.append("")
        lines.append(f"| 순위 | {aggregate.group_column} | 매출 | 비중 | 직전 대비 |")
        lines.append("|---:|---|---:|---:|---:|")
        for rank, item in enumerate(aggregate.top, start=1):
            lines.append(f"| {rank} | {item['name']} | {_won(item['amount'])} | "
                         f"{item['share']:.1f}% | {_arrow(item['delta'])} "
                         f"{_won(abs(item['delta']))} |")
        lines.append("")

    # ── 해석
    lines.append("## 읽기")
    lines.append("")
    if narration.reading:
        for line in narration.reading:
            lines.append(f"- {line}")
    else:
        lines.append("- (해석을 만들지 못했습니다)")
    lines.append("")

    if narration.caution:
        lines.append(f"> {narration.caution}")
        lines.append("")

    # ── 할 일
    lines.append("## 다음 기간에 할 일")
    lines.append("")
    if narration.actions:
        for action in narration.actions:
            lines.append(f"- [ ] {action}")
    else:
        lines.append("- [ ] (할 일을 만들지 못했습니다)")
    lines.append("")

    # ── 일별
    if aggregate.daily:
        lines.append("## 일별")
        lines.append("")
        lines.append("| 날짜 | 매출 |")
        lines.append("|---|---:|")
        for row in aggregate.daily:
            lines.append(f"| {row['day']} | {_won(row['amount'])} |")
        lines.append("")

    # ── 확인할 것
    notes = list(aggregate.notes) + list(narration.warnings)
    if notes:
        lines.append("## 확인하실 것")
        lines.append("")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("숫자는 시트 원본을 집계한 값입니다. 해석과 할 일은 초안이니 "
                 "사장님이 아시는 사정과 맞춰 고쳐 보세요.")

    return "\n".join(lines)


def write_markdown(text: str, path: Path, ai_label_on: bool = True) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ai_label.add_text_label(text) if ai_label_on else text
    path.write_text(body + "\n", encoding="utf-8")
    return path


def write_docx(aggregate, narration, path: Path, title: str = "",
               ai_label_on: bool = True) -> Path:
    """워드 파일. 사장님께 그대로 드릴 수 있는 모양으로."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    label = {"week": "주간", "month": "월간", "quarter": "분기"}.get(aggregate.period, "기간")
    document = Document()

    # 한글 글꼴을 기본으로. 안 잡으면 워드가 제멋대로 고릅니다.
    style = document.styles["Normal"]
    style.font.name = "맑은 고딕"
    style.font.size = Pt(10)

    document.add_heading(title or f"{label} 매출 보고서", level=0)
    subtitle = document.add_paragraph(f"{aggregate.start} ~ {aggregate.end} ({aggregate.days}일)")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.LEFT

    document.add_heading("한눈에", level=1)
    table = document.add_table(rows=1, cols=4)
    table.style = "Light Grid Accent 1"
    header = table.rows[0].cells
    header[0].text, header[1].text = "", "이번 기간"
    header[2].text, header[3].text = "직전 기간", "증감"

    row = table.add_row().cells
    row[0].text = "매출"
    row[1].text = _won(aggregate.total)
    row[2].text = _won(aggregate.prev_total)
    row[3].text = (f"{_arrow(aggregate.delta)} {_won(abs(aggregate.delta))} "
                   f"({aggregate.delta_ratio:+.1f}%)")

    row = table.add_row().cells
    row[0].text, row[1].text = "건수", f"{aggregate.count:,}건"
    row = table.add_row().cells
    row[0].text, row[1].text = "평균 단가", _won(aggregate.average)

    if aggregate.top:
        document.add_heading(f"{aggregate.group_column} 상위 {len(aggregate.top)}", level=1)
        top_table = document.add_table(rows=1, cols=4)
        top_table.style = "Light Grid Accent 1"
        head = top_table.rows[0].cells
        head[0].text, head[1].text = "순위", aggregate.group_column
        head[2].text, head[3].text = "매출", "비중"
        for rank, item in enumerate(aggregate.top, start=1):
            cells = top_table.add_row().cells
            cells[0].text = str(rank)
            cells[1].text = item["name"]
            cells[2].text = _won(item["amount"])
            cells[3].text = f"{item['share']:.1f}%"

    document.add_heading("읽기", level=1)
    for line in narration.reading or ["(해석을 만들지 못했습니다)"]:
        document.add_paragraph(line, style="List Bullet")
    if narration.caution:
        note = document.add_paragraph(narration.caution)
        note.runs[0].italic = True

    document.add_heading("다음 기간에 할 일", level=1)
    for action in narration.actions or ["(할 일을 만들지 못했습니다)"]:
        document.add_paragraph(action, style="List Bullet")

    notes = list(aggregate.notes) + list(narration.warnings)
    if notes:
        document.add_heading("확인하실 것", level=1)
        for note in notes:
            document.add_paragraph(note, style="List Bullet")

    tail = document.add_paragraph(
        "숫자는 시트 원본을 집계한 값입니다. 해석과 할 일은 초안이니 "
        "사장님이 아시는 사정과 맞춰 고쳐 보세요.")
    tail.runs[0].font.size = Pt(9)

    if ai_label_on:
        labelled = document.add_paragraph(ai_label.label_text_for("ko"))
        labelled.runs[0].font.size = Pt(9)

    document.save(path)
    if ai_label_on:
        # 파일 속성에도 남긴다. 기계가 읽을 수 있게.
        ai_label.add_metadata(path)
    return path


def write_all(aggregate, narration, out_dir: Path, title: str = "", source: str = "",
              ai_label_on: bool = True, stamp: str = "") -> tuple[Path, Path]:
    """마크다운과 워드를 함께 쓴다."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now().strftime("%Y%m%d")

    text = report_markdown(aggregate, narration, title=title, source=source)
    md_path = write_markdown(text, out_dir / f"report_{stamp}.md", ai_label_on)
    docx_path = write_docx(aggregate, narration, out_dir / f"report_{stamp}.docx",
                           title=title, ai_label_on=ai_label_on)
    return md_path, docx_path
