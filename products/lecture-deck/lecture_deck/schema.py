"""deck_input.yaml 스키마와 텍스트 맞춤(오버플로 방지) 규칙.

슬라이드가 넘치는 것은 이 도구에서 가장 흔한 사고다. 그래서 규칙을
프롬프트로만 부탁하지 않고 :func:`fit_body` 로 **강제**한다.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = [
    "DeckInput", "ModuleInput", "load_input", "fit_body", "wrap_line",
    "MAX_BODY_LINES", "MAX_LINE_CHARS", "NOTE_MIN_CHARS", "NOTE_MAX_CHARS",
    "MIN_MODULES", "MAX_MODULES", "MIN_CONCEPTS", "MAX_CONCEPTS", "STYLES",
]

Style = Literal["minimal", "bold", "corporate"]
STYLES = ("minimal", "bold", "corporate")

#: 슬라이드 본문 한 장에 들어갈 최대 줄 수.
MAX_BODY_LINES = 6
#: 본문 한 줄의 최대 글자 수. 넘으면 읽기 전에 시선이 흩어진다.
MAX_LINE_CHARS = 20

#: 발표자 노트 분량. 비어 있으면 안 된다.
NOTE_MIN_CHARS = 200
NOTE_MAX_CHARS = 400

MIN_MODULES, MAX_MODULES = 5, 8
MIN_CONCEPTS, MAX_CONCEPTS = 3, 5

_SLUG_STRIP_RE = re.compile(r"[^0-9a-z가-힣]+")


class ModuleInput(BaseModel):
    """입력으로 받는 모듈. 비워두면 LLM 이 제안한다."""

    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, description="모듈 제목")
    goal: str = Field(default="", description="이 모듈의 학습 목표")
    concepts: list[str] = Field(
        default_factory=list, description="핵심 개념 3~5개. 비우면 LLM 이 채운다"
    )

    @field_validator("concepts")
    @classmethod
    def _concept_count(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values if item and item.strip()]
        if cleaned and not MIN_CONCEPTS <= len(cleaned) <= MAX_CONCEPTS:
            raise ValueError(
                f"핵심 개념은 {MIN_CONCEPTS}~{MAX_CONCEPTS}개여야 합니다 (현재 {len(cleaned)}개). "
                "비워두면 자동으로 채웁니다."
            )
        return cleaned


class DeckInput(BaseModel):
    """강의 슬라이드 한 벌을 만드는 데 필요한 입력."""

    model_config = {"extra": "forbid"}

    course_title: str = Field(min_length=1, description="강의 제목")
    audience: str = Field(min_length=1, description="누가 듣는 강의인지 한 줄")
    total_minutes: int = Field(ge=30, le=960, description="전체 강의 시간 (분)")
    instructor: str = Field(default="", description="강사명. 비우면 자리만 만든다")
    modules: list[ModuleInput] = Field(
        default_factory=list, description=f"모듈 목록. 비우면 LLM 이 {MIN_MODULES}~{MAX_MODULES}개 제안"
    )
    style: Style = Field(default="minimal", description="minimal | bold | corporate")

    @field_validator("course_title", "audience")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("빈 값일 수 없습니다")
        return value.strip()

    @model_validator(mode="after")
    def _module_count(self) -> "DeckInput":
        if self.modules and not MIN_MODULES <= len(self.modules) <= MAX_MODULES:
            raise ValueError(
                f"모듈은 {MIN_MODULES}~{MAX_MODULES}개여야 합니다 (현재 {len(self.modules)}개). "
                "비워두면 자동으로 제안합니다."
            )
        return self

    @property
    def slug(self) -> str:
        normalized = unicodedata.normalize("NFC", self.course_title).lower()
        return _SLUG_STRIP_RE.sub("-", normalized).strip("-") or "deck"

    @property
    def duration_text(self) -> str:
        hours, minutes = divmod(self.total_minutes, 60)
        if hours and minutes:
            return f"{hours}시간 {minutes}분"
        return f"{hours}시간" if hours else f"{minutes}분"


def load_input(path: str | Path) -> DeckInput:
    """YAML 을 읽어 검증된 :class:`DeckInput` 으로 돌려준다."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"입력 파일이 없습니다: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} 의 최상위는 키-값 매핑이어야 합니다")
    return DeckInput(**raw)


# --------------------------------------------------------------- 텍스트 맞춤
def wrap_line(text: str, limit: int = MAX_LINE_CHARS) -> list[str]:
    """한 줄을 limit 글자 이하 여러 줄로 쪼갠다.

    띄어쓰기에서 끊는 것을 우선하고, 한 단어가 limit 보다 길면 글자 수로 자른다.
    LLM 이 규칙을 못 지켰을 때의 마지막 안전장치다.
    """
    text = " ".join(text.split())
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        while len(word) > limit:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:limit])
            word = word[limit:]
        candidate = f"{current} {word}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_body(
    lines: list[str],
    max_lines: int = MAX_BODY_LINES,
    limit: int = MAX_LINE_CHARS,
) -> list[list[str]]:
    """본문 줄 목록을 슬라이드 단위로 나눈다.

    1. 각 줄을 ``limit`` 글자 이하로 쪼갠다
    2. ``max_lines`` 줄씩 묶어 슬라이드로 나눈다

    Returns:
        슬라이드마다 한 덩어리인 줄 목록. 입력이 비면 빈 리스트.
    """
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(wrap_line(str(line), limit))
    if not wrapped:
        return []
    return [wrapped[i:i + max_lines] for i in range(0, len(wrapped), max_lines)]
