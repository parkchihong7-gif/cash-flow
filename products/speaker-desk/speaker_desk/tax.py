"""원천징수 — **돈이 가장 많이 어긋나는 지점.**

비거주자에게 국내에서 인적용역(강연 등) 대가를 지급하면 **지급하는 쪽이
원천징수**를 해야 한다 (소득세법 제156조, 비거주자의 국내원천소득에 대한
원천징수).

기본 세율은 **20%** 이고 여기에 지방소득세 10%(즉 2%)가 붙어 **합계 22%** 다.

문제는 이거다. 계약서에 "강연료 500만 원" 이라고만 써 놓으면, 연사는 500만 원을
기대하고 실제로는 390만 원을 받는다. **그 자리에서 분쟁이 난다.**

그래서 계약할 때 정해야 하는 것은 하나다.

* **gross** — 500만 원에서 세금을 떼고 390만 원을 보낸다
* **net** — 연사 손에 500만 원이 가도록, 총액을 그로스업해서 지급한다

두 번째를 택하면 주최 측 실제 부담이 늘어난다. 이 모듈은 그 금액을 계산한다.

## 조세조약

연사 거주국과 한국 사이에 조세조약이 있으면 **면제되거나 제한세율**이 적용될
수 있다. 다만 자동이 아니다. **연사가 서류를 내야 한다.**

* 거주자증명서 (Certificate of Residence) — 연사 거주국 세무당국 발급
* 제한세율 적용신청서 또는 비과세·면제 신청서

이 서류를 **지급일 전에** 받아야 한다. 나중에 받으면 이미 뗀 세금을 돌려받는
경정청구 절차를 밟아야 하고, 그건 훨씬 번거롭다.

⚠ 이 모듈은 세무 자문이 아니다. 조약 적용 여부와 세율은 사안마다 다르므로
**반드시 세무대리인에게 확인하라.**
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "BASE_RATE", "LOCAL_SURTAX", "TOTAL_RATE", "TREATY_DOCS", "NOT_TAX_ADVICE",
    "Withholding", "compute", "gross_up",
]

#: 소득세법 제156조 — 비거주자 인적용역소득 원천징수 세율.
BASE_RATE = 0.20
#: 지방소득세는 소득세액의 10%.
LOCAL_SURTAX = 0.10
#: 합계 22%.
TOTAL_RATE = BASE_RATE * (1 + LOCAL_SURTAX)

TREATY_DOCS = (
    "거주자증명서 (Certificate of Residence) — 연사 거주국 세무당국 발급, 원본",
    "제한세율 적용신청서 또는 비과세·면제 신청서 — 국세청 서식",
    "여권 사본",
    "계약서 사본 (용역의 내용과 대가가 드러나야 합니다)",
)

NOT_TAX_ADVICE = (
    "이 계산은 **세무 자문이 아닙니다.** 기본 세율로 잡아 본 값이고, "
    "조세조약 적용 여부·제한세율·소득 구분은 사안마다 다릅니다. "
    "실제 지급 전에 반드시 세무대리인에게 확인하세요."
)


@dataclass
class Withholding:
    """원천징수 계산 결과."""

    contract_amount: int      # 계약서에 적는 금액
    gross: int                # 지급 총액 (원천징수 대상)
    tax: int                  # 뗄 세금
    net: int                  # 연사가 실제로 받는 돈
    rate: float               # 적용 세율
    basis: str                # 'net' 인가 'gross' 인가
    treaty: bool = False

    @property
    def sponsor_cost(self) -> int:
        """주최 측이 실제로 쓰는 돈."""
        return self.gross

    @property
    def extra_for_net(self) -> int:
        """net 방식으로 바꾸면 더 드는 돈."""
        return max(0, self.gross - self.contract_amount)

    @property
    def rate_percent(self) -> float:
        return round(self.rate * 100, 2)


def gross_up(net_amount: int, rate: float = TOTAL_RATE) -> int:
    """연사 손에 이 금액이 가려면 총액이 얼마여야 하는가."""
    if rate >= 1:
        raise ValueError("세율이 100% 이상일 수 없습니다")
    return round(net_amount / (1 - rate))


def compute(amount: int, basis: str = "gross", treaty_rate: float | None = None) -> Withholding:
    """원천징수를 계산한다.

    Args:
        amount: 계약서에 적는 금액.
        basis: 'gross' 면 이 금액에서 세금을 뗀다.
               'net' 이면 연사 손에 이 금액이 가도록 총액을 올린다.
        treaty_rate: 조세조약 제한세율(0.0~1.0). None 이면 기본 22%.
    """
    if amount < 0:
        raise ValueError("금액은 0 이상이어야 합니다")
    basis = (basis or "gross").strip().lower()
    if basis not in ("gross", "net"):
        raise ValueError("basis 는 'gross' 또는 'net' 이어야 합니다")

    treaty = treaty_rate is not None
    rate = TOTAL_RATE if treaty_rate is None else float(treaty_rate)
    if not 0 <= rate < 1:
        raise ValueError("세율은 0 이상 1 미만이어야 합니다")

    if basis == "gross":
        gross = amount
        tax = round(gross * rate)
        net = gross - tax
    else:
        net = amount
        gross = gross_up(net, rate)
        tax = gross - net

    return Withholding(contract_amount=amount, gross=gross, tax=tax, net=net,
                       rate=rate, basis=basis, treaty=treaty)
