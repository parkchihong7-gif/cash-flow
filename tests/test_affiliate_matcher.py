"""10번 제휴 상품 매칭 로직 테스트.

이 상품에서 깨지면 안 되는 것은 세 가지다.

    1. **대가성 문구 없이는 링크가 나가지 않는다.** 빠뜨리면 쿠팡파트너스가
       경고 없이 자격을 정지한다(CLAUDE.md §3-6).
    2. **본문과 무관한 상품을 끼워 넣지 않는다.** 구매 의도 2 이하는 계획에서 뺀다.
    3. **자가 구매를 부추기지 않는다.** 파트너스 규정 위반이라 계정이 끊긴다.

서명(HMAC)은 공식 문서에 적힌 규칙대로 조립되는지 고정한다. 이 환경에서는
api-gateway.coupang.com 에 닿지 못해 실제 응답으로는 확인하지 못했다.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_module
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import load_product_cli
from shared import banned_phrases

from affiliate import disclosure
from affiliate.extract import Extractor, numbered, split_paragraphs
from affiliate.links import (
    CoupangClient, CoupangError, DEEPLINK_PATH, SEARCH_PATH, authorization,
    candidates_for, search_url, signature, signed_date,
)
from affiliate.output import insert_plan_markdown, write_outputs, build_result
from affiliate.sample_content import fake_ask
from affiliate.schema import (
    Extraction, Mention, MatchResult, self_purchase_hits, slugify,
)
from affiliate.score import load_rates, score_all, score_one

BASE_DIR = Path(__file__).resolve().parents[1] / "products" / "affiliate-matcher"
SAMPLES = sorted((BASE_DIR / "data" / "samples").glob("*.md"))

cli = load_product_cli("affiliate-matcher")


@pytest.fixture(scope="module")
def table():
    return load_rates()


def _mention(**kwargs) -> Mention:
    base = {
        "paragraph": 3,
        "context": "무게 1kg 안쪽으로 고르시면 됩니다.",
        "category": "스포츠레저",
        "keywords": ["캠핑 의자", "경량 폴딩 체어", "백패킹 의자"],
        "intent": 5,
        "insert_sentence": "제가 쓰는 건 1kg 아래 접이식입니다.",
    }
    base.update(kwargs)
    return Mention(**base)


def _run_dry(tmp_path: Path, source: Path, extra: list[str] | None = None) -> Path:
    args = ["run", str(source), "--dry-run", "--out", str(tmp_path)]
    code = cli.main(args + (extra or []))
    assert code in (0, 2), f"종료 코드 {code}"
    return next(tmp_path.iterdir())


# ------------------------------------------------------------------ 원고 자르기
def test_paragraphs_split_on_blank_lines():
    text = "첫 문단입니다.\n\n둘째 문단입니다.\n\n셋째 문단입니다."
    assert split_paragraphs(text) == ["첫 문단입니다.", "둘째 문단입니다.", "셋째 문단입니다."]


def test_a_script_without_blank_lines_still_splits():
    """대본은 줄바꿈 한 번으로 이어 쓴다. 문단이 하나면 '어디에' 를 말할 수 없다."""
    text = "첫 줄입니다.\n둘째 줄입니다.\n셋째 줄입니다."
    assert len(split_paragraphs(text)) == 3


def test_numbering_starts_at_zero():
    assert numbered(["가", "나"]).startswith("[0] 가")


def test_empty_text_gives_no_paragraphs():
    assert split_paragraphs("   \n\n  ") == []


# --------------------------------------------------------------------- 규격
def test_keywords_must_be_exactly_three():
    with pytest.raises(ValidationError, match="정확히 3개"):
        _mention(keywords=["캠핑 의자", "폴딩 체어"])


def test_keywords_must_differ():
    with pytest.raises(ValidationError, match="겹칩니다"):
        _mention(keywords=["캠핑 의자", "캠핑 의자", "폴딩 체어"])


@pytest.mark.parametrize("intent", [0, 6, -1])
def test_intent_stays_between_one_and_five(intent):
    with pytest.raises(ValidationError):
        _mention(intent=intent)


def test_insert_sentence_rejects_self_purchase():
    """자가 구매 유도는 파트너스 규정 위반이다. 규격에서 막는다."""
    with pytest.raises(ValidationError, match="자가 구매"):
        _mention(insert_sentence="제 링크로 사시면 제가 수수료를 받아 페이백 드립니다.")


def test_insert_sentence_rejects_banned_phrases():
    with pytest.raises(ValidationError, match="쓰면 안 되는"):
        _mention(insert_sentence="이거 하나면 수익 보장 됩니다.")


@pytest.mark.parametrize("text", [
    "본인 구매도 수수료가 붙습니다",
    "자가 구매 하시면 됩니다",
    "제 링크로 사시면 제가 캐시백 드립니다",
    "수수료 나눠 드릴게요",
])
def test_self_purchase_detector_catches_variants(text):
    assert self_purchase_hits(text)


def test_self_purchase_detector_ignores_normal_sentences():
    assert self_purchase_hits("제가 직접 써 보고 좋아서 소개합니다.") == []


def test_mentions_beyond_the_text_are_dropped():
    extraction = Extraction(mentions=[_mention(paragraph=2), _mention(paragraph=99)])
    extraction.within(5)
    assert [m.paragraph for m in extraction.mentions] == [2]


def test_slugify_keeps_korean():
    assert slugify("캠핑 장비 순서!!") == "캠핑-장비-순서"
    assert slugify("   ", "기본값") == "기본값"


# ------------------------------------------------------------------- 수수료 표
def test_every_rate_carries_a_source(table):
    for category in table.categories:
        assert len(category.source) >= 8, category.name
    assert len(table.default_source) >= 8


def test_a_rate_without_a_source_is_refused(tmp_path):
    """근거 없는 숫자를 넣으면 표를 아예 읽지 않는다."""
    path = tmp_path / "bad.yaml"
    path.write_text(
        "meta:\n  as_of: '2026-01-01'\n  default_source: 아무 근거나 적어 둔 문장입니다\n"
        "categories:\n  - name: 뷰티\n    rate: 0.07\n    avg_price: 30000\n    source: ''\n",
        encoding="utf-8")
    with pytest.raises(ValueError, match="근거"):
        load_rates(path)


def test_boosted_categories_beat_the_default(table):
    """뷰티·패션·스포츠·출산육아는 상향 구간이다(요청 규격)."""
    for name in ("뷰티", "패션의류잡화", "스포츠레저", "출산유아동"):
        category = table.find(name)
        assert category is not None, name
        assert category.rate > table.default_rate, name


def test_unknown_category_falls_back_with_a_reason(table):
    scored = score_one(_mention(category="듣도보도못한분류"), table)
    assert scored.rate == table.default_rate
    assert "표에 없는" in scored.rate_source
    assert scored.matched_category.startswith("(표에 없음")


def test_category_matching_tolerates_small_differences(table):
    """Claude 는 '뷰티/미용' 처럼 조금 다르게 적어 온다."""
    assert table.find("뷰티/미용") is not None
    assert table.find("패션 의류 잡화") is not None


# ----------------------------------------------------------------------- 점수
def test_score_is_commission_times_intent_weight(table):
    scored = score_one(_mention(category="스포츠레저", intent=4), table)
    category = table.find("스포츠레저")
    expected = round(category.avg_price * category.rate)
    assert scored.expected_commission == expected
    assert scored.score == pytest.approx(expected * table.weight(4), rel=1e-6)


def test_higher_intent_ranks_higher(table):
    low = score_one(_mention(intent=3), table)
    high = score_one(_mention(intent=5), table)
    assert high.score > low.score


@pytest.mark.parametrize("intent", [1, 2])
def test_weak_mentions_are_excluded_from_the_plan(table, intent):
    """본문과 무관한 상품 추천 금지 — 강도 2 이하는 계획에서 뺀다."""
    scored = score_one(_mention(intent=intent), table)
    assert not scored.in_plan
    assert scored.intent_weight == 0
    assert scored.score == 0
    assert "구매 의도" in scored.excluded_because


@pytest.mark.parametrize("intent", [3, 4, 5])
def test_strong_mentions_enter_the_plan(table, intent):
    assert score_one(_mention(intent=intent), table).in_plan


def test_results_come_back_sorted(table):
    extraction = Extraction(mentions=[
        _mention(paragraph=1, intent=3),
        _mention(paragraph=2, intent=5),
        _mention(paragraph=3, intent=4),
    ])
    scored = score_all(extraction, table)
    assert [item.mention.intent for item in scored] == [5, 4, 3]


# ------------------------------------------------------------------- 서명(HMAC)
# 쿠팡 공식 문서가 적어 둔 규칙:
#   message   = signed-date + METHOD + path + query   (물음표는 빼고 잇는다)
#   signature = HMAC-SHA256(secret, message) 16진수 소문자
#   header    = "CEA algorithm=HmacSHA256, access-key=..., signed-date=..., signature=..."
#
# 문서의 예시 요청(products/search?keyword=good&limit=10)을 입력으로 쓰고,
# 기대값은 이 파일 안에서 **따로 조립해** 계산한다. 구현이 틀리면 두 값이 갈린다.
DOC_METHOD = "GET"
DOC_PATH = SEARCH_PATH
DOC_QUERY = "keyword=good&limit=10"
DOC_DATE = "260917T010203Z"
DOC_SECRET = "test-secret-key"
DOC_ACCESS = "test-access-key"

#: 위 값으로 한 번 계산해 못 박아 둔 값. 조립 규칙이 바뀌면 여기서 걸린다.
DOC_SIGNATURE = "e41b455699a3f44e6033d0c3fc679720c79c231a1acec000516345d898eba3c9"


def test_signature_matches_an_independent_calculation():
    message = DOC_DATE + DOC_METHOD + DOC_PATH + DOC_QUERY
    expected = hmac_module.new(
        DOC_SECRET.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    got = signature(DOC_METHOD, f"{DOC_PATH}?{DOC_QUERY}", DOC_SECRET, DOC_DATE)
    assert got == expected == DOC_SIGNATURE


def test_signature_drops_the_question_mark():
    """물음표를 남기면 서명이 달라져 401 이 난다."""
    with_query = signature("GET", f"{DOC_PATH}?{DOC_QUERY}", DOC_SECRET, DOC_DATE)
    wrong = hmac_module.new(
        DOC_SECRET.encode("utf-8"),
        (DOC_DATE + "GET" + DOC_PATH + "?" + DOC_QUERY).encode("utf-8"),
        hashlib.sha256).hexdigest()
    assert with_query != wrong


def test_signature_ignores_the_domain():
    """서명에는 경로만 들어간다. 도메인을 넣으면 거절당한다."""
    bare = signature("GET", DOC_PATH, DOC_SECRET, DOC_DATE)
    full = signature("GET", "https://api-gateway.coupang.com" + DOC_PATH, DOC_SECRET, DOC_DATE)
    assert bare == full


def test_signature_uses_the_method_in_upper_case():
    assert (signature("get", DOC_PATH, DOC_SECRET, DOC_DATE)
            == signature("GET", DOC_PATH, DOC_SECRET, DOC_DATE))


def test_a_different_secret_gives_a_different_signature():
    assert signature("GET", DOC_PATH, "another-secret", DOC_DATE) != DOC_SIGNATURE


def test_authorization_header_has_the_documented_shape():
    header = authorization(DOC_METHOD, f"{DOC_PATH}?{DOC_QUERY}",
                           DOC_ACCESS, DOC_SECRET, DOC_DATE)
    assert header == (f"CEA algorithm=HmacSHA256, access-key={DOC_ACCESS}, "
                      f"signed-date={DOC_DATE}, signature={DOC_SIGNATURE}")


def test_signed_date_is_gmt_not_local_time():
    """한국 시각으로 서명하면 9시간이 어긋나 거절당한다."""
    kst = timezone(timedelta(hours=9))
    assert signed_date(datetime(2026, 9, 17, 10, 2, 3, tzinfo=kst)) == "260917T010203Z"
    assert signed_date(datetime(2026, 9, 17, 1, 2, 3, tzinfo=timezone.utc)) == "260917T010203Z"


def test_signed_date_shape():
    now = signed_date()
    assert len(now) == 14 and now[6] == "T" and now.endswith("Z")
    assert now[:6].isdigit() and now[7:13].isdigit()


# ------------------------------------------------------------------- 링크 후보
def test_without_keys_only_search_urls_are_made():
    links, warnings = candidates_for(["캠핑 의자", "헤드랜턴"], None)
    assert set(links) == {"캠핑 의자", "헤드랜턴"}
    for candidates in links.values():
        assert candidates[0].kind == "search_url"
        assert candidates[0].needs_api_key
        assert "API 키" in candidates[0].note
    assert warnings == []


def test_search_url_is_percent_encoded():
    assert search_url("캠핑 의자").startswith("https://www.coupang.com/np/search?q=")
    assert " " not in search_url("캠핑 의자")


def test_duplicate_keywords_are_searched_once():
    links, _ = candidates_for(["캠핑 의자", "캠핑 의자", " 캠핑 의자 "], None)
    assert list(links) == ["캠핑 의자"]


class _FakeResponse:
    """urlopen 이 돌려주는 것 흉내."""

    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_client(payload: dict, seen: list) -> CoupangClient:
    client = CoupangClient(access_key="AK", secret_key="SK")

    def opener(request, timeout=None):
        seen.append(request)
        return _FakeResponse(payload)

    client.opener = opener
    return client


def test_search_sends_a_signed_request():
    seen: list = []
    client = _fake_client({"data": {"productData": [
        {"productName": "접이식 캠핑 의자", "productUrl": "https://link.coupang.com/a/AAA",
         "productPrice": 32900, "productImage": "https://img/1.jpg", "isRocket": True},
    ]}}, seen)

    found = client.search("캠핑 의자", limit=5)

    assert len(seen) == 1
    request = seen[0]
    header = request.get_header("Authorization")
    assert header.startswith("CEA algorithm=HmacSHA256, access-key=AK, ")
    assert "signature=" in header
    assert SEARCH_PATH in request.full_url
    assert found[0].kind == "api" and found[0].price == 32900 and found[0].is_rocket


def test_deeplink_posts_the_urls():
    seen: list = []
    client = _fake_client({"data": [
        {"originalUrl": "https://www.coupang.com/vp/products/1",
         "shortenUrl": "https://link.coupang.com/a/BBB"},
    ]}, seen)

    mapping = client.deeplink(["https://www.coupang.com/vp/products/1"])

    assert mapping == {"https://www.coupang.com/vp/products/1": "https://link.coupang.com/a/BBB"}
    assert seen[0].method == "POST" and DEEPLINK_PATH in seen[0].full_url


def test_deeplink_without_urls_calls_nothing():
    seen: list = []
    assert _fake_client({}, seen).deeplink([]) == {}
    assert seen == []


def test_a_failed_search_falls_back_to_the_search_url():
    class _Broken(CoupangClient):
        def search(self, keyword, limit=5):
            raise CoupangError("[HTTP 429] 호출이 너무 잦습니다.")

    links, warnings = candidates_for(["캠핑 의자"], _Broken(access_key="A", secret_key="B"))
    assert links["캠핑 의자"][0].kind == "search_url"
    assert warnings and "검색 실패" in warnings[0]


# ------------------------------------------------------------------ 대가성 문구
def test_disclosure_block_covers_every_channel():
    block = disclosure.disclosure_block("블로그")
    for marker in ("쿠팡 파트너스", "유료 프로모션", "제휴 링크"):
        assert marker in block


def test_assert_disclosed_passes_on_the_real_thing():
    disclosure.assert_disclosed(disclosure.COUPANG)
    disclosure.assert_disclosed("본문입니다.\n\n" + disclosure.YOUTUBE_DESCRIPTION)


def test_assert_disclosed_refuses_a_bare_link():
    with pytest.raises(disclosure.DisclosureMissing, match="자격이 정지"):
        disclosure.assert_disclosed("좋은 의자입니다 https://link.coupang.com/a/AAA")


def test_result_cannot_be_built_without_a_disclosure():
    with pytest.raises(ValidationError, match="대가성 문구"):
        MatchResult(disclosure="")


def test_written_files_all_carry_the_disclosure(tmp_path):
    out = _run_dry(tmp_path, SAMPLES[0])
    for name in ("matches.json", "insert_plan.md", "disclosure.txt"):
        text = (out / name).read_text(encoding="utf-8")
        disclosure.assert_disclosed(text, name)


def test_writing_is_refused_when_the_disclosure_is_stripped(tmp_path, monkeypatch, table):
    """문구를 지운 채로는 저장되지 않는다. 이 상품의 마지막 방어선이다."""
    extraction = Extraction(mentions=[_mention()])
    result = build_result(
        extraction=extraction, scored=score_all(extraction, table), links={},
        table=table, source_file="x.md", paragraph_count=5, dry_run=True,
        api_used=False, warnings=[])

    # 문구 덩어리를 통째로 갈아 끼운다. 쓰는 사람이 disclosure.py 를 고쳐
    # 문구를 빼 버린 상황이다.
    monkeypatch.setattr(disclosure, "disclosure_block",
                        lambda medium="": "오늘도 좋은 하루 보내세요")

    with pytest.raises(disclosure.DisclosureMissing):
        write_outputs(result, ["문단"], tmp_path / "out")
    assert not (tmp_path / "out" / "insert_plan.md").exists()
    assert not (tmp_path / "out" / "matches.json").exists()


# --------------------------------------------------------------------- 산출물
@pytest.mark.parametrize("sample", SAMPLES, ids=lambda p: p.stem)
def test_every_sample_runs_and_writes_three_files(tmp_path, sample):
    out = _run_dry(tmp_path, sample)
    for name in ("matches.json", "insert_plan.md", "disclosure.txt"):
        assert (out / name).is_file(), name
        assert (out / name).stat().st_size > 200


def test_there_are_three_samples():
    assert len(SAMPLES) == 3, "샘플 원고 3개가 있어야 합니다"


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda p: p.stem)
def test_matches_json_validates_against_the_schema(tmp_path, sample):
    out = _run_dry(tmp_path, sample)
    assert cli.main(["check", str(out / "matches.json")]) == 0


def test_the_plan_only_holds_strong_mentions(tmp_path):
    out = _run_dry(tmp_path, SAMPLES[0])
    raw = json.loads((out / "matches.json").read_text(encoding="utf-8"))
    planned = [item for item in raw["matches"] if item["in_plan"]]
    assert planned, "넣을 자리가 하나도 없습니다"
    assert all(item["mention"]["intent"] >= 3 for item in planned)


def test_dropped_mentions_are_kept_with_a_reason(tmp_path):
    """뺀 것을 지워 버리면 프로그램이 놓친 줄 안다."""
    out = _run_dry(tmp_path, SAMPLES[0])
    plan = (out / "insert_plan.md").read_text(encoding="utf-8")
    assert "## 뺀 것" in plan
    assert "구매 의도" in plan


def test_the_plan_tells_where_and_what_to_write(tmp_path):
    out = _run_dry(tmp_path, SAMPLES[0])
    plan = (out / "insert_plan.md").read_text(encoding="utf-8")
    assert "번 문단 뒤" in plan
    assert "**넣을 문장**" in plan
    assert "올리기 전에" in plan


def test_outputs_are_labelled_as_ai_made(tmp_path):
    out = _run_dry(tmp_path, SAMPLES[0])
    plan = (out / "insert_plan.md").read_text(encoding="utf-8")
    assert "생성형 AI" in plan
    raw = json.loads((out / "matches.json").read_text(encoding="utf-8"))
    assert raw["ai_generated"] is True


def test_the_ai_label_can_be_turned_off(tmp_path):
    out = _run_dry(tmp_path, SAMPLES[0], ["--no-ai-label"])
    assert "생성형 AI" not in (out / "insert_plan.md").read_text(encoding="utf-8")


def test_a_dry_run_says_so_in_the_file(tmp_path):
    out = _run_dry(tmp_path, SAMPLES[0])
    assert "모의 실행" in (out / "insert_plan.md").read_text(encoding="utf-8")


def test_no_banned_phrases_in_the_plan(tmp_path):
    out = _run_dry(tmp_path, SAMPLES[0])
    assert banned_phrases.check((out / "insert_plan.md").read_text(encoding="utf-8")) == []


def test_no_self_purchase_wording_in_the_plan(tmp_path):
    out = _run_dry(tmp_path, SAMPLES[0])
    assert self_purchase_hits((out / "insert_plan.md").read_text(encoding="utf-8")) == []


def test_a_script_without_products_gets_no_plan(table):
    """상품 이야기가 없으면 '붙이지 마세요' 라고 말해야 한다."""
    extraction = Extraction(mentions=[_mention(intent=1), _mention(paragraph=4, intent=2)])
    result = build_result(
        extraction=extraction, scored=score_all(extraction, table), links={},
        table=table, source_file="x.md", paragraph_count=6, dry_run=True,
        api_used=False, warnings=[])
    plan = insert_plan_markdown(result, ["문단"] * 6)
    assert "넣을 자리가 없습니다" in plan
    assert "붙이지 않는 편이 낫습니다" in plan


# ------------------------------------------------------------------- 추출기
def test_extractor_retries_when_the_shape_is_wrong():
    calls = {"n": 0}

    def flaky(system, user, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"mentions": [{"paragraph": 0, "context": "짧", "category": "뷰티",
                                  "keywords": ["하나"], "intent": 9,
                                  "insert_sentence": "짧음"}]}
        return fake_ask(system, user)

    extractor = Extractor("test", flaky)
    script = "\n\n".join([f"캠핑 이야기 {n}번째 문단입니다. 의자와 랜턴, 침낭 이야기."
                           for n in range(9)])
    extraction, paragraphs = extractor.run(script)
    assert calls["n"] == 2
    assert extractor.warnings and "2번째" in extractor.warnings[0]
    assert extraction.mentions


def test_extractor_gives_up_with_advice():
    def always_bad(system, user, **kwargs):
        return {"mentions": [{"paragraph": 0}]}

    with pytest.raises(ValueError, match="규격에 맞지 않았습니다"):
        Extractor("test", always_bad).run("문단 하나.\n\n문단 둘.")


def test_extractor_refuses_an_empty_script():
    with pytest.raises(ValueError, match="비어 있습니다"):
        Extractor("test", fake_ask).run("   ")


def test_extractor_drops_out_of_range_paragraphs():
    def far_away(system, user, **kwargs):
        return {"medium": "블로그", "mentions": [
            _mention(paragraph=0).model_dump(),
            _mention(paragraph=50).model_dump(),
        ]}

    extractor = Extractor("test", far_away)
    extraction, _ = extractor.run("첫 문단.\n\n둘째 문단.")
    assert [m.paragraph for m in extraction.mentions] == [0]
    assert any("본문에 없는 문단" in w for w in extractor.warnings)


def test_the_fixtures_include_weak_mentions():
    """걸러지는 장치가 실제로 도는지 보려면 약한 언급이 섞여 있어야 한다."""
    from affiliate.sample_content import FIXTURES

    for name, data in FIXTURES.items():
        assert any(m["intent"] <= 2 for m in data["mentions"]), name


# ----------------------------------------------------------------------- CLI
def test_cli_without_a_command_shows_help(capsys):
    assert cli.main([]) == 1
    assert "run" in capsys.readouterr().out


def test_cli_rejects_a_missing_script(capsys):
    assert cli.main(["run", "/없는/원고.md", "--dry-run"]) == 1
    assert "찾지 못했습니다" in capsys.readouterr().err


def test_rates_command_shows_sources(capsys):
    assert cli.main(["rates", "--sources"]) == 0
    out = capsys.readouterr().out
    assert "기준일" in out and "CLAUDE.md" in out
    assert "계획에서 제외" in out


def test_run_without_api_keys_finishes_cleanly(tmp_path, monkeypatch, capsys):
    """키 없는 환경에서도 정상 종료 — 요청 규격의 완료 기준."""
    monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
    monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)
    code = cli.main(["run", str(SAMPLES[0]), "--dry-run", "--out", str(tmp_path)])
    assert code in (0, 2)
    out = capsys.readouterr().out
    assert "오류가 아닙니다" in out
    assert "검색 주소" in out


def test_check_rejects_a_plan_holding_weak_mentions(tmp_path):
    """규격을 우회해 손으로 고친 파일도 걸러 낸다."""
    out = _run_dry(tmp_path, SAMPLES[0])
    path = out / "matches.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    for item in raw["matches"]:
        item["in_plan"] = True
        item["excluded_because"] = ""
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    assert cli.main(["check", str(path)]) == 2


def test_check_refuses_a_file_without_a_disclosure(tmp_path):
    path = tmp_path / "matches.json"
    path.write_text(json.dumps({"disclosure": ""}, ensure_ascii=False), encoding="utf-8")
    assert cli.main(["check", str(path)]) == 1


# ---------------------------------------------------------------------- 문서
def test_readme_covers_usage_and_limits():
    text = (BASE_DIR / "README.md").read_text(encoding="utf-8")
    for token in ("cli.py run", "COUPANG_ACCESS_KEY", "대가성", "구매 의도"):
        assert token in text, token
    assert banned_phrases.check(text) == []


def test_product_manuals_are_detailed_and_clean():
    for name in ("admin.md", "client.md"):
        path = BASE_DIR / "docs" / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert len(text) > 4000, f"{name} 이 너무 짧습니다"
        assert banned_phrases.check(text) == []


def test_the_prompt_states_the_hard_rules():
    text = (BASE_DIR / "prompts" / "extract.md").read_text(encoding="utf-8")
    for token in ("자가 구매", "2 이하", "키워드"):
        assert token in text, token


def test_env_example_lists_the_coupang_keys():
    text = (BASE_DIR / ".env.example").read_text(encoding="utf-8")
    assert "COUPANG_ACCESS_KEY" in text and "COUPANG_SECRET_KEY" in text
    assert "실제 키" not in text.split("=")[-1]
