"""전자책 생성기 — 1단계 목차, 2단계 챕터 원고, 3단계 부가 산출물.

3단계 워크플로우
    1. :func:`build_outline`  주제 → outline.yaml (사람이 손으로 고친다)
    2. :func:`write_chapters` outline.yaml → chapters/ch01.md ...
    3. :mod:`ebook_gen.docx_builder` chapters/ → ebook.docx

챕터는 한 편씩 따로 호출한다. 한 챕터가 실패해도 나머지는 살아 있고,
그 챕터만 다시 쓰면 된다. 앞 챕터의 요약을 다음 챕터 프롬프트에 넣어
같은 사례를 두 번 쓰거나 설명을 반복하는 것을 막는다.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ebook_gen.schema import (  # noqa: E402
    CHAPTER_MAX_CHARS, CHAPTER_MIN_CHARS, ChapterPlan, Outline, plan_budget,
)
from shared import banned_phrases  # noqa: E402
from shared.ai_label import add_text_label  # noqa: E402
from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import LLMError, ask as default_ask  # noqa: E402

__all__ = [
    "EbookGenerator", "ChapterDraft", "ChapterResult", "build_outline",
    "write_chapters", "render_chapter_markdown", "parse_chapter_markdown",
    "BASE_DIR",
]

#: 상품 폴더 (이 패키지의 부모).
BASE_DIR = Path(__file__).resolve().parents[1]
PROMPTS_DIR = BASE_DIR / "prompts"

#: 섹션당 최대 재생성 횟수.
MAX_RETRIES = 2

#: 챕터 분량이 목표에서 이만큼 벗어나면 한 번 다시 쓴다.
CHAPTER_LENGTH_SLACK = 0.25


@dataclass
class ChapterDraft:
    """챕터 한 편의 원고."""

    plan: ChapterPlan
    intro_case: str
    sections: list[dict[str, str]]
    checklist: list[str]
    summary: list[str]

    @property
    def char_count(self) -> int:
        """공백을 제외한 본문 글자 수."""
        parts = [self.intro_case, *(s.get("body", "") for s in self.sections),
                 *self.checklist, *self.summary]
        return sum(len("".join(str(p).split())) for p in parts)

    @property
    def summary_text(self) -> str:
        return " ".join(self.summary)


@dataclass
class ChapterResult:
    """챕터 한 편의 생성 결과와 검사 이력."""

    number: int
    draft: ChapterDraft | None = None
    attempts: int = 0
    banned: list[str] = field(default_factory=list)
    length_off: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.draft is not None

    @property
    def clean(self) -> bool:
        return self.ok and not self.banned and not self.length_off


def _collect_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _collect_strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _collect_strings(item)]
    return []


class EbookGenerator:
    """목차와 챕터 원고를 만든다.

    Args:
        model: Claude 모델 ID.
        ask_fn: LLM 호출 함수. 테스트·모의 실행에서 교체한다.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        ask_fn: Callable[..., Any] = default_ask,
    ) -> None:
        self.model = model
        self.ask_fn = ask_fn
        self.outline_rules = (PROMPTS_DIR / "outline.md").read_text(encoding="utf-8")
        self.chapter_rules = (PROMPTS_DIR / "chapter.md").read_text(encoding="utf-8")

    # ------------------------------------------------------------- 1단계
    def build_outline(
        self, topic: str, audience: str, pages: int, author: str = "",
        evidence: list[str] | None = None,
    ) -> tuple[Outline, str]:
        """주제에서 목차를 만든다. (목차, 경고 문구) 를 돌려준다."""
        budget = plan_budget(pages)
        evidence = evidence or []
        evidence_text = (
            "\n".join(f"  - {item}" for item in evidence)
            if evidence else "  (없음 — 수치·출처를 지어내지 말 것)"
        )

        instruction = (
            f"[주제] {topic}\n"
            f"[독자] {audience}\n"
            f"[목표 분량] 약 {budget.achievable_pages}쪽 "
            f"(챕터 {budget.chapter_count}개, 챕터당 {budget.chars_per_chapter:,}자 기준)\n"
            f"[참고 자료]\n{evidence_text}\n\n"
            f"위 주제로 전자책 목차를 만드세요.\n"
            f"- 챕터는 정확히 {budget.chapter_count}개\n"
            f"- 각 챕터에 소제목 3~5개\n"
            f"- target_chars 는 {CHAPTER_MIN_CHARS:,}~{CHAPTER_MAX_CHARS:,} 범위, "
            f"합계는 {budget.total_chars:,}자 안팎\n"
            f"- 제목은 3안을 서로 다른 각도로\n"
            'JSON: {"title_options": ["...", "...", "..."], "subtitle": "...", '
            '"preface": "...", "chapters": [{"number": 1, "title": "...", '
            '"key_message": "...", "subheadings": ["...", "...", "..."], '
            '"target_chars": 2000}]}'
        )

        data = self._ask_checked("outline", self.outline_rules, instruction)
        outline = Outline(
            topic=topic, audience=audience, author=author, pages=pages,
            title_options=data["title_options"],
            subtitle=data.get("subtitle", ""),
            preface=data["preface"],
            chapters=[ChapterPlan(**chapter) for chapter in data["chapters"]],
        )
        return outline, budget.warning

    # ------------------------------------------------------------- 2단계
    def write_chapter(
        self, outline: Outline, plan: ChapterPlan, previous_summary: str = "",
    ) -> ChapterResult:
        """챕터 한 편을 쓴다. 금지 문구나 분량 이탈이 있으면 다시 쓴다."""
        subheadings = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(plan.subheadings))
        context = (
            f"[책 제목] {outline.title}\n"
            f"[독자] {outline.audience}\n"
            f"[서문 요지] {outline.preface}\n\n"
            f"[이번 챕터] {plan.number}장. {plan.title}\n"
            f"[핵심 메시지] {plan.key_message}\n"
            f"[소제목]\n{subheadings}\n"
            f"[목표 글자 수] {plan.target_chars:,}자 (±10%)\n"
        )
        if previous_summary:
            context += (
                f"\n[앞 챕터 요약] {previous_summary}\n"
                "이 내용을 전제로 쓰고, 같은 설명이나 같은 사례를 반복하지 마세요.\n"
            )
        else:
            context += "\n이 책의 첫 챕터입니다. 독자가 아무 배경도 모른다고 가정하세요.\n"

        result = ChapterResult(number=plan.number)
        user = context
        for attempt in range(1, MAX_RETRIES + 2):
            result.attempts = attempt
            try:
                data = self.ask_fn(
                    self.chapter_rules, user, model=self.model, json_mode=True
                )
            except LLMError as exc:
                result.error = str(exc)
                continue  # 이 챕터만 다시 시도한다

            draft = ChapterDraft(
                plan=plan,
                intro_case=str(data.get("intro_case", "")).strip(),
                sections=[
                    {"subheading": str(s.get("subheading", "")).strip(),
                     "body": str(s.get("body", "")).strip()}
                    for s in data.get("sections", [])
                ],
                checklist=[str(item).strip() for item in data.get("checklist", [])],
                summary=[str(item).strip() for item in data.get("summary", [])][:3],
            )
            result.draft = draft
            result.error = ""

            banned = banned_phrases.check("\n".join(_collect_strings(data)))
            low = plan.target_chars * (1 - CHAPTER_LENGTH_SLACK)
            high = plan.target_chars * (1 + CHAPTER_LENGTH_SLACK)
            length_off = not (low <= draft.char_count <= high)

            result.banned = banned
            result.length_off = length_off
            if not banned and not length_off:
                return result

            problems = []
            if banned:
                problems.append(f"금지 문구가 들어갔습니다: {', '.join(banned)}")
            if length_off:
                direction = "짧습니다" if draft.char_count < low else "깁니다"
                problems.append(
                    f"분량이 {direction}. 현재 {draft.char_count:,}자, "
                    f"목표 {plan.target_chars:,}자"
                )
            user = (
                f"{context}\n[재작성 요청]\n"
                + "\n".join(f"- {p}" for p in problems)
                + "\n해당 부분을 고쳐 처음부터 다시 쓰세요."
            )

        return result

    # ------------------------------------------------------------- 3단계
    def sales_copy(self, outline: Outline) -> dict[str, Any]:
        """판매용 소개글. 금지 문구 검사를 통과해야 한다."""
        toc = "\n".join(
            f"  {c.number}. {c.title} — {c.key_message}" for c in outline.chapters
        )
        instruction = (
            f"[책 제목] {outline.title}\n"
            f"[부제] {outline.subtitle}\n"
            f"[독자] {outline.audience}\n"
            f"[분량] 약 {outline.estimated_pages}쪽\n"
            f"[목차]\n{toc}\n\n"
            "크몽·인스타그램에 올릴 판매용 소개글을 만드세요.\n"
            "- intro: 500자 안팎의 소개글. 무엇을 다루고 읽으면 뭐가 달라지는지\n"
            "- toc_summary: 목차를 3~4줄로 압축\n"
            "- for_whom: 추천 대상 3~4개\n"
            "- not_for_whom: 맞지 않는 사람 2~3개 (솔직하게 쓰면 신뢰가 올라갑니다)\n"
            "- pricing: 가격 제안 3안. plan/price/includes/reason 포함\n"
            "  (전자책 단독 / 전자책+템플릿 / 전자책+1:1 피드백)\n"
            "성과를 단정하는 표현은 쓰지 마세요. 조건부로 쓰세요.\n"
            'JSON: {"intro": "...", "toc_summary": "...", "for_whom": ["..."], '
            '"not_for_whom": ["..."], "pricing": [{"plan": "...", "price": 19000, '
            '"includes": ["..."], "reason": "..."}]}'
        )
        return self._ask_checked("sales_copy", self.outline_rules, instruction)

    def cover_brief(self, outline: Outline) -> dict[str, Any]:
        """표지 디자인 지시서."""
        instruction = (
            f"[책 제목] {outline.title}\n"
            f"[부제] {outline.subtitle}\n"
            f"[독자] {outline.audience}\n"
            f"[주제] {outline.topic}\n\n"
            "전자책 표지 디자인 지시서를 만드세요. 디자이너와 이미지 생성 도구 둘 다에 넘길 수 있게요.\n"
            "- concept: 표지가 전달해야 할 인상 한 문단\n"
            "- mood: 분위기 키워드 4~6개\n"
            "- colors: 색 조합 제안 (이름과 hex 코드)\n"
            "- typography: 제목·부제 글꼴 방향\n"
            "- layout: 요소 배치\n"
            "- image_prompt: 이미지 생성 도구에 그대로 넣을 영문 프롬프트. "
            "글자를 넣지 말라는 지시(no text)를 포함하세요\n"
            "- avoid: 피해야 할 것 3~4개\n"
            'JSON: {"concept": "...", "mood": ["..."], "colors": [{"name": "...", '
            '"hex": "#000000", "use": "..."}], "typography": "...", "layout": "...", '
            '"image_prompt": "...", "avoid": ["..."]}'
        )
        return self._ask_checked("cover_brief", self.outline_rules, instruction)

    # ------------------------------------------------------------- 공통
    def _ask_checked(self, name: str, system: str, instruction: str) -> dict[str, Any]:
        """금지 문구가 나오면 최대 2회 다시 만든다."""
        user = instruction
        data: dict[str, Any] = {}
        for _ in range(MAX_RETRIES + 1):
            data = self.ask_fn(system, user, model=self.model, json_mode=True)
            found = banned_phrases.check("\n".join(_collect_strings(data)))
            if not found:
                return data
            user = (
                f"{instruction}\n\n[재작성 요청] 금지 문구가 들어갔습니다: "
                f"{', '.join(found)}\n해당 표현을 빼고 다시 쓰세요."
            )
        return data


# ==================================================================== 마크다운
def render_chapter_markdown(draft: ChapterDraft, ai_label: bool = True) -> str:
    """챕터 원고를 사람이 고칠 수 있는 마크다운으로.

    3단계(build)가 이 형식을 그대로 다시 읽으므로 제목 구조를 바꾸면 안 된다.
    """
    plan = draft.plan
    lines = [
        f"# {plan.number}장. {plan.title}",
        "",
        f"> **핵심 메시지** {plan.key_message}",
        f"> 목표 {plan.target_chars:,}자 · 현재 {draft.char_count:,}자",
        "",
        "## 도입 사례",
        "",
        draft.intro_case,
        "",
        "## 핵심 설명",
        "",
    ]
    for section in draft.sections:
        lines += [f"### {section['subheading']}", "", section["body"], ""]

    lines += ["## 실행 체크리스트", ""]
    lines += [f"- [ ] {item}" for item in draft.checklist]
    lines += ["", "## 요약 3줄", ""]
    lines += [f"{i}. {line}" for i, line in enumerate(draft.summary, start=1)]
    lines.append("")

    text = "\n".join(lines)
    return add_text_label(text) + "\n" if ai_label else text


def parse_chapter_markdown(text: str, plan: ChapterPlan) -> ChapterDraft:
    """마크다운을 다시 읽는다. 사람이 고친 내용을 docx 에 반영하기 위해서다.

    Raises:
        ValueError: 필수 구간(도입 사례·핵심 설명·실행 체크리스트·요약)이 빠졌을 때.
    """
    intro, sections, checklist, summary = "", [], [], []
    current, buffer, subheading = None, [], ""

    def flush() -> None:
        nonlocal buffer, subheading
        body = "\n".join(buffer).strip()
        if current == "intro" and body:
            nonlocal intro
            intro = body
        elif current == "sections" and subheading:
            sections.append({"subheading": subheading, "body": body})
        buffer = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            flush()
            heading = stripped[3:].strip()
            subheading = ""
            current = {
                "도입 사례": "intro", "핵심 설명": "sections",
                "실행 체크리스트": "checklist", "요약 3줄": "summary",
            }.get(heading)
            continue
        if stripped.startswith("### ") and current == "sections":
            flush()
            subheading = stripped[4:].strip()
            continue
        if current == "checklist":
            if stripped.startswith(("- [ ]", "- [x]", "- [X]")):
                checklist.append(stripped[5:].strip())
            elif stripped.startswith("- "):
                checklist.append(stripped[2:].strip())
            continue
        if current == "summary":
            if stripped and stripped[0].isdigit() and "." in stripped[:3]:
                summary.append(stripped.split(".", 1)[1].strip())
            elif stripped.startswith("- "):
                summary.append(stripped[2:].strip())
            continue
        if stripped.startswith(("# ", "> ")):
            continue
        buffer.append(line)
    flush()

    missing = [
        name for name, value in
        [("도입 사례", intro), ("핵심 설명", sections),
         ("실행 체크리스트", checklist), ("요약 3줄", summary)]
        if not value
    ]
    if missing:
        raise ValueError(
            f"{plan.filename} 에서 '{', '.join(missing)}' 를 찾지 못했습니다. "
            "제목 구조(## 도입 사례 / ## 핵심 설명 / ## 실행 체크리스트 / ## 요약 3줄)를 "
            "그대로 두고 내용만 고치세요."
        )

    return ChapterDraft(
        plan=plan, intro_case=intro, sections=sections,
        checklist=checklist, summary=summary[:3],
    )
