"""모델끼리 견주기.

**같은 시간을 넣으면 어느 쪽이 나은가**가 이 표가 답하려는 질문이다.
그래서 정렬 기준은 12개월 손익이 아니라 **시간당 수익**이다.
손익이 큰 쪽이 시간을 네 배 쓰고 있으면 더 나은 선택이 아니기 때문이다.

'환산' 칸은 시간당 수익에 시간을 곱한 단순 비례값이다. 참고용으로만 보아야 한다.
- 고정비는 시간을 줄여도 줄지 않는다.
- 시간을 두 배 넣는다고 조회수가 두 배가 되지 않는다.
- 혼자 할 수 있는 양에는 한계가 있다.
"""

from __future__ import annotations

from dataclasses import dataclass

from income_sim.engine import Projection, simulate
from income_sim.schema import ModelSpec

__all__ = ["ComparisonRow", "compare_models", "DEFAULT_BUDGET"]

#: 환산 기준 시간(월). 주말 이틀 × 5시간 정도를 부업의 현실적인 상한으로 잡았다.
DEFAULT_BUDGET = 40.0


@dataclass
class ComparisonRow:
    projection: Projection
    scaled_monthly_profit: float | None

    @property
    def model(self) -> ModelSpec:
        return self.projection.model

    @property
    def monthly_hours(self) -> float:
        rows = self.projection.rows
        return self.projection.total_hours / max(1, len(rows))


def compare_models(models: list[ModelSpec], budget_hours: float = DEFAULT_BUDGET,
                   overrides: dict[str, dict[str, float]] | None = None,
                   ) -> list[ComparisonRow]:
    """시간당 수익이 높은 순으로 돌려준다."""
    if budget_hours <= 0:
        raise ValueError("--hours 는 0보다 커야 합니다")

    overrides = overrides or {}
    rows = []
    for model in models:
        projection = simulate(model, overrides.get(model.id))
        hourly = projection.hourly
        scaled = None if hourly is None else hourly * budget_hours
        rows.append(ComparisonRow(projection=projection, scaled_monthly_profit=scaled))

    rows.sort(key=lambda row: (row.projection.hourly is None,
                               -(row.projection.hourly or 0)))
    return rows
