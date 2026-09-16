"""노드 템플릿 라이브러리.

n8n 노드 파라미터 구조는 LLM 에 맡기지 않는다. 틀린 구조를 만들면 import 자체가
실패하기 때문이다. 검증된 템플릿을 `templates/nodes/*.json` 에 두고,
LLM 은 **어떤 템플릿을 어떤 순서로 연결하고 파라미터를 무엇으로 채울지**만 정한다.

미지원 서비스는 오류를 내지 않고 :data:`FALLBACK_TEMPLATE` (HTTP Request) 로
대체하고 그 사실을 계획에 남긴다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "NodeTemplate", "load_templates", "get_template", "template_ids",
    "catalog_text", "FALLBACK_TEMPLATE", "TEMPLATES_DIR",
]

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = BASE_DIR / "templates" / "nodes"

#: 지원하지 않는 서비스를 만났을 때 대신 쓰는 템플릿.
FALLBACK_TEMPLATE = "http-request"


@dataclass(frozen=True)
class NodeTemplate:
    """노드 템플릿 하나."""

    id: str
    label: str
    category: str
    description: str
    n8n_type: str
    type_version: float
    is_trigger: bool
    credential: str | None
    params: tuple[dict[str, Any], ...]
    parameters: dict[str, Any]
    outputs: tuple[str, ...]
    inputs: int

    @property
    def param_keys(self) -> tuple[str, ...]:
        return tuple(str(p["key"]) for p in self.params)

    def defaults(self) -> dict[str, Any]:
        return {str(p["key"]): p.get("default") for p in self.params}

    def param_label(self, key: str) -> str:
        for param in self.params:
            if param["key"] == key:
                return str(param.get("label", key))
        return key


def _load_one(path: Path) -> NodeTemplate:
    raw = json.loads(path.read_text(encoding="utf-8"))
    missing = [
        key for key in
        ("id", "label", "category", "description", "n8n_type", "type_version",
         "is_trigger", "params", "parameters")
        if key not in raw
    ]
    if missing:
        raise ValueError(f"{path.name} 에 필수 키가 없습니다: {', '.join(missing)}")
    return NodeTemplate(
        id=raw["id"], label=raw["label"], category=raw["category"],
        description=raw["description"], n8n_type=raw["n8n_type"],
        type_version=raw["type_version"], is_trigger=bool(raw["is_trigger"]),
        credential=raw.get("credential"), params=tuple(raw["params"]),
        parameters=raw["parameters"],
        outputs=tuple(raw.get("outputs", ["main"])),
        inputs=int(raw.get("inputs", 0 if raw["is_trigger"] else 1)),
    )


@lru_cache(maxsize=1)
def load_templates() -> dict[str, NodeTemplate]:
    """`templates/nodes/*.json` 을 전부 읽는다."""
    if not TEMPLATES_DIR.is_dir():
        raise FileNotFoundError(f"템플릿 폴더가 없습니다: {TEMPLATES_DIR}")
    templates = {}
    for path in sorted(TEMPLATES_DIR.glob("*.json")):
        template = _load_one(path)
        if template.id in templates:
            raise ValueError(f"템플릿 id 가 겹칩니다: {template.id}")
        templates[template.id] = template
    if not templates:
        raise FileNotFoundError(f"{TEMPLATES_DIR} 에 템플릿이 없습니다")
    return templates


def get_template(template_id: str) -> NodeTemplate:
    """id 로 템플릿을 찾는다.

    Raises:
        KeyError: 없는 id 일 때. 호출하는 쪽에서 대체 템플릿으로 넘긴다.
    """
    templates = load_templates()
    if template_id not in templates:
        raise KeyError(template_id)
    return templates[template_id]


def template_ids() -> list[str]:
    return list(load_templates())


def catalog_text() -> str:
    """LLM 프롬프트에 넣을 템플릿 목록."""
    lines = []
    for template in load_templates().values():
        params = ", ".join(
            f"{p['key']}({p.get('label', '')})" for p in template.params
        ) or "없음"
        kind = "트리거" if template.is_trigger else template.category
        lines.append(
            f"- `{template.id}` [{kind}] {template.label} — {template.description}\n"
            f"  파라미터: {params}"
        )
    return "\n".join(lines)
