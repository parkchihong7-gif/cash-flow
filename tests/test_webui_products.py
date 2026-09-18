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


def test_a_product_without_a_screen_still_gets_the_default():
    ui = load_webui(Registry().require("funnel-builder"))
    assert not ui.custom
    assert ui.admin and ui.client
