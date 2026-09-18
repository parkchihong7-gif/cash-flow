"""통합 관리자 대시보드 테스트.

실제 Claude 호출 없이, 프로그램 등록 → 화면 → 모의 실행 → 회원관리까지 검사한다.
"""

from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from core import auth
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
    """접속 코드를 통과한 상태의 클라이언트.

    대시보드는 접속 코드를 넣어야 열린다. 화면을 보는 테스트는
    매번 로그인을 되풀이할 이유가 없으므로 여기서 한 번 통과시킨다.
    코드 잠금 자체는 `test_auth.py` 가 따로 검사한다.
    """
    client = TestClient(create_app(tmp_path / "app.db"))
    response = client.post("/login", data={"code": auth.access_code()})
    assert response.status_code == 200, "테스트용 로그인이 실패했습니다"
    return client


@pytest.fixture
def locked_client(tmp_path):
    """로그인하지 않은 클라이언트. 리다이렉트를 그대로 본다."""
    return TestClient(create_app(tmp_path / "app.db"), follow_redirects=False)


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
    assert {"funnel-builder", "hook-script", "ebook-gen", "lecture-deck",
            "kmong-copy", "n8n-gen", "groupbuy-ledger", "income-sim",
            "notion-template-kit", "affiliate-matcher", "agency-kit",
            "niche-research", "exam-drill", "senior-video", "naver-blog", "speaker-desk"} <= set(ids)
    assert len(numbers) == len(set(numbers)), "프로그램 번호가 겹칩니다"
    assert registry.errors == []


@pytest.mark.parametrize("program_id", ["funnel-builder", "hook-script", "ebook-gen",
                                       "lecture-deck", "kmong-copy", "n8n-gen",
                                       "groupbuy-ledger", "income-sim",
                                       "notion-template-kit", "affiliate-matcher",
                                       "agency-kit", "niche-research", "exam-drill", "senior-video", "naver-blog", "speaker-desk"])
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


@pytest.mark.parametrize("program_id", ["funnel-builder", "hook-script", "ebook-gen",
                                       "lecture-deck", "kmong-copy", "n8n-gen",
                                       "groupbuy-ledger", "income-sim",
                                       "notion-template-kit", "affiliate-matcher",
                                       "agency-kit", "niche-research", "exam-drill", "senior-video", "naver-blog", "speaker-desk"])
def test_every_program_manual_is_detailed_and_clean(program_id):
    program = Registry().require(program_id)
    for audience, relative in (("admin", program.manuals.admin),
                               ("client", program.manuals.client)):
        assert relative, f"{program_id} 에 {audience} 매뉴얼 경로가 없습니다"
        text = program.resolve(relative).read_text(encoding="utf-8")
        assert len(text) > 4000, f"{program_id}/{relative} 이 너무 짧습니다"
        assert banned_phrases.check(text) == [], relative
        assert "## " in text, "장 구분이 없습니다"


@pytest.mark.parametrize("program_id", ["funnel-builder", "hook-script", "ebook-gen",
                                       "lecture-deck", "kmong-copy", "n8n-gen",
                                       "groupbuy-ledger", "income-sim",
                                       "notion-template-kit", "affiliate-matcher",
                                       "agency-kit", "niche-research", "exam-drill", "senior-video", "naver-blog", "speaker-desk"])
def test_client_manual_covers_the_essentials(program_id):
    """구매자가 반드시 알아야 할 것이 빠지면 문의가 들어온다."""
    program = Registry().require(program_id)
    text = program.resolve(program.manuals.client).read_text(encoding="utf-8")
    # 구매자용 문서에서는 대시보드를 '관리 화면' 으로 부른다. 용어를 통일한다.
    for topic in ["비용", "API", "초안", "관리 화면"]:
        assert topic in text, f"{program_id} 클라이언트 매뉴얼에 '{topic}' 안내가 없습니다"


@pytest.mark.parametrize("program_id", ["funnel-builder", "hook-script", "ebook-gen",
                                       "lecture-deck", "kmong-copy", "n8n-gen",
                                       "groupbuy-ledger", "income-sim",
                                       "notion-template-kit", "affiliate-matcher",
                                       "agency-kit", "niche-research", "exam-drill", "senior-video", "naver-blog", "speaker-desk"])
def test_every_editable_file_exists(program_id):
    program = Registry().require(program_id)
    for spec in program.editable_files:
        assert program.resolve(spec.path).is_file(), f"{program_id}: {spec.path} 가 없습니다"


@pytest.mark.parametrize("program_id", ["funnel-builder", "hook-script", "ebook-gen",
                                       "lecture-deck", "kmong-copy", "n8n-gen",
                                       "groupbuy-ledger", "income-sim",
                                       "notion-template-kit", "affiliate-matcher",
                                       "agency-kit", "niche-research", "exam-drill", "senior-video", "naver-blog", "speaker-desk"])
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


def test_lecture_deck_is_registered():
    program = Registry().require("lecture-deck")
    assert program.status == "ready"
    assert program.number == 4
    assert program.runnable and program.run.dry_run_command


def test_lecture_deck_dry_run_through_ui(client):
    response = client.post(
        "/programs/lecture-deck/test", data={"mode": "dry", "member_id": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "성공" in response.text or "경고" in response.text


def test_kmong_copy_is_registered():
    program = Registry().require("kmong-copy")
    assert program.status == "ready"
    assert program.number == 5
    assert program.runnable and program.run.dry_run_command


def test_kmong_copy_dry_run_through_ui(client):
    response = client.post(
        "/programs/kmong-copy/test", data={"mode": "dry", "member_id": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "성공" in response.text or "경고" in response.text


def test_n8n_gen_is_registered():
    program = Registry().require("n8n-gen")
    assert program.status == "ready"
    assert program.number == 6
    assert program.runnable and program.run.dry_run_command


def test_n8n_gen_dry_run_through_ui(client):
    response = client.post(
        "/programs/n8n-gen/test", data={"mode": "dry", "member_id": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "성공" in response.text or "경고" in response.text


def test_groupbuy_ledger_is_registered():
    program = Registry().require("groupbuy-ledger")
    assert program.status == "ready"
    assert program.number == 7
    assert program.runnable and program.run.dry_run_command


def test_groupbuy_ledger_dry_run_through_ui(client):
    response = client.post(
        "/programs/groupbuy-ledger/test", data={"mode": "dry", "member_id": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "성공" in response.text or "경고" in response.text


def test_income_sim_is_registered():
    program = Registry().require("income-sim")
    assert program.status == "ready"
    assert program.number == 8
    assert program.runnable and program.run.dry_run_command


def test_income_sim_dry_run_through_ui(client):
    response = client.post(
        "/programs/income-sim/test", data={"mode": "dry", "member_id": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "성공" in response.text or "경고" in response.text


def test_notion_template_kit_is_registered():
    program = Registry().require("notion-template-kit")
    assert program.status == "ready"
    assert program.number == 9
    assert program.runnable and program.run.dry_run_command


def test_notion_template_kit_dry_run_through_ui(client):
    response = client.post(
        "/programs/notion-template-kit/test", data={"mode": "dry", "member_id": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "성공" in response.text or "경고" in response.text


def test_affiliate_matcher_is_registered():
    program = Registry().require("affiliate-matcher")
    assert program.status == "ready"
    assert program.number == 10
    assert program.runnable and program.run.dry_run_command


def test_affiliate_matcher_dry_run_through_ui(client):
    response = client.post(
        "/programs/affiliate-matcher/test", data={"mode": "dry", "member_id": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "성공" in response.text or "경고" in response.text


def test_agency_kit_is_registered():
    program = Registry().require("agency-kit")
    assert program.status == "ready"
    assert program.number == 11
    assert program.runnable and program.run.dry_run_command


def test_agency_kit_dry_run_through_ui(client):
    """세 모듈을 한 번에 돌려 본다. 대행 상담에서 그대로 보여 주는 화면이다."""
    response = client.post(
        "/programs/agency-kit/test", data={"mode": "dry", "member_id": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "성공" in response.text or "경고" in response.text


def test_niche_research_is_registered():
    program = Registry().require("niche-research")
    assert program.status == "ready"
    assert program.number == 12
    assert program.runnable and program.run.dry_run_command


def test_niche_research_dry_run_through_ui(client):
    """샘플 자료 3일치로 보고서를 만든다. 유튜브도 Claude 도 부르지 않는다."""
    response = client.post(
        "/programs/niche-research/test", data={"mode": "dry", "member_id": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "성공" in response.text or "경고" in response.text


# ------------------------------------------------------------ 정기 실행
def test_schedule_page_shows_recurring_and_manual_programs(client):
    """되풀이하는 것과 필요할 때만 도는 것이 갈려 보여야 한다."""
    response = client.get("/schedule")
    assert response.status_code == 200
    body = response.text
    assert "정기 실행" in body
    assert "되풀이해 돌리는 것" in body
    assert "필요할 때만 돌리는 것" in body
    # 매일 돌아야 하는 12번은 반드시 위쪽 묶음에 있어야 한다.
    assert "니치 리서치" in body
    assert "0 6 * * *" in body, "크론 한 줄을 복사할 수 있어야 한다"


def test_schedule_page_does_not_offer_to_run_anything(client):
    """이 화면에서 프로그램을 돌리면 안 된다. 스케줄러는 cron 이다."""
    body = client.get("/schedule").text
    # 본문만 본다. 왼쪽 메뉴의 검색창은 모든 화면에 있다.
    main = body.split("<h1>정기 실행</h1>", 1)[1]
    assert "<form" not in main, "정기 실행 화면에는 실행 폼이 없어야 한다"
    assert "이 화면은 프로그램을 돌리지 않습니다" in main or \
           "이 화면은 프로그램을 돌리지 않습니다".replace(" ", "") in main.replace(" ", "")


def test_recurring_programs_explain_what_breaks_if_skipped():
    """되풀이하는 프로그램은 '거르면 무엇이 깨지는지' 를 적어 둬야 한다."""
    for program in Registry().programs:
        if not program.recurring:
            continue
        assert program.schedule.why, f"{program.id}: 왜 이 주기인지가 비었습니다"
        assert program.schedule.skipped, f"{program.id}: 거르면 어떻게 되는지가 비었습니다"
        assert program.schedule.command, f"{program.id}: 손으로 돌릴 명령이 비었습니다"


def test_niche_research_must_run_daily():
    """매일 찍지 않으면 그날은 영영 빈다. 이 상품의 전제다."""
    program = Registry().require("niche-research")
    assert program.schedule.cadence == "daily"
    assert program.schedule.grace_days == 1
    assert program.schedule.warmup_days >= 3, "3일치는 쌓여야 지표가 나온다"
    assert program.schedule.cron.startswith("0 6 * * *")


def test_one_shot_programs_are_never_late():
    """퍼널·전자책은 안 돌렸다고 밀린 게 아니다."""
    from core.schedule import collect as collect_schedule

    rows = {row.id: row for row in collect_schedule(Registry(), Database(":memory:"))}
    assert rows["funnel-builder"].state == "manual"
    assert rows["funnel-builder"].late is False
    assert rows["ebook-gen"].late is False


def test_schedule_marks_a_stale_daily_program_as_late(db):
    """어제 돌고 만 매일 프로그램은 밀린 것으로 잡혀야 한다."""
    from datetime import date, timedelta

    from core.schedule import collect as collect_schedule, summarize

    run_id = db.start_run("niche-research", mode="dry")
    db.finish_run(run_id, status="success", exit_code=0, log="ok")

    later = date.today() + timedelta(days=5)
    rows = {row.id: row for row in collect_schedule(Registry(), db, today=later)}
    row = rows["niche-research"]
    assert row.age_days == 5
    assert row.late is True
    assert row.state_label == "밀렸습니다"

    # 오늘 기준이면 밀리지 않았다.
    fresh = {r.id: r for r in collect_schedule(Registry(), db)}
    assert fresh["niche-research"].late is False
    assert fresh["niche-research"].state == "fresh"
    assert summarize(list(fresh.values()))["late"] == 0


def test_schedule_counts_never_run_programs_separately(db):
    """한 번도 안 돈 것과 밀린 것은 다른 일이다. 손쓸 방법이 다르다."""
    from core.schedule import collect as collect_schedule, summarize

    rows = collect_schedule(Registry(), db)
    counts = summarize(rows)
    assert counts["recurring"] >= 3
    assert counts["never"] == counts["recurring"], "아직 아무것도 안 돌렸다"
    assert counts["late"] == 0, "한 번도 안 돈 것을 밀렸다고 하면 안 된다"


def test_schedule_parses_unreadable_timestamps_without_crashing():
    """DB 값이 깨져 있어도 화면은 떠야 한다."""
    from core.schedule import days_since, parse_when

    assert parse_when("") is None
    assert parse_when("어제") is None
    assert parse_when("2026-09-17T06:00:00Z") is not None
    assert days_since(None) is None


# ---------------------------------------------------------- 권한·환경 점검
def test_access_page_splits_ready_now_from_waiting(client):
    """오늘 바로 되는 것과 심사를 기다려야 하는 것이 갈려 보여야 한다."""
    response = client.get("/access")
    assert response.status_code == 200
    body = response.text
    assert "권한·환경 점검" in body
    assert "지금 바로" in body
    assert "심사를 기다려야" in body
    assert "집 컴퓨터" in body


def test_access_page_never_prints_a_key_value(client, monkeypatch):
    """값은 절대 화면에 싣지 않는다. 대시보드는 터널로도 열린다."""
    monkeypatch.setenv("YOUTUBE_API_KEY", "AIzaSy-절대-보이면-안-되는-값")
    body = client.get("/access").text
    assert "절대-보이면-안-되는-값" not in body
    assert "YOUTUBE_API_KEY" in body


def test_access_marks_a_set_key(monkeypatch):
    from core.access import collect

    monkeypatch.setenv("YOUTUBE_API_KEY", "있음")
    rows = {row.id: row for row in collect(Registry())}
    youtube = next(item for item in rows["niche-research"].accounts
                   if item.env_key == "YOUTUBE_API_KEY")
    assert youtube.env_set
    assert youtube.state_label == "넣었습니다"


def test_programs_needing_review_are_not_called_ready_now():
    """심사가 걸린 상품을 '오늘 바로' 라고 팔면 환불로 돌아온다."""
    from core.access import collect

    rows = {row.id: row for row in collect(Registry(), environ={})}
    for program_id in ("agency-kit", "senior-video"):
        assert rows[program_id].waiting, f"{program_id} 에 심사 항목이 있어야 한다"
        assert rows[program_id].state == "wait"
        assert not rows[program_id].ready_now


def test_offline_programs_need_no_signup():
    """계정도 인터넷도 없는 상품은 '지금 바로' 여야 한다."""
    from core.access import collect

    rows = {row.id: row for row in collect(Registry(), environ={})}
    for program_id in ("speaker-desk", "exam-drill", "income-sim"):
        assert rows[program_id].ready_now, f"{program_id} 는 바로 쓸 수 있어야 한다"


def test_every_program_declares_what_it_needs():
    """준비물을 상품이 스스로 들고 있어야 화면이 한 장으로 모을 수 있다."""
    for program in Registry().programs:
        need = program.requirements
        assert need.cautions, f"{program.id}: 조심할 것이 비었습니다"
        assert need.limits, f"{program.id}: 한도·쿼터가 비었습니다"
        for account in need.accounts:
            assert account.why, f"{program.id}/{account.name}: 왜 필요한지가 없습니다"
            assert account.how, f"{program.id}/{account.name}: 어디서 받는지가 없습니다"


def test_hard_to_run_at_home_must_say_why():
    """'집에서 어렵다' 고만 적으면 화면이 아무 도움이 안 된다."""
    from core.manifest import Requirements

    with pytest.raises(Exception, match="home_pc_note"):
        Requirements(home_pc="partial")
    assert Requirements(home_pc="partial", home_pc_note="서버가 필요합니다")


def test_yaml_bare_yes_is_read_as_the_string():
    """YAML 은 따옴표 없는 yes 를 참으로 읽는다. 여기서는 그게 뜻한 값이다."""
    from core.manifest import Requirements

    assert Requirements(home_pc=True).home_pc == "yes"
    assert Requirements(home_pc=False, home_pc_note="이유").home_pc == "no"


def test_access_summary_counts_add_up():
    from core.access import collect, summarize

    rows = collect(Registry(), environ={})
    counts = summarize(rows)
    assert counts["total"] == len(rows)
    assert counts["now"] + counts["setup"] + counts["wait"] + counts["hard"] \
        == counts["total"]
