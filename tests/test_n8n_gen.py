"""products/n8n-gen 테스트.

가짜 LLM(`sample_content.fake_ask`)을 주입해 실제 Claude 호출 없이
계획 → 조립 → 검증 → 산출물 전 과정을 검증한다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import load_product_cli
from n8n_gen.assembler import (
    WORKFLOW_ID_LENGTH, X_STEP, assemble, workflow_id,
)
from n8n_gen.generator import BASE_DIR, PlanGenerator
from n8n_gen.nodes import (
    FALLBACK_TEMPLATE, get_template, load_templates, template_ids,
)
from n8n_gen.pusher import N8nNotConfigured, n8n_config
from n8n_gen.sample_content import PLANS, fake_ask, pick_plan
from n8n_gen.schema import Plan
from n8n_gen.validator import validate
from n8n_gen.writers import CREDENTIAL_GUIDE, write_outputs
from shared import banned_phrases

n8n_cli = load_product_cli("n8n-gen")

N8N_DIR = Path(BASE_DIR)
EXAMPLES_PATH = N8N_DIR / "templates" / "examples.txt"

#: 사양에 명시된 1차 지원 노드.
REQUIRED_TEMPLATES = (
    "schedule-trigger", "webhook-trigger", "google-sheets-read",
    "google-sheets-append", "http-request", "code", "if", "set",
    "gmail-send", "slack-post", "telegram-send", "claude",
    "notion-create-page", "wait", "merge",
)


# ------------------------------------------------------------------ 픽스처
def _plan(name: str = "sheet-claude-slack") -> Plan:
    return Plan(**PLANS[name])


@pytest.fixture
def plan() -> Plan:
    return _plan()


@pytest.fixture
def built(plan, tmp_path):
    workflow = assemble(plan)
    result = validate(workflow.workflow)
    out_dir = write_outputs(
        plan, workflow, result, tmp_path, "테스트 요구", "test",
        datetime(2026, 1, 1).astimezone(),
    )
    return {"dir": out_dir, "plan": plan, "workflow": workflow, "result": result}


# --------------------------------------------------------- 템플릿 라이브러리
def test_all_required_templates_exist():
    """사양의 1차 지원 노드가 전부 있어야 한다."""
    available = set(template_ids())
    missing = [t for t in REQUIRED_TEMPLATES if t not in available]
    assert missing == [], f"빠진 템플릿: {missing}"


def test_every_template_declares_type_version():
    for template in load_templates().values():
        assert template.n8n_type.startswith("n8n-nodes-base."), template.id
        assert isinstance(template.type_version, (int, float)), template.id
        assert template.type_version > 0, template.id


def test_exactly_two_trigger_templates():
    triggers = [t.id for t in load_templates().values() if t.is_trigger]
    assert sorted(triggers) == ["schedule-trigger", "webhook-trigger"]


def test_every_template_has_description_and_params():
    for template in load_templates().values():
        assert template.label and template.description, template.id
        for param in template.params:
            assert "key" in param and "label" in param, template.id


def test_unknown_template_raises():
    with pytest.raises(KeyError):
        get_template("없는-템플릿")


def test_credential_templates_have_a_setup_guide():
    """credential 이 필요한 템플릿은 설치 가이드에 안내가 있어야 한다."""
    for template in load_templates().values():
        if template.credential:
            assert template.credential in CREDENTIAL_GUIDE, (
                f"{template.id} 의 {template.credential} 안내가 없습니다"
            )


# ------------------------------------------------------------- 계획 스키마
def test_plan_rejects_duplicate_step_ids():
    payload = json.loads(json.dumps(PLANS["sheet-claude-slack"]))
    payload["steps"][1]["id"] = payload["steps"][0]["id"]
    with pytest.raises(ValidationError, match="겹칩니다"):
        Plan(**payload)


def test_plan_rejects_connection_to_unknown_step():
    payload = json.loads(json.dumps(PLANS["sheet-claude-slack"]))
    payload["connections"].append({"from": "s1", "to": "없는단계"})
    with pytest.raises(ValidationError, match="없는 단계"):
        Plan(**payload)


def test_plan_requires_at_least_one_step():
    payload = json.loads(json.dumps(PLANS["sheet-claude-slack"]))
    payload["steps"] = []
    with pytest.raises(ValidationError):
        Plan(**payload)


def test_plan_slug_is_filesystem_safe(plan):
    assert "/" not in plan.slug and " " not in plan.slug


# ------------------------------------------------------------------ 조립
def test_assemble_places_nodes_with_x_spacing(plan):
    workflow = assemble(plan)
    positions = [p.node["position"] for p in workflow.placements[:5]]
    xs = [p[0] for p in positions]
    assert xs == [250 + X_STEP * i for i in range(len(xs))]


def test_assemble_dedupes_node_names():
    payload = json.loads(json.dumps(PLANS["sheet-claude-slack"]))
    for step in payload["steps"]:
        step["name"] = "같은 이름"
    workflow = assemble(Plan(**payload))
    names = [p.name for p in workflow.placements]
    assert len(set(names)) == len(names), "이름이 겹칩니다"
    assert names[0] == "같은 이름" and names[1] == "같은 이름 2"


def test_assemble_keeps_credentials_as_placeholder_only(plan):
    """실제 키를 파일에 넣지 않는다."""
    workflow = assemble(plan)
    for placement in workflow.placements:
        credentials = placement.node.get("credentials")
        if credentials:
            for value in credentials.values():
                assert value["id"] is None
                assert "연결 필요" in value["name"]


def test_assemble_substitutes_params(plan):
    workflow = assemble(plan)
    trigger = workflow.placements[0].node
    assert trigger["parameters"]["rule"]["interval"][0]["expression"] == "0 9 * * *"


def test_assemble_preserves_param_types():
    """문자열 전체가 토큰이면 숫자를 문자열로 바꾸지 않는다."""
    payload = json.loads(json.dumps(PLANS["payment-receipt"]))
    workflow = assemble(Plan(**payload))
    wait = next(p for p in workflow.placements if p.template.id == "wait")
    assert wait.node["parameters"]["amount"] == 30
    assert isinstance(wait.node["parameters"]["amount"], int)


def test_assemble_drops_unknown_params():
    payload = json.loads(json.dumps(PLANS["sheet-claude-slack"]))
    payload["steps"][0]["params"]["엉뚱한파라미터"] = "값"
    workflow = assemble(Plan(**payload))
    assert "엉뚱한파라미터" not in workflow.placements[0].params


def test_assemble_falls_back_for_unknown_template():
    """미지원 노드는 오류 대신 HTTP Request 로 대체하고 기록한다."""
    payload = json.loads(json.dumps(PLANS["sheet-claude-slack"]))
    payload["steps"][4]["template"] = "kakao-alimtalk"
    payload["steps"][4]["name"] = "카카오 알림톡"

    workflow = assemble(Plan(**payload))

    assert workflow.placements[4].template.id == FALLBACK_TEMPLATE
    assert workflow.unsupported, "대체 사실을 기록해야 합니다"
    assert "카카오 알림톡" in workflow.unsupported[0].want
    assert workflow.notes


def test_assemble_builds_if_branches():
    workflow = assemble(_plan("webhook-triage"))
    if_node = next(p for p in workflow.placements if p.template.id == "if")
    outputs = workflow.workflow["connections"][if_node.name]["main"]
    assert len(outputs) == 2, "IF 는 참·거짓 두 갈래여야 합니다"
    assert outputs[0] and outputs[1]


def test_workflow_id_is_stable_and_right_length():
    first = workflow_id("같은 이름")
    assert first == workflow_id("같은 이름"), "같은 이름이면 같은 id 여야 합니다"
    assert len(first) == WORKFLOW_ID_LENGTH
    assert first != workflow_id("다른 이름")


def test_workflow_has_top_level_id(plan):
    """n8n CLI import 는 최상위 id 가 없으면 DB 제약에 걸려 실패한다."""
    workflow = assemble(plan)
    assert workflow.workflow["id"]
    assert len(workflow.workflow["id"]) == WORKFLOW_ID_LENGTH


def test_workflow_is_created_inactive(plan):
    assert assemble(plan).workflow["active"] is False


# ------------------------------------------------------------------ 검증
@pytest.mark.parametrize("name", list(PLANS))
def test_every_sample_plan_validates(name):
    """완료 기준: 예시 요청 5개로 모두 validator 통과."""
    result = validate(assemble(_plan(name)).workflow)
    assert result.ok, result.report()


def test_validator_catches_missing_id(plan):
    workflow = assemble(plan).workflow
    del workflow["id"]
    result = validate(workflow)
    assert not result.ok
    assert any(i.code == "missing-id" for i in result.errors)


def test_validator_catches_missing_keys():
    result = validate({"id": "x"})
    assert not result.ok
    assert any("nodes" in i.message for i in result.errors)


def test_validator_catches_dangling_connection(plan):
    workflow = assemble(plan).workflow
    first = workflow["nodes"][0]["name"]
    workflow["connections"][first]["main"][0][0]["node"] = "없는 노드"
    result = validate(workflow)
    assert any(i.code == "connection-target" for i in result.errors)


def test_validator_catches_no_trigger(plan):
    workflow = assemble(plan).workflow
    workflow["nodes"][0]["type"] = "n8n-nodes-base.set"
    result = validate(workflow)
    assert any(i.code == "no-trigger" for i in result.errors)


def test_validator_catches_two_triggers(plan):
    workflow = assemble(plan).workflow
    workflow["nodes"][1]["type"] = "n8n-nodes-base.scheduleTrigger"
    result = validate(workflow)
    assert any(i.code == "many-triggers" for i in result.errors)


def test_validator_catches_orphan_node(plan):
    workflow = assemble(plan).workflow
    orphan_name = workflow["nodes"][-1]["name"]
    for outputs in workflow["connections"].values():
        for branches in outputs.values():
            for branch in branches:
                branch[:] = [l for l in branch if l["node"] != orphan_name]
    result = validate(workflow)
    assert any(i.code == "orphan-node" for i in result.errors)


def test_validator_catches_duplicate_names(plan):
    workflow = assemble(plan).workflow
    workflow["nodes"][1]["name"] = workflow["nodes"][0]["name"]
    result = validate(workflow)
    assert any(i.code == "duplicate-name" for i in result.errors)


def test_validator_catches_bad_position(plan):
    workflow = assemble(plan).workflow
    workflow["nodes"][0]["position"] = "가운데"
    result = validate(workflow)
    assert any(i.code == "node-position" for i in result.errors)


def test_validator_warns_on_unknown_node_type(plan):
    workflow = assemble(plan).workflow
    workflow["nodes"][1]["type"] = "n8n-nodes-base.somethingNew"
    result = validate(workflow)
    assert result.ok, "모르는 타입은 경고이지 오류가 아닙니다"
    assert any(i.code == "unknown-type" for i in result.warnings)


def test_validator_rejects_non_dict():
    assert not validate("워크플로").ok


# ------------------------------------------------------------------ 생성기
def test_generator_returns_a_valid_plan():
    plan = PlanGenerator(model="test", ask_fn=fake_ask).build(
        "매일 9시에 구글시트를 읽어 Claude로 요약해 슬랙에 보내줘"
    )
    assert plan.workflow_name
    assert validate(assemble(plan).workflow).ok


def test_generator_retries_on_bad_schema():
    state = {"calls": 0}

    def broken_first(system, user, model="test", json_mode=False, **kw):
        state["calls"] += 1
        if state["calls"] == 1:
            return {"workflow_name": "깨진 계획"}  # steps 가 없다
        return fake_ask(system, user, model, json_mode)

    generator = PlanGenerator(model="test", ask_fn=broken_first)
    plan = generator.build("매일 9시에 구글시트를 읽어 슬랙에 보내줘")
    assert generator.attempts == 2
    assert plan.steps


def test_generator_gives_up_with_a_clear_message():
    def always_broken(system, user, model="test", json_mode=False, **kw):
        return {"workflow_name": "깨진 계획"}

    with pytest.raises(ValueError, match="형식이 맞지 않습니다"):
        PlanGenerator(model="test", ask_fn=always_broken).build("아무 요구")


def test_generator_prompt_lists_every_template():
    generator = PlanGenerator(model="test", ask_fn=fake_ask)
    system = generator._system()
    for template_id in template_ids():
        assert f"`{template_id}`" in system, template_id


# ------------------------------------------------------------------ 산출물
def test_all_outputs_created(built):
    for name in ("workflow.json", "plan.md", "setup_guide.md"):
        assert (built["dir"] / name).is_file(), name


def test_workflow_json_is_valid_json(built):
    workflow = json.loads((built["dir"] / "workflow.json").read_text(encoding="utf-8"))
    assert validate(workflow).ok


def test_plan_md_lists_nodes_credentials_and_params(built):
    text = (built["dir"] / "plan.md").read_text(encoding="utf-8")
    for placement in built["workflow"].placements:
        assert placement.name in text
    assert "필요한 credential" in text
    assert "노드별 파라미터" in text
    for credential in built["workflow"].credentials:
        assert credential in text


def test_plan_md_records_unsupported_fallback(tmp_path):
    """미지원 노드는 오류 대신 plan.md 에 기록되어야 한다."""
    payload = json.loads(json.dumps(PLANS["sheet-claude-slack"]))
    payload["steps"][4]["template"] = "kakao-alimtalk"
    payload["steps"][4]["name"] = "카카오 알림톡"
    plan = Plan(**payload)
    workflow = assemble(plan)
    result = validate(workflow.workflow)

    out_dir = write_outputs(plan, workflow, result, tmp_path, "요구", "test",
                            datetime(2026, 1, 1).astimezone())
    text = (out_dir / "plan.md").read_text(encoding="utf-8")

    assert "지원하지 않아 대체한 항목" in text
    assert "카카오 알림톡" in text
    assert "HTTP Request" in text
    assert result.ok, "대체했으면 검증은 통과해야 합니다"


def test_setup_guide_covers_every_step(built):
    text = (built["dir"] / "setup_guide.md").read_text(encoding="utf-8")
    for heading in ("1단계. n8n 접속", "2단계. 워크플로 가져오기",
                    "4단계. 계정 연결", "6단계. 테스트 실행", "7단계. 활성화"):
        assert heading in text, heading
    assert "docker run" in text
    assert "스크린샷 자리" in text


def test_setup_guide_has_credential_instructions(built):
    text = (built["dir"] / "setup_guide.md").read_text(encoding="utf-8")
    for credential in built["workflow"].credentials:
        label, _ = CREDENTIAL_GUIDE[credential]
        assert label in text, label


def test_test_payload_only_for_webhook(tmp_path):
    schedule_plan = _plan("sheet-claude-slack")
    workflow = assemble(schedule_plan)
    out_dir = write_outputs(schedule_plan, workflow, validate(workflow.workflow),
                            tmp_path / "a", "요구", "test",
                            datetime(2026, 1, 1).astimezone())
    assert not (out_dir / "test_payload.json").exists()

    webhook_plan = _plan("webhook-triage")
    workflow = assemble(webhook_plan)
    out_dir = write_outputs(webhook_plan, workflow, validate(workflow.workflow),
                            tmp_path / "b", "요구", "test",
                            datetime(2026, 1, 1).astimezone())
    payload = json.loads((out_dir / "test_payload.json").read_text(encoding="utf-8"))
    assert payload["_웹훅_경로"] == "inquiry"
    assert "body" in payload


def test_outputs_have_no_banned_phrases(built):
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(built["dir"].rglob("*")) if path.is_file()
    )
    assert banned_phrases.check(text) == []


# ------------------------------------------------------------------ 예시
def test_examples_file_has_five_requests():
    requests = n8n_cli.load_examples()
    assert len(requests) == 5


def test_every_example_maps_to_a_plan():
    for request in n8n_cli.load_examples():
        assert pick_plan(request) in PLANS


def test_examples_cover_both_trigger_kinds():
    kinds = set()
    for request in n8n_cli.load_examples():
        plan = Plan(**PLANS[pick_plan(request)])
        kinds.add(plan.steps[0].template)
    assert kinds == {"schedule-trigger", "webhook-trigger"}


# ------------------------------------------------------------------ push
def test_push_without_config_explains_what_to_set(monkeypatch):
    monkeypatch.delenv("N8N_URL", raising=False)
    monkeypatch.delenv("N8N_API_KEY", raising=False)
    with pytest.raises(N8nNotConfigured) as excinfo:
        n8n_config()
    assert "N8N_URL" in str(excinfo.value)
    assert "N8N_API_KEY" in str(excinfo.value)


def test_push_config_reads_env(monkeypatch):
    monkeypatch.setenv("N8N_URL", "http://localhost:5678/")
    monkeypatch.setenv("N8N_API_KEY", "key")
    assert n8n_config() == ("http://localhost:5678", "key")


# ------------------------------------------------------------------ 문서
def test_readme_has_docker_command_and_workflow():
    text = (N8N_DIR / "README.md").read_text(encoding="utf-8")
    assert "docker run" in text
    assert "5678" in text
    for name in ("workflow.json", "plan.md", "setup_guide.md", "test_payload.json"):
        assert name in text, name
    assert banned_phrases.check(text) == []


def test_product_manuals_are_detailed_and_clean():
    for name in ("admin.md", "client.md"):
        path = N8N_DIR / "docs" / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert len(text) > 4000, f"{name} 이 너무 짧습니다"
        assert banned_phrases.check(text) == []


def test_prompt_explains_the_division_of_labor():
    text = (N8N_DIR / "prompts" / "plan.md").read_text(encoding="utf-8")
    assert "하지 않는 일" in text
    assert "http-request" in text
