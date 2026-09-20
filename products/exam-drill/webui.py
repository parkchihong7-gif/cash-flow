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
    """1번 운영 콘솔."""
    analysis = _analysis(RECORDS)
    count = analysis.attempts if analysis else 0
    ui = build(program, ctx)

    def panel(key: str):
        return next((item for item in ui.admin if item.key == key), None)

    tabs = [
        Tab(key="entry", label="문항 채우기", icon="✏️", group="푸는 자리",
            intro="한 문항씩 바로 찍어 넣습니다. **엑셀을 열 필요가 없습니다.**",
            panels=[p for p in [panel("state"), panel("entry")] if p],
            common_buttons="`채우기` — 틀림을 고르시면 이유를 꼭 물어봅니다."),
    ]

    if analysis:
        tabs += [
            Tab(key="scores", label="과목별 성적", icon="📊", group="보는 자리",
                intro="**과락부터 보세요.** 평균이 아무리 높아도 한 과목이 40점 "
                      "아래면 불합격입니다.",
                panels=[Panel(key="scores", title="과목별", notes=_verdict_notes(analysis),
                              table=_score_table(analysis))]),
            Tab(key="weak", label="약한 단원", icon="🎯", group="보는 자리",
                intro="이유마다 **해야 할 일이 다릅니다.** 같은 오답이 아닙니다.",
                panels=[Panel(key="weak", title="약한 단원", table=_weak_table(analysis))]),
            Tab(key="time", label="시간", icon="⏱️", group="보는 자리",
                intro="아는데 못 푸는 것과 모르는 것은 처방이 다릅니다.",
                panels=[Panel(key="time", title="과목별 풀이 시간",
                              table=_time_table(analysis))]),
            Tab(key="rounds", label="회차", icon="📋", group="보는 자리",
                panels=[Panel(key="rounds", title="회차별 추이",
                              table=_round_table(analysis))]),
        ]

    tabs += [
        Tab(key="report", label="보고서", icon="📄", group="내보내기",
            panels=[p for p in [panel("run")] if p]),
        Tab(key="sheet", label="빈 기록표", icon="📥", group="내보내기",
            intro="엑셀로 채우실 분용입니다. 회차별 40문항짜리 빈 표를 만듭니다.",
            panels=[p for p in [panel("sheet")] if p]),
        Tab(key="danger", label="기록 지우기", icon="🗑", group="내보내기",
            admin_only=True,
            panels=[p for p in [panel("clear")] if p]),
    ]

    todos = [
        Todo("오늘 푼 기출을 한 문항씩 찍어 넣기", tab="entry",
             detail="틀린 것만 넣어도 됩니다. **맞은 것도 넣으면** 정답률이 정확해집니다."),
        Todo("과락 과목이 생겼는지 보기", tab="scores",
             detail="40점 아래가 하나라도 있으면 그 과목부터 하세요."),
        Todo("약한 단원의 **이유**를 보고 오늘 할 일 정하기", tab="weak",
             detail="`몰라서` 면 개념서, `헷갈려서` 면 비교표, `실수` 면 검산, "
                    "`시간부족` 이면 푸는 순서입니다."),
    ]

    return Console(
        program_id=program.id,
        title=program.name,
        subtitle=program.tagline,
        tabs=tabs,
        stats=_stats(analysis),
        todos=todos,
        manual_tasks=[
            ManualTask(
                task="문제를 푸는 것",
                where="가지고 계신 문제집·기출 사이트",
                why="이 프로그램에는 **문제 지문을 넣는 칸이 없습니다.** 기출 지문은 "
                    "저작권이 있어 옮겨 담지 않습니다. 여기는 **채점 결과와 이유**만 "
                    "받습니다."),
            ManualTask(
                task="틀린 이유를 고르는 것",
                where="문항 채우기 탭",
                why="`몰라서` 와 `헷갈려서` 는 본인만 압니다. 이걸 프로그램이 짐작하면 "
                    "처방이 통째로 틀립니다.",
                someday="정답 선택지까지 받으면 '헷갈림' 을 일부 짐작할 수 있지만, "
                        "그러려면 지문이 필요해 하지 않습니다."),
            ManualTask(
                task="소요 시간 재기",
                where="스톱워치·시계",
                why="화면에 머문 시간을 재면 딴짓한 시간까지 들어갑니다. 재실 수 "
                    "있는 분만 적으시면 됩니다 — 비워 두셔도 나머지는 다 나옵니다."),
        ],
        troubles=[
            Trouble("과락 경고가 안 뜬다",
                    f"한 과목에 **{MIN_SAMPLE}문항 미만**이면 판정하지 않습니다. "
                    "세 문항이면 우연히 다 틀릴 수 있어서입니다. 더 넣어 보세요."),
            Trouble("평균이 실제보다 높게 나온다",
                    "안 푼 과목은 평균에서 빠집니다. 위쪽 **손 안 댄 과목** 타일을 "
                    "보세요. 다섯 과목을 다 풀어야 진짜 평균입니다."),
            Trouble("줄이 밀렸다고 나온다",
                    "회차·과목·문항번호 중 하나가 비었을 때입니다. "
                    "문항 채우기 탭에서 넣으시면 이 일이 생기지 않습니다."),
            Trouble("시간 표가 비어 있다",
                    "소요초를 한 번도 안 적으셨습니다. 안 적으셔도 되지만, "
                    "적으시면 '아는데 못 푸는' 과목이 보입니다."),
            Trouble("단원이 '기타' 로만 쌓인다",
                    "단원을 안 고르고 넣으셨습니다. 단원이 없으면 **어디가 약한지** "
                    "를 못 냅니다. 채우실 때 같이 골라 주세요."),
        ],
        files=[
            FileLoc("기록표", "products/exam-drill/data/records.csv",
                    "이 파일 하나가 전부입니다. 백업은 이것만 복사하시면 됩니다."),
            FileLoc("과목·단원 목록", "products/exam-drill/exam_drill/syllabus.py",
                    "출제 범위가 바뀌면 여기를 고칩니다."),
            FileLoc("보고서", "products/exam-drill/outputs/"),
        ],
        admin_intro=f"기출을 풀고 **채점만 하고 넘기는 일**을 막는 도구입니다. "
                    f"지금 기록표에 {count}문항 들어 있습니다.",
        client_intro="푸신 문제를 찍어 넣으시면 **어디가 약한지** 알려 드립니다. "
                     "문제는 가지고 계신 문제집으로 푸세요.",
        custom=True,
    )
