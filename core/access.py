"""권한·환경 점검 — **오늘 바로 되는 것과, 가입부터 해야 하는 것.**

상세페이지에 "설치만 하면 바로 씁니다" 라고 써 놓고, 막상 사고 나니 API 심사가
2주 걸린다면 그건 환불로 돌아온다. 사기까지는 아니어도 신뢰는 거기서 끝난다.

그래서 이 화면은 두 가지만 답한다.

1. **집 컴퓨터에서 되나** — 서버·클라우드·별도 장비가 필요한가
2. **무슨 권한이 필요한가** — 계정, 비용, 그리고 *받는 데 걸리는 시간*

세 번째 것이 제일 자주 발목을 잡는다. 돈은 카드로 바로 내지만 심사는 못 당긴다.

`.env` 값과 맞대어, 받아 놓고 안 넣은 키까지 짚는다. 값은 읽지 않는다.
**있다/없다만** 본다 (core/overview.py 와 같은 원칙).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

__all__ = [
    "AccountRow",
    "ProgramAccess",
    "collect",
    "summarize",
    "LEAD_ORDER",
]

#: 오래 걸리는 것부터. 일정은 여기서 밀린다.
LEAD_ORDER = {"심사 필요": 0, "하루 이틀": 1, "즉시": 2}


@dataclass
class AccountRow:
    """계정 한 줄 + 지금 `.env` 에 들어 있는지."""

    name: str
    why: str
    cost: str
    lead_time: str
    how: str
    env_key: str
    blocking: bool
    env_set: bool = False

    @property
    def waiting(self) -> bool:
        return self.lead_time == "심사 필요"

    @property
    def state(self) -> str:
        """화면에 칠할 색. 키를 안 쓰는 계정은 'n/a' 다."""
        if not self.env_key:
            return "manual"
        return "set" if self.env_set else ("missing" if self.blocking else "optional")

    @property
    def state_label(self) -> str:
        return {
            "set": "넣었습니다",
            "missing": "아직 안 넣었습니다",
            "optional": "없어도 됩니다",
            "manual": "키가 아니라 계정입니다",
        }[self.state]


@dataclass
class ProgramAccess:
    """프로그램 한 개의 준비물."""

    id: str
    number: int
    name: str
    status_label: str
    home_pc: str
    home_pc_label: str
    home_pc_note: str
    internet: str
    internet_label: str
    accounts: list[AccountRow] = field(default_factory=list)
    software: list[dict] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> list[AccountRow]:
        return [row for row in self.accounts if row.blocking]

    @property
    def waiting(self) -> list[AccountRow]:
        return [row for row in self.accounts if row.waiting]

    @property
    def missing(self) -> list[AccountRow]:
        """없으면 못 쓰는데 아직 `.env` 에 안 들어온 것."""
        return [row for row in self.accounts if row.state == "missing"]

    @property
    def extra_software(self) -> list[dict]:
        return [item for item in self.software if not item["bundled"]]

    @property
    def ready_now(self) -> bool:
        """가입도 심사도 없이 지금 당장 되는가.

        심사 항목은 **없어도 쓸 수 있는 것이라도** 여기서 뺀다. 14번처럼
        견적은 오늘 되지만 실제 업로드는 감사를 기다려야 하는 상품을
        '지금 바로' 라고 팔면 환불로 돌아온다.
        """
        return (not self.blocking and not self.extra_software
                and not self.waiting and self.home_pc == "yes")

    @property
    def state(self) -> str:
        if self.home_pc == "no":
            return "hard"
        if self.waiting:
            return "wait"
        if self.blocking or self.extra_software:
            return "setup"
        return "now"

    @property
    def state_label(self) -> str:
        return {
            "now": "지금 바로",
            "setup": "준비 먼저",
            "wait": "심사를 기다려야",
            "hard": "집 컴퓨터로는 어려움",
        }[self.state]

    @property
    def prep_line(self) -> str:
        """한 줄 요약. 표 한 칸에 들어갈 길이로."""
        bits: list[str] = []
        if self.blocking:
            bits.append(f"계정 {len(self.blocking)}개")
        if self.extra_software:
            bits.append(f"설치 {len(self.extra_software)}개")
        if self.waiting:
            bits.append("심사 대기")
        return " · ".join(bits) if bits else "없음"


def collect(registry, environ: dict[str, str] | None = None) -> list[ProgramAccess]:
    """프로그램마다 준비물을 모은다. 손이 많이 가는 것이 앞에 온다."""
    source = os.environ if environ is None else environ

    result: list[ProgramAccess] = []
    for program in registry.programs:
        need = program.requirements
        accounts = [
            AccountRow(
                name=item.name, why=item.why, cost=item.cost,
                lead_time=item.lead_time, how=item.how, env_key=item.env_key,
                blocking=item.blocking,
                env_set=bool((source.get(item.env_key) or "").strip())
                if item.env_key else False,
            )
            for item in need.accounts
        ]
        accounts.sort(key=lambda row: (LEAD_ORDER.get(row.lead_time, 9),
                                       not row.blocking, row.name))
        result.append(ProgramAccess(
            id=program.id,
            number=program.number,
            name=program.name,
            status_label=program.status_label,
            home_pc=need.home_pc,
            home_pc_label=need.home_pc_label,
            home_pc_note=need.home_pc_note,
            internet=need.internet,
            internet_label=need.internet_label,
            accounts=accounts,
            software=[item.model_dump() for item in need.software],
            limits=list(need.limits),
            cautions=list(need.cautions),
        ))

    order = {"hard": 0, "wait": 1, "setup": 2, "now": 3}
    result.sort(key=lambda item: (order[item.state], item.number))
    return result


def summarize(rows: list[ProgramAccess]) -> dict[str, int]:
    """윗줄 숫자."""
    return {
        "total": len(rows),
        "now": sum(1 for row in rows if row.state == "now"),
        "setup": sum(1 for row in rows if row.state == "setup"),
        "wait": sum(1 for row in rows if row.state == "wait"),
        "hard": sum(1 for row in rows if row.state == "hard"),
        "missing": sum(len(row.missing) for row in rows),
    }
