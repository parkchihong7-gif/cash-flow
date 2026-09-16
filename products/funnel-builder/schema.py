"""funnel_input.yaml 스키마와 검증."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

__all__ = ["FunnelInput", "load_input"]

_SLUG_STRIP_RE = re.compile(r"[^0-9a-z가-힣]+")


class FunnelInput(BaseModel):
    """퍼널 한 건을 만드는 데 필요한 입력 5종."""

    model_config = {"extra": "forbid"}

    product_name: str = Field(min_length=1, description="상품명")
    target: str = Field(min_length=1, description="한 줄 페르소나")
    price: int = Field(gt=0, description="판매가 (원)")
    core_promise: str = Field(min_length=1, description="한 줄 핵심 약속")
    lead_magnet_title: str = Field(min_length=1, description="무료 리드매그넷 제목")
    pain_points: list[str] = Field(min_length=3, max_length=5, description="고객의 통증 3~5개")
    proof: list[str] = Field(default_factory=list, description="실적·후기. 없으면 빈 리스트")
    cta_url: str = Field(min_length=1, description="결제/신청 링크")
    sender_name: str = Field(min_length=1, description="이메일 발신자 이름")

    @field_validator("product_name", "target", "core_promise", "lead_magnet_title", "sender_name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("빈 값일 수 없습니다")
        return value.strip()

    @field_validator("pain_points", "proof")
    @classmethod
    def _items_not_blank(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values if item and item.strip()]
        if len(cleaned) != len(values):
            raise ValueError("빈 항목이 섞여 있습니다")
        return cleaned

    @field_validator("cta_url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("cta_url 은 http:// 또는 https:// 로 시작해야 합니다")
        return value

    @property
    def slug(self) -> str:
        """산출물 폴더 이름. 한글은 그대로 두고 공백·기호만 하이픈으로 바꾼다."""
        normalized = unicodedata.normalize("NFC", self.product_name).lower()
        slug = _SLUG_STRIP_RE.sub("-", normalized).strip("-")
        return slug or "funnel"

    @property
    def price_text(self) -> str:
        """1,200,000원 형태."""
        return f"{self.price:,}원"


def load_input(path: str | Path) -> FunnelInput:
    """YAML 을 읽어 검증된 :class:`FunnelInput` 으로 돌려준다.

    Raises:
        FileNotFoundError: 파일이 없을 때.
        ValueError: YAML 이 매핑이 아닐 때.
        pydantic.ValidationError: 필드 검증에 실패했을 때.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"입력 파일이 없습니다: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} 의 최상위는 키-값 매핑이어야 합니다")
    return FunnelInput(**raw)
