"""예산 — **주최 측이 실제로 쓰는 돈.**

계약서에 적은 사례비와 실제 지출은 다르다. 원천징수를 `net` 으로 하기로 했다면
그로스업한 금액이 나가고, 항공·숙박·통역이 그 위에 붙는다.

엑셀로 뽑는 이유는 하나다. **결재를 올려야 하기 때문이다.**
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from speaker_desk.roster import Event, Speaker
from speaker_desk.tax import NOT_TAX_ADVICE, Withholding, compute

__all__ = ["Line", "SpeakerBudget", "build", "write_xlsx", "INTERPRETER_KRW"]

#: 동시통역 2인 1조 하루 대략값. 분야와 언어에 따라 크게 다르다.
INTERPRETER_KRW = 1_600_000


@dataclass
class Line:
    label: str
    amount: int
    note: str = ""


@dataclass
class SpeakerBudget:
    speaker: str
    country: str
    lines: list[Line] = field(default_factory=list)
    withholding: Withholding | None = None

    @property
    def total(self) -> int:
        return sum(line.amount for line in self.lines)

    @property
    def to_speaker(self) -> int:
        """연사 손에 들어가는 돈."""
        return self.withholding.net if self.withholding else 0

    @property
    def tax(self) -> int:
        return self.withholding.tax if self.withholding else 0


def build(event: Event) -> list[SpeakerBudget]:
    """연사별 예산."""
    result: list[SpeakerBudget] = []
    for speaker in event.speakers:
        lines: list[Line] = []
        withholding = None

        if speaker.paid:
            withholding = compute(speaker.fee_krw, speaker.fee_basis,
                                  speaker.treaty_rate)
            basis_note = ("계약서 금액에서 원천징수합니다"
                          if speaker.fee_basis == "gross"
                          else "연사 손에 계약서 금액이 가도록 그로스업했습니다")
            lines.append(Line("사례비 (지급 총액)", withholding.gross, basis_note))
            lines.append(Line("  ├ 연사 수령액", withholding.net,
                              "실제로 송금되는 금액"))
            lines.append(Line("  └ 원천징수액", withholding.tax,
                              f"세율 {withholding.rate_percent}%"
                              + (" (조세조약 적용)" if withholding.treaty else "")))

        if speaker.airfare_krw:
            lines.append(Line("항공", speaker.airfare_krw))
        if speaker.hotel_krw:
            lines.append(Line("숙박", speaker.hotel_krw,
                              f"{speaker.stay_days}일" if speaker.stay_days else ""))
        if speaker.needs_interpreter:
            lines.append(Line("통역", INTERPRETER_KRW, "동시통역 2인 1조 하루 기준"))
        if speaker.other_krw:
            lines.append(Line("기타", speaker.other_krw, "이동·식사·의전"))

        result.append(SpeakerBudget(
            speaker=speaker.name, country=speaker.country,
            lines=lines, withholding=withholding))
    return result


def _cash_out(budget: SpeakerBudget) -> int:
    """실제로 나가는 돈. 안쪽 내역(├ └)은 이미 총액에 포함돼 있어 뺀다."""
    return sum(line.amount for line in budget.lines
               if not line.label.startswith("  "))


def write_xlsx(event: Event, budgets: list[SpeakerBudget], out_dir: str | Path) -> Path:
    """결재용 엑셀."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"budget_{event.event_date.isoformat()}.xlsx"

    book = Workbook()
    sheet = book.active
    sheet.title = "예산"

    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="EEF0F4")
    money = "#,##0"

    sheet["A1"] = event.title
    sheet["A1"].font = Font(bold=True, size=14)
    sheet["A2"] = f"{event.event_date.isoformat()} · {event.venue}"
    sheet["A3"] = NOT_TAX_ADVICE
    sheet["A3"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.merge_cells("A3:D3")
    sheet.row_dimensions[3].height = 40

    row = 5
    for budget in budgets:
        sheet.cell(row, 1, f"{budget.speaker} ({budget.country})").font = bold
        row += 1
        for header, index in (("항목", 1), ("금액(원)", 2), ("비고", 3)):
            cell = sheet.cell(row, index, header)
            cell.font = bold
            cell.fill = head_fill
        row += 1
        for line in budget.lines:
            sheet.cell(row, 1, line.label)
            cell = sheet.cell(row, 2, line.amount)
            cell.number_format = money
            sheet.cell(row, 3, line.note)
            row += 1
        sheet.cell(row, 1, "소계").font = bold
        cell = sheet.cell(row, 2, _cash_out(budget))
        cell.font = bold
        cell.number_format = money
        sheet.cell(row, 3, "안쪽 내역(├ └)은 사례비 총액에 이미 들어 있습니다")
        row += 2

    sheet.cell(row, 1, "합계").font = Font(bold=True, size=12)
    total = sheet.cell(row, 2, sum(_cash_out(item) for item in budgets))
    total.font = Font(bold=True, size=12)
    total.number_format = money

    sheet.column_dimensions["A"].width = 26
    sheet.column_dimensions["B"].width = 16
    sheet.column_dimensions["C"].width = 46

    book.save(path)
    return path
