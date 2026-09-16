"""service_input.yaml 스키마와 길이 제한.

크몽 입력 폼에는 글자 수 제한이 있다. 제목이 잘리면 검색에서 불리하므로
프롬프트로 부탁만 하지 않고 검사해서 강제한다.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = [
    "ServiceInput", "load_input", "truncate",
    "HEADLINE_LIMIT", "TITLE_LIMIT", "PACKAGE_TITLE_LIMIT", "PACKAGE_DESC_LIMIT",
    "TITLE_COUNT", "TAG_COUNT", "FAQ_COUNT", "SCRIPT_COUNT", "PROCESS_STEPS",
    "NO_PROOF_TEXT", "PACKAGE_TIERS",
]

#: 상세페이지 한 줄 헤드라인.
HEADLINE_LIMIT = 30
#: 크몽 서비스 제목.
TITLE_LIMIT = 25
#: 패키지 제목·설명.
PACKAGE_TITLE_LIMIT = 20
PACKAGE_DESC_LIMIT = 100

TITLE_COUNT = 10
TAG_COUNT = 20
FAQ_COUNT = 7
SCRIPT_COUNT = 8
PROCESS_STEPS = 5

#: proof 가 비었을 때 성과 자리에 넣는 문구. 수치를 지어내지 않는다.
NO_PROOF_TEXT = "사례 준비 중"

PACKAGE_TIERS = ("BASIC", "STANDARD", "PREMIUM")

_SLUG_STRIP_RE = re.compile(r"[^0-9a-z가-힣]+")


class ServiceInput(BaseModel):
    """크몽에 올릴 서비스 하나의 정보."""

    model_config = {"extra": "forbid"}

    service_name: str = Field(min_length=1, description="서비스 이름")
    category: str = Field(min_length=1, description="크몽 카테고리")
    what_you_deliver: list[str] = Field(
        min_length=2, max_length=10, description="산출물 목록 2~10개"
    )
    who_for: str = Field(min_length=1, description="누구를 위한 서비스인지 한 줄")
    differentiators: list[str] = Field(
        min_length=3, max_length=3, description="차별점 정확히 3개"
    )
    turnaround_days: int = Field(ge=1, le=90, description="기본 작업일")
    price_basic: int = Field(gt=0, description="BASIC 가격 (원)")
    price_standard: int = Field(gt=0, description="STANDARD 가격 (원)")
    price_premium: int = Field(gt=0, description="PREMIUM 가격 (원)")
    proof: list[str] = Field(
        default_factory=list,
        description="실적·후기. 비우면 성과 자리에 '사례 준비 중'이 들어간다",
    )
    faq_seed: list[str] = Field(
        default_factory=list, description="직접 넣고 싶은 FAQ 질문"
    )

    @field_validator("service_name", "category", "who_for")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("빈 값일 수 없습니다")
        return value.strip()

    @field_validator("what_you_deliver", "differentiators", "proof", "faq_seed")
    @classmethod
    def _items_not_blank(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values if item and item.strip()]
        if len(cleaned) != len(values):
            raise ValueError("빈 항목이 섞여 있습니다")
        return cleaned

    @model_validator(mode="after")
    def _prices_increase(self) -> "ServiceInput":
        prices = (self.price_basic, self.price_standard, self.price_premium)
        if not prices[0] < prices[1] < prices[2]:
            raise ValueError(
                f"가격은 BASIC < STANDARD < PREMIUM 이어야 합니다 "
                f"(현재 {prices[0]:,} / {prices[1]:,} / {prices[2]:,}원)"
            )
        return self

    @property
    def slug(self) -> str:
        normalized = unicodedata.normalize("NFC", self.service_name).lower()
        return _SLUG_STRIP_RE.sub("-", normalized).strip("-") or "service"

    @property
    def has_proof(self) -> bool:
        return bool(self.proof)

    @property
    def prices(self) -> dict[str, int]:
        return {
            "BASIC": self.price_basic,
            "STANDARD": self.price_standard,
            "PREMIUM": self.price_premium,
        }

    def price_text(self, tier: str) -> str:
        return f"{self.prices[tier]:,}원"


def load_input(path: str | Path) -> ServiceInput:
    """YAML 을 읽어 검증된 :class:`ServiceInput` 으로 돌려준다."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"입력 파일이 없습니다: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} 의 최상위는 키-값 매핑이어야 합니다")
    return ServiceInput(**raw)


def truncate(text: str, limit: int) -> str:
    """글자 수 제한에 맞춰 자른다. 마지막 안전장치."""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit].rstrip()
