"""12번 니치 리서치 테스트 — 수집·쿼터·지표·표절 차단.

이 상품에서 깨지면 안 되는 것 셋.

    1. **쿼터를 넘지 않는다.** 넘기면 그날 수집이 통째로 빠지고,
       시계열에 구멍이 나면 이 상품은 쓸모가 없어진다.
    2. **다섯 지표가 3일치 자료로 계산된다.** 며칠치가 쌓였는지는 정직하게 적는다.
    3. **개별 영상·채널을 따라 만들라고 하지 않는다.**
       노아AI 전례(CLAUDE.md §3-1)를 피하려고 입력에서부터 뺐다.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from shared import banned_phrases

BASE_DIR = Path(__file__).resolve().parents[1] / "products" / "niche-research"
FIXTURES = BASE_DIR / "data" / "fixtures"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from niche import commentary as commentary_mod                       # noqa: E402
from niche import metrics as metrics_mod                             # noqa: E402
from niche import quota as quota_mod                                 # noqa: E402
from niche import report as report_mod                               # noqa: E402
from niche.demo import seed_demo                                     # noqa: E402
from niche.store import Store, VideoRow                              # noqa: E402
from niche.youtube import FixtureClient, parse_duration              # noqa: E402


def _load(name: str) -> ModuleType:
    """`collector.py` 처럼 폴더 최상단에 있는 파일을 고유 이름으로 싣는다."""
    import importlib.util

    unique = f"niche_{name}"
    if unique in sys.modules:
        return sys.modules[unique]
    spec = importlib.util.spec_from_file_location(unique, BASE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique] = module
    spec.loader.exec_module(module)
    return module


collector = _load("collector")
analyzer = _load("analyzer")
suggest = _load("suggest")


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "niche.db")


@pytest.fixture
def seeded(tmp_path) -> Store:
    """샘플 자료 3일치가 든 창고."""
    store = Store(tmp_path / "seeded.db")
    seed_demo(store, FIXTURES, days=3, end="2026-09-15")
    return store


# ====================================================================== 쿼터
def test_units_per_keyword_matches_the_documented_costs():
    """search 100 + videos 1 + channels 1 = 102 유닛."""
    assert quota_mod.COSTS["search.list"] == 100
    assert quota_mod.UNITS_PER_KEYWORD == 102


def test_the_daily_limit_is_enforced_in_code(tmp_path):
    """부탁이 아니라 강제다. 상한을 넘는 키워드는 다음 날로 넘어간다."""
    state = quota_mod.QuotaState(path=tmp_path / "state.json", day="2026-09-17",
                                 limit=3)
    keywords = [f"키워드{index}" for index in range(10)]

    today, carried = quota_mod.plan_today(keywords, state)

    assert len(today) == 3
    assert len(carried) == 7
    assert set(today) & set(carried) == set()


def test_the_limit_never_exceeds_the_unit_budget(tmp_path):
    """상한이 80이어도 남은 유닛이 없으면 못 본다. **작은 쪽을 따른다.**"""
    state = quota_mod.QuotaState(path=tmp_path / "state.json", day="2026-09-17",
                                 limit=80)
    state.used_units = quota_mod.DAILY_UNITS - 300     # 두 개 반쯤 남았다

    assert state.remaining_keywords == 2
    today, carried = quota_mod.plan_today([f"k{n}" for n in range(10)], state)
    assert len(today) == 2 and len(carried) == 8


def test_spending_past_the_budget_raises(tmp_path):
    state = quota_mod.QuotaState(path=tmp_path / "state.json", day="2026-09-17")
    state.used_units = quota_mod.DAILY_UNITS - 50

    state.spend("videos.list")                        # 1 유닛 — 된다
    with pytest.raises(quota_mod.QuotaExceeded, match="오늘 몫"):
        state.spend("search.list")                    # 100 유닛 — 안 된다


def test_carried_keywords_come_first_the_next_day(tmp_path):
    """뒤쪽 키워드가 영원히 안 보이는 일이 없어야 한다."""
    state = quota_mod.QuotaState(path=tmp_path / "state.json", day="2026-09-17",
                                 limit=2, carried=["밀린것"])
    today, _ = quota_mod.plan_today(["첫째", "둘째", "밀린것"], state)
    assert today[0] == "밀린것"


def test_a_new_day_resets_the_units_but_keeps_the_backlog(tmp_path):
    path = tmp_path / "state.json"
    state = quota_mod.QuotaState(path=path, day="2026-09-16", used_units=9_000,
                                 done=["어제본것"], carried=["밀린것"])
    state.save()

    fresh = quota_mod.QuotaState.load(path, today="2026-09-17")
    assert fresh.used_units == 0, "날이 바뀌면 유닛은 0 부터"
    assert fresh.done == [], "'오늘 본 것' 도 비워야 합니다"
    assert fresh.carried == ["밀린것"], "밀린 것은 남아야 합니다"


def test_a_broken_state_file_does_not_stop_collection(tmp_path):
    """여기서 멈추면 그날 수집이 통째로 빠진다."""
    path = tmp_path / "state.json"
    path.write_text("{망가진 파일", encoding="utf-8")
    state = quota_mod.QuotaState.load(path, today="2026-09-17")
    assert state.used_units == 0 and state.day == "2026-09-17"


def test_the_shipped_keyword_file_fits_one_day():
    keywords = collector.read_keywords(BASE_DIR / "keywords.txt")
    assert keywords, "샘플 키워드가 있어야 합니다"
    assert len(keywords) <= quota_mod.DEFAULT_KEYWORD_LIMIT


def test_comments_and_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "keywords.txt"
    path.write_text("# 설명\n\n첫째\n둘째\n첫째\n", encoding="utf-8")
    assert collector.read_keywords(path) == ["첫째", "둘째"]


# ==================================================================== 수집기
def test_fixture_mode_collects_without_a_key(tmp_path, capsys):
    """키가 없어도 전체 흐름이 돌아야 한다 (요청 규격의 완료 기준)."""
    code = collector.main([
        "--db", str(tmp_path / "n.db"), "--state", str(tmp_path / "s.json"),
        "--keywords", str(BASE_DIR / "keywords.txt"),
        "run", "--fixture", "--date", "2026-09-15",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "샘플 자료로 돕니다" in out

    counts = Store(tmp_path / "n.db").counts()
    assert counts["videos"] > 0 and counts["channels"] > 0
    assert counts["days"] == 1


def test_collect_one_spends_the_right_units(tmp_path):
    store = Store(tmp_path / "n.db")
    state = quota_mod.QuotaState(path=tmp_path / "s.json", day="2026-09-15")
    client = FixtureClient(fixture_dir=FIXTURES)

    collector.collect_one("소상공인 세금", client, store, state, "2026-09-15")

    assert state.used_units == quota_mod.UNITS_PER_KEYWORD
    assert [call for call, _ in client.calls] == [
        "search.list", "videos.list", "channels.list"]
    assert state.done == ["소상공인 세금"]


def test_running_out_of_quota_carries_the_rest(tmp_path, capsys):
    """남은 것을 버리지 않고 다음 날로 넘긴다."""
    state_path = tmp_path / "s.json"
    quota_mod.QuotaState(path=state_path, day="2026-09-15",
                         used_units=quota_mod.DAILY_UNITS - 150).save()

    collector.main([
        "--db", str(tmp_path / "n.db"), "--state", str(state_path),
        "--keywords", str(BASE_DIR / "keywords.txt"),
        "run", "--fixture", "--date", "2026-09-15",
    ])

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["carried"], "밀린 키워드가 남아야 합니다"
    assert len(saved["done"]) < 3


def test_snapshots_append_day_by_day(tmp_path):
    """같은 날 두 번 돌려도 줄이 늘지 않는다."""
    store = Store(tmp_path / "n.db")
    state = quota_mod.QuotaState(path=tmp_path / "s.json", day="2026-09-15")
    client = FixtureClient(fixture_dir=FIXTURES)

    collector.collect_one("소상공인 세금", client, store, state, "2026-09-15")
    first = store.counts()["video_snapshots"]

    state.done = []
    collector.collect_one("소상공인 세금", client, store, state, "2026-09-15")
    assert store.counts()["video_snapshots"] == first, "같은 날인데 줄이 늘었습니다"

    state.done = []
    collector.collect_one("소상공인 세금", client, store, state, "2026-09-16")
    assert store.counts()["video_snapshots"] > first
    assert store.counts()["days"] == 2


@pytest.mark.parametrize("text,seconds", [
    ("PT4M13S", 253), ("PT58S", 58), ("PT1H2M3S", 3723), ("P1DT2H", 93600),
    ("", 0), ("이상한값", 0),
])
def test_duration_parsing(text, seconds):
    assert parse_duration(text) == seconds


def test_shorts_are_decided_by_length(tmp_path):
    """3분 이하가 쇼츠다. 길이를 못 읽으면 쇼츠로 치지 않는다."""
    rows = collector._to_rows(
        [{"id": {"videoId": "a"}, "snippet": {"channelId": "c", "title": "짧은 것",
                                              "publishedAt": "2026-09-10T00:00:00Z"}},
         {"id": {"videoId": "b"}, "snippet": {"channelId": "c", "title": "긴 것",
                                              "publishedAt": "2026-09-10T00:00:00Z"}},
         {"id": {"videoId": "c"}, "snippet": {"channelId": "c", "title": "모르는 것",
                                              "publishedAt": "2026-09-10T00:00:00Z"}}],
        [{"id": "a", "contentDetails": {"duration": "PT45S"}, "statistics": {}},
         {"id": "b", "contentDetails": {"duration": "PT12M"}, "statistics": {}},
         {"id": "c", "contentDetails": {}, "statistics": {}}])

    assert [row.is_short for row in rows] == [True, False, False]


# ==================================================================== 지표
def test_all_five_metrics_come_out_of_three_days(seeded):
    """요청 규격의 완료 기준 — 3일치 픽스처로 다섯 지표가 계산된다."""
    assert seeded.counts()["days"] == 3
    results = metrics_mod.analyze_all(seeded, today=date(2026, 9, 15))
    assert len(results) == 3

    for item in results:
        assert item.videos > 0                                   # 자료가 있다
        assert item.weekly_counts, "① 공급 증가율(주간 추이)"
        assert item.gap > 0, "② 공백 지수"
        assert item.small_channel_videos >= 0, "③ 소형 채널 성과율"
        assert item.shorts + item.longform == item.videos, "④ 쇼츠 vs 롱폼"
        assert item.growth_samples > 0, "⑤ 채널 성장률"


def test_results_are_sorted_by_gap(seeded):
    results = metrics_mod.analyze_all(seeded, today=date(2026, 9, 15))
    gaps = [item.gap for item in results]
    assert gaps == sorted(gaps, reverse=True)


def test_gap_index_is_views_over_supply():
    assert metrics_mod.gap_index(10_000, 10) == 1000.0
    assert metrics_mod.gap_index(10_000, 100) == 100.0
    assert metrics_mod.gap_index(10_000, 0) == 0.0, "영상이 없으면 0"


def test_gap_uses_the_median_not_the_mean(store):
    """영상 하나가 크게 터지면 평균은 통째로 끌려간다. 중앙값을 쓴다."""
    rows = [VideoRow(video_id=f"v{n}", channel_id="c", title=f"t{n}",
                     published_at="2026-09-10T00:00:00Z", duration_sec=600,
                     views=1_000) for n in range(9)]
    rows.append(VideoRow(video_id="big", channel_id="c", title="터진 것",
                         published_at="2026-09-10T00:00:00Z", duration_sec=600,
                         views=10_000_000))
    store.save_videos("테스트", rows, "2026-09-15")

    item = metrics_mod.analyze_keyword(
        "테스트", store.videos_for("테스트", "2026-09-15"), store=store,
        today=date(2026, 9, 15))
    assert item.median_views == 1_000, "평균이었다면 100만을 넘었을 것입니다"


def test_breakout_rate_counts_only_small_channels(store):
    """구독자 1만 이하가 구독자의 5배 넘게 본 비율."""
    store.save_channels([
        {"channel_id": "small", "title": "작은 채널", "subscribers": 1_000},
        {"channel_id": "big", "title": "큰 채널", "subscribers": 500_000},
    ], "2026-09-15")
    store.save_videos("테스트", [
        VideoRow(video_id="a", channel_id="small", title="뚫림", views=9_000,
                 published_at="2026-09-10T00:00:00Z", duration_sec=600),
        VideoRow(video_id="b", channel_id="small", title="못 뚫음", views=1_200,
                 published_at="2026-09-10T00:00:00Z", duration_sec=600),
        VideoRow(video_id="c", channel_id="big", title="큰 채널 것", views=5_000_000,
                 published_at="2026-09-10T00:00:00Z", duration_sec=600),
    ], "2026-09-15")

    item = metrics_mod.analyze_keyword(
        "테스트", store.videos_for("테스트", "2026-09-15"), store=store,
        today=date(2026, 9, 15))

    assert item.small_channel_videos == 2, "큰 채널은 세지 않습니다"
    assert item.small_channel_breakouts == 1
    assert item.breakout_rate == 50.0


def test_channel_growth_compares_a_week_apart(store):
    """7일 전 스냅샷과 견준다."""
    for offset, subscribers in ((7, 1_000), (0, 1_100)):
        day = (date(2026, 9, 15) - timedelta(days=offset)).isoformat()
        store.save_channels([{"channel_id": "c", "title": "채널",
                              "subscribers": subscribers}], day)
    store.save_videos("테스트", [
        VideoRow(video_id="a", channel_id="c", title="영상", views=500,
                 published_at="2026-09-10T00:00:00Z", duration_sec=600)],
        "2026-09-15")

    item = metrics_mod.analyze_keyword(
        "테스트", store.videos_for("테스트", "2026-09-15"), store=store,
        today=date(2026, 9, 15))
    assert item.channel_growth == pytest.approx(10.0, abs=0.01)


def test_one_day_of_data_says_so_instead_of_guessing(store):
    """자료가 모자라면 0 을 내고 **왜 못 봤는지** 적는다."""
    store.save_channels([{"channel_id": "c", "title": "채널", "subscribers": 500}],
                        "2026-09-15")
    store.save_videos("테스트", [
        VideoRow(video_id="a", channel_id="c", title="영상", views=100,
                 published_at="2026-09-14T00:00:00Z", duration_sec=60)],
        "2026-09-15")

    item = metrics_mod.analyze_keyword(
        "테스트", store.videos_for("테스트", "2026-09-15"), store=store,
        today=date(2026, 9, 15))
    assert item.channel_growth == 0
    assert any("이틀치" in note for note in item.notes)


def test_entry_friendly_needs_small_channels_breaking_through(seeded):
    results = metrics_mod.analyze_all(seeded, today=date(2026, 9, 15))
    for item in results:
        assert item.entry_friendly == (item.breakout_rate >= 20 and item.videos > 0)


# ================================================================== 표절 차단
def test_no_module_reads_video_titles_into_the_model():
    """모델에게 주는 글에 영상 제목·채널명이 섞이면 안 된다."""
    facts = suggest._facts(metrics_mod.KeywordMetrics(
        keyword="테스트", videos=10, median_views=5_000, gap=500.0,
        breakout_rate=30.0, shorts=4, longform=6))
    for forbidden in ("title", "제목", "채널명", "channel_title", "videoId"):
        assert forbidden not in facts


@pytest.mark.parametrize("line", [
    "이 영상을 따라 만드세요",
    "터진 영상을 그대로 만드는 것이 빠릅니다",
    "이 채널처럼 구성해 보세요",
    "인기 영상을 리메이크하세요",
])
def test_copycat_wording_is_detected(line):
    assert commentary_mod.copycat_hits(line)


def test_normal_commentary_passes():
    assert commentary_mod.copycat_hits(
        "공백 지수가 높아 만드는 사람이 적은 편으로 보입니다.") == []


def test_a_copycat_suggestion_is_replaced(seeded):
    """모델이 표절을 권하면 그 줄을 **버리고** 규칙 문장으로 바꾼다."""
    item = metrics_mod.analyze_all(seeded, today=date(2026, 9, 15))[0]

    def bad_model(system, user, **kwargs):
        return {"ideas": [
            {"format": "터진 영상 따라 만들기", "why": "이 채널처럼 하면 됩니다",
             "first_episode": "인기 영상을 그대로 만드세요", "length": "쇼츠"},
        ]}

    ideas, warnings = suggest.ideas_for(item, bad_model, "test")
    assert warnings, "걸렀다는 사실을 알려야 합니다"
    text = json.dumps(ideas, ensure_ascii=False)
    assert commentary_mod.copycat_hits(text) == []


def test_a_banned_phrase_in_an_idea_is_replaced(seeded):
    item = metrics_mod.analyze_all(seeded, today=date(2026, 9, 15))[0]

    def greedy(system, user, **kwargs):
        return {"ideas": [{"format": "수익 보장 채널", "why": "무조건 됩니다",
                           "first_episode": "시작하세요", "length": "롱폼"}]}

    ideas, warnings = suggest.ideas_for(item, greedy, "test")
    assert warnings
    assert banned_phrases.check(json.dumps(ideas, ensure_ascii=False)) == []


def test_commentary_replaces_copycat_lines(seeded):
    results = metrics_mod.analyze_all(seeded, today=date(2026, 9, 15))

    def bad_model(system, user, **kwargs):
        return {"lines": ["1위 영상을 따라 만드세요", "공백 지수가 높습니다",
                          "베끼면 빠릅니다", "쇼츠가 많습니다", "괜찮습니다"]}

    lines = commentary_mod.commentary_for(results, 3, bad_model, "test")
    assert len(lines) == 5
    assert commentary_mod.copycat_hits(" ".join(lines)) == []


def test_the_prompts_forbid_copying():
    for prompt in (commentary_mod.COMMENTARY_SYSTEM, suggest.SUGGEST_SYSTEM):
        assert "따라 만들" in prompt
        assert "예측" in prompt


# ==================================================================== 보고서
def test_report_files_are_written(tmp_path, seeded):
    results = metrics_mod.analyze_all(seeded, today=date(2026, 9, 15))
    commentary = commentary_mod.offline_commentary(results, 3)

    md_path = report_mod.write_markdown(results, tmp_path, 3, commentary=commentary)
    html_path = report_mod.write_html(results, tmp_path, 3, commentary=commentary)

    assert md_path.is_file() and html_path.is_file()
    text = md_path.read_text(encoding="utf-8")
    assert "공백 지수" in text and "소형 채널 성과율" in text
    assert banned_phrases.check(text) == []
    # 보고서 본문에는 "따라 만들라고 하지 않습니다" 같은 **부정문**이 들어간다.
    # 그래서 문서 전체가 아니라 모델이 쓴 해설 줄만 검사한다.
    for line in commentary:
        assert commentary_mod.copycat_hits(line) == [], line


def test_the_report_never_lists_video_titles(tmp_path, seeded):
    """목록을 보여 주는 순간 '이걸 따라 만들라' 는 도구가 된다."""
    results = metrics_mod.analyze_all(seeded, today=date(2026, 9, 15))
    md_path = report_mod.write_markdown(results, tmp_path, 3)
    html_path = report_mod.write_html(results, tmp_path, 3)

    for path in (md_path, html_path):
        text = path.read_text(encoding="utf-8")
        assert "관련 영상" not in text, f"{path.name} 에 영상 제목이 들어갔습니다"
        assert "채널 1" not in text, f"{path.name} 에 채널 이름이 들어갔습니다"


def test_the_html_says_why_charts_are_missing(tmp_path, seeded):
    """인터넷이 없으면 빈 상자만 남기지 말고 이유를 적는다."""
    results = metrics_mod.analyze_all(seeded, today=date(2026, 9, 15))
    html = report_mod.write_html(results, tmp_path, 3).read_text(encoding="utf-8")
    assert "차트를 못 받아왔습니다" in html
    assert report_mod.CHART_JS in html


def test_a_short_history_is_flagged_in_the_report(tmp_path, seeded):
    results = metrics_mod.analyze_all(seeded, today=date(2026, 9, 15))
    text = report_mod.write_markdown(results, tmp_path, 1).read_text(encoding="utf-8")
    assert "1일치뿐입니다" in text


def test_demo_reports_say_the_numbers_are_made_up(tmp_path, seeded):
    results = metrics_mod.analyze_all(seeded, today=date(2026, 9, 15))
    text = report_mod.write_markdown(results, tmp_path, 3, demo=True
                                     ).read_text(encoding="utf-8")
    assert "샘플 자료로 만든 보고서" in text and "지어낸" in text


# ======================================================================= CLI
def test_analyzer_runs_end_to_end(tmp_path, capsys):
    code = analyzer.main(["--db", str(tmp_path / "n.db"), "run", "--demo",
                          "--dry-run", "--out", str(tmp_path / "out")])
    assert code == 0
    assert (tmp_path / "out" / "report.html").is_file()
    assert list((tmp_path / "out").glob("report_*.md"))
    assert "샘플 자료" in capsys.readouterr().out


def test_analyzer_without_data_says_what_to_do(tmp_path, capsys):
    code = analyzer.main(["--db", str(tmp_path / "empty.db"), "run"])
    assert code == 1
    assert "collector.py run" in capsys.readouterr().err


def test_suggest_runs_end_to_end(tmp_path, capsys):
    code = suggest.main(["--db", str(tmp_path / "n.db"), "run", "--demo",
                         "--dry-run", "--out", str(tmp_path / "out"), "--json"])
    assert code == 0
    ideas = list((tmp_path / "out").glob("ideas_*.md"))
    assert ideas
    text = ideas[0].read_text(encoding="utf-8")
    assert banned_phrases.check(text) == []

    payload = json.loads((tmp_path / "out" / "ideas.json").read_text(encoding="utf-8"))
    assert all(len(row["ideas"]) == suggest.IDEAS_PER_KEYWORD for row in payload)
    # 아이디어 본문에는 표절을 부추기는 말이 없어야 한다 (문서의 부정문은 뺀다)
    for row in payload:
        for idea in row["ideas"]:
            assert commentary_mod.copycat_hits(
                " ".join(str(value) for value in idea.values())) == []


def test_collector_status_reports_the_days(tmp_path, capsys):
    store = Store(tmp_path / "n.db")
    seed_demo(store, FIXTURES, days=3, end="2026-09-15")
    collector.main(["--db", str(tmp_path / "n.db"),
                    "--state", str(tmp_path / "s.json"), "status"])
    out = capsys.readouterr().out
    assert "3일치" in out


def test_collector_without_a_key_explains_the_fixture_mode(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    code = collector.main(["--db", str(tmp_path / "n.db"),
                           "--state", str(tmp_path / "s.json"),
                           "--keywords", str(BASE_DIR / "keywords.txt"), "run"])
    assert code == 1
    assert "--fixture" in capsys.readouterr().err


# ==================================================================== 문서
def test_readme_has_the_noah_ai_section():
    """이 상품이 무엇을 하지 않는지 밝히는 절. 요청 규격의 완료 기준."""
    text = (BASE_DIR / "README.md").read_text(encoding="utf-8")
    assert "노아AI" in text
    assert "하지 않" in text
    assert banned_phrases.check(text) == []


def test_readme_explains_the_time_series_problem():
    text = (BASE_DIR / "README.md").read_text(encoding="utf-8")
    assert "시계열" in text
    assert "매일" in text


def test_product_manuals_are_detailed_and_clean():
    for name in ("admin.md", "client.md"):
        path = BASE_DIR / "docs" / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert len(text) > 3500, f"{name} 이 너무 짧습니다"
        assert banned_phrases.check(text) == []


def test_env_example_has_no_real_keys():
    text = (BASE_DIR / ".env.example").read_text(encoding="utf-8")
    assert "YOUTUBE_API_KEY=" in text
    for line in text.splitlines():
        if line.startswith(("YOUTUBE_API_KEY=", "ANTHROPIC_API_KEY=")):
            assert line.split("=", 1)[1].strip() == ""
