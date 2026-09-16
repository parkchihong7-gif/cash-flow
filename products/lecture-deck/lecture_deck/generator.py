"""강의 슬라이드 생성기 — 커리큘럼 설계와 모듈별 슬라이드 집필.

흐름
    1. :meth:`DeckGenerator.build_curriculum` 모듈·목표·시간·실습·평가 기준
    2. (사람 확인 — CLI 가 물어본다. ``--yes`` 로 건너뛴다)
    3. :meth:`DeckGenerator.write_module` 모듈마다 슬라이드 본문과 발표자 노트
    4. :func:`assemble_deck` 고정 슬라이드를 붙이고 넘치는 본문을 쪼갠다

슬라이드 본문은 프롬프트로만 부탁하지 않고 :func:`lecture_deck.schema.fit_body` 로
6줄·20자를 **강제**한다. 발표자 노트도 비어 있으면 채운다.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from lecture_deck.schema import (  # noqa: E402
    DeckInput, MAX_BODY_LINES, MAX_CONCEPTS, MAX_LINE_CHARS, MAX_MODULES,
    MIN_CONCEPTS, MIN_MODULES, NOTE_MAX_CHARS, NOTE_MIN_CHARS, fit_body,
)
from shared import banned_phrases  # noqa: E402
from shared.ai_label import LABELS  # noqa: E402
from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import LLMError, ask as default_ask  # noqa: E402

__all__ = [
    "DeckGenerator", "Slide", "ModuleResult", "DeckResult", "Curriculum",
    "assemble_deck", "pad_note", "BASE_DIR",
]

#: 상품 폴더 (이 패키지의 부모).
BASE_DIR = Path(__file__).resolve().parents[1]
PROMPTS_DIR = BASE_DIR / "prompts"

MAX_RETRIES = 2

#: 슬라이드 종류.
KINDS = ("cover", "instructor", "agenda", "module", "concept", "practice",
         "summary", "closing", "ai_notice")


@dataclass
class Slide:
    """슬라이드 한 장."""

    kind: str
    title: str
    body: list[str] = field(default_factory=list)
    note: str = ""
    subtitle: str = ""
    module_number: int | None = None

    @property
    def overflows(self) -> bool:
        return (
            len(self.body) > MAX_BODY_LINES
            or any(len(line) > MAX_LINE_CHARS for line in self.body)
        )


@dataclass
class Curriculum:
    """1단계 산출물 — 모듈별 목표·시간·실습·평가 기준."""

    modules: list[dict[str, Any]]

    @property
    def total_minutes(self) -> int:
        return sum(int(m.get("minutes", 0)) for m in self.modules)

    def concepts(self, index: int) -> list[str]:
        return list(self.modules[index].get("concepts", []))


@dataclass
class ModuleResult:
    """모듈 하나의 슬라이드 생성 결과."""

    number: int
    slides: list[Slide] = field(default_factory=list)
    attempts: int = 0
    banned: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.slides)


@dataclass
class DeckResult:
    """덱 한 벌의 전체 결과."""

    data: DeckInput
    curriculum: Curriculum
    slides: list[Slide]
    model: str
    generated_at: datetime
    warnings: list[str] = field(default_factory=list)
    split_count: int = 0
    padded_notes: int = 0

    @property
    def slide_count(self) -> int:
        return len(self.slides)


def _collect_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _collect_strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _collect_strings(item)]
    return []


# ------------------------------------------------------------------ 노트 보정
_SENTENCE_RE = re.compile(r"(?<=[.!?。])\s+|(?<=다\.)\s*")


def pad_note(note: str, slide: Slide, course_title: str) -> str:
    """노트가 비었거나 너무 짧으면 채운다. 빈 노트는 허용하지 않는다.

    발표자 노트가 없는 슬라이드는 강사에게 쓸모가 없고, 완료 기준이기도 하다.
    """
    note = " ".join(str(note).split())
    if len(note) >= NOTE_MIN_CHARS:
        return note[:NOTE_MAX_CHARS] if len(note) > NOTE_MAX_CHARS else note

    keywords = " / ".join(slide.body[:3]) if slide.body else slide.title
    filler = (
        f"이 슬라이드에서는 '{slide.title}' 를 다룹니다. "
        f"화면의 {keywords} 를 하나씩 짚으면서 왜 그런지 설명하세요. "
        "수강생이 여기서 자주 막히는 지점을 미리 짚어 주면 질문이 줄어듭니다. "
        f"'{course_title}' 전체 흐름에서 이 부분이 어디에 놓이는지도 한 번 짚고 "
        "다음 슬라이드로 넘어가세요. "
        "[강사가 채울 곳: 본인 경험이나 현장 사례 한 가지]"
    )
    combined = f"{note} {filler}".strip() if note else filler
    while len(combined) < NOTE_MIN_CHARS:
        combined += " 필요하면 여기서 질문을 받고 넘어가세요."
    return combined[:NOTE_MAX_CHARS]


# ------------------------------------------------------------------ 덱 조립
def assemble_deck(
    data: DeckInput,
    curriculum: Curriculum,
    module_slides: dict[int, list[Slide]],
    model: str,
) -> DeckResult:
    """고정 슬라이드를 붙이고 넘치는 본문을 쪼개 최종 덱을 만든다."""
    slides: list[Slide] = []
    warnings: list[str] = []
    split_count = 0
    padded = 0

    def push(slide: Slide) -> None:
        """6줄·20자를 넘으면 슬라이드를 나눠서 넣는다."""
        nonlocal split_count, padded
        chunks = fit_body(slide.body) or [[]]
        total = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            title = slide.title if total == 1 else f"{slide.title} ({index}/{total})"
            part = Slide(
                kind=slide.kind, title=title, body=chunk,
                note=slide.note if index == 1 else "",
                subtitle=slide.subtitle, module_number=slide.module_number,
            )
            before = part.note
            part.note = pad_note(part.note, part, data.course_title)
            if len(" ".join(str(before).split())) < NOTE_MIN_CHARS:
                padded += 1
            slides.append(part)
        if total > 1:
            split_count += total - 1

    # 표지
    push(Slide(
        kind="cover", title=data.course_title,
        subtitle=f"{data.audience} · {data.duration_text}",
        note=(
            f"'{data.course_title}' 강의를 시작합니다. "
            f"오늘은 {data.duration_text} 동안 {len(curriculum.modules)}개 모듈을 다룹니다. "
            "먼저 수강생에게 지금 어떤 상황인지 한 명씩 한 문장으로 말하게 하세요. "
            "뒤에서 예시를 들 때 그 말을 그대로 쓸 수 있고, 수강생도 "
            "'내 얘기를 하는 강의'라고 느낍니다. 인원이 많으면 세 명만 받아도 충분합니다. "
            "그다음 쉬는 시간이 언제인지, 질문은 중간에 받는지 끝에 받는지 정해 두세요. "
            "이걸 안 정하면 질문 때문에 진도가 밀립니다."
        ),
    ))

    # 강사 소개 (자리)
    push(Slide(
        kind="instructor", title="강사 소개",
        subtitle=data.instructor or "[강사명을 채우세요]",
        body=["[경력 한 줄]", "[이 주제를 다루는 이유]", "[연락처 또는 채널]"],
        note=(
            "여기서 길게 말하지 마세요. 2분을 넘기면 수강생이 지칩니다. "
            "경력을 나열하는 소개는 기억에 남지 않습니다. 대신 "
            "'왜 내가 이 주제를 다루는가'를 한 문장으로 말하세요. "
            "이 강의에서 다룰 문제를 본인이 직접 겪었다는 사실 하나면 충분합니다. "
            "연락처나 채널은 화면에 띄워 두고 말로는 짧게 언급만 하세요. "
            "마지막에 다시 안내할 기회가 있습니다. "
            "[강사가 채울 곳: 이 주제와 이어지는 본인 경험 한 가지]"
        ),
    ))

    # 커리큘럼 개요
    agenda_lines = [
        f"{index}. {module.get('title', '')}"
        for index, module in enumerate(curriculum.modules, start=1)
    ]
    push(Slide(
        kind="agenda", title="오늘 다룰 것",
        body=agenda_lines,
        note=(
            f"전체 흐름을 먼저 보여 줍니다. {len(curriculum.modules)}개 모듈이고 "
            f"총 {data.duration_text} 걸립니다. "
            "여기서 중요한 건 '각 모듈이 앞 모듈을 전제로 쌓인다'는 점을 말하는 것입니다. "
            "그래야 중간에 빠지거나 딴짓하는 사람이 줄어듭니다. "
            "어디에 실습이 있는지도 미리 알려 주세요. 손을 쓰는 시간이 있다는 걸 알면 "
            "앉아 있는 태도가 달라집니다. "
            "쉬는 시간 위치도 이 화면에서 같이 짚어 두면 질문이 줄어듭니다."
        ),
    ))

    # 모듈별
    for index, module in enumerate(curriculum.modules, start=1):
        minutes = module.get("minutes", 0)
        push(Slide(
            kind="module", title=f"{index}. {module.get('title', '')}",
            subtitle=f"{minutes}분",
            body=[module.get("goal", "")] if module.get("goal") else [],
            module_number=index,
            note=(
                f"{index}번째 모듈입니다. 목표는 '{module.get('goal', '')}' 이고 "
                f"{minutes}분을 씁니다. "
                "여기서 목표를 소리 내어 읽어 주세요. 눈으로만 보면 넘어가지만 "
                "들으면 기억에 남습니다. 모듈이 끝났을 때 이걸 할 수 있게 되었는지 "
                "수강생이 스스로 확인할 기준이 됩니다. "
                "앞 모듈과 어떻게 이어지는지도 한 문장으로 짚고 시작하세요. "
                "연결이 보이지 않으면 따로 노는 강의가 됩니다."
            ),
        ))
        for slide in module_slides.get(index, []):
            slide.module_number = index
            push(slide)

    # 마무리
    push(Slide(
        kind="closing", title="내일부터 할 것",
        body=["[가장 먼저 할 한 가지]", "[막히면 볼 자료]", "[질문 받는 곳]"],
        note=(
            "배운 것을 다 하려고 하면 결국 아무것도 안 하게 됩니다. "
            "그래서 '내일 할 한 가지'만 정하게 하세요. 실습지에 적게 하고 "
            "두세 명에게 무엇을 적었는지 물어보면 서로 참고가 되고, "
            "말로 뱉은 것은 실제로 하는 비율이 올라갑니다. "
            "그다음 막혔을 때 볼 자료와 질문할 곳을 알려 주고 마무리합니다. "
            "여기서 다음 강의나 후속 과정을 안내해도 좋습니다. "
            "[강사가 채울 곳: 실제 자료 링크와 문의 경로]"
        ),
    ))

    # AI 고지
    push(Slide(
        kind="ai_notice", title="AI 활용 고지",
        body=["초안은 AI가 작성", "강사가 검수·수정", "인공지능기본법 제31조"],
        note=(
            f"{LABELS['ko']} "
            "이 강의 자료의 초안은 생성형 AI로 만든 뒤 강사가 검토하고 고쳤습니다. "
            "인공지능기본법 제31조(인공지능 생성물의 표시)에 따라 이 사실을 밝힙니다. "
            "이 장을 빠르게 넘기지 말고 한 문장만 말해 주세요. "
            "AI를 썼다는 사실을 밝히는 것이 오히려 신뢰를 높입니다. "
            "수강생이 자료를 다시 쓰거나 배포할 때 이 표시를 지우지 않도록 안내하고, "
            "슬라이드를 배포용 PDF로 만들 때도 이 장을 빼지 마세요."
        ),
    ))

    if split_count:
        warnings.append(
            f"본문이 {MAX_BODY_LINES}줄·{MAX_LINE_CHARS}자를 넘어 {split_count}장이 "
            "자동으로 나뉘었습니다. 제목에 (1/2) 이 붙은 슬라이드를 확인하세요."
        )
    if padded:
        warnings.append(
            f"발표자 노트가 짧아 {padded}장을 자동으로 채웠습니다. "
            "'[강사가 채울 곳]' 표시를 본인 내용으로 바꾸세요."
        )

    return DeckResult(
        data=data, curriculum=curriculum, slides=slides, model=model,
        generated_at=datetime.now().astimezone(), warnings=warnings,
        split_count=split_count, padded_notes=padded,
    )


class DeckGenerator:
    """커리큘럼과 슬라이드를 만든다.

    Args:
        data: 검증된 입력.
        model: Claude 모델 ID.
        ask_fn: LLM 호출 함수. 테스트·모의 실행에서 교체한다.
    """

    def __init__(
        self,
        data: DeckInput,
        model: str = DEFAULT_MODEL,
        ask_fn: Callable[..., Any] = default_ask,
    ) -> None:
        self.data = data
        self.model = model
        self.ask_fn = ask_fn
        self.curriculum_rules = (PROMPTS_DIR / "curriculum.md").read_text(encoding="utf-8")
        self.slide_rules = (PROMPTS_DIR / "slides.md").read_text(encoding="utf-8")

    def _brief(self) -> str:
        return (
            f"[강의] {self.data.course_title}\n"
            f"[수강생] {self.data.audience}\n"
            f"[전체 시간] {self.data.total_minutes}분 ({self.data.duration_text})\n"
        )

    # ------------------------------------------------------------- 1단계
    def build_curriculum(self) -> Curriculum:
        """모듈·목표·시간·실습·평가 기준을 만든다."""
        if self.data.modules:
            given = "\n".join(
                f"  {i}. {m.title}"
                + (f" — 목표: {m.goal}" if m.goal else "")
                + (f" / 개념: {', '.join(m.concepts)}" if m.concepts else "")
                for i, m in enumerate(self.data.modules, start=1)
            )
            module_instruction = (
                f"[주어진 모듈]\n{given}\n\n"
                "이 모듈을 그대로 쓰되, 비어 있는 목표·핵심 개념·시간·실습·평가 기준을 채우세요.\n"
                "모듈 제목과 순서는 바꾸지 마세요."
            )
        else:
            module_instruction = (
                f"모듈을 {MIN_MODULES}~{MAX_MODULES}개 제안하세요.\n"
                "앞 모듈이 뒤 모듈의 전제가 되도록 쌓으세요."
            )

        instruction = (
            f"{self._brief()}\n{module_instruction}\n\n"
            f"각 모듈에 다음을 채웁니다.\n"
            f"- goal: 학습 목표. '~을 할 수 있다' 형태\n"
            f"- concepts: 핵심 개념 {MIN_CONCEPTS}~{MAX_CONCEPTS}개\n"
            f"- minutes: 소요 시간(분). 합계가 {self.data.total_minutes}분과 맞아야 합니다\n"
            f"- practice: 강의실에서 그 시간 안에 끝낼 수 있는 실습 과제\n"
            f"- assessment: 익혔는지 확인하는 방법\n"
            'JSON: {"modules": [{"title": "...", "goal": "...", "concepts": ["..."], '
            '"minutes": 30, "practice": "...", "assessment": "..."}]}'
        )
        data = self._ask_checked(self.curriculum_rules, instruction)
        return Curriculum(modules=data.get("modules", []))

    # ------------------------------------------------------------- 2단계
    def write_module(
        self, curriculum: Curriculum, index: int, previous_summary: str = "",
    ) -> ModuleResult:
        """모듈 하나의 슬라이드를 만든다. 실패하면 이 모듈만 다시 시도한다."""
        module = curriculum.modules[index - 1]
        concepts = module.get("concepts", [])
        concept_lines = "\n".join(f"  {i}. {c}" for i, c in enumerate(concepts, start=1))

        context = (
            f"{self._brief()}\n"
            f"[이번 모듈] {index}. {module.get('title', '')}\n"
            f"[학습 목표] {module.get('goal', '')}\n"
            f"[핵심 개념]\n{concept_lines}\n"
            f"[실습 과제] {module.get('practice', '')}\n"
            f"[시간] {module.get('minutes', 0)}분\n\n"
            f"이 모듈의 슬라이드를 만드세요.\n"
            f"- concept 슬라이드 {len(concepts)}장 (핵심 개념 순서대로)\n"
            f"- practice 슬라이드 1장 (실습 단계를 순서대로)\n"
            f"- summary 슬라이드 1장 (본문 3줄)\n"
            f"- 본문 한 줄 {MAX_LINE_CHARS}자 이내, 슬라이드당 {MAX_BODY_LINES}줄 이내\n"
            f"- 발표자 노트는 슬라이드마다 {NOTE_MIN_CHARS}~{NOTE_MAX_CHARS}자\n"
        )
        if previous_summary:
            context += (
                f"\n[앞 모듈 요약] {previous_summary}\n"
                "이 내용을 전제로 쓰고 같은 설명을 반복하지 마세요.\n"
            )

        result = ModuleResult(number=index)
        user = context
        for attempt in range(1, MAX_RETRIES + 2):
            result.attempts = attempt
            try:
                payload = self.ask_fn(
                    self.slide_rules, user, model=self.model, json_mode=True
                )
            except LLMError as exc:
                result.error = str(exc)
                continue

            slides = [
                Slide(
                    kind=str(item.get("kind", "concept")),
                    title=str(item.get("title", "")).strip(),
                    body=[str(line).strip() for line in item.get("body", []) if str(line).strip()],
                    note=str(item.get("note", "")).strip(),
                )
                for item in payload.get("slides", [])
            ]
            result.slides = slides
            result.error = ""

            banned = banned_phrases.check("\n".join(_collect_strings(payload)))
            result.banned = banned
            if not banned:
                return result

            user = (
                f"{context}\n[재작성 요청] 금지 문구가 들어갔습니다: {', '.join(banned)}\n"
                "해당 표현을 빼고 다시 쓰세요."
            )

        return result

    # ------------------------------------------------------------- 공통
    def _ask_checked(self, system: str, instruction: str) -> dict[str, Any]:
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
