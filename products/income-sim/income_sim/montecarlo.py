"""값을 흔들어 보는 계산.

기본값 하나로 나온 숫자는 "이대로 되면" 이라는 가정 위에 있다.
조회수나 전환율은 원래 크게 흔들리므로, 그 흔들림을 같이 보여 주는 편이
판단에 도움이 된다.

흔드는 방법은 **삼각분포**를 쓴다. 가장 그럴듯한 값이 가운데(기본값)이고
양쪽으로 갈수록 덜 그럴듯하다는 뜻이다. 정규분포보다 설명하기 쉽고,
"최소·보통·최대" 라는 사람의 어림과 모양이 같다.

흔들 값과 폭은 모델 파일의 `uncertain` 이 정한다. 0 이면 흔들지 않는다.
같은 `--seed` 를 주면 결과가 항상 같다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from income_sim.engine import Projection, simulate
from income_sim.schema import ModelSpec

__all__ = ["Percentiles", "MonteCarloResult", "run_montecarlo", "percentile"]


def percentile(sorted_values: list[float], fraction: float) -> float:
    """정렬된 값에서 백분위를 뽑는다 (선형 보간)."""
    if not sorted_values:
        raise ValueError("값이 없습니다")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = fraction * (len(sorted_values) - 1)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    weight = position - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


@dataclass
class Percentiles:
    p10: float
    p50: float
    p90: float

    @classmethod
    def of(cls, values: list[float]) -> "Percentiles":
        ordered = sorted(values)
        return cls(p10=percentile(ordered, 0.10),
                   p50=percentile(ordered, 0.50),
                   p90=percentile(ordered, 0.90))


@dataclass
class MonteCarloResult:
    model: ModelSpec
    runs: int
    seed: int
    shaken: list[str]
    net: Percentiles
    hourly: Percentiles
    loss_rate: float
    base: Projection

    def as_dict(self) -> dict:
        return {
            "model": self.model.id, "runs": self.runs, "seed": self.seed,
            "shaken": self.shaken,
            "net": vars(self.net), "hourly": vars(self.hourly),
            "loss_rate": self.loss_rate,
        }


def run_montecarlo(model: ModelSpec, overrides: dict[str, float] | None = None,
                   runs: int = 1000, seed: int = 20260916) -> MonteCarloResult:
    """값을 흔들어 여러 번 돌린다."""
    if runs < 1:
        raise ValueError("--n 은 1 이상이어야 합니다")

    base_values = model.with_overrides(overrides or {})
    shaken = [p.key for p in model.params if p.uncertain > 0]
    if not shaken:
        raise ValueError(
            f"{model.id} 에는 흔들 값이 없습니다. "
            "모델 파일의 params 에 uncertain 을 적어야 합니다")

    rng = random.Random(seed)
    spread = {p.key: p.uncertain for p in model.params if p.uncertain > 0}
    limits = {p.key: (p.minimum, p.maximum) for p in model.params}

    nets: list[float] = []
    hourlies: list[float] = []

    for _ in range(runs):
        trial = dict(base_values)
        for key, ratio in spread.items():
            factor = rng.triangular(1 - ratio, 1 + ratio, 1.0)
            low, high = limits[key]
            trial[key] = min(high, max(low, base_values[key] * factor))

        projection = simulate(model, trial)
        nets.append(projection.net_after_initial)
        if projection.hourly is not None:
            hourlies.append(projection.hourly)

    losses = sum(1 for value in nets if value < 0)
    return MonteCarloResult(
        model=model, runs=runs, seed=seed, shaken=shaken,
        net=Percentiles.of(nets),
        hourly=Percentiles.of(hourlies or [0.0]),
        loss_rate=losses / len(nets),
        base=simulate(model, base_values),
    )
