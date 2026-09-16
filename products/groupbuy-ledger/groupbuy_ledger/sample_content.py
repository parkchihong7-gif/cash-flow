"""모의 실행용 가짜 코멘트.

실제 Claude 를 부르지 않고 리포트까지 만들어 보기 위한 고정 응답이다.
프롬프트에 붙는 `[수치]` 블록을 실제로 읽어서 그 숫자만 써서 세 줄을 만든다.
그래야 모의 실행 결과도 "엑셀 계산값만 인용" 규칙을 똑같이 지키고,
숫자 검사기가 제대로 도는지도 함께 확인된다.
"""

from __future__ import annotations

import json

__all__ = ["fake_ask", "compose_lines"]


def compose_lines(facts: dict) -> list[str]:
    """수치 블록만 보고 세 줄을 만든다."""
    best = facts.get("가장_잘_팔린_옵션")
    refund = facts.get("환불률_퍼센트")
    low_stock = facts.get("재고부족_옵션") or []
    products = facts.get("상품별") or []
    margin = facts.get("순마진율_퍼센트")

    if best:
        first = (f"{best['이름']} 이 {best['판매수량']}개로 가장 많이 나갔습니다. "
                 f"이익도 {best['이익']:,}원으로 이번 회차를 끌고 간 옵션입니다.")
    else:
        first = ("판매된 옵션이 아직 없습니다. 주문 시트에 주문을 채운 뒤 "
                 "다시 리포트를 만들어 보세요.")

    if refund is not None and refund > 0:
        second = (f"환불률이 {refund}% 입니다. 취소 사유를 주문 메모에 남겨 두면 "
                  "다음 회차에 상세페이지의 어느 설명이 부족했는지 짚어 볼 수 있습니다.")
    else:
        second = ("취소·환불이 아직 없습니다. 발송이 끝난 뒤에 몰리는 경우가 많으니 "
                  "회차가 닫힌 다음 한 번 더 확인해 보시길 권합니다.")

    if low_stock:
        item = low_stock[0]
        third = (f"{item['이름']} 재고가 {item['남은재고']}개 남았습니다. "
                 "추가 발주를 넣거나 품절 표시를 먼저 해 두는 편이 안전해 보입니다.")
    elif len(products) > 3 and margin is not None:
        third = (f"순마진율이 {margin}% 입니다. 옵션이 {len(products)}개로 많은 편이라 "
                 "덜 팔린 옵션을 줄여 보는 것을 시도해 볼 만합니다.")
    else:
        third = ("다음 회차에는 잘 나간 옵션의 수량을 늘려 보는 쪽을 시도해 볼 만합니다. "
                 "다만 한 회차 결과만으로는 판단하기 이르니 한 번 더 지켜보세요.")

    return [first, second, third]


def fake_ask(system: str, user: str, model: str = "dry-run", **_) -> str:
    """`[수치]` 블록을 읽어 세 줄을 돌려준다."""
    if "[수치]" not in user:
        raise AssertionError(f"모의 콘텐츠가 모르는 프롬프트입니다:\n{user[:300]}")

    block = user.split("[수치]", 1)[1].strip()
    depth, end = 0, len(block)
    for index, char in enumerate(block):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    facts = json.loads(block[:end])
    return "\n".join(f"- {line}" for line in compose_lines(facts))
