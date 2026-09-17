"""해석 — Claude 는 **여기서만** 말을 한다.

시키는 것
    숫자 해석 3줄 + 다음 주에 할 일 2가지.

시키지 않는 것
    **계산.** 합계도, 비율도, 증감도 시키지 않는다. 이미 pandas 가 냈다.

왜 굳이 막는가
    모델이 더한 숫자는 사람이 검산할 수 없다. 보고서에 적힌 값이 시트와 다르면
    그 보고서는 한 번에 못 쓰게 되고, 대행 계약도 거기서 끝난다.

어떻게 막는가
    1. 지시로 막는다 — "주어진 값만 그대로 인용하라"
    2. **뒤에서 확인한다** — 나온 글의 숫자가 집계에 있던 값인지 대조한다.
       없는 숫자가 있으면 한 번 더 시키고, 그래도 남으면 그 사실을 보고서에 적는다.
       조용히 넘어가지 않는다.
"""

from __future__ import annotations

import re

__all__ = ["NARRATE_SYSTEM", "unknown_numbers", "Narration", "narrate", "MAX_RETRY"]

MAX_RETRY = 1

#: 글에서 숫자를 뽑는 모양. 천 단위 쉼표와 소수점을 허용한다.
NUMBER = re.compile(r"\d[\d,]*\.?\d*")

#: 대조하지 않는 숫자. 순위·개수처럼 글에서 자연스럽게 나오는 작은 수.
IGNORED = {str(n) for n in range(0, 13)}

NARRATE_SYSTEM = """당신은 소상공인 사장님에게 주간 보고를 하는 담당자다.

주어진 **집계 결과만** 보고 쓴다.

절대 하지 않는 것
  - 계산하지 않는다. 더하기·나누기·비율 계산을 하지 마라
  - 주어지지 않은 숫자를 쓰지 마라. 추정치도 쓰지 마라
  - 숫자를 쓸 때는 주어진 값을 **그대로** 옮겨라

쓸 것
  1. 해석 3줄 — 숫자가 무슨 뜻인지. 숫자를 다시 읽어 주는 게 아니라
     "무엇 때문에 이렇게 됐을 수 있는지" 를 말한다. 단정하지 말고
     "~로 보입니다", "~일 수 있습니다" 로 쓴다
  2. 다음 주 할 일 2가지 — 사장님이 **이번 주에 실제로 할 수 있는** 일.
     "마케팅 강화" 같은 말은 쓰지 마라. "월요일에 A채널 재고 20개 채우기" 처럼
     오늘 달력에 적을 수 있는 일로 쓴다

말투
  존댓말. 짧게. 한 줄에 한 가지만.

출력 형식 (JSON 하나만)
{
  "reading": ["해석 1줄", "해석 2줄", "해석 3줄"],
  "actions": ["할 일 1", "할 일 2"],
  "caution": "이 숫자만으로는 알 수 없는 것 한 줄"
}"""


def unknown_numbers(text: str, allowed: set[str]) -> list[str]:
    """글에 있는데 집계에는 없던 숫자를 찾는다.

    쉼표가 있든 없든 같은 값으로 본다. 작은 수(0~12)는 순위·개수라서 뺀다.
    """
    found: list[str] = []
    for raw in NUMBER.findall(text or ""):
        cleaned = raw.rstrip(".")
        if not cleaned:
            continue
        bare = cleaned.replace(",", "")
        if bare in IGNORED or cleaned in IGNORED:
            continue
        # 소수점 아래 0 만 다른 경우도 같은 값으로 본다
        candidates = {cleaned, bare, bare.rstrip("0").rstrip(".")}
        try:
            number = float(bare)
            candidates.add(f"{number:,.0f}")
            candidates.add(f"{number:.1f}")
            candidates.add(str(int(number)))
        except ValueError:
            pass
        if not (candidates & allowed):
            found.append(cleaned)
    return found


class Narration:
    """해석 결과. 확인 결과도 함께 들고 다닌다."""

    def __init__(self, reading: list[str], actions: list[str], caution: str = "",
                 warnings: list[str] | None = None, tries: int = 1,
                 numbers_ok: bool = True) -> None:
        self.reading = reading
        self.actions = actions
        self.caution = caution
        self.warnings = warnings or []
        self.tries = tries
        #: 숫자 대조를 통과했는가. **경고 유무와 따로 둔다.**
        #: "2번째에 맞았습니다" 같은 알림까지 실패로 세면, 고쳐서 맞은 것과
        #: 끝내 못 맞춘 것을 구분할 수 없게 된다.
        self.numbers_ok = numbers_ok

    @property
    def verified(self) -> bool:
        """지어낸 숫자가 없는가."""
        return self.numbers_ok

    def as_text(self) -> str:
        return "\n".join(self.reading + self.actions + [self.caution])


def _clean_list(value, limit: int) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


def narrate(aggregate, ask_fn, model: str) -> Narration:
    """집계를 받아 해석 3줄과 할 일 2가지를 받아 온다.

    Args:
        aggregate: `aggregate.Aggregate`.
        ask_fn: `shared.llm.ask` 같은 함수.
        model: 쓸 모델.
    """
    facts = "\n".join(aggregate.facts())
    allowed = aggregate.numbers()
    user = f"[집계 결과]\n{facts}\n\n위 값만 써서 해석 3줄과 할 일 2가지를 내라."

    warnings: list[str] = []
    last: Narration | None = None

    for attempt in range(1, MAX_RETRY + 2):
        raw = ask_fn(NARRATE_SYSTEM, user, model=model, json_mode=True)
        if not isinstance(raw, dict):
            raw = {}

        narration = Narration(
            reading=_clean_list(raw.get("reading"), 3),
            actions=_clean_list(raw.get("actions"), 2),
            caution=str(raw.get("caution") or "").strip(),
            tries=attempt,
        )
        last = narration

        made_up = unknown_numbers(narration.as_text(), allowed)
        if not made_up:
            if attempt > 1:
                narration.warnings.append(f"{attempt}번째 시도에 숫자가 맞았습니다")
            return narration

        warnings = [f"집계에 없는 숫자가 나왔습니다: {', '.join(made_up[:5])}"]
        if attempt > MAX_RETRY:
            break
        user = (f"[집계 결과]\n{facts}\n\n"
                f"앞선 답에 주어지지 않은 숫자({', '.join(made_up[:5])})가 들어갔다. "
                "계산하지 말고 위 값만 그대로 인용해 다시 써라.")

    # 두 번 시켜도 안 되면 그대로 두되 **보고서에 그 사실을 적는다.**
    narration = last or Narration(reading=[], actions=[])
    narration.numbers_ok = False
    narration.warnings = warnings + [
        "⚠ 해석 문장의 숫자를 집계와 대조하지 못했습니다. 보내기 전에 눈으로 확인하세요"]
    return narration
