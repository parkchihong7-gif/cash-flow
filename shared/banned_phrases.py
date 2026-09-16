"""판매용 텍스트 금지 문구 검사기.

CLAUDE.md §3-2 / §7: 상세페이지·README·마케팅 카피에 "수익 보장" 류 표현을 쓰지 않는다.
고액 부업 강의 소비자 피해가 실재하고(2025년 42건, 소비자원 주의보), 이런 문구는
상품 자체를 폐기시킬 수 있는 리스크다.

**판매용 텍스트를 생성한 뒤에는 반드시 :func:`check` 를 호출한다.**
파이프라인에서 강제하려면 :func:`assert_clean` 을 쓴다.

띄어쓰기 변형("수익 보장" / "수익보장")을 모두 잡기 위해 공백을 제거하고 비교한다.
"""

from __future__ import annotations

import re

__all__ = ["BANNED", "check", "is_clean", "assert_clean", "BannedPhraseError"]

#: 금지 문구. 판매용 텍스트에서 발견되면 반드시 고쳐 쓴다.
#: 대체 표현: "시간 절약", "반복 작업 자동화", "검증 필요" (CLAUDE.md §7)
BANNED: tuple[str, ...] = (
    "수익 보장",
    "보장된 수익",
    "확정 수익",
    "수익률 보장",
    "원금 보장",
    "월 1000만원 보장",
    "월 천만원 보장",
    "무조건",
    "확실히 벌",
    "반드시 벌",
    "자동으로 돈",
    "돈이 복사",
    "돈복사",
    "완전 자동 수익",
    "자동 수익 기계",
    "100% 수익",
    "100퍼센트 수익",
    "절대 실패",
    "실패 없는",
    "누구나 성공",
    "무조건 성공",
    "노력 없이",
    "아무것도 안 해도",
    "잠자는 동안 돈",
    "클릭 한 번으로 수익",
    "하루 만에 부자",
    "단기간에 부자",
    "무위험",
    "리스크 제로",
    "평생 수익 보장",
)

_WHITESPACE_RE = re.compile(r"\s+")


class BannedPhraseError(ValueError):
    """판매용 텍스트에서 금지 문구가 발견됐을 때."""

    def __init__(self, found: list[str]) -> None:
        super().__init__("금지 문구가 발견됐습니다: " + ", ".join(found))
        self.found = found


def _normalize(text: str) -> str:
    """공백을 모두 제거해 띄어쓰기 변형을 흡수한다."""
    return _WHITESPACE_RE.sub("", text)


def check(text: str) -> list[str]:
    """텍스트에서 발견된 금지 문구를 BANNED 순서대로 돌려준다.

    Args:
        text: 검사할 텍스트 (README, 상세페이지, 이메일 카피 등).

    Returns:
        발견된 금지 문구 목록. 깨끗하면 빈 리스트.
    """
    if not text:
        return []
    haystack = _normalize(text)
    return [phrase for phrase in BANNED if _normalize(phrase) in haystack]


def is_clean(text: str) -> bool:
    """금지 문구가 하나도 없으면 True."""
    return not check(text)


def assert_clean(text: str) -> str:
    """깨끗하면 텍스트를 그대로 돌려주고, 아니면 BannedPhraseError 를 낸다.

    판매용 텍스트를 파일로 쓰기 직전에 끼워 넣어 쓴다.
    """
    found = check(text)
    if found:
        raise BannedPhraseError(found)
    return text
