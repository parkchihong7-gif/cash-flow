"""script_input.yaml 스키마와 포맷별 타임코드 계산."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = [
    "ScriptInput", "load_input", "Segment", "shorts_segments", "long_segments",
    "timecode", "FORMAT_LABEL", "TONE_LABEL", "CTA_LABEL",
    "SHORTS_CAPTION_LIMIT", "TITLE_LIMIT", "THUMBNAIL_LIMIT",
]

Format = Literal["long", "shorts", "reels"]
Tone = Literal["정보형", "스토리형", "반전형"]
Cta = Literal["구독", "링크", "댓글"]

FORMAT_LABEL = {"long": "롱폼", "shorts": "쇼츠", "reels": "릴스"}
TONE_LABEL = {
    "정보형": "사실과 근거를 앞세워 설명한다. 감정 표현을 절제한다.",
    "스토리형": "한 사람의 경험을 시간 순서로 따라간다. 장면이 보이게 쓴다.",
    "반전형": "흔히 믿는 것을 먼저 말하고 그것이 왜 다른지 뒤집는다.",
}
CTA_LABEL = {
    "구독": "구독과 알림 설정을 요청한다",
    "링크": "설명란 링크로 이동을 요청한다",
    "댓글": "구체적인 질문을 던져 댓글을 요청한다",
}

#: 쇼츠·릴스 자막 한 줄 최대 글자 수. 화면에서 한 번에 읽히는 한계.
SHORTS_CAPTION_LIMIT = 15
#: 제목 최대 글자 수.
TITLE_LIMIT = 40
#: 썸네일 문구 최대 글자 수.
THUMBNAIL_LIMIT = 12

_SLUG_STRIP_RE = re.compile(r"[^0-9a-z가-힣]+")

#: 포맷별 허용 길이 (초).
DURATION_RANGE = {"shorts": (15, 60), "reels": (15, 60), "long": (300, 1200)}


class ScriptInput(BaseModel):
    """대본 한 편을 만드는 데 필요한 입력."""

    model_config = {"extra": "forbid"}

    topic: str = Field(min_length=1, description="다룰 주제")
    format: Format = Field(description="long | shorts | reels")
    duration_sec: int = Field(description="쇼츠·릴스 15~60초, 롱폼 300~1200초")
    audience: str = Field(min_length=1, description="누가 보는 영상인지 한 줄")
    tone: Tone = "정보형"
    cta: Cta = "구독"
    evidence: list[str] = Field(
        default_factory=list,
        description="참고할 사실 자료. 비우면 대본에 수치·출처를 만들어 넣지 않는다",
    )

    @field_validator("topic", "audience")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("빈 값일 수 없습니다")
        return value.strip()

    @field_validator("evidence")
    @classmethod
    def _clean_evidence(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values if item and item.strip()]
        if len(cleaned) != len(values):
            raise ValueError("빈 항목이 섞여 있습니다")
        return cleaned

    @model_validator(mode="after")
    def _duration_in_range(self) -> "ScriptInput":
        low, high = DURATION_RANGE[self.format]
        if not low <= self.duration_sec <= high:
            raise ValueError(
                f"{FORMAT_LABEL[self.format]} 의 duration_sec 은 {low}~{high}초여야 합니다 "
                f"(입력: {self.duration_sec})"
            )
        return self

    @property
    def is_short_form(self) -> bool:
        return self.format in {"shorts", "reels"}

    @property
    def slug(self) -> str:
        normalized = unicodedata.normalize("NFC", self.topic).lower()
        base = _SLUG_STRIP_RE.sub("-", normalized).strip("-") or "script"
        return f"{base}-{self.format}-{self.duration_sec}s"

    @property
    def format_label(self) -> str:
        return FORMAT_LABEL[self.format]


def load_input(path: str | Path) -> ScriptInput:
    """YAML 을 읽어 검증된 :class:`ScriptInput` 으로 돌려준다."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"입력 파일이 없습니다: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} 의 최상위는 키-값 매핑이어야 합니다")
    return ScriptInput(**raw)


# ------------------------------------------------------------------ 타임코드
@dataclass
class Segment:
    """대본의 한 구간."""

    key: str
    label: str
    start: int
    end: int
    instruction: str = ""
    #: True 면 M:SS 로 표기한다. 롱폼은 전 구간을 타임코드로 통일한다.
    timecoded: bool = False

    @property
    def seconds(self) -> int:
        return self.end - self.start

    @property
    def range_text(self) -> str:
        if self.timecoded or self.end >= 60:
            return f"{timecode(self.start)}~{timecode(self.end)}"
        return f"{self.start}~{self.end}초"


def timecode(seconds: int) -> str:
    """초를 M:SS 로."""
    return f"{seconds // 60}:{seconds % 60:02d}"


def shorts_segments(duration: int) -> list[Segment]:
    """쇼츠·릴스 구간. 길이에 비례해 나눈다.

    30초면 [0~3 후크] [3~8 문제] [8~26 핵심 3포인트] [26~30 CTA] 가 된다.
    """
    hook_end = min(3, max(2, round(duration * 0.2)))
    problem_end = hook_end + max(3, round(duration * 0.15))
    cta_seconds = min(5, max(2, round(duration * 0.12)))
    cta_start = max(problem_end + 3, duration - cta_seconds)

    core_span = cta_start - problem_end
    step = core_span / 3
    points = [
        Segment(
            key=f"point{i + 1}",
            label=f"핵심 포인트 {i + 1}",
            start=round(problem_end + step * i),
            end=round(problem_end + step * (i + 1)),
        )
        for i in range(3)
    ]

    return [
        Segment("hook", "후크", 0, hook_end, "첫 문장에서 손가락을 멈추게 한다"),
        Segment("problem", "문제 제기", hook_end, problem_end, "보는 사람의 상황을 그대로 되비춘다"),
        *points,
        Segment("cta", "CTA", cta_start, duration, "행동 하나만 요청한다"),
    ]


def long_segments(duration: int, chapters: int = 6) -> list[Segment]:
    """롱폼 구간. 후크 30초 + 약속 30초 + 챕터 + 요약 60초 + CTA 30초."""
    chapters = max(5, min(7, chapters))
    hook_end, promise_end = 30, 60
    cta_start = duration - 30
    summary_start = cta_start - 60
    chapter_span = summary_start - promise_end
    step = chapter_span / chapters

    chapter_segments = [
        Segment(
            key=f"chapter{i + 1}",
            label=f"챕터 {i + 1}",
            start=round(promise_end + step * i),
            end=round(promise_end + step * (i + 1)),
            timecoded=True,
        )
        for i in range(chapters)
    ]

    return [
        Segment("hook", "후크", 0, hook_end, "30초 안에 볼 이유를 준다", timecoded=True),
        Segment("promise", "약속", hook_end, promise_end,
                "끝까지 보면 무엇을 얻는지 말한다", timecoded=True),
        *chapter_segments,
        Segment("summary", "요약", summary_start, cta_start, "핵심을 다시 정리한다", timecoded=True),
        Segment("cta", "CTA", cta_start, duration, "행동 하나만 요청한다", timecoded=True),
    ]


def segments_for(data: ScriptInput, chapters: int = 6) -> list[Segment]:
    """입력에 맞는 구간 목록."""
    if data.is_short_form:
        return shorts_segments(data.duration_sec)
    return long_segments(data.duration_sec, chapters)
