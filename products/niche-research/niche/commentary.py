"""해설 5줄 — Claude 는 **지표만 읽는다.**

무엇을 주는가
    키워드 이름과 숫자뿐이다. **영상 제목도 채널명도 주지 않는다.**
    줄 수 있어도 주지 않는다. 주는 순간 "이 채널처럼 만드세요" 라는 말이
    나오고, 그게 노아AI 가 닫힌 이유다(CLAUDE.md §3-1).

무엇을 시키는가
    숫자가 무슨 뜻인지 5줄. 그게 전부다.

무엇을 막는가
    - 특정 영상·채널을 따라 만들라는 제안
    - 조회수 예측
    - 성과 단정

    프롬프트로 막고, 받은 글도 **뒤에서 한 번 더 검사한다.** 걸리면 그 줄을
    버리고 규칙으로 쓴 문장으로 갈아 끼운다. 조용히 통과시키지 않는다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from shared import banned_phrases                                    # noqa: E402

__all__ = ["COMMENTARY_SYSTEM", "commentary_for", "offline_commentary",
           "copycat_hits", "COPYCAT"]

#: 표절을 부추기는 말. 해설에 나오면 그 줄을 버린다.
COPYCAT: tuple[str, ...] = (
    "따라 만드", "그대로 만드", "베끼", "복제", "똑같이 만드", "모방",
    "리메이크", "재업로드", "같은 영상을 만드", "이 채널처럼", "이 영상처럼",
    "벤치마킹해서 그대로",
)

COMMENTARY_SYSTEM = """당신은 유튜브 시장 지표를 읽어 주는 분석가다.

받은 것은 **키워드별 숫자뿐**이다. 영상 제목도 채널 이름도 없다.
그것만으로 5줄을 쓴다.

각 줄은
  - 숫자 하나를 짚고, 그게 무슨 뜻인지 말한다
  - 단정하지 않는다. "~로 보입니다", "~일 수 있습니다"
  - 한 줄에 한 가지만

절대 하지 않는 것
  - **특정 영상이나 채널을 따라 만들라는 제안** (이 도구는 그런 도구가 아니다)
  - 조회수·구독자 수 예측
  - "이렇게 하면 터진다" 같은 단정
  - 주어지지 않은 숫자 지어내기

지표 읽는 법
  - 공백 지수: 중앙값 조회수 ÷ 신규 영상 수. 높을수록 보는 사람 대비 만드는
    사람이 적다
  - 소형 채널 성과율: 구독자 1만 이하 채널이 구독자의 5배 넘게 본 비율.
    **높으면 새로 들어갈 여지가 있다**
  - 공급 증가율: 남들이 들어오고 있는지
  - 쇼츠 비중: 어떤 포맷이 도는 시장인지

출력은 JSON 하나만.
{"lines": ["1줄", "2줄", "3줄", "4줄", "5줄"]}"""


def copycat_hits(text: str) -> list[str]:
    """표절을 부추기는 말이 있는지 본다."""
    squashed = re.sub(r"\s+", "", text or "")
    return [word for word in COPYCAT if re.sub(r"\s+", "", word) in squashed]


def _facts(metrics: list, days: int) -> str:
    """Claude 에게 줄 것. **숫자와 키워드뿐이다.**"""
    lines = [f"모은 날수: {days}일"]
    for item in metrics:
        lines.append(
            f"- {item.keyword}: 신규 영상 {item.videos}편, "
            f"중앙값 조회수 {item.median_views:,}, 공백 지수 {item.gap:,.1f}, "
            f"소형 채널 성과율 {item.breakout_rate:.1f}%, "
            f"쇼츠 비중 {item.shorts_ratio:.1f}%, "
            f"공급 증가율 {item.supply_growth:+.1f}%, "
            f"채널 성장률 {item.channel_growth:+.2f}%")
    return "\n".join(lines)


def offline_commentary(metrics: list, days: int) -> list[str]:
    """Claude 없이 규칙으로 쓰는 해설. 모의 실행과 폴백에 쓴다."""
    if not metrics:
        return ["아직 읽을 자료가 없습니다."]

    top = metrics[0]
    friendly = [item for item in metrics if item.entry_friendly]
    crowded = max(metrics, key=lambda item: item.videos)
    shorts_heavy = max(metrics, key=lambda item: item.shorts_ratio)
    growing = max(metrics, key=lambda item: item.supply_growth)

    lines = [
        f"공백 지수가 가장 높은 것은 '{top.keyword}' 입니다"
        f"({top.gap:,.1f}). 보는 사람 대비 만드는 사람이 적은 쪽으로 보입니다.",
        (f"'{crowded.keyword}' 은 최근 30일 신규 영상이 {crowded.videos}편으로 "
         "가장 많습니다. 이미 사람이 몰린 자리일 수 있습니다."),
        (f"소형 채널이 뚫고 있는 키워드는 {', '.join(item.keyword for item in friendly)}"
         " 입니다. 새로 들어갈 여지가 있다는 신호로 읽힙니다."
         if friendly else
         "구독자 1만 이하 채널이 크게 뚫은 키워드가 없습니다. "
         "지금은 자리가 굳어 있는 편으로 보입니다."),
        (f"'{shorts_heavy.keyword}' 은 쇼츠 비중이 {shorts_heavy.shorts_ratio:.1f}% 로 "
         "가장 높습니다. 어느 포맷이 도는 시장인지 참고하세요."),
        (f"'{growing.keyword}' 의 공급 증가율이 {growing.supply_growth:+.1f}% 입니다. "
         "남들도 들어오고 있는지 지켜볼 만합니다."
         if days >= 3 else
         f"아직 {days}일치라 추이 지표는 뜻이 약합니다. 2주쯤 모은 뒤에 보세요."),
    ]
    return lines


def commentary_for(metrics: list, days: int, ask_fn, model: str) -> list[str]:
    """Claude 에게 해설 5줄을 받는다. 걸리는 줄은 규칙 문장으로 갈아 끼운다."""
    if not metrics:
        return offline_commentary(metrics, days)

    user = (f"[지표]\n{_facts(metrics, days)}\n\n"
            "위 숫자만 읽어 5줄을 쓰라. 영상이나 채널을 따라 만들라는 말은 하지 마라.")

    raw = ask_fn(COMMENTARY_SYSTEM, user, model=model, json_mode=True)
    lines = []
    if isinstance(raw, dict):
        lines = [str(item).strip() for item in (raw.get("lines") or []) if str(item).strip()]

    fallback = offline_commentary(metrics, days)
    cleaned: list[str] = []
    for index, line in enumerate(lines[:5]):
        if copycat_hits(line) or banned_phrases.check(line):
            # 표절을 부추기거나 성과를 단정하는 줄은 버린다. 고쳐 쓰지 않고
            # 규칙으로 쓴 문장으로 바꾼다 — 고쳐 쓰면 또 비슷한 말이 나온다.
            cleaned.append(fallback[index % len(fallback)])
        else:
            cleaned.append(line)

    return cleaned or fallback
