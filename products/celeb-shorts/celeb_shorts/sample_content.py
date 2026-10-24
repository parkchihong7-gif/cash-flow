"""모의 실행용 가짜 Claude — 비용 0원, 인터넷 없이 기획서 모양을 보여 준다.

입력(요청 JSON)을 그대로 읽어 규칙에 맞는 기획을 만든다. 프롬프트는 쓰지 않는다.
"""

from __future__ import annotations

import json


def _won(price: int) -> str:
    if price >= 10000 and price % 10000 == 0:
        return f"{price // 10000:,}만원"
    return f"{price:,}원"


def fake_ask(system: str, user: str, **_kwargs) -> dict:
    request = json.loads(user)
    who = request.get("celebrity") or ""
    occasion = request.get("occasion") or "요즘"
    items = request["items"]
    duration = request["duration_sec"]

    lead = f"{who} {occasion}" if who else f"{occasion} 스타일"
    scenes = [{"start": 0, "end": 2, "subtitle": f"{lead} 템", "narration": f"{lead}에서 눈에 띈 아이템",
               "visual": "text_card", "item_index": None}]

    middle = duration - 2 - 3
    per = middle / len(items)
    cursor = 2.0
    for index, item in enumerate(items):
        name = item["name"]
        if item["mode"] == "확인":
            line = f"{item['brand']} {name}".strip()
        else:
            line = f"비슷한 {name}"
        price = item.get("price")
        half = per / 2
        scenes.append({"start": cursor, "end": cursor + half, "subtitle": line,
                       "narration": f"{line}입니다", "visual": "product_image", "item_index": index})
        detail = _won(price) if price else "이런 느낌이에요"
        scenes.append({"start": cursor + half, "end": cursor + per, "subtitle": detail,
                       "narration": detail, "visual": "product_image", "item_index": index})
        cursor += per

    scenes.append({"start": cursor, "end": duration, "subtitle": "상품 태그 확인",
                   "narration": request.get("cta") or "상품 태그에서 확인하세요",
                   "visual": "text_card", "item_index": None})

    return {
        "title": f"{lead} 아이템 {len(items)}가지",
        "hook": f"{lead} 템",
        "scenes": scenes,
        "description": f"{lead}에서 화제가 된 아이템과 비슷한 상품을 모았습니다.",
        "hashtags": ["#쇼츠", "#패션", "#스타일"],
    }
