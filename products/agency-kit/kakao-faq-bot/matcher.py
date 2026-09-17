"""질문을 FAQ 에 맞춘다.

두 단계로 본다.

    1. **글자로 먼저 본다** — 거의 같은 질문이면 Claude 를 부르지 않는다.
       공짜이고 즉시 끝난다. 실제로 들어오는 질문의 상당수가 여기서 걸린다.
    2. 그래도 모르면 **Claude 에게 뜻으로 물어본다** — FAQ 목록과 질문을 주고
       가장 가까운 번호 하나 또는 "없음" 을 JSON 으로 받는다.

왜 Claude 에게 답을 짓게 하지 않고 번호만 받는가.
    시트에 적힌 답이 **고객이 검수한 문장**이기 때문이다. 같은 뜻으로 다시 쓰면
    조금씩 달라지고, 그 조금이 환불·보증 같은 데서 문제가 된다.
    맞는 항목이 있으면 **시트 문장을 그대로** 내보낸다.
"""

from __future__ import annotations

import json
import re

__all__ = ["normalize", "literal_match", "SIMILARITY_FLOOR", "match", "MATCH_SYSTEM"]

#: 글자로 볼 때 이 정도 겹치면 같은 질문으로 본다.
SIMILARITY_FLOOR = 0.75

#: 조사·군더더기. 견주기 전에 떼어 낸다.
_NOISE = re.compile(r"(요|은|는|이|가|을|를|에|의|도|만|좀|please)$")


def normalize(text: str) -> str:
    """견주기 좋게 다듬는다. 공백·문장부호를 지우고 소문자로."""
    cleaned = re.sub(r"[^0-9a-z가-힣\s]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _tokens(text: str) -> set[str]:
    words = []
    for word in normalize(text).split():
        trimmed = _NOISE.sub("", word)
        words.append(trimmed or word)
    return {word for word in words if len(word) > 1}


def similarity(left: str, right: str) -> float:
    """두 질문이 얼마나 겹치는가 (0~1). 자카드 유사도."""
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def literal_match(question: str, faqs: list) -> int | None:
    """글자만 보고 찾는다. 찾으면 0부터 세는 번호, 못 찾으면 None.

    Claude 를 부르지 않으므로 **즉시 끝나고 돈이 들지 않는다.**
    카카오의 5초 제한에서 이만큼 벌어 두는 것이 크다.
    """
    target = normalize(question)
    if not target:
        return None

    best_index, best_score = None, 0.0
    for index, faq in enumerate(faqs):
        stored = normalize(faq.question)
        if stored == target:
            return index
        score = similarity(question, faq.question)
        if score > best_score:
            best_index, best_score = index, score

    return best_index if best_score >= SIMILARITY_FLOOR else None


MATCH_SYSTEM = """당신은 고객센터 FAQ 담당자다.

아래 FAQ 목록에서 고객 질문과 **같은 것을 묻는** 항목의 번호를 고른다.

고르는 기준
  - 말이 달라도 묻는 것이 같으면 그 번호를 고른다
  - 비슷해 보여도 묻는 것이 다르면 고르지 않는다
  - 확신이 안 서면 고르지 않는다

**모르면 null 을 내는 것이 맞다.** 억지로 고르면 엉뚱한 답이 고객에게 나간다.
그건 답을 못 주는 것보다 나쁘다.

출력은 JSON 하나만.
  {"index": 3, "confidence": "high"}   또는   {"index": null, "confidence": "low"}
설명도 코드 펜스도 붙이지 않는다."""


def match(question: str, faqs: list, ask_fn, model: str) -> int | None:
    """Claude 에게 뜻으로 물어 번호를 받는다. 못 찾으면 None.

    Args:
        question: 고객이 보낸 말.
        faqs: `Faq` 목록.
        ask_fn: `shared.llm.ask` 같은 함수. 테스트에서 갈아 끼운다.
        model: 쓸 모델 이름.
    """
    if not faqs:
        return None

    listing = "\n".join(
        f"{number}. {faq.question}" for number, faq in enumerate(faqs[:60], start=1))
    user = f"[FAQ 목록]\n{listing}\n\n[고객 질문]\n{question}"

    raw = ask_fn(MATCH_SYSTEM, user, model=model, json_mode=True)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None

    value = raw.get("index")
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None

    # 1부터 세는 번호로 받았다. 범위를 벗어나면 못 찾은 것으로 본다.
    # 모델이 목록에 없는 번호를 말하는 일이 실제로 있다.
    if not 1 <= number <= min(len(faqs), 60):
        return None
    return number - 1
