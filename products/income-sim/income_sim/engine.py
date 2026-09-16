"""12개월 손익 계산.

**이 계산은 추정입니다. 실제 수익을 보장하지 않습니다.**
모든 출력 맨 위에 같은 문구가 붙습니다(`DISCLAIMER`).

손익분기를 어떻게 보는가. 두 가지를 따로 계산한다.

    월 손익분기   그달 매출이 그달 비용을 넘긴 첫 달
    누적 손익분기 초기 투자까지 다 갚고 누적이 0 을 넘긴 첫 달

둘을 합쳐 쓰면 오해가 생긴다. 매달 남는데도 초기 투자를 아직 못 갚은 상태가
흔하기 때문이다. 화면에도 두 줄로 나눠 보여 준다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from income_sim.expr import evaluate
from income_sim.schema import MONTHS, ModelSpec

__all__ = ["DISCLAIMER", "MonthRow", "Projection", "simulate"]

#: 모든 출력 맨 위에 붙는 고정 문구. 바꾸지 말 것.
DISCLAIMER = "이 계산은 추정치이며 실제 수익을 보장하지 않습니다."


@dataclass
class MonthRow:
    month: int
    revenue: float
    cost: float
    profit: float
    cumulative: float
    hours: float
    state: dict[str, float] = field(default_factory=dict)


@dataclass
class Projection:
    model: ModelSpec
    values: dict[str, float]
    rows: list[MonthRow]

    @property
    def total_revenue(self) -> float:
        return sum(row.revenue for row in self.rows)

    @property
    def total_cost(self) -> float:
        return sum(row.cost for row in self.rows)

    @property
    def total_profit(self) -> float:
        return sum(row.profit for row in self.rows)

    @property
    def total_hours(self) -> float:
        return sum(row.hours for row in self.rows)

    @property
    def initial_cost(self) -> float:
        return float(self.values.get("initial_cost", 0.0))

    @property
    def net_after_initial(self) -> float:
        """초기 투자까지 뺀 12개월 최종 잔액."""
        return self.total_profit - self.initial_cost

    @property
    def monthly_breakeven(self) -> int | None:
        """그달 매출이 그달 비용을 넘긴 첫 달. 끝내 못 넘기면 None."""
        for row in self.rows:
            if row.profit > 0:
                return row.month
        return None

    @property
    def cumulative_breakeven(self) -> int | None:
        """초기 투자까지 갚고 누적이 0 을 넘긴 첫 달. 12개월 안에 못 넘기면 None."""
        for row in self.rows:
            if row.cumulative > 0:
                return row.month
        return None

    @property
    def hourly(self) -> float | None:
        """시간당 수익. 투입 시간이 0 이면 계산할 수 없다."""
        if self.total_hours <= 0:
            return None
        return self.total_profit / self.total_hours

    @property
    def last_month_profit(self) -> float:
        return self.rows[-1].profit if self.rows else 0.0

    def as_dict(self) -> dict:
        return {
            "model": self.model.id,
            "name": self.model.name,
            "values": self.values,
            "months": [
                {"month": r.month, "revenue": r.revenue, "cost": r.cost,
                 "profit": r.profit, "cumulative": r.cumulative,
                 "hours": r.hours, "state": r.state}
                for r in self.rows
            ],
            "total_revenue": self.total_revenue,
            "total_cost": self.total_cost,
            "total_profit": self.total_profit,
            "total_hours": self.total_hours,
            "initial_cost": self.initial_cost,
            "net_after_initial": self.net_after_initial,
            "monthly_breakeven": self.monthly_breakeven,
            "cumulative_breakeven": self.cumulative_breakeven,
            "hourly": self.hourly,
            "disclaimer": DISCLAIMER,
        }


def simulate(model: ModelSpec, overrides: dict[str, float] | None = None,
             months: int = MONTHS) -> Projection:
    """모델 하나를 달별로 돌린다.

    이어지는 값(고객 수 등)은 1개월차에 `initial`, 그다음부터 `next` 로 계산한다.
    `next` 안의 `prev` 는 지난달 값이다.
    """
    values = model.with_overrides(overrides or {})
    rows: list[MonthRow] = []
    carried: dict[str, float] = {}
    cumulative = -float(values.get("initial_cost", 0.0))

    for month in range(1, months + 1):
        scope = dict(values)
        scope["month"] = float(month)

        for spec in model.state:
            if month == 1:
                carried[spec.key] = evaluate(spec.initial, scope)
            else:
                carried[spec.key] = evaluate(
                    spec.next, {**scope, "prev": carried[spec.key]})
            scope[spec.key] = carried[spec.key]

        revenue = evaluate(model.formulas.revenue, scope)
        cost = evaluate(model.formulas.cost, scope)
        hours = evaluate(model.formulas.hours, scope)
        profit = revenue - cost
        cumulative += profit

        rows.append(MonthRow(
            month=month, revenue=revenue, cost=cost, profit=profit,
            cumulative=cumulative, hours=hours, state=dict(carried),
        ))

    return Projection(model=model, values=values, rows=rows)
