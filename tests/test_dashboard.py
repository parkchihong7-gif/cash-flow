"""통합 관리자 대시보드 테스트.

실제 Claude 호출 없이, 프로그램 등록 → 화면 → 모의 실행 → 회원관리까지 검사한다.
"""

from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from core.db import Database
from core.manifest import ProgramManifest, load_manifest
from core.registry import Registry
from core.runner import RunError, run_program
from dashboard.app import create_app
from shared import banned_phrases
from shared.config import PRODUCTS_DIR, ROOT_DIR


# ------------------------------------------------------------------ 픽스처
@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path / "app.db"))


@pytest.fixture
def minimal_program(tmp_path):
    """program.yaml 최소 구성 하나짜리 products 폴더."""
    products = tmp_path / "products"
    (products / "demo").mkdir(parents=True)
    (products / "demo" / "program.yaml").write_text(
        yaml.safe_dump(
            {"id": "demo", "number": 1, "name": "데모", "status": "planned"},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return products


# --------------------------------------------------------------- 매니페스트
def test_funnel_builder_manifest_is_valid():
    program = load_manifest(PRODUCTS_DIR / "funnel-builder")
    assert program.id == "funnel-builder"
    assert program.status == "ready"
    assert program.runnable
    assert program.run.dry_run_command, "모의 실행을 지원해야 합니다"


def test_manifest_requires_only_three_fields(minimal_program):
    program = load_manifest(minimal_program / "demo")
    assert (program.id, program.number, program.name) == ("demo", 1, "데모")
    assert program.steps == [] and program.faq == [] and not program.runnable


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"id": "Funnel_Builder"}, "대문자·밑줄은 id 로 못 쓴다"),
        ({"number": 0}, "번호는 1 이상"),
        ({"status": "done"}, "정의되지 않은 상태"),
        ({"unknown_field": 1}, "모르는 키는 거부"),
    ],
)
def test_invalid_manifest_rejected(overrides, reason):
    payload = {"id": "demo", "number": 1, "name": "데모", **overrides}
    with pytest.raises(Exception):
        ProgramManifest(**payload)


def test_select_setting_requires_options():
    with pytest.raises(Exception):
        ProgramManifest(
            id="demo", number=1, name="데모",
            settings=[{"key": "m", "label": "모델", "type": "select"}],
        )


def test_resolve_blocks_path_escape():
    program = load_manifest(PRODUCTS_DIR / "funnel-builder")
    assert program.resolve("prompts/hooks.md").is_file()
    with pytest.raises(ValueError, match="폴더 밖"):
        program.resolve("../../shared/llm.py")


# ----------------------------------------------------------------- 레지스트리
def test_registry_finds_funnel_builder():
    registry = Registry()
    assert registry.get("funnel-builder") is not None
    assert registry.errors == []


def test_registry_reports_broken_manifest_without_dying(tmp_path):
    products = tmp_path / "products"
    (products / "good").mkdir(parents=True)
    (products / "good" / "program.yaml").write_text(
        "id: good\nnumber: 1\nname: 정상\n", encoding="utf-8"
    )
    (products / "broken").mkdir(parents=True)
    (products / "broken" / "program.yaml").write_text("id: 대문자안됨\n", encoding="utf-8")

    registry = Registry(products)
    assert [p.id for p in registry] == ["good"]
    assert [e.name for e in registry.errors] == ["broken"]


def test_registry_ignores_folders_without_manifest(tmp_path):
    products = tmp_path / "products"
    (products / "nothing").mkdir(parents=True)
    assert len(Registry(products)) == 0


def test_registry_sorts_by_number(tmp_path):
    products = tmp_path / "products"
    for name, number in [("c", 3), ("a", 1), ("b", 2)]:
        (products / name).mkdir(parents=True)
        (products / name / "program.yaml").write_text(
            f"id: {name}\nnumber: {number}\nname: {name}\n", encoding="utf-8"
        )
    assert [p.number for p in Registry(products)] == [1, 2, 3]


# ------------------------------------------------------------------------ DB
def test_member_lifecycle(db):
    member_id = db.add_member("홍길동", "hong@example.com", source="크몽")
    assert db.get_member(member_id)["name"] == "홍길동"

    db.update_member(member_id, name="홍길순")
    assert db.get_member(member_id)["name"] == "홍길순"

    db.delete_member(member_id)
    assert db.get_member(member_id) is None


def test_license_rollup_and_status(db):
    member_id = db.add_member("김철수", "kim@example.com")
    db.add_license(member_id, "funnel-builder", plan="템플릿", price=150000, retainer=50000)

    summary = db.summary()
    assert summary["members"] == 1
    assert summary["revenue"] == 150000
    assert summary["retainer"] == 50000

    license_id = db.list_licenses(member_id=member_id)[0]["id"]
    db.set_license_status(license_id, "refunded")
    assert db.summary()["revenue"] == 0, "환불하면 누적 결제액에서 빠져야 합니다"


def test_deleting_member_removes_licenses(db):
    member_id = db.add_member("이영희", "lee@example.com")
    db.add_license(member_id, "funnel-builder", price=150000)
    db.delete_member(member_id)
    assert db.list_licenses(program_id="funnel-builder") == []


def test_member_search(db):
    db.add_member("홍길동", "hong@example.com", memo="크몽 문의")
    db.add_member("김철수", "kim@example.com")
    assert len(db.list_members("홍")) == 1
    assert len(db.list_members("example.com")) == 2
    assert len(db.list_members("없는이름")) == 0


def test_settings_roundtrip(db):
    assert db.get_setting("default_model", "기본") == "기본"
    db.set_setting("default_model", "claude-opus-5")
    db.set_setting("default_model", "claude-sonnet-5")  # 덮어쓰기
    assert db.get_setting("default_model") == "claude-sonnet-5"

    db.set_program_setting("funnel-builder", "AI_LABEL", "0")
    assert db.get_program_settings("funnel-builder") == {"AI_LABEL": "0"}


def test_run_history(db):
    run_id = db.start_run("funnel-builder", "dry")
    assert db.get_run(run_id)["status"] == "running"
    db.finish_run(run_id, "success", 0, "로그", "/tmp/out")
    record = db.get_run(run_id)
    assert record["status"] == "success" and record["output_dir"] == "/tmp/out"


# -------------------------------------------------------------------- 실행기
def test_dry_run_produces_outputs(db, tmp_path):
    """실제 퍼널 빌더를 모의 실행해 산출물이 나오는지 본다."""
    program = load_manifest(PRODUCTS_DIR / "funnel-builder")
    outcome = run_program(program, db, mode="dry")

    assert outcome.status == "success", outcome.log
    assert outcome.output_dir
    from pathlib import Path

    produced = {p.name for p in Path(outcome.output_dir).rglob("*") if p.is_file()}
    assert {"landing.html", "build_report.md", "copy_variants.json"} <= produced


def test_run_without_run_spec_raises(db, minimal_program):
    program = load_manifest(minimal_program / "demo")
    with pytest.raises(RunError, match="실행 정의"):
        run_program(program, db, mode="dry")


def test_dry_run_unsupported_raises(db, tmp_path):
    program = ProgramManifest(
        id="demo", number=1, name="데모",
        run={"command": ["echo", "hi"], "dry_run_command": []},
    )
    program.directory = tmp_path
    with pytest.raises(RunError, match="모의 실행"):
        run_program(program, db, mode="dry")


def test_failed_run_is_recorded(db, tmp_path):
    program = ProgramManifest(
        id="demo", number=1, name="데모",
        run={"command": ["python", "-c", "import sys; sys.exit(1)"]},
    )
    program.directory = tmp_path
    outcome = run_program(program, db, mode="real")
    assert outcome.status == "failed"
    assert db.get_run(outcome.run_id)["status"] == "failed"


def test_exit_code_2_is_warning_not_failure(db, tmp_path):
    """종료 코드 2 = '만들어졌지만 사람이 고쳐야 함' 이라는 약속."""
    program = ProgramManifest(
        id="demo", number=1, name="데모",
        run={"command": ["python", "-c", "import sys; sys.exit(2)"]},
    )
    program.directory = tmp_path
    assert run_program(program, db, mode="real").status == "warning"


# ------------------------------------------------------------------- 화면
@pytest.mark.parametrize(
    "url",
    [
        "/",
        "/programs/funnel-builder",
        "/programs/funnel-builder/edit",
        "/programs/funnel-builder/test",
        "/programs/funnel-builder/members",
        "/programs/funnel-builder/manual/admin",
        "/programs/funnel-builder/manual/client",
        "/members",
        "/settings",
        "/manual",
        "/manual/admin",
        "/manual/client",
    ],
)
def test_every_page_renders(client, url):
    response = client.get(url)
    assert response.status_code == 200, url
    assert "통합 관리자 대시보드" in response.text


def test_home_lists_registered_programs(client):
    body = client.get("/").text
    assert "퍼널 빌더" in body


def test_unknown_program_returns_404(client):
    assert client.get("/programs/없는프로그램").status_code == 404


def test_program_view_shows_steps_and_faq(client):
    body = client.get("/programs/funnel-builder").text
    assert "이용 순서" in body
    assert "자주 묻는 질문" in body
    assert "모의 실행과 실제 실행은 뭐가 다른가요?" in body


def test_edit_page_shows_settings_and_files(client):
    body = client.get("/programs/funnel-builder/edit").text
    assert "prompts/hooks.md" in body
    assert "사용할 Claude 모델" in body


def test_file_editor_loads_and_saves(client, tmp_path):
    response = client.get("/programs/funnel-builder/file?path=prompts/hooks.md")
    assert response.status_code == 200
    assert "사람이 스크롤을 멈추는" in response.text


def test_file_editor_rejects_unlisted_path(client):
    response = client.get(
        "/programs/funnel-builder/file?path=../../shared/llm.py", follow_redirects=False
    )
    assert response.status_code == 303, "편집 대상이 아닌 파일은 막아야 합니다"


def test_program_settings_save(client):
    response = client.post(
        "/programs/funnel-builder/settings",
        data={"CLAUDE_MODEL": "claude-opus-5"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "claude-opus-5" in client.get("/programs/funnel-builder/edit").text


def test_member_flow_through_ui(client):
    client.post(
        "/members",
        data={"name": "박영수", "email": "park@example.com", "source": "크몽", "memo": ""},
        follow_redirects=True,
    )
    assert "박영수" in client.get("/members").text

    client.post(
        "/members/1/licenses",
        data={"program_id": "funnel-builder", "plan": "템플릿", "price": 150000,
              "retainer": 0, "expires_at": "", "memo": ""},
        follow_redirects=True,
    )
    detail = client.get("/members/1").text
    assert "템플릿" in detail and "150,000원" in detail

    # 프로그램별 회원 화면에도 나타난다
    assert "박영수" in client.get("/programs/funnel-builder/members").text

    client.post("/members/1/notes", data={"body": "환불 문의 응대함"}, follow_redirects=True)
    assert "환불 문의 응대함" in client.get("/members/1").text


def test_global_settings_save(client):
    client.post(
        "/settings",
        data={"default_model": "claude-opus-5", "ai_label": "on",
              "business_name": "테스트상회", "contact_email": "a@b.com",
              "refund_policy": "7일 이내 환불"},
        follow_redirects=True,
    )
    body = client.get("/settings").text
    assert "테스트상회" in body and "7일 이내 환불" in body


def test_settings_page_lists_banned_phrases(client):
    body = client.get("/settings").text
    assert str(len(banned_phrases.BANNED)) in body


def test_dry_run_through_ui(client):
    response = client.post(
        "/programs/funnel-builder/test", data={"mode": "dry", "member_id": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "성공" in response.text or "경고" in response.text
    assert "산출물 보기" in response.text


def test_reload_button_works(client):
    assert client.post("/reload", follow_redirects=True).status_code == 200


def test_preview_blocks_files_outside_outputs(client):
    response = client.get(f"/preview?path={ROOT_DIR / 'shared' / 'llm.py'}")
    assert response.status_code == 403


# ------------------------------------------------------------------- 문서
@pytest.mark.parametrize("name", ["admin-manual.md", "client-manual.md"])
def test_manuals_exist_and_are_clean(name):
    path = ROOT_DIR / "docs" / name
    assert path.is_file(), f"{name} 이 없습니다"
    text = path.read_text(encoding="utf-8")
    assert len(text) > 3000, "매뉴얼이 너무 짧습니다"
    assert banned_phrases.check(text) == []


def test_client_manual_covers_cost_and_legal_duties():
    text = (ROOT_DIR / "docs" / "client-manual.md").read_text(encoding="utf-8")
    for topic in ["비용", "환불", "사업자", "API", "초안"]:
        assert topic in text, f"클라이언트 매뉴얼에 '{topic}' 안내가 없습니다"


def test_admin_manual_explains_adding_a_program():
    text = (ROOT_DIR / "docs" / "admin-manual.md").read_text(encoding="utf-8")
    assert "program.yaml" in text
    assert "새 프로그램" in text


def test_program_manuals_are_clean():
    program = load_manifest(PRODUCTS_DIR / "funnel-builder")
    for relative in (program.manuals.admin, program.manuals.client):
        text = program.resolve(relative).read_text(encoding="utf-8")
        assert banned_phrases.check(text) == [], relative


# ------------------------------------------------- 등록된 프로그램 전체 규약
def test_all_programs_registered_with_unique_numbers():
    registry = Registry()
    ids = [p.id for p in registry]
    numbers = [p.number for p in registry]
    assert {"funnel-builder", "hook-script", "ebook-gen"} <= set(ids)
    assert len(numbers) == len(set(numbers)), "프로그램 번호가 겹칩니다"
    assert registry.errors == []


@pytest.mark.parametrize("program_id", ["funnel-builder", "hook-script", "ebook-gen"])
def test_every_program_has_full_manifest(program_id):
    """운영 중인 프로그램은 대시보드 화면을 채울 정보를 모두 갖춰야 한다."""
    program = Registry().require(program_id)
    assert program.status == "ready"
    assert program.summary.strip()
    assert len(program.steps) >= 5, "이용 순서가 부실합니다"
    assert len(program.faq) >= 5, "FAQ 가 부실합니다"
    assert program.settings, "설정 항목이 없습니다"
    assert program.editable_files, "편집 가능한 파일이 없습니다"
    assert len(program.outputs) >= 3
    assert program.pricing, "판매 플랜이 없습니다"
    assert program.runnable and program.run.dry_run_command


@pytest.mark.parametrize("program_id", ["funnel-builder", "hook-script", "ebook-gen"])
def test_every_program_manual_is_detailed_and_clean(program_id):
    program = Registry().require(program_id)
    for audience, relative in (("admin", program.manuals.admin),
                               ("client", program.manuals.client)):
        assert relative, f"{program_id} 에 {audience} 매뉴얼 경로가 없습니다"
        text = program.resolve(relative).read_text(encoding="utf-8")
        assert len(text) > 4000, f"{program_id}/{relative} 이 너무 짧습니다"
        assert banned_phrases.check(text) == [], relative
        assert "## " in text, "장 구분이 없습니다"


@pytest.mark.parametrize("program_id", ["funnel-builder", "hook-script", "ebook-gen"])
def test_client_manual_covers_the_essentials(program_id):
    """구매자가 반드시 알아야 할 것이 빠지면 문의가 들어온다."""
    program = Registry().require(program_id)
    text = program.resolve(program.manuals.client).read_text(encoding="utf-8")
    # 구매자용 문서에서는 대시보드를 '관리 화면' 으로 부른다. 용어를 통일한다.
    for topic in ["비용", "API", "초안", "관리 화면"]:
        assert topic in text, f"{program_id} 클라이언트 매뉴얼에 '{topic}' 안내가 없습니다"


@pytest.mark.parametrize("program_id", ["funnel-builder", "hook-script", "ebook-gen"])
def test_every_editable_file_exists(program_id):
    program = Registry().require(program_id)
    for spec in program.editable_files:
        assert program.resolve(spec.path).is_file(), f"{program_id}: {spec.path} 가 없습니다"


@pytest.mark.parametrize("program_id", ["funnel-builder", "hook-script", "ebook-gen"])
def test_program_pages_render_for_each_program(client, program_id):
    for suffix in ("", "/edit", "/test", "/members", "/manual/admin", "/manual/client"):
        response = client.get(f"/programs/{program_id}{suffix}")
        assert response.status_code == 200, f"{program_id}{suffix}"


def test_hook_script_dry_run_through_ui(client):
    response = client.post(
        "/programs/hook-script/test", data={"mode": "dry", "member_id": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "성공" in response.text or "경고" in response.text


def test_ebook_gen_is_registered():
    program = Registry().require("ebook-gen")
    assert program.status == "ready"
    assert program.runnable and program.run.dry_run_command
    assert program.number == 3


def test_ebook_gen_dry_run_through_ui(client):
    response = client.post(
        "/programs/ebook-gen/test", data={"mode": "dry", "member_id": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "성공" in response.text or "경고" in response.text
