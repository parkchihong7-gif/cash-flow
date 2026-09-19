"""14번 전용 웹 화면 — **값을 바꾸면 견적이 바로 바뀐다.**

이 상품의 쓸모는 "얼마 드나" 보다 **"어디서 새나"** 에 있다. 그런데 CLI 로는
`plan.yaml` 을 고치고 명령을 다시 쳐야 견적이 바뀐다. 값을 바꿔 가며 비교해
보는 일이 번거로우면 아무도 안 한다.

화면이 알고 있어야 하는 것
--------------------------

* **가장 큰 줄을 짚어 준다.** 총액만 보면 어디를 손댈지 모른다
* **절감안에 대가를 같이 적는다.** ⚠ 는 시니어 시청자에게 불리한 선택이다
* **승인자 이름 없이는 승인 버튼이 안 먹는다.** 화면에서도 코드에서도
* 업로드 쿼터(하루 6편)를 미리 보여 준다. 나중에 알면 이미 늦다
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.webui import Field, Note, Panel, Table, WebUI          # noqa: E402

from senior_video.estimate import VideoPlan, estimate            # noqa: E402
from senior_video.rates import RateError, load_rates             # noqa: E402
from senior_video.savings import suggest                         # noqa: E402
from senior_video.senior import RULES, SPEC_SUMMARY, check_plan, grade  # noqa: E402
from senior_video.upload import (                                # noqa: E402
    AUDIT_NOTE, DAILY_UNITS, MAX_UPLOADS_PER_DAY, Queue, QueueError, UPLOAD_UNITS,
    uploads_possible,
)

PLAN = BASE_DIR / "plan.yaml"
RATES = BASE_DIR / "data" / "unit_costs.yaml"
QUEUE_DB = BASE_DIR / "queue.db"

NUMERIC_KEYS = ("script_chars", "images", "monthly_videos", "subtitle_px",
                "subtitle_chars", "speech_rate", "bgm_db", "length_minutes")
FLOAT_KEYS = ("scene_seconds", "contrast")


def _plan() -> VideoPlan:
    if not PLAN.is_file():
        return VideoPlan()
    raw = yaml.safe_load(PLAN.read_text(encoding="utf-8")) or {}
    known = VideoPlan().__dict__.keys()
    return VideoPlan(**{k: v for k, v in raw.items() if k in known})


def _won(value: float) -> str:
    return f"{value:,.0f}원"


def _estimate_panel(plan: VideoPlan, rates) -> Panel:
    est = estimate(plan, rates)
    rows, tones = [], []
    biggest = est.biggest
    for line in est.lines:
        rows.append([line.label, line.detail, _won(line.won),
                     _won(line.won * plan.monthly_videos), f"{est.share(line)}%"])
        tones.append("warn" if (biggest and line.key == biggest.key) else "")
    rows.append(["**합계**", "", f"**{_won(est.per_video)}**",
                 f"**{_won(est.per_month)}**", "100%"])
    tones.append("")

    notes = []
    if est.free:
        notes.append(Note("청구서가 날아오지 않는 조합입니다",
                          "무료 구간·무료 스톡·직접 작성. 대신 시간이 듭니다.", tone="ok"))
    else:
        notes.append(Note(
            f"편당 {_won(est.per_video)} · 월 {_won(est.per_month)} · 연 {_won(est.per_year)}",
            "", tone=""))
        if biggest:
            notes.append(Note(
                f"가장 큰 줄: {biggest.label} ({est.share(biggest)}%)",
                "**줄이시려면 여기부터 보셔야 합니다.**", tone="warn"))
    return Panel(
        key="estimate", title="견적", notes=notes,
        table=Table(headers=["항목", "계산", "편당", "월", "비중"],
                    rows=rows, tones=tones, numeric=[2, 3, 4],
                    note=f"단가 기준일 {est.asof} · 추정치입니다. "
                         f"실제 청구액은 각 서비스의 사용량 화면이 기준입니다."))


def _savings_panel(plan: VideoPlan, rates) -> Panel:
    est = estimate(plan, rates)
    items = suggest(est, rates)
    if not items:
        return Panel(key="savings", title="줄일 수 있는 것",
                     notes=[Note("더 줄일 것이 없습니다", "이미 무료 조합입니다.", tone="ok")])
    rows, tones = [], []
    for item in items:
        mark = " ⚠" if not item.senior_safe else ""
        rows.append([item.title + mark, _won(item.monthly_won),
                     _won(item.yearly_won), item.cost])
        tones.append("warn" if not item.senior_safe else "")
    top = items[0]
    return Panel(
        key="savings", title="줄일 수 있는 것",
        intro="**공짜 절감은 하나뿐입니다.** 나머지는 무언가를 내줍니다.",
        notes=[Note(f"가장 큰 것: {top.title}",
                    f"연 {_won(top.yearly_won)} · {top.how}", tone="ok")],
        table=Table(headers=["무엇", "월 절감", "연 절감", "대가"],
                    rows=rows, tones=tones, numeric=[1, 2],
                    note="⚠ 는 **시니어 시청자에게 불리해지는** 선택입니다. "
                         "아끼는 돈이 연 1만 원대인데 시청자가 떠나면 손해입니다."))


def _spec_panel(plan: VideoPlan) -> Panel:
    findings = check_plan(plan.as_check())
    rows, tones = [], []
    for item in findings:
        value = item.value if item.value not in (None, "") else "—"
        rows.append([item.rule.title, item.rule.recommended, str(value), item.label])
        tones.append("bad" if item.warn else ("ok" if item.ok else ""))
    warns = [item for item in findings if item.warn]
    notes = [Note(grade(findings), "", tone="bad" if warns else "ok")]
    for item in warns[:3]:
        notes.append(Note(item.rule.title, item.rule.why, tone="warn"))
    return Panel(
        key="spec", title="시니어 시청자 규격",
        intro=f"취향이 아니라 **몸이 달라서** 생기는 기준입니다. {SPEC_SUMMARY}",
        notes=notes,
        table=Table(headers=["항목", "권장", "지금 값", "판정"], rows=rows, tones=tones))


def _quota_panel(plan: VideoPlan) -> Panel:
    quota = uploads_possible(plan.monthly_videos)
    tone = "ok" if quota["fits"] else "bad"
    return Panel(
        key="quota", title="업로드 한도",
        notes=[
            Note(f"하루 10,000 유닛 · 업로드 한 번 {UPLOAD_UNITS:,} 유닛",
                 f"→ 하루 **{MAX_UPLOADS_PER_DAY}편**, 월 {quota['max_monthly']}편이 끝입니다."),
            Note(f"계획하신 월 {quota['monthly']}편 = 하루 {quota['per_day']}편",
                 "쿼터 안에 들어갑니다" if quota["fits"]
                 else "**쿼터를 넘습니다.** 편수를 줄이거나 상향 심사를 받으셔야 합니다",
                 tone=tone),
            Note("감사(audit)를 먼저 신청하세요", AUDIT_NOTE, tone="warn"),
        ],
        fields=[Field("monthly_videos", "월 몇 편", "number",
                      default=plan.monthly_videos)],
        action="do:quota", action_label="이 편수로 다시 보기")


def _queue_panel(mode: str) -> Panel:
    queue = Queue(QUEUE_DB)
    items = queue.list()
    rows, tones = [], []
    for item in items:
        rows.append([str(item.id), item.title, item.status_label,
                     item.approved_by or "—"])
        tones.append({"approved": "ok", "uploaded": "", "rejected": "bad"}.get(
            item.status, "warn"))
    counts = queue.counts()
    notes = [Note(
        "사람이 승인한 것만 올라갑니다",
        "유튜브 2025.7 양산형 콘텐츠 정책 때문입니다. "
        "**승인자 이름이 없으면 승인으로 치지 않습니다.**", tone="warn")]
    if counts.get("draft"):
        notes.append(Note(f"승인 기다리는 것 {counts['draft']}건",
                          "대본을 소리 내어 한 번 읽어 보시고 승인하세요.", tone=""))
    return Panel(
        key="queue", title="승인 대기열",
        notes=notes,
        table=Table(headers=["번호", "제목", "상태", "승인자"], rows=rows, tones=tones,
                    note="초안 → 사람 승인 → 올림. 승인 없이 올리는 길이 없습니다."),
        fields=[
            Field("title", "영상 제목", "text", placeholder="어르신 스마트폰 3편"),
            Field("script_chars", "대본 글자 수", "number", default=1500),
        ],
        action="do:queue_add", action_label="초안으로 넣기")


def _approve_panel() -> Panel:
    queue = Queue(QUEUE_DB)
    waiting = queue.list("draft")
    options = [f"{item.id} — {item.title}" for item in waiting]
    return Panel(
        key="approve", title="승인하기",
        intro="**승인자 이름이 없으면 거절합니다.** 이름 없는 승인은 자동 승인과 "
              "다르지 않기 때문입니다.",
        fields=[
            Field("item_id", "무엇을", "select",
                  options=options or ["— 승인 기다리는 것이 없습니다 —"]),
            Field("by", "승인하는 사람", "text", placeholder="홍길동", required=True),
            Field("note", "메모", "text", placeholder="자막 크기 확인함"),
        ],
        action="do:approve", action_label="승인",
        note="승인 전에 대본을 소리 내어 한 번 읽어 보세요. 어색한 문장이 바로 걸립니다.")


def _plan_fields(plan: VideoPlan, rates, client_mode: bool = False) -> list[Field]:
    tts = [row.key for row in rates.tts]
    images = [row.key for row in rates.image]
    scripts = [row.key for row in rates.script]
    fields = [
        Field("title", "영상 제목", "text", default=plan.title),
        Field("script_chars", "대본 글자 수", "number", default=plan.script_chars,
              help="10분 영상이면 2,700자쯤 됩니다."),
        Field("images", "쓸 이미지 장 수", "number", default=plan.images),
        Field("monthly_videos", "한 달에 몇 편", "number", default=plan.monthly_videos,
              help=f"API 로는 하루 {MAX_UPLOADS_PER_DAY}편이 한계입니다."),
        Field("tts", "음성 엔진", "select", default=plan.tts, options=tts,
              help="한국어 시니어 대상은 **클로바**가 가장 잘 맞습니다."),
        Field("image_source", "이미지", "select", default=plan.image_source,
              options=images),
    ]
    if not client_mode:
        fields.append(Field("script_source", "대본", "select",
                            default=plan.script_source, options=scripts))
    fields += [
        Field("subtitle_px", "자막 글자 크기(px)", "number", default=plan.subtitle_px or 64,
              help="1080p 기준 **64 이상**. 시니어 대상은 더 키워도 좋습니다."),
        Field("speech_rate", "말 속도(분당 음절)", "number",
              default=plan.speech_rate or 300, help="**300 이하**로."),
        Field("bgm_db", "배경음악(dB)", "number", default=plan.bgm_db or -18,
              help="말소리 대비 **-18 이하**. 아예 빼는 것도 좋습니다."),
        Field("scene_seconds", "장면 유지 시간(초)", "number",
              default=plan.scene_seconds or 4),
        Field("length_minutes", "영상 길이(분)", "number",
              default=plan.length_minutes or 10, help="8~15분이 무난합니다."),
    ]
    return fields


def build(program, ctx) -> WebUI:
    try:
        rates = load_rates(RATES)
    except RateError as exc:
        broken = Panel(key="broken", title="단가표를 읽지 못했습니다",
                       note=str(exc), tone="bad")
        return WebUI(program_id=program.id, title=program.name,
                     admin=[broken], client=[broken])

    plan = _plan()
    plan_panel = Panel(
        key="plan", title="기획 수치",
        intro="값을 바꾸고 저장하면 **바로 아래 견적이 다시 계산됩니다.**",
        fields=_plan_fields(plan, rates),
        action="do:plan", action_label="저장하고 다시 계산")

    admin = [
        plan_panel,
        _estimate_panel(plan, rates),
        _savings_panel(plan, rates),
        _spec_panel(plan),
        _quota_panel(plan),
        _queue_panel("admin"),
        _approve_panel(),
        Panel(key="run", title="견적서 파일로 받기",
              intro="`outputs/` 에 마크다운으로 저장합니다. 비용 0원입니다.",
              action="run", action_label="견적서 만들기", run_mode="dry"),
    ]

    client = [
        Panel(key="plan", title="내 영상 계획",
              intro="값을 바꾸시면 비용이 바로 다시 계산됩니다.",
              fields=_plan_fields(plan, rates, client_mode=True),
              action="do:plan", action_label="저장하고 다시 계산"),
        _estimate_panel(plan, rates),
        _savings_panel(plan, rates),
        _spec_panel(plan),
        Panel(key="run", title="견적서 받기",
              action="run", action_label="견적서 만들기", run_mode="dry"),
    ]

    return WebUI(
        program_id=program.id, title=program.name,
        admin=admin, client=client,
        admin_intro="값을 바꿔 가며 **어디서 새는지** 보세요. "
                    "절감안마다 무엇을 내주는지 같이 적혀 있습니다.",
        client_intro="어르신 대상 영상의 **비용과 규격**을 봐 드립니다. "
                     "자동 업로드는 하지 않습니다.",
    )


# ------------------------------------------------------------------ 동작
def handle(program, ctx, action: str, form: dict) -> str:
    if action == "plan":
        return _save_plan(form)
    if action == "quota":
        return _save_plan({**_current_raw(), "monthly_videos": form.get("monthly_videos")})
    if action == "queue_add":
        return _queue_add(form)
    if action == "approve":
        return _approve(form)
    return "error=모르는 동작입니다"


def _current_raw() -> dict:
    if not PLAN.is_file():
        return {}
    return yaml.safe_load(PLAN.read_text(encoding="utf-8")) or {}


def _save_plan(form: dict) -> str:
    payload = _current_raw()
    for key, value in form.items():
        text = str(value).strip()
        if key in NUMERIC_KEYS:
            if text == "":
                continue
            try:
                payload[key] = int(float(text))
            except ValueError:
                return f"error={key} 는 숫자로 적어 주세요"
        elif key in FLOAT_KEYS:
            if text == "":
                continue
            try:
                payload[key] = float(text)
            except ValueError:
                return f"error={key} 는 숫자로 적어 주세요"
        elif key in VideoPlan().__dict__:
            payload[key] = text

    if int(payload.get("monthly_videos") or 0) < 1:
        return "error=한 달 편수는 1 이상이어야 합니다"

    PLAN.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    quota = uploads_possible(int(payload.get("monthly_videos") or 0))
    if not quota["fits"]:
        return (f"saved=저장했습니다. 다만 월 {quota['monthly']}편은 API 쿼터를 "
                f"넘습니다 (최대 월 {quota['max_monthly']}편)")
    return "saved=저장했습니다. 견적을 다시 계산했습니다"


def _queue_add(form: dict) -> str:
    title = (form.get("title") or "").strip()
    if not title:
        return "error=영상 제목을 적어 주세요"
    try:
        chars = int(form.get("script_chars") or 0)
    except ValueError:
        chars = 0
    item_id = Queue(QUEUE_DB).add_draft(title, chars)
    return f"saved={item_id}번으로 넣었습니다. 승인 전에는 올릴 수 없습니다"


def _approve(form: dict) -> str:
    raw = (form.get("item_id") or "").strip()
    who = (form.get("by") or "").strip()
    if not who:
        return ("error=승인하는 사람 이름을 적어 주세요. "
                "이름 없는 승인은 자동 승인과 다르지 않습니다")
    if not raw or raw.startswith("—"):
        return "error=승인 기다리는 항목이 없습니다"
    try:
        item_id = int(raw.split("—")[0].strip())
    except ValueError:
        return "error=승인할 항목을 고르세요"
    try:
        item = Queue(QUEUE_DB).approve(item_id, who, (form.get("note") or "").strip())
    except QueueError as exc:
        return f"error={exc}"
    return f"saved={item.title} 을 {item.approved_by} 님이 승인했습니다"


# ══════════════════════════════════════════════════════════ 운영 콘솔
#
# 탭은 **어르신 대상 영상 채널을 돌리는 일**에서 나온다. 컨퍼런스 관리자의
# 탭을 베끼지 않는다. 이 사람이 하는 일은 이렇다.
#
#     한 달에 몇 편 만들지 정한다 → 비용이 얼마인지 본다 → 줄일 곳을 찾는다
#     → 어르신이 볼 수 있는 규격인지 본다 → 사람이 보고 승인한다 → 올린다
#
# '손으로 할 일' 표는 사용자가 이미 쓰고 있는 유튜브 자동 제작 관리자
# (`admin\MANUAL.html`) 의 「스튜디오에서 직접 할 일」 을 그대로 옮겼다.
# 지어낸 것이 아니라 실제로 API 가 못 하는 일들이다.

from core.console import Console, FileLoc, ManualTask, Stat, Tab, Todo, Trouble  # noqa: E402


def _stats(plan, rates) -> list[Stat]:
    """위쪽 타일. **달마다 나가는 돈**이 맨 앞이다.

    이 프로그램을 여는 이유가 그것이기 때문이다. 조회수나 편수를 앞에 두면
    정작 볼 것을 못 본다.
    """
    est = estimate(plan, rates)
    savings = suggest(est, rates)
    findings = check_plan(_current_raw())
    # 'warn' 은 권장값을 벗어난 것이다. 어르신이 못 보는 설정이라 여기서는
    # 경고가 아니라 **막아야 할 것**으로 센다. 돈보다 이게 먼저다.
    blocking = [item for item in findings if item.warn]
    possible = uploads_possible(plan.monthly_videos)

    tiles = [
        Stat("달마다", _won(est.per_month), "",
             hint=f"{plan.monthly_videos}편 기준", tab="estimate"),
        Stat("한 편에", _won(est.per_video), "", tab="estimate"),
    ]
    if savings:
        top = max(savings, key=lambda s: s.monthly_won)
        tiles.append(Stat(
            "줄일 수 있는 돈", _won(sum(s.monthly_won for s in savings)), "",
            tone="ok", hint=f"가장 큰 줄: {top.title}", tab="savings"))
    tiles.append(Stat(
        "시니어 규격", "통과" if not blocking else f"{len(blocking)}곳",
        tone="ok" if not blocking else "bad",
        hint="어르신이 못 보는 설정이 있습니다" if blocking else "권장값 안에 있습니다",
        tab="spec"))
    tiles.append(Stat(
        "하루 업로드 한도", str(MAX_UPLOADS_PER_DAY), "편",
        tone="warn" if not possible else "",
        hint="쿼터를 넘습니다 — 다음 날로 넘어갑니다" if not possible
             else f"하루 {DAILY_UNITS:,} 유닛",
        tab="quota"))
    return tiles


def console(program, ctx) -> Console:
    """14번 운영 콘솔."""
    try:
        rates = load_rates(RATES)
    except RateError as exc:
        return Console(
            program_id=program.id, title=program.name,
            tabs=[Tab(key="broken", label="단가표", icon="⚠",
                      panels=[Panel(key="broken", title="단가표를 읽지 못했습니다",
                                    note=str(exc), tone="bad")])],
            troubles=[Trouble("단가표를 못 읽는다",
                              "`data/unit_costs.yaml` 를 고치셨다면 되돌리거나, "
                              "**기본 세팅** 탭에서 검증값으로 돌리세요.")],
        )

    plan = _plan()
    est = estimate(plan, rates)

    tabs = [
        Tab(key="plan", label="기획 수치", icon="📐", group="정하는 자리",
            intro="여기서 바꾼 값이 **모든 탭의 계산을 바꿉니다.**",
            panels=[Panel(key="plan", title="기획 수치",
                          intro="값을 바꾸고 저장하면 바로 다시 계산됩니다.",
                          fields=_plan_fields(plan, rates),
                          action="do:plan", action_label="저장하고 다시 계산")]),
        Tab(key="estimate", label="견적", icon="💰", group="보는 자리",
            intro="무엇에 얼마가 드는지 **줄마다** 나눠 적었습니다.",
            panels=[_estimate_panel(plan, rates)]),
        Tab(key="savings", label="줄이기", icon="✂️", group="보는 자리",
            intro="줄이는 데에는 **대가가 있습니다.** 무엇을 내주는지 같이 적었습니다.",
            panels=[_savings_panel(plan, rates)]),
        Tab(key="spec", label="시니어 규격", icon="👓", group="보는 자리",
            intro="어르신이 **볼 수 있는지**를 봅니다. 돈보다 이게 먼저입니다.",
            panels=[_spec_panel(plan)],
            common_buttons=f"권장값 — {SPEC_SUMMARY}"),
        Tab(key="quota", label="업로드 한도", icon="📊", group="올리는 자리",
            intro="유튜브 API 는 하루 쓸 수 있는 양이 정해져 있습니다.",
            panels=[_quota_panel(plan)]),
        Tab(key="queue", label="승인 대기열", icon="✅", group="올리는 자리",
            intro="**사람이 보고 승인해야** 올라갑니다. 이 단계는 뺄 수 없습니다.",
            panels=[_queue_panel("admin"), _approve_panel()],
            admin_only=True),
        Tab(key="report", label="견적서", icon="📄", group="내보내기",
            panels=[Panel(key="run", title="견적서 파일로 받기",
                          intro="`outputs/` 에 마크다운으로 저장합니다. 비용 0원입니다.",
                          action="run", action_label="견적서 만들기", run_mode="dry")]),
    ]

    return Console(
        program_id=program.id,
        title=program.name,
        subtitle=program.tagline,
        tabs=tabs,
        stats=_stats(plan, rates),
        todos=[
            Todo("어젯밤 만들어진 편이 있으면 **직접 보고** 승인하기", tab="queue",
                 by_hand=True, admin_only=True,
                 detail="승인에는 이름이 들어갑니다. 누가 봤는지 남아야 합니다."),
            Todo("시니어 규격에 걸린 곳이 있는지 보기", tab="spec",
                 detail="자막이 작거나 말이 빠르면 어르신은 그냥 나갑니다."),
            Todo("이번 달 비용이 예상과 맞는지 보기", tab="estimate"),
            Todo("유튜브 스튜디오에서 공개 예약하기", by_hand=True,
                 detail="API 로는 **비공개까지만** 올라갑니다. 아래 '손으로 할 일' 참고."),
        ],
        # 아래 표는 사용자의 유튜브 자동 제작 관리자 매뉴얼 「스튜디오에서
        # 직접 할 일」 을 그대로 옮긴 것이다. 실제로 API 가 못 하는 일들이다.
        manual_tasks=[
            ManualTask(
                task="공개·예약 설정",
                where="YouTube 스튜디오 → 콘텐츠 → 영상 → 공개 상태 → 예약",
                why=AUDIT_NOTE,
                someday="구글 API 감사를 통과하면 예약 공개까지 자동으로 할 수 "
                        "있습니다. 신청부터 답까지 며칠에서 몇 주 걸립니다."),
            ManualTask(
                task="숏폼의 '관련 동영상' 로 롱폼 지정",
                where="스튜디오 → 숏폼 → 세부정보 → 관련 동영상",
                why="**API 가 지원하지 않습니다.** 게다가 Shorts 는 댓글·설명의 "
                    "링크가 눌리지 않아(2023-08-31 정책), 숏폼에서 롱폼으로 가는 "
                    "**유일한 길**이 이 버튼입니다. 빠뜨리면 숏폼 조회수가 롱폼으로 "
                    "이어지지 않습니다."),
            ManualTask(
                task="댓글 고정",
                where="영상 → 댓글 → ⋮ → 고정",
                why="댓글을 **다는 것**은 API 로 되지만 **고정**은 안 됩니다."),
            ManualTask(
                task="최종 화면·카드 편집",
                where="스튜디오 → 편집기 → 최종 화면 / 카드",
                why="API 미지원입니다.",
                someday="한 번 만들어 두고 '동영상에서 가져오기' 로 복사하면 "
                        "두 번째부터는 몇 초면 됩니다."),
            ManualTask(
                task="배너·워터마크·채널 홈 배치",
                where="스튜디오 → 맞춤설정",
                why="파일은 만들어 드릴 수 있지만 **등록은 손으로** 해야 합니다."),
            ManualTask(
                task="만든 영상을 직접 보고 승인",
                where="승인 대기열 탭",
                why="유튜브 2025-07 **양산형(비진정성) 콘텐츠** 정책 때문입니다. "
                    "사람이 안 본 영상을 대량으로 올리면 채널 전체가 수익화에서 "
                    "빠집니다. 이 단계는 기능이 아니라 **안전장치**라 뺄 수 없습니다."),
        ],
        troubles=[
            Trouble("견적이 생각보다 비싸다",
                    "**줄이기** 탭을 보세요. 가장 큰 줄은 보통 음성 엔진입니다. "
                    "다만 값싼 엔진은 어르신이 알아듣기 어려울 수 있어, 바꾸기 전에 "
                    "**시니어 적합도**를 같이 보세요."),
            Trouble("어제 만든 편이 공개가 안 됐다",
                    "API 로 올린 영상은 **비공개로 잠깁니다**(구글 API 감사 전). "
                    "스튜디오에서 직접 공개로 바꾸셔야 합니다. 위 '손으로 할 일' 참고."),
            Trouble("하루에 세 편밖에 못 올렸다",
                    f"업로드 한 번에 {UPLOAD_UNITS:,} 유닛이 들고 하루 한도가 "
                    f"{DAILY_UNITS:,} 유닛이라 **하루 {MAX_UPLOADS_PER_DAY}편**이 "
                    "상한입니다. 넘는 분량은 다음 날로 넘어갑니다. 쿼터는 기다리는 "
                    "것이 맞고, 재시도하면 더 깎입니다."),
            Trouble("자막이 잘려 보인다",
                    "한 줄 16자를 넘기면 어르신 화면에서 잘립니다. **시니어 규격** "
                    "탭에서 경고가 떴는지 보세요."),
            Trouble("어르신이 '말이 빠르다' 고 한다",
                    "분당 300음절을 넘겼을 때입니다. 대본을 줄이거나 음성 속도를 "
                    "낮추세요. 규격 탭에 지금 값이 나옵니다."),
            Trouble("승인 버튼이 안 먹는다",
                    "**이름을 적어야** 승인됩니다. 누가 보고 넘겼는지 남기지 않으면 "
                    "나중에 문제가 생겼을 때 확인할 방법이 없습니다."),
        ],
        files=[
            FileLoc("기획 수치", "products/senior-video/plan.yaml",
                    "모든 계산이 이 파일에서 나옵니다."),
            FileLoc("단가표", "products/senior-video/data/unit_costs.yaml",
                    "외부 요금이 바뀌면 여기를 고칩니다. 바꾸시면 **기본 세팅** "
                    "탭이 노랗게 뜹니다."),
            FileLoc("승인 대기열", "products/senior-video/data/queue.db"),
            FileLoc("견적서", "products/senior-video/outputs/"),
        ],
        admin_intro=f"한 달 **{_won(est.per_month)}** 이 드는 계획입니다. "
                    f"값을 바꿔 가며 어디서 새는지 보세요.",
        client_intro="어르신 대상 영상의 **비용과 규격**을 봐 드립니다. "
                     "이 화면에서 영상을 올리지는 않습니다.",
        custom=True,
    )
