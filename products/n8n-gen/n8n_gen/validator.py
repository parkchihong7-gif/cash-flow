"""workflow.json 검증.

n8n 은 구조가 어긋난 워크플로를 조용히 반쯤 열거나 아예 거절한다.
납품 전에 잡는 편이 낫다.

검사 항목
    1. nodes / connections 가 있고 타입이 맞는가
    2. 노드마다 필수 키(name, type, typeVersion, position, parameters)가 있는가
    3. 노드 이름이 겹치지 않는가 (n8n 은 이름으로 연결을 찾는다)
    4. 모든 connection 의 출발·도착 노드가 실제로 있는가
    5. 트리거 노드가 정확히 1개인가
    6. 고아 노드(트리거가 아닌데 들어오는 연결이 없는 노드)가 0개인가
    7. 최상위 id 가 있는가 (n8n CLI import 가 요구한다)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from n8n_gen.nodes import load_templates  # noqa: E402

__all__ = ["validate", "ValidationResult", "Issue", "TRIGGER_TYPE_SUFFIXES"]

#: 트리거로 보는 노드 타입 접미사.
TRIGGER_TYPE_SUFFIXES = ("trigger", "webhook")

_REQUIRED_NODE_KEYS = ("name", "type", "typeVersion", "position", "parameters")


@dataclass
class Issue:
    """검사에서 걸린 항목 하나."""

    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


@dataclass
class ValidationResult:
    """검사 결과."""

    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def report(self) -> str:
        if self.ok and not self.warnings:
            return "검증 통과"
        lines = []
        for issue in self.errors:
            lines.append(f"  ✗ {issue}")
        for issue in self.warnings:
            lines.append(f"  ! {issue}")
        return "\n".join(lines)


def _is_trigger(node_type: str) -> bool:
    lowered = str(node_type).lower()
    return any(lowered.endswith(suffix) for suffix in TRIGGER_TYPE_SUFFIXES)


def validate(workflow: Any) -> ValidationResult:
    """워크플로 구조를 검사한다.

    Args:
        workflow: 파싱된 workflow.json.

    Returns:
        오류와 경고 목록.
    """
    result = ValidationResult()

    if not isinstance(workflow, dict):
        result.errors.append(Issue("not-object", "워크플로가 객체(JSON dict)가 아닙니다"))
        return result

    for key in ("nodes", "connections"):
        if key not in workflow:
            result.errors.append(Issue("missing-key", f"필수 키 '{key}' 가 없습니다"))

    # n8n CLI 의 import:workflow 는 최상위 id 가 없으면 DB 제약에 걸려 실패한다
    if not str(workflow.get("id", "")).strip():
        result.errors.append(Issue(
            "missing-id",
            "최상위 'id' 가 없습니다. n8n CLI 로 가져올 때 "
            "NOT NULL constraint failed 오류가 납니다"
        ))

    nodes = workflow.get("nodes")
    connections = workflow.get("connections")

    if not isinstance(nodes, list):
        result.errors.append(Issue("nodes-type", "'nodes' 는 리스트여야 합니다"))
        return result
    if not isinstance(connections, dict):
        result.errors.append(Issue("connections-type", "'connections' 는 객체여야 합니다"))
        return result
    if not nodes:
        result.errors.append(Issue("no-nodes", "노드가 하나도 없습니다"))
        return result

    # --- 노드 자체 ---
    names: list[str] = []
    known_types = {t.n8n_type for t in load_templates().values()}

    for index, node in enumerate(nodes):
        where = f"{index + 1}번 노드"
        if not isinstance(node, dict):
            result.errors.append(Issue("node-type", f"{where} 가 객체가 아닙니다"))
            continue
        missing = [key for key in _REQUIRED_NODE_KEYS if key not in node]
        if missing:
            result.errors.append(Issue(
                "node-missing-key",
                f"{where}({node.get('name', '이름 없음')})에 "
                f"필수 키가 없습니다: {', '.join(missing)}"
            ))
        name = node.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name)
        else:
            result.errors.append(Issue("node-name", f"{where} 의 이름이 비어 있습니다"))

        position = node.get("position")
        if not (isinstance(position, list) and len(position) == 2
                and all(isinstance(v, (int, float)) for v in position)):
            result.errors.append(Issue(
                "node-position", f"{where}({name}) 의 position 이 [x, y] 형식이 아닙니다"
            ))

        node_type = node.get("type")
        if isinstance(node_type, str) and node_type not in known_types:
            result.warnings.append(Issue(
                "unknown-type",
                f"{where}({name}) 의 타입 '{node_type}' 은 템플릿 목록에 없습니다. "
                "n8n 버전에 따라 열리지 않을 수 있습니다"
            ))

    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        result.errors.append(Issue(
            "duplicate-name",
            f"노드 이름이 겹칩니다: {', '.join(duplicates)}. "
            "n8n 은 이름으로 연결을 찾으므로 겹치면 흐름이 어긋납니다"
        ))

    name_set = set(names)

    # --- 연결 ---
    targets: set[str] = set()
    for source, outputs in connections.items():
        if source not in name_set:
            result.errors.append(Issue(
                "connection-source", f"연결의 출발 노드 '{source}' 가 nodes 에 없습니다"
            ))
        if not isinstance(outputs, dict):
            result.errors.append(Issue(
                "connection-shape", f"'{source}' 의 연결이 객체가 아닙니다"
            ))
            continue
        for _, branches in outputs.items():
            if not isinstance(branches, list):
                result.errors.append(Issue(
                    "connection-shape", f"'{source}' 의 연결 갈래가 리스트가 아닙니다"
                ))
                continue
            for branch in branches:
                if not isinstance(branch, list):
                    result.errors.append(Issue(
                        "connection-shape", f"'{source}' 의 연결 항목이 리스트가 아닙니다"
                    ))
                    continue
                for link in branch:
                    target = link.get("node") if isinstance(link, dict) else None
                    if target is None:
                        result.errors.append(Issue(
                            "connection-target", f"'{source}' 의 연결에 대상 노드가 없습니다"
                        ))
                        continue
                    if target not in name_set:
                        result.errors.append(Issue(
                            "connection-target",
                            f"'{source}' 가 없는 노드 '{target}' 를 가리킵니다"
                        ))
                    targets.add(target)

    # --- 트리거 ---
    triggers = [
        node.get("name") for node in nodes
        if isinstance(node, dict) and _is_trigger(node.get("type", ""))
    ]
    if len(triggers) == 0:
        result.errors.append(Issue(
            "no-trigger", "트리거 노드가 없습니다. 워크플로를 시작할 방법이 없습니다"
        ))
    elif len(triggers) > 1:
        result.errors.append(Issue(
            "many-triggers",
            f"트리거 노드가 {len(triggers)}개입니다: {', '.join(str(t) for t in triggers)}. "
            "정확히 1개여야 합니다"
        ))

    # --- 고아 노드 ---
    orphans = [
        node.get("name") for node in nodes
        if isinstance(node, dict)
        and not _is_trigger(node.get("type", ""))
        and node.get("name") not in targets
    ]
    if orphans:
        result.errors.append(Issue(
            "orphan-node",
            f"들어오는 연결이 없는 노드가 있습니다: {', '.join(str(o) for o in orphans)}. "
            "실행되지 않습니다"
        ))

    return result
