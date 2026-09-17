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

from funnel_builder import generator as gen
from funnel_builder.sample_content import always_dirty_ask, dirty_then_clean_ask, fake_ask
from funnel_builder.schema import FunnelInput, load_input
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


# ------------------------------------------------------------ 플랫폼별 산출물
# 같은 퍼널이라도 어디에 올리느냐에 따라 첫 화면이 다르다.
#   own        landing.html      내 도메인
#   kmong      detail_page.md    크몽은 HTML 을 못 올린다
#   instagram  reels_captions.md + dm_flow.yaml
from funnel_builder import platforms                                # noqa: E402

COMMON_FILES = ("emails", "lead_magnet_outline.md", "copy_variants.json",
                "build_report.md")


def _build(tmp_path, sample_input, platform: str):
    result = gen.FunnelGenerator(sample_input, model="test", ask_fn=fake_ask,
                                 platform=platform).build()
    return gen.write_outputs(result, tmp_path), result


@pytest.mark.parametrize("platform", platforms.PLATFORMS)
def test_each_platform_writes_its_own_files(tmp_path, sample_input, platform):
    out_dir, _ = _build(tmp_path, sample_input, platform)
    for name in platforms.platform_files[platform]:
        assert (out_dir / name).is_file(), f"{platform}: {name} 이 없습니다"
    for name in COMMON_FILES:
        assert (out_dir / name).exists(), f"{platform}: 공통 산출물 {name} 이 없습니다"


@pytest.mark.parametrize("platform", platforms.PLATFORMS)
def test_each_platform_leaves_out_the_others(tmp_path, sample_input, platform):
    """크몽 폴더에 landing.html 이 섞여 들어가면 무엇을 올릴지 헷갈린다."""
    out_dir, _ = _build(tmp_path, sample_input, platform)
    others = {name for key, names in platforms.platform_files.items()
              if key != platform for name in names}
    for name in others - set(platforms.platform_files[platform]):
        assert not (out_dir / name).exists(), f"{platform} 인데 {name} 이 있습니다"


def test_kmong_detail_follows_the_listing_shape(tmp_path, sample_input):
    out_dir, _ = _build(tmp_path, sample_input, "kmong")
    text = (out_dir / "detail_page.md").read_text(encoding="utf-8")
    for heading in ("## 이런 분께 추천합니다", "## 제공 내용", "## 진행 순서",
                    "## 포트폴리오", "## 가격", "## 자주 묻는 질문"):
        assert heading in text, heading
    assert "HTML 을 못 올립니다" in text, "크몽의 제약을 알려 줘야 합니다"
    assert banned_phrases.check(text) == []


def test_kmong_detail_does_not_invent_proof(tmp_path, sample_input):
    """실적이 없으면 비워 두고 판매자가 채우게 한다."""
    sample_input.proof = []
    out_dir, _ = _build(tmp_path, sample_input, "kmong")
    text = (out_dir / "detail_page.md").read_text(encoding="utf-8")
    assert "사례 준비 중" in text
    assert "없는 실적을 지어내면" in text


def test_instagram_pack_has_five_captions(tmp_path, sample_input):
    out_dir, _ = _build(tmp_path, sample_input, "instagram")
    text = (out_dir / "reels_captions.md").read_text(encoding="utf-8")
    assert text.count("**첫 줄 (더 보기 앞에서 끝나는 자리)**") == 5
    assert "프로필 링크 문구" in text
    assert sample_input.cta_url in text


def test_instagram_pack_carries_the_comment_keyword(tmp_path, sample_input):
    out_dir, _ = _build(tmp_path, sample_input, "instagram")
    text = (out_dir / "reels_captions.md").read_text(encoding="utf-8")
    assert "'가이드' 댓글 남기" in text or "'가이드' 댓글 남겨" in text
    assert "DM으로 보내드려요" in text


def test_instagram_pack_forbids_cold_dm_and_auto_follow(tmp_path, sample_input):
    out_dir, _ = _build(tmp_path, sample_input, "instagram")
    text = (out_dir / "reels_captions.md").read_text(encoding="utf-8")
    assert "콜드 DM" in text and "계정 정지" in text
    assert "자동 팔로우" in text


# ------------------------------------------------------------------ DM 흐름
@pytest.fixture
def dm_flow(tmp_path, sample_input):
    out_dir, _ = _build(tmp_path, sample_input, "instagram")
    path = out_dir / "dm_flow.yaml"
    return path, yaml.safe_load(path.read_text(encoding="utf-8"))


def test_dm_flow_starts_only_from_a_comment(dm_flow):
    """시작점이 댓글 하나뿐이어야 콜드 DM 이 될 수 없다."""
    _, flow = dm_flow
    assert flow["trigger"]["type"] == "instagram_comment"
    assert flow["trigger"]["keyword"]
    assert "먼저 보내지 않습니다" in flow["trigger"]["note"]


def test_dm_flow_states_the_24_hour_rule(dm_flow):
    path, flow = dm_flow
    assert "24시간" in flow["정책"]["24시간_규칙"]
    assert "24시간" in path.read_text(encoding="utf-8").splitlines()[2]


def test_dm_flow_refuses_cold_dm_in_writing(dm_flow):
    _, flow = dm_flow
    assert "만들지 마세요" in flow["정책"]["콜드_DM"]
    assert "위반" in flow["정책"]["자동_팔로우_좋아요"]


def test_dm_flow_tells_the_person_it_is_automated(dm_flow):
    """인공지능기본법 제31조. 첫 메시지에서 밝힌다."""
    _, flow = dm_flow
    first = flow["steps"][0]
    assert "자동 응답" in first["text"]


def test_dm_flow_hands_over_to_a_human(dm_flow):
    _, flow = dm_flow
    assert flow["handoff"]["when"], "사람에게 넘기는 조건이 있어야 합니다"
    assert any("가격" in item or "환불" in item for item in flow["handoff"]["when"])


def test_dm_flow_has_an_opt_out(dm_flow):
    """그만 받겠다는 사람에게 계속 보내면 신고된다."""
    _, flow = dm_flow
    assert flow["opt_out"]["keyword"] == "그만"
    assert flow["opt_out"]["message"]


def test_dm_flow_names_only_official_tools(dm_flow):
    _, flow = dm_flow
    assert "ManyChat" in flow["메타"]["넣을_도구"]
    text = json.dumps(flow, ensure_ascii=False)
    for macro in ("selenium", "매크로", "비밀번호"):
        assert macro not in text, f"비공식 자동화가 들어갔습니다: {macro}"


def test_dm_flow_is_loadable_yaml(dm_flow):
    """도구에 그대로 넣으려면 기계가 읽을 수 있어야 한다."""
    path, flow = dm_flow
    assert isinstance(flow, dict)
    assert set(flow) >= {"trigger", "steps", "handoff", "opt_out", "정책"}


# -------------------------------------------------------------------- serve
def test_serve_folder_only_exposes_that_folder(tmp_path, sample_input):
    """산출물에는 고객 이름이 들어갈 수 있다. 상위 폴더가 새면 안 된다."""
    import http.client
    import threading
    import urllib.request

    from conftest import load_product_cli

    cli = load_product_cli("funnel-builder")
    out_dir, _ = _build(tmp_path, sample_input, "own")
    (tmp_path / "비밀.txt").write_text("보이면 안 됩니다", encoding="utf-8")

    httpd, url, first = cli.make_server(out_dir, port=8231)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        assert first == "landing.html"
        body = urllib.request.urlopen(url, timeout=3).read().decode("utf-8")
        assert "<h1" in body

        # urllib 은 '..' 을 보내기 전에 스스로 정리해 버린다. 실제 공격은 그러지
        # 않으므로 경로를 손으로 적어 그대로 보낸다.
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", "/../%EB%B9%84%EB%B0%80.txt")
        response = conn.getresponse()
        response.read()
        conn.close()
        assert response.status == 404, "상위 폴더가 열렸습니다"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_serve_picks_the_right_first_file(tmp_path, sample_input, capsys):
    """플랫폼마다 첫 화면이 다르다. 없는 파일을 열려고 하면 안 된다."""
    from conftest import load_product_cli

    cli = load_product_cli("funnel-builder")
    out_dir, _ = _build(tmp_path, sample_input, "kmong")
    url = cli.serve_folder(out_dir, port=8232, open_browser=False, forever=False)
    assert url.endswith("detail_page.md")
    assert "landing.html 이 없어" in capsys.readouterr().out


def test_latest_output_finds_the_newest(tmp_path):
    from conftest import load_product_cli

    cli = load_product_cli("funnel-builder")
    assert cli.latest_output(tmp_path / "없음") is None

    first = tmp_path / "하나"
    first.mkdir()
    second = tmp_path / "둘"
    second.mkdir()
    import os
    import time

    os.utime(second, (time.time() + 10, time.time() + 10))
    assert cli.latest_output(tmp_path) == second


def test_build_report_records_the_platform(tmp_path, sample_input):
    out_dir, _ = _build(tmp_path, sample_input, "instagram")
    text = (out_dir / "build_report.md").read_text(encoding="utf-8")
    assert "플랫폼: instagram" in text
