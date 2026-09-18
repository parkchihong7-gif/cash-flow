"""네이버 블로그에서 **되는 것과 안 되는 것.**

이 파일이 이 상품의 설계 전제다. 여기부터 읽어야 나머지가 이해된다.

## 자동 게시가 없는 이유

네이버는 **블로그 글쓰기 공개 API 를 제공하지 않는다.** 예전에 있던 오픈API
글쓰기 기능은 오래전에 닫혔고, 지금 네이버 개발자센터에서 받을 수 있는 것은
**읽는 API**(검색·데이터랩)와 로그인·지도 같은 것뿐이다.

그러면 자동 게시를 하려면 방법이 하나뿐이다. **브라우저를 흉내 내서 로그인하고
글쓰기 화면을 조작하는 것.** 이건 두 가지 이유로 안 만든다.

1. 네이버 이용약관이 금지한다. 계정이 정지된다
2. CLAUDE.md §7 이 금지한다 — 비공식 자동화(브라우저 매크로, 비밀번호 저장형)

"그래도 다들 하던데요" 라는 말을 듣는다. 하는 사람이 있는 것과 팔아도 되는 것은
다르다. 남의 계정이 정지되는 도구를 팔면 환불로 끝나지 않는다.

## 그래서 이 상품은

**붙여넣기 직전까지** 간다. 수요를 확인하고, 초안을 쓰고, 검사하고, 사람이
복사해 붙인다. 마지막 한 걸음만 사람이 한다.

역설적으로 이게 더 낫다. 네이버 검색 노출 로직(C-Rank·D.I.A.+)은 **원본성과
체류시간**을 본다. 양산한 글은 어차피 안 올라간다. 붙여넣기 전에 한 번 읽고
고치는 그 과정이 품질을 만든다.

## 대가성 문구

협찬·제휴·원고료를 받은 글은 **경제적 이해관계를 공개**해야 한다
(공정거래위원회 추천·보증 등에 관한 표시·광고 심사지침). 이건 권고가 아니라
표시광고법에 근거한 것이고, 빠뜨리면 사업자가 제재를 받는다.

그래서 이 프로그램은 대가를 받은 글에 **문구 없이는 산출물을 내보내지 않는다.**
"""

from __future__ import annotations

__all__ = [
    "NO_WRITE_API", "BANNED_AUTOMATION", "DISCLOSURE", "DISCLOSURE_RULES",
    "disclosure_for", "DisclosureMissing", "assert_disclosed", "SPONSOR_KINDS",
]

NO_WRITE_API = (
    "네이버는 블로그 글쓰기 공개 API 를 제공하지 않습니다. "
    "이 프로그램은 초안까지만 만들고, 올리는 것은 사람이 복사해 붙입니다."
)

BANNED_AUTOMATION = (
    "브라우저를 흉내 내 로그인하고 글쓰기 화면을 조작하는 방식은 만들지 않습니다. "
    "네이버 약관 위반이라 계정이 정지됩니다."
)

#: 대가를 받은 유형. 유형마다 문구가 다르다.
SPONSOR_KINDS = ("none", "sponsored", "affiliate", "paid", "gift")

DISCLOSURE = {
    "sponsored": "이 글은 OO으로부터 원고료를 지급받아 작성한 광고 글입니다.",
    "affiliate": "이 글에는 제휴 링크가 포함되어 있으며, 구매 시 작성자가 "
                 "일정액의 수수료를 받습니다.",
    "paid": "이 글은 OO으로부터 대가를 받아 작성하였습니다.",
    "gift": "이 글은 OO으로부터 제품을 무상으로 제공받아 작성하였습니다.",
}

DISCLOSURE_RULES = (
    "본문 **맨 위**에 둡니다. 맨 아래나 '더보기' 안에 숨기면 표시한 것으로 보지 않습니다",
    "본문과 같은 크기·같은 색으로 씁니다. 작게 흐리게 쓰면 안 됩니다",
    "'체험단', '서포터즈' 같은 말만으로는 부족합니다. 무엇을 받았는지 적습니다",
    "해시태그 사이에 끼워 넣지 않습니다",
)


class DisclosureMissing(RuntimeError):
    """대가성 문구 없이 내보내려 할 때."""


def disclosure_for(kind: str, sponsor: str = "") -> str:
    """유형에 맞는 대가성 문구. 대가가 없으면 빈 문자열."""
    kind = (kind or "none").strip().lower()
    if kind in ("", "none"):
        return ""
    if kind not in DISCLOSURE:
        raise ValueError(
            f"모르는 유형입니다: {kind}\n"
            f"  쓸 수 있는 것: {', '.join(SPONSOR_KINDS)}")
    text = DISCLOSURE[kind]
    name = (sponsor or "").strip()
    return text.replace("OO", name) if name else text


def assert_disclosed(text: str, kind: str) -> None:
    """대가를 받은 글인데 문구가 없으면 막는다. **우회 경로를 두지 않는다.**"""
    kind = (kind or "none").strip().lower()
    if kind in ("", "none"):
        return
    body = text or ""
    # 문구의 고정 부분이 들어 있는지만 본다. 광고주 이름은 사람이 채운다.
    needles = {
        "sponsored": "원고료",
        "affiliate": "제휴 링크",
        "paid": "대가를 받아",
        "gift": "무상으로 제공받아",
    }
    if needles[kind] not in body:
        raise DisclosureMissing(
            f"대가를 받은 글({kind})인데 대가성 문구가 없습니다.\n"
            f"  넣어야 할 문구: {DISCLOSURE[kind]}\n"
            f"  빠뜨리면 표시광고법 위반입니다. 이 프로그램은 문구 없이 "
            f"산출물을 내보내지 않습니다")
