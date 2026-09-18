"""절감 — **공짜 절감은 없다.** 무엇을 내주고 얼마를 아끼는지 같이 적는다.

"비용 최적화" 를 파는 도구가 흔히 하는 거짓말이 "품질 그대로 비용만 절반" 이다.
대부분은 뭔가를 내준다. 이 모듈은 아낀 돈과 **그 대가**를 나란히 놓는다.
대가를 감수할지는 사는 사람이 정한다.

한 가지 예외가 캐시다. 같은 문장을 두 번 읽히지 않는 것은 정말로 공짜다.
채널 인사말·구독 요청처럼 매 편 똑같이 들어가는 문장이 있기 때문이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from senior_video.estimate import Estimate, VideoPlan
from senior_video.rates import RateTable

__all__ = ["Saving", "suggest", "INTRO_OUTRO_CHARS", "apply_cache"]

#: 매 편 똑같이 들어가는 인사말·마무리 멘트의 대략 길이.
#: 두 번째 편부터는 만들어 둔 음성 파일을 그대로 쓰면 된다.
INTRO_OUTRO_CHARS = 220


@dataclass
class Saving:
    """절감 수단 하나."""

    key: str
    title: str
    monthly_won: float
    how: str
    cost: str
    senior_safe: bool = True

    @property
    def yearly_won(self) -> float:
        return round(self.monthly_won * 12, 1)

    @property
    def worth_it(self) -> bool:
        """연 3만 원은 아껴야 손댈 값어치가 있다고 본다."""
        return self.yearly_won >= 30000


def apply_cache(plan: VideoPlan) -> int:
    """캐시를 쓰면 실제로 읽혀야 하는 글자 수."""
    return max(0, plan.script_chars - INTRO_OUTRO_CHARS)


def suggest(est: Estimate, rates: RateTable) -> list[Saving]:
    """이 기획에서 실제로 쓸 수 있는 절감 수단만 고른다. 큰 것부터."""
    plan = est.plan
    monthly = plan.monthly_videos
    current_tts = rates.pick("tts", plan.tts)
    out: list[Saving] = []

    # 1) 캐시 — 대가가 없는 유일한 절감
    if current_tts.won > 0 and plan.script_chars > INTRO_OUTRO_CHARS:
        saved = round(INTRO_OUTRO_CHARS / 1000 * current_tts.won * monthly, 1)
        out.append(Saving(
            key="cache", title="인사말·마무리 음성 재사용",
            monthly_won=saved,
            how=f"매 편 똑같이 들어가는 {INTRO_OUTRO_CHARS}자를 한 번만 만들어 "
                f"파일로 두고 붙입니다",
            cost="없습니다. 어차피 같은 문장입니다"))

    # 2) 음성 엔진 — 가장 큰 줄이지만 대가가 있다
    cheaper = [row for row in rates.tts if row.won < current_tts.won]
    for row in sorted(cheaper, key=lambda r: r.won)[:2]:
        saved = round((current_tts.won - row.won) / 1000 * plan.script_chars * monthly, 1)
        drop = current_tts.senior_fit - row.senior_fit
        out.append(Saving(
            key=f"tts:{row.key}", title=f"음성을 {row.name} 로 바꾸기",
            monthly_won=saved,
            how=f"{current_tts.name} → {row.name}",
            cost=(f"시니어 적합도가 {current_tts.senior_fit}에서 {row.senior_fit}로 "
                  f"떨어집니다. {row.note}" if drop > 0
                  else f"품질은 {row.quality} 입니다. {row.note}"),
            senior_safe=drop <= 0))

    # 3) 이미지
    current_image = rates.pick("image", plan.image_source)
    if current_image.won > 0:
        free = rates.cheapest("image")
        saved = round((current_image.won - free.won) * plan.images * monthly, 1)
        if saved > 0:
            out.append(Saving(
                key="image", title=f"이미지를 {free.name} 로 바꾸기",
                monthly_won=saved,
                how=f"{current_image.name} → {free.name}",
                cost="라이선스를 한 장씩 확인해야 합니다. 상업적 이용 가능 표기를 보세요"))

    # 4) 대본
    current_script = rates.pick("script", plan.script_source)
    if current_script.won > 200:
        cheap = min(rates.script, key=lambda r: r.won if r.won > 0 else 9e9)
        saved = round((current_script.won - cheap.won) * monthly, 1)
        if saved > 0:
            out.append(Saving(
                key="script", title=f"대본을 {cheap.name} 로 바꾸기",
                monthly_won=saved,
                how=f"{current_script.name} → {cheap.name}",
                cost="기획이 복잡한 편에서는 품질 차이가 납니다. "
                     "첫 기획만 상위 모델로 잡고 나머지는 내려도 됩니다"))

    # 5) 편수 — 대가가 가장 큰 선택이라 맨 뒤에 둔다
    if monthly > 12 and est.per_video > 0:
        cut = monthly // 3
        out.append(Saving(
            key="volume", title=f"월 {monthly}편을 {monthly - cut}편으로 줄이기",
            monthly_won=round(est.per_video * cut, 1),
            how="편수를 줄이고 편당 공을 더 들입니다",
            cost="업로드가 줄면 노출도 줄 수 있습니다. 다만 사람 검수 시간이 "
                 "늘어 품질은 올라갑니다. 양산은 유튜브 정책상으로도 위험합니다"))

    return sorted(out, key=lambda item: -item.monthly_won)
