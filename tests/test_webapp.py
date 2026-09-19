"""상품별 웹 화면 테스트 — [관리자 모드] / [클라이언트 모드].

가장 중요한 검사는 **두 모드가 정말로 다른가**다. 화면만 다르고 뒤가 같으면
고객이 건드리면 안 되는 값을 건드리게 된다. 그래서 주소를 직접 쳐서 들어오는
길까지 막혔는지 본다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core import auth
from core.db import Database
from core.registry import Registry
from core.webui import (
    MODES, MODE_LABEL, Panel, WebUI, default_webui, load_webui,
)
from dashboard.app import create_app

ALL_IDS = [program.id for program in Registry().programs]


@pytest.fixture
def client(tmp_path):
    client = TestClient(create_app(tmp_path / "app.db"))
    assert client.post("/login", data={"code": auth.access_code()}).status_code == 200
    return client


# ------------------------------------------------ 16종 × 두 모드가 전부 뜬다
@pytest.mark.parametrize("program_id", ALL_IDS)
@pytest.mark.parametrize("mode", MODES)
def test_every_program_has_both_screens(client, program_id, mode):
    response = client.get(f"/apps/{program_id}/{mode}")
    assert response.status_code == 200, f"{program_id}/{mode}"
    assert MODE_LABEL[mode] in response.text


def test_unknown_mode_is_refused(client):
    assert client.get("/apps/exam-drill/superuser").status_code == 404


def test_unknown_program_is_refused(client):
    assert client.get("/apps/없는상품/admin").status_code == 404


# ------------------------------------------------------ 뒤로가기는 항상 있다
@pytest.mark.parametrize("program_id", ["exam-drill", "naver-blog", "speaker-desk"])
@pytest.mark.parametrize("mode", MODES)
def test_back_link_is_always_present(client, program_id, mode):
    """깊이 들어갔다가 길을 잃는 것이 가장 흔한 불만이다."""
    body = client.get(f"/apps/{program_id}/{mode}").text
    assert "data-back" in body, "뒤로가기 버튼이 없습니다"
    assert f'href="/programs/{program_id}"' in body, "통합 대시보드로 가는 길이 없습니다"
    assert "통합 대시보드로 돌아가기" in body, "바닥에도 돌아가는 길이 있어야 한다"


def test_program_detail_page_has_back_and_both_mode_links(client):
    body = client.get("/programs/exam-drill").text
    assert "data-back" in body
    assert 'href="/apps/exam-drill/admin"' in body
    assert 'href="/apps/exam-drill/client"' in body
    assert 'target="_blank"' in body, "새 창에서 열려야 한다"


@pytest.mark.parametrize("suffix", ["", "/edit", "/test", "/members", "/manual/admin"])
def test_every_detail_tab_carries_the_back_button(client, suffix):
    body = client.get(f"/programs/exam-drill{suffix}").text
    assert "data-back" in body, f"{suffix} 에 뒤로가기가 없습니다"


def test_each_mode_links_to_the_other(client):
    admin = client.get("/apps/exam-drill/admin").text
    assert "/apps/exam-drill/client" in admin
    client_body = client.get("/apps/exam-drill/client").text
    assert "/apps/exam-drill/admin" in client_body


# ---------------------------------------------- 두 모드가 실제로 다르다
def test_client_mode_hides_admin_tools(client):
    """편집할 파일·실행 이력·실제 실행은 관리자만 본다."""
    body = client.get("/apps/exam-drill/client").text
    assert "편집할 파일" not in body
    assert "최근 실행" not in body
    assert "실제로 돌리기" not in body
    assert "테스트용 화면입니다" not in body


def test_admin_mode_shows_them(client):
    """관리자 화면에는 파일 편집과 **실제 실행**이 있다.

    패널 제목은 상품마다 다르므로(돌리기/만들기) 제목이 아니라
    실제 실행 폼이 있는지로 본다. 콘솔로 바꾸면서 자리가 갈렸다 —
    실행은 '만들기' 탭에, 파일 편집은 '파일 위치' 탭에 있다.
    """
    make = client.get("/apps/funnel-builder/admin/t/make").text
    assert 'value="real"' in make, "실제 실행 폼이 없습니다"

    files = client.get("/apps/funnel-builder/admin/t/files").text
    assert "결과를 좌우하는 파일" in files
    assert "/apps/funnel-builder/admin/file?path=" in files


def test_client_mode_never_exposes_key_settings(client):
    """모델·키 같은 값은 고객 화면에 그리지 않는다."""
    for program_id in ("funnel-builder", "naver-blog"):
        body = client.get(f"/apps/{program_id}/client").text
        assert "CLAUDE_MODEL" not in body, program_id
        assert "초안을 쓸 모델" not in body, program_id


def test_client_mode_refuses_a_real_run_even_by_url(client):
    """화면에서 숨기는 것만으로는 부족하다. 주소를 직접 쳐도 막혀야 한다."""
    response = client.post("/apps/exam-drill/client/run",
                           data={"run_mode": "real"}, follow_redirects=False)
    assert response.status_code == 303
    from urllib.parse import unquote
    assert "실제 실행을 하지 않습니다" in unquote(response.headers["location"])
    assert Database(client.app.state.db.path).list_runs("exam-drill") == []


def test_client_mode_cannot_save_an_admin_only_setting(client):
    """고객 화면에서 안 보이는 값은 넘어와도 버린다."""
    client.post("/apps/funnel-builder/client/settings",
                data={"CLAUDE_MODEL": "claude-opus-5"},
                follow_redirects=False)
    stored = client.app.state.db.get_program_settings("funnel-builder")
    assert "CLAUDE_MODEL" not in stored, "고객이 모델을 바꿀 수 있으면 안 된다"


def test_a_custom_client_screen_without_settings_saves_nothing(client):
    """전용 화면에 설정 패널이 없으면 아무것도 저장되지 않아야 한다.

    닫히는 쪽으로 틀리는 것이 맞다. 패널을 안 그렸는데 값이 저장되면
    화면에 없는 값이 조용히 바뀐다.
    """
    client.post("/apps/exam-drill/client/settings",
                data={"MIN_SAMPLE": "9"}, follow_redirects=False)
    assert client.app.state.db.get_program_settings("exam-drill") == {}


def test_admin_can_save_any_declared_setting(client):
    client.post("/apps/naver-blog/admin/settings",
                data={"CLAUDE_MODEL": "claude-opus-5", "없는키": "x"},
                follow_redirects=False)
    stored = client.app.state.db.get_program_settings("naver-blog")
    assert stored.get("CLAUDE_MODEL") == "claude-opus-5"
    assert "없는키" not in stored, "매니페스트에 없는 값은 저장하지 않는다"


# ---------------------------------------------------------------- 실행
def test_dry_run_from_the_admin_screen_records_a_run(client):
    response = client.post("/apps/exam-drill/admin/run",
                           data={"run_mode": "dry"}, follow_redirects=False)
    assert response.status_code == 303
    assert "run=" in response.headers["location"]
    runs = client.app.state.db.list_runs("exam-drill")
    assert len(runs) == 1
    assert runs[0]["mode"] == "dry"


def test_client_dry_run_works(client):
    response = client.post("/apps/naver-blog/client/run",
                           data={"run_mode": "dry"}, follow_redirects=False)
    assert response.status_code == 303
    assert "error=" not in response.headers["location"]
    assert client.app.state.db.list_runs("naver-blog")


def test_run_result_is_shown_on_the_screen(client):
    client.post("/apps/exam-drill/admin/run", data={"run_mode": "dry"})
    run_id = client.app.state.db.list_runs("exam-drill")[0]["id"]
    body = client.get(f"/apps/exam-drill/admin?run={run_id}").text
    assert "종료 코드" in body
    assert "과락" in body, "실행 로그가 화면에 보여야 한다"


# ------------------------------------------------------------ 파일 편집
def test_admin_can_edit_and_save_a_file(client, tmp_path):
    program = Registry().require("exam-drill")
    target = program.resolve("README.md")
    before = target.read_text(encoding="utf-8")
    try:
        response = client.get("/apps/exam-drill/admin/file?path=README.md")
        assert response.status_code == 200
        assert "13. 공인중개사" in response.text

        client.post("/apps/exam-drill/admin/file?path=README.md",
                    data={"path": "README.md", "content": before + "\n<!-- 테스트 -->\n"},
                    follow_redirects=False)
        assert "테스트" in target.read_text(encoding="utf-8")
    finally:
        target.write_text(before, encoding="utf-8")


def test_file_editing_cannot_escape_the_program_folder(client):
    """경로 탈출은 매니페스트의 resolve() 가 막는다. 화면에서도 확인한다."""
    from urllib.parse import unquote

    response = client.get("/apps/exam-drill/admin/file?path=../../.env",
                          follow_redirects=False)
    assert response.status_code == 303
    assert "폴더 밖" in unquote(response.headers["location"])


def test_client_mode_has_no_file_editor(client):
    assert client.get("/apps/exam-drill/client/file?path=README.md").status_code == 404


# ------------------------------------------------------- 화면 정의 규격
def test_default_webui_covers_every_program():
    """상품이 전용 화면을 안 만들었어도 기본 화면이 나와야 한다."""
    for program in Registry().programs:
        ui = default_webui(program)
        assert ui.admin, f"{program.id}: 관리자 패널이 없습니다"
        assert ui.client, f"{program.id}: 클라이언트 패널이 없습니다"


def test_editable_files_panel_is_not_duplicated():
    """껍데기가 이미 그리므로 기본 화면에서는 만들지 않는다."""
    ui = default_webui(Registry().require("exam-drill"))
    assert "files" not in [panel.key for panel in ui.admin]


def test_a_broken_product_screen_falls_back(tmp_path):
    """상품 하나가 깨져도 나머지 화면은 떠야 한다."""
    program = Registry().require("exam-drill").model_copy()
    (tmp_path / "webui.py").write_text(
        "def build(program, ctx):\n    raise RuntimeError('일부러 낸 오류')\n",
        encoding="utf-8")
    program.directory = tmp_path
    ui = load_webui(program)
    assert ui.admin[0].key == "broken"
    assert "일부러 낸 오류" in ui.admin[0].note


def test_custom_screen_is_marked():
    """2·3차에서 전용 화면을 얹었는지 화면이 알아야 한다."""
    ui = WebUI(program_id="x", title="x", admin=[Panel(key="a", title="A")])
    assert not ui.custom
    assert ui.panels("admin")[0].key == "a"
    assert ui.panels("client") == []
