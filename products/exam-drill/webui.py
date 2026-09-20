"""1번 전용 웹 화면 — **표를 화면에서 채운다.**

CLI 로 쓸 때 가장 번거로운 곳이 기록표였다. 엑셀을 따로 열어 O/X 를 치고,
저장하고, 다시 명령을 쳐야 한다. 그 사이에 파일을 잘못 저장하거나 열이
밀린다. 그래서 웹 화면에서는 **한 문항씩 바로 찍어 넣게** 만든다.

화면이 알고 있어야 하는 것
--------------------------

* **과락이 맨 위에 와야 한다.** 절대평가라 평균 65점으로 떨어진다.
  평균부터 보여 주면 사람이 판단을 그르친다
* **이유 칸이 비면 처방을 못 준다.** 그래서 틀림을 고르면 이유를 요구한다
* 문제 지문을 적는 칸은 **여기에도 없다** (README §2)
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.webui import Field, Note, Panel, Table, WebUI          # noqa: E402

from exam_drill.metrics import MIN_SAMPLE, PASS_AVERAGE, PASS_SUBJECT, analyze  # noqa: E402
from exam_drill.records import (                                  # noqa: E402
    COLUMNS, REASONS, REASON_FIX, RecordError, load_records, write_blank_sheet,
)
from exam_drill.syllabus import SUBJECTS, subject_of              # noqa: E402

RECORDS = BASE_DIR / "data" / "records.csv"

SUBJECT_OPTIONS = [f"{item.key} — {item.name}" for item in SUBJECTS]
UNIT_OPTIONS: list[str] = []
for _subject in SUBJECTS:
    UNIT_OPTIONS += _subject.units


def _analysis(path: Path):
    """지금 기록표를 읽어 지표로. 없거나 비었으면 None."""
    try:
        return analyze(load_records(path).attempts)
    except (RecordError, ValueError):
        return None


def _score_table(analysis) -> Table:
    rows, tones = [], []
    for item in analysis.subjects:
        rows.append([
            item.name, str(item.total), f"**{item.score}점**",
            f"{item.margin:+.1f}" if item.failing else "넘김",
            f"{item.median_seconds}초", item.top_reason or "—",
        ])
        tones.append("bad" if item.failing else ("warn" if item.too_slow else ""))
    return Table(
        headers=["과목", "푼 문항", "환산", "과락선까지", "문항당", "잦은 이유"],
        rows=rows, tones=tones, numeric=[1, 2, 3, 4],
        note=f"전 과목 평균 {analysis.average}점 · 합격선 {PASS_AVERAGE}점 "
             f"· 과목 과락선 {PASS_SUBJECT}점")


def _weak_table(analysis) -> Table:
    rows, tones = [], []
    for unit in analysis.weakest[:10]:
        name = next((s.name for s in analysis.subjects if s.key == unit.subject),
                    unit.subject)
        fix = REASON_FIX.get(unit.top_reason, "")
        rows.append([name, unit.unit, str(unit.total), f"**{unit.rate}%**", fix])
        tones.append("bad" if unit.rate < 40 else ("warn" if unit.rate < 60 else ""))
    return Table(
        headers=["과목", "단원", "푼 문항", "정답률", "해야 할 일"],
        rows=rows, tones=tones, numeric=[2, 3],
        note=f"{MIN_SAMPLE}문항 이상 푼 단원만 셉니다. "
             f"두 문제 중 하나를 50%라고 부르지 않기 위해서입니다.")


def _verdict_notes(analysis) -> list[Note]:
    if analysis is None:
        return [Note("아직 푼 기록이 없습니다",
                     "아래에서 한 문항씩 찍어 넣으시거나, 빈 기록표를 내려받아 채우세요.")]
    notes = []
    for item in analysis.failing:
        notes.append(Note(
            f"{item.name} {item.score}점 — 과락입니다",
            f"과락선까지 {item.margin}점 모자랍니다. **평균이 아무리 높아도 "
            f"한 과목이 40점 아래면 불합격입니다.**", tone="bad"))
    if not analysis.failing:
        notes.append(Note(
            f"과락 없음 · 평균 {analysis.average}점",
            analysis.verdict, tone="ok" if analysis.would_pass else "warn"))
    if analysis.untouched:
        names = ", ".join(item.name for item in analysis.untouched)
        notes.append(Note("아직 한 문제도 안 푼 과목",
                          f"{names} — 위 평균에 들어 있지 않습니다.", tone="warn"))
    return notes


def _entry_panel() -> Panel:
    """한 문항 찍어 넣기. 이 상품에서 가장 자주 쓰는 화면이다."""
    return Panel(
        key="entry", title="한 문항 채우기",
        intro="푸신 문제를 하나씩 찍어 넣으세요. **엑셀을 열 필요가 없습니다.**",
        fields=[
            Field("round_name", "회차", "text", default="36회",
                  placeholder="36회", required=True),
            Field("subject", "과목", "select", options=SUBJECT_OPTIONS, required=True),
            Field("number", "문항번호", "number", default=1, required=True),
            Field("correct", "결과", "select", options=["맞음", "틀림"], required=True),
            Field("unit", "단원", "select", options=[""] + UNIT_OPTIONS,
                  help="교재마다 이름이 다릅니다. 비슷한 것을 고르시면 됩니다."),
            Field("reason", "왜 틀렸나", "select", options=[""] + list(REASONS),
                  help="**틀렸을 때만.** 이유마다 해야 할 일이 다릅니다. "
                       "비우면 처방을 못 드립니다."),
            Field("seconds", "걸린 시간(초)", "number", default=0,
                  help="안 재셨으면 0으로 두세요."),
        ],
        action="do:add", action_label="이 문항 넣기",
        note="'맞음' 을 고르고 이유를 적으면 거절합니다. 줄이 밀린 것으로 봅니다.")


def build(program, ctx) -> WebUI:
    analysis = _analysis(RECORDS)
    count = analysis.attempts if analysis else 0

    # ---------------------------------------------------------- 관리자
    admin = [
        Panel(key="state", title="지금 상태",
              intro=f"기록표 `data/records.csv` · **{count}문항** 들어 있습니다.",
              notes=_verdict_notes(analysis),
              # 기록표 원본을 여는 링크는 두지 않는다. /preview 는 산출물
              # 폴더만 열도록 막혀 있고, 그 경계를 이 편의 하나 때문에
              # 넓힐 이유가 없다. 내용은 바로 아래 표에 다 있다.
              ),
        _entry_panel(),
    ]

    if analysis:
        admin += [
            Panel(key="scores", title="과목별 성적", table=_score_table(analysis)),
            Panel(key="weak", title="약한 단원", table=_weak_table(analysis)),
        ]

    admin += [
        Panel(key="sheet", title="빈 기록표 만들기",
              intro="회차별로 40문항짜리 빈 표를 만듭니다. 엑셀로 채우실 분용입니다.",
              fields=[
                  Field("round_name", "회차", "text", default="36회", required=True),
                  Field("subjects", "과목", "select",
                        options=["전 과목"] + SUBJECT_OPTIONS),
              ],
              action="do:sheet", action_label="빈 표 만들기",
              note="문제 지문을 적는 칸은 없습니다. 적지 마세요 (저작권)."),
        Panel(key="run", title="보고서 만들기",
              intro="지금 기록표로 마크다운·HTML 보고서를 만듭니다. "
                    "**Claude 를 부르지 않아 비용이 0원입니다.**",
              fields=[Field("input_path", "입력 파일", "text",
                            default="data/records.csv")],
              action="run", action_label="보고서 만들기", run_mode="dry"),
        Panel(key="clear", title="기록표 비우기",
              intro="테스트하다 쌓인 줄을 지웁니다. **되돌릴 수 없습니다.**",
              fields=[Field("confirm", "정말 지우시려면 '비움' 이라고 적으세요",
                            "text", placeholder="비움")],
              action="do:clear", action_label="비우기", tone="warn"),
    ]

    # -------------------------------------------------------- 클라이언트
    client = [
        Panel(key="state", title="내 점수",
              intro=f"지금까지 **{count}문항** 푸셨습니다.",
              notes=_verdict_notes(analysis)),
        _entry_panel(),
    ]
    if analysis:
        client += [
            Panel(key="scores", title="과목별", table=_score_table(analysis)),
            Panel(key="weak", title="어디가 약한가",
                  intro="**여기부터 보세요.** 이유마다 해야 할 일이 다릅니다.",
                  table=_weak_table(analysis)),
            Panel(key="run", title="보고서 받기",
                  intro="지금까지 푸신 것으로 보고서를 만듭니다.",
                  action="run", action_label="보고서 만들기", run_mode="dry"),
        ]

    return WebUI(
        program_id=program.id, title=program.name,
        admin=admin, client=client,
        admin_intro="기출을 풀고 **채점만 하고 넘기는 일**을 막는 도구입니다. "
                    "여기서 직접 찍어 넣어 보시고 불편한 곳을 찾으세요.",
        client_intro="푸신 문제를 찍어 넣으시면 **어디가 약한지** 알려 드립니다. "
                     "문제는 가지고 계신 문제집으로 푸세요.",
    )


# ------------------------------------------------------------------ 동작
def _subject_key(raw: str) -> str:
    return subject_of((raw or "").split("—")[0].strip()).key


def handle(program, ctx, action: str, form: dict) -> str:
    """이 상품에만 있는 동작을 처리한다."""
    if action == "add":
        return _add_row(form)
    if action == "sheet":
        return _make_sheet(form)
    if action == "clear":
        return _clear(form)
    return "error=모르는 동작입니다"


def _add_row(form: dict) -> str:
    correct = (form.get("correct") or "").strip() == "맞음"
    reason = (form.get("reason") or "").strip()
    unit = (form.get("unit") or "").strip()
    round_name = (form.get("round_name") or "").strip()

    if not round_name:
        return "error=회차를 적으세요"
    if correct and reason:
        return "error=맞은 문제에 이유가 적혀 있습니다. 줄이 밀리지 않았는지 보세요"
    if not correct and not reason:
        return "error=틀린 문제는 이유를 골라 주세요. 이유가 없으면 처방을 못 드립니다"

    try:
        subject = _subject_key(form.get("subject") or "")
        number = int(form.get("number") or 0)
        seconds = int(form.get("seconds") or 0)
    except ValueError as exc:
        return f"error={exc}"
    if not 1 <= number <= 40:
        return "error=문항번호는 1~40 사이입니다"

    RECORDS.parent.mkdir(parents=True, exist_ok=True)
    new_file = not RECORDS.is_file()
    with RECORDS.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(COLUMNS)
        writer.writerow([round_name, subject, number,
                         "O" if correct else "X", unit, reason, seconds])
    return f"saved={round_name} {number}번"


def _make_sheet(form: dict) -> str:
    round_name = (form.get("round_name") or "36회").strip()
    picked = (form.get("subjects") or "전 과목").strip()
    keys = ([item.key for item in SUBJECTS] if picked.startswith("전 과목")
            else [_subject_key(picked)])
    path = BASE_DIR / "data" / f"records_{round_name}.csv"
    write_blank_sheet(path, round_name, keys)
    return f"saved=빈 기록표 {path.name} 을 만들었습니다"


def _clear(form: dict) -> str:
    if (form.get("confirm") or "").strip() != "비움":
        return "error=지우려면 '비움' 이라고 정확히 적어 주세요"
    with RECORDS.open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerow(COLUMNS)
    return "saved=기록표를 비웠습니다"


# ══════════════════════════════════════════════════════════ 운영 콘솔
#
# 탭은 **공인중개사 수험에서** 나온다. 참조한 관리자(컨퍼런스·유튜브)의 탭을
# 베끼지 않는다. 이 사람이 하루에 하는 일은 이렇다.
#
#     기출을 푼다 → 채점한다 → 틀린 이유를 적는다 → 어디가 약한지 본다
#
# 그래서 '문항 채우기' 가 가장 크고 가장 먼저다. 나머지는 그 결과를 보는 자리다.
# 과락(40점)은 평균과 **다른 축**이라 탭을 따로 두었다 — 평균 70점이어도
# 한 과목이 39점이면 불합격이라, 같은 화면에 섞으면 사람이 판단을 그르친다.

from core.console import Console, FileLoc, ManualTask, Stat, Tab, Todo, Trouble  # noqa: E402

#: 한 문항에 쓰는 목표 시간. 1교시 100분/80문항 기준.
from exam_drill.metrics import TARGET_SECONDS                     # noqa: E402


def _stats(analysis) -> list[Stat]:
    """위쪽 타일. **과락이 맨 앞에 온다.**

    평균을 앞에 두면 과락을 못 보고 지나간다. 순서가 곧 판단 순서다.
    """
    if analysis is None:
        return [Stat("푼 문항", "0", "개", hint="먼저 한 문항 채워 보세요", tab="entry")]

    failing = analysis.failing
    tiles = [
        Stat("과락 위험", str(len(failing)), "과목",
             tone="bad" if failing else "ok",
             hint=", ".join(item.name for item in failing) if failing
                  else "40점 아래 과목이 없습니다",
             tab="scores"),
        Stat("평균", str(analysis.average), "점",
             tone="" if analysis.average >= PASS_AVERAGE else "warn",
             hint=f"합격선까지 {analysis.average_margin}점"
                  if analysis.average < PASS_AVERAGE else "합격선을 넘었습니다",
             tab="scores"),
        Stat("푼 문항", str(analysis.attempts), "개",
             hint=f"{len(analysis.rounds)}개 회차", tab="entry"),
    ]
    if analysis.untouched:
        tiles.append(Stat(
            "손 안 댄 과목", str(len(analysis.untouched)), "과목", tone="warn",
            hint="평균에서 빠져 있습니다 — 지금 평균은 실제보다 높습니다",
            tab="scores"))
    slow = [item for item in analysis.subjects if item.too_slow]
    if slow:
        tiles.append(Stat("시간 초과 과목", str(len(slow)), "과목", tone="warn",
                          hint=f"문항당 {TARGET_SECONDS}초를 넘습니다", tab="time"))
    return tiles


def _time_table(analysis) -> Table:
    """과목별 풀이 시간. 아는데 못 푸는 것과 모르는 것은 처방이 다르다."""
    rows, tones = [], []
    for item in analysis.subjects:
        if not item.median_seconds:
            continue
        over = item.median_seconds - TARGET_SECONDS
        rows.append([
            item.name, f"{item.median_seconds}초",
            f"{over:+d}초",
            f"{item.median_seconds * 40 // 60}분",
            "시간부족" if item.reasons.get("시간부족") else "—",
        ])
        tones.append("warn" if item.too_slow else "")
    return Table(
        headers=["과목", "문항당(중앙값)", f"{TARGET_SECONDS}초 대비", "40문항 환산", "이유"],
        rows=rows, tones=tones, numeric=[1, 2, 3],
        note=(f"**시험은 1교시 100분에 80문항**입니다. 문항당 {TARGET_SECONDS}초가 목표입니다. "
              "넘는 과목은 아는데 못 푸는 것이니, 더 외우지 마시고 **푸는 순서**를 바꿔 보세요. "
              "소요초를 안 적으신 문항은 여기 안 들어옵니다."),
    )


def _round_table(analysis) -> Table:
    """회차별 추이. 늘고 있는지 아닌지는 한 회차만 봐서는 모른다."""
    rows = []
    for name in analysis.rounds:
        per = [item for item in analysis.subjects if item.round_name == name]
        if not per:
            continue
        total = sum(item.total for item in per)
        avg = round(sum(item.score for item in per) / len(per), 1)
        rows.append([name, str(total), f"{avg}점",
                     ", ".join(item.name for item in per if item.failing) or "없음"])
    return Table(
        headers=["회차", "푼 문항", "평균", "과락 과목"], rows=rows, numeric=[1],
        note="회차가 하나뿐이면 추이를 말할 수 없습니다. **세 회차는 쌓여야** 늘었는지 보입니다.",
    )


def console(program, ctx) -> Console:
    """1번 운영 콘솔.

    **이 프로그램의 본체는 여기에 없다.** GitHub Pages 에서 돌고, 고객은
    거기로 들어간다. 그래서 이 화면은 프로그램을 흉내 내지 않는다.
    흉내 내면 사장님이 여기서 키를 발급하려 들고, 고객에게 이 주소를 보낸다.

    대신 **파는 사람이 실제로 하는 일**만 둔다.
      관리자 모드 — 팔기 전 확인 · 키 보내는 길 · 값 · 문의 대응
      클라이언트 모드 — 고객에게 그대로 읽어 드릴 사용 안내

    화면 글은 `docs/admin.md` · `docs/client.md` 와 같은 말을 해야 한다.
    한쪽만 고치면 고객이 서로 다른 안내를 두 번 받는다.
    """
    밖 = program.live
    관리자주소 = 밖.admin or "(program.yaml 의 live.admin 이 비었습니다)"
    고객주소 = 밖.client or "(program.yaml 의 live.client 가 비었습니다)"

    시작 = Tab(
        key="start", label="여기서 시작", icon="🚪", group="파는 자리",
        intro="이 프로그램의 본체는 **밖에서 돕니다.** 사장님 컴퓨터가 꺼져 있어도 "
              "고객은 들어갑니다. 여기서는 팔고 키를 보내는 일만 하십니다.",
        panels=[
            Panel(key="where", title="주소 세 개",
                  tone="good",
                  table=Table(
                      headers=["무엇", "어디로", "누가 봅니까"],
                      rows=[
                          ["관리자 모드", 관리자주소, "사장님"],
                          ["클라이언트 모드", 고객주소, "**고객에게 보낼 주소가 이것입니다**"],
                          ["접속키 발급", ".env 의 KEYSERVER_URL", "사장님"],
                      ]),
                  notes=[Note("", "고객이 들어가는 곳은 [클라이언트 모드] 와 **같은 주소**입니다. "
                              "따로 보내실 주소가 없습니다.", "info")]),
            Panel(key="flow", title="파는 순서",
                  lines=[
                      "1. **권리 확인** — 아래 [팔기 전 확인] 탭을 먼저 보십시오",
                      "2. 상세페이지 올리기 (문구 초안은 README 맨 아래)",
                      "3. 결제가 들어오면 [🔑 접속키 발급하기] 에서 이름·이메일 넣고 [이메일로 배포]",
                      "4. 주소와 키 네 개가 **한 통에** 갑니다. 따로 보내실 것이 없습니다",
                      "5. 문의가 오면 [문의 대응] 탭",
                  ]),
        ])

    권리 = Tab(
        key="rights", label="팔기 전 확인", icon="⚖️", group="파는 자리",
        admin_only=True,
        intro="**프로그램이 대신 해결해 드릴 수 없는 유일한 항목입니다.** "
              "문항 4,400개를 담아 파는 상품이라, 여기가 상품 전체를 뒤집을 수 있습니다.",
        panels=[
            Panel(key="why", title="무엇이 문제인가", tone="warn",
                  lines=[
                      "이 프로그램 안에는 실제 기출문제가 **지문과 보기까지 통째로** 들어 있습니다.",
                      "공개된 자료를 모아 상품으로 파는 것은 **별개의 판단**을 받습니다.",
                      "«공개돼 있으니 괜찮다» 가 아닙니다.",
                  ]),
            Panel(key="known", title="알려진 사실만",
                  lines=[
                      "공인중개사 시험은 **한국산업인력공단**이 시행하고 기출은 Q-Net 에 공개됩니다",
                      "저작권법 제7조는 국가·지자체의 고시·공고 등을 보호에서 제외합니다 — "
                      "시험문제가 여기 해당하는지는 자료마다 다르게 다뤄져 왔습니다",
                      "입시 문제를 어문저작물로 본 판례가 있습니다 (대법원 2007다354)",
                  ],
                  notes=[Note("", "여기까지가 말씀드릴 수 있는 범위입니다. **법률 자문이 아닙니다.**", "warn")]),
            Panel(key="todo", title="팔기 전에 하실 일",
                  lines=[
                      "**한국산업인력공단**(Q-Net)에 문의하고 답변을 **글로 받아 두기**",
                      "**한국저작권위원회** 무료 상담 (1800-5455)",
                      "답이 애매하면 **팔지 않기**",
                  ]),
            Panel(key="plan-b", title='답이 "안 된다" 로 나오면',
                  intro="상품을 버리실 필요는 없습니다. 껍데기는 두고 내용만 바꿉니다.",
                  lines=[
                      "사장님이 **직접 만든 문제**로 채우기 (학원·강사라면 이미 갖고 계십니다)",
                      "라이선스를 받은 문제집과 제휴",
                      "문제는 빼고 **채점·통계·복습 기능만** 파는 판",
                  ]),
        ])

    키 = Tab(
        key="howkeys", label="키 보내는 법", icon="✉️", group="파는 자리",
        admin_only=True,
        intro="키는 **앱스 스크립트 화면**에서 만듭니다. 여기서는 만들지 않습니다 — "
              "두 군데서 만들면 장부가 갈라집니다.",
        panels=[
            Panel(key="dual", title="한 사람에게 키가 네 개",
                  table=Table(
                      headers=["무엇", "몇 개", "쓰임"],
                      rows=[
                          ["1차키", "1개", "그 사람 본인"],
                          ["2차키", "3개", "PC · 노트북 · 휴대폰"],
                      ]),
                  notes=[Note("", "둘을 같이 넣어야 열립니다. 기기 세 대까지 쓰시고, "
                              "**같은 2차키로 다른 곳에서 또 들어가면 먼저 있던 쪽이 끊깁니다.**", "info")]),
            Panel(key="send", title="보내는 법",
                  lines=[
                      "[🔑 접속키 발급하기] → 개수 · 유효기간(일, 비우면 무제한) · 이름 · 이메일",
                      "[이메일로 배포] → **주소 + 키 네 개**가 한 통에 갑니다",
                      "실수했으면 목록에서 그 줄 [삭제]. 전부 다시면 [모든 키 초기화]",
                  ]),
            Panel(key="quota", title="하루에 몇 명까지", tone="warn",
                  table=Table(
                      headers=["계정", "하루 발송", "= 하루 발급"],
                      rows=[
                          ["개인 (@gmail.com)", "100통", "100명"],
                          ["워크스페이스 (회사 도메인)", "1,500통", "1,500명"],
                      ]),
                  notes=[Note("", "키 한 건이 메일 한 통입니다. 이것이 유일한 한도이고, "
                              "**그 밖의 서버 비용은 0원**입니다.", "info")]),
            Panel(key="resale", title="관리자 권한도 파실 수 있습니다",
                  intro="학원·강사에게 «수강생에게 직접 발급하세요» 로 파는 방식입니다.",
                  table=Table(
                      headers=["", "사장님", "산 분"],
                      rows=[
                          ["고객용 키 발급", "○", "○"],
                          ["관리자 키 발급", "○", "✕"],
                          ["보이는 목록", "전부", "자기가 발급한 것만"],
                          ["전체 초기화", "○", "✕"],
                          ["다루는 프로그램", "전부", "산 것 하나만"],
                      ]),
                  notes=[Note("", "**관리자 비밀번호는 절대 넘기지 마십시오.** "
                              "넘기면 위 표가 전부 무의미해집니다.", "warn")]),
        ])

    값 = Tab(
        key="price", label="값 정하기", icon="💰", group="파는 자리",
        admin_only=True,
        panels=[
            Panel(key="now", title="지금 적어 둔 값",
                  table=Table(
                      headers=["플랜", "값", "내용"],
                      rows=[[p.plan, f"{p.price:,}원", p.description] for p in program.pricing]),
                  notes=[Note("", "`program.yaml` 의 `pricing` 을 고치시면 바뀝니다.", "info")]),
            Panel(key="think", title="정하실 때 참고",
                  lines=[
                      "시중 기출문제집이 권당 2~3만 원입니다. 그 위로 올리려면 **설명이 필요합니다**",
                      "차별점은 문제 자체가 아니라 **복습함과 통계**입니다. 거기를 파세요",
                      "학원·강사 대상 관리자 권한은 **수강생 수 기준**으로 따로 잡으시는 편이 낫습니다",
                  ]),
            Panel(key="never", title="상세페이지에 쓰면 안 되는 것", tone="warn",
                  lines=[
                      "**합격을 약속하는 말.** 이 상품은 합격을 약속하지 않습니다",
                      "근거 없는 **합격률 숫자**",
                      "점수를 예측한다는 말 — 통계는 푸신 것의 정답률일 뿐입니다",
                      "AI 가 정답을 알려 준다는 말 — AI 풀이는 초안입니다",
                  ]),
            Panel(key="must", title="상세페이지에 반드시 넣을 것",
                  lines=[
                      "22개 회차 · **4,400문항** 이라는 구체적인 숫자",
                      "설치가 없고 휴대폰에서도 된다는 것",
                      "성적은 **그 브라우저에만** 남는다는 것 "
                      "(기기를 바꾸면 사라집니다 — 미리 말 안 하면 환불 사유가 됩니다)",
                      "AI 문제풀이는 **고객 본인 AI 계정**이 필요하다는 것",
                  ]),
        ])

    # ------------------------------------------------ 고객에게 그대로 읽어 드릴 것
    안내 = Tab(
        key="guide", label="고객 안내", icon="📖", group="고객에게",
        intro="상담할 때 이 탭을 띄워 놓고 그대로 읽어 드리시면 됩니다. "
              "사용 설명서(`docs/client.md`)와 같은 내용입니다.",
        panels=[
            Panel(key="first", title="처음 한 번 — 키 넣기",
                  lines=[
                      "메일의 주소를 누릅니다",
                      "**인증코드 입력** 칸이 나옵니다",
                      "**1차 인증키** — 메일에 하나. 그대로 넣습니다",
                      "**2차 인증키** — 메일에 세 개. **지금 쓰는 기기에 맞는 것**을 넣습니다",
                      "[확인] — 그 기기에서는 다시 안 물어봅니다",
                  ],
                  notes=[Note("", "여기서 제일 많이 헤맵니다. PC용을 휴대폰에 넣으면 안 됩니다.", "warn")]),
            Panel(key="screens", title="화면 여섯 개",
                  table=Table(
                      headers=["이름", "하는 일"],
                      rows=[
                          ["회차별 기출문제", "회차 → 1차·2차 과목. 실전처럼 한 회차 통째로"],
                          ["과목별 기출문제", "과목 → 회차 목록. 약한 과목만 몰아서"],
                          ["모의 기출문제", "과목별 40문항을 출제·보기 순서 무작위로 재배치"],
                          ["통계", "응시 회차 수 · 전체 정답률 · 가장 취약한 과목"],
                          ["복습함", "틀린 문제 · 저장한 문제 (전체 / 회차별)"],
                          ["⚙ 설정", "연습모드 · AI 서비스 고르기 · 전체 초기화"],
                      ])),
            Panel(key="scale", title="들어 있는 것",
                  table=Table(
                      headers=["", ""],
                      rows=[
                          ["회차", "제15회 ~ 제36회 (22개 회차)"],
                          ["문항", "4,400 (1차 1,760 · 2차 2,640)"],
                          ["1차", "부동산학개론 · 민법 및 민사특별법"],
                          ["2차", "공인중개사법령 및 중개실무 · 부동산공법 · "
                                  "부동산공시에 관한 법령 및 부동산세법"],
                      ])),
        ])

    공부 = Tab(
        key="howto", label="공부 순서", icon="🗓", group="고객에게",
        intro="«어떻게 쓰면 되냐» 는 질문에 이대로 답하시면 됩니다.",
        panels=[
            Panel(key="plan", title="네 단계",
                  table=Table(
                      headers=["시기", "연습모드", "무엇을"],
                      rows=[
                          ["처음 한 달", "켬", "[과목별] 로 한 과목씩. 틀려도 괜찮습니다 — "
                                              "복습함에 쌓이는 게 목적입니다"],
                          ["두 달째", "켬", "주 2회 새 회차 + 주 1회 **복습함만**"],
                          ["시험 두 달 전", "끔", "[회차별] 로 한 회차 통째로, 시간 재며"],
                          ["시험 2주 전", "끔", "새 문제 금지. **복습함만** 도십니다"],
                      ])),
            Panel(key="weak", title="다음에 뭘 할지는 [통계] 가 정해 줍니다",
                  lines=[
                      "공인중개사는 **과락**이 있습니다. 한 과목이 40점 아래면 "
                      "나머지가 아무리 좋아도 불합격입니다",
                      "그래서 평균보다 **제일 낮은 과목**이 먼저입니다",
                      "[통계] 의 «가장 취약한 과목» → [과목별 기출문제] 에서 그 과목",
                  ]),
            Panel(key="ai", title="🤖 AI 문제풀이 쓰는 법",
                  lines=[
                      "누르면 고르신 AI 서비스 창이 열리고 **질문이 클립보드에 복사**됩니다",
                      "그 창에 **Ctrl+V** (휴대폰은 길게 눌러 붙여넣기)",
                      "AI 가 쓴 풀이는 **초안**입니다. 완성된 답이 아닙니다",
                  ],
                  notes=[Note("", "순서를 지키시면 됩니다 — "
                              "**AI 초안 읽기 → ✅ 정답 확인 → 다르면 정답이 맞습니다.**", "warn")]),
        ])

    문의 = Tab(
        key="ask", label="문의 대응", icon="💬", group="고객에게",
        intro="실제로 들어오는 것들입니다. 답을 그대로 쓰시면 됩니다.",
        panels=[
            Panel(key="qa", title="자주 들어오는 것",
                  table=Table(
                      headers=["문의", "답"],
                      rows=[
                          ["문제집이랑 뭐가 다른가요",
                           "틀린 문제가 **자동으로** 모입니다. 종이는 본인이 표시하고 "
                           "찾아가야 하는데 두 달쯤 지나면 안 합니다"],
                          ["휴대폰으로 되나요",
                           "됩니다. 2차키가 셋이라 기기 세 대까지"],
                          ["**성적이 사라졌어요**",
                           "브라우저 기록을 지우셨거나 다른 기기입니다. 성적은 서버가 아니라 "
                           "**그 브라우저 안에** 있습니다. 고칠 수 있는 문제가 아니라 구조입니다"],
                          ["모의고사는 새 문제인가요",
                           "아닙니다. 기출 안에서 순서만 바꿉니다. 없던 문제를 지어내지 않습니다"],
                          ["AI 풀이가 틀렸어요",
                           "있을 수 있습니다. 정답은 [✅ 정답 확인] 이 기준입니다"],
                          ["키가 안 먹습니다",
                           "① 1차/2차를 바꿔 넣었는지 ② 그 기기용 2차키인지 "
                           "③ 유효기간이 지났는지"],
                      ])),
            Panel(key="refund", title="환불 요청이 들어오면", tone="warn",
                  table=Table(
                      headers=["말", "어떻게"],
                      rows=[
                          ["기기를 바꿨더니 성적이 없어졌다",
                           "구조상 그렇습니다. **미리 안내 안 하셨으면 사장님 책임입니다.** "
                           "환불하시고 상세페이지를 고치십시오"],
                          ["AI 가 필요한 줄 몰랐다",
                           "AI 없이 모든 기능이 돕니다. 그렇게 설명하고, 그래도 원하시면 환불"],
                          ["생각보다 문제가 적다",
                           "4,400문항이 상세페이지에 적혀 있으면 이 말이 안 나옵니다"],
                      ])),
        ])

    return Console(
        program_id=program.id,
        title=program.name,
        subtitle=program.tagline,
        tabs=[시작, 권리, 키, 값, 안내, 공부, 문의],
        stats=[
            Stat(label="문항", value="4,400", tone="good"),
            Stat(label="회차", value="22", unit="개", hint="제15회 ~ 제36회"),
            Stat(label="과목", value="5", unit="개", hint="1차 2 · 2차 3"),
            Stat(label="서버 비용", value="0", unit="원",
                 tone="good", hint="GitHub Pages + 앱스 스크립트 + 구글 시트"),
        ],
        todos=[
            Todo("**팔기 전에** 기출 재배포 권리 확인하기", tab="rights", admin_only=True,
                 by_hand=True,
                 detail="한국산업인력공단에 문의하고 답을 글로 받아 두십시오. "
                        "이 항목만은 프로그램이 대신 못 합니다."),
            Todo("결제가 들어온 건 키 발급하기", tab="howkeys", admin_only=True,
                 detail="[🔑 접속키 발급하기] → 이름·이메일 → [이메일로 배포]. "
                        "**주소와 키가 한 통에** 갑니다."),
            Todo("들어온 문의에 답하기", tab="ask",
                 detail="«성적이 사라졌어요» 가 제일 많습니다. 구조라서 못 고칩니다 — "
                        "파실 때 미리 말씀하시는 것이 유일한 예방입니다."),
        ],
        manual_tasks=[
            ManualTask(
                task="기출 재배포 권리 확인",
                where="한국산업인력공단 · 한국저작권위원회 (1800-5455)",
                why="문항 4,400개를 담아 파는 상품입니다. **법률 판단은 프로그램이 "
                    "대신 할 수 없습니다.** 답을 글로 받아 두십시오."),
            ManualTask(
                task="키를 만들고 보내는 것",
                where="구글 앱스 스크립트 접속키 관리자",
                why="장부가 구글 시트에 있어서 **그 화면 하나에서만** 만듭니다. "
                    "여기서도 만들면 두 장부가 갈라집니다.",
                someday="대시보드에서 눌러도 시트에 바로 적히게 이어 둘 수 있습니다."),
            ManualTask(
                task="회차 추가 (제37회~)",
                where="GitHub Pages 저장소의 index.html",
                why="문항이 프로그램 파일 안에 들어 있습니다. 시험이 끝나면 "
                    "거기에 넣고 다시 올리셔야 합니다."),
        ],
        troubles=[
            Trouble("[🔑 접속키 발급하기] 버튼이 안 보인다",
                    "`.env` 에 `KEYSERVER_URL` 이 없습니다. 앱스 스크립트 배포 주소"
                    "(`…/exec`)를 넣으시면 생깁니다. **저장소가 공개라 파일에 박아 두지 "
                    "않았습니다.**"),
            Trouble("[관리자 모드] · [클라이언트 모드] 가 안 열린다",
                    "`program.yaml` 의 `live.admin` · `live.client` 를 보십시오. "
                    "비밀번호는 여기 적지 않습니다 — 사장님이 따로 보관하신 것을 쓰십니다."),
            Trouble("고객이 «어디로 들어가냐» 고 묻는다",
                    "메일에 주소가 들어 있습니다. 못 찾으시면 [클라이언트 모드] 의 주소를 "
                    "그대로 알려 드리십시오. 같은 주소입니다."),
            Trouble("고객 성적이 사라졌다고 한다",
                    "브라우저 안에만 저장되는 구조입니다. **고칠 수 없습니다.** "
                    "파실 때 미리 말씀하시는 것이 유일한 예방입니다."),
            Trouble("하루에 키를 100개 넘게 보내야 한다",
                    "개인 구글 계정의 메일 한도입니다. 워크스페이스(회사 도메인)로 "
                    "옮기시면 1,500통이 됩니다."),
        ],
        files=[
            FileLoc("프로그램 본체", 고객주소,
                    "이 저장소가 아니라 GitHub Pages 에 있습니다. 문항도 그 안에 있습니다."),
            FileLoc("접속키 장부", "구글 시트",
                    "누구에게 언제 무슨 키가 나갔는지. **직접 고치지 마십시오** — "
                    "프로그램이 읽는 표입니다."),
            FileLoc("키 서버 주소", ".env 의 KEYSERVER_URL",
                    "공개 저장소라 파일에 박지 않습니다. `.env` 는 커밋되지 않습니다."),
            FileLoc("파는 문구 초안", "products/exam-drill/README.md"),
        ],
        admin_intro="**본체는 밖에서 돕니다.** 사장님 컴퓨터가 꺼져 있어도 고객은 "
                    "들어갑니다. 여기서는 팔고, 키를 보내고, 문의에 답하는 일만 하십니다. "
                    "**팔기 전에 [팔기 전 확인] 탭을 먼저 보십시오.**",
        client_intro="고객에게 그대로 읽어 드릴 안내입니다. 고객이 실제로 쓰는 화면은 "
                     "위 [클라이언트 모드 ↗] 버튼의 주소입니다 — 이 화면이 아닙니다.",
        custom=True,
    )
