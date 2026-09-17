"""추출 결과의 규격.

Claude 가 뽑아 오는 것은 **언급 지점**이지 상품이 아니다. 이 구분이 중요하다.
"이 글은 이 대목에서 이런 물건 이야기를 하고 있다" 까지가 프로그램의 일이고,
무엇을 붙일지 정하는 것은 사람이다.

여기서 막는 것
    - 구매 의도 강도가 1~5 를 벗어나는 값
    - 키워드가 3개가 아닌 것 (검색을 세 갈래로 해 봐야 후보가 모인다)
    - 본문에 없는 문단을 가리키는 것 (없는 자리에 상품을 끼울 수는 없다)
    - **자가 구매를 부추기는 삽입 문장** — 파트너스 규정 위반이라 계정이 끊긴다
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from shared import banned_phrases                                   # noqa: E402

__all__ = [
    "Mention",
    "Extraction",
    "ScoredMention",
    "MatchResult",
    "SELF_PURCHASE",
    "self_purchase_hits",
    "slugify",
    "KEYWORD_COUNT",
]

#: 검색 키워드 개수. 세 갈래로 찾아야 후보가 모인다.
KEYWORD_COUNT = 3

#: 자가 구매 유도 표현. 쿠팡파트너스는 본인 구매를 금지하고, 걸리면 계정이 끊긴다.
#: 문장을 통째로 막지 않고 조각으로 잡는다. 표현이 조금씩 다르기 때문이다.
SELF_PURCHASE: tuple[str, ...] = (
    "제 링크로 사시면 제가",
    "본인 링크",
    "자기 링크로",
    "내 링크로 사",
    "셀프 구매",
    "자가 구매",
    "자기 구매",
    "본인 구매",
    "직접 구매하시고 수수료",
    "링크로 사고 캐시백",
    "수수료 나눠",
    "수수료 돌려",
    "페이백",
    "캐시백 드립니다",
)


def _squash(text: str) -> str:
    """띄어쓰기 변형을 무시하고 비교하기 위해 공백을 지운다."""
    return re.sub(r"\s+", "", text or "")


def self_purchase_hits(text: str) -> list[str]:
    """자가 구매를 부추기는 표현을 찾는다. 없으면 빈 목록."""
    squashed = _squash(text)
    return [phrase for phrase in SELF_PURCHASE if _squash(phrase) in squashed]


def slugify(text: str, fallback: str = "matches") -> str:
    """폴더 이름으로 쓸 수 있게 다듬는다. 한글은 그대로 둔다."""
    cleaned = re.sub(r"[^0-9A-Za-z가-힣]+", "-", (text or "").strip()).strip("-")
    return (cleaned[:40] or fallback).lower()


class Mention(BaseModel):
    """본문에서 상품 이야기가 나온 자리 하나."""

    model_config = {"extra": "forbid"}

    paragraph: int = Field(ge=0, description="본문 문단 번호. 0 부터 센다")
    context: str = Field(min_length=5, description="그 자리의 문맥 문장")
    category: str = Field(min_length=2, description="쿠팡 카테고리 명칭")
    keywords: list[str] = Field(description=f"검색 키워드 {KEYWORD_COUNT}개")
    intent: int = Field(ge=1, le=5, description="구매 의도 강도")
    insert_sentence: str = Field(min_length=5, description="자연스러운 삽입 문장 제안")
    reason: str = Field(default="", description="왜 이 강도로 봤는지")

    @field_validator("keywords")
    @classmethod
    def _three_keywords(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if len(cleaned) != KEYWORD_COUNT:
            raise ValueError(f"검색 키워드는 정확히 {KEYWORD_COUNT}개여야 합니다 "
                             f"(받은 개수: {len(cleaned)})")
        if len(set(cleaned)) != KEYWORD_COUNT:
            raise ValueError("검색 키워드가 서로 겹칩니다. 세 갈래로 다르게 주세요")
        return cleaned

    @field_validator("insert_sentence")
    @classmethod
    def _no_self_purchase(cls, value: str) -> str:
        hits = self_purchase_hits(value)
        if hits:
            raise ValueError(f"자가 구매를 부추기는 표현이 있습니다: {', '.join(hits)}")
        found = banned_phrases.check(value)
        if found:
            raise ValueError(f"쓰면 안 되는 표현이 있습니다: {', '.join(found)}")
        return value.strip()

    @property
    def strong(self) -> bool:
        """본문과 실제로 이어진 언급인가. 약하면 끼워넣기가 된다."""
        return self.intent >= 3


class Extraction(BaseModel):
    """한 편의 글에서 뽑아낸 것 전부."""

    model_config = {"extra": "forbid"}

    title: str = Field(default="", description="글 제목(있으면)")
    summary: str = Field(default="", description="이 글이 무엇에 대한 글인지 한 줄")
    medium: str = Field(default="블로그", description="대본·블로그·릴스 캡션 중 무엇인지")
    mentions: list[Mention] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sorted_by_paragraph(self) -> "Extraction":
        self.mentions.sort(key=lambda item: (item.paragraph, -item.intent))
        return self

    def within(self, paragraph_count: int) -> "Extraction":
        """본문에 없는 문단을 가리키는 언급을 걷어낸다."""
        self.mentions = [m for m in self.mentions if m.paragraph < paragraph_count]
        return self


class ScoredMention(BaseModel):
    """점수를 매긴 언급 하나. `score.py` 가 만든다."""

    model_config = {"extra": "forbid"}

    mention: Mention
    rate: float = Field(ge=0, le=1, description="카테고리 수수료율")
    avg_price: int = Field(ge=0, description="객단가 추정")
    intent_weight: float = Field(ge=0, le=1)
    expected_commission: int = Field(ge=0, description="1건 팔렸을 때 수수료 추정")
    score: float = Field(ge=0, description="우선순위 점수")
    rate_source: str = Field(description="수수료율의 근거. 비울 수 없다")
    matched_category: str = Field(description="표에서 실제로 맞은 카테고리")
    in_plan: bool = Field(description="insert_plan 에 넣을지")
    excluded_because: str = Field(default="")

    @field_validator("rate_source")
    @classmethod
    def _source_required(cls, value: str) -> str:
        if len((value or "").strip()) < 8:
            raise ValueError("수수료율에는 근거가 필요합니다. 근거 없는 숫자는 위험합니다")
        return value.strip()


class LinkCandidate(BaseModel):
    """붙일 수 있는 링크 후보 하나."""

    model_config = {"extra": "forbid"}

    keyword: str
    kind: str = Field(description="api | search_url | youtube_shopping")
    title: str = ""
    url: str
    price: int = 0
    image: str = ""
    is_rocket: bool = False
    needs_api_key: bool = False
    note: str = ""


class MatchResult(BaseModel):
    """matches.json 의 전체 모양."""

    model_config = {"extra": "forbid"}

    disclosure: str = Field(description="대가성 문구. 비면 저장하지 않는다")
    source_file: str = ""
    title: str = ""
    summary: str = ""
    medium: str = ""
    paragraph_count: int = 0
    generated_at: str = ""
    rates_as_of: str = ""
    dry_run: bool = False
    api_used: bool = False
    matches: list[ScoredMention] = Field(default_factory=list)
    links: dict[str, list[LinkCandidate]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("disclosure")
    @classmethod
    def _disclosure_required(cls, value: str) -> str:
        if len((value or "").strip()) < 20:
            raise ValueError("대가성 문구 없이는 결과를 만들 수 없습니다")
        return value

    @property
    def planned(self) -> list[ScoredMention]:
        """insert_plan 에 실제로 들어가는 것만, 점수 높은 순으로."""
        return sorted((m for m in self.matches if m.in_plan),
                      key=lambda m: m.score, reverse=True)
