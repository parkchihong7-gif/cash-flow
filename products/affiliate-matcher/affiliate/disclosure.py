"""대가성 문구 — 이 상품에서 **양보하지 않는 한 가지**.

쿠팡파트너스는 대가성 문구가 없으면 경고 없이 자격을 정지한다(CLAUDE.md §3-6).
유튜브는 유료 프로모션을 알리지 않으면 영상이 내려가거나 채널에 제재가 붙는다.
표시광고법상으로도 경제적 이해관계 공개는 사업자의 의무다.

그래서 이 모듈은 문구를 '제공' 하지 않고 **강제**한다.

    - 링크가 하나라도 든 산출물은 문구 없이 저장되지 않는다(`assert_disclosed`).
    - 문구를 지우는 옵션은 만들지 않았다. 옵션으로 두면 언젠가 꺼진다.

문구를 채널 사정에 맞게 고치는 것은 자유다. 다만 **없애지는 못한다.**
"""

from __future__ import annotations

import re

__all__ = [
    "COUPANG",
    "YOUTUBE_DESCRIPTION",
    "YOUTUBE_SPOKEN",
    "INSTAGRAM",
    "MARKERS",
    "disclosure_block",
    "assert_disclosed",
    "DisclosureMissing",
]


class DisclosureMissing(RuntimeError):
    """대가성 문구 없이 링크를 내보내려 했을 때."""


#: 쿠팡파트너스 표준 문구. 링크와 **같은 화면**에 보여야 한다.
COUPANG = (
    "이 글(영상)에는 쿠팡 파트너스 활동의 일환으로, "
    "이에 따른 일정액의 수수료를 제공받는 링크가 포함되어 있습니다."
)

#: 유튜브 설명란 맨 위에 넣는 문구.
YOUTUBE_DESCRIPTION = (
    "유료 프로모션 포함 — 이 영상에는 제휴 링크가 있으며, "
    "시청자가 구매하시면 제작자에게 수수료가 지급됩니다. "
    "구매 가격은 달라지지 않습니다."
)

#: 영상에서 말로도 알리는 편이 안전하다. 설명란은 접혀 있어 잘 안 읽힌다.
YOUTUBE_SPOKEN = (
    "이 영상에는 제휴 링크가 들어 있습니다. "
    "구매하시면 저에게 수수료가 오지만 가격은 그대로입니다."
)

#: 인스타그램은 첫 줄에 두어야 '더 보기' 앞에서 보인다.
INSTAGRAM = "광고·제휴 링크 포함 (구매 시 수수료를 받습니다 / 가격 변동 없음)"

#: 문구가 살아 있는지 확인할 때 찾는 조각.
#: 문장을 통째로 비교하면 한 글자만 고쳐도 통과하지 못해, 핵심만 본다.
MARKERS: tuple[str, ...] = ("쿠팡 파트너스", "수수료를 제공받", "유료 프로모션", "제휴 링크")


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def disclosure_block(medium: str = "") -> str:
    """산출물 맨 위에 붙는 고지 덩어리.

    Args:
        medium: 블로그·유튜브·인스타 중 무엇인지. 몰라도 전부 담는다.
            **어느 채널에 올릴지 모를 때 빠뜨리는 것이 가장 흔한 사고**라
            기본은 전부 싣고 쓰는 사람이 지우게 둔다.
    """
    lines = [
        "========================================",
        "  대가성 표시 — 지우지 마세요",
        "========================================",
        "",
        f"[쿠팡파트너스 / 필수] {COUPANG}",
        "",
        f"[유튜브 설명란] {YOUTUBE_DESCRIPTION}",
        f"[유튜브 육성 고지] {YOUTUBE_SPOKEN}",
        f"[인스타·릴스 첫 줄] {INSTAGRAM}",
        "",
        "넣는 자리",
        "  - 블로그: 본문 **맨 위**. 맨 아래에만 두면 못 보고 지나칩니다.",
        "  - 유튜브: 업로드 화면의 '유료 프로모션 포함' 체크 + 설명란 첫 줄.",
        "  - 인스타: 캡션 첫 줄. '더 보기' 뒤로 넘어가면 안 보인 것과 같습니다.",
        "",
        "빠뜨리면 쿠팡은 경고 없이 자격을 정지하고, 유튜브는 영상을 내립니다.",
    ]
    if medium:
        lines.append(f"이번 원고는 '{medium}' 기준으로 뽑았습니다. 다른 채널에도 올리면"
                     " 그 채널 문구를 함께 쓰세요.")
    return "\n".join(lines)


def assert_disclosed(text: str, what: str = "산출물") -> None:
    """링크가 든 글에 대가성 문구가 살아 있는지 확인한다.

    Raises:
        DisclosureMissing: 문구 조각이 하나도 없을 때.
    """
    squashed = _squash(text)
    if any(_squash(marker) in squashed for marker in MARKERS):
        return
    raise DisclosureMissing(
        f"{what} 에 대가성 문구가 없습니다.\n"
        "  링크만 있고 문구가 없으면 쿠팡파트너스 자격이 정지됩니다(경고 없음).\n"
        "  affiliate/disclosure.py 의 문구를 쓰거나, 같은 뜻의 문장을 넣으세요."
    )
