"""연사별 브리프 — 담당자가 한 장으로 들고 다니는 문서."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from speaker_desk.budget import SpeakerBudget
from speaker_desk.checklist import Task, overdue_count
from speaker_desk.roster import Event, Speaker
from speaker_desk.tax import NOT_TAX_ADVICE, TREATY_DOCS, compute
from speaker_desk.visa import MUST_CONFIRM, assess

__all__ = ["write_brief", "DISCLAIMER"]

DISCLAIMER = (
    "이 문서는 일정과 금액을 **계산해 본 것**이지 법률·세무 자문이 아닙니다. "
    "체류자격은 출입국·주한공관에, 원천징수는 세무대리인에게 확인하세요."
)


def _won(value: int) -> str:
    return f"{value:,}원"


def write_brief(event: Event, speaker: Speaker, tasks: list[Task],
                budget: SpeakerBudget, out_dir: str | Path,
                today: date | None = None) -> Path:
    today = today or date.today()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    hint = assess(paid=speaker.paid, days=speaker.stay_days or 1,
                  visa_waiver=speaker.visa_waiver,
                  expenses_only=speaker.expenses_only)
    late = overdue_count(tasks, today)

    lines = [f"# {speaker.name} — 초청 브리프", "",
             f"> {DISCLAIMER}", "",
             f"**{event.title}** · {event.event_date.isoformat()}"
             f" · D-{event.days_until(today)}", ""]

    if late:
        lines += [f"## ⚠ 지난 필수 일정 {late}건", "",
                  "놓치면 되돌리기 어려운 일입니다. 아래 체크리스트에서 "
                  "'지났습니다' 를 먼저 보세요.", ""]

    lines += ["## 연사", "",
              f"| | |", "|---|---|",
              f"| 이름 | {speaker.name} |",
              f"| 소속 | {speaker.affiliation or '—'} |",
              f"| 거주국 | {speaker.country} |",
              f"| 세션 | {speaker.session_title or '—'} |",
              f"| 체류 | "
              + (f"{speaker.arrival} ~ {speaker.departure} ({speaker.stay_days}일)"
                 if speaker.arrival else "미정") + " |",
              f"| 시차 | {speaker.jetlag_note} |",
              f"| 통역 | {'필요' if speaker.needs_interpreter else '불필요'} |", ""]

    lines += ["## 체류자격 — 확인할 방향", "",
              f"**{hint.name}**", "",
              f"- 해당 조건: {hint.when}",
              f"- 참고: {hint.note}", "",
              "왜 이쪽인가:"]
    lines += [f"- {reason}" for reason in hint.reasons]
    lines.append("")
    if hint.warnings:
        lines += ["### ⚠ 조심할 것", ""]
        lines += [f"- {item}" for item in hint.warnings]
        lines.append("")
    lines += [f"> {MUST_CONFIRM}", ""]

    lines += ["## 돈", ""]
    if not speaker.paid:
        lines += ["사례비가 없습니다."
                  + (" 항공·숙박 실비만 지원합니다." if speaker.expenses_only else ""), ""]
    else:
        result = compute(speaker.fee_krw, speaker.fee_basis, speaker.treaty_rate)
        basis = ("계약서 금액에서 세금을 뗍니다 (gross)"
                 if speaker.fee_basis == "gross"
                 else "연사 손에 계약서 금액이 가도록 올렸습니다 (net)")
        lines += [f"계약 방식: **{basis}**", "",
                  "| | 금액 |", "|---|---:|",
                  f"| 계약서 금액 | {_won(result.contract_amount)} |",
                  f"| 지급 총액 | **{_won(result.gross)}** |",
                  f"| 원천징수 ({result.rate_percent}%) | {_won(result.tax)} |",
                  f"| 연사 수령액 | **{_won(result.net)}** |", ""]
        if speaker.fee_basis == "net" and result.extra_for_net:
            lines += [f"> net 방식이라 주최 측 부담이 "
                      f"{_won(result.extra_for_net)} 늘어납니다.", ""]
        if result.treaty:
            lines += ["조세조약 제한세율을 적용한 값입니다. "
                      "**서류가 지급일 전에 도착해야 적용됩니다.**", ""]
        lines += ["### 조세조약을 쓰려면 받아야 할 서류", ""]
        lines += [f"{index}. {item}" for index, item in enumerate(TREATY_DOCS, 1)]
        lines += ["",
                  "**지급일 전에** 받아야 합니다. 늦으면 기본 세율로 떼고 나중에 "
                  "경정청구를 해야 하는데 훨씬 번거롭습니다.", "",
                  f"> {NOT_TAX_ADVICE}", ""]

    lines += ["## 예산", "", "| 항목 | 금액 | 비고 |", "|---|---:|---|"]
    for line in budget.lines:
        lines.append(f"| {line.label} | {_won(line.amount)} | {line.note} |")
    cash = sum(item.amount for item in budget.lines
               if not item.label.startswith("  "))
    lines += [f"| **소계** | **{_won(cash)}** | 안쪽 내역은 총액에 포함 |", ""]

    lines += ["## 체크리스트", "", "| 기한 | 날짜 | 할 일 | 상태 |", "|---|---|---|---|"]
    for task in tasks:
        mark = {"late": "⚠ 지났습니다", "past": "지난 일정",
                "soon": "곧", "ahead": "여유 있음"}[task.state(today)]
        hard = " **(필수)**" if task.hard else ""
        lines.append(f"| {task.dday} | {task.due.isoformat()} | "
                     f"{task.title}{hard} | {mark} |")
    lines.append("")

    lines += ["### 각 항목 설명", ""]
    for task in tasks:
        if task.hard:
            lines.append(f"- **{task.title}** ({task.dday}) — {task.detail}")
    lines.append("")

    path = out_dir / f"brief_{speaker.name.replace(' ', '_')}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
