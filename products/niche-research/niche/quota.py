"""쿼터 관리 — 유튜브가 주는 하루치를 넘지 않게 **코드가 막는다**.

유튜브 데이터 API 는 하루 10,000 유닛을 준다. 값은 호출마다 다르다.

    search.list    100 유닛   ← 이게 거의 전부를 먹는다
    videos.list      1 유닛
    channels.list    1 유닛

키워드 하나를 보는 데 search 한 번(100) + videos 한 번(1) + channels 한 번(1)
= 약 102 유닛이다. 그래서 **하루 80개**를 상한으로 둔다. 8,160 유닛이고,
나머지는 다시 돌릴 여유로 남긴다.

왜 부탁이 아니라 강제인가
    쿼터를 넘기면 그날 남은 호출이 전부 거절된다. 수집이 하루 빠지면 그날의
    시계열에 구멍이 나고, 이 상품은 시계열이 전부다. 그래서 코드가 막는다.

넘치면 버리지 않고 **다음 날로 넘긴다**(`state.json`). 못 본 키워드가 다음 날
맨 앞에 선다. 그래야 순서가 한쪽으로 쏠리지 않는다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

__all__ = [
    "COSTS", "DAILY_UNITS", "DEFAULT_KEYWORD_LIMIT", "UNITS_PER_KEYWORD",
    "QuotaState", "plan_today", "QuotaExceeded",
]

#: 호출당 유닛. 유튜브가 바꾸면 여기만 고친다.
COSTS = {"search.list": 100, "videos.list": 1, "channels.list": 1}

#: 하루에 주어지는 유닛.
DAILY_UNITS = 10_000

#: 키워드 하나를 보는 데 드는 유닛.
UNITS_PER_KEYWORD = COSTS["search.list"] + COSTS["videos.list"] + COSTS["channels.list"]

#: 하루에 볼 키워드 수 상한. 넘으면 다음 날로 넘긴다.
DEFAULT_KEYWORD_LIMIT = int(os.getenv("DAILY_KEYWORD_LIMIT", "80"))

DEFAULT_STATE = "state.json"


class QuotaExceeded(RuntimeError):
    """오늘 몫을 다 썼을 때."""


@dataclass
class QuotaState:
    """오늘 얼마나 썼고 무엇이 밀렸는지. `state.json` 에 남는다."""

    path: Path
    day: str = ""
    used_units: int = 0
    done: list[str] = field(default_factory=list)      # 오늘 본 키워드
    carried: list[str] = field(default_factory=list)   # 다음 날로 넘긴 키워드
    limit: int = DEFAULT_KEYWORD_LIMIT

    # ------------------------------------------------------------ 읽고 쓰기
    @classmethod
    def load(cls, path: str | Path = DEFAULT_STATE,
             limit: int = DEFAULT_KEYWORD_LIMIT, today: str = "") -> "QuotaState":
        """상태를 읽는다. **날이 바뀌었으면 쓴 양을 0으로 되돌린다.**"""
        path = Path(path)
        today = today or date.today().isoformat()

        if not path.is_file():
            return cls(path=path, day=today, limit=limit)

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # 파일이 깨졌으면 새로 시작한다. 여기서 멈추면 수집이 하루 빠진다.
            return cls(path=path, day=today, limit=limit)

        state = cls(
            path=path,
            day=str(raw.get("day", "")),
            used_units=int(raw.get("used_units", 0)),
            done=list(raw.get("done", [])),
            carried=list(raw.get("carried", [])),
            limit=limit,
        )
        if state.day != today:
            # 새 날이다. 쓴 양과 '오늘 본 것' 만 비우고, 밀린 것은 그대로 둔다.
            state.day = today
            state.used_units = 0
            state.done = []
        return state

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "day": self.day,
            "used_units": self.used_units,
            "done": self.done,
            "carried": self.carried,
            "안내": (f"하루 {DAILY_UNITS:,} 유닛 중 {self.used_units:,} 유닛을 썼습니다. "
                    f"키워드 상한 {self.limit}개. 밀린 것은 다음 날 맨 앞에 섭니다."),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------------------------------------------------------- 계산
    @property
    def remaining_units(self) -> int:
        return max(0, DAILY_UNITS - self.used_units)

    @property
    def remaining_keywords(self) -> int:
        """오늘 더 볼 수 있는 키워드 수. 상한과 남은 유닛 중 **작은 쪽**."""
        by_limit = max(0, self.limit - len(self.done))
        by_units = self.remaining_units // UNITS_PER_KEYWORD
        return min(by_limit, by_units)

    def can_spend(self, call: str) -> bool:
        return self.remaining_units >= COSTS.get(call, 1)

    def spend(self, call: str) -> None:
        """유닛을 쓴다. 모자라면 멈춘다. **넘겨 쓰지 않는다.**"""
        cost = COSTS.get(call, 1)
        if self.remaining_units < cost:
            raise QuotaExceeded(
                f"오늘 몫을 다 썼습니다 ({self.used_units:,}/{DAILY_UNITS:,} 유닛).\n"
                "  내일 다시 돌리면 밀린 키워드부터 봅니다.\n"
                "  더 많이 보셔야 하면 구글 클라우드 콘솔에서 쿼터 증설을 신청하세요.")
        self.used_units += cost

    def finish(self, keyword: str) -> None:
        if keyword not in self.done:
            self.done.append(keyword)
        if keyword in self.carried:
            self.carried.remove(keyword)


def plan_today(keywords: list[str], state: QuotaState) -> tuple[list[str], list[str]]:
    """오늘 볼 것과 다음 날로 넘길 것을 나눈다.

    **밀린 것이 맨 앞에 선다.** 그래야 목록 뒤쪽 키워드가 영원히 안 보이는
    일이 생기지 않는다.

    Returns:
        (오늘 볼 키워드, 다음 날로 넘길 키워드)
    """
    cleaned = [word.strip() for word in keywords if word and word.strip()]
    seen: list[str] = []
    for word in state.carried + cleaned:
        if word not in seen and word in cleaned:
            seen.append(word)

    today = [word for word in seen if word not in state.done]
    room = state.remaining_keywords
    return today[:room], today[room:]
