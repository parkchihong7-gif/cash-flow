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


# ══════════════════════════════════════════════════════════ 운영 콘솔
#
# 참조로 받은 컨퍼런스 관리자와 **업종이 같은 유일한 프로그램**이다. 그래서
# 더 조심했다. 그쪽 탭(초청 현황·실무 진행·정산·사후·협업)을 그대로 옮기면
# 쉽지만, 그건 그 행사의 구조지 이 프로그램의 구조가 아니다.
#
# 이 프로그램이 실제로 하는 일은 좁다. **판정하지 않고, 물어볼 것을 좁힌다.**
# 실무 사고는 대부분 "물어봐야 하는 줄 몰라서" 난다. 그래서 탭은
#
#     연사 명부 → 비자 → 사례비·세금 → 일정 → 예산 → 문서
#
# 다섯 개의 사고 지점을 따라간다. 행사 운영 전반(등록·부스·케이터링)은
# 여기 없다. 만들지 않은 것이 아니라 이 상품의 범위가 아니다.

from core.console import Console, FileLoc, ManualTask, Stat, Tab, Todo, Trouble  # noqa: E402

from speaker_desk.tax import TOTAL_RATE                           # noqa: E402
from speaker_desk.visa import SHORT_STAY_DAYS                     # noqa: E402


def _stats(event, today) -> list[Stat]:
    """위쪽 타일. **지난 일**이 맨 앞이다.

    초청 실무는 날짜가 전부다. 비자 신청이 늦으면 연사가 못 온다. 돈은
    나중에 고칠 수 있지만 날짜는 못 고친다.
    """
    if event is None:
        return [Stat("행사", "없음", tone="warn",
                     hint="event.yaml 에 행사와 연사를 적어 주세요", tab="roster")]

    tasks = build_checklist(event)
    late = overdue_count(tasks, today)
    speakers = list(event.speakers)
    days_left = (event.event_date - today).days

    tiles = [
        Stat("지난 할 일", str(late), "건", tone="bad" if late else "ok",
             hint="날짜는 되돌릴 수 없습니다" if late else "지난 것이 없습니다",
             tab="checklist"),
        Stat("행사까지", str(days_left), "일",
             tone="warn" if 0 <= days_left <= 30 else "",
             hint=event.event_date.isoformat(), tab="checklist"),
        Stat("연사", str(len(speakers)), "명", tab="roster"),
    ]

    # 사례비를 세후(net)로 적기로 한 연사. 주최 측이 세금을 더 얹어 내야 해서
    # 예산이 22% 더 나간다. 결재를 다시 받는 일이 생기므로 미리 띄운다.
    net_basis = [s for s in speakers if s.paid and s.fee_basis == "net"]
    if net_basis:
        tiles.append(Stat(
            "세후로 약속한 연사", str(len(net_basis)), "명", tone="warn",
            hint="세금을 주최 측이 더 냅니다 — 예산이 늘어납니다", tab="tax"))

    long_stay = [s for s in speakers if s.stay_days > SHORT_STAY_DAYS]
    if long_stay:
        tiles.append(Stat(
            f"{SHORT_STAY_DAYS}일 초과 체류", str(len(long_stay)), "명", tone="warn",
            hint="사증면제로 안 됩니다", tab="visa"))

    budgets = build_budget(event)
    if budgets:
        total = sum(b.total for b in budgets)
        tiles.append(Stat("예산 합계", _won(total), "", tab="budget"))
    return tiles


def _visa_table(event) -> Table:
    """연사별로 **무엇을 확인해야 하는지.** 판정은 하지 않는다."""
    if event is None:
        return Table(headers=["연사"], rows=[], note="행사 정보가 없습니다.")

    rows, tones = [], []
    for speaker in event.speakers:
        hint = assess(paid=speaker.paid, days=speaker.stay_days,
                      visa_waiver=speaker.visa_waiver,
                      expenses_only=speaker.expenses_only)
        rows.append([
            speaker.name, speaker.country or "—",
            f"{speaker.stay_days}일" if speaker.stay_days else "미정",
            "있음" if speaker.paid else ("실비만" if speaker.expenses_only else "없음"),
            f"**{hint.name}** — {hint.when}",
        ])
        tones.append("bad" if hint.urgent else ("warn" if hint.kind != "면제" else ""))
    return Table(
        headers=["연사", "국적", "체류", "사례비", "확인할 것"],
        rows=rows, tones=tones,
        note="**이 표는 판정이 아닙니다.** 사증면제로 들어와도 사례비를 받으면 "
             "문제가 되는 경우가 있어, 반드시 아래를 확인하세요.\n\n"
             + "\n".join(f"- {item}" for item in MUST_CONFIRM),
    )


def console(program, ctx) -> Console:
    """16번 운영 콘솔."""
    today = date.today()
    event = _event()
    ui = build(program, ctx)

    def panel(key: str):
        return next((item for item in ui.admin if item.key == key), None)

    tabs = [
        Tab(key="roster", label="연사 명부", icon="👤", group="사람",
            intro="**사례비 유무·체류일수·사증면제 여부**가 나머지 모든 판단을 "
                  "바꿉니다. 여기부터 채우세요.",
            panels=[p for p in [panel("risk"), panel("roster"), panel("add")] if p]),
        Tab(key="visa", label="비자", icon="🛂", group="사람",
            intro="이 탭은 **판정하지 않습니다.** 무엇을 물어봐야 하는지 좁혀 드립니다.",
            panels=[Panel(key="visa", title="연사별 확인할 것",
                          table=_visa_table(event))]),
        Tab(key="tax", label="사례비·세금", icon="💸", group="돈",
            intro=f"비거주자 강연료는 주최 측이 **{TOTAL_RATE:.0%}** 를 떼고 드립니다. "
                  f"계약서에 적는 금액이 세전인지 세후인지를 **서명 전에** 정하세요.",
            panels=[p for p in [panel("tax"), panel("calc")] if p],
            common_buttons="`계산해 보기` — 명부에 넣기 전에 숫자만 견줘 볼 때."),
        Tab(key="budget", label="예산", icon="📊", group="돈",
            panels=[p for p in [panel("budget")] if p]),
        Tab(key="checklist", label="일정", icon="🗓", group="진행",
            intro="**지난 것이 맨 위**에 옵니다. 날짜는 되돌릴 수 없습니다.",
            panels=[p for p in [panel("checklist")] if p]),
        Tab(key="docs", label="문서", icon="📄", group="내보내기",
            intro="영문 초청장·계약서 초안·결재용 예산 엑셀.",
            panels=[p for p in [panel("docs")] if p]),
    ]

    return Console(
        program_id=program.id,
        title=program.name,
        subtitle=program.tagline,
        tabs=tabs,
        stats=_stats(event, today),
        todos=[
            Todo("지난 할 일이 있는지 보기", tab="checklist",
                 detail="비자 신청이 늦으면 연사가 **못 옵니다.** 돈은 나중에 "
                        "고칠 수 있지만 날짜는 못 고칩니다."),
            Todo("사례비를 세전으로 적을지 세후로 적을지 정하기", tab="tax",
                 detail="안 정하면 지급일에 연사는 500만 원을 기대하고 390만 원을 "
                        "받습니다. **서명 전에** 정하셔야 합니다."),
            Todo("조세조약 서류를 **지급일 전에** 받기", tab="tax", by_hand=True,
                 detail="지급 후에 받으면 소급이 안 되는 경우가 있습니다."),
            Todo("초청장을 보내고 연사 확인 받기", tab="docs", by_hand=True),
        ],
        manual_tasks=[
            ManualTask(
                task="비자 종류 확정",
                where="법무부 출입국·외국인정책본부, 또는 해당국 한국 공관",
                why="**이 프로그램은 판정하지 않습니다.** 국적·체류목적·사례비 "
                    "유무·체류일수가 얽혀 있고 예외가 많아, 틀리면 연사가 입국을 "
                    "거부당합니다. 여기서는 '무엇을 물어봐야 하는지' 만 좁혀 드립니다."),
            ManualTask(
                task="원천징수 세율 확정",
                where="세무대리인",
                why=NOT_TAX_ADVICE + " 조세조약은 나라마다 다르고, 같은 나라라도 "
                    "소득 종류에 따라 다릅니다. 여기 숫자는 **견줘 보시라고** "
                    "만든 것입니다."),
            ManualTask(
                task="계약서 검토",
                where="법무 담당자 또는 변호사",
                why="만들어 드리는 것은 **초안**입니다. 녹화물 범위와 취소 조항은 "
                    "기관마다 달라 일부러 비워 두었습니다.",
                someday="기관의 표준 계약서가 있으면 그 문구를 넣어 두고 쓰시면 "
                        "됩니다."),
            ManualTask(
                task="항공·숙소 예약",
                where="여행사 또는 예약 사이트",
                why="예산은 잡아 드리지만 예약은 하지 않습니다. 연사의 일정 변경이 "
                    "잦아 사람이 붙어 있어야 합니다."),
            ManualTask(
                task="초청장 발송과 연사 확인",
                where="이메일",
                why="문서는 만들어 드립니다. 보내고 답을 받는 것은 사람 일입니다."),
        ],
        troubles=[
            Trouble("비자가 '필요' 인지 '불필요' 인지 딱 말해 주지 않는다",
                    "일부러 그렇게 만들었습니다. **사증면제로 들어와도 사례비를 "
                    "받으면 문제가 되는 경우**가 있어, 잘못 단정하면 연사가 입국을 "
                    "거부당합니다. 비자 탭의 '확인할 것' 을 들고 공관에 문의하세요."),
            Trouble("연사가 받은 금액이 계약서와 다르다고 한다",
                    "세전/세후를 안 정하신 경우입니다. 사례비·세금 탭에서 "
                    "**기준 미정** 인 연사를 먼저 정리하세요. "
                    "다음부터는 계약서에 'gross(세전)' 인지 'net(세후)' 인지 "
                    "적어 두시면 이 일이 안 생깁니다."),
            Trouble("조세조약 감면을 못 받았다",
                    f"서류를 **지급일 전에** 받으셔야 합니다: "
                    f"{', '.join(TREATY_DOCS[:2])}. 지급 후에는 소급이 안 되는 "
                    "경우가 있습니다."),
            Trouble("체크리스트 날짜가 이미 지났다",
                    "행사일을 기준으로 거꾸로 계산한 날짜입니다. 지났다면 "
                    "**지금 당장** 하시고, 늦은 만큼 뒤의 일정도 당기셔야 합니다."),
            Trouble("연사를 넣었는데 표에 안 나온다",
                    "이름과 국적이 비어 있으면 명부에 들어가지 않습니다. "
                    "연사 명부 탭의 '연사 추가' 에서 다시 넣어 보세요."),
            Trouble("예산 엑셀이 결재 양식과 다르다",
                    "기관마다 양식이 달라 일반적인 형태로 만들어 드립니다. "
                    "받으신 뒤 열을 옮기셔서 쓰시면 됩니다."),
        ],
        files=[
            FileLoc("행사·연사", "products/speaker-desk/event.yaml",
                    "이 파일 하나에 다 들어 있습니다."),
            FileLoc("만든 문서", "products/speaker-desk/outputs/",
                    "초청장·계약서 초안·예산 엑셀."),
        ],
        admin_intro="**판정하지 않습니다.** 무엇을 확인해야 하는지 좁혀 드립니다. "
                    "실무 사고는 대부분 '물어봐야 하는 줄 몰라서' 납니다.",
        client_intro="해외 연사 초청에서 **빠뜨리기 쉬운 것**을 짚어 드립니다.",
        custom=True,
    )
