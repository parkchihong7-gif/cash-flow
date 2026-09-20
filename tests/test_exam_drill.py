"""13번 공인중개사 기출 풀이 분석기 테스트.

가장 중요한 검사는 **문제 본문이 들어올 자리가 없는지**다. 기능이 아니라
설계를 지키는 테스트라서, 칸이 늘어나면 여기서 먼저 걸린다.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from conftest import load_product_cli
from core.registry import Registry
from exam_drill.metrics import (
    MIN_SAMPLE, PASS_AVERAGE, PASS_SUBJECT, TARGET_SECONDS, analyze,
)
from exam_drill.plan import BANNED, banned_hits, facts_for, offline_plan, plan_for
from exam_drill.records import (
    COLUMNS, REASONS, Attempt, RecordError, load_records, write_blank_sheet,
)
from exam_drill.report import write_html, write_markdown
from exam_drill.syllabus import SUBJECTS, subject_of

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "exam-drill"
SAMPLE = PRODUCT / "data" / "samples" / "records_sample.csv"


@pytest.fixture
def analysis():
    return analyze(load_records(SAMPLE).attempts)


# --------------------------------------------- 문제 본문이 들어올 자리가 없다
def test_record_sheet_has_no_place_for_question_text():
    """지문·보기·정답 칸이 생기면 그 순간 기출문제 사본이 된다."""
    joined = " ".join(COLUMNS)
    for forbidden in ("지문", "보기", "정답", "문제", "본문", "해설"):
        assert forbidden not in joined, f"기록표에 '{forbidden}' 칸이 생겼습니다"


def test_attempt_rejects_unknown_columns():
    """모르는 칸을 넣으면 거절한다. 슬며시 늘어나는 것을 막는다."""
    with pytest.raises(Exception):
        Attempt(round_name="35회", subject="civil", number=1, correct=False,
                question_text="문제 지문입니다")


def test_blank_sheet_only_has_the_declared_columns(tmp_path):
    path = write_blank_sheet(tmp_path / "s.csv", "36회", ["civil"])
    with path.open(encoding="utf-8-sig") as handle:
        header = next(csv.reader(handle))
    assert tuple(header) == COLUMNS
    assert len(path.read_text(encoding="utf-8-sig").splitlines()) == 41  # 머리글 + 40문항


def test_model_never_receives_question_text(analysis):
    """Claude 에 넘어가는 것은 단원명과 숫자뿐이다."""
    facts = facts_for(analysis)
    assert "부동산공법" in facts
    assert "점" in facts
    # 단원 이름은 있어도 문항 단위 정보는 없어야 한다.
    assert "번 문항" not in facts
    assert "지문" not in facts and "보기" not in facts


# ------------------------------------------------------------ 기록표 읽기
def test_unanswered_rows_are_skipped(tmp_path):
    """빈 표를 미리 뽑아 두고 푸는 대로 채우는 쓰임을 전제로 한다."""
    path = write_blank_sheet(tmp_path / "s.csv", "36회", ["civil"])
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    rows[1][3] = "O"
    rows[2][3] = "X"
    rows[2][5] = "몰라서"
    path.write_text("\n".join(",".join(row) for row in rows), encoding="utf-8-sig")

    result = load_records(path)
    assert result.count == 2
    assert len(result.skipped) == 38


def test_empty_sheet_says_what_to_do(tmp_path):
    path = write_blank_sheet(tmp_path / "s.csv", "36회", ["civil"])
    with pytest.raises(RecordError, match="O 나 X"):
        load_records(path)


def test_reason_on_a_correct_answer_is_a_shifted_row():
    """맞은 문제에 이유가 붙어 있으면 대개 줄이 밀린 것이다."""
    with pytest.raises(Exception, match="줄이 밀리지"):
        Attempt(round_name="35회", subject="civil", number=3,
                correct=True, reason="실수")


def test_unknown_reason_is_rejected():
    with pytest.raises(Exception):
        Attempt(round_name="35회", subject="civil", number=3,
                correct=False, reason="그냥")


def test_o_and_zero_both_mean_correct(tmp_path):
    """손으로 적을 때 O 와 0 을 섞어 쓴다. 둘 다 받아 준다."""
    path = tmp_path / "s.csv"
    path.write_text(
        "회차,과목,문항번호,정오,단원,이유,소요초\n"
        "35회,civil,1,O,대리,,60\n"
        "35회,civil,2,0,대리,,55\n", encoding="utf-8-sig")
    result = load_records(path)
    assert [item.correct for item in result.attempts] == [True, True]


def test_missing_column_names_the_missing_one(tmp_path):
    path = tmp_path / "s.csv"
    path.write_text("회차,과목,문항번호\n35회,civil,1\n", encoding="utf-8-sig")
    with pytest.raises(RecordError, match="정오"):
        load_records(path)


# ---------------------------------------------------------------- 지표
def test_failing_subject_beats_the_average(analysis):
    """과락이 있으면 평균을 말하지 않는다. 평균부터 보면 판단을 그르친다."""
    assert analysis.failing, "샘플에는 과락 과목이 있어야 한다"
    assert "과락" in analysis.verdict
    assert "평균이 아무리 높아도" in analysis.verdict


def test_public_law_is_the_weak_subject_in_the_sample(analysis):
    public = next(item for item in analysis.subjects if item.key == "public")
    assert public.failing
    assert public.score < PASS_SUBJECT
    assert public.margin > 0, "과락선까지 남은 점수는 양수여야 한다"


def test_thin_units_are_not_counted(analysis):
    """두 문제 중 하나 틀린 것을 50%라고 부르지 않는다."""
    for unit in analysis.weakest:
        assert unit.total >= MIN_SAMPLE


def test_median_is_used_for_time_not_mean():
    """한 문제에서 5분 붙잡은 것이 전체를 끌고 가면 안 된다."""
    rows = [Attempt(round_name="35회", subject="civil", number=n,
                    correct=True, seconds=60) for n in range(1, 10)]
    rows.append(Attempt(round_name="35회", subject="civil", number=10,
                        correct=True, seconds=900))
    civil = analyze(rows).subjects[0]
    assert civil.median_seconds == 60, "중앙값이어야 한다"
    assert not civil.too_slow


def test_slow_subject_is_flagged():
    rows = [Attempt(round_name="35회", subject="public", number=n,
                    correct=True, seconds=TARGET_SECONDS + 30) for n in range(1, 8)]
    assert analyze(rows).subjects[0].too_slow


def test_untouched_subjects_are_called_out():
    """안 푼 과목은 평균에서 빠져 있으니 짚어 줘야 한다."""
    rows = [Attempt(round_name="35회", subject="civil", number=n, correct=True)
            for n in range(1, 6)]
    result = analyze(rows)
    assert len(result.untouched) == len(SUBJECTS) - 1
    assert result.average == 100.0


def test_pass_needs_both_no_failing_and_the_average():
    """평균만 넘겨서는 안 된다. 과목 하나가 40점 아래면 불합격이다."""
    rows = [Attempt(round_name="35회", subject="civil", number=n, correct=True)
            for n in range(1, 11)]
    rows += [Attempt(round_name="35회", subject="public", number=n, correct=False,
                     reason="몰라서") for n in range(1, 11)]
    result = analyze(rows)
    assert result.average == 50.0 < PASS_AVERAGE
    assert not result.would_pass
    assert [item.key for item in result.failing] == ["public"]


# ---------------------------------------------------------------- 계획
def test_offline_plan_starts_with_the_failing_subject(analysis):
    lines = offline_plan(analysis)
    assert lines
    assert "부동산공법" in lines[0]
    assert len(lines) <= 8


def test_plan_replaces_promises_with_rule_written_lines(analysis):
    """모델이 합격을 약속하면 그 줄만 규칙 문장으로 갈아 끼운다."""
    def fake_ask(system, user, model="", max_tokens=0):
        return ("이대로 하면 반드시 합격합니다\n"
                "부동산공법 국토계획법 총칙을 다시 봅니다")

    lines = plan_for(analysis, fake_ask, "test-model")
    assert lines
    for line in lines:
        assert banned_hits(line) == [], line
    assert any("부동산공법" in line for line in lines)


def test_banned_list_covers_the_obvious_promises():
    for word in ("합격을 보장", "무조건 합격", "족보"):
        assert word in BANNED


def test_plan_prompt_forbids_inventing_questions():
    from exam_drill.plan import PLAN_SYSTEM
    assert "문제 본문은 받지 않습니다" in PLAN_SYSTEM
    assert "지어내지 않습니다" in PLAN_SYSTEM


# ---------------------------------------------------------------- 보고서
def test_report_leads_with_the_failing_subject(tmp_path, analysis):
    path = write_markdown(analysis, tmp_path, plan=offline_plan(analysis))
    text = path.read_text(encoding="utf-8")
    assert text.index("과락 위험") < text.index("## 과목별")
    assert "이 프로그램이 하지 않는 것" in text
    assert "기출문제 지문" in text


def test_report_never_contains_question_text(tmp_path, analysis):
    text = write_markdown(analysis, tmp_path).read_text(encoding="utf-8")
    for forbidden in ("보기 ①", "다음 중 옳은 것", "정답:"):
        assert forbidden not in text


def test_html_report_falls_back_without_the_internet(tmp_path, analysis):
    html = write_html(analysis, tmp_path).read_text(encoding="utf-8")
    assert 'typeof Chart === "undefined"' in html
    assert "차트를 불러오지 못했습니다" in html
    assert "cdnjs.cloudflare.com" in html


def test_ai_label_is_added_only_when_claude_wrote_the_plan(tmp_path, analysis):
    from shared.ai_label import label_text_for

    with_plan = write_markdown(analysis, tmp_path, plan=["한 줄"]).read_text(encoding="utf-8")
    assert label_text_for("ko") in with_plan

    plain = write_markdown(analysis, tmp_path, plan=[]).read_text(encoding="utf-8")
    assert label_text_for("ko") not in plain, "사람이 만든 표에 AI 표시를 붙이면 사실과 다르다"


# ------------------------------------------------------------------ CLI
def test_cli_dry_run_makes_both_reports(tmp_path, capsys):
    cli = load_product_cli("exam-drill")
    code = cli.main(["report", "--demo", "--dry-run", "--out", str(tmp_path)])
    assert code == 2, "과락이 있으면 경고로 끝난다"
    out = capsys.readouterr().out
    assert "과락" in out
    assert len(list(tmp_path.glob("report_*.md"))) == 1
    assert len(list(tmp_path.glob("report_*.html"))) == 1


def test_cli_sheet_tells_you_not_to_write_the_question(tmp_path, capsys):
    cli = load_product_cli("exam-drill")
    code = cli.main(["sheet", "--round", "36회", "--subject", "civil",
                     "--out", str(tmp_path / "s.csv")])
    assert code == 0
    out = capsys.readouterr().out
    assert "문제 지문을 적는 칸은 없습니다" in out
    assert (tmp_path / "s.csv").is_file()


def test_cli_check_points_out_missing_reasons(tmp_path, capsys):
    path = tmp_path / "s.csv"
    path.write_text(
        "회차,과목,문항번호,정오,단원,이유,소요초\n"
        "35회,civil,1,X,,,60\n", encoding="utf-8-sig")
    cli = load_product_cli("exam-drill")
    assert cli.main(["check", "--input", str(path)]) == 0
    out = capsys.readouterr().out
    assert "이유를 안 적은" in out
    assert "단원을 안 적은" in out


def test_cli_subjects_lists_five_subjects(capsys):
    cli = load_product_cli("exam-drill")
    assert cli.main(["subjects"]) == 0
    out = capsys.readouterr().out
    assert "40점 이상" in out
    for subject in SUBJECTS:
        assert subject.name in out


def test_cli_without_a_command_explains_itself(capsys):
    cli = load_product_cli("exam-drill")
    assert cli.main([]) == 1
    assert "report --demo" in capsys.readouterr().err


# --------------------------------------------------------------- 등록
def test_registered_as_program_1():
    program = Registry().require("exam-drill")
    assert program.number == 1
    assert program.status == "ready"
    assert program.requirements.signup_free, "가입 없이 바로 써야 한다"


def test_it_lives_outside_and_says_so():
    """본체가 GitHub Pages 로 옮겨 갔다. 화면 설명이 그걸 알고 있어야 한다.

    옛 설명(집 컴퓨터에서 도는 파이썬 분석기)이 남아 있으면 산 분이
    엉뚱한 것을 설치하려 든다. 그래서 세 가지를 못 박아 둔다.
    """
    program = Registry().require("exam-drill")
    assert program.live.elsewhere, "밖에서 도는 프로그램으로 표시되어야 한다"
    assert program.requirements.home_pc == "no", "집 컴퓨터에서 돌릴 것이 없다"
    assert program.requirements.internet == "needed", "인터넷이 있어야 한다"


def test_manifest_warns_about_copyright():
    """문항 4,400개를 담고 판다. 저작권 확인은 사람이 해야 하는 일이다.

    옛 판은 문제를 아예 담지 않아 '어문저작물' 한 줄로 끝났다. 지금은
    담고 있으니, 넘기지 말고 **팔기 전에 확인하라**고 적혀 있어야 한다.
    """
    cautions = " ".join(Registry().require("exam-drill").requirements.cautions)
    assert "재배포 권리" in cautions
    assert "팔기 전에 확인" in cautions
    assert "약속하지 않습니다" in cautions


def test_subject_lookup_accepts_short_names():
    assert subject_of("민법").key == "civil"
    assert subject_of("civil").key == "civil"
    with pytest.raises(ValueError, match="모르는 과목"):
        subject_of("영어")


# ------------------------------------------------------ 매뉴얼이 프로그램을 따라오는가
#
# 본체가 GitHub Pages 로 옮겨 갔을 때 매뉴얼만 옛 파이썬 분석기 내용으로
# 남아 있었다. 사장님이 화면에서 보고 "매뉴얼은 전혀 변경이 안 되어 있다"고
# 짚으셨다. 번호만 바꾸고 내용을 안 봤던 것이다.
#
# 프로그램이 바뀌면 매뉴얼도 바뀌어야 한다. 사람이 기억하는 대신 여기서 막는다.

def _manual(audience: str) -> str:
    program = Registry().require("exam-drill")
    relative = getattr(program.manuals, audience)
    return program.resolve(relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("audience", ["admin", "client"])
def test_manuals_dropped_the_old_analyzer(audience):
    """옛 '기출 풀이 분석기' 이야기가 한 줄도 남으면 안 된다.

    남아 있으면 산 분이 없는 파이썬 프로그램을 설치하려 들고,
    "기출문제는 들어 있지 않습니다" 라는 이제 거짓인 문장을 읽는다.
    """
    글 = _manual(audience)
    for 옛것 in ("분석기", "cli.py", "기록표", "기출문제는 들어 있지 않습니다"):
        assert 옛것 not in 글, f"{audience} 매뉴얼에 옛 분석기 내용이 남았습니다: {옛것}"


@pytest.mark.parametrize("audience", ["admin", "client"])
def test_manuals_describe_what_the_program_actually_is(audience):
    """지금 프로그램의 뼈대가 두 매뉴얼에 다 들어 있어야 한다."""
    글 = _manual(audience)
    for 낱말 in ("4,400", "제15회", "제36회", "복습함", "모의", "통계", "2차키"):
        assert 낱말 in 글, f"{audience} 매뉴얼에 '{낱말}' 설명이 없습니다"


def test_client_manual_warns_that_scores_live_in_the_browser():
    """가장 많이 들어올 문의이자 환불 사유다. 미리 적혀 있어야 한다."""
    글 = _manual("client")
    assert "브라우저" in 글
    assert "사라집니다" in 글, "기록을 지우면 성적이 사라진다고 적어야 한다"


def test_admin_manual_puts_the_copyright_check_before_selling():
    """문항 4,400개를 담고 판다. 권리 확인을 넘기면 상품이 통째로 위험하다."""
    글 = _manual("admin")
    assert "재배포" in 글
    assert "한국산업인력공단" in 글, "어디에 물어볼지가 적혀 있어야 한다"
    assert "법률 자문이 아닙니다" in 글, "할 수 없는 말을 하지 않는다"


def test_admin_manual_states_the_mail_quota():
    """하루 몇 명까지 팔 수 있는지가 곧 사업 한도다."""
    글 = _manual("admin")
    assert "100통" in 글 and "1,500통" in 글


@pytest.mark.parametrize("audience", ["admin", "client"])
def test_manuals_promise_nothing_about_passing(audience):
    """자격증 상품에서 가장 위험한 문구다. 두 매뉴얼 모두에서 막는다."""
    글 = _manual(audience)
    assert "합격을 약속하지 않습니다" in 글
    for 위험 in ("합격 보장", "합격보장", "합격률 90", "반드시 합격"):
        assert 위험 not in 글, f"{audience} 매뉴얼에 위험한 문구: {위험}"


# --------------------------------------------- 화면도 프로그램을 따라오는가
#
# 매뉴얼 문서를 고친 뒤에도 사장님이 "클라이언트는 예전 그대로" 라고 하셨다.
# 문서가 아니라 **화면**(`webui.py` 의 콘솔)이 옛 분석기였다. 탭 이름이
# 「문항 채우기」·「빈 기록표」 였고, 손으로 할 일에 "이 프로그램에는 문제
# 지문을 넣는 칸이 없습니다" 가 그대로 있었다.
#
# 문서 셋(README·admin.md·client.md)과 화면이 따로 놀면, 고객은 서로 다른
# 안내를 두 번 받는다. 여기서 같이 묶는다.

def _console():
    from core.webui import load_console

    return load_console(Registry().require("exam-drill"), {})


def test_console_dropped_the_old_analyzer():
    """옛 분석기 화면이 한 조각도 남으면 안 된다."""
    화면 = _console()
    글 = " ".join([
        화면.admin_intro, 화면.client_intro,
        " ".join(t.label + " " + t.intro for t in 화면.tabs),
        " ".join(m.task + " " + m.why for m in 화면.manual_tasks),
        " ".join(t.symptom + " " + t.fix for t in 화면.troubles),
        " ".join(f.what for f in 화면.files),
    ])
    for 옛것 in ("문항 채우기", "빈 기록표", "기록 지우기", "약한 단원",
                 "지문을 넣는 칸", "records.csv", "syllabus.py"):
        assert 옛것 not in 글, f"콘솔 화면에 옛 분석기 내용이 남았습니다: {옛것}"


def test_console_is_about_selling_not_about_pretending_to_be_the_program():
    """본체가 밖에 있으니 화면은 **파는 일**만 다뤄야 한다.

    프로그램을 흉내 내면 사장님이 여기서 키를 발급하려 들고,
    고객에게 이 주소를 보낸다.
    """
    화면 = _console()
    라벨 = [t.label for t in 화면.tabs]
    for 필요 in ("여기서 시작", "팔기 전 확인", "키 보내는 법", "고객 안내", "문의 대응"):
        assert 필요 in 라벨, f"'{필요}' 탭이 없습니다 (지금: {라벨})"

    assert "밖에서 돕니다" in 화면.admin_intro
    assert "이 화면이 아닙니다" in 화면.client_intro, (
        "고객이 실제로 쓰는 곳은 밖이라고 못 박아야 한다"
    )


def test_console_carries_the_copyright_check_as_a_todo():
    """권리 확인은 '오늘 할 일' 에 떠 있어야 한다. 문서에만 있으면 안 읽는다."""
    화면 = _console()
    할일 = " ".join(t.text + " " + t.detail for t in 화면.todos)
    assert "권리" in 할일
    손 = " ".join(m.task + " " + m.where for m in 화면.manual_tasks)
    assert "한국산업인력공단" in 손


def test_console_numbers_match_the_manuals():
    """화면 타일과 매뉴얼이 다른 숫자를 말하면 안 된다."""
    화면 = _console()
    타일 = {s.label: s.value for s in 화면.stats}
    assert 타일["문항"] == "4,400"
    assert 타일["회차"] == "22"
    for audience in ("admin", "client"):
        assert "4,400" in _manual(audience)
