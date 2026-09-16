"""장부 데이터 모델.

엑셀 파일은 이 모델에서 **매번 새로 만든다**. 기존 파일을 열어 고쳐 저장하지 않는다.
openpyxl 은 파일을 읽었다 다시 쓸 때 차트를 잃어버리기 때문이다.
그래서 `import-orders` 도 기존 파일에서 데이터를 뽑아내(`reader.py`) 합친 뒤
전체를 다시 만든다. 차트·조건부 서식·유효성 검사가 모두 살아남는다.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = [
    "Settings", "Product", "Order", "Ledger",
    "STATUSES", "ACTIVE_STATUSES", "VOID_STATUSES", "PAY_METHODS",
    "STOCK_WARN", "slugify",
]

#: 배송상태. 주문 시트의 드롭다운과 순서가 같다.
STATUSES = ("대기", "발송", "완료", "취소", "환불")

#: 매출로 세지 않는 상태. 정산 시트의 '취소·환불 차감' 이 이 둘을 뺀다.
VOID_STATUSES = ("취소", "환불")

#: 매출로 세는 상태.
ACTIVE_STATUSES = tuple(s for s in STATUSES if s not in VOID_STATUSES)

#: 결제수단 드롭다운.
PAY_METHODS = ("카드", "계좌이체", "간편결제", "무통장", "기타")

#: 현재재고가 이 값보다 적으면 재고 경고. 조건부 서식과 대시보드가 같이 쓴다.
STOCK_WARN = 10


def slugify(text: str) -> str:
    """파일 이름에 쓸 수 있게 다듬는다. 한글은 그대로 둔다."""
    text = unicodedata.normalize("NFC", text).strip()
    text = re.sub(r"[\\/:*?\"<>|]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text.strip("-") or "회차"


class Settings(BaseModel):
    """[설정] 시트. 여기 값이 바뀌면 정산 시트가 전부 다시 계산된다."""

    name: str = Field(min_length=1, description="공구명")
    round_label: str = Field(default="", description="회차. 파일 이름에 들어간다")
    start: date
    end: date
    default_cost: int = Field(ge=0, description="기본 공급가")
    default_price: int = Field(gt=0, description="기본 판매가")
    shipping_fee: int = Field(default=3000, ge=0, description="건당 배송비")
    payment_fee_rate: float = Field(default=0.032, ge=0, le=1, description="결제수수료율")
    platform_fee_rate: float = Field(default=0.0, ge=0, le=1, description="플랫폼수수료율")
    vat_included: bool = Field(default=True, description="판매가에 부가세가 포함되어 있는가")
    vat_rate: float = Field(default=0.1, ge=0, le=1)

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if self.end < self.start:
            raise ValueError("종료일이 시작일보다 빠릅니다")
        if self.default_price < self.default_cost:
            raise ValueError("기본 판매가가 기본 공급가보다 낮습니다")
        if not self.round_label:
            object.__setattr__(self, "round_label", slugify(self.name))
        return self

    @property
    def margin_rate(self) -> float:
        """기본 마진율 = 1 - 공급가/판매가."""
        return 1 - self.default_cost / self.default_price

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


class Product(BaseModel):
    """[상품] 시트 한 줄."""

    code: str = Field(min_length=1)
    option: str = ""
    cost: int = Field(ge=0)
    price: int = Field(gt=0)
    initial_stock: int = Field(ge=0)

    @property
    def key(self) -> str:
        """상품코드+옵션. 정산 시트가 INDEX/MATCH 로 찾을 때 쓰는 열쇠."""
        return f"{self.code}|{self.option}"

    @model_validator(mode="after")
    def _check(self) -> "Product":
        if self.price < self.cost:
            raise ValueError(f"{self.code} 의 판매가가 공급가보다 낮습니다")
        return self


class Order(BaseModel):
    """[주문] 시트 한 줄."""

    order_date: date
    order_no: str = Field(min_length=1)
    customer: str = ""
    phone: str = ""
    code: str = Field(min_length=1)
    option: str = ""
    qty: int = Field(gt=0)
    amount: int = Field(ge=0)
    method: str = "카드"
    status: Literal["대기", "발송", "완료", "취소", "환불"] = "대기"
    invoice: str = ""
    memo: str = ""
    address: str = ""

    @field_validator("phone")
    @classmethod
    def _keep_leading_zero(cls, value: str) -> str:
        """연락처는 010 의 0 이 날아가지 않게 문자열로 다룬다."""
        return value.strip()

    @property
    def key(self) -> str:
        return f"{self.code}|{self.option}"

    @property
    def is_void(self) -> bool:
        return self.status in VOID_STATUSES


class Ledger(BaseModel):
    """엑셀 한 권 전체."""

    settings: Settings
    products: list[Product] = Field(min_length=1)
    orders: list[Order] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "Ledger":
        keys = [p.key for p in self.products]
        duplicated = {k for k in keys if keys.count(k) > 1}
        if duplicated:
            raise ValueError(f"상품코드+옵션이 겹칩니다: {', '.join(sorted(duplicated))}")

        numbers = [o.order_no for o in self.orders]
        repeated = {n for n in numbers if numbers.count(n) > 1}
        if repeated:
            raise ValueError(f"주문번호가 겹칩니다: {', '.join(sorted(repeated))}")
        return self

    @property
    def product_keys(self) -> set[str]:
        return {p.key for p in self.products}

    def unknown_order_keys(self) -> list[str]:
        """상품 시트에 없는 상품코드+옵션. 있으면 정산이 원가를 못 찾는다."""
        known = self.product_keys
        return sorted({o.key for o in self.orders if o.key not in known})

    @property
    def filename(self) -> str:
        return f"groupbuy_{slugify(self.settings.round_label)}.xlsx"
