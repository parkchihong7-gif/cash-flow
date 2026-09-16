"""products/funnel-builder 테스트.

실제 Claude 호출 없이 가짜 LLM(`tests/fake_funnel_llm.py`)을 주입해
파이프라인 전체(생성 → 금지 문구 검사 → 산출물 쓰기)를 돌린다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

import generator as gen
from fake_funnel_llm import always_dirty_ask, dirty_then_clean_ask, fake_ask
from schema import FunnelInput, load_input
from shared import banned_phrases

FUNNEL_DIR = Path(gen.BASE_DIR)
EXAMPLE_YAML = FUNNEL_DIR / "funnel_input.yaml"

FRONTMATTER_RE = re.compile(r"\A---\n(?P<meta>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)


# ------------------------------------------------------------------ 픽스처
@pytest.fixture
def sample_input() -> FunnelInput:
    return load_input(EXAMPLE_YAML)


@pytest.fixture
def built(tmp_path, sample_input):
    """가짜 LLM 으로 퍼널 한 건을 만들고 산출물 폴더를 돌려준다."""
    result = gen.FunnelGenerator(sample_input, model="test", ask_fn=fake_ask).build()
    return gen.write_outputs(result, tmp_path), result


# ------------------------------------------------------------- yaml 검증
def test_example_yaml_loads(sample_input):
    assert sample_input.product_name
    assert sample_input.price > 0
    assert 3 <= len(sample_input.pain_points) <= 5
    assert sample_input.cta_url.startswith("https://")


def test_example_yaml_has_every_required_key():
    raw = yaml.safe_load(EXAMPLE_YAML.read_text(encoding="utf-8"))
    required = {
        "product_name", "target", "price", "core_promise", "lead_magnet_title",
        "pain_points", "proof", "cta_url", "sender_name",
    }
    assert required <= set(raw)


def _valid_payload(**overrides):
    payload = {
        "product_name": "테스트 강의",
        "target": "테스트 대상",
        "price": 10000,
        "core_promise": "시간을 줄인다",
        "lead_magnet_title": "무료 자료",
        "pain_points": ["가", "나", "다"],
        "proof": [],
        "cta_url": "https://example.com/buy",
        "sender_name": "홍길동",
    }
    payload.update(overrides)
    return payload


def test_proof_defaults_to_empty_list():
    payload = _valid_payload()
    del payload["proof"]
    assert FunnelInput(**payload).proof == []


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"pain_points": ["가", "나"]}, "통증 3개 미만"),
        ({"pain_points": list("가나다라마바")}, "통증 5개 초과"),
        ({"price": 0}, "가격 0"),
        ({"price": -1000}, "가격 음수"),
        ({"cta_url": "example.com/buy"}, "스킴 없는 URL"),
        ({"product_name": "   "}, "공백 상품명"),
        ({"pain_points": ["가", "", "다"]}, "빈 항목"),
    ],
)
def test_invalid_input_rejected(overrides, reason):
    with pytest.raises(ValidationError):
        FunnelInput(**_valid_payload(**overrides))


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        FunnelInput(**_valid_payload(오타_필드="값"))


def test_load_input_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_input(tmp_path / "없음.yaml")


def test_load_input_non_mapping(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("- 리스트\n- 입니다\n", encoding="utf-8")
    with pytest.raises(ValueError, match="매핑"):
        load_input(path)


def test_slug_is_filesystem_safe(sample_input):
    assert "/" not in sample_input.slug
    assert " " not in sample_input.slug


# ------------------------------------------------------------- 산출물 5종
def test_build_creates_all_five_outputs(built):
    out_dir, _ = built
    assert (out_dir / "landing.html").is_file()
    assert (out_dir / "lead_magnet_outline.md").is_file()
    assert (out_dir / "copy_variants.json").is_file()
    assert (out_dir / "build_report.md").is_file()
    assert sorted(p.name for p in (out_dir / "emails").glob("*.md")) == [
        "01.md", "02.md", "03.md", "04.md", "05.md"
    ]


def test_landing_sections_in_fixed_order(built):
    out_dir, _ = built
    html = (out_dir / "landing.html").read_text(encoding="utf-8")
    markers = [
        "<!-- 1. 히어로 -->",
        "<!-- 2. 문제 공감 -->",
        "<!-- 3. 해결 약속 -->",
        "<!-- 4. 커리큘럼 -->",
        "<!-- 5. 증거",
        "<!-- 6. 가격·구성 -->",
        "<!-- 7. FAQ -->",
        "<!-- 8. 최종 CTA -->",
        "<!-- 9. 푸터 -->",
    ]
    positions = [html.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_landing_is_responsive_single_file(built):
    out_dir, _ = built
    html = (out_dir / "landing.html").read_text(encoding="utf-8")
    assert 'name="viewport"' in html
    assert "@media (min-width: 768px)" in html
    assert "<style>" in html          # CSS 인라인
    assert "<link" not in html        # 외부 CSS 없음
    assert "<script" not in html      # 외부 JS 없음


def test_landing_renders_proof_when_present(built, sample_input):
    out_dir, _ = built
    html = (out_dir / "landing.html").read_text(encoding="utf-8")
    assert "지금까지의 기록" in html
    assert sample_input.proof[0][:20] in html


def test_landing_omits_proof_section_when_empty(tmp_path, sample_input):
    no_proof = sample_input.model_copy(update={"proof": []})
    result = gen.FunnelGenerator(no_proof, model="test", ask_fn=fake_ask).build()
    out_dir = gen.write_outputs(result, tmp_path)

    html = (out_dir / "landing.html").read_text(encoding="utf-8")
    assert "지금까지의 기록" not in html
    assert "<!-- 7. FAQ -->" in html  # 나머지 섹션은 그대로


def test_landing_has_refund_slot_and_ai_label(built):
    out_dir, _ = built
    html = (out_dir / "landing.html").read_text(encoding="utf-8")
    assert "환불 정책" in html
    assert "생성형 AI" in html


def test_no_ai_label_removes_footer_notice(tmp_path, sample_input):
    result = gen.FunnelGenerator(
        sample_input, model="test", ask_fn=fake_ask, ai_label=False
    ).build()
    out_dir = gen.write_outputs(result, tmp_path)

    assert "생성형 AI" not in (out_dir / "landing.html").read_text(encoding="utf-8")
    assert "생성형 AI" not in (out_dir / "emails" / "01.md").read_text(encoding="utf-8")


# --------------------------------------------------------- 이메일 프론트매터
def _parse_email(path: Path) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    assert match, f"{path.name} 에 프론트매터가 없습니다"
    return yaml.safe_load(match.group("meta")), match.group("body")


def test_emails_frontmatter_parses(built):
    out_dir, _ = built
    for path in sorted((out_dir / "emails").glob("*.md")):
        meta, body = _parse_email(path)
        assert isinstance(meta["subject"], str) and meta["subject"].strip()
        assert isinstance(meta["send_day"], int)
        assert body.strip()


def test_emails_send_days_are_fixed_sequence(built):
    out_dir, _ = built
    days = [_parse_email(p)[0]["send_day"] for p in sorted((out_dir / "emails").glob("*.md"))]
    assert days == list(gen.EMAIL_DAYS) == [0, 1, 3, 5, 7]


def test_email_bodies_are_300_to_500_chars(built):
    out_dir, _ = built
    for path in sorted((out_dir / "emails").glob("*.md")):
        _, body = _parse_email(path)
        # 말미 AI 표시 한 줄은 분량에서 뺀다
        text = body.replace("※ 이 콘텐츠는 생성형 AI의 도움을 받아 제작되었습니다.", "").strip()
        assert 300 <= len(text) <= 500, f"{path.name}: {len(text)}자"


def test_emails_carry_ai_label(built):
    out_dir, _ = built
    for path in sorted((out_dir / "emails").glob("*.md")):
        assert "생성형 AI" in path.read_text(encoding="utf-8")


def test_email_subject_with_quotes_stays_parseable(tmp_path, sample_input):
    def quoting_ask(system, user, model="test", json_mode=False, **kw):
        data = fake_ask(system, user, model, json_mode)
        if "이메일 5통" in user:
            data = json.loads(json.dumps(data))  # 원본을 건드리지 않는다
            data["emails"][0]["subject"] = '"따옴표" 가 들어간 제목'
        return data

    result = gen.FunnelGenerator(sample_input, model="test", ask_fn=quoting_ask).build()
    out_dir = gen.write_outputs(result, tmp_path)

    meta, _ = _parse_email(out_dir / "emails" / "01.md")
    assert meta["subject"] == '"따옴표" 가 들어간 제목'


# ------------------------------------------------------- 리드매그넷 / 카피
def test_lead_magnet_outline_has_7_to_10_items(built):
    out_dir, _ = built
    text = (out_dir / "lead_magnet_outline.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## \d+\. ", text, re.MULTILINE)
    assert 7 <= len(headings) <= 10


def test_copy_variants_has_10_headlines_and_5_ctas(built):
    out_dir, _ = built
    payload = json.loads((out_dir / "copy_variants.json").read_text(encoding="utf-8"))
    assert len(payload["headlines"]) == 10
    assert len(payload["ctas"]) == 5


def test_every_headline_combines_two_or_more_hooks(built):
    out_dir, _ = built
    payload = json.loads((out_dir / "copy_variants.json").read_text(encoding="utf-8"))
    for item in payload["headlines"]:
        assert len(item["hooks"]) >= 2, item


# -------------------------------------------------------- 금지 문구 0건
def _all_output_text(out_dir: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(out_dir.rglob("*"))
        if path.is_file()
    )


def test_outputs_contain_no_banned_phrases(built):
    out_dir, _ = built
    assert banned_phrases.check(_all_output_text(out_dir)) == []


def test_build_report_records_clean_result(built):
    out_dir, result = built
    report = (out_dir / "build_report.md").read_text(encoding="utf-8")
    assert "모든 섹션이 금지 문구 검사를 통과했습니다" in report
    assert result.warnings == []


def test_dirty_section_is_regenerated(tmp_path, sample_input):
    ask, state = dirty_then_clean_ask()
    result = gen.FunnelGenerator(sample_input, model="test", ask_fn=ask).build()

    headlines = result.sections["headlines"]
    assert headlines.attempts == 2, "금지 문구가 나온 섹션은 다시 만들어야 합니다"
    assert headlines.clean
    assert result.warnings == []
    assert banned_phrases.check(_all_output_text(gen.write_outputs(result, tmp_path))) == []


def test_regeneration_limit_is_reported_not_silent(tmp_path, sample_input):
    result = gen.FunnelGenerator(sample_input, model="test", ask_fn=always_dirty_ask).build()

    headlines = result.sections["headlines"]
    assert headlines.attempts == gen.MAX_REGENERATIONS + 1
    assert "무조건" in headlines.remaining_banned
    assert [s.name for s in result.warnings] == ["headlines"]

    out_dir = gen.write_outputs(result, tmp_path)
    report = (out_dir / "build_report.md").read_text(encoding="utf-8")
    assert "발행 전 사람이 고쳐야 합니다" in report


# ------------------------------------------------------------ 빌드 리포트
def test_build_report_lists_hooks_and_faq_coverage(built):
    out_dir, _ = built
    report = (out_dir / "build_report.md").read_text(encoding="utf-8")
    assert "사용된 후킹 규칙" in report
    for objection in ("price", "fit", "trust"):
        assert f"({objection}): ✓" in report


def test_build_report_records_generated_at_and_model(built):
    out_dir, result = built
    report = (out_dir / "build_report.md").read_text(encoding="utf-8")
    assert result.generated_at.strftime("%Y-%m-%d") in report
    assert "모델: test" in report


# ------------------------------------------------------------------ 문서
def test_product_readme_has_no_banned_phrases():
    readme = FUNNEL_DIR / "README.md"
    assert banned_phrases.check(readme.read_text(encoding="utf-8")) == []


def test_hooks_prompt_lists_all_eight_reasons():
    hooks = (FUNNEL_DIR / "prompts" / "hooks.md").read_text(encoding="utf-8")
    for reason in ("돈", "시간", "관계", "지위", "안전", "호기심", "비교", "손실회피"):
        assert reason in hooks
