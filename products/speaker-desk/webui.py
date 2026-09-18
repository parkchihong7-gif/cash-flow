"""16번 전용 웹 화면 — **틀리면 사람이 공항에서 돌아가는 일**을 화면이 막는다.

이 상품은 계산이 어려운 게 아니다. **물어봐야 하는 줄 모르는 것**이 문제다.
그래서 화면은 답을 주기보다 *지금 이 조합이 위험하다*고 먼저 소리친다.

화면이 알고 있어야 하는 것
--------------------------

* **무비자 + 강연료 = 빨간불.** 실무에서 가장 많이 틀리는 조합이다
* **gross / net 을 나란히 놓는다.** 500만 원 계약이 641만 원이 되는 것을
  계약 전에 봐야 한다. 지급일에 알면 이미 늦다
* **지난 필수 일정을 맨 위로.** 거주자증명서를 늦게 요청하면 조약을 못 쓴다
* 어디에도 "이 비자면 됩니다" 라고 쓰지 않는다. 확인할 방향만 좁힌다
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.webui import Field, Note, Panel, Table, WebUI          # noqa: E402

from speaker_desk.budget import build as build_budget            # noqa: E402
from speaker_desk.checklist import build as build_checklist, overdue_count  # noqa: E402
from speaker_desk.roster import Event, RosterError, Speaker, load_event  # noqa: E402
from speaker_desk.tax import (                                   # noqa: E402
    NOT_TAX_ADVICE, TOTAL_RATE, TREATY_DOCS, compute,
)
from speaker_desk.visa import MUST_CONFIRM, assess               # noqa: E402

EVENT = BASE_DIR / "event.yaml"


def _event() -> Event | None:
    try:
        return load_event(EVENT)
    except RosterError:
        return None


def _won(value: int) -> str:
    return f"{value:,}원"


# ------------------------------------------------------------------ 위험 신호
def _risk_notes(event: Event | None, today: date) -> list[Note]:
    """맨 위에 오는 것들. **일정보다 비자가 먼저다.**"""
    if event is None:
        return [Note("행사 명부를 읽지 못했습니다",
                     "`event.yaml` 을 확인하시거나 아래에서 연사를 추가하세요.",
                     tone="warn")]

    notes = [Note(f"{event.title} · {event.event_date.isoformat()}",
                  f"D-{event.days_until(today)} · 연사 {len(event.speakers)}명")]

    for speaker in event.speakers:
        hint = assess(paid=speaker.paid, days=speaker.stay_days or 1,
                      visa_waiver=speaker.visa_waiver,
                      expenses_only=speaker.expenses_only)
        for warning in hint.warnings:
            notes.append(Note(f"{speaker.name} — {hint.name}", warning, tone="bad"))

    for speaker in event.speakers:
        tasks = build_checklist(event, speaker)
        late = overdue_count(tasks, today)
        if late:
            missed = [task.title for task in tasks
                      if task.state(today) == "late"][:3]
            notes.append(Note(
                f"{speaker.name} — 지난 필수 일정 {late}건",
                " / ".join(missed) + " — **되돌리기 어려운 일입니다.**", tone="warn"))

    if not any(note.tone in ("bad", "warn") for note in notes):
        notes.append(Note("지금 걸리는 것이 없습니다",
                          "체크리스트를 계속 보시면 됩니다.", tone="ok"))
    return notes


# ------------------------------------------------------------------ 표
def _roster_table(event: Event | None) -> Table:
    if event is None:
        return Table(note="연사가 없습니다.")
    rows, tones = [], []
    for speaker in event.speakers:
        hint = assess(paid=speaker.paid, days=speaker.stay_days or 1,
                      visa_waiver=speaker.visa_waiver,
                      expenses_only=speaker.expenses_only)
        fee = _won(speaker.fee_krw) if speaker.paid else (
            "실비만" if speaker.expenses_only else "무보수")
        rows.append([speaker.name, speaker.country, fee,
                     f"{speaker.stay_days}일" if speaker.stay_days else "미정",
                     hint.name, speaker.jetlag_note.split(".")[0]])
        tones.append("bad" if hint.warnings else "")
    return Table(
        headers=["연사", "거주국", "사례비", "체류", "확인할 체류자격", "시차"],
        rows=rows, tones=tones,
        note=MUST_CONFIRM)


def _tax_table(event: Event | None) -> Table:
    """gross / net 을 나란히. **이 표가 이 상품에서 제일 값어치 있다.**"""
    if event is None:
        return Table()
    rows, tones = [], []
    for speaker in event.speakers:
        if not speaker.paid:
            continue
        gross = compute(speaker.fee_krw, "gross", speaker.treaty_rate)
        net = compute(speaker.fee_krw, "net", speaker.treaty_rate)
        chosen = speaker.fee_basis
        rows.append([
            f"{speaker.name} · **{'세전(gross)' if chosen == 'gross' else '세후(net)'}** 로 계약",
            _won(speaker.fee_krw),
            f"{_won(gross.net)} 수령 / {_won(gross.gross)} 지출",
            f"{_won(net.net)} 수령 / {_won(net.gross)} 지출",
            f"**{_won(net.extra_for_net)}**",
        ])
        tones.append("warn" if chosen == "net" else "")
    return Table(
        headers=["연사", "계약서 금액", "세전으로 적으면", "세후로 적으면", "차이"],
        rows=rows, tones=tones, numeric=[1],
        note=f"기본 원천징수 {TOTAL_RATE * 100:.0f}% (소득세 20% + 지방소득세 2%). "
             f"{NOT_TAX_ADVICE}")


def _checklist_table(event: Event | None, today: date) -> Table:
    if event is None:
        return Table()
    rows, tones = [], []
    for speaker in event.speakers:
        for task in build_checklist(event, speaker):
            state = task.state(today)
            if state == "ahead":
                continue
            rows.append([speaker.name, task.dday, task.due.isoformat(),
                         task.title + (" **(필수)**" if task.hard else ""),
                         task.label(today)])
            tones.append({"late": "bad", "soon": "warn"}.get(state, ""))
    return Table(headers=["연사", "기한", "날짜", "할 일", "상태"],
                 rows=rows, tones=tones,
                 note="여유 있는 항목은 접어 두었습니다. 지난 것과 곧 닥칠 것만 보입니다.")


def _budget_table(event: Event | None) -> Table:
    if event is None:
        return Table()
    rows = []
    total = 0
    for budget in build_budget(event):
        cash = sum(line.amount for line in budget.lines
                   if not line.label.startswith("  "))
        total += cash
        rows.append([budget.speaker, budget.country, _won(cash),
                     _won(budget.tax) if budget.tax else "—",
                     _won(budget.to_speaker) if budget.to_speaker else "—"])
    if rows:
        rows.append(["**합계**", "", f"**{_won(total)}**", "", ""])
    return Table(headers=["연사", "거주국", "주최 측 지출", "원천징수", "연사 수령"],
                 rows=rows, numeric=[2, 3, 4])


# ------------------------------------------------------------------ 화면
def _speaker_fields() -> list[Field]:
    return [
        Field("name", "이름 (영문)", "text", placeholder="Jane Doe", required=True),
        Field("country", "거주국", "text", placeholder="United States", required=True),
        Field("affiliation", "소속", "text", placeholder="MIT CSAIL"),
        Field("session_title", "세션 제목", "text"),
        Field("fee_krw", "사례비(원)", "number", default=0,
              help="0 이면 무보수입니다. **사례비가 있으면 비자 판단이 달라집니다.**"),
        Field("fee_basis", "계약 방식", "select", default="gross",
              options=["gross", "net"],
              help="gross = 이 금액에서 세금을 뗍니다 / net = 연사 손에 이 금액이 갑니다"),
        Field("expenses_only", "사례비 없이 실비만", "boolean", default=False,
              help="항공·숙박만 지원하는 경우입니다. 사례비와 함께 켤 수 없습니다."),
        Field("visa_waiver", "사증면제 대상국", "boolean", default=False,
              help="**대가를 받으면 무비자로 강연할 수 없습니다.** 가장 많이 틀리는 곳입니다."),
        Field("arrival", "입국일", "date"),
        Field("departure", "출국일", "date"),
        Field("utc_offset", "연사 현지 UTC 오프셋", "number", default=0,
              help="미국 동부는 -5, 일본은 9 입니다. 시차로 리허설 시각을 조언합니다."),
        Field("airfare_krw", "항공(원)", "number", default=0),
        Field("hotel_krw", "숙박(원)", "number", default=0),
        Field("needs_interpreter", "통역 필요", "boolean", default=False),
    ]


def build(program, ctx) -> WebUI:
    today = date.today()
    event = _event()

    risk = Panel(key="risk", title="지금 걸리는 것",
                 notes=_risk_notes(event, today))
    roster = Panel(key="roster", title="연사 명부", table=_roster_table(event))
    tax = Panel(
        key="tax", title="사례비 — 세전으로 적을지 세후로 적을지",
        intro="**계약서에 서명하기 전에** 정해야 합니다. 안 정하면 지급일에 "
              "연사는 500만 원을 기대하고 390만 원을 받습니다.",
        table=_tax_table(event),
        lines=[f"조세조약을 쓰려면 **지급일 전에** 받아야 할 서류: {item}"
               for item in TREATY_DOCS[:2]])
    checklist = Panel(key="checklist", title="체크리스트 (지난 것·곧 닥칠 것)",
                      table=_checklist_table(event, today))
    budget = Panel(key="budget", title="예산", table=_budget_table(event))

    add = Panel(
        key="add", title="연사 추가",
        intro="사례비 유무·체류일수·사증면제 여부가 **비자 판단을 바꾸는 값**입니다.",
        fields=_speaker_fields(),
        action="do:add_speaker", action_label="명부에 넣기")

    calc = Panel(
        key="calc", title="원천징수 계산기",
        intro="명부에 넣기 전에 숫자만 먼저 견줘 보실 때 쓰세요.",
        fields=[
            Field("amount", "계약서에 적을 금액(원)", "number", default=5000000),
            Field("treaty", "조세조약 제한세율", "text", placeholder="비우면 기본 22%",
                  help="세무대리인께 확인하신 값을 적으세요. 예: 0.0(면제) 또는 0.15"),
        ],
        action="do:tax", action_label="계산해 보기")

    docs = Panel(
        key="docs", title="문서 만들기",
        intro="영문 초청장과 계약서 초안, 결재용 예산 엑셀을 만듭니다.",
        lines=["초청장은 비자 신청에 그대로 냅니다",
               "**계약서는 초안입니다.** 서명 전에 검토를 받으세요",
               "녹화물 범위와 취소 조항은 일부러 비워 두었습니다"],
        action="run", action_label="브리프·문서 만들기", run_mode="dry")

    admin = [risk, roster, tax, checklist, budget, add, calc, docs]

    client = [
        Panel(key="risk", title="지금 걸리는 것", notes=_risk_notes(event, today)),
        roster,
        Panel(key="tax", title="사례비와 세금", table=_tax_table(event),
              intro="비거주자에게 강연료를 드리면 **주최 측이 세금을 떼고** 드립니다.",
              note=NOT_TAX_ADVICE),
        checklist,
        Panel(key="docs", title="문서 받기",
              action="run", action_label="브리프 만들기", run_mode="dry"),
    ]

    return WebUI(
        program_id=program.id, title=program.name,
        admin=admin, client=client,
        admin_intro="**판정하지 않습니다.** 무엇을 확인해야 하는지 좁혀 드립니다. "
                    "실무 사고는 대부분 '물어봐야 하는 줄 몰라서' 납니다.",
        client_intro="해외 연사 초청에서 **빠뜨리기 쉬운 것**을 짚어 드립니다.",
    )


# ------------------------------------------------------------------ 동작
def handle(program, ctx, action: str, form: dict) -> str:
    if action == "add_speaker":
        return _add_speaker(form)
    if action == "tax":
        return _tax_preview(form)
    return "error=모르는 동작입니다"


def _flag(form: dict, key: str) -> bool:
    return str(form.get(key) or "").strip() in ("1", "true", "on", "True")


def _readable(exc: Exception) -> str:
    """pydantic 오류에서 **사람이 읽을 줄**만 골라낸다.

    마지막 줄은 문서 링크라 그대로 띄우면 화면에 URL 만 남는다.
    """
    for line in str(exc).splitlines():
        text = line.strip()
        if text.startswith("Value error,"):
            message = text[len("Value error,"):].strip()
            return message.split(" [type=")[0].strip()
    for line in str(exc).splitlines():
        text = line.strip()
        if text and not text.startswith(("For further", "http")) and "validation error" not in text:
            return text
    return "명부에 넣을 수 없는 값입니다"
    return str(form.get(key) or "").strip() in ("1", "true", "on", "True")


def _add_speaker(form: dict) -> str:
    name = (form.get("name") or "").strip()
    if not name:
        return "error=연사 이름을 적어 주세요"

    raw = yaml.safe_load(EVENT.read_text(encoding="utf-8")) if EVENT.is_file() else {}
    raw = raw or {}
    speakers = raw.get("speakers") or []
    if any((item.get("name") or "").strip() == name for item in speakers):
        return f"error=이미 명부에 있는 이름입니다: {name}"

    entry: dict = {"name": name,
                   "country": (form.get("country") or "").strip() or "미상"}
    for key in ("affiliation", "session_title"):
        value = (form.get(key) or "").strip()
        if value:
            entry[key] = value
    for key in ("fee_krw", "airfare_krw", "hotel_krw"):
        try:
            entry[key] = int(float(form.get(key) or 0))
        except ValueError:
            return f"error={key} 는 숫자로 적어 주세요"
    try:
        entry["utc_offset"] = float(form.get("utc_offset") or 0)
    except ValueError:
        return "error=UTC 오프셋은 숫자로 적어 주세요"

    entry["fee_basis"] = (form.get("fee_basis") or "gross").strip()
    entry["expenses_only"] = _flag(form, "expenses_only")
    entry["visa_waiver"] = _flag(form, "visa_waiver")
    entry["needs_interpreter"] = _flag(form, "needs_interpreter")
    for key in ("arrival", "departure"):
        value = (form.get(key) or "").strip()
        if value:
            entry[key] = value

    # 명부에 넣기 전에 검증한다. 잘못된 줄이 들어가면 화면 전체가 안 뜬다.
    try:
        speaker = Speaker(**entry)
    except Exception as exc:
        return f"error={_readable(exc)}"

    raw["speakers"] = speakers + [entry]
    EVENT.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
                     encoding="utf-8")

    hint = assess(paid=speaker.paid, days=speaker.stay_days or 1,
                  visa_waiver=speaker.visa_waiver,
                  expenses_only=speaker.expenses_only)
    if hint.warnings:
        return f"error={name} 을 넣었습니다. 다만 ⚠ {hint.warnings[0]}"
    return f"saved={name} 을 명부에 넣었습니다 · 확인할 체류자격: {hint.name}"


def _tax_preview(form: dict) -> str:
    try:
        amount = int(float(form.get("amount") or 0))
    except ValueError:
        return "error=금액은 숫자로 적어 주세요"
    if amount <= 0:
        return "error=금액을 적어 주세요"

    treaty_raw = (form.get("treaty") or "").strip()
    treaty = None
    if treaty_raw:
        try:
            treaty = float(treaty_raw)
        except ValueError:
            return "error=제한세율은 0.0~0.99 사이 숫자로 적어 주세요"
        if not 0 <= treaty < 1:
            return "error=제한세율은 0 이상 1 미만이어야 합니다"

    gross = compute(amount, "gross", treaty)
    net = compute(amount, "net", treaty)
    return (f"saved=세전으로 적으면 연사가 {gross.net:,}원을 받고 주최 측은 "
            f"{gross.gross:,}원을 씁니다. 세후로 적으면 연사가 {net.net:,}원을 받고 "
            f"주최 측은 {net.gross:,}원을 씁니다 (차이 {net.extra_for_net:,}원)")
