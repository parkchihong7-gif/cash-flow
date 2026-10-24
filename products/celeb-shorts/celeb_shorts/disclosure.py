"""대가성 문구와 출처 표시 — 지우는 옵션은 없다.

쿠팡파트너스는 문구가 없으면 경고 없이 자격을 정지하고(CLAUDE.md §3-6),
유튜브는 유료 프로모션을 알리지 않으면 영상을 내린다. 쇼츠는 설명란이 접혀 있어
**설명란 첫 줄 + 업로드 화면의 '유료 프로모션 포함' 체크** 둘 다 해야 한다.
"""

from __future__ import annotations

import re

__all__ = ["COUPANG", "YOUTUBE", "SHOPPING_NOTE", "description_block", "assert_disclosed", "DisclosureMissing"]


class DisclosureMissing(RuntimeError):
    """대가성 문구 없이 설명란을 내보내려 했을 때."""


COUPANG = (
    "이 영상에는 쿠팡 파트너스 활동의 일환으로, "
    "이에 따른 일정액의 수수료를 제공받는 링크가 포함되어 있습니다."
)

YOUTUBE = (
    "유료 프로모션 포함 — 소개한 상품을 구매하시면 제작자에게 수수료가 지급됩니다. "
    "구매 가격은 달라지지 않습니다."
)

#: 쇼츠 설명란·댓글 링크는 눌리지 않는다(2023년부터). 실제로 팔리는 자리는 상품 태그다.
SHOPPING_NOTE = (
    "쇼츠 설명란·댓글의 링크는 눌리지 않습니다. 유튜브 쇼핑 제휴(구독자 500명 + YPP)라면 "
    "업로드 화면 '상품' 에서 태그하고, 그 전에는 관련 롱폼 영상이나 채널 프로필 링크로 보내세요."
)

_MARKERS = ("쿠팡 파트너스", "유료 프로모션")


def description_block() -> str:
    return f"{YOUTUBE}\n{COUPANG}"


def assert_disclosed(text: str) -> None:
    squashed = re.sub(r"\s+", "", text or "")
    if all(re.sub(r"\s+", "", marker) in squashed for marker in _MARKERS):
        return
    raise DisclosureMissing("설명란에 대가성 문구가 없습니다. 쿠팡 자격 정지·유튜브 제재 대상입니다.")
