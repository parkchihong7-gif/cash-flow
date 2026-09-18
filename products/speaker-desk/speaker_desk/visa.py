"""비자 — **실무에서 가장 많이 틀리는 지점.**

가장 흔한 착각은 이것이다.

> "무비자 입국이 되는 나라니까 그냥 오시면 됩니다."

**강연료를 받으면 그렇지 않다.** 대가를 받는 강연은 '취업활동' 으로 보아
그에 맞는 체류자격이 필요하다. K-ETA 나 무비자(B-1/B-2)로 들어와 돈을 받고
강연하면 체류자격 외 활동이 된다.

반대 경우도 있다. **정말로 대가가 없고 순수한 학술 발표·회의 참석**이면
단기방문(C-3)이나 무비자로 되는 경우가 많다. 항공·숙박 실비만 대는 것을
'대가' 로 볼지는 사안마다 다르다.

그래서 이 모듈은 **판정하지 않는다.** 어느 쪽을 확인해야 하는지 좁혀 주고,
**반드시 출입국·주한공관에 확인하라**고 말한다. 여기서 틀리면 연사가 공항에서
돌아간다. 프로그램이 책임질 수 있는 일이 아니다.

법령 근거: 출입국관리법 제18조(외국인 고용의 제한), 제20조(체류자격 외 활동),
출입국관리법 시행령 별표1 체류자격 구분.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "VisaHint", "assess", "VISA_KINDS", "MUST_CONFIRM", "SHORT_STAY_DAYS",
]

#: 이 일수를 넘으면 단기 체류자격으로는 어렵다.
SHORT_STAY_DAYS = 90

MUST_CONFIRM = (
    "이것은 **확인해야 할 방향**을 좁혀 주는 것이지 판정이 아닙니다. "
    "반드시 관할 출입국·외국인청이나 연사 거주국의 주한 대한민국 공관에 "
    "확인하세요. 여기서 틀리면 연사가 공항에서 돌아갑니다."
)

VISA_KINDS = {
    "C-4": {
        "name": "단기취업 (C-4)",
        "when": "90일 이하 체류하며 **대가를 받고** 강연·공연·연구 등을 할 때",
        "note": "강연료를 지급하는 초청은 대개 여기를 확인하게 됩니다. "
                "초청장·계약서·일정표가 필요합니다",
    },
    "C-3": {
        "name": "단기방문 (C-3)",
        "when": "90일 이하, **대가 없이** 회의 참석·학술 발표·시장조사 등",
        "note": "실비(항공·숙박)만 대는 경우 여기에 해당할 수 있으나, "
                "사안마다 판단이 다릅니다",
    },
    "무비자/K-ETA": {
        "name": "무비자 또는 K-ETA",
        "when": "사증면제 협정국·무사증 입국 대상국 국민이 **대가 없이** 짧게 올 때",
        "note": "**대가를 받으면 이 경로로는 안 됩니다.** 가장 많이 틀리는 곳입니다",
    },
    "장기": {
        "name": "90일 초과 — 별도 체류자격",
        "when": "90일을 넘겨 머물 때",
        "note": "E-1(교수)·E-7 등 다른 자격을 봐야 합니다. 일정이 오래 걸립니다",
    },
}


@dataclass
class VisaHint:
    """확인해야 할 방향."""

    kind: str
    name: str
    when: str
    note: str
    reasons: list[str]
    warnings: list[str]

    @property
    def urgent(self) -> bool:
        return bool(self.warnings)


def assess(paid: bool, days: int, visa_waiver: bool,
           expenses_only: bool = False) -> VisaHint:
    """대가 유무·체류일수·사증면제 여부로 확인할 방향을 좁힌다.

    Args:
        paid: 강연료·사례비 등 **대가**를 지급하는가.
        days: 한국에 머무는 일수.
        visa_waiver: 그 나라가 사증면제·무사증 입국 대상인가.
        expenses_only: 항공·숙박 실비만 대는가 (대가는 없음).
    """
    reasons: list[str] = []
    warnings: list[str] = []

    if days > SHORT_STAY_DAYS:
        reasons.append(f"체류 {days}일 — {SHORT_STAY_DAYS}일을 넘습니다")
        warnings.append(
            f"{SHORT_STAY_DAYS}일 초과는 단기 체류자격으로 안 됩니다. "
            f"E-1·E-7 등을 봐야 하고 준비 기간이 훨씬 깁니다")
        kind = "장기"
    elif paid:
        reasons.append("강연료 등 **대가를 지급**합니다")
        reasons.append(f"체류 {days}일 — 90일 이하")
        if visa_waiver:
            warnings.append(
                "사증면제 대상국이라도 **대가를 받으면 무비자로 강연할 수 없습니다.** "
                "여기서 가장 많이 틀립니다. 입국은 되지만 체류자격 외 활동이 됩니다")
        kind = "C-4"
    elif expenses_only:
        reasons.append("대가는 없고 **항공·숙박 실비만** 지원합니다")
        warnings.append(
            "실비 지원을 대가로 볼지는 사안마다 다릅니다. "
            "금액이 크거나 명목이 애매하면 반드시 확인하세요")
        kind = "무비자/K-ETA" if visa_waiver else "C-3"
    else:
        reasons.append("대가 없이 회의 참석·발표만 합니다")
        kind = "무비자/K-ETA" if visa_waiver else "C-3"

    spec = VISA_KINDS[kind]
    return VisaHint(kind=kind, name=spec["name"], when=spec["when"],
                    note=spec["note"], reasons=reasons, warnings=warnings)
