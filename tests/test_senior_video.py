"""14번 시니어 영상 비용 견적·절감기 테스트.

핵심 검사 셋:
1. **승인 없이 올라가는 길이 없는가** (유튜브 양산형 콘텐츠 정책)
2. **절감안이 대가를 같이 말하는가** ("품질 그대로 절반" 은 거짓말이다)
3. **단가에 출처가 붙어 있는가** (근거 없는 견적은 분쟁이 된다)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import load_product_cli
from core.registry import Registry
from senior_video.estimate import VideoPlan, estimate
from senior_video.rates import MIN_SOURCE_LEN, RateError, load_rates
from senior_video.report import write_report
from senior_video.savings import INTRO_OUTRO_CHARS, apply_cache, suggest
from senior_video.senior import RULES, check_plan, grade
from senior_video.upload import (
    MAX_UPLOADS_PER_DAY, Queue, QueueError, UPLOAD_UNITS, uploads_possible,
)

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "senior-video"
RATES_PATH = PRODUCT / "data" / "unit_costs.yaml"


@pytest.fixture
def rates():
    return load_rates(RATES_PATH)


@pytest.fixture
def est(rates):
    return estimate(VideoPlan(tts="elevenlabs", image_source="ai-image",
                              script_source="claude-opus"), rates)


# ------------------------------------------- 승인 없이 올라가는 길이 없다
def test_new_items_always_start_as_draft(tmp_path):
    """상태를 직접 지정하는 방법이 없다. 늘 초안으로 들어간다."""
    queue = Queue(tmp_path / "q.db")
    item_id = queue.add_draft("어르신 스마트폰 3편", 1500)
    assert queue.get(item_id).status == "draft"


def test_approval_without_a_name_is_refused(tmp_path):
    """이름 없는 승인은 자동 승인과 다르지 않다."""
    queue = Queue(tmp_path / "q.db")
    item_id = queue.add_draft("제목", 1500)
    with pytest.raises(QueueError, match="승인한 사람 이름"):
        queue.approve(item_id, "")
    with pytest.raises(QueueError, match="승인한 사람 이름"):
        queue.approve(item_id, "   ")


def test_unapproved_item_cannot_be_uploaded(tmp_path):
    queue = Queue(tmp_path / "q.db")
    item_id = queue.add_draft("제목", 1500)
    with pytest.raises(QueueError, match="승인되지 않은"):
        queue.mark_uploaded(item_id)


def test_approved_item_records_who_and_when(tmp_path):
    queue = Queue(tmp_path / "q.db")
    item_id = queue.add_draft("제목", 1500)
    item = queue.approve(item_id, "박치홍", "자막 크기 확인함")
    assert item.approved_by == "박치홍"
    assert item.approved_at
    assert item.ready
    assert queue.mark_uploaded(item_id).status == "uploaded"


def test_uploaded_item_cannot_be_re_approved(tmp_path):
    queue = Queue(tmp_path / "q.db")
    item_id = queue.add_draft("제목")
    queue.approve(item_id, "박치홍")
    queue.mark_uploaded(item_id)
    with pytest.raises(QueueError, match="이미 올린"):
        queue.approve(item_id, "박치홍")


def test_rejected_item_is_not_ready(tmp_path):
    queue = Queue(tmp_path / "q.db")
    item_id = queue.add_draft("제목")
    assert not queue.reject(item_id, "말이 너무 빠름").ready


# ------------------------------------------------------------ 업로드 쿼터
def test_six_uploads_a_day_is_the_ceiling():
    """하루 10,000 유닛 ÷ 업로드 1,600 유닛 = 6편."""
    assert UPLOAD_UNITS == 1600
    assert MAX_UPLOADS_PER_DAY == 6


def test_quota_flags_a_plan_that_does_not_fit():
    assert uploads_possible(60)["fits"] is True
    heavy = uploads_possible(300)
    assert heavy["fits"] is False
    assert heavy["max_monthly"] == 180


# ---------------------------------------------------- 단가에 출처가 붙는다
def test_every_rate_carries_a_source(rates):
    for group in (rates.tts, rates.image, rates.script):
        for row in group:
            assert len(row.source) >= MIN_SOURCE_LEN, f"{row.key} 에 출처가 없습니다"


def test_rate_without_a_source_is_refused(tmp_path):
    """고칠 때 근거도 같이 고치게 만드는 장치다."""
    path = tmp_path / "rates.yaml"
    path.write_text(yaml.safe_dump({
        "meta": {"기준일": "2026-01-01"},
        "tts": [{"key": "x", "name": "X", "won_per_1k_chars": 10, "source": "몰라"}],
        "image": [], "script": [],
    }, allow_unicode=True), encoding="utf-8")
    with pytest.raises(RateError, match="출처가 없습니다"):
        load_rates(path)


def test_rate_table_needs_an_asof_date(tmp_path):
    path = tmp_path / "rates.yaml"
    path.write_text(yaml.safe_dump({"meta": {}, "tts": [], "image": [], "script": []},
                                   allow_unicode=True), encoding="utf-8")
    with pytest.raises(RateError, match="기준일"):
        load_rates(path)


def test_clova_is_the_best_fit_for_korean_seniors(rates):
    """한국어 중저음 화자가 있어 시니어 대상에 유리하다."""
    assert rates.best_for_senior().key == "clova"


# ---------------------------------------------------------------- 견적
def test_estimate_splits_the_cost_and_names_the_biggest(est):
    keys = [line.key for line in est.lines]
    assert keys == ["tts", "image", "script", "render"]
    assert est.per_video > 0
    assert est.per_month == pytest.approx(est.per_video * 20)
    assert est.biggest is not None
    assert est.share(est.biggest) > 0


def test_free_combination_costs_nothing(rates):
    plan = VideoPlan(tts="local-piper", image_source="stock-free",
                     script_source="직접작성")
    result = estimate(plan, rates)
    assert result.free, "청구서가 날아오는 줄이 하나도 없어야 한다"
    assert result.billed == 0
    assert result.per_video == pytest.approx(rates.render_won), "전기값만 남는다"


def test_unknown_engine_lists_the_valid_ones(rates):
    with pytest.raises(RateError, match="쓸 수 있는 것"):
        estimate(VideoPlan(tts="없는엔진"), rates)


# ---------------------------------------------------------------- 절감
def test_every_saving_states_what_it_costs_you(est, rates):
    """'품질 그대로 절반' 은 거짓말이다. 대가를 비워 두면 안 된다."""
    for item in suggest(est, rates):
        assert item.cost.strip(), f"{item.title} 에 대가가 안 적혀 있습니다"


def test_cache_is_the_only_free_saving(est, rates):
    cache = next(item for item in suggest(est, rates) if item.key == "cache")
    assert "없습니다" in cache.cost
    assert cache.senior_safe


def test_cheaper_voice_is_marked_unsafe_for_seniors(est, rates):
    """싼 음성으로 바꾸는 것은 이 채널이 노리는 시청자를 잃는 선택이다."""
    unsafe = [item for item in suggest(est, rates) if not item.senior_safe]
    assert unsafe, "시니어 적합도가 떨어지는 절감안은 표시되어야 한다"
    assert all(item.key.startswith("tts:") for item in unsafe)


def test_savings_are_sorted_biggest_first(est, rates):
    amounts = [item.monthly_won for item in suggest(est, rates)]
    assert amounts == sorted(amounts, reverse=True)


def test_cache_shortens_the_chargeable_script():
    plan = VideoPlan(script_chars=1500)
    assert apply_cache(plan) == 1500 - INTRO_OUTRO_CHARS


def test_free_plan_has_nothing_left_to_cut(rates):
    plan = VideoPlan(tts="local-piper", image_source="stock-free",
                     script_source="직접작성", monthly_videos=4)
    assert suggest(estimate(plan, rates), rates) == []


# ------------------------------------------------------------ 시니어 규격
def test_every_rule_explains_why():
    """"자막을 크게" 는 누구나 한다. 왜인지까지 말해야 돈을 받는다."""
    for rule in RULES:
        assert len(rule.why) > 30, f"{rule.key} 의 설명이 부실합니다"
        assert rule.recommended.strip()


def test_small_subtitles_and_fast_speech_are_flagged():
    findings = {item.rule.key: item for item in check_plan(
        {"subtitle_px": 40, "speech_rate": 400, "bgm_db": -6, "scene_seconds": 1.5})}
    assert findings["subtitle_px"].warn
    assert findings["speech_rate"].warn
    assert findings["bgm_db"].warn
    assert findings["scene_seconds"].warn


def test_a_compliant_plan_passes():
    findings = check_plan({
        "subtitle_px": 72, "subtitle_chars": 14, "speech_rate": 280,
        "bgm_db": -20, "scene_seconds": 5, "contrast": 7.0, "length_minutes": 12})
    assert all(item.ok for item in findings if item.status not in ("na", "advice"))
    assert "모두 맞췄습니다" in grade(findings)


def test_qualitative_rules_are_advice_not_a_failure():
    """목소리 높낮이는 숫자로 못 잰다. 그걸 '안 적었다' 고 하면 잔소리가 된다."""
    findings = {item.rule.key: item for item in check_plan({})}
    assert findings["voice_pitch"].status == "advice"
    assert findings["subtitle_px"].status == "na"


def test_unset_values_are_not_treated_as_failures():
    findings = check_plan({})
    assert all(item.status in ("na", "advice") for item in findings)
    assert not any(item.warn for item in findings), "안 적은 것을 어겼다고 하면 안 된다"
    assert "확인하지 못했습니다" in grade(findings)


# ---------------------------------------------------------------- 보고서
def test_report_warns_about_uploads_and_approval(tmp_path, est, rates):
    findings = check_plan(est.plan.as_check())
    path = write_report(est, suggest(est, rates), findings, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "사람이 승인한 것만 올라갑니다" in text
    assert "1,600" in text and "6편" in text
    assert "비공개(private)로 잠깁니다" in text
    assert "추정한 값" in text


def test_report_marks_senior_unsafe_savings(tmp_path, est, rates):
    findings = check_plan(est.plan.as_check())
    text = write_report(est, suggest(est, rates), findings, tmp_path).read_text(encoding="utf-8")
    assert "⚠ 표시는" in text
    assert "시니어 시청자에게 불리해지는" in text


# ------------------------------------------------------------------ CLI
def test_cli_demo_estimate_warns_about_the_spec(tmp_path, capsys):
    cli = load_product_cli("senior-video")
    code = cli.main(["estimate", "--demo", "--out", str(tmp_path)])
    assert code == 2, "샘플 기획은 일부러 규격을 어겨 두었다"
    out = capsys.readouterr().out
    assert "권장값을 벗어난" in out
    assert len(list(tmp_path.glob("estimate_*.md"))) == 1


def test_cli_rates_shows_the_sources(capsys):
    cli = load_product_cli("senior-video")
    assert cli.main(["rates"]) == 0
    out = capsys.readouterr().out
    assert "출처:" in out
    assert "기준일" in out


def test_cli_quota_refuses_an_impossible_plan(capsys):
    cli = load_product_cli("senior-video")
    assert cli.main(["quota", "--monthly", "300"]) == 2
    assert "쿼터를 넘습니다" in capsys.readouterr().out


def test_cli_approve_requires_a_name(tmp_path, capsys):
    cli = load_product_cli("senior-video")
    db = str(tmp_path / "q.db")
    cli.main(["queue", "add", "제목", "--db", db])
    assert cli.main(["approve", "1", "--by", "박치홍", "--db", db]) == 0
    assert "승인했습니다" in capsys.readouterr().out


def test_cli_spec_prints_the_reasons(capsys):
    cli = load_product_cli("senior-video")
    assert cli.main(["spec"]) == 0
    out = capsys.readouterr().out
    assert "고주파" in out or "노안" in out


# --------------------------------------------------------------- 등록
def test_registered_as_program_2():
    program = Registry().require("senior-video")
    assert program.number == 2
    assert program.status == "ready"


def test_audit_is_declared_as_a_waiting_item():
    """심사에 몇 주가 걸린다는 것을 상품이 스스로 들고 있어야 한다."""
    need = Registry().require("senior-video").requirements
    waiting = [item.name for item in need.reviewed_accounts]
    assert any("감사" in name for name in waiting)
    assert not need.starts_today, "심사가 걸린 상품을 '오늘 바로' 라고 하면 안 된다"


def test_manifest_warns_about_mass_upload_policy():
    cautions = " ".join(Registry().require("senior-video").requirements.cautions)
    assert "양산형" in cautions
    assert "승인자 이름" in cautions
