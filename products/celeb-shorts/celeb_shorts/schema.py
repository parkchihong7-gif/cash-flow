"""입력과 기획서의 모양.

입력은 사람이 채우는 `shorts_input.yaml`, 기획서는 Claude 가 돌려주는 JSON 이다.
둘 다 여기서 검사하고, 규칙 검사(얼굴 금지·출처·가격)는 `rules.py` 가 맡는다.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

__all__ = ["Item", "ShortsInput", "Scene", "PlanDraft", "parse_item", "slugify", "VISUALS"]

#: 장면 화면으로 쓸 수 있는 것. 연예인 얼굴·방송 화면은 여기 없다 — 일부러다.
VISUALS: dict[str, str] = {
    "product_image": "쇼핑몰·브랜드가 제공하는 상품 이미지",
    "own_photo": "직접 찍은 상품 사진",
    "text_card": "글자만 있는 화면(배경색 + 큰 자막)",
}

Visual = Literal["product_image", "own_photo", "text_card"]

_YES = {"o", "y", "yes", "true", "1", "확인", "예", "ㅇ"}


class Item(BaseModel):
    """아이템 하나."""

    name: str = Field(min_length=1)
    brand: str = ""
    confirmed: bool = Field(default=False, description="출처에서 착용·사용이 확인된 아이템인가")
    price: int | None = Field(default=None, ge=0)
    price_source: str = ""
    keyword: str = Field(default="", description="쇼핑 검색어. 비우면 이름을 쓴다")

    @property
    def search_keyword(self) -> str:
        return (self.keyword or self.name).strip()


def parse_item(raw: str | dict) -> Item:
    """`이름 | 브랜드 | o | 가격 | 가격 출처 | 검색어` 한 줄 또는 dict 를 Item 으로."""
    if isinstance(raw, dict):
        return Item(**raw)
    cells = [cell.strip() for cell in str(raw).split("|")]
    cells += [""] * (6 - len(cells))
    name, brand, ok, price, price_source, keyword = cells[:6]
    digits = re.sub(r"[^\d]", "", price)
    return Item(
        name=name, brand=brand, confirmed=ok.lower() in _YES,
        price=int(digits) if digits else None,
        price_source=price_source, keyword=keyword,
    )


class ShortsInput(BaseModel):
    """`shorts_input.yaml` 한 장."""

    celebrity: str = ""
    occasion: str = ""
    source_url: str = ""
    source_name: str = ""
    duration_sec: int = Field(default=15, ge=10, le=60)
    items: list[Item] = Field(min_length=1)
    cta: str = "고정 상품 태그에서 비슷한 제품 보기"

    @field_validator("items", mode="before")
    @classmethod
    def _parse_items(cls, value):
        if not value:
            return []
        return [parse_item(raw) if not isinstance(raw, Item) else raw for raw in value]

    @field_validator("source_url")
    @classmethod
    def _url(cls, value: str) -> str:
        value = (value or "").strip()
        if value and not re.match(r"^https?://", value):
            raise ValueError("출처 주소는 http:// 나 https:// 로 시작해야 합니다")
        return value

    @property
    def has_source(self) -> bool:
        return bool(self.source_url)

    @property
    def max_items(self) -> int:
        return 3 if self.duration_sec <= 30 else 5


class Scene(BaseModel):
    """장면 하나 — 자막 한 장."""

    start: float = Field(ge=0)
    end: float = Field(gt=0)
    subtitle: str = Field(min_length=1)
    narration: str = ""
    visual: Visual = "text_card"
    item_index: int | None = Field(default=None, description="몇 번째 아이템을 보여 주나(0부터)")


class PlanDraft(BaseModel):
    """Claude 가 돌려주는 기획 초안."""

    title: str = Field(min_length=1)
    hook: str = Field(min_length=1, description="첫 2초 큰 자막")
    scenes: list[Scene] = Field(min_length=2)
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)


def slugify(text: str, fallback: str = "shorts") -> str:
    """폴더 이름. 한글은 두고 나머지 기호만 정리한다."""
    slug = re.sub(r"[^\w가-힣]+", "-", text or "").strip("-").lower()
    return slug[:40] or fallback
