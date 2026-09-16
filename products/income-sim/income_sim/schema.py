"""모델 정의 읽기와 검사.

`models/*.yaml` 한 장이 부업 모델 하나다. 값(파라미터)과 계산식이 들어 있다.

**기본값에는 근거가 반드시 붙는다.** `source` 가 비면 모델을 아예 읽지 않는다.
근거 없는 기본값은 그럴듯해 보이는 만큼 위험하다. 쓰는 사람은 그 숫자가
어디서 왔는지 모른 채 그걸 기준으로 판단하게 된다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from income_sim.expr import ExpressionError, check_expression

__all__ = ["ParamSpec", "StateSpec", "Formulas", "ModelSpec", "load_model",
           "load_all", "MODELS_DIR", "MONTHS"]

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

#: 몇 달치를 계산하는가. 12개월로 고정한다.
MONTHS = 12


class ParamSpec(BaseModel):
    """사람이 넣는 값 하나."""

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    default: float
    unit: str = ""
    kind: Literal["count", "money", "rate", "hours"] = "count"
    minimum: float = 0
    maximum: float
    step: float = 1
    source: str = Field(min_length=1, description="이 기본값이 어디서 왔는지")
    help: str = ""

    #: 몬테카를로에서 흔들 폭. 0.3 이면 ±30%. 0 이면 흔들지 않는다.
    uncertain: float = Field(default=0.0, ge=0, le=0.95)

    @field_validator("source")
    @classmethod
    def _source_must_say_something(cls, value: str) -> str:
        if len(value.strip()) < 8:
            raise ValueError("근거를 한 문장으로 적어 주세요. 기본값에 근거는 필수입니다")
        return value.strip()

    @model_validator(mode="after")
    def _range_holds_default(self) -> "ParamSpec":
        if self.maximum <= self.minimum:
            raise ValueError(f"{self.key}: 최댓값이 최솟값보다 커야 합니다")
        if not (self.minimum <= self.default <= self.maximum):
            raise ValueError(
                f"{self.key}: 기본값 {self.default} 이 범위 "
                f"{self.minimum}~{self.maximum} 밖입니다")
        if self.kind == "rate" and self.maximum > 1:
            raise ValueError(f"{self.key}: 비율은 0~1 로 적습니다 (30% 는 0.3)")
        return self


class StateSpec(BaseModel):
    """달마다 이어지는 값. 고객 수처럼 지난달 결과가 이번 달에 영향을 주는 것.

    `initial` 은 1개월차 값, `next` 는 그다음 달 값이다.
    `next` 안에서 `prev` 는 지난달 값을 가리킨다.
    """

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    initial: str = Field(min_length=1)
    next: str = Field(min_length=1)
    unit: str = ""


class Formulas(BaseModel):
    revenue: str = Field(min_length=1)
    cost: str = Field(min_length=1)
    hours: str = Field(min_length=1)


class ModelSpec(BaseModel):
    """부업 모델 하나."""

    id: str = Field(min_length=1)
    number: int = Field(ge=1)
    name: str = Field(min_length=1)
    tagline: str = ""
    summary: str = ""
    params: list[ParamSpec] = Field(min_length=1)
    state: list[StateSpec] = Field(default_factory=list)
    formulas: Formulas
    #: 이 모델을 볼 때 같이 봐야 하는 것. 숫자가 말해 주지 않는 부분.
    cautions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _formulas_only_use_known_names(self) -> "ModelSpec":
        known = {p.key for p in self.params} | {s.key for s in self.state} | {"month"}
        if len(known) - 1 != len(self.params) + len(self.state):
            raise ValueError("값 이름이 겹칩니다")

        checks = [("revenue", self.formulas.revenue), ("cost", self.formulas.cost),
                  ("hours", self.formulas.hours)]
        for spec in self.state:
            checks.append((f"state.{spec.key}.initial", spec.initial))
        for spec in self.state:
            checks.append((f"state.{spec.key}.next", spec.next))

        for where, source in checks:
            allowed = known | ({"prev"} if where.endswith(".next") else set())
            try:
                used = check_expression(source)
            except ExpressionError as exc:
                raise ValueError(f"{self.id}.{where}: {exc}") from exc
            unknown = sorted(used - allowed)
            if unknown:
                raise ValueError(
                    f"{self.id}.{where}: 모르는 이름 {', '.join(unknown)}\n"
                    f"  쓸 수 있는 이름: {', '.join(sorted(allowed))}")
        return self

    @property
    def param_map(self) -> dict[str, ParamSpec]:
        return {p.key: p for p in self.params}

    def defaults(self) -> dict[str, float]:
        return {p.key: p.default for p in self.params}

    def with_overrides(self, overrides: dict[str, float]) -> dict[str, float]:
        """기본값 위에 사용자가 준 값을 얹는다. 모르는 이름은 알려 준다."""
        known = self.param_map
        unknown = sorted(set(overrides) - set(known))
        if unknown:
            raise ValueError(
                f"{self.id} 에 없는 값입니다: {', '.join(unknown)}\n"
                f"  쓸 수 있는 값: {', '.join(known)}")
        values = self.defaults()
        for key, value in overrides.items():
            spec = known[key]
            if value < 0:
                raise ValueError(f"{key}: 음수는 넣을 수 없습니다 ({value})")
            if spec.kind == "rate" and value > 1:
                raise ValueError(f"{key}: 비율은 0~1 로 넣으세요. 30% 는 0.3 입니다 ({value})")
            values[key] = float(value)
        return values


def load_model(path: Path) -> ModelSpec:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    data.setdefault("id", Path(path).stem)
    return ModelSpec(**data)


def load_all(directory: Path | None = None) -> dict[str, ModelSpec]:
    """models/ 를 전부 읽는다. 번호 순으로 돌려준다."""
    directory = Path(directory or MODELS_DIR)
    found = {}
    for path in sorted(directory.glob("*.yaml")):
        spec = load_model(path)
        if spec.id in found:
            raise ValueError(f"모델 id 가 겹칩니다: {spec.id}")
        found[spec.id] = spec

    numbers = [spec.number for spec in found.values()]
    if len(numbers) != len(set(numbers)):
        raise ValueError("모델 번호가 겹칩니다")
    return dict(sorted(found.items(), key=lambda item: item[1].number))
