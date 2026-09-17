"""캡션 초안 만들기.

Claude 가 쓰는 것은 **초안**이다. 승인 없이는 큐에 들어가지 않는다.

지키는 것
    - 팔로우 요청·좋아요 구걸·DM 유도 문구를 넣지 않는다. Meta 가 싫어하고,
      실제로 도달이 떨어진다
    - "수익 보장" 류 표현을 넣지 않는다 (`shared.banned_phrases` 로 검사)
    - 해시태그는 **10개 안쪽**. 30개를 채우는 시절은 지났고, 지금은 스팸으로 본다
    - 광고·협찬이면 그 사실을 첫 줄에 적는다
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from shared import banned_phrases                                    # noqa: E402

__all__ = ["CAPTION_SYSTEM", "draft_caption", "clean_hashtags", "MAX_TAGS", "BEGGING"]

#: 해시태그 최대 개수.
MAX_TAGS = 10

#: 넣으면 안 되는 부탁조 문구. 정책상 위험하고 도달에도 나쁘다.
BEGGING = (
    "팔로우 부탁", "맞팔", "선팔", "좋아요 부탁", "좋아요 눌러", "dm 주세요",
    "디엠 주세요", "댓글 달아주시면 팔로우",
)

CAPTION_SYSTEM = """당신은 작은 가게의 인스타그램 계정을 맡은 사람이다.

사진 설명과 메모를 받아 **캡션 초안**을 쓴다.

쓰는 법
  - 첫 줄이 전부다. '더 보기' 앞에서 끝나는 한 줄에 제일 중요한 말을 넣는다
  - 3~5줄. 길면 안 읽는다
  - 사장님이 직접 쓴 것처럼. 광고 문투를 쓰지 마라
  - 하나의 게시물에 하나의 이야기만

절대 쓰지 않는 것
  - "팔로우 부탁드려요", "맞팔해요", "좋아요 눌러주세요" — 정책상 위험하고
    도달에도 나쁘다
  - "수익 보장", "무조건", "100%" 같은 단정
  - 효능·안전을 단언하는 말 (식품·화장품은 특히)
  - 없는 할인, 없는 마감

해시태그
  - **10개 안쪽**. 지역·업종·상황 위주로
  - 아무 상관 없는 인기 태그를 붙이지 마라. 스팸으로 본다

광고·협찬이면 첫 줄에 "광고" 또는 "협찬" 을 적는다.

출력 (JSON 하나만)
{"caption": "캡션 본문", "hashtags": ["#태그1", "#태그2"], "first_line_note": "첫 줄을 이렇게 잡은 이유"}"""


def clean_hashtags(tags) -> str:
    """해시태그를 다듬는다. 중복·빈 것을 빼고 10개로 자른다."""
    if isinstance(tags, str):
        raw = tags.split()
    else:
        raw = list(tags or [])

    seen: list[str] = []
    for tag in raw:
        text = str(tag).strip()
        if not text:
            continue
        text = "#" + re.sub(r"[^0-9A-Za-z가-힣_]", "", text.lstrip("#"))
        if len(text) <= 1 or text in seen:
            continue
        seen.append(text)
    return " ".join(seen[:MAX_TAGS])


def _begging_hits(text: str) -> list[str]:
    lowered = (text or "").lower()
    return [phrase for phrase in BEGGING if phrase in lowered]


def draft_caption(note: str, ask_fn, model: str, brand: str = "",
                  sponsored: bool = False) -> tuple[str, str, list[str]]:
    """캡션 초안을 받는다.

    Returns:
        (캡션, 해시태그 문자열, 경고 목록)
    """
    user = (f"[가게] {brand or '(적지 않음)'}\n"
            f"[광고·협찬 여부] {'있음 — 첫 줄에 밝혀야 합니다' if sponsored else '없음'}\n"
            f"[사진·메모]\n{note}")

    raw = ask_fn(CAPTION_SYSTEM, user, model=model, json_mode=True)
    if not isinstance(raw, dict):
        raw = {}

    caption = str(raw.get("caption") or "").strip()
    hashtags = clean_hashtags(raw.get("hashtags"))

    warnings: list[str] = []
    if not caption:
        warnings.append("캡션을 만들지 못했습니다. 직접 쓰셔야 합니다")

    found = banned_phrases.check(caption)
    if found:
        warnings.append(f"쓰면 안 되는 표현이 있습니다: {', '.join(found)}")

    begging = _begging_hits(caption)
    if begging:
        warnings.append(f"부탁조 문구가 있습니다(정책상 위험): {', '.join(begging)}")

    if sponsored and not re.search(r"광고|협찬|유료", caption[:60]):
        warnings.append("광고·협찬인데 첫 줄에 밝히지 않았습니다. 표시광고법 문제가 됩니다")

    if len(caption) > 2200:
        warnings.append("캡션이 인스타 한도(2,200자)를 넘습니다")

    return caption, hashtags, warnings
