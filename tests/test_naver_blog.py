"""15번 네이버 블로그 초안 생성기 테스트.

핵심 검사 셋:
1. **자동 게시 경로가 없는가** (네이버는 글쓰기 API 가 없고, 흉내 내면 계정 정지)
2. **대가성 문구 없이 산출물이 나오는가** (나오면 안 된다 — 표시광고법)
3. **빈칸을 안 채운 글이 통과되는가** (통과되면 안 된다 — 원본성)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import load_product_cli
from core.registry import Registry
from naver_blog.demand import (
    DAILY_CALL_LIMIT, DemandError, FixtureClient, Keyword, NaverClient,
    collect, competition_label, make_client,
)
from naver_blog.draft import (
    DRAFT_SYSTEM, Draft, PLACEHOLDER, Request, build_prompt, offline_draft, parse_draft,
)
from naver_blog.policy import (
    BANNED_AUTOMATION, DISCLOSURE, DISCLOSURE_RULES, DisclosureMissing,
    NO_WRITE_API, SPONSOR_KINDS, assert_disclosed, disclosure_for,
)
from naver_blog.review import MIN_CHARS, ready, review

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "naver-blog"
FIXTURES = PRODUCT / "data" / "fixtures"

LONG_BODY = "\n".join([
    "## 첫 소제목", "본문 " * 200, "", "## 둘째 소제목", "본문 " * 200,
    "", "## 셋째 소제목", "본문 " * 200,
])


def _draft(**kwargs) -> Draft:
    base = dict(title="제목입니다", body=LONG_BODY, tags=["가", "나", "다"])
    base.update(kwargs)
    return Draft(**base)


# ------------------------------------------------ 자동 게시 경로가 없다
def test_no_posting_api_is_stated_plainly():
    assert "글쓰기 공개 API 를 제공하지 않습니다" in NO_WRITE_API
    assert "계정이 정지" in BANNED_AUTOMATION


def test_the_client_only_reads():
    """쓰기 메서드가 있으면 안 된다. 읽는 것 둘뿐이다."""
    methods = {name for name in dir(NaverClient) if not name.startswith("_")}
    assert methods == {"blog_count", "trend"}
    for forbidden in ("post_article", "publish", "write", "login"):
        assert forbidden not in methods


def test_no_module_mentions_a_password_field():
    """비밀번호를 받는 자리가 어디에도 없어야 한다."""
    for path in (PRODUCT / "naver_blog").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("selenium", "webdriver", "pyautogui", "NAVER_PASSWORD"):
            assert forbidden not in source, f"{path.name} 에 {forbidden} 이 있습니다"


def test_env_example_warns_against_storing_naver_credentials():
    text = (PRODUCT / ".env.example").read_text(encoding="utf-8")
    assert "비밀번호를 여기 적지 마세요" in text


# --------------------------------------------------------- 대가성 문구
@pytest.mark.parametrize("kind", ["sponsored", "affiliate", "paid", "gift"])
def test_paid_posts_need_a_disclosure(kind):
    with pytest.raises(DisclosureMissing, match="대가성 문구가 없습니다"):
        assert_disclosed("아무 말도 없는 본문입니다", kind)


def test_unpaid_posts_need_nothing():
    assert_disclosed("본문", "none") is None
    assert_disclosed("본문", "") is None
    assert disclosure_for("none") == ""


def test_disclosure_fills_in_the_sponsor_name():
    text = disclosure_for("sponsored", "OO상사")
    assert "OO상사" in text
    assert "원고료" in text


def test_disclosure_without_a_name_keeps_the_placeholder():
    assert "OO" in disclosure_for("sponsored")


def test_unknown_sponsor_kind_lists_the_valid_ones():
    with pytest.raises(ValueError, match="쓸 수 있는 것"):
        disclosure_for("뭔가")


def test_draft_with_disclosure_passes_the_check():
    request = Request(topic="주제", sponsor_kind="sponsored", sponsor_name="OO상사")
    draft = offline_draft(request)
    assert draft.disclosure
    assert draft.full_text().startswith(draft.disclosure), "문구는 맨 위에 와야 한다"


def test_disclosure_rules_cover_where_to_put_it():
    joined = " ".join(DISCLOSURE_RULES)
    assert "맨 위" in joined
    assert "더보기" in joined
    assert "해시태그" in joined


def test_parse_draft_blocks_a_paid_post_missing_the_phrase(monkeypatch):
    """모델이 문구를 빼먹어도 여기서 막힌다."""
    import naver_blog.draft as draft_module

    monkeypatch.setattr(draft_module, "disclosure_for", lambda kind, name="": "")
    request = Request(topic="주제", sponsor_kind="sponsored")
    with pytest.raises(DisclosureMissing):
        draft_module.parse_draft("제목: 제목\n---\n본문\n---\n태그: 가", request)


# ------------------------------------------------------------ 빈칸 검사
def test_unfilled_placeholders_block_publishing():
    draft = _draft(body=f"## 소제목\n{PLACEHOLDER}\n{LONG_BODY}")
    issues = review(draft)
    assert not ready(issues)
    blocking = [item for item in issues if item.blocking]
    assert any("채우지 않은 자리" in item.title for item in blocking)


def test_offline_draft_leaves_places_to_fill():
    draft = offline_draft(Request(topic="전세 계약"))
    assert draft.placeholders >= 3, "사람이 쓸 자리를 남겨야 한다"
    assert not ready(review(draft))


def test_a_filled_draft_is_ready():
    assert ready(review(_draft()))


def test_short_body_is_warned_not_blocked():
    issues = review(_draft(body="## 소제목\n짧은 본문"))
    short = [item for item in issues if "짧습니다" in item.title]
    assert short and short[0].level == "warn"
    assert f"{MIN_CHARS:,}" in short[0].detail


def test_banned_phrases_block_publishing():
    draft = _draft(body=LONG_BODY + "\n이 방법이면 무조건 수익 보장됩니다")
    issues = review(draft)
    assert not ready(issues)
    assert any("과장 문구" in item.title for item in issues)


def test_too_many_tags_is_warned():
    issues = review(_draft(tags=[f"태그{n}" for n in range(15)]))
    assert any("태그가 15개" in item.title for item in issues)


# ---------------------------------------------------------------- 수요
def test_fixture_client_needs_no_key():
    client = make_client(fixture_dir=FIXTURES)
    assert isinstance(client, FixtureClient)
    assert client.blog_count("전세 계약 주의사항") > 0


def test_missing_key_tells_you_where_to_get_one():
    with pytest.raises(DemandError, match="developers.naver.com"):
        make_client("", "")


def test_collect_sorts_least_crowded_first():
    rows = collect(["전세 계약 주의사항", "인천 신축 아파트 하자"],
                   make_client(fixture_dir=FIXTURES))
    assert rows[0].total_posts < rows[-1].total_posts


def test_very_quiet_keywords_are_flagged_as_suspicious():
    """경쟁이 없는 게 아니라 찾는 사람이 없는 것일 수 있다."""
    quiet = Keyword(word="아주 좁은 말", total_posts=900)
    assert quiet.too_quiet
    assert not quiet.crowded
    assert competition_label(900) == "아주 한산함"


def test_trend_direction_reads_the_shape():
    assert Keyword(word="가", trend=[10, 12, 14, 30, 34, 40]).trend_direction == "오르는 중"
    assert Keyword(word="가", trend=[40, 38, 36, 12, 10, 9]).trend_direction == "내려가는 중"
    assert Keyword(word="가", trend=[20, 21, 20, 21, 20, 21]).trend_direction == "비슷함"
    assert Keyword(word="가", trend=[1, 2]).trend_direction == "알 수 없음"


def test_quota_message_says_to_wait_not_retry():
    assert "내일 도세요" in NaverClient._explain(429)
    assert f"{DAILY_CALL_LIMIT:,}" in NaverClient._explain(429)


def test_403_points_at_the_app_settings():
    assert "데이터랩" in NaverClient._explain(403)


# ---------------------------------------------------------------- 초안
def test_prompt_forbids_copying_and_overclaiming():
    assert "남의 글을 옮기지 않습니다" in DRAFT_SYSTEM
    assert "보장하는 말을 쓰지 않습니다" in DRAFT_SYSTEM
    assert PLACEHOLDER in DRAFT_SYSTEM


def test_prompt_carries_the_request_details():
    prompt = build_prompt(Request(topic="전세 계약", keyword="전세 주의사항",
                                  must_include=["등기부등본"]))
    assert "전세 계약" in prompt and "등기부등본" in prompt


def test_parse_draft_reads_the_three_blocks():
    raw = "제목: 좋은 제목\n---\n## 소제목\n본문입니다\n---\n태그: 가, 나, 다"
    draft = parse_draft(raw, Request(topic="주제"))
    assert draft.title == "좋은 제목"
    assert draft.headings == ["소제목"]
    assert draft.tags == ["가", "나", "다"]


def test_parse_draft_survives_a_malformed_answer():
    draft = parse_draft("형식이 다 틀린 답", Request(topic="원래 주제"))
    assert draft.title == "원래 주제"
    assert draft.body


# ------------------------------------------------------------------ CLI
def test_cli_dry_run_refuses_to_call_it_ready(tmp_path, capsys):
    cli = load_product_cli("naver-blog")
    code = cli.main(["draft", "--dry-run", "--out", str(tmp_path)])
    assert code == 2, "빈칸이 남은 초안은 아직 올리면 안 된다"
    out = capsys.readouterr().out
    assert "아직 올리시면 안 됩니다" in out
    assert len(list(tmp_path.glob("draft_*.md"))) == 1


def test_cli_demand_runs_without_a_key(capsys):
    cli = load_product_cli("naver-blog")
    assert cli.main(["demand", "--fixture"]) == 0
    out = capsys.readouterr().out
    assert "샘플 자료입니다" in out
    assert "붐빔" in out


def test_cli_policy_explains_what_is_not_possible(capsys):
    cli = load_product_cli("naver-blog")
    assert cli.main(["policy"]) == 0
    out = capsys.readouterr().out
    assert "글쓰기 공개 API" in out
    assert "맨 위" in out


def test_cli_disclosure_prints_the_phrase_and_the_rules(capsys):
    cli = load_product_cli("naver-blog")
    assert cli.main(["disclosure", "--kind", "gift", "--name", "OO전자"]) == 0
    out = capsys.readouterr().out
    assert "무상으로 제공받아" in out
    assert "OO전자" in out


# --------------------------------------------------------------- 등록
def test_registered_as_program_15():
    program = Registry().require("naver-blog")
    assert program.number == 15
    assert program.status == "ready"
    assert program.requirements.home_pc == "yes"


def test_manifest_warns_about_credentials_and_disclosure():
    cautions = " ".join(Registry().require("naver-blog").requirements.cautions)
    assert "자동 게시를 하지 않습니다" in cautions
    assert "비밀번호를 .env 에 적지 마세요" in cautions
    assert "표시광고법" in cautions


def test_naver_app_is_available_immediately():
    """심사가 없어서 파시기 쉬운 상품이다. 그 사실이 매니페스트에 있어야 한다."""
    need = Registry().require("naver-blog").requirements
    naver = next(item for item in need.accounts if "네이버 개발자센터" in item.name)
    assert naver.lead_time == "즉시"
    assert "무료" in naver.cost


def test_all_sponsor_kinds_have_a_phrase():
    for kind in SPONSOR_KINDS:
        if kind == "none":
            continue
        assert kind in DISCLOSURE
