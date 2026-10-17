"""products/celeb-shorts 테스트.

가짜 LLM 을 넣어 Claude 없이 입력 검사 → 기획 → 검사 → 산출물 → 승인 전 과정을 본다.
규칙이 "있다" 가 아니라 **실제로 막는다** 는 것을 확인하는 것이 목적이다.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from celeb_shorts.generator import Planner, build_request
from celeb_shorts.output import ApprovalRefused, approve, write_outputs
from celeb_shorts.rules import SUBTITLE_MAX, review_input, review_plan, split_subtitle
from celeb_shorts.sample_content import fake_ask
from celeb_shorts.schema import VISUALS, PlanDraft, Scene, ShortsInput, parse_item
from shared import banned_phrases

PRODUCT_DIR = Path(__file__).resolve().parent.parent / "products" / "celeb-shorts"


def _input(**overrides) -> ShortsInput:
    payload = {
        "celebrity": "배우 A",
        "occasion": "공항 출국",
        "source_url": "https://example.com/news/1",
        "source_name": "예시뉴스",
        "duration_sec": 15,
        "items": ["블랙 숄더백 | 브랜드B | o | 3200000 | 예시뉴스 | 블랙 숄더백",
                  "와이드 데님 | | x | | | 와이드 데님 팬츠"],
    }
    payload.update(overrides)
    return ShortsInput.model_validate(payload)


def _plan(**overrides) -> PlanDraft:
    payload = {
        "title": "공항 출국 아이템",
        "hook": "공항 출국 템",
        "scenes": [
            {"start": 0, "end": 2, "subtitle": "공항 출국 템", "visual": "text_card"},
            {"start": 2, "end": 8, "subtitle": "블랙 숄더백", "visual": "product_image", "item_index": 0},
            {"start": 8, "end": 13, "subtitle": "비슷한 데님", "visual": "product_image", "item_index": 1},
            {"start": 13, "end": 15, "subtitle": "상품 태그 확인", "visual": "text_card"},
        ],
        "description": "아이템을 모았습니다.",
        "hashtags": ["#쇼츠"],
    }
    payload.update(overrides)
    return PlanDraft.model_validate(payload)


def _build(tmp_path, data=None, dry_run=True):
    review = review_input(data or _input())
    plan, issues, notes = Planner("dry-run", fake_ask).run(review)
    out = write_outputs(tmp_path / "out", review, plan, issues, review.notes + notes,
                        dry_run=dry_run, ai_label_on=True, model="dry-run")
    return out, review, plan, issues


# ------------------------------------------------------------ 입력
def test_item_line_is_parsed():
    item = parse_item("블랙 숄더백 | 브랜드B | o | 3,200,000원 | 예시뉴스 | 숄더백")
    assert (item.name, item.brand, item.confirmed, item.price, item.keyword) == \
        ("블랙 숄더백", "브랜드B", True, 3200000, "숄더백")
    bare = parse_item("와이드 데님")
    assert not bare.confirmed and bare.price is None and bare.search_keyword == "와이드 데님"


def test_source_url_must_be_a_link():
    with pytest.raises(ValidationError):
        _input(source_url="기사에서 봄")


def test_too_many_items_for_15_seconds_is_blocked():
    review = review_input(_input(items=["a", "b", "c", "d"]))
    assert review.blocked


# ------------------------------------------------------------ 얼굴·이름·가격
def test_visuals_have_no_face_or_broadcast_option():
    joined = " ".join(VISUALS) + " ".join(VISUALS.values())
    for word in ("얼굴", "방송", "캡처", "직캠", "celeb", "face"):
        assert word not in joined
    with pytest.raises(ValidationError):
        Scene(start=0, end=2, subtitle="x", visual="celebrity_photo")


def test_without_source_the_name_is_never_sent():
    review = review_input(_input(source_url=""))
    assert not review.name_allowed
    request = build_request(review)
    assert request["celebrity"] == ""
    assert all(item["mode"] == "비슷한 스타일" for item in request["items"])
    assert "배우 A" not in json.dumps(request, ensure_ascii=False)


def test_leaked_name_is_scrubbed_when_not_allowed():
    review = review_input(_input(source_url=""))
    plan = _plan(title="배우 A 공항 가방", hook="배우 A 템")
    fixed, _, notes = review_plan(plan, review)
    text = fixed.model_dump_json()
    assert "배우 A" not in text
    assert any("지웠습니다" in note for note in notes)


def test_price_without_source_is_not_sent():
    review = review_input(_input(items=["가방 | | o | 50000 | | 가방"]))
    assert build_request(review)["items"][0]["price"] is None


def test_made_up_price_is_blocked():
    review = review_input(_input(items=["가방 | | o | | | 가방"]))
    plan = _plan(scenes=[
        {"start": 0, "end": 5, "subtitle": "가방 5만원", "visual": "product_image", "item_index": 0},
        {"start": 5, "end": 15, "subtitle": "상품 태그", "visual": "text_card"},
    ])
    _, issues, _ = review_plan(plan, review)
    assert any(i.level == "block" and "가격" in i.message for i in issues)


def test_wonga_is_blocked_even_with_a_price():
    _, issues, _ = review_plan(_plan(hook="샤넬백 원가 ㄷㄷ"), review_input(_input()))
    assert any(i.level == "block" and "원가" in i.message for i in issues)


def test_same_product_words_blocked_for_unconfirmed_item():
    plan = _plan(scenes=[
        {"start": 0, "end": 5, "subtitle": "똑같은 데님", "visual": "product_image", "item_index": 1},
        {"start": 5, "end": 15, "subtitle": "상품 태그", "visual": "text_card"},
    ])
    _, issues, _ = review_plan(plan, review_input(_input()))
    assert any(i.level == "block" and "똑같은" in i.message for i in issues)


def test_banned_phrase_is_blocked():
    _, issues, _ = review_plan(_plan(description="무조건 팔리는 템"), review_input(_input()))
    assert any(i.level == "block" and "금지 문구" in i.message for i in issues)


# ------------------------------------------------------------ 시간·자막
def test_timing_is_fitted_to_duration():
    plan = _plan(scenes=[
        {"start": 1, "end": 3, "subtitle": "a", "visual": "text_card"},
        {"start": 3, "end": 9, "subtitle": "b", "visual": "text_card"},
    ])
    fixed, _, _ = review_plan(plan, review_input(_input()))
    assert fixed.scenes[0].start == 0
    assert fixed.scenes[-1].end == 15
    assert all(a.end == b.start for a, b in zip(fixed.scenes, fixed.scenes[1:]))


def test_long_subtitle_is_split_in_two_lines():
    text = "이 가방 하나로 공항 패션이 완성됩니다"
    lines = split_subtitle(text).splitlines()
    assert len(lines) == 2 and all(len(line) <= SUBTITLE_MAX for line in lines)


def test_bad_item_index_falls_back_to_text_card():
    plan = _plan(scenes=[
        {"start": 0, "end": 5, "subtitle": "a", "visual": "product_image", "item_index": 9},
        {"start": 5, "end": 15, "subtitle": "b", "visual": "text_card"},
    ])
    fixed, _, _ = review_plan(plan, review_input(_input()))
    assert fixed.scenes[0].visual == "text_card" and fixed.scenes[0].item_index is None


# ------------------------------------------------------------ 산출물
def test_dry_run_writes_all_files_cleanly(tmp_path):
    out, _, plan, issues = _build(tmp_path)
    for name in ("plan.md", "plan.json", "subtitles.srt", "description.txt",
                 "shopping_list.csv", "checklist.md"):
        assert (out / name).is_file(), name
    assert not [i for i in issues if i.level == "block"]
    assert plan.scenes[-1].end == 15


def test_description_has_disclosure_source_and_ai_label(tmp_path):
    out, *_ = _build(tmp_path)
    text = (out / "description.txt").read_text(encoding="utf-8")
    assert text.startswith("유료 프로모션 포함")
    assert "쿠팡 파트너스" in text
    assert "https://example.com/news/1" in text
    assert "생성형 AI" in text
    assert banned_phrases.check(text) == []


def test_no_source_means_no_source_line_and_no_name(tmp_path):
    out, *_ = _build(tmp_path, _input(source_url=""))
    # 올라가는 글(설명란·자막)과 기획 본문에는 이름이 없어야 한다.
    # plan.md 의 '고친 것' 안내에는 왜 뺐는지 설명하느라 이름이 나온다 — 사람만 보는 곳이다.
    for name in ("description.txt", "subtitles.srt"):
        assert "배우 A" not in (out / name).read_text(encoding="utf-8"), name
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))["plan"]
    assert "배우 A" not in json.dumps(plan, ensure_ascii=False)
    assert "출처:" not in (out / "description.txt").read_text(encoding="utf-8")


def test_shopping_list_marks_modes_and_links(tmp_path):
    out, *_ = _build(tmp_path)
    rows = list(csv.DictReader((out / "shopping_list.csv").open(encoding="utf-8-sig")))
    assert [r["소개 방식"] for r in rows] == ["확인", "비슷한 스타일"]
    assert rows[0]["쿠팡 검색 주소"].startswith("https://www.coupang.com/np/search?q=")


def test_srt_is_well_formed(tmp_path):
    out, *_ = _build(tmp_path)
    blocks = (out / "subtitles.srt").read_text(encoding="utf-8").strip().split("\n\n")
    assert blocks[0].splitlines()[1] == "00:00:00,000 --> 00:00:02,000"
    assert blocks[-1].splitlines()[1].endswith("00:00:15,000")


# ------------------------------------------------------------ 승인
def test_dry_run_cannot_be_approved(tmp_path):
    out, *_ = _build(tmp_path)
    with pytest.raises(ApprovalRefused):
        approve(out, "홍길동")


def test_approval_needs_a_name_and_no_blocks(tmp_path):
    out, *_ = _build(tmp_path, dry_run=False)
    with pytest.raises(ApprovalRefused):
        approve(out, "  ")
    payload = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    payload["issues"].append({"level": "block", "where": "후크", "message": "원가"})
    (out / "plan.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ApprovalRefused):
        approve(out, "홍길동")


def test_clean_real_plan_is_approved(tmp_path):
    out, *_ = _build(tmp_path, dry_run=False)
    result = approve(out, "홍길동")
    assert result["by"] == "홍길동"
    assert json.loads((out / "plan.json").read_text(encoding="utf-8"))["approved"]["by"] == "홍길동"


# ------------------------------------------------------------ 판매 문서
def test_sales_texts_have_no_banned_phrases():
    for name in ("README.md", "program.yaml", "docs/client.md", "docs/admin.md"):
        assert banned_phrases.check((PRODUCT_DIR / name).read_text(encoding="utf-8")) == [], name


def test_cli_dry_run_end_to_end(tmp_path):
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "cli.py", "build", "shorts_input.yaml", "--dry-run", "--out", str(tmp_path)],
        cwd=PRODUCT_DIR, capture_output=True, text=True)
    assert result.returncode in (0, 2), result.stdout + result.stderr
    assert list(tmp_path.glob("*/plan.md"))
