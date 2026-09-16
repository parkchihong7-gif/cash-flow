"""LLM 이 내는 '계획'의 스키마.

계획은 워크플로 자체가 아니라 **어떤 템플릿을 어떻게 잇는지**만 담는다.
n8n 노드 구조는 조립기가 템플릿에서 만든다.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = ["Plan", "PlanStep", "PlanConnection", "Unsupported", "slugify"]

_SLUG_STRIP_RE = re.compile(r"[^0-9a-z가-힣]+")


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text).lower()
    return _SLUG_STRIP_RE.sub("-", normalized).strip("-")[:60] or "workflow"


class PlanStep(BaseModel):
    """워크플로의 한 단계."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, description="이 단계의 짧은 식별자 (s1, s2 ...)")
    template: str = Field(min_length=1, description="쓸 노드 템플릿 id")
    name: str = Field(min_length=1, description="n8n 화면에 보일 노드 이름")
    params: dict[str, Any] = Field(default_factory=dict, description="채울 파라미터")
    note: str = Field(default="", description="이 단계가 하는 일 한 줄")


class PlanConnection(BaseModel):
    """단계 사이의 연결."""

    model_config = {"extra": "forbid"}

    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    from_output: int = Field(default=0, ge=0, description="IF 는 0=참, 1=거짓")
    to_input: int = Field(default=0, ge=0, description="Merge 는 0 또는 1")

    model_config = {"extra": "forbid", "populate_by_name": True}


class Unsupported(BaseModel):
    """지원하지 않아 대체한 항목."""

    model_config = {"extra": "forbid"}

    want: str = Field(min_length=1, description="원래 하려던 것")
    fallback: str = Field(default="http-request", description="대신 쓴 템플릿")
    manual: str = Field(default="", description="사람이 직접 해야 하는 설정")


class Plan(BaseModel):
    """워크플로 한 벌의 계획."""

    model_config = {"extra": "forbid"}

    workflow_name: str = Field(min_length=1, description="워크플로 이름")
    summary: str = Field(default="", description="무엇을 하는 흐름인지 한 문단")
    steps: list[PlanStep] = Field(min_length=1)
    connections: list[PlanConnection] = Field(default_factory=list)
    unsupported: list[Unsupported] = Field(default_factory=list)

    @field_validator("steps")
    @classmethod
    def _unique_step_ids(cls, values: list[PlanStep]) -> list[PlanStep]:
        ids = [step.id for step in values]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"단계 id 가 겹칩니다: {', '.join(sorted(duplicates))}")
        return values

    @model_validator(mode="after")
    def _connections_point_at_known_steps(self) -> "Plan":
        known = {step.id for step in self.steps}
        for connection in self.connections:
            for side, value in (("from", connection.from_), ("to", connection.to)):
                if value not in known:
                    raise ValueError(
                        f"연결의 {side} 가 없는 단계를 가리킵니다: {value}"
                    )
        return self

    @property
    def slug(self) -> str:
        return slugify(self.workflow_name)

    def step(self, step_id: str) -> PlanStep | None:
        return next((s for s in self.steps if s.id == step_id), None)
