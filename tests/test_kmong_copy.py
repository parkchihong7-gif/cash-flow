"""products/kmong-copy 테스트.

가짜 LLM(`sample_content.fake_ask`)을 주입해 실제 Claude 호출 없이
생성 → 금지 문구·크몽 정책 검사 → 산출물 5종 쓰기 전 과정을 검증한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from kmong_copy.generator import BASE_DIR, KmongGenerator
from kmong_copy.policy import check_contact_lure
from kmong_copy.sample_content import fake_ask
from kmong_copy.schema import (
    FAQ_COUNT, HEADLINE_LIMIT, NO_PROOF_TEXT, PACKAGE_DESC_LIMIT,
    PACKAGE_TITLE_LIMIT, PACKAGE_TIERS, PROCESS_STEPS, SCRIPT_COUNT,
    ServiceInput, TAG_COUNT, TITLE_COUNT, TITLE_LIMIT, load_input, truncate,
)
from kmong_copy.writers import KMONG_FIELDS, write_outputs
from shared import banned_phrases

KMONG_DIR = Path(BASE_DIR)
EXAMPLE_YAML = KMONG_DIR / "service_input.yaml"


# ------------------------------------------------------------------ 픽스처
def _input(**overrides) -> ServiceInput:
    payload = {
        "service_name": "테스트 서비스",
        "category": "디자인 > 로고",
        "what_you_deliver": ["산출물 하나", "산출물 둘"],
        "who_for": "테스트 대상",
        "differentiators": ["차별점 1", "차별점 2", "차별점 3"],
        "turnaround_days": 5,
        "price_basic": 90000,
        "price_standard": 150000,
        "price_premium": 250000,
        "proof": [],
        "faq_seed": [],
    }
    payload.update(overrides)
    return ServiceInput(**payload)


@pytest.fixture
def result():
    return KmongGenerator(_input(), model="test", ask_fn=fake_ask).build()


@pytest.fixture
def built(tmp_path, result):
    out_dir, passed = write_outputs(result, tmp_path)
    return {"dir": out_dir, "passed": passed, "result": result}


def _read(built, name: str) -> str:
    return (built["dir"] / name).read_text(encoding="utf-8")


def _json(built, name: str) -> dict:
    return json.loads(_read(built, name))


# --------------------------------------------------------------- 입력 검증
def test_example_yaml_loads():
    data = load_input(EXAMPLE_YAML)
    assert len(data.differentiators) == 3
    assert data.proof == [], "예시는 실적 없이 시작하도록 비워둔다"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"differentiators": ["하나", "둘"]}, "차별점 3개 아님"),
        ({"differentiators": ["하나", "둘", "셋", "넷"]}, "차별점 4개"),
        ({"what_you_deliver": ["하나"]}, "산출물 2개 미만"),
        ({"turnaround_days": 0}, "작업일 0"),
        ({"turnaround_days": 100}, "작업일 과다"),
        ({"price_basic": 0}, "가격 0"),
        ({"service_name": "   "}, "빈 서비스명"),
        ({"proof": ["자료", ""]}, "빈 항목"),
    ],
)
def test_invalid_input_rejected(overrides, reason):
    with pytest.raises(ValidationError):
        _input(**overrides)


@pytest.mark.parametrize(
    "prices",
    [
        {"price_basic": 200000, "price_standard": 150000, "price_premium": 250000},
        {"price_basic": 90000, "price_standard": 150000, "price_premium": 100000},
        {"price_basic": 100000, "price_standard": 100000, "price_premium": 200000},
    ],
)
def test_prices_must_increase(prices):
    with pytest.raises(ValidationError, match="BASIC < STANDARD < PREMIUM"):
        _input(**prices)


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        _input(할인율=10)


def test_truncate_respects_limit():
    assert truncate("가" * 50, 25) == "가" * 25
    assert truncate("짧음", 25) == "짧음"


# ----------------------------------------------- 크몽 정책 검사 (핵심)
@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("문의는 010-1234-5678 로 주세요", "전화번호"),
        ("연락처 02-123-4567 입니다", "일반 전화번호"),
        ("메일 주소는 hello@example.com 입니다", "이메일 주소"),
        ("카톡 아이디로 문의 주세요", "카카오톡 유도"),
        ("오픈채팅방에서 상담합니다", "카카오톡 유도"),
        ("텔레그램으로 연락 주세요", "다른 메신저 유도"),
        ("인스타 DM 주시면 답변드립니다", "SNS 계정 유도"),
        ("직거래하시면 더 저렴합니다", "직거래 유도"),
        ("수수료 아끼고 진행하실 수 있습니다", "플랫폼 이탈 유도"),
        ("포트폴리오는 https://myblog.com 에", "외부 링크"),
    ],
)
def test_contact_lure_is_detected(text, label):
    findings = check_contact_lure(text)
    assert label in [f.label for f in findings], f"{text} 에서 {label} 을 못 잡았습니다"


@pytest.mark.parametrize(
    "text",
    [
        "크몽 메시지로 문의 주시면 24시간 안에 답변드립니다",
        "작업 상담은 크몽 메시지에서 진행합니다",
        "포트폴리오는 https://www.kmong.com/gig/123 에 있습니다",
        "영업일 기준 3일 안에 드립니다",
        "",
    ],
)
def test_clean_text_passes_policy(text):
    assert check_contact_lure(text) == []


def test_contact_finding_shows_context():
    findings = check_contact_lure("앞쪽 문장입니다 010-1234-5678 뒤쪽 문장입니다")
    assert findings[0].matched == "010-1234-5678"
    assert "앞쪽" in findings[0].context and "뒤쪽" in findings[0].context


def test_same_match_is_not_reported_twice():
    findings = check_contact_lure("010-1234-5678 그리고 또 010-1234-5678")
    assert len([f for f in findings if f.label == "전화번호"]) == 1


# ------------------------------------------------------- 생성 + 재작성
def test_sections_are_clean(result):
    for section in result.sections.values():
        assert section.clean, f"{section.name}: {section.banned} {section.contact}"
    assert result.warnings == []


def test_banned_phrase_triggers_rewrite():
    state = {"calls": 0}

    def dirty_first(system, user, model="test", json_mode=False, **kw):
        state["calls"] += 1
        payload = fake_ask(system, user, model, json_mode)
        if "크몽 상세페이지 본문을" in user and state["calls"] == 1:
            payload["headline"] = "무조건 되는 로고"
        return payload

    result = KmongGenerator(_input(), model="test", ask_fn=dirty_first).build()
    assert result.sections["detail"].attempts == 2
    assert result.sections["detail"].clean


def test_contact_lure_triggers_rewrite():
    """크몽 정책 위반은 금지 문구와 똑같이 재작성 대상이다."""
    # scripts 는 세 번째 호출이라 전체 호출 수가 아니라 이 섹션의 첫 시도를 센다
    state = {"script_calls": 0}

    def leaky_first(system, user, model="test", json_mode=False, **kw):
        payload = fake_ask(system, user, model, json_mode)
        if "문의 응답 템플릿" in user:
            state["script_calls"] += 1
            if state["script_calls"] == 1:
                payload["scripts"][0]["body"] = "급하시면 010-1234-5678 로 연락 주세요"
        return payload

    result = KmongGenerator(_input(), model="test", ask_fn=leaky_first).build()
    assert result.sections["scripts"].attempts == 2
    assert result.sections["scripts"].clean


def test_persistent_violation_is_reported(tmp_path):
    def always_leaky(system, user, model="test", json_mode=False, **kw):
        payload = fake_ask(system, user, model, json_mode)
        if "문의 응답 템플릿" in user:
            payload["scripts"][0]["body"] = "카톡으로 문의 주세요"
        return payload

    result = KmongGenerator(_input(), model="test", ask_fn=always_leaky).build()
    assert result.sections["scripts"].contact
    assert [s.name for s in result.warnings] == ["scripts"]

    out_dir, passed = write_outputs(result, tmp_path)
    assert not passed
    report = (out_dir / "compliance_report.md").read_text(encoding="utf-8")
    assert "반드시 지우세요" in report


def test_over_long_headline_is_truncated():
    def long_headline(system, user, model="test", json_mode=False, **kw):
        payload = fake_ask(system, user, model, json_mode)
        if "크몽 상세페이지 본문을" in user:
            payload["headline"] = "가" * 80
        return payload

    result = KmongGenerator(_input(), model="test", ask_fn=long_headline).build()
    assert len(result.detail["headline"]) <= HEADLINE_LIMIT


def test_over_long_titles_are_truncated():
    def long_titles(system, user, model="test", json_mode=False, **kw):
        payload = fake_ask(system, user, model, json_mode)
        if "패키지 3단과 제목" in user:
            payload["titles"][0]["text"] = "가" * 60
            payload["packages"][0]["title"] = "나" * 40
            payload["packages"][0]["description"] = "다" * 300
        return payload

    result = KmongGenerator(_input(), model="test", ask_fn=long_titles).build()
    packages = result.packages
    assert len(packages["titles"][0]["text"]) <= TITLE_LIMIT
    assert len(packages["packages"][0]["title"]) <= PACKAGE_TITLE_LIMIT
    assert len(packages["packages"][0]["description"]) <= PACKAGE_DESC_LIMIT


# ------------------------------------------------------------ 산출물 5종
def test_all_five_outputs_created(built):
    for name in ("detail_page.md", "packages.json", "title_variants.json",
                 "inquiry_scripts.md", "compliance_report.md"):
        assert (built["dir"] / name).is_file(), name


def test_detail_page_has_every_section_in_order(built):
    text = _read(built, "detail_page.md")
    sections = [
        "## 이런 분께 추천합니다",
        "## 제공 내용",
        "## 작업 프로세스",
        "## 이 서비스의 차별점",
        "## 포트폴리오",
        "## 자주 묻는 질문",
        "## 작업 전 준비해 주실 것",
        "## 수정·환불 정책",
        "## AI 활용 고지",
    ]
    positions = [text.index(section) for section in sections]
    assert positions == sorted(positions), "섹션 순서가 어긋났습니다"


def test_detail_page_headline_within_limit(built):
    assert len(built["result"].detail["headline"]) <= HEADLINE_LIMIT


def test_detail_page_has_five_process_steps(built):
    assert len(built["result"].detail["process"]) == PROCESS_STEPS


def test_detail_page_has_seven_faqs(built):
    assert len(built["result"].detail["faq"]) == FAQ_COUNT


def test_detail_page_states_who_it_is_not_for(built):
    text = _read(built, "detail_page.md")
    assert "맞지 않습니다" in text


def test_detail_page_without_proof_says_preparing(built):
    """규칙: 성과 수치는 proof 에 있는 것만. 없으면 '사례 준비 중'."""
    text = _read(built, "detail_page.md")
    assert NO_PROOF_TEXT in text
    assert "판매자가 채울 곳" in text


def test_detail_page_with_proof_renders_it(tmp_path):
    data = _input(proof=["2026년 상반기 42건 작업 (크몽 거래 내역)"])
    result = KmongGenerator(data, model="test", ask_fn=fake_ask).build()
    out_dir, _ = write_outputs(result, tmp_path)
    text = (out_dir / "detail_page.md").read_text(encoding="utf-8")
    assert "42건" in text
    assert NO_PROOF_TEXT not in text
    assert "보장하지 않으며" in text


# ------------------------------------------------------------ packages.json
def test_packages_use_kmong_form_field_names(built):
    payload = _json(built, "packages.json")
    rows = payload["패키지"]
    assert [row[KMONG_FIELDS["tier"]] for row in rows] == list(PACKAGE_TIERS)
    for row in rows:
        for field in KMONG_FIELDS.values():
            assert field in row, f"{field} 칸이 없습니다"


def test_packages_prices_come_from_input(built):
    rows = _json(built, "packages.json")["패키지"]
    data = built["result"].data
    assert [row[KMONG_FIELDS["price"]] for row in rows] == [
        data.price_basic, data.price_standard, data.price_premium
    ]


def test_package_titles_and_descriptions_within_limits(built):
    for row in _json(built, "packages.json")["패키지"]:
        assert len(row[KMONG_FIELDS["title"]]) <= PACKAGE_TITLE_LIMIT
        assert len(row[KMONG_FIELDS["description"]]) <= PACKAGE_DESC_LIMIT


def test_package_days_do_not_increase(built):
    days = [row[KMONG_FIELDS["days"]] for row in _json(built, "packages.json")["패키지"]]
    assert days == sorted(days, reverse=True) or len(set(days)) == 1


def test_package_revisions_do_not_decrease(built):
    revisions = [
        row[KMONG_FIELDS["revisions"]] for row in _json(built, "packages.json")["패키지"]
    ]
    assert revisions == sorted(revisions)


# --------------------------------------------- title_variants.json (핵심)
def test_ten_titles_all_within_25_chars(built):
    """완료 기준: 제목 10안 모두 25자 이내."""
    titles = _json(built, "title_variants.json")["제목_후보"]
    assert len(titles) == TITLE_COUNT
    too_long = [
        f"{t['번호']}안 {t['글자수']}자: {t['제목']}"
        for t in titles if len(t["제목"]) > TITLE_LIMIT
    ]
    assert too_long == [], f"25자 초과 제목: {too_long}"


def test_title_char_count_field_is_accurate(built):
    for title in _json(built, "title_variants.json")["제목_후보"]:
        assert title["글자수"] == len(title["제목"])


def test_titles_are_distinct(built):
    titles = [t["제목"] for t in _json(built, "title_variants.json")["제목_후보"]]
    assert len(set(titles)) == len(titles), "같은 제목이 섞여 있습니다"


def test_twenty_search_tags(built):
    tags = _json(built, "title_variants.json")["검색_태그"]
    assert len(tags) == TAG_COUNT
    assert len(set(tags)) == TAG_COUNT


# --------------------------------------------------------- inquiry_scripts
def test_eight_inquiry_scripts(built):
    text = _read(built, "inquiry_scripts.md")
    assert len(built["result"].scripts["scripts"]) == SCRIPT_COUNT
    for number in range(1, SCRIPT_COUNT + 1):
        assert f"## {number}. " in text


def test_inquiry_scripts_cover_required_situations(built):
    situations = " ".join(
        s["situation"] for s in built["result"].scripts["scripts"]
    )
    for required in ("견적", "기간", "범위", "환불", "리뷰"):
        assert required in situations, f"'{required}' 상황 템플릿이 없습니다"


def test_inquiry_scripts_have_no_contact_lure(built):
    """생성된 스크립트 본문에 외부 연락처가 없어야 한다."""
    bodies = "\n".join(s["body"] for s in built["result"].scripts["scripts"])
    assert check_contact_lure(bodies) == []


def test_inquiry_scripts_warn_about_kmong_policy(built):
    assert "크몽 정책" in _read(built, "inquiry_scripts.md")


# ------------------------------------------------------ compliance_report
def test_compliance_report_passes_for_clean_input(built):
    assert built["passed"]
    report = _read(built, "compliance_report.md")
    assert "✅ 통과" in report


def test_compliance_report_checks_ecommerce_law(built):
    report = _read(built, "compliance_report.md")
    for label in ("수정 가능 횟수와 범위", "추가 수정 시 비용", "환불 가능한 경우",
                  "환불이 어려운 경우", "작업 시작 후 취소 시 처리"):
        assert label in report, label
    assert "통신판매업 신고번호" in report


def test_compliance_report_flags_missing_policy(tmp_path):
    def no_policy(system, user, model="test", json_mode=False, **kw):
        payload = fake_ask(system, user, model, json_mode)
        if "크몽 상세페이지 본문을" in user:
            payload["policy"]["refund_no"] = ""
        return payload

    result = KmongGenerator(_input(), model="test", ask_fn=no_policy).build()
    out_dir, passed = write_outputs(result, tmp_path)
    assert not passed
    report = (out_dir / "compliance_report.md").read_text(encoding="utf-8")
    assert "⚠️ 비어 있음" in report


def test_compliance_report_catches_contact_in_user_input(tmp_path):
    """판매자가 차별점 칸에 전화번호를 적는 일이 실제로 있다."""
    data = _input(differentiators=["급하면 010-1234-5678 로 연락", "차별점 2", "차별점 3"])
    result = KmongGenerator(data, model="test", ask_fn=fake_ask).build()
    out_dir, passed = write_outputs(result, tmp_path)

    assert not passed
    report = (out_dir / "compliance_report.md").read_text(encoding="utf-8")
    assert "010-1234-5678" in report


def test_compliance_report_does_not_flag_its_own_guidance(built):
    """프로그램이 넣는 '전화번호를 쓰지 마세요' 안내가 스스로 걸리면 안 된다."""
    report = _read(built, "compliance_report.md")
    assert "⚠️ **1건 발견" not in report
    assert "고정 안내문은 제외" in report


def test_compliance_report_lists_section_history(built):
    report = _read(built, "compliance_report.md")
    for name in ("detail", "packages", "scripts"):
        assert f"| {name} |" in report


# ------------------------------------------------ 완료 기준: 금지 문구 0건
def _all_output_text(out_dir: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(out_dir.rglob("*")) if path.is_file()
    )


def test_outputs_contain_no_banned_phrases(built):
    """완료 기준: 예시 입력으로 5종 산출물 생성, 금지 문구 0건."""
    assert banned_phrases.check(_all_output_text(built["dir"])) == []


def test_outputs_carry_ai_label(built):
    assert "생성형 AI" in _read(built, "detail_page.md")
    assert "생성형 AI" in _read(built, "inquiry_scripts.md")


def test_ai_label_can_be_disabled(tmp_path, result):
    out_dir, _ = write_outputs(result, tmp_path, ai_label=False)
    text = (out_dir / "detail_page.md").read_text(encoding="utf-8")
    assert "생성형 AI" in text, "AI 활용 고지 섹션은 항상 들어간다"
    assert not text.rstrip().endswith("제작되었습니다.")


# ------------------------------------------------------------------ 문서
def test_readme_has_kmong_registration_mapping():
    """완료 기준: README 에 크몽 등록 순서 매핑표."""
    text = (KMONG_DIR / "README.md").read_text(encoding="utf-8")
    assert "크몽 등록 순서" in text
    for name in ("detail_page.md", "packages.json", "title_variants.json",
                 "inquiry_scripts.md", "compliance_report.md"):
        assert name in text, name
    assert banned_phrases.check(text) == []


def test_product_manuals_are_detailed_and_clean():
    for name in ("admin.md", "client.md"):
        path = KMONG_DIR / "docs" / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert len(text) > 4000, f"{name} 이 너무 짧습니다"
        assert banned_phrases.check(text) == []


def test_prompts_state_the_policy_rules():
    common = (KMONG_DIR / "prompts" / "common.md").read_text(encoding="utf-8")
    assert "외부 연락처" in common
    assert "크몽 메시지" in common
    assert NO_PROOF_TEXT in common
