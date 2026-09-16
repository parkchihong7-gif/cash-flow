"""계획 → n8n workflow.json 조립.

하는 일
    - 템플릿의 `parameters` 에서 `{{key}}` 토큰을 계획의 파라미터로 치환
    - 노드를 x 간격 250 으로 배치
    - 노드 이름 중복 방지 (같은 이름이면 뒤에 번호를 붙인다)
    - connections 를 n8n 형식으로 변환
    - credentials 는 이름만 placeholder 로 남긴다 (실제 키를 파일에 넣지 않는다)

모르는 템플릿이 오면 오류를 내지 않고 HTTP Request 로 대체하고 그 사실을 기록한다.
납품 현장에서 "지원 안 함"으로 멈추는 것보다 대체안을 주는 쪽이 쓸모 있다.
"""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from n8n_gen.nodes import (  # noqa: E402
    FALLBACK_TEMPLATE, NodeTemplate, get_template, load_templates,
)
from n8n_gen.schema import Plan, PlanStep, Unsupported  # noqa: E402

__all__ = [
    "assemble", "AssembledWorkflow", "NodePlacement", "workflow_id",
    "X_STEP", "Y_BASE", "WORKFLOW_ID_LENGTH",
]

#: 노드 사이 가로 간격.
X_STEP = 250
#: 첫 줄 y 좌표.
Y_BASE = 300
#: 한 줄에 놓을 최대 노드 수. 넘으면 아래 줄로 접는다.
ROW_LIMIT = 6
#: 줄 간 세로 간격.
Y_STEP = 200

#: n8n 워크플로 id 길이. n8n 은 16자 nanoid 를 쓴다.
WORKFLOW_ID_LENGTH = 16
#: id 에 쓰는 글자. n8n nanoid 와 같은 집합.
_ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

_TOKEN_RE = re.compile(r"\{\{(\w+)\}\}")
#: 문자열 전체가 토큰 하나인 경우 — 값의 타입을 그대로 살린다.
_WHOLE_TOKEN_RE = re.compile(r"^\{\{(\w+)\}\}$")


@dataclass
class NodePlacement:
    """조립된 노드 하나와 그 출처."""

    step_id: str
    name: str
    template: NodeTemplate
    params: dict[str, Any]
    node: dict[str, Any]


@dataclass
class AssembledWorkflow:
    """조립 결과."""

    workflow: dict[str, Any]
    placements: list[NodePlacement]
    unsupported: list[Unsupported] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def credentials(self) -> list[str]:
        """필요한 credential 종류 (중복 제거, 정렬)."""
        return sorted({
            placement.template.credential
            for placement in self.placements
            if placement.template.credential
        })

    def placement(self, step_id: str) -> NodePlacement | None:
        return next((p for p in self.placements if p.step_id == step_id), None)


def workflow_id(name: str) -> str:
    """워크플로 이름에서 16자 id 를 만든다.

    n8n CLI 의 `import:workflow` 는 최상위 `id` 가 없으면
    `NOT NULL constraint failed: workflow_entity.id` 로 실패한다.
    (화면에서 Import from File 로 가져올 때는 n8n 이 직접 만들어 준다.)

    같은 이름이면 같은 id 가 나오게 해서 다시 가져올 때 중복 생성 대신
    같은 워크플로를 갱신하도록 한다.
    """
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    base = len(_ID_ALPHABET)
    return "".join(
        _ID_ALPHABET[digest[i] % base] for i in range(WORKFLOW_ID_LENGTH)
    )


def _substitute(value: Any, params: dict[str, Any]) -> Any:
    """`{{key}}` 토큰을 치환한다.

    문자열 전체가 토큰 하나면 값의 타입을 그대로 쓴다 (숫자를 문자열로 만들지 않는다).
    문자열 안에 섞여 있으면 문자열로 이어 붙인다.
    """
    if isinstance(value, str):
        whole = _WHOLE_TOKEN_RE.match(value)
        if whole:
            key = whole.group(1)
            return params.get(key, value)
        return _TOKEN_RE.sub(
            lambda m: str(params.get(m.group(1), m.group(0))), value
        )
    if isinstance(value, dict):
        return {key: _substitute(item, params) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute(item, params) for item in value]
    return value


def _unique_name(name: str, used: set[str]) -> str:
    """노드 이름이 겹치면 뒤에 번호를 붙인다. n8n 은 이름으로 연결을 찾는다."""
    name = " ".join(str(name).split()) or "노드"
    if name not in used:
        used.add(name)
        return name
    index = 2
    while f"{name} {index}" in used:
        index += 1
    unique = f"{name} {index}"
    used.add(unique)
    return unique


def _resolve_template(step: PlanStep, unsupported: list[Unsupported],
                      notes: list[str]) -> NodeTemplate:
    """템플릿을 찾는다. 없으면 HTTP Request 로 대체하고 기록한다."""
    try:
        return get_template(step.template)
    except KeyError:
        notes.append(
            f"'{step.template}' 템플릿이 없어 HTTP Request 로 대체했습니다 "
            f"({step.name})."
        )
        unsupported.append(Unsupported(
            want=f"{step.name} ({step.template})",
            fallback=FALLBACK_TEMPLATE,
            manual="HTTP Request 노드의 URL·헤더·본문을 직접 채워야 합니다. "
                   "해당 서비스의 API 문서를 보고 설정하세요.",
        ))
        return get_template(FALLBACK_TEMPLATE)


def _build_node(step: PlanStep, template: NodeTemplate, name: str,
                position: list[int]) -> tuple[dict[str, Any], dict[str, Any]]:
    """노드 하나를 만든다. (노드, 실제 쓰인 파라미터) 를 돌려준다."""
    params = {**template.defaults()}
    # 템플릿이 모르는 파라미터는 버린다. 엉뚱한 값이 섞여 들어가는 것을 막는다.
    params.update({
        key: value for key, value in step.params.items()
        if key in template.param_keys
    })

    node: dict[str, Any] = {
        "parameters": _substitute(template.parameters, params),
        "id": f"{step.id}-{template.id}",
        "name": name,
        "type": template.n8n_type,
        "typeVersion": template.type_version,
        "position": position,
    }
    if template.credential:
        # 실제 키는 넣지 않는다. n8n 에서 연결할 자리만 만든다.
        node["credentials"] = {
            template.credential: {"id": None, "name": f"[{template.credential} 연결 필요]"}
        }
    return node, params


def assemble(plan: Plan) -> AssembledWorkflow:
    """계획을 n8n 워크플로 JSON 으로 조립한다."""
    load_templates()  # 템플릿이 깨졌으면 여기서 바로 알린다

    unsupported: list[Unsupported] = list(plan.unsupported)
    notes: list[str] = []
    used_names: set[str] = set()
    placements: list[NodePlacement] = []

    for index, step in enumerate(plan.steps):
        template = _resolve_template(step, unsupported, notes)
        name = _unique_name(step.name, used_names)
        row, column = divmod(index, ROW_LIMIT)
        position = [X_STEP * column + 250, Y_BASE + Y_STEP * row]
        node, params = _build_node(step, template, name, position)
        placements.append(NodePlacement(
            step_id=step.id, name=name, template=template, params=params, node=node
        ))

    by_step = {placement.step_id: placement for placement in placements}
    connections: dict[str, Any] = {}

    for connection in plan.connections:
        source = by_step.get(connection.from_)
        target = by_step.get(connection.to)
        if source is None or target is None:
            # 스키마에서 걸러지지만 방어적으로 둔다
            notes.append(f"연결을 건너뛰었습니다: {connection.from_} → {connection.to}")
            continue

        outputs = connections.setdefault(source.name, {}).setdefault("main", [])
        while len(outputs) <= connection.from_output:
            outputs.append([])
        outputs[connection.from_output].append({
            "node": target.name, "type": "main", "index": connection.to_input,
        })

    workflow = {
        "id": workflow_id(plan.workflow_name),
        "name": plan.workflow_name,
        "nodes": [placement.node for placement in placements],
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1"},
        "pinData": {},
        "meta": {"instanceId": "generated-by-n8n-gen"},
        "tags": [],
    }
    return AssembledWorkflow(
        workflow=workflow, placements=placements,
        unsupported=unsupported, notes=notes,
    )
