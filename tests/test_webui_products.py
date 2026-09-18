"""2단계 — 13·15·14번 전용 웹 화면.

껍데기(1단계)는 `test_webapp.py` 가 본다. 여기서는 **그 상품에만 있는 일**이
화면에서 제대로 막히고 제대로 되는지를 본다.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from core import auth
from core.registry import Registry
from core.webui import load_handler, load_webui
from dashboard.app import create_app

ROOT = Path(__file__).resolve().parents[1]
EXAM = ROOT / "products" / "exam-drill"
NAVER = ROOT / "products" / "naver-blog"
SENIOR = ROOT / "products" / "senior-video"


@pytest.fixture
def client(tmp_path):
    client = TestClient(create_app(tmp_path / "app.db"))
    assert client.post("/login", data={"code": auth.access_code()}).status_code == 200
    return client


@pytest.fixture
def keep(tmp_path):
    """상품 폴더의 파일을 건드리는 테스트가 원본을 되돌리게 한다."""
    saved: list[tuple[Path, str]] = []

    def remember(path: Path):
        saved.append((path, path.read_text(encoding="utf-8") if path.is_file() else None))
    yield remember
    for path, before in saved:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(before, encoding="utf-8")


def _flash(response) -> str:
    from urllib.parse import unquote
    return unquote(response.headers.get("location", ""))


# ═══════════════════════════════════════════════ 13 공인중개사 기출
def test_exam_screen_leads_with_the_failing_subject():
    """과락이 맨 위에 와야 한다. 평균부터 보면 판단을 그르친다."""
    ui = load_webui(Registry().require("exam-drill"))
    assert ui.custom
    first = ui.admin[0]
    assert first.key == "state"
    assert first.notes, "지금 상태에 짚어 줄 것이 있어야 한다"
    assert any("과락" in note.title for note in first.notes)
    assert first.notes[0].tone == "bad"


def test_exam_screen_has_no_place_for_question_text():
    """화면에도 지문을 적는 칸을 만들지 않는다 (README §2)."""
    ui = load_webui(Registry().require("exam-drill"))
    for panel in ui.admin + ui.client:
        for field in panel.fields:
            for forbidden in ("지문", "보기", "정답", "본문", "해설"):
                assert forbidden not in field.label, f"{field.key} 에 {forbidden} 칸이 생겼습니다"


def test_exam_entry_rejects_a_shifted_row(client, keep):
    """'맞음' 인데 이유가 있으면 줄이 밀린 것이다."""
    keep(EXAM / "data" / "records.csv")
    response = client.post(
        "/apps/exam-drill/admin/do/add",
        data={"round_name": "36회", "subject": "civil — 민법 및 민사특별법",
              "number": "3", "correct": "맞음", "reason": "실수"},
        follow_redirects=False)
    assert "줄이 밀리지" in _flash(response)


def test_exam_entry_requires_a_reason_when_wrong(client, keep):
    """이유가 없으면 처방을 못 준다. 그게 이 상품의 핵심이다."""
    keep(EXAM / "data" / "records.csv")
    response = client.post(
        "/apps/exam-drill/admin/do/add",
        data={"round_name": "36회", "subject": "public — 부동산공법",
              "number": "3", "correct": "틀림", "reason": ""},
        follow_redirects=False)
    assert "이유를 골라" in _flash(response)


def test_exam_entry_appends_one_row(client, keep):
    path = EXAM / "data" / "records.csv"
    keep(path)
    before = len(path.read_text(encoding="utf-8-sig").splitlines())
    response = client.post(
        "/apps/exam-drill/admin/do/add",
        data={"round_name": "36회", "subject": "public — 부동산공법",
              "number": "7", "correct": "틀림", "reason": "몰라서",
              "unit": "개발행위허가", "seconds": "95"},
        follow_redirects=False)
    assert "36회 7번" in _flash(response)
    after = path.read_text(encoding="utf-8-sig").splitlines()
    assert len(after) == before + 1
    assert after[-1].startswith("36회,public,7,X,개발행위허가,몰라서,95")


def test_exam_entry_refuses_a_bad_question_number(client, keep):
    keep(EXAM / "data" / "records.csv")
    response = client.post(
        "/apps/exam-drill/admin/do/add",
        data={"round_name": "36회", "subject": "civil — 민법 및 민사특별법",
              "number": "99", "correct": "맞음"},
        follow_redirects=False)
    assert "1~40" in _flash(response)


def test_exam_clear_needs_the_exact_word(client, keep):
    """되돌릴 수 없는 일은 정확히 적게 한다."""
    keep(EXAM / "data" / "records.csv")
    response = client.post("/apps/exam-drill/admin/do/clear",
                           data={"confirm": "네"}, follow_redirects=False)
    assert "'비움' 이라고 정확히" in _flash(response)


def test_exam_client_screen_hides_destructive_tools():
    ui = load_webui(Registry().require("exam-drill"))
    keys = [panel.key for panel in ui.client]
    assert "clear" not in keys, "고객 화면에 기록표 비우기가 있으면 안 된다"
    assert "sheet" not in keys
    assert "state" in keys and "entry" in keys


# ═══════════════════════════════════════════════ 15 네이버 블로그
def test_naver_screen_explains_why_there_is_no_publish_button():
    """없는 걸 이상하게 여기지 않게 하는 것도 화면의 일이다."""
    ui = load_webui(Registry().require("naver-blog"))
    panel = next(item for item in ui.admin if item.key == "policy")
    titles = " ".join(note.title + note.body for note in panel.notes)
    assert "글쓰기 API" in titles
    assert "비밀번호" in titles or "브라우저" in titles


def test_naver_screen_has_no_publish_action():
    ui = load_webui(Registry().require("naver-blog"))
    for panel in ui.admin + ui.client:
        assert "게시" not in panel.action_label or not panel.action
        assert panel.custom_action not in ("publish", "post")


def test_naver_paid_post_needs_a_sponsor_name(client, keep):
    """이름이 없으면 문구에 OO 가 그대로 남는다. 그건 표시한 게 아니다."""
    keep(NAVER / "request.yaml")
    response = client.post(
        "/apps/naver-blog/admin/do/request",
        data={"topic": "전세 계약", "sponsor_kind": "원고료를 받음",
              "sponsor_name": ""}, follow_redirects=False)
    assert "광고주 이름을 적어" in _flash(response)


def test_naver_saving_a_paid_post_shows_the_phrase(client, keep):
    keep(NAVER / "request.yaml")
    response = client.post(
        "/apps/naver-blog/admin/do/request",
        data={"topic": "전세 계약", "sponsor_kind": "원고료를 받음",
              "sponsor_name": "OO상사"}, follow_redirects=False)
    flash = _flash(response)
    assert "원고료" in flash
    saved = yaml.safe_load((NAVER / "request.yaml").read_text(encoding="utf-8"))
    assert saved["sponsor_kind"] == "sponsored"
    assert saved["sponsor_name"] == "OO상사"


def test_naver_topic_is_required(client, keep):
    keep(NAVER / "request.yaml")
    response = client.post("/apps/naver-blog/admin/do/request",
                           data={"topic": "  "}, follow_redirects=False)
    assert "무엇에 대해 쓰실지" in _flash(response)


def test_naver_review_blocks_while_placeholders_remain():
    """빈칸이 남아 있으면 '올리시면 안 됩니다' 가 떠야 한다."""
    ui = load_webui(Registry().require("naver-blog"))
    state = next(item for item in ui.admin if item.key == "state")
    assert any("올리시면 안 됩니다" in note.title for note in state.notes)


def test_naver_demand_works_without_a_key():
    """키가 없어도 샘플 자료로 흐름을 볼 수 있어야 한다."""
    ui = load_webui(Registry().require("naver-blog"))
    panel = next(item for item in ui.admin if item.key == "demand")
    assert panel.table and panel.table.rows
    assert "샘플 자료" in panel.table.note


def test_naver_client_screen_hides_the_tone_field():
    ui = load_webui(Registry().require("naver-blog"))
    panel = next(item for item in ui.client if item.key == "request")
    assert "tone" not in [field.key for field in panel.fields]
    assert "sponsor_kind" in [field.key for field in panel.fields], \
        "대가 유형은 고객도 골라야 한다"


# ═══════════════════════════════════════════════ 14 시니어 영상
def test_senior_estimate_names_the_biggest_line():
    """총액만 보면 어디를 손댈지 모른다."""
    ui = load_webui(Registry().require("senior-video"))
    panel = next(item for item in ui.admin if item.key == "estimate")
    assert any("가장 큰 줄" in note.title for note in panel.notes)
    assert panel.table and panel.table.rows


def test_senior_savings_always_state_the_cost():
    ui = load_webui(Registry().require("senior-video"))
    panel = next(item for item in ui.admin if item.key == "savings")
    if panel.table and panel.table.rows:
        for row in panel.table.rows:
            assert row[-1].strip(), "대가가 비어 있는 절감안이 있습니다"


def test_senior_quota_warns_over_the_ceiling(client, keep):
    keep(SENIOR / "plan.yaml")
    response = client.post("/apps/senior-video/admin/do/plan",
                           data={"monthly_videos": "300"}, follow_redirects=False)
    assert "쿼터를 넘습니다" in _flash(response)


def test_senior_plan_saves_and_recalculates(client, keep):
    path = SENIOR / "plan.yaml"
    keep(path)
    client.post("/apps/senior-video/admin/do/plan",
                data={"monthly_videos": "40", "script_chars": "2000"},
                follow_redirects=False)
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["monthly_videos"] == 40
    assert saved["script_chars"] == 2000


def test_senior_plan_refuses_a_non_number(client, keep):
    keep(SENIOR / "plan.yaml")
    response = client.post("/apps/senior-video/admin/do/plan",
                           data={"monthly_videos": "스무 편"}, follow_redirects=False)
    assert "숫자로 적어" in _flash(response)


def test_senior_approval_without_a_name_is_refused_server_side(client, tmp_path):
    """브라우저가 막기 전에 서버도 막아야 한다. 주소를 직접 치는 길이 있다."""
    response = client.post("/apps/senior-video/admin/do/approve",
                           data={"item_id": "1 — 제목", "by": "  "},
                           follow_redirects=False)
    flash = _flash(response)
    assert "이름을 적어" in flash
    assert "자동 승인과 다르지 않습니다" in flash


def test_senior_client_screen_has_no_queue_or_approval():
    """승인은 파는 사람이 한다. 고객 화면에 있으면 검수가 무너진다."""
    ui = load_webui(Registry().require("senior-video"))
    keys = [panel.key for panel in ui.client]
    assert "queue" not in keys
    assert "approve" not in keys


def test_senior_spec_panel_explains_why():
    """"자막을 크게" 는 누구나 한다. 이유까지 말해야 한다."""
    ui = load_webui(Registry().require("senior-video"))
    panel = next(item for item in ui.admin if item.key == "spec")
    assert panel.table and panel.table.rows
    bodies = " ".join(note.body for note in panel.notes)
    assert bodies.strip(), "권장값을 벗어난 항목은 왜 그런지가 붙어야 한다"


# ═══════════════════════════════════════════════ 공통
@pytest.mark.parametrize("program_id", ["exam-drill", "naver-blog", "senior-video"])
def test_each_has_a_handler(program_id):
    assert load_handler(Registry().require(program_id)) is not None


@pytest.mark.parametrize("program_id", ["exam-drill", "naver-blog", "senior-video"])
def test_unknown_action_is_refused(client, program_id):
    response = client.post(f"/apps/{program_id}/admin/do/없는동작",
                           data={}, follow_redirects=False)
    assert "모르는 동작" in _flash(response)


@pytest.mark.parametrize("program_id", ["exam-drill", "naver-blog", "senior-video"])
@pytest.mark.parametrize("mode", ["admin", "client"])
def test_dedicated_screens_still_render(client, program_id, mode):
    response = client.get(f"/apps/{program_id}/{mode}")
    assert response.status_code == 200
    assert "data-back" in response.text


def test_a_product_without_a_screen_still_gets_the_default(tmp_path):
    """새 상품을 만들면 webui.py 없이도 화면이 떠야 한다."""
    program = Registry().require("funnel-builder").model_copy()
    program.directory = tmp_path          # webui.py 가 없는 폴더
    ui = load_webui(program)
    assert not ui.custom
    assert ui.admin and ui.client


# ═══════════════════════════════════════════════ 3단계 — 나머지 13종
ALL_IDS = [program.id for program in Registry().programs]


@pytest.mark.parametrize("program_id", ALL_IDS)
def test_every_program_now_has_its_own_screen(program_id):
    """16종 전부 전용 화면을 가진다. 기본 화면으로 떨어지면 안 된다."""
    ui = load_webui(Registry().require(program_id))
    assert ui.custom, f"{program_id} 가 아직 기본 화면입니다"


@pytest.mark.parametrize("program_id", ALL_IDS)
def test_no_screen_falls_back_to_broken(program_id):
    """상품 화면이 깨지면 'broken' 패널이 뜬다. 하나도 없어야 한다."""
    ui = load_webui(Registry().require(program_id), {"settings": {}})
    broken = [panel for panel in ui.admin if panel.key == "broken"]
    assert not broken, f"{program_id}: {broken[0].note if broken else ''}"


@pytest.mark.parametrize("program_id", ALL_IDS)
def test_client_screen_is_never_empty(program_id):
    ui = load_webui(Registry().require(program_id), {"settings": {}})
    assert ui.client, f"{program_id} 의 고객 화면이 비어 있습니다"
    assert ui.client_intro.strip()


@pytest.mark.parametrize("program_id", ALL_IDS)
def test_real_run_never_appears_on_a_client_screen(program_id):
    """고객이 실수로 API 비용을 쓰는 일을 만들지 않는다."""
    ui = load_webui(Registry().require(program_id), {"settings": {}})
    for panel in ui.client:
        assert panel.run_mode != "real", f"{program_id}/{panel.key}"


# ── 16 해외 연사
def test_speaker_screen_shouts_about_visa_waiver_plus_fee():
    """무비자 + 강연료는 실무에서 가장 많이 틀리는 조합이다."""
    ui = load_webui(Registry().require("speaker-desk"))
    risk = next(panel for panel in ui.admin if panel.key == "risk")
    bad = [note for note in risk.notes if note.tone == "bad"]
    assert bad, "위험 조합이 빨갛게 떠야 한다"
    assert any("무비자" in note.body or "사증면제" in note.body for note in bad)


def test_speaker_tax_table_compares_gross_and_net():
    """500만 원 계약이 641만 원이 되는 것을 계약 전에 봐야 한다."""
    ui = load_webui(Registry().require("speaker-desk"))
    tax = next(panel for panel in ui.admin if panel.key == "tax")
    assert tax.table and tax.table.rows
    assert "세전으로 적으면" in tax.table.headers
    assert "세후로 적으면" in tax.table.headers


def test_speaker_tax_calculator_shows_both_sides(client):
    response = client.post("/apps/speaker-desk/admin/do/tax",
                           data={"amount": "5000000"}, follow_redirects=False)
    flash = _flash(response)
    assert "6,410,256" in flash
    assert "1,410,256" in flash


def test_speaker_calculator_refuses_a_bad_treaty_rate(client):
    response = client.post("/apps/speaker-desk/admin/do/tax",
                           data={"amount": "5000000", "treaty": "22"},
                           follow_redirects=False)
    assert "0 이상 1 미만" in _flash(response)


def test_speaker_add_validates_before_writing(client, keep):
    """잘못된 줄이 명부에 들어가면 화면 전체가 안 뜬다."""
    keep(Path(ROOT / "products" / "speaker-desk" / "event.yaml"))
    response = client.post(
        "/apps/speaker-desk/admin/do/add_speaker",
        data={"name": "Test Person", "country": "Japan",
              "fee_krw": "1000000", "expenses_only": "1"},
        follow_redirects=False)
    assert "둘 다일 수 없습니다" in _flash(response)


def test_speaker_add_warns_on_the_dangerous_combination(client, keep):
    keep(Path(ROOT / "products" / "speaker-desk" / "event.yaml"))
    response = client.post(
        "/apps/speaker-desk/admin/do/add_speaker",
        data={"name": "Risky Guest", "country": "United States",
              "fee_krw": "3000000", "visa_waiver": "1",
              "arrival": "2026-11-18", "departure": "2026-11-20"},
        follow_redirects=False)
    assert "무비자로 강연할 수 없습니다" in _flash(response)


def test_speaker_duplicate_name_is_refused(client, keep):
    keep(Path(ROOT / "products" / "speaker-desk" / "event.yaml"))
    response = client.post(
        "/apps/speaker-desk/admin/do/add_speaker",
        data={"name": "Jane Doe", "country": "United States"},
        follow_redirects=False)
    assert "이미 명부에 있는" in _flash(response)


# ── 12 니치 리서치
def test_niche_screen_flags_missing_days():
    """거른 날은 영영 빈다. 화면이 알려 줘야 한다."""
    ui = load_webui(Registry().require("niche-research"))
    state = next(panel for panel in ui.admin if panel.key == "state")
    assert state.notes


def test_niche_quota_panel_counts_units():
    ui = load_webui(Registry().require("niche-research"))
    quota = next(panel for panel in ui.admin if panel.key == "quota")
    assert any("유닛" in note.title for note in quota.notes)


def test_niche_warns_when_over_the_daily_keyword_cap(client, keep):
    keep(Path(ROOT / "products" / "niche-research" / "keywords.txt"))
    words = "\n".join(f"키워드{index}" for index in range(90))
    response = client.post("/apps/niche-research/admin/do/keywords",
                           data={"words": words}, follow_redirects=False)
    assert "다음 날로 넘어갑니다" in _flash(response)


def test_niche_screen_never_lists_videos_or_channels():
    """노아AI 전례. 화면에도 영상 제목·채널명을 싣지 않는다."""
    ui = load_webui(Registry().require("niche-research"))
    gap = next(panel for panel in ui.admin if panel.key == "gap")
    if gap.table:
        for header in gap.table.headers:
            assert "제목" not in header and "채널명" not in header


# ── 10 제휴 매칭
def test_affiliate_screen_leads_with_the_disclosure():
    ui = load_webui(Registry().require("affiliate-matcher"))
    assert ui.admin[0].key == "disclosure"
    joined = " ".join(note.title + note.body for note in ui.admin[0].notes)
    assert "쿠팡 파트너스" in joined
    assert "자격이 정지" in joined


def test_affiliate_refuses_a_too_short_body(client, keep):
    keep(Path(ROOT / "products" / "affiliate-matcher" / "data" / "input.txt"))
    response = client.post("/apps/affiliate-matcher/admin/do/save",
                           data={"text": "짧은 글"}, follow_redirects=False)
    assert "100자 이상" in _flash(response)


def test_affiliate_rate_table_carries_sources():
    ui = load_webui(Registry().require("affiliate-matcher"))
    rates = next(panel for panel in ui.admin if panel.key == "rates")
    assert rates.table and rates.table.rows
    assert "출처" in rates.table.headers


# ── 11 대행 키트
def test_agency_screen_leads_with_pending_reviews():
    """코드가 다 돼도 심사가 안 나면 못 판다."""
    ui = load_webui(Registry().require("agency-kit"))
    assert ui.admin[0].key == "review"
    joined = " ".join(note.title for note in ui.admin[0].notes)
    assert "오픈빌더" in joined and "인스타" in joined


def test_agency_package_needs_a_client_name(client):
    response = client.post("/apps/agency-kit/admin/do/package",
                           data={"plan": "basic", "client": ""},
                           follow_redirects=False)
    assert "고객 상호를 적어" in _flash(response)


def test_agency_client_screen_lists_what_was_left_out():
    ui = load_webui(Registry().require("agency-kit"))
    never = next(panel for panel in ui.client if panel.key == "never")
    joined = " ".join(never.lines)
    assert "콜드 DM" in joined
    assert "사람이 승인한 것만" in joined


# ── 8 수익 시뮬레이터
def test_income_sim_shows_a_projection():
    ui = load_webui(Registry().require("income-sim"), {"settings": {}})
    result = next(panel for panel in ui.admin if panel.key == "result")
    assert result.table and len(result.table.rows) == 12
    assert any("추정치" in note.title for note in result.notes)


def test_income_sim_rejects_a_non_number(client):
    response = client.post("/apps/income-sim/admin/do/calc",
                           data={"new_deals_per_month": "두 건"},
                           follow_redirects=False)
    assert "숫자로 적어" in _flash(response)


# ── 7 공구 정산
def test_groupbuy_screen_checks_the_inputs_first():
    """계산이 아니라 원본이 성한지부터 본다."""
    ui = load_webui(Registry().require("groupbuy-ledger"))
    assert ui.admin[0].key == "check"
    joined = " ".join(note.title + note.body for note in ui.admin[0].notes)
    assert "개인정보" in joined or "참여자 이름" in joined


# ── 6 n8n
def test_n8n_screen_shows_the_four_tips():
    ui = load_webui(Registry().require("n8n-gen"))
    tips = next(panel for panel in ui.admin if panel.key == "tips")
    assert len(tips.lines) == 4
    assert any("credential" in note.title for note in tips.notes)


def test_n8n_refuses_an_empty_request(client, keep):
    keep(Path(ROOT / "products" / "n8n-gen" / "request.txt"))
    response = client.post("/apps/n8n-gen/admin/do/save",
                           data={"requests": "   \n  "}, follow_redirects=False)
    assert "한 줄에 하나씩" in _flash(response)


# ── 생성기 일곱 종 공통
GENERATORS = ["funnel-builder", "hook-script", "ebook-gen", "lecture-deck",
              "kmong-copy", "notion-template-kit"]


@pytest.mark.parametrize("program_id", GENERATORS)
def test_generator_screens_share_one_shape(program_id):
    """한 곳을 고치면 일곱 종이 같이 바뀌어야 한다."""
    ui = load_webui(Registry().require(program_id))
    assert [panel.key for panel in ui.admin] == ["input", "run", "run_real", "outputs"]
    assert [panel.key for panel in ui.client] == ["input", "run", "outputs"]


@pytest.mark.parametrize("program_id", GENERATORS)
def test_generator_input_requires_its_key_field(client, keep, program_id):
    program = Registry().require(program_id)
    keep(program.resolve(program.run.input_file))
    response = client.post(f"/apps/{program_id}/admin/do/save",
                           data={}, follow_redirects=False)
    assert "적어 주세요" in _flash(response)


def test_generator_save_writes_the_input_file(client, keep):
    program = Registry().require("ebook-gen")
    path = program.resolve(program.run.input_file)
    keep(path)
    client.post("/apps/ebook-gen/admin/do/save",
                data={"topic": "테스트 주제", "pages": "30"}, follow_redirects=False)
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["topic"] == "테스트 주제"
    assert saved["pages"] == 30
