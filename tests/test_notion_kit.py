"""products/notion-template-kit 테스트.

노션 API 에 닿지 못하는 곳에서도 `deploy` 의 **순서**를 확인해야 한다.
관계 속성은 이을 상대가 이미 있어야 만들어지고, 롤업은 관계가 있어야 걸린다.
이 순서가 어긋나면 노션이 거절하는데, 그건 실제로 호출해 봐야 안다.

그래서 **노션인 척하는 작은 서버**를 띄워 요청을 받아 적는다.
무엇을 어떤 차례로 보냈는지 보면 순서가 맞는지 알 수 있다.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from conftest import load_product_cli
from notion_kit import deploy as deploy_mod
from notion_kit.deploy import (
    NotionError, NotionNotConfigured, build_property_schema, build_row_properties,
    deploy, notion_config, write_deploy_log,
)
from notion_kit.generator import TemplateGenerator
from notion_kit.notion_types import ALL_TYPES, CREATABLE, MANUAL_ONLY, SUBSTITUTE
from notion_kit.sample_content import fake_ask, load_fixture
from notion_kit.schema import TemplateSpec, slugify
from notion_kit.writers import OUTPUT_FILES, estimate_minutes, write_outputs
from shared import banned_phrases

kit_cli = load_product_cli("notion-template-kit")
BASE_DIR = Path(kit_cli.BASE_DIR)


@pytest.fixture(scope="session")
def spec() -> TemplateSpec:
    return TemplateSpec(**load_fixture())


@pytest.fixture(scope="session")
def built(tmp_path_factory, spec):
    generator = TemplateGenerator("dry-run", fake_ask)
    out_dir, dirty = write_outputs(
        spec, generator.build_sales(spec), generator.build_extras(spec),
        tmp_path_factory.mktemp("kit"))
    return {"dir": out_dir, "dirty": dirty, "spec": spec}


def _raw(**changes) -> dict:
    data = load_fixture()
    data.update(changes)
    return data


# ------------------------------------------------------------------ 속성 타입
def test_manual_only_types_are_not_in_creatable():
    """API 로 못 만드는 타입이 만들 수 있는 목록에 섞이면 deploy 가 거짓말한다."""
    assert set(MANUAL_ONLY) & CREATABLE == set()
    assert set(MANUAL_ONLY) <= ALL_TYPES


def test_every_manual_type_has_a_substitute():
    for kind in MANUAL_ONLY:
        assert SUBSTITUTE[kind] in CREATABLE, kind


def test_spec_rejects_an_unknown_property_type():
    data = _raw()
    data["databases"][0]["properties"][1]["type"] = "마법"
    with pytest.raises(ValidationError, match="모르는 속성 타입"):
        TemplateSpec(**data)


def test_select_needs_options():
    data = _raw()
    data["databases"][0]["properties"][4]["options"] = []
    with pytest.raises(ValidationError, match="선택지"):
        TemplateSpec(**data)


def test_plain_types_cannot_carry_options():
    data = _raw()
    data["databases"][0]["properties"][1]["options"] = ["가", "나"]
    with pytest.raises(ValidationError, match="선택지를 넣을 수 없습니다"):
        TemplateSpec(**data)


# ------------------------------------------------------------- 구조 검사
def test_each_database_needs_exactly_one_title(spec):
    for db in spec.databases:
        assert sum(1 for p in db.properties if p.type == "title") == 1


def test_two_titles_are_rejected():
    data = _raw()
    data["databases"][0]["properties"][1]["type"] = "title"
    with pytest.raises(ValidationError, match="title 속성이 정확히 하나"):
        TemplateSpec(**data)


def test_no_title_is_rejected():
    data = _raw()
    data["databases"][0]["properties"][0]["type"] = "rich_text"
    with pytest.raises(ValidationError, match="title 속성이 정확히 하나"):
        TemplateSpec(**data)


def test_relation_must_point_at_a_real_database():
    data = _raw()
    for prop in data["databases"][1]["properties"]:
        if prop["type"] == "relation":
            prop["relation_to"] = "없는디비"
    with pytest.raises(ValidationError, match="없는 데이터베이스"):
        TemplateSpec(**data)


def test_rollup_must_travel_through_a_relation_in_the_same_database():
    data = _raw()
    for prop in data["databases"][1]["properties"]:
        if prop["type"] == "rollup":
            prop["rollup_relation"] = "시작일"       # 관계가 아니라 날짜 속성
    with pytest.raises(ValidationError, match="relation 속성이어야"):
        TemplateSpec(**data)


def test_rollup_target_property_must_exist_on_the_other_side():
    data = _raw()
    for prop in data["databases"][1]["properties"]:
        if prop["type"] == "rollup":
            prop["rollup_property"] = "저쪽에없는칸"
    with pytest.raises(ValidationError, match="rollup_property 가"):
        TemplateSpec(**data)


def test_duplicate_property_names_are_rejected():
    data = _raw()
    data["databases"][0]["properties"][2]["name"] = \
        data["databases"][0]["properties"][1]["name"]
    with pytest.raises(ValidationError, match="속성 이름이 겹칩니다"):
        TemplateSpec(**data)


def test_board_view_needs_a_group_by():
    data = _raw()
    for view in data["databases"][0]["views"]:
        if view["type"] == "board":
            view["group_by"] = ""
    with pytest.raises(ValidationError, match="group_by"):
        TemplateSpec(**data)


def test_view_cannot_reference_a_missing_property():
    data = _raw()
    for view in data["databases"][0]["views"]:
        if view["type"] == "board":
            view["group_by"] = "없는속성"
    with pytest.raises(ValidationError, match="없는 속성"):
        TemplateSpec(**data)


def test_sample_rows_cannot_use_unknown_properties():
    data = _raw()
    data["databases"][0]["sample_rows"][0]["엉뚱한칸"] = "값"
    with pytest.raises(ValidationError, match="없는 속성을 씁니다"):
        TemplateSpec(**data)


def test_database_parent_page_must_exist():
    data = _raw()
    data["databases"][0]["parent_page"] = "없는페이지"
    with pytest.raises(ValidationError, match="없는 페이지"):
        TemplateSpec(**data)


def test_button_cannot_prefill_a_missing_property():
    data = _raw()
    data["buttons"][0]["prefill"] = {"없는칸": 1}
    with pytest.raises(ValidationError, match="없는 속성을 미리 채웁니다"):
        TemplateSpec(**data)


def test_fixture_has_the_structure_the_prompt_asks_for(spec):
    """관계 2개·롤업 1개 이상이 없으면 '표 여러 개' 와 다를 바 없다."""
    assert 3 <= len(spec.databases) <= 5
    relations = [p for _, p in spec.relation_properties() if p.type == "relation"]
    rollups = [p for _, p in spec.relation_properties() if p.type == "rollup"]
    assert len(relations) >= 2
    assert len(rollups) >= 1
    for db in spec.databases:
        assert len(db.sample_rows) == 5, db.name
        assert 2 <= len(db.views) <= 3, db.name


def test_slugify_keeps_korean_and_drops_path_characters():
    assert slugify("프리랜서 프로젝트 관리") == "프리랜서-프로젝트-관리"
    assert "/" not in slugify("가/나")
    assert slugify("   ") == "템플릿"


# ------------------------------------------------------------------ 산출물
def test_all_six_outputs_are_written(built):
    """완료 기준: plan 실행 시 6종 산출물."""
    for name in OUTPUT_FILES:
        path = built["dir"] / name
        assert path.is_file(), name
        assert path.stat().st_size > 800, name


def test_spec_yaml_round_trips(built, spec):
    data = yaml.safe_load((built["dir"] / "spec.yaml").read_text(encoding="utf-8"))
    again = TemplateSpec(**data)
    assert again.name == spec.name
    assert len(again.databases) == len(spec.databases)
    assert [p.name for p in again.databases[0].properties] == \
           [p.name for p in spec.databases[0].properties]


def test_spec_yaml_warns_about_views_in_its_header(built):
    head = (built["dir"] / "spec.yaml").read_text(encoding="utf-8")[:700]
    assert "뷰" in head and "API" in head


def test_build_guide_covers_every_database_and_view(built, spec):
    text = (built["dir"] / "build_guide.md").read_text(encoding="utf-8")
    for db in spec.databases:
        assert db.name in text
        for prop in db.properties:
            assert prop.name in text, f"{db.name}.{prop.name}"
        for view in db.views:
            assert view.name in text


def test_build_guide_orders_relations_after_databases(built):
    """관계를 먼저 만들라고 적으면 따라 하다 막힌다."""
    text = (built["dir"] / "build_guide.md").read_text(encoding="utf-8")
    assert text.index("## 2단계") < text.index("## 3단계")
    assert "데이터베이스를 전부 만든 뒤에" in text


def test_build_guide_has_screenshot_placeholders(built):
    text = (built["dir"] / "build_guide.md").read_text(encoding="utf-8")
    assert text.count("스크린샷 자리") >= 4


def test_build_guide_estimates_time(built):
    text = (built["dir"] / "build_guide.md").read_text(encoding="utf-8")
    assert "예상 소요" in text and "시간" in text


def _tiny(**changes) -> TemplateSpec:
    """가장 작은 올바른 설계. 계산 규칙만 보고 싶을 때 쓴다."""
    data = {
        "name": "작은 템플릿", "topic": "주제", "audience": "타깃",
        "pages": [{"title": "홈"}],
        "databases": [{
            "key": "one", "name": "하나", "parent_page": "홈",
            "properties": [{"name": "이름", "type": "title"}],
        }],
    }
    data.update(changes)
    return TemplateSpec(**data)


def test_time_estimate_grows_with_the_structure(spec):
    """항목을 더하면 예상 시간도 늘어야 한다. 고정된 숫자면 쓸모가 없다."""
    bare = estimate_minutes(_tiny())["합계"]

    with_views = estimate_minutes(_tiny(databases=[{
        "key": "one", "name": "하나", "parent_page": "홈",
        "properties": [{"name": "이름", "type": "title"}],
        "views": [{"name": "전체", "type": "table"}],
    }]))["합계"]
    assert with_views > bare

    assert estimate_minutes(spec)["합계"] > with_views, "큰 설계가 더 오래 걸려야 합니다"


def test_time_estimate_charges_more_for_linked_properties():
    """관계·롤업은 대상을 고르고 확인하는 시간이 더 든다."""
    plain = estimate_minutes(_tiny(databases=[{
        "key": "one", "name": "하나", "parent_page": "홈",
        "properties": [{"name": "이름", "type": "title"},
                       {"name": "메모", "type": "rich_text"}],
    }]))["합계"]
    linked = estimate_minutes(_tiny(databases=[
        {"key": "one", "name": "하나", "parent_page": "홈",
         "properties": [{"name": "이름", "type": "title"},
                        {"name": "이음", "type": "relation", "relation_to": "two"}]},
        {"key": "two", "name": "둘", "parent_page": "홈",
         "properties": [{"name": "이름", "type": "title"}]},
    ]))["합계"]
    assert linked > plain


def test_build_guide_flags_properties_the_api_cannot_make(built):
    text = (built["dir"] / "build_guide.md").read_text(encoding="utf-8")
    assert "직접 만들어야 합니다" in text
    assert "상태(status) 속성은 공개 API 로 만들지 못합니다" in text


def test_sales_page_has_every_section(built):
    text = (built["dir"] / "sales_page.md").read_text(encoding="utf-8")
    for heading in ("## 제목 5안", "## 소개", "## 포함 내용", "## 사용법 3단계",
                    "## 이런 분께 맞습니다", "## 가격 3안", "## 등록 전 점검"):
        assert heading in text, heading


def test_sales_page_counts_title_lengths(built):
    text = (built["dir"] / "sales_page.md").read_text(encoding="utf-8")
    assert "자)" in text


def test_sales_page_checks_itself_for_banned_phrases(built):
    text = (built["dir"] / "sales_page.md").read_text(encoding="utf-8")
    assert banned_phrases.check(text) == []
    assert "성과를 단정하는 표현은 없습니다" in text
    assert built["dirty"] == []


def test_sales_page_keeps_the_not_for_section(built):
    """안 맞는 사람을 걸러 내면 환불과 별점 1개가 줄어든다."""
    text = (built["dir"] / "sales_page.md").read_text(encoding="utf-8")
    assert "맞지 않습니다" in text


def test_user_manual_explains_the_relations(built, spec):
    text = (built["dir"] / "user_manual.md").read_text(encoding="utf-8")
    assert "복제" in text
    assert "자주 하는 실수" in text
    for db in spec.databases:
        assert db.name in text
    relations = [(db, p) for db, p in spec.relation_properties() if p.type == "relation"]
    for db, prop in relations:
        assert prop.name in text, f"{db.name}.{prop.name}"


def test_user_manual_answers_the_empty_rollup_question(built):
    """롤업이 0 으로 보이는 이유는 구조를 모르면 못 고친다."""
    text = (built["dir"] / "user_manual.md").read_text(encoding="utf-8")
    assert "롤업" in text and "0" in text


def test_preview_brief_says_to_photograph_not_to_draw(built):
    text = (built["dir"] / "preview_brief.md").read_text(encoding="utf-8")
    assert "찍는 것" in text
    assert text.count("촬영 자리") >= 3
    assert "썸네일" in text


def test_preview_brief_warns_about_notion_branding(built):
    text = (built["dir"] / "preview_brief.md").read_text(encoding="utf-8")
    assert "로고" in text


def test_variants_lists_five_with_effort(built):
    text = (built["dir"] / "variants.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines()
            if line.startswith("|") and "---" not in line]
    assert len(rows) >= 6           # 머리글 + 5개
    assert "예상 시간" in text


def test_variants_warns_against_mass_producing(built):
    """CLAUDE.md §3 — 개수만 늘리는 방식은 만들지 않는다."""
    text = (built["dir"] / "variants.md").read_text(encoding="utf-8")
    assert "개수만 늘리는" in text


def test_outputs_carry_the_ai_label(built):
    for name in ("build_guide.md", "sales_page.md", "user_manual.md",
                 "preview_brief.md", "variants.md"):
        text = (built["dir"] / name).read_text(encoding="utf-8")
        assert "생성형 AI" in text, name


def test_ai_label_can_be_turned_off(tmp_path, spec):
    generator = TemplateGenerator("dry-run", fake_ask)
    out_dir, _ = write_outputs(spec, generator.build_sales(spec),
                               generator.build_extras(spec), tmp_path,
                               ai_label=False)
    assert "생성형 AI" not in (out_dir / "variants.md").read_text(encoding="utf-8")


def test_no_banned_phrases_anywhere(built):
    blob = "\n".join(path.read_text(encoding="utf-8")
                     for path in sorted(built["dir"].iterdir()) if path.is_file())
    assert banned_phrases.check(blob) == []


# ------------------------------------------------------------------ 생성기
def test_generator_makes_three_calls(spec):
    generator = TemplateGenerator("dry-run", fake_ask)
    generator.build_spec("주제", "타깃")
    generator.build_sales(spec)
    generator.build_extras(spec)
    assert generator.calls == 3


def test_generator_retries_with_the_reason(spec):
    state = {"n": 0}

    def broken_first(system, user, model="x", json_mode=False, **kw):
        state["n"] += 1
        if state["n"] == 1:
            return {"name": "반쪽", "pages": []}        # databases 가 없다
        assert "규격에 맞지 않았다" in user, "무엇이 틀렸는지 알려 줘야 합니다"
        return fake_ask(system, user, model, json_mode)

    generator = TemplateGenerator("x", broken_first)
    result = generator.build_spec("주제", "타깃")
    assert state["n"] == 2
    assert result.databases
    assert generator.warnings


def test_generator_gives_up_with_a_clear_message():
    def always_broken(system, user, model="x", json_mode=False, **kw):
        return {"name": "반쪽"}

    with pytest.raises(ValueError, match="규격에 맞지 않았습니다"):
        TemplateGenerator("x", always_broken).build_spec("주제", "타깃")


def test_generator_retries_sales_on_a_banned_phrase(spec):
    state = {"n": 0}

    def dirty_first(system, user, model="x", json_mode=False, **kw):
        if "판매 문구" not in system:
            return fake_ask(system, user, model, json_mode)
        state["n"] += 1
        if state["n"] == 1:
            bad = dict(fake_ask(system, user, model, json_mode))
            bad["intro"] = "이 템플릿은 수익 보장 상품입니다"
            return bad
        return fake_ask(system, user, model, json_mode)

    generator = TemplateGenerator("x", dirty_first)
    sales = generator.build_sales(spec)
    assert state["n"] == 2
    assert banned_phrases.check(json.dumps(sales, ensure_ascii=False)) == []


def test_generator_keeps_the_topic_from_the_request():
    generator = TemplateGenerator("dry-run", fake_ask)
    result = generator.build_spec("반려견 산책 기록", "애견인")
    assert result.topic == "반려견 산책 기록"
    assert result.audience == "애견인"
    assert result.slug == "반려견-산책-기록"


# ------------------------------------------------------- 노션 요청 모양
def test_property_schema_shapes(spec):
    ids = {db.key: f"id-{db.key}" for db in spec.databases}
    projects = spec.database_map["projects"]

    kind, schema, _ = build_property_schema(projects.property_map["프로젝트명"], ids)
    assert (kind, schema) == ("title", {"title": {}})

    kind, schema, _ = build_property_schema(projects.property_map["클라이언트"], ids)
    assert kind == "relation"
    assert schema["relation"]["database_id"] == "id-clients"
    assert schema["relation"]["type"] == "dual_property"

    kind, schema, _ = build_property_schema(projects.property_map["작업 수"], ids)
    assert schema["rollup"]["relation_property_name"] == "클라이언트"
    assert schema["rollup"]["function"] == "count"


def test_status_is_substituted_and_explained(spec):
    projects = spec.database_map["projects"]
    kind, schema, note = build_property_schema(projects.property_map["진행"], {})
    assert kind == "select", "status 는 API 로 못 만들어 select 로 대신한다"
    assert [o["name"] for o in schema["select"]["options"]] == \
           projects.property_map["진행"].options
    assert "공개 API 로 만들지 못합니다" in note


def test_relation_is_held_back_until_the_target_exists(spec):
    projects = spec.database_map["projects"]
    _, schema, note = build_property_schema(projects.property_map["클라이언트"], {})
    assert schema is None
    assert "아직 없습니다" in note


def test_unknown_number_format_falls_back_and_says_so(spec):
    prop = spec.database_map["projects"].property_map["견적가"].model_copy(
        update={"number_format": "도지코인"})
    _, schema, note = build_property_schema(prop, {})
    assert schema["number"]["format"] == "number"
    assert "모르는 숫자 형식" in note


def test_row_properties_skip_relations_and_empties(spec):
    tasks = spec.database_map["tasks"]
    built = build_row_properties(tasks, {
        "할 일": "테스트", "프로젝트": "무시됨", "완료": False,
        "우선순위": "높음", "예정일": "2026-09-17", "예상 시간": 3, "메모없음": "x",
    })
    assert built["할 일"]["title"][0]["text"]["content"] == "테스트"
    assert built["완료"] == {"checkbox": False}
    assert built["우선순위"] == {"select": {"name": "높음"}}
    assert built["예정일"] == {"date": {"start": "2026-09-17"}}
    assert built["예상 시간"] == {"number": 3.0}
    assert "프로젝트" not in built, "관계는 행 만들 때 채우지 않는다"
    assert "메모없음" not in built


def test_page_id_is_pulled_out_of_a_pasted_url():
    from notion_kit.deploy import _clean_id

    assert _clean_id("https://www.notion.so/My-Page-1a2b3c4d5e6f7890abcdef1234567890") \
        == "1a2b3c4d5e6f7890abcdef1234567890"
    assert _clean_id("  abc123  ") == "abc123"


# ------------------------------------------------------------------ 설정
def test_deploy_without_a_token_explains_both_steps(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    with pytest.raises(NotionNotConfigured) as excinfo:
        notion_config()
    message = str(excinfo.value)
    assert "NOTION_TOKEN" in message and "NOTION_PARENT_PAGE_ID" in message
    assert "연결" in message, "통합을 페이지에 연결하라는 안내가 빠지면 반드시 막힙니다"
    assert "없어도 됩니다" in message


def test_config_reads_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "ntn_test")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID",
                       "https://notion.so/P-1a2b3c4d5e6f7890abcdef1234567890")
    token, parent = notion_config()
    assert token == "ntn_test"
    assert parent == "1a2b3c4d5e6f7890abcdef1234567890"


# ------------------------------------------- 노션인 척하는 서버로 순서 확인
class _FakeNotion(BaseHTTPRequestHandler):
    """받은 요청을 받아 적는다. 클래스 변수로 모아 테스트가 읽는다."""

    log: list[dict] = []
    fail_on: str = ""

    def _reply(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):                                          # noqa: N802
        _FakeNotion.log.append({"method": "GET", "path": self.path})
        self._reply(200, {"object": "user", "id": "bot"})

    def do_POST(self):                                         # noqa: N802
        payload = self._read()
        entry = {"method": "POST", "path": self.path, "body": payload}
        _FakeNotion.log.append(entry)
        if _FakeNotion.fail_on and _FakeNotion.fail_on in json.dumps(
                payload, ensure_ascii=False):
            self._reply(400, {"code": "validation_error", "message": "일부러 실패"})
            return
        made = f"{self.path.strip('/')}-{len(_FakeNotion.log)}"
        self._reply(200, {"id": made, "object": "page"})

    def do_PATCH(self):                                        # noqa: N802
        payload = self._read()
        _FakeNotion.log.append({"method": "PATCH", "path": self.path, "body": payload})
        self._reply(200, {"id": self.path.rsplit("/", 1)[-1]})

    def log_message(self, *args):                              # noqa: A003
        pass


@pytest.fixture
def fake_notion(monkeypatch):
    """노션인 척하는 서버를 띄우고 deploy 를 그쪽으로 보낸다."""
    _FakeNotion.log = []
    _FakeNotion.fail_on = ""
    server = HTTPServer(("127.0.0.1", 0), _FakeNotion)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    monkeypatch.setattr(deploy_mod, "API_BASE", f"http://{host}:{port}")
    monkeypatch.setattr(deploy_mod, "PAUSE_SECONDS", 0)
    yield _FakeNotion
    server.shutdown()


def _kinds(log, method: str, path_part: str) -> list[dict]:
    return [item for item in log
            if item["method"] == method and path_part in item["path"]]


def test_deploy_checks_the_token_before_making_anything(fake_notion, spec):
    deploy(spec, "ntn_test", "parent-id")
    assert fake_notion.log[0]["method"] == "GET"
    assert "/users/me" in fake_notion.log[0]["path"]


def test_deploy_makes_pages_before_databases(fake_notion, spec):
    deploy(spec, "ntn_test", "parent-id")
    first_database = next(index for index, item in enumerate(fake_notion.log)
                          if item["path"].endswith("/databases"))
    pages_before = [item for item in fake_notion.log[:first_database]
                    if item["path"].endswith("/pages")]
    assert len(pages_before) == sum(1 for p in spec.pages for _ in p.walk())


def test_databases_are_created_without_relations_or_rollups(fake_notion, spec):
    deploy(spec, "ntn_test", "parent-id")
    for call in _kinds(fake_notion.log, "POST", "/databases"):
        for name, schema in call["body"]["properties"].items():
            assert "relation" not in schema, name
            assert "rollup" not in schema, name


def test_relations_are_patched_after_every_database_exists(fake_notion, spec):
    deploy(spec, "ntn_test", "parent-id")
    last_create = max(index for index, item in enumerate(fake_notion.log)
                      if item["method"] == "POST" and item["path"].endswith("/databases"))
    relation_patches = [index for index, item in enumerate(fake_notion.log)
                        if item["method"] == "PATCH"
                        and any("relation" in s for s in item["body"]["properties"].values())]
    assert relation_patches
    assert min(relation_patches) > last_create


def test_rollups_are_patched_after_relations(fake_notion, spec):
    deploy(spec, "ntn_test", "parent-id")
    relation_at = [index for index, item in enumerate(fake_notion.log)
                   if item["method"] == "PATCH"
                   and any("relation" in s for s in item["body"]["properties"].values())]
    rollup_at = [index for index, item in enumerate(fake_notion.log)
                 if item["method"] == "PATCH"
                 and any("rollup" in s for s in item["body"]["properties"].values())]
    assert rollup_at, "롤업을 걸지 않았습니다"
    assert min(rollup_at) > max(relation_at), "롤업은 관계가 생긴 뒤에 걸어야 합니다"


def test_relation_patch_points_at_a_real_created_id(fake_notion, spec):
    deploy(spec, "ntn_test", "parent-id")
    made = {item["path"].rsplit("/", 1)[-1] for item in fake_notion.log
            if item["method"] == "POST" and item["path"].endswith("/databases")}
    created_ids = {f"databases-{index + 1}" for index in range(len(fake_notion.log))}
    for item in fake_notion.log:
        if item["method"] != "PATCH":
            continue
        for schema in item["body"]["properties"].values():
            if "relation" in schema:
                assert schema["relation"]["database_id"] in created_ids
    assert made is not None


def test_sample_rows_are_added_last(fake_notion, spec):
    deploy(spec, "ntn_test", "parent-id")
    row_calls = [index for index, item in enumerate(fake_notion.log)
                 if item["method"] == "POST" and item["path"].endswith("/pages")
                 and item["body"].get("parent", {}).get("type") == "database_id"]
    patches = [index for index, item in enumerate(fake_notion.log)
               if item["method"] == "PATCH"]
    assert row_calls and min(row_calls) > max(patches)
    assert len(row_calls) == sum(len(db.sample_rows) for db in spec.databases)


def test_deploy_reports_success_and_manual_work(fake_notion, spec):
    report = deploy(spec, "ntn_test", "parent-id")
    assert report.ok
    assert report.made > 10
    joined = " ".join(report.manual_todo)
    assert "뷰" in joined, "뷰는 API 로 못 만든다는 것을 알려야 합니다"
    assert "복제 허용" in joined


def test_deploy_records_how_far_it_got_when_it_fails(fake_notion, spec, tmp_path):
    """중간에 끊기면 노션에 절반만 남는다. 무엇이 남았는지 알아야 지운다."""
    fake_notion.fail_on = "클라이언트"
    report = deploy(spec, "ntn_test", "parent-id")

    assert not report.ok
    assert report.failed_at
    assert report.made >= 1, "실패 전에 만든 것은 기록에 남아야 합니다"

    log_path = write_deploy_log(report, tmp_path / "deploy_log.md")
    text = log_path.read_text(encoding="utf-8")
    assert "멈췄습니다" in text
    assert "만들어진 페이지를 지우세요" in text
    assert "두 벌" in text


def test_deploy_log_lists_every_step(fake_notion, spec, tmp_path):
    report = deploy(spec, "ntn_test", "parent-id")
    text = write_deploy_log(report, tmp_path / "log.md").read_text(encoding="utf-8")
    for db in spec.databases:
        assert db.name in text
    assert "손으로 해야 하는 것" in text


def test_deploy_explains_a_permission_error(fake_notion, spec, monkeypatch):
    class Denied(BaseHTTPRequestHandler):
        pass

    from notion_kit.deploy import _explain

    class _Response:
        status_code = 403

        @staticmethod
        def json():
            return {"code": "restricted_resource", "message": "no"}
        text = ""

    assert "연결" in _explain(_Response())
    assert Denied is not None


# ------------------------------------------------------------------ CLI
def test_cli_plan_writes_six_files(tmp_path, capsys):
    """완료 기준: plan 실행 시 6종 산출물 생성."""
    assert kit_cli.main(["plan", "프리랜서 프로젝트 관리",
                         "--audience", "1인 디자이너",
                         "--dry-run", "--out", str(tmp_path)]) == 0
    out_dir = tmp_path / "프리랜서-프로젝트-관리"
    for name in OUTPUT_FILES:
        assert (out_dir / name).is_file(), name
    assert "모의 실행" in capsys.readouterr().out


def test_cli_plan_warns_about_manual_properties(tmp_path, capsys):
    kit_cli.main(["plan", "주제", "--dry-run", "--out", str(tmp_path)])
    assert "API 로 못 만드는 속성" in capsys.readouterr().out


def test_cli_check_validates_a_spec(tmp_path, capsys):
    kit_cli.main(["plan", "주제", "--dry-run", "--out", str(tmp_path)])
    spec_path = next(tmp_path.glob("*/spec.yaml"))
    assert kit_cli.main(["check", str(spec_path)]) == 0
    assert "규격에 맞습니다" in capsys.readouterr().out


def test_cli_check_reports_a_broken_spec(tmp_path, capsys):
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump({"name": "x", "topic": "y", "audience": "z"}),
                    encoding="utf-8")
    assert kit_cli.main(["check", str(path)]) == 1
    assert "규격에 맞지 않습니다" in capsys.readouterr().err


def test_cli_deploy_without_a_token_is_not_an_error(tmp_path, capsys, monkeypatch):
    """완료 기준: 토큰 없으면 친절한 안내 후 종료(에러 아님)."""
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    kit_cli.main(["plan", "주제", "--dry-run", "--out", str(tmp_path)])
    capsys.readouterr()

    spec_path = next(tmp_path.glob("*/spec.yaml"))
    assert kit_cli.main(["deploy", str(spec_path)]) == 0, "오류가 아니라 안내입니다"
    out = capsys.readouterr().out
    assert "NOTION_TOKEN" in out
    assert "build_guide.md" in out, "손으로 만드는 길을 알려 줘야 합니다"


def test_cli_without_a_command_shows_help(capsys):
    assert kit_cli.main([]) == 1
    assert "plan" in capsys.readouterr().out


def test_cli_rejects_a_missing_spec(capsys):
    assert kit_cli.main(["check", "/없는/파일.yaml"]) == 1
    assert "찾지 못했습니다" in capsys.readouterr().err


# ------------------------------------------------------------------ 문서
def test_readme_covers_usage_and_limits():
    text = (BASE_DIR / "README.md").read_text(encoding="utf-8")
    for token in ("cli.py plan", "deploy", "spec.yaml", "NOTION_TOKEN", "뷰"):
        assert token in text, token
    assert banned_phrases.check(text) == []


def test_product_manuals_are_detailed_and_clean():
    for name in ("admin.md", "client.md"):
        path = BASE_DIR / "docs" / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert len(text) > 4000, f"{name} 이 너무 짧습니다"
        assert banned_phrases.check(text) == []


def test_prompts_state_the_hard_rules():
    spec_prompt = (BASE_DIR / "prompts" / "spec.md").read_text(encoding="utf-8")
    assert "title 속성이 정확히 하나" in spec_prompt
    assert "정확히 5행" in spec_prompt
    sales_prompt = (BASE_DIR / "prompts" / "sales.md").read_text(encoding="utf-8")
    assert "성과를 단정하지 마라" in sales_prompt
