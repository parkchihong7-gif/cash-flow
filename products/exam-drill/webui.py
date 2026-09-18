"""13번 전용 웹 화면 — **표를 화면에서 채운다.**

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
