"""후킹 대본 생성기 — 후크 10개 → 본문 → 제목 → 체크리스트.

호출 순서
    1. 후크 10개 생성 (각각 멈춤 이유 태그와 예상 강도)
    2. 그중 하나를 골라 (기본 1위, --hook-index 로 변경) 본문 생성
    3. 본문을 컨텍스트로 제목·썸네일 문구 생성
    4. 양산형 회피 체크리스트 생성

검사 두 가지가 생성 뒤에 붙는다.
    - 금지 문구 (:mod:`shared.banned_phrases`)
    - 길이 제한 (쇼츠 자막 15자, 제목 40자, 썸네일 12자)

둘 다 걸리면 해당 섹션만 최대 2회 다시 만들고, 그래도 남으면 기계적으로 고친 뒤
build 결과에 경고로 남긴다. 조용히 넘어가지 않는다.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from hook_script.schema import (  # noqa: E402
    CTA_LABEL, SHORTS_CAPTION_LIMIT, ScriptInput, Segment, THUMBNAIL_LIMIT,
    TITLE_LIMIT, TONE_LABEL, segments_for, timecode,
)
from shared import banned_phrases  # noqa: E402
from shared.ai_label import add_text_label, label_text_for  # noqa: E402
from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import ask as default_ask  # noqa: E402

__all__ = ["ScriptGenerator", "ScriptResult", "SectionResult", "write_outputs", "wrap_caption"]

#: 상품 폴더 (이 패키지의 부모).
BASE_DIR = Path(__file__).resolve().parents[1]
PROMPTS_DIR = BASE_DIR / "prompts"

#: 섹션당 최대 재생성 횟수.
MAX_REGENERATIONS = 2

#: 롱폼 기본 챕터 수.
DEFAULT_CHAPTERS = 6


@dataclass
class SectionResult:
    """섹션 하나의 생성 결과와 검사 이력."""

    name: str
    data: dict[str, Any]
    attempts: int = 1
    banned: list[str] = field(default_factory=list)
    length_fixes: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.banned and not self.length_fixes


@dataclass
class ScriptResult:
    """대본 한 편의 전체 생성 결과."""

    data: ScriptInput
    segments: list[Segment]
    sections: dict[str, SectionResult]
    hook_index: int
    model: str
    ai_label: bool
    generated_at: datetime

    @property
    def chosen_hook(self) -> dict[str, Any]:
        hooks = self.sections["hooks"].data.get("hooks", [])
        if not hooks:
            return {"text": self.data.topic, "tags": [], "strength": 0}
        return hooks[min(self.hook_index, len(hooks) - 1)]

    @property
    def warnings(self) -> list[SectionResult]:
        return [s for s in self.sections.values() if not s.clean]


# ------------------------------------------------------------------ 길이 보정
def wrap_caption(text: str, limit: int = SHORTS_CAPTION_LIMIT) -> list[str]:
    """자막 한 줄을 limit 글자 이하 여러 줄로 쪼갠다.

    띄어쓰기에서 끊는 것을 우선하고, 한 단어가 limit 보다 길면 글자 수로 자른다.
    LLM 이 규칙을 못 지켰을 때의 마지막 안전장치다.
    """
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []

    lines: list[str] = []
    current = ""
    for word in text.split():
        while len(word) > limit:  # 한 단어가 한 줄보다 긴 경우
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


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip()


def _collect_strings(value: Any) -> list[str]:
    """중첩 JSON 에서 문자열만 모은다 (금지 문구 검사용)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _collect_strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _collect_strings(item)]
    return []


class ScriptGenerator:
    """입력 하나로 대본 산출물 5종을 만든다.

    Args:
        data: 검증된 입력.
        model: Claude 모델 ID.
        ask_fn: LLM 호출 함수. 테스트·모의 실행에서 교체한다.
        ai_label: AI 생성물 표시 여부. 기본 on (CLAUDE.md §7).
        hook_index: 쓸 후크 번호 (0부터). 기본 0 = 강도 1위.
        chapters: 롱폼 챕터 수 (5~7).
    """

    def __init__(
        self,
        data: ScriptInput,
        model: str = DEFAULT_MODEL,
        ask_fn: Callable[..., Any] = default_ask,
        ai_label: bool = True,
        hook_index: int = 0,
        chapters: int = DEFAULT_CHAPTERS,
    ) -> None:
        self.data = data
        self.model = model
        self.ask_fn = ask_fn
        self.ai_label = ai_label
        self.hook_index = max(0, hook_index)
        self.segments = segments_for(data, chapters)
        self.sections: dict[str, SectionResult] = {}

        self.common = (PROMPTS_DIR / "common.md").read_text(encoding="utf-8")
        format_file = "format_shorts.md" if data.is_short_form else "format_long.md"
        self.format_rules = (PROMPTS_DIR / format_file).read_text(encoding="utf-8")

    # ------------------------------------------------------------- 프롬프트
    def _system(self) -> str:
        return f"{self.common}\n\n---\n\n{self.format_rules}"

    def _brief(self) -> str:
        evidence = (
            "\n".join(f"  - {item}" for item in self.data.evidence)
            if self.data.evidence
            else "  (없음 — 수치·출처·사례를 지어내지 말 것)"
        )
        segment_lines = "\n".join(
            f"  - {s.key}: {s.label} ({s.range_text}, {s.seconds}초)"
            + (f" — {s.instruction}" if s.instruction else "")
            for s in self.segments
        )
        return (
            f"[주제] {self.data.topic}\n"
            f"[포맷] {self.data.format_label} / 전체 {self.data.duration_sec}초\n"
            f"[시청자] {self.data.audience}\n"
            f"[톤] {self.data.tone} — {TONE_LABEL[self.data.tone]}\n"
            f"[CTA] {self.data.cta} — {CTA_LABEL[self.data.cta]}\n"
            f"[참고 자료]\n{evidence}\n"
            f"[구간]\n{segment_lines}\n"
        )

    # -------------------------------------------------------- 생성 + 재시도
    def _generate(
        self,
        name: str,
        instruction: str,
        length_check: Callable[[dict], list[str]] | None = None,
    ) -> SectionResult:
        """섹션을 만들고 금지 문구·길이 위반이 있으면 최대 2회 다시 만든다."""
        system = self._system()
        base_user = f"{self._brief()}\n{instruction}"
        user = base_user
        data: dict[str, Any] = {}
        banned: list[str] = []
        too_long: list[str] = []

        for attempt in range(1, MAX_REGENERATIONS + 2):
            data = self.ask_fn(system, user, model=self.model, json_mode=True)
            banned = banned_phrases.check("\n".join(_collect_strings(data)))
            too_long = length_check(data) if length_check else []
            if not banned and not too_long:
                return SectionResult(name=name, data=data, attempts=attempt)

            problems = []
            if banned:
                problems.append(f"금지 문구가 들어갔습니다: {', '.join(banned)}")
            if too_long:
                shown = too_long[:5]
                problems.append(
                    "글자 수 제한을 넘긴 줄이 있습니다: "
                    + " / ".join(shown)
                    + (f" 외 {len(too_long) - 5}건" if len(too_long) > 5 else "")
                )
            user = (
                f"{base_user}\n\n[재작성 요청]\n"
                + "\n".join(f"- {p}" for p in problems)
                + "\n해당 부분을 고쳐서 처음부터 다시 쓰세요."
            )

        return SectionResult(
            name=name, data=data, attempts=MAX_REGENERATIONS + 1,
            banned=banned, length_fixes=too_long,
        )

    # ------------------------------------------------------------ 섹션 정의
    def _hooks(self) -> SectionResult:
        return self._generate(
            "hooks",
            "첫 3초에 쓸 후크 후보 10개를 만드세요.\n"
            "- 각 후크는 멈춤 이유 2개 이상을 결합하고, 쓴 이유를 tags 에 적습니다.\n"
            "- strength 는 이 시청자에게 통할 것 같은 정도를 1~5 로 스스로 매깁니다.\n"
            "- reason 에 왜 그 강도인지 한 줄로 적습니다.\n"
            "- 10개가 서로 다른 조합이 되게 하세요. strength 내림차순으로 정렬합니다.\n"
            + (
                f"- 쇼츠 자막이므로 text 는 {SHORTS_CAPTION_LIMIT}자 이내로 씁니다.\n"
                if self.data.is_short_form else ""
            )
            + 'JSON: {"hooks": [{"text": "...", "tags": ["호기심","손실회피"], '
              '"strength": 5, "reason": "..."}]}',
            length_check=self._check_hooks if self.data.is_short_form else None,
        )

    def _check_hooks(self, data: dict) -> list[str]:
        return [
            f"후크 {i + 1}({len(item.get('text', ''))}자)"
            for i, item in enumerate(data.get("hooks", []))
            if len(str(item.get("text", ""))) > SHORTS_CAPTION_LIMIT
        ]

    def _script(self, hook: dict[str, Any]) -> SectionResult:
        instruction = (
            f"확정된 후크: {hook.get('text', '')}\n"
            f"(사용한 멈춤 이유: {', '.join(hook.get('tags', []))})\n\n"
            "이 후크로 시작하는 본문을 구간 순서대로 쓰세요.\n"
            "human_slots 에는 사람이 직접 채워야 할 자리를 3가지 적습니다 "
            "(개인 경험 / 실제 사례 / 시청자 의견).\n"
        )
        if self.data.is_short_form:
            instruction += (
                f"자막 한 줄은 반드시 {SHORTS_CAPTION_LIMIT}자 이내입니다. "
                "길면 의미 단위로 나눠 여러 줄로 만드세요."
            )
            return self._generate("script", instruction, length_check=self._check_captions)
        return self._generate("script", instruction)

    def _check_captions(self, data: dict) -> list[str]:
        violations = []
        for segment in data.get("segments", []):
            for line in segment.get("captions", []):
                if len(str(line)) > SHORTS_CAPTION_LIMIT:
                    violations.append(f"{segment.get('key')}:{len(str(line))}자 \"{line}\"")
        return violations

    def _titles(self, script: dict[str, Any]) -> SectionResult:
        return self._generate(
            "titles",
            f"본문 요약: {json.dumps(script, ensure_ascii=False)[:900]}\n\n"
            f"제목 후보 10개({TITLE_LIMIT}자 이내)와 썸네일 문구 5개({THUMBNAIL_LIMIT}자 이내)를 만드세요.\n"
            "제목은 검색되는 말과 클릭되는 말을 섞습니다. 썸네일 문구는 짧을수록 좋습니다.\n"
            "과장하지 말고, 본문에 없는 내용을 제목에 넣지 마세요.\n"
            'JSON: {"titles": [{"text": "...", "tags": ["호기심"]}], "thumbnails": ["...", "..."]}',
            length_check=self._check_titles,
        )

    def _check_titles(self, data: dict) -> list[str]:
        violations = [
            f"제목 {i + 1}({len(str(item.get('text', '')))}자)"
            for i, item in enumerate(data.get("titles", []))
            if len(str(item.get("text", ""))) > TITLE_LIMIT
        ]
        violations += [
            f"썸네일 {i + 1}({len(str(text))}자)"
            for i, text in enumerate(data.get("thumbnails", []))
            if len(str(text)) > THUMBNAIL_LIMIT
        ]
        return violations

    def _checklist(self, script: dict[str, Any]) -> SectionResult:
        return self._generate(
            "checklist",
            f"본문 요약: {json.dumps(script, ensure_ascii=False)[:900]}\n\n"
            "이 대본을 그대로 찍으면 양산형 콘텐츠로 분류될 수 있습니다 "
            "(유튜브 2025.7 비진정성 콘텐츠 정책).\n"
            "이 대본에 **사람이 반드시 추가해야 할 것** 3가지를 구체적으로 제안하세요.\n"
            "각 항목은 kind(personal_experience | real_case | audience_voice), "
            "where(어느 구간인지 key), what(무엇을 넣어야 하는지), why(왜 필요한지), "
            "how(어떻게 구하는지) 를 포함합니다.\n"
            "일반론 말고 이 주제에 맞는 구체적인 제안을 하세요.\n"
            'JSON: {"additions": [{"kind": "...", "where": "hook", "what": "...", '
            '"why": "...", "how": "..."}]}',
        )

    # ------------------------------------------------------------------ 실행
    def build(self) -> ScriptResult:
        hooks = self._hooks()
        self.sections["hooks"] = hooks

        hook_list = hooks.data.get("hooks", [])
        index = min(self.hook_index, max(0, len(hook_list) - 1))
        chosen = hook_list[index] if hook_list else {"text": self.data.topic, "tags": []}

        script = self._script(chosen)
        # LLM 이 끝내 못 지킨 자막은 기계적으로 쪼갠다. 경고는 그대로 남긴다.
        if self.data.is_short_form and script.length_fixes:
            for segment in script.data.get("segments", []):
                wrapped: list[str] = []
                for line in segment.get("captions", []):
                    wrapped.extend(wrap_caption(str(line)))
                segment["captions"] = wrapped
        self.sections["script"] = script

        titles = self._titles(script.data)
        if titles.length_fixes:
            for item in titles.data.get("titles", []):
                item["text"] = _truncate(str(item.get("text", "")), TITLE_LIMIT)
            titles.data["thumbnails"] = [
                _truncate(str(text), THUMBNAIL_LIMIT)
                for text in titles.data.get("thumbnails", [])
            ]
        self.sections["titles"] = titles

        self.sections["checklist"] = self._checklist(script.data)

        return ScriptResult(
            data=self.data, segments=self.segments, sections=self.sections,
            hook_index=index, model=self.model, ai_label=self.ai_label,
            generated_at=datetime.now().astimezone(),
        )


# ==================================================================== 산출물 쓰기
def _segment_map(result: ScriptResult) -> dict[str, Segment]:
    return {s.key: s for s in result.segments}


def write_script(result: ScriptResult, out_dir: Path) -> Path:
    """script.md — 타임코드 구간별 대본."""
    data = result.data
    body = result.sections["script"].data
    segments = _segment_map(result)
    hook = result.chosen_hook

    lines = [
        f"# {data.topic}",
        "",
        f"- 포맷: {data.format_label} / {data.duration_sec}초",
        f"- 시청자: {data.audience}",
        f"- 톤: {data.tone} · CTA: {data.cta}",
        f"- 사용한 후크: **{hook.get('text', '')}** "
        f"(멈춤 이유: {', '.join(hook.get('tags', []))}, 강도 {hook.get('strength', '-')})",
        "",
        "> 초안입니다. 촬영 전에 반드시 사람이 읽고 고치세요. "
        "`checklist.md` 의 3가지를 채우지 않으면 양산형으로 분류될 수 있습니다.",
        "",
        "---",
        "",
    ]

    if data.is_short_form:
        rendered = {s.get("key"): s for s in body.get("segments", [])}
        for segment in result.segments:
            block = rendered.get(segment.key, {})
            lines.append(f"## [{segment.range_text}] {segment.label}")
            if block.get("note"):
                lines.append(f"*화면: {block['note']}*")
            lines.append("")
            for caption in block.get("captions", []):
                lines.append(f"- {caption}")
            lines.append("")
    else:
        lines.append(f"## [{segments['hook'].range_text}] 후크")
        lines.append("")
        lines.append(str(body.get("hook", {}).get("body", "")).strip())
        lines.append("")
        lines.append(f"## [{segments['promise'].range_text}] 약속")
        lines.append("")
        lines.append(str(body.get("promise", {}).get("body", "")).strip())
        lines.append("")
        for chapter in body.get("chapters", []):
            segment = segments.get(chapter.get("key", ""), None)
            head = f"## [{segment.range_text}] " if segment else "## "
            lines.append(f"{head}{chapter.get('title', '')}")
            lines.append("")
            if chapter.get("key_sentence"):
                lines.append(f"> **핵심:** {chapter['key_sentence']}")
                lines.append("")
            lines.append(str(chapter.get("body", "")).strip())
            lines.append("")
            if chapter.get("example"):
                lines.append(f"**예시** — {chapter['example']}")
                lines.append("")
            if chapter.get("transition"):
                lines.append(f"*전환* — {chapter['transition']}")
                lines.append("")
        lines.append(f"## [{segments['summary'].range_text}] 요약")
        lines.append("")
        lines.append(str(body.get("summary", {}).get("body", "")).strip())
        lines.append("")
        lines.append(f"## [{segments['cta'].range_text}] CTA")
        lines.append("")
        lines.append(str(body.get("cta", {}).get("body", "")).strip())
        lines.append("")

    slots = body.get("human_slots", [])
    if slots:
        lines += ["---", "", "## 사람이 채울 자리", ""]
        lines += [f"- {slot}" for slot in slots]
        lines.append("")

    text = "\n".join(lines).rstrip() + "\n"
    if result.ai_label:
        text = add_text_label(text) + "\n"

    path = out_dir / "script.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_hooks(result: ScriptResult, out_dir: Path) -> Path:
    """hooks.json — 후크 후보 10개."""
    payload = {
        "topic": result.data.topic,
        "format": result.data.format,
        "generated_at": result.generated_at.isoformat(),
        "chosen_index": result.hook_index,
        "hooks": result.sections["hooks"].data.get("hooks", []),
    }
    path = out_dir / "hooks.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_titles(result: ScriptResult, out_dir: Path) -> Path:
    """titles.json — 제목 10개, 썸네일 문구 5개."""
    titles = result.sections["titles"].data
    payload = {
        "topic": result.data.topic,
        "generated_at": result.generated_at.isoformat(),
        "limits": {"title": TITLE_LIMIT, "thumbnail": THUMBNAIL_LIMIT},
        "titles": titles.get("titles", []),
        "thumbnails": titles.get("thumbnails", []),
    }
    path = out_dir / "titles.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


KIND_LABEL = {
    "personal_experience": "개인 경험",
    "real_case": "실제 사례",
    "audience_voice": "시청자 의견",
}


def write_checklist(result: ScriptResult, out_dir: Path) -> Path:
    """checklist.md — 양산형 판정 회피 체크리스트."""
    additions = result.sections["checklist"].data.get("additions", [])
    segments = _segment_map(result)

    lines = [
        f"# 발행 전 체크리스트 — {result.data.topic}",
        "",
        "유튜브는 2025년 7월부터 '양산형(비진정성) 콘텐츠'를 수익화에서 제외합니다.",
        "AI가 쓴 대본을 그대로 읽어 올리면 여기에 걸릴 수 있습니다.",
        "**아래 3가지를 채우는 것이 이 대본을 내 것으로 만드는 작업입니다.**",
        "",
        "## 1. 사람이 반드시 추가할 것",
        "",
    ]
    for index, item in enumerate(additions, start=1):
        kind = KIND_LABEL.get(item.get("kind", ""), item.get("kind", ""))
        where = item.get("where", "")
        segment = segments.get(where)
        location = f"{segment.label} ({segment.range_text})" if segment else where
        lines += [
            f"### {index}. {kind}",
            "",
            f"- **넣을 위치**: {location}",
            f"- **무엇을**: {item.get('what', '')}",
            f"- **왜**: {item.get('why', '')}",
            f"- **어떻게 구하나**: {item.get('how', '')}",
            "- [ ] 채웠음",
            "",
        ]

    lines += [
        "## 2. 대본 점검",
        "",
        "- [ ] 대본에 남은 `[사람이 채울 곳: ...]` 표시를 모두 처리했다",
        "- [ ] 수치·출처가 실제 자료와 일치한다 (참고 자료를 넣지 않았다면 수치가 아예 없어야 한다)",
        "- [ ] 다른 채널의 구성이나 문장을 그대로 따라가지 않았다",
        "- [ ] 성과를 단정하는 표현이 없다",
        "",
        "## 3. 업로드 점검",
        "",
        "- [ ] 설명란에 `ai_label.txt` 의 고지 문구를 넣었다",
        "- [ ] 유튜브 업로드 화면의 '변경된 콘텐츠 또는 합성 콘텐츠' 항목을 사실대로 체크했다",
        "- [ ] 썸네일 문구가 제목·본문과 어긋나지 않는다 (낚시성 제목은 노출이 줄어듭니다)",
        "- [ ] 자막을 직접 확인했다",
        "",
        "## 4. 생성 정보",
        "",
        f"- 생성 시각: {result.generated_at.strftime('%Y-%m-%d %H:%M:%S %z')}",
        f"- 모델: {result.model}",
        f"- 포맷: {result.data.format_label} / {result.data.duration_sec}초",
        f"- 쓴 후크: {result.chosen_hook.get('text', '')} (후보 {result.hook_index + 1}번)",
        "",
        "### 자동 검사 결과",
        "",
        "| 섹션 | 생성 시도 | 금지 문구 | 길이 제한 |",
        "|---|---|---|---|",
    ]
    for name, section in result.sections.items():
        banned = ", ".join(section.banned) if section.banned else "통과"
        length = f"⚠ {len(section.length_fixes)}건 자동 보정" if section.length_fixes else "통과"
        lines.append(f"| {name} | {section.attempts}회 | {banned} | {length} |")

    if result.warnings:
        lines += [
            "",
            "> ⚠ **사람이 확인해야 합니다.** 위 표에 통과가 아닌 항목이 있습니다. "
            "금지 문구는 직접 고치고, 자동 보정된 자막은 의미가 끊기지 않았는지 확인하세요.",
        ]
    lines.append("")

    text = "\n".join(lines)
    if result.ai_label:
        text = add_text_label(text) + "\n"

    path = out_dir / "checklist.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_ai_label(result: ScriptResult, out_dir: Path) -> Path:
    """ai_label.txt — 설명란에 붙여 넣을 AI 사용 고지."""
    notice = label_text_for("ko")
    text = (
        "[영상 설명란에 붙여 넣으세요]\n\n"
        f"{notice}\n"
        "대본 초안을 생성형 AI로 작성한 뒤 사람이 검수·수정하여 제작했습니다.\n\n"
        "---\n"
        "왜 넣나요\n"
        "- 인공지능기본법 제31조(2026-01-22 시행)에 따른 AI 생성물 표시입니다.\n"
        "- 유튜브 업로드 화면의 '변경된 콘텐츠 또는 합성 콘텐츠' 항목도 사실대로 체크하세요.\n"
        "- 목소리나 얼굴을 AI로 합성했다면 그 사실도 함께 밝혀야 합니다.\n"
    )
    path = out_dir / "ai_label.txt"
    path.write_text(text, encoding="utf-8")
    return path


def write_outputs(result: ScriptResult, out_root: Path) -> Path:
    """산출물 5종을 `out_root/<slug>/` 에 쓰고 폴더 경로를 돌려준다."""
    out_dir = out_root / result.data.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    write_script(result, out_dir)
    write_hooks(result, out_dir)
    write_titles(result, out_dir)
    write_checklist(result, out_dir)
    write_ai_label(result, out_dir)
    return out_dir
