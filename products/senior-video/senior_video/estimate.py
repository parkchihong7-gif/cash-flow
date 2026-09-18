"""비용 견적 — 영상 한 편에 얼마 드는지.

이 상품의 쓸모는 "얼마 드나" 보다 **"어디서 새나"** 에 있다. 대개 돈은
음성에서 샌다. 대본 1,500자짜리 영상을 월 30편 만들면 음성만 글자 수로
45,000자다. 엔진을 바꾸면 그 줄이 통째로 달라진다.

그래서 견적은 항목별로 쪼개서 보여 주고, 가장 큰 줄을 짚는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from senior_video.rates import Rate, RateTable

__all__ = ["VideoPlan", "Line", "Estimate", "estimate", "SYLLABLE_PER_CHAR"]

#: 한국어는 한 글자가 대체로 한 음절이다. 말 속도 계산에 쓴다.
SYLLABLE_PER_CHAR = 1.0


@dataclass
class VideoPlan:
    """영상 한 편의 기획 수치."""

    title: str = "제목 미정"
    script_chars: int = 1500
    images: int = 12
    monthly_videos: int = 20
    tts: str = "clova"
    image_source: str = "stock-free"
    script_source: str = "claude-sonnet"
    # 시니어 규격 확인용 값. 없어도 견적은 나온다.
    subtitle_px: int | None = None
    subtitle_chars: int | None = None
    speech_rate: int | None = None
    bgm_db: int | None = None
    scene_seconds: float | None = None
    contrast: float | None = None
    length_minutes: float | None = None

    def as_check(self) -> dict:
        return {
            "subtitle_px": self.subtitle_px,
            "subtitle_chars": self.subtitle_chars,
            "speech_rate": self.speech_rate,
            "bgm_db": self.bgm_db,
            "scene_seconds": self.scene_seconds,
            "contrast": self.contrast,
            "length_minutes": self.length_minutes,
        }

    @property
    def estimated_minutes(self) -> float:
        """대본 길이로 어림잡은 영상 길이. 분당 300음절 기준."""
        rate = self.speech_rate or 300
        return round(self.script_chars * SYLLABLE_PER_CHAR / max(rate, 1), 1)


@dataclass
class Line:
    """견적서 한 줄."""

    key: str
    label: str
    detail: str
    won: float
    source: str = ""

    @property
    def monthly(self) -> float:
        return self.won


@dataclass
class Estimate:
    """견적 결과."""

    plan: VideoPlan
    lines: list[Line] = field(default_factory=list)
    asof: str = ""

    @property
    def per_video(self) -> float:
        return round(sum(line.won for line in self.lines), 1)

    @property
    def per_month(self) -> float:
        return round(self.per_video * self.plan.monthly_videos, 1)

    @property
    def per_year(self) -> float:
        return round(self.per_month * 12, 1)

    @property
    def biggest(self) -> Line | None:
        """가장 큰 줄. 여기를 건드려야 의미가 있다."""
        paid = [line for line in self.lines if line.won > 0]
        return max(paid, key=lambda line: line.won) if paid else None

    #: 바깥에 돈을 내는 줄. 전기값은 여기 안 든다.
    BILLED = ("tts", "image", "script")

    @property
    def billed(self) -> float:
        """청구서가 날아오는 금액. 전기값은 뺀다."""
        return round(sum(line.won for line in self.lines
                         if line.key in self.BILLED), 1)

    @property
    def free(self) -> bool:
        """어디에도 돈을 안 내는가. 전기값은 청구서가 아니라 제외한다."""
        return self.billed <= 0

    def share(self, line: Line) -> float:
        return round(line.won / self.per_video * 100, 1) if self.per_video else 0.0


def _tts_line(plan: VideoPlan, rate: Rate) -> Line:
    won = round(plan.script_chars / 1000 * rate.won, 1)
    return Line(
        key="tts", label=f"음성 — {rate.name}",
        detail=f"{plan.script_chars:,}자 × {rate.won:,.1f}원/1,000자",
        won=won, source=rate.source)


def _image_line(plan: VideoPlan, rate: Rate) -> Line:
    won = round(plan.images * rate.won, 1)
    return Line(
        key="image", label=f"이미지 — {rate.name}",
        detail=f"{plan.images}장 × {rate.won:,.0f}원",
        won=won, source=rate.source)


def _script_line(plan: VideoPlan, rate: Rate) -> Line:
    return Line(
        key="script", label=f"대본 — {rate.name}",
        detail=f"1편 기준 {rate.won:,.0f}원",
        won=round(rate.won, 1), source=rate.source)


def estimate(plan: VideoPlan, rates: RateTable) -> Estimate:
    """기획 수치와 단가표로 견적을 낸다."""
    lines = [
        _tts_line(plan, rates.pick("tts", plan.tts)),
        _image_line(plan, rates.pick("image", plan.image_source)),
        _script_line(plan, rates.pick("script", plan.script_source)),
        Line(key="render", label="렌더 — 전기값",
             detail="10분 영상 1편 기준", won=rates.render_won,
             source="대략값"),
    ]
    return Estimate(plan=plan, lines=lines, asof=rates.asof)
