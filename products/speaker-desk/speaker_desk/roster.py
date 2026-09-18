"""연사 명부 — 한 사람에 대해 챙겨야 하는 것들.

해외 연사 초청이 국내 연사와 다른 점은 **되돌릴 수 없는 일정이 많다**는 것이다.
비자는 신청해 놓고 기다려야 하고, 항공권은 바꾸면 돈이 들고, 원천징수는
지급하고 나면 되돌리기가 번거롭다.

그래서 이 명부는 **언제까지 무엇을 해야 하는지**를 계산하는 데 필요한 값만
담는다. 자세한 연락 이력 같은 것은 담지 않는다. 그건 CRM 이 할 일이다.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = ["Speaker", "Event", "load_event", "RosterError", "FEE_BASIS"]

FEE_BASIS = ("gross", "net")


class RosterError(ValueError):
    """명부를 읽지 못했을 때."""


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value).strip())


class Speaker(BaseModel):
    """연사 한 명."""

    model_config = {"extra": "forbid"}

    name: str
    country: str = Field(description="거주국. 조세조약과 비자 판단에 씁니다")
    affiliation: str = ""
    email: str = ""

    fee_krw: int = Field(default=0, ge=0, description="강연료. 0이면 무보수")
    fee_basis: str = Field(default="gross", description="gross 면 여기서 세금을 뗍니다")
    treaty_rate: float | None = Field(
        default=None,
        description="조세조약 제한세율(0~1). 비워 두면 기본 22% 로 잡습니다")
    expenses_only: bool = Field(
        default=False, description="대가 없이 항공·숙박 실비만 지원하는가")

    visa_waiver: bool = Field(
        default=False, description="사증면제·무사증 입국 대상국인가")
    arrival: date | None = None
    departure: date | None = None

    airfare_krw: int = Field(default=0, ge=0)
    hotel_krw: int = Field(default=0, ge=0)
    other_krw: int = Field(default=0, ge=0)

    utc_offset: float = Field(default=0.0, description="연사 현지 UTC 오프셋. 예: -5")
    needs_interpreter: bool = False
    session_title: str = ""

    @field_validator("fee_basis")
    @classmethod
    def _known_basis(cls, value: str) -> str:
        text = (value or "gross").strip().lower()
        if text not in FEE_BASIS:
            raise ValueError(f"fee_basis 는 {' 또는 '.join(FEE_BASIS)} 여야 합니다")
        return text

    @field_validator("arrival", "departure", mode="before")
    @classmethod
    def _parse_date(cls, value):
        return _as_date(value) if value else None

    @field_validator("treaty_rate")
    @classmethod
    def _rate_range(cls, value):
        if value is not None and not 0 <= float(value) < 1:
            raise ValueError("treaty_rate 는 0 이상 1 미만이어야 합니다")
        return value

    @model_validator(mode="after")
    def _dates_make_sense(self) -> "Speaker":
        if self.arrival and self.departure and self.departure < self.arrival:
            raise ValueError(f"{self.name}: 출국일이 입국일보다 빠릅니다")
        if self.fee_krw > 0 and self.expenses_only:
            raise ValueError(
                f"{self.name}: 강연료가 있는데 expenses_only 가 켜져 있습니다. "
                f"비자 판단이 달라지는 값이라 둘 다일 수 없습니다")
        return self

    @property
    def paid(self) -> bool:
        return self.fee_krw > 0

    @property
    def stay_days(self) -> int:
        if not (self.arrival and self.departure):
            return 0
        return (self.departure - self.arrival).days + 1

    @property
    def time_gap(self) -> float:
        """한국(UTC+9)과의 시차."""
        return round(9.0 - self.utc_offset, 1)

    @property
    def jetlag_note(self) -> str:
        gap = abs(self.time_gap)
        if gap >= 10:
            return (f"시차 {gap:g}시간. 도착 다음 날 오전 일정은 피하세요. "
                    f"리허설은 도착 이틀째 오후가 무난합니다")
        if gap >= 5:
            return f"시차 {gap:g}시간. 도착 당일 저녁 일정은 무리입니다"
        if gap > 0:
            return f"시차 {gap:g}시간. 큰 영향은 없습니다"
        return "시차가 없습니다"


class Event(BaseModel):
    """행사 하나와 연사들."""

    model_config = {"extra": "forbid"}

    title: str
    event_date: date
    venue: str = ""
    host: str = Field(default="", description="주최 기관. 초청장에 들어갑니다")
    contact_name: str = ""
    contact_email: str = ""
    speakers: list[Speaker] = Field(default_factory=list)

    @field_validator("event_date", mode="before")
    @classmethod
    def _parse(cls, value):
        return _as_date(value)

    @model_validator(mode="after")
    def _needs_speakers(self) -> "Event":
        if not self.speakers:
            raise ValueError("연사가 한 명도 없습니다")
        names = [item.name for item in self.speakers]
        if len(names) != len(set(names)):
            raise ValueError("연사 이름이 겹칩니다. 구분되게 적으세요")
        return self

    def days_until(self, today: date | None = None) -> int:
        return (self.event_date - (today or date.today())).days

    def speaker(self, name: str) -> Speaker:
        for item in self.speakers:
            if item.name == name:
                return item
        raise RosterError(
            f"명부에 없는 연사입니다: {name}\n"
            f"  있는 연사: {', '.join(item.name for item in self.speakers)}")


def load_event(path: str | Path) -> Event:
    """행사 YAML 을 읽는다."""
    path = Path(path)
    if not path.is_file():
        raise RosterError(
            f"행사 파일이 없습니다: {path}\n"
            f"  `event.yaml` 을 본떠 만드시거나 `--demo` 로 먼저 보세요")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        return Event(**raw)
    except Exception as exc:
        raise RosterError(f"{path.name} 을 읽지 못했습니다:\n  {exc}") from exc
