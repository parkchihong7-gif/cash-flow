"""기획 초안 만들기 — Claude 한 번 부르고, 규칙으로 고치고 검사한다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from .rules import InputReview, Issue, review_plan
from .schema import PlanDraft

__all__ = ["Planner", "build_request", "PROMPT_PATH"]

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "plan.md"


def build_request(review: InputReview) -> dict:
    """Claude 에 넘길 요청. **쓰면 안 되는 것은 처음부터 넘기지 않는다** —
    출처 없는 이름, 출처 없는 가격은 여기서 빠진다."""
    data = review.data
    return {
        "celebrity": data.celebrity.strip() if review.name_allowed else "",
        "occasion": data.occasion.strip(),
        "duration_sec": data.duration_sec,
        "cta": data.cta,
        "items": [
            {
                "name": item.name,
                "brand": item.brand if review.item_mode(i) == "확인" else "",
                "mode": review.item_mode(i),
                "price": review.shown_price(i),
            }
            for i, item in enumerate(data.items)
        ],
    }


class Planner:
    def __init__(self, model: str, ask: Callable | None = None) -> None:
        self.model = model
        if ask is None:
            from shared.llm import ask as real_ask
            ask = real_ask
        self._ask = ask

    def run(self, review: InputReview) -> tuple[PlanDraft, list[Issue], list[str]]:
        request = build_request(review)
        system = PROMPT_PATH.read_text(encoding="utf-8")
        raw = self._ask(system, json.dumps(request, ensure_ascii=False),
                        model=self.model, max_tokens=4000, json_mode=True)
        try:
            draft = PlanDraft.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"기획 초안 모양이 맞지 않습니다: {exc.errors()[0]['msg']}") from exc
        return review_plan(draft, review)
