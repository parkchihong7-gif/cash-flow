"""엑셀과 **따로** 계산하는 파이썬 정산기.

두 가지에 쓴다.

1. 리포트 — 숫자를 여기서 가져온다(엑셀 재계산이 가능하면 그 값을 먼저 쓴다).
2. 검증 — 테스트가 엑셀 재계산 결과와 이 값을 맞춰 본다.
   두 계산이 독립적이어야 검증에 뜻이 있으므로, 엑셀 수식 문자열을
   그대로 흉내 내지 않고 정의대로 다시 계산한다.

엑셀 `ROUND` 는 0.5 를 **0 에서 먼 쪽으로** 올린다. 파이썬 `round` 는
짝수로 붙이므로(banker's rounding) 그대로 쓰면 1원씩 어긋난다.
`excel_round()` 가 이 차이를 맞춘다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from groupbuy_ledger.schema import STOCK_WARN, VOID_STATUSES, Ledger

__all__ = ["excel_round", "Totals", "ProductResult", "DayResult", "compute"]


def excel_round(value: float, digits: int = 0) -> float:
    """엑셀 ROUND 와 같은 반올림 (0.5 는 0 에서 먼 쪽으로)."""
    quantum = Decimal(1).scaleb(-digits)
    rounded = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    return float(rounded)


@dataclass
class ProductResult:
    code: str
    option: str
    sold: int
    revenue: int
    voided: int
    cost: int
    profit: int
    margin: float | None
    stock: int
    rank: int

    @property
    def label(self) -> str:
        return f"{self.code} {self.option}".strip()

    @property
    def low_stock(self) -> bool:
        return self.stock < STOCK_WARN


@dataclass
class DayResult:
    day: date
    revenue: int
    orders: int


@dataclass
class Totals:
    """정산 시트 요약 블록과 같은 값."""

    gross: float = 0.0
    void: float = 0.0
    net: float = 0.0
    payment_fee: float = 0.0
    platform_fee: float = 0.0
    cost: float = 0.0
    shipping: float = 0.0
    vat: float = 0.0
    profit: float = 0.0
    margin: float | None = None
    orders: int = 0
    void_orders: int = 0
    active_orders: int = 0
    refund_rate: float | None = None
    waiting: int = 0
    avg_order: float | None = None

    products: list[ProductResult] = field(default_factory=list)
    days: list[DayResult] = field(default_factory=list)

    def as_summary(self) -> dict[str, float | int | None]:
        """정산 시트의 항목 열쇠와 같은 이름으로 돌려준다. 검증이 이걸 비교한다."""
        return {
            "gross": self.gross, "void": self.void, "net": self.net,
            "payment_fee": self.payment_fee, "platform_fee": self.platform_fee,
            "cost": self.cost, "shipping": self.shipping, "vat": self.vat,
            "profit": self.profit, "margin": self.margin,
            "orders": self.orders, "void_orders": self.void_orders,
            "active_orders": self.active_orders, "refund_rate": self.refund_rate,
            "waiting": self.waiting, "avg_order": self.avg_order,
        }

    @property
    def best_seller(self) -> ProductResult | None:
        """가장 많이 팔린 옵션. 판매가 0이면 없음."""
        sold = [p for p in self.products if p.sold > 0]
        return max(sold, key=lambda p: p.sold) if sold else None

    @property
    def low_stock_products(self) -> list[ProductResult]:
        return [p for p in self.products if p.code and p.low_stock]


def compute(ledger: Ledger) -> Totals:
    """장부 하나를 통째로 계산한다."""
    settings = ledger.settings
    orders = ledger.orders
    live = [o for o in orders if not o.is_void]
    dead = [o for o in orders if o.is_void]

    totals = Totals()
    totals.gross = float(sum(o.amount for o in orders))
    totals.void = float(sum(o.amount for o in dead))
    totals.net = totals.gross - totals.void

    totals.orders = len(orders)
    totals.void_orders = len(dead)
    totals.active_orders = totals.orders - totals.void_orders
    totals.waiting = sum(1 for o in orders if o.status == "대기")
    totals.refund_rate = (totals.void_orders / totals.orders) if totals.orders else None

    # 상품별 — 취소·환불은 수량에서도 금액에서도 뺀다
    results: list[ProductResult] = []
    for product in ledger.products:
        mine = [o for o in orders if o.key == product.key]
        sold = sum(o.qty for o in mine if not o.is_void)
        revenue = sum(o.amount for o in mine if not o.is_void)
        voided = sum(o.amount for o in mine if o.is_void)
        cost = sold * product.cost
        profit = revenue - cost
        results.append(ProductResult(
            code=product.code, option=product.option, sold=sold,
            revenue=revenue, voided=voided, cost=cost, profit=profit,
            margin=(profit / revenue) if revenue else None,
            stock=product.initial_stock - sold, rank=0,
        ))

    # 순위 — 이익이 같으면 위에 있는 줄이 앞 순위. 엑셀의 RANK+COUNTIFS 와 같은 규칙
    for index, result in enumerate(results):
        higher = sum(1 for other in results if other.profit > result.profit)
        tied_above = sum(1 for other in results[:index] if other.profit == result.profit)
        result.rank = higher + tied_above + 1
    totals.products = results

    totals.cost = float(sum(r.cost for r in results))
    totals.payment_fee = excel_round(totals.net * settings.payment_fee_rate)
    totals.platform_fee = excel_round(totals.net * settings.platform_fee_rate)
    totals.shipping = float(totals.active_orders * settings.shipping_fee)
    totals.vat = (
        excel_round(totals.net / (1 + settings.vat_rate) * settings.vat_rate)
        if settings.vat_included else 0.0
    )
    totals.profit = (totals.net - totals.payment_fee - totals.platform_fee
                     - totals.cost - totals.shipping - totals.vat)
    totals.margin = (totals.profit / totals.net) if totals.net else None
    totals.avg_order = (totals.net / totals.active_orders) if totals.active_orders else None

    # 일별 — 취소·환불을 뺀 매출. 주문 건수는 취소 포함(들어온 건수 자체)
    for offset in range(settings.days):
        day = settings.start + timedelta(days=offset)
        same_day = [o for o in orders if o.order_date == day]
        totals.days.append(DayResult(
            day=day,
            revenue=sum(o.amount for o in same_day if not o.is_void),
            orders=len(same_day),
        ))

    _ = live  # 가독성을 위해 위에서 갈라 두었다
    return totals
