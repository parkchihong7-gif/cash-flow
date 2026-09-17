"""모의 실행용 가짜 응답.

Claude 를 부르지 않고도 챗봇 흐름을 끝까지 볼 수 있어야 한다. 시연할 때,
설치 직후 점검할 때, 그리고 테스트에서.

**뜻 매칭을 흉내 낸다.** 질문에 들어 있는 낱말로 FAQ 번호를 고르고, 아무것도
안 맞으면 `null` 을 낸다. 실제 Claude 와 같은 모양의 JSON 을 돌려준다.
"""

from __future__ import annotations

import json
import re

__all__ = ["fake_ask", "HINTS"]

#: 낱말 → FAQ 에서 찾을 말. 모의 실행이 그럴듯해 보이는 만큼만 넣는다.
HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("영업", "몇 시", "여는", "문 닫"), "영업시간"),
    (("주차", "차 가지고", "주차장"), "주차"),
    (("예약", "당일", "워크인"), "예약 없이"),
    (("취소", "노쇼", "못 가"), "예약 취소"),
    (("환불", "돈 돌려", "반환"), "환불 규정"),
    (("얼마", "가격", "수업료", "비용", "요금"), "수업료"),
    (("초보", "처음", "경험 없"), "초보자"),
    (("준비물", "뭐 가져", "챙길"), "준비물"),
    (("샤워", "탈의", "락커"), "샤워실"),
    (("아이", "애기", "유아", "동반"), "아이와"),
    (("결제", "카드", "현금영수증", "계좌"), "결제 수단"),
    (("위치", "어디", "오시는", "역"), "위치"),
)


def _pick(question: str, listing: str) -> int | None:
    """FAQ 목록에서 번호를 고른다. 목록은 '1. 질문' 꼴이다."""
    lowered = question.lower()
    numbered = {}
    for line in listing.splitlines():
        matched = re.match(r"\s*(\d+)\.\s*(.+)", line)
        if matched:
            numbered[int(matched.group(1))] = matched.group(2)

    for words, needle in HINTS:
        if not any(word in lowered for word in words):
            continue
        for number, text in numbered.items():
            if needle in text:
                return number
    return None


def fake_ask(system: str, user: str, **kwargs):
    """`shared.llm.ask` 자리에 끼우는 가짜.

    - 매칭 요청(json_mode) 이면 번호 또는 null 을 돌려준다.
    - 답변 요청이면 짧은 문장을 돌려준다. **없는 사실을 지어내지 않는다.**
    """
    question = ""
    listing = ""
    if "[고객 질문]" in user:
        head, _, question = user.partition("[고객 질문]")
        listing = head
        question = question.strip()

    if kwargs.get("json_mode"):
        index = _pick(question, listing)
        return {"index": index, "confidence": "high" if index else "low"}

    return ("문의하신 내용은 제가 확인하기 어렵습니다. "
            "담당자에게 연결해 드리겠습니다.")


def fake_ask_slow(seconds: float = 10.0):
    """느린 응답을 흉내 낸다. 5초 제한을 지키는지 볼 때 쓴다."""
    import time

    def _slow(system: str, user: str, **kwargs):
        time.sleep(seconds)
        return json.dumps({"index": None})

    return _slow
