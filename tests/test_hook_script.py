"""products/hook-script 테스트.

가짜 LLM(`sample_content.fake_ask`)을 주입해 실제 Claude 호출 없이
생성 → 검사 → 산출물 쓰기 전 과정을 검증한다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from hook_script import generator as gen
from hook_script.sample_content import fake_ask
from hook_script.schema import (
    SHORTS_CAPTION_LIMIT, ScriptInput, THUMBNAIL_LIMIT, TITLE_LIMIT,
    load_input, long_segments, shorts_segments, timecode,
)
from shared import banned_phrases

HOOK_DIR = Path(gen.BASE_DIR)
EXAMPLE_YAML = HOOK_DIR / "script_input.yaml"

CAPTION_RE = re.compile(r"^- (?P<text>.+)$", re.MULTILINE)


# ------------------------------------------------------------------ 픽스처
def _input(**overrides) -> ScriptInput:
    payload = {
        "topic": "테스트 주제",
        "format": "shorts",
        "duration_sec": 30,
        "audience": "테스트 시청자",
        "tone": "정보형",
        "cta": "구독",
        "evidence": [],
    }
    payload.update(overrides)
    return ScriptInput(**payload)


def _build(data: ScriptInput, tmp_path: Path, **kwargs):
    result = gen.ScriptGenerator(data, model="test", ask_fn=fake_ask, **kwargs).build()
    return gen.write_outputs(result, tmp_path), result


@pytest.fixture
def shorts_build(tmp_path):
    return _build(_input(format="shorts", duration_sec=30), tmp_path)


@pytest.fixture
def long_build(tmp_path):
    return _build(_input(format="long", duration_sec=600), tmp_path)


# --------------------------------------------------------------- 입력 검증
def test_example_yaml_loads():
    data = load_input(EXAMPLE_YAML)
    assert data.format in {"long", "shorts", "reels"}
    assert data.evidence == [], "예시는 자료 없이 시작하도록 비워둔다"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"format": "shorts", "duration_sec": 14}, "쇼츠 최소 미만"),
        ({"format": "shorts", "duration_sec": 61}, "쇼츠 최대 초과"),
        ({"format": "reels", "duration_sec": 120}, "릴스 범위 밖"),
        ({"format": "long", "duration_sec": 299}, "롱폼 최소 미만"),
        ({"format": "long", "duration_sec": 1201}, "롱폼 최대 초과"),
        ({"format": "tiktok"}, "지원하지 않는 포맷"),
        ({"tone": "감성형"}, "정의되지 않은 톤"),
        ({"cta": "좋아요"}, "정의되지 않은 CTA"),
        ({"topic": "  "}, "빈 주제"),
        ({"evidence": ["자료", ""]}, "빈 항목"),
    ],
)
def test_invalid_input_rejected(overrides, reason):
    with pytest.raises(ValidationError):
        _input(**overrides)


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        _input(채널명="어떤채널")


@pytest.mark.parametrize(("fmt", "duration"), [("shorts", 15), ("shorts", 60), ("reels", 30),
                                               ("long", 300), ("long", 1200)])
def test_boundary_durations_accepted(fmt, duration):
    assert _input(format=fmt, duration_sec=duration).duration_sec == duration


def test_slug_includes_format_and_duration():
    assert _input(topic="테스트", format="shorts", duration_sec=30).slug.endswith("-shorts-30s")


# --------------------------------------------------------------- 타임코드
@pytest.mark.parametrize("duration", [15, 20, 30, 45, 60])
def test_shorts_segments_cover_whole_duration(duration):
    segments = shorts_segments(duration)
    assert segments[0].start == 0
    assert segments[-1].end == duration
    assert [s.key for s in segments] == ["hook", "problem", "point1", "point2", "point3", "cta"]
    for earlier, later in zip(segments, segments[1:]):
        assert earlier.end == later.start, "구간 사이에 빈틈이 있으면 안 됩니다"
        assert earlier.seconds > 0


def test_shorts_30s_matches_spec():
    """사양 예시: [0~3 후크] [3~ 문제] [~ 핵심3] [마지막 CTA]"""
    segments = {s.key: s for s in shorts_segments(30)}
    assert (segments["hook"].start, segments["hook"].end) == (0, 3)
    assert segments["cta"].end == 30
    assert segments["cta"].seconds <= 5


@pytest.mark.parametrize("duration", [300, 600, 900, 1200])
@pytest.mark.parametrize("chapters", [5, 6, 7])
def test_long_segments_structure(duration, chapters):
    segments = long_segments(duration, chapters)
    keys = [s.key for s in segments]
    assert keys[0] == "hook" and keys[1] == "promise"
    assert keys[-2] == "summary" and keys[-1] == "cta"
    assert len([k for k in keys if k.startswith("chapter")]) == chapters
    assert segments[0].end == 30, "롱폼 후크는 30초"
    assert segments[-1].end == duration
    for earlier, later in zip(segments, segments[1:]):
        assert earlier.end == later.start


def test_long_chapter_count_clamped():
    assert len([s for s in long_segments(600, 2) if s.key.startswith("chapter")]) == 5
    assert len([s for s in long_segments(600, 99) if s.key.startswith("chapter")]) == 7


def test_timecode_format():
    assert timecode(0) == "0:00"
    assert timecode(75) == "1:15"
    assert timecode(600) == "10:00"


# ------------------------------------------------------- 자막 15자 (핵심)
def _caption_lines(script_md: str) -> list[str]:
    """script.md 본문의 자막 줄만 뽑는다.

    머리말(포맷·시청자·톤)과 '사람이 채울 자리' 목록은 자막이 아니므로 뺀다.
    본문은 첫 번째 `---` 구분선 다음부터 시작한다.
    """
    body = script_md.split("\n---\n", 1)[-1]
    body = body.split("## 사람이 채울 자리")[0]
    return [m.group("text").strip() for m in CAPTION_RE.finditer(body)]


@pytest.mark.parametrize("duration", [15, 30, 45, 60])
def test_shorts_captions_never_exceed_15_chars(tmp_path, duration):
    out_dir, _ = _build(_input(format="shorts", duration_sec=duration), tmp_path)
    lines = _caption_lines((out_dir / "script.md").read_text(encoding="utf-8"))

    assert lines, "자막이 하나도 없습니다"
    too_long = [f"{len(line)}자: {line}" for line in lines if len(line) > SHORTS_CAPTION_LIMIT]
    assert too_long == [], f"{duration}초 대본에 15자 초과 자막이 있습니다"


def test_reels_captions_also_limited(tmp_path):
    out_dir, _ = _build(_input(format="reels", duration_sec=30), tmp_path)
    lines = _caption_lines((out_dir / "script.md").read_text(encoding="utf-8"))
    assert all(len(line) <= SHORTS_CAPTION_LIMIT for line in lines)


def test_long_caption_is_wrapped_as_last_resort(tmp_path):
    """LLM 이 끝내 규칙을 못 지켜도 산출물에는 15자 초과가 없어야 한다."""
    def sloppy_ask(system, user, model="test", json_mode=False, **kw):
        data = json.loads(json.dumps(fake_ask(system, user, model, json_mode)))
        if "본문을 구간 순서대로" in user:
            data["segments"][0]["captions"] = [
                "이건 열다섯 글자를 훌쩍 넘기는 아주 긴 자막 줄입니다"
            ]
        return data

    result = gen.ScriptGenerator(
        _input(), model="test", ask_fn=sloppy_ask
    ).build()
    out_dir = gen.write_outputs(result, tmp_path)

    lines = _caption_lines((out_dir / "script.md").read_text(encoding="utf-8"))
    assert all(len(line) <= SHORTS_CAPTION_LIMIT for line in lines)
    assert result.sections["script"].length_fixes, "자동 보정 사실을 기록해야 합니다"
    assert "자동 보정" in (out_dir / "checklist.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "text",
    [
        "이건 열다섯 글자를 넘기는 긴 문장입니다",
        "짧은 줄",
        "띄어쓰기없이아주긴한단어가들어있는경우도처리해야합니다",
        "",
    ],
)
def test_wrap_caption_never_exceeds_limit(text):
    assert all(len(line) <= SHORTS_CAPTION_LIMIT for line in gen.wrap_caption(text))


def test_wrap_caption_keeps_all_characters():
    text = "이건 열다섯 글자를 넘기는 긴 문장입니다"
    joined = "".join(gen.wrap_caption(text)).replace(" ", "")
    assert joined == text.replace(" ", ""), "글자를 잃어버리면 안 됩니다"


# -------------------------------------------------------------- 산출물 5종
def test_shorts_produces_all_five_outputs(shorts_build):
    out_dir, _ = shorts_build
    for name in ("script.md", "hooks.json", "titles.json", "checklist.md", "ai_label.txt"):
        assert (out_dir / name).is_file(), name


def test_long_produces_all_five_outputs(long_build):
    out_dir, _ = long_build
    for name in ("script.md", "hooks.json", "titles.json", "checklist.md", "ai_label.txt"):
        assert (out_dir / name).is_file(), name


def test_shorts_script_has_all_timecoded_sections(shorts_build):
    out_dir, result = shorts_build
    text = (out_dir / "script.md").read_text(encoding="utf-8")
    for segment in result.segments:
        assert f"[{segment.range_text}] {segment.label}" in text, segment.key


def test_long_script_has_chapters_and_transitions(long_build):
    out_dir, _ = long_build
    text = (out_dir / "script.md").read_text(encoding="utf-8")
    assert "## [0:00~0:30] 후크" in text
    assert "## [0:30~1:00] 약속" in text
    assert text.count("*전환* —") >= 5, "챕터마다 전환 문장이 있어야 합니다"
    assert "**핵심:**" in text
    assert "## [9:30~10:00] CTA" in text


def test_hooks_json_has_ten_candidates_with_tags(shorts_build):
    out_dir, _ = shorts_build
    payload = json.loads((out_dir / "hooks.json").read_text(encoding="utf-8"))
    assert len(payload["hooks"]) == 10
    for hook in payload["hooks"]:
        assert len(hook["tags"]) >= 2, "멈춤 이유 2개 이상을 결합해야 합니다"
        assert 1 <= hook["strength"] <= 5


def test_hook_tags_come_from_the_eight_reasons(shorts_build):
    out_dir, _ = shorts_build
    allowed = {"돈", "시간", "관계", "지위", "안전", "호기심", "비교", "손실회피"}
    payload = json.loads((out_dir / "hooks.json").read_text(encoding="utf-8"))
    for hook in payload["hooks"]:
        assert set(hook["tags"]) <= allowed, hook


def test_titles_respect_length_limits(shorts_build):
    out_dir, _ = shorts_build
    payload = json.loads((out_dir / "titles.json").read_text(encoding="utf-8"))
    assert len(payload["titles"]) == 10
    assert len(payload["thumbnails"]) == 5
    assert all(len(t["text"]) <= TITLE_LIMIT for t in payload["titles"])
    assert all(len(t) <= THUMBNAIL_LIMIT for t in payload["thumbnails"])


def test_over_long_titles_are_truncated(tmp_path):
    def long_title_ask(system, user, model="test", json_mode=False, **kw):
        data = json.loads(json.dumps(fake_ask(system, user, model, json_mode)))
        if "제목 후보 10개" in user:
            data["titles"][0]["text"] = "가" * 80
            data["thumbnails"][0] = "나" * 40
        return data

    result = gen.ScriptGenerator(_input(), model="test", ask_fn=long_title_ask).build()
    out_dir = gen.write_outputs(result, tmp_path)
    payload = json.loads((out_dir / "titles.json").read_text(encoding="utf-8"))
    assert all(len(t["text"]) <= TITLE_LIMIT for t in payload["titles"])
    assert all(len(t) <= THUMBNAIL_LIMIT for t in payload["thumbnails"])


def test_checklist_proposes_three_human_additions(shorts_build):
    out_dir, _ = shorts_build
    text = (out_dir / "checklist.md").read_text(encoding="utf-8")
    for label in ("개인 경험", "실제 사례", "시청자 의견"):
        assert label in text, label
    assert "양산형" in text
    assert text.count("- [ ]") >= 8, "체크박스가 충분해야 합니다"


def test_ai_label_file_mentions_law_and_youtube(shorts_build):
    out_dir, _ = shorts_build
    text = (out_dir / "ai_label.txt").read_text(encoding="utf-8")
    assert "인공지능기본법" in text
    assert "합성 콘텐츠" in text


# ----------------------------------------------------------- 후크 선택
def test_hook_index_selects_different_hook(tmp_path):
    _, first = _build(_input(), tmp_path / "a", hook_index=0)
    _, third = _build(_input(), tmp_path / "b", hook_index=2)
    assert first.chosen_hook["text"] != third.chosen_hook["text"]
    assert third.hook_index == 2


def test_hook_index_beyond_range_falls_back_to_last(tmp_path):
    _, result = _build(_input(), tmp_path, hook_index=99)
    assert result.hook_index == 9, "후보가 10개면 마지막으로 떨어져야 합니다"


def test_chosen_hook_appears_in_script(shorts_build):
    out_dir, result = shorts_build
    text = (out_dir / "script.md").read_text(encoding="utf-8")
    assert result.chosen_hook["text"] in text


# ------------------------------------------------------------ 금지 문구
def _all_text(out_dir: Path) -> str:
    return "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(out_dir.rglob("*")) if p.is_file()
    )


def test_outputs_contain_no_banned_phrases(shorts_build, long_build):
    for out_dir, _ in (shorts_build, long_build):
        assert banned_phrases.check(_all_text(out_dir)) == []


def test_banned_phrase_triggers_regeneration(tmp_path):
    state = {"calls": 0}

    def dirty_first(system, user, model="test", json_mode=False, **kw):
        state["calls"] += 1
        if "후크 후보 10개" in user and state["calls"] == 1:
            return {"hooks": [{"text": "수익 보장 방법", "tags": ["돈", "시간"], "strength": 5}]}
        return fake_ask(system, user, model, json_mode)

    result = gen.ScriptGenerator(_input(), model="test", ask_fn=dirty_first).build()
    assert result.sections["hooks"].attempts == 2
    assert result.sections["hooks"].clean


def test_regeneration_limit_is_reported(tmp_path):
    def always_dirty(system, user, model="test", json_mode=False, **kw):
        if "후크 후보 10개" in user:
            return {"hooks": [{"text": "무조건 됩니다", "tags": ["돈", "시간"], "strength": 5}]}
        return fake_ask(system, user, model, json_mode)

    result = gen.ScriptGenerator(_input(), model="test", ask_fn=always_dirty).build()
    out_dir = gen.write_outputs(result, tmp_path)
    assert "무조건" in result.sections["hooks"].banned
    assert [s.name for s in result.warnings] == ["hooks"]
    assert "사람이 확인해야 합니다" in (out_dir / "checklist.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------- AI 표시
def test_ai_label_appended_by_default(shorts_build):
    out_dir, _ = shorts_build
    assert "생성형 AI" in (out_dir / "script.md").read_text(encoding="utf-8")


def test_ai_label_can_be_disabled(tmp_path):
    out_dir, _ = _build(_input(), tmp_path, ai_label=False)
    assert "생성형 AI" not in (out_dir / "script.md").read_text(encoding="utf-8")
    # ai_label.txt 는 고지 문구 자체가 목적이므로 항상 만든다
    assert (out_dir / "ai_label.txt").is_file()


# -------------------------------------------------------------- 프롬프트
def test_prompts_are_split_by_format():
    for name in ("common.md", "format_shorts.md", "format_long.md"):
        assert (HOOK_DIR / "prompts" / name).is_file(), name


def test_shorts_prompt_states_caption_limit():
    text = (HOOK_DIR / "prompts" / "format_shorts.md").read_text(encoding="utf-8")
    assert "15자" in text


def test_common_prompt_forbids_copying_channels():
    text = (HOOK_DIR / "prompts" / "common.md").read_text(encoding="utf-8")
    assert "베끼지 않는다" in text or "재현" in text
    assert "지어내지" in text


def test_generator_uses_format_specific_prompt():
    shorts = gen.ScriptGenerator(_input(format="shorts"), ask_fn=fake_ask)
    long = gen.ScriptGenerator(_input(format="long", duration_sec=600), ask_fn=fake_ask)
    assert "자막" in shorts.format_rules
    assert "챕터" in long.format_rules
    assert shorts.format_rules != long.format_rules


def test_evidence_absent_warns_model_not_to_invent():
    generator = gen.ScriptGenerator(_input(evidence=[]), ask_fn=fake_ask)
    assert "지어내지" in generator._brief()


def test_evidence_present_is_passed_through():
    generator = gen.ScriptGenerator(
        _input(evidence=["2026년 자체 설문 42명 중 31명"]), ask_fn=fake_ask
    )
    assert "42명 중 31명" in generator._brief()


# ------------------------------------------------------------------ 문서
def test_readme_has_human_review_warning():
    text = (HOOK_DIR / "README.md").read_text(encoding="utf-8")
    assert "초안" in text
    assert "사람 검수" in text or "사람이 검수" in text
    assert banned_phrases.check(text) == []


def test_product_manuals_are_clean_and_detailed():
    for name in ("admin.md", "client.md"):
        path = HOOK_DIR / "docs" / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert len(text) > 4000, f"{name} 이 너무 짧습니다"
        assert banned_phrases.check(text) == []
