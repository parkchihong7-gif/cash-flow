"""전자책 목차(outline.yaml) 스키마와 분량 계산.

3단계 워크플로우의 1단계 산출물이 `outline.yaml` 이고, 사용자가 손으로 고친 뒤
2단계(write)와 3단계(build)가 그 파일을 읽는다. 그래서 이 스키마는
**사람이 편집한 뒤에도 검증을 통과해야 한다.**
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = [
    "Outline", "ChapterPlan", "load_outline", "save_outline", "plan_budget",
    "Budget", "CHARS_PER_PAGE", "CHAPTER_MIN_CHARS", "CHAPTER_MAX_CHARS",
    "MIN_CHAPTERS", "MAX_CHAPTERS", "LENGTH_TOLERANCE",
]

#: A4·여백 2.5cm·맑은 고딕 10.5pt·줄간격 1.5 기준 한 쪽에 들어가는 글자 수.
#: 제목·체크리스트 표·문단 사이 여백을 감안한 보수적인 값이다.
CHARS_PER_PAGE = 750

#: 챕터 한 편의 글자 수 범위.
CHAPTER_MIN_CHARS = 1500
CHAPTER_MAX_CHARS = 2500

#: 챕터 개수 범위.
MIN_CHAPTERS = 8
MAX_CHAPTERS = 12

#: 완성 원고가 목표 분량에서 벗어나도 되는 비율.
LENGTH_TOLERANCE = 0.20

_SLUG_STRIP_RE = re.compile(r"[^0-9a-z가-힣]+")


class ChapterPlan(BaseModel):
    """챕터 하나의 계획. 2단계(write)가 이걸 보고 원고를 쓴다."""

    model_config = {"extra": "forbid"}

    number: int = Field(ge=1, description="챕터 번호 (1부터)")
    title: str = Field(min_length=1, description="챕터 제목")
    key_message: str = Field(min_length=1, description="이 챕터에서 독자가 가져갈 문장 하나")
    subheadings: list[str] = Field(
        min_length=3, max_length=5, description="소제목 3~5개. 챕터 안의 흐름"
    )
    target_chars: int = Field(
        ge=CHAPTER_MIN_CHARS, le=CHAPTER_MAX_CHARS, description="목표 글자 수"
    )

    @field_validator("title", "key_message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("빈 값일 수 없습니다")
        return value.strip()

    @field_validator("subheadings")
    @classmethod
    def _clean_subheadings(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values if item and item.strip()]
        if len(cleaned) != len(values):
            raise ValueError("빈 소제목이 섞여 있습니다")
        return cleaned

    @property
    def filename(self) -> str:
        return f"ch{self.number:02d}.md"


class Outline(BaseModel):
    """전자책 한 권의 목차. 1단계 산출물이자 2·3단계의 입력."""

    model_config = {"extra": "forbid"}

    topic: str = Field(min_length=1, description="원래 입력한 주제")
    audience: str = Field(min_length=1, description="누가 읽는 책인지 한 줄")
    author: str = Field(default="", description="표지에 넣을 저자명")
    pages: int = Field(ge=10, le=80, description="목표 쪽수")

    title_options: list[str] = Field(
        min_length=3, max_length=3, description="제목 3안. 첫 번째가 표지에 쓰인다"
    )
    subtitle: str = Field(default="", description="부제")
    preface: str = Field(min_length=1, description="서문 요지")
    chapters: list[ChapterPlan] = Field(min_length=MIN_CHAPTERS, max_length=MAX_CHAPTERS)

    @field_validator("title_options")
    @classmethod
    def _clean_titles(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values if item and item.strip()]
        if len(cleaned) != 3:
            raise ValueError("제목은 정확히 3안이어야 합니다")
        return cleaned

    @model_validator(mode="after")
    def _chapters_numbered_in_order(self) -> "Outline":
        numbers = [chapter.number for chapter in self.chapters]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError(
                f"챕터 번호는 1부터 빠짐없이 이어져야 합니다 (현재: {numbers})"
            )
        return self

    @property
    def title(self) -> str:
        """표지에 쓸 제목. 제목 3안 중 첫 번째."""
        return self.title_options[0]

    @property
    def slug(self) -> str:
        normalized = unicodedata.normalize("NFC", self.topic).lower()
        return _SLUG_STRIP_RE.sub("-", normalized).strip("-") or "ebook"

    @property
    def target_chars(self) -> int:
        """챕터 목표 글자 수의 합. 완성 원고는 여기서 ±20% 안에 들어야 한다."""
        return sum(chapter.target_chars for chapter in self.chapters)

    @property
    def estimated_pages(self) -> int:
        return max(1, round(self.target_chars / CHARS_PER_PAGE))

    def within_tolerance(self, actual_chars: int) -> bool:
        low = self.target_chars * (1 - LENGTH_TOLERANCE)
        high = self.target_chars * (1 + LENGTH_TOLERANCE)
        return low <= actual_chars <= high

    def chapter(self, number: int) -> ChapterPlan | None:
        return next((c for c in self.chapters if c.number == number), None)


class Budget:
    """쪽수 요청을 챕터 수와 챕터당 분량으로 환산한 결과.

    챕터 수(8~12)와 챕터당 분량(1,500~2,500자)에 한계가 있어서
    요청한 쪽수를 그대로 맞추지 못할 수 있다. 그럴 때 조용히 넘어가지 않고
    :attr:`warning` 에 남긴다.
    """

    def __init__(self, pages: int) -> None:
        self.requested_pages = pages
        target = pages * CHARS_PER_PAGE

        raw_count = round(target / ((CHAPTER_MIN_CHARS + CHAPTER_MAX_CHARS) / 2))
        self.chapter_count = max(MIN_CHAPTERS, min(MAX_CHAPTERS, raw_count))

        per_chapter = round(target / self.chapter_count)
        self.chars_per_chapter = max(
            CHAPTER_MIN_CHARS, min(CHAPTER_MAX_CHARS, per_chapter)
        )
        self.total_chars = self.chapter_count * self.chars_per_chapter
        self.achievable_pages = round(self.total_chars / CHARS_PER_PAGE)

        self.warning = ""
        if abs(self.total_chars - target) > target * LENGTH_TOLERANCE:
            low = round(MIN_CHAPTERS * CHAPTER_MIN_CHARS / CHARS_PER_PAGE)
            high = round(MAX_CHAPTERS * CHAPTER_MAX_CHARS / CHARS_PER_PAGE)
            self.warning = (
                f"{pages}쪽은 맞추기 어렵습니다. 챕터 {MIN_CHAPTERS}~{MAX_CHAPTERS}개, "
                f"챕터당 {CHAPTER_MIN_CHARS:,}~{CHAPTER_MAX_CHARS:,}자 기준으로 "
                f"만들 수 있는 범위는 약 {low}~{high}쪽입니다. "
                f"이번에는 {self.achievable_pages}쪽 분량으로 만듭니다."
            )


def plan_budget(pages: int) -> Budget:
    """쪽수 → 챕터 수·챕터당 분량."""
    return Budget(pages)


def load_outline(path: str | Path) -> Outline:
    """outline.yaml 을 읽어 검증한다. 사람이 고친 파일도 여기를 통과해야 한다."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"목차 파일이 없습니다: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} 의 최상위는 키-값 매핑이어야 합니다")
    return Outline(**raw)


def save_outline(outline: Outline, path: str | Path) -> Path:
    """사람이 고칠 수 있게 주석을 붙여 저장한다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    header = (
        "# 전자책 목차 — 이 파일을 손으로 고친 뒤 2단계(write)를 실행하세요.\n"
        "#\n"
        "# 고쳐도 되는 것\n"
        "#   title_options  제목 3안. 첫 번째가 표지에 쓰입니다. 순서를 바꿔 고르세요.\n"
        "#   subtitle       부제\n"
        "#   preface        서문 요지\n"
        "#   chapters       챕터 제목·핵심 메시지·소제목·목표 글자 수\n"
        "#   author         표지에 들어갈 저자명\n"
        "#\n"
        f"# 지켜야 하는 것\n"
        f"#   챕터 {MIN_CHAPTERS}~{MAX_CHAPTERS}개, 번호는 1부터 빠짐없이\n"
        f"#   소제목 3~5개, 목표 글자 수 {CHAPTER_MIN_CHARS:,}~{CHAPTER_MAX_CHARS:,}자\n"
        "#   이 범위를 벗어나면 2단계에서 오류로 알려드립니다.\n"
        "\n"
    )
    body = yaml.safe_dump(
        outline.model_dump(), allow_unicode=True, sort_keys=False, width=100
    )
    path.write_text(header + body, encoding="utf-8")
    return path
