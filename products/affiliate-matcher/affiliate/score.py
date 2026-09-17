"""우선순위 점수 — 어디부터 붙일지 정한다.

계산은 세 가지를 곱한 것뿐이다.

    수수료율 × 객단가 = 1건 팔렸을 때 받는 돈 (expected_commission)
    거기에 구매 의도 가중치를 곱한 것 = 우선순위 점수 (score)

왜 이렇게 단순한가. **더 정교하게 만들 근거가 없기 때문이다.**
전환율을 알려면 본인 파트너스 화면의 실측이 있어야 하는데, 그건 이 프로그램이
가질 수 없는 값이다. 없는 정밀도를 흉내 내면 쓰는 사람이 그 숫자를 믿게 된다.

그래서 이 모듈은 두 가지를 지킨다.

    1. 모든 숫자에 **근거 문장이 붙는다.** 근거가 비면 프로그램이 멈춘다.
    2. 구매 의도 2 이하는 가중치가 **0** 이다. 점수가 낮은 게 아니라 아예 0 이다.
       본문과 무관한 상품을 끼워 넣는 것이 이 바닥에서 가장 빨리 신뢰를 잃는 길이라.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from affiliate.schema import Extraction, Mention, ScoredMention      # noqa: E402

__all__ = ["RateTable", "load_rates", "score_all", "DEFAULT_RATES_PATH"]

DEFAULT_RATES_PATH = Path(__file__).resolve().parent.parent / "data" / "commission_rates.yaml"


def _normalize(text: str) -> str:
    """카테고리 이름을 견주기 좋게 다듬는다. '패션/의류' 와 '패션의류' 는 같다."""
    return re.sub(r"[^0-9a-z가-힣]+", "", (text or "").lower())


@dataclass
class Category:
    name: str
    rate: float
    avg_price: int
    source: str
    note: str = ""


class RateTable:
    """수수료율 표. `data/commission_rates.yaml` 한 장이 원본이다."""

    def __init__(self, raw: dict) -> None:
        meta = raw.get("meta") or {}
        self.as_of: str = str(meta.get("as_of", ""))
        self.default_rate: float = float(meta.get("default_rate", 0.03))
        self.default_avg_price: int = int(meta.get("default_avg_price", 30000))
        self.default_source: str = str(meta.get("default_source", "")).strip()
        self.cookie_hours: int = int(meta.get("cookie_hours", 24))
        self.payout_note: str = str(meta.get("payout_note", "")).strip()

        self.categories: list[Category] = []
        for item in raw.get("categories") or []:
            source = str(item.get("source", "")).strip()
            if len(source) < 8:
                raise ValueError(
                    f"'{item.get('name')}' 에 근거(source)가 없습니다.\n"
                    "  근거 없는 수수료율은 넣지 않습니다. 어디서 온 숫자인지 모른 채"
                    " 그 숫자로 판단하게 되기 때문입니다.")
            self.categories.append(Category(
                name=str(item["name"]),
                rate=float(item["rate"]),
                avg_price=int(item["avg_price"]),
                source=source,
                note=str(item.get("note", "")).strip(),
            ))
        if not self.categories:
            raise ValueError("수수료율 표가 비어 있습니다")
        if len(self.default_source) < 8:
            raise ValueError("meta.default_source 가 없습니다. 기본값에도 근거가 필요합니다")

        weights = raw.get("intent_weights") or {}
        self.intent_weights = {int(k): float(v) for k, v in weights.items()}
        for level in range(1, 6):
            self.intent_weights.setdefault(level, 0.0)
        self.min_intent_for_plan = int(raw.get("min_intent_for_plan", 3))

    # ---------------------------------------------------------------- 조회
    def find(self, name: str) -> Category | None:
        """카테고리 이름으로 찾는다. 부분만 맞아도 받아 준다.

        Claude 가 '뷰티/미용' 처럼 조금 다르게 적어 올 수 있어서, 완전히 같은
        이름만 받으면 대부분 기본값으로 떨어진다.
        """
        target = _normalize(name)
        if not target:
            return None
        for category in self.categories:
            if _normalize(category.name) == target:
                return category
        for category in self.categories:
            key = _normalize(category.name)
            if key and (key in target or target in key):
                return category
        return None

    def weight(self, intent: int) -> float:
        return self.intent_weights.get(int(intent), 0.0)


def load_rates(path: str | Path = DEFAULT_RATES_PATH) -> RateTable:
    """표를 읽는다. 근거가 빠진 줄이 있으면 여기서 멈춘다."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"수수료율 표가 없습니다: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} 의 최상위는 키-값 매핑이어야 합니다")
    return RateTable(raw)


def score_one(mention: Mention, table: RateTable) -> ScoredMention:
    """언급 하나에 점수를 매긴다."""
    category = table.find(mention.category)
    if category is None:
        rate = table.default_rate
        avg_price = table.default_avg_price
        source = (f"표에 없는 카테고리('{mention.category}')라 기본값을 썼습니다. "
                  + table.default_source)
        matched = "(표에 없음 · 기본값)"
    else:
        rate, avg_price, source = category.rate, category.avg_price, category.source
        matched = category.name

    weight = table.weight(mention.intent)
    expected = int(round(avg_price * rate))
    score = round(expected * weight, 2)

    in_plan = mention.intent >= table.min_intent_for_plan and weight > 0
    excluded = ""
    if not in_plan:
        excluded = (f"구매 의도 {mention.intent} — 본문과 이어지지 않아 넣지 않습니다"
                    f" (기준 {table.min_intent_for_plan} 이상)")

    return ScoredMention(
        mention=mention,
        rate=rate,
        avg_price=avg_price,
        intent_weight=weight,
        expected_commission=expected,
        score=score,
        rate_source=source,
        matched_category=matched,
        in_plan=in_plan,
        excluded_because=excluded,
    )


def score_all(extraction: Extraction, table: RateTable) -> list[ScoredMention]:
    """뽑아낸 언급 전부에 점수를 매긴다. 점수 높은 순으로 돌려준다."""
    scored = [score_one(mention, table) for mention in extraction.mentions]
    scored.sort(key=lambda item: (item.score, item.mention.intent), reverse=True)
    return scored
