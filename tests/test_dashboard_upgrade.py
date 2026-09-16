"""대시보드 업그레이드 테스트 — 오늘 볼 것 · 매출 그래프 · 검색 · 실행 이력.

프로그램이 여덟 개가 되면서 생긴 문제들을 다룬다.

    오늘 볼 것   숫자 여섯 개만으로는 지금 뭘 해야 하는지 안 보였다.
                 **할 일이 없으면 아무것도 안 띄우는 것**까지가 규칙이다.
                 늘 떠 있는 경고는 곧 안 보게 되기 때문이다.
    매출 그래프  인터넷 없이도 열려야 하므로 라이브러리 없이 SVG 를 직접 그린다.
    검색         매뉴얼 18개·FAQ 90개를 기억해서 찾아 들어가야 했다.
    실행 이력    홈에 최근 8건만 있었다. 실패한 것만 모아 보는 길이 없었다.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from core import auth
from core.db import Database
from core.health import EXPIRY_WINDOW_DAYS, Task, checklist
from core.overview import collect as collect_config, env_rows
from core.registry import Registry
from core.search import GROUPS, MAX_PER_GROUP, search
from dashboard.app import create_app
from dashboard.charts import monthly_chart, program_chart
from shared.config import ROOT_DIR

DOCS = ROOT_DIR / "docs"


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(tmp_path / "up.db")


@pytest.fixture
def registry() -> Registry:
    return Registry()


@pytest.fixture
def client(tmp_path) -> TestClient:
    client = TestClient(create_app(tmp_path / "web.db"))
    client.post("/login", data={"code": auth.access_code()})
    return client


def _buyer(db: Database, program: str = "n8n-gen", price: int = 550000,
           expires: str = "", retainer: int = 0) -> int:
    member = db.add_member("고객 (예시)", "sample@example.com")
    return db.add_license(member, program, "기본", price,
                          expires_at=expires, retainer=retainer)


# ------------------------------------------------------------------ 매출 집계
def test_monthly_revenue_keeps_empty_months(db):
    """매출이 0인 달을 빼면 추이가 왜곡된다. 자리는 있어야 한다."""
    _buyer(db)
    series = db.monthly_revenue(months=12)
    assert len(series) == 12
    assert sum(1 for row in series if row["amount"] > 0) == 1
    assert series[-1]["month"] == date.today().strftime("%Y-%m")


def test_monthly_revenue_excludes_refunds(db):
    kept = _buyer(db, price=100000)
    refunded = _buyer(db, price=999999)
    db.set_license_status(refunded, "refunded")
    assert sum(row["amount"] for row in db.monthly_revenue()) == 100000
    assert kept


def test_monthly_revenue_keeps_expired_licenses(db):
    """만료는 돈을 돌려준 것이 아니다. 매출에 남아야 한다."""
    license_id = _buyer(db, price=100000)
    db.set_license_status(license_id, "expired")
    assert sum(row["amount"] for row in db.monthly_revenue()) == 100000


def test_revenue_by_program_is_sorted_high_to_low(db):
    _buyer(db, "n8n-gen", 550000)
    _buyer(db, "kmong-copy", 120000)
    _buyer(db, "groupbuy-ledger", 250000)
    rows = db.revenue_by_program()
    assert [row["program_id"] for row in rows] == [
        "n8n-gen", "groupbuy-ledger", "kmong-copy"]


def test_last_run_per_program_takes_the_latest(db):
    first = db.start_run("n8n-gen", "dry")
    db.finish_run(first, "failed", 1, "", "")
    second = db.start_run("n8n-gen", "dry")
    db.finish_run(second, "success", 0, "", "")
    assert db.last_run_per_program()["n8n-gen"]["id"] == second


# ------------------------------------------------------------------ 그래프
def test_monthly_chart_scales_bars_to_the_tallest(db):
    _buyer(db, price=100000)
    chart = monthly_chart(db.monthly_revenue(12))
    assert len(chart.bars) == 12
    assert not chart.empty
    tallest = max(chart.bars, key=lambda bar: bar.height)
    assert tallest.value == 100000
    assert tallest.height < chart.baseline, "막대가 천장에 닿으면 안 됩니다"


def test_monthly_chart_marks_the_current_month(db):
    chart = monthly_chart(db.monthly_revenue(12))
    assert chart.bars[-1].highlight
    assert not any(bar.highlight for bar in chart.bars[:-1])


def test_monthly_chart_says_it_is_empty_without_sales(db):
    chart = monthly_chart(db.monthly_revenue(12))
    assert chart.empty and chart.total == 0
    assert len(chart.bars) == 12, "빈 달도 자리는 그린다"


def test_bars_never_stick_out_of_the_canvas(db):
    _buyer(db, price=9_999_999)
    chart = monthly_chart(db.monthly_revenue(12))
    for bar in chart.bars:
        assert bar.y >= 0
        assert bar.x + bar.width <= chart.width + 0.01
        assert bar.y + bar.height <= chart.baseline + 0.01


def test_program_chart_leaves_room_for_the_amount_label(db):
    _buyer(db, "n8n-gen", 550000)
    chart = program_chart(db.revenue_by_program(), {"n8n-gen": "n8n 생성기"})
    bar = chart.bars[0]
    assert bar.label == "n8n 생성기"
    assert bar.x + bar.width <= chart.width - 100, "금액을 적을 자리가 남아야 합니다"


def test_program_chart_skips_programs_with_no_sales(db):
    _buyer(db, "n8n-gen", 550000)
    _buyer(db, "kmong-copy", 0)
    chart = program_chart(db.revenue_by_program(), {})
    assert [bar.value for bar in chart.bars] == [550000]


# ------------------------------------------------------------- 오늘 볼 것
def test_nothing_to_show_when_everything_is_fine(db, registry):
    """늘 떠 있는 경고는 곧 안 보게 된다. 할 일이 없으면 비워 둔다."""
    for program in registry.programs:
        run = db.start_run(program.id, "dry")
        db.finish_run(run, "success", 0, "", "")
    assert checklist(db, registry, api_key_set=True, default_code=False) == []


def test_failed_runs_come_first(db, registry):
    run = db.start_run("n8n-gen", "dry")
    db.finish_run(run, "failed", 1, "오류", "")
    tasks = checklist(db, registry, api_key_set=True, default_code=False)
    assert tasks[0].level == "bad"
    assert "실패한 실행" in tasks[0].title
    assert tasks[0].href == "/runs?status=failed"


def test_warning_runs_are_flagged_as_needing_a_person(db, registry):
    run = db.start_run("n8n-gen", "dry")
    db.finish_run(run, "warning", 2, "", "")
    titles = [t.title for t in checklist(db, registry, api_key_set=True)]
    assert any("손볼 곳" in title for title in titles)


def test_overdue_licenses_are_reported_as_serious(db, registry):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _buyer(db, expires=yesterday)
    tasks = checklist(db, registry, api_key_set=True)
    overdue = [t for t in tasks if "기한이 지난" in t.title]
    assert overdue and overdue[0].level == "bad"
    assert "매출이 부풀어" in overdue[0].detail


def test_licenses_ending_soon_are_a_warning(db, registry):
    soon = (date.today() + timedelta(days=EXPIRY_WINDOW_DAYS - 2)).isoformat()
    _buyer(db, expires=soon)
    tasks = [t for t in checklist(db, registry, api_key_set=True)
             if "안에 끝나는" in t.title]
    assert tasks and tasks[0].level == "warn"


def test_licenses_ending_far_out_are_not_nagged(db, registry):
    later = (date.today() + timedelta(days=EXPIRY_WINDOW_DAYS + 40)).isoformat()
    _buyer(db, expires=later)
    assert not [t for t in checklist(db, registry, api_key_set=True)
                if "이용권" in t.title]


def test_never_run_programs_are_listed(db, registry):
    tasks = [t for t in checklist(db, registry, api_key_set=True)
             if "한 번도" in t.title]
    assert tasks and tasks[0].level == "info"
    assert "비용이 들지 않습니다" in tasks[0].detail


def test_default_access_code_is_flagged(db, registry):
    titles = [t.title for t in checklist(db, registry, api_key_set=True,
                                         default_code=True)]
    assert any("접속 코드" in title for title in titles)


def test_missing_api_key_is_only_informational(db, registry):
    tasks = [t for t in checklist(db, registry, api_key_set=False)
             if "API 키" in t.title]
    assert tasks and tasks[0].level == "info", "막는 것이 아니라 알리는 것입니다"


def test_tasks_are_sorted_by_severity(db, registry):
    failed = db.start_run("n8n-gen", "dry")
    db.finish_run(failed, "failed", 1, "", "")
    warned = db.start_run("kmong-copy", "dry")
    db.finish_run(warned, "warning", 2, "", "")
    tasks = checklist(db, registry, api_key_set=False, default_code=True)
    assert [task.order for task in tasks] == sorted(task.order for task in tasks)


def test_task_with_an_unknown_level_sorts_last():
    assert Task("몰라", "x", "y").order > Task("info", "x", "y").order


# ------------------------------------------------------------------ 검색
def test_search_needs_two_letters(db, registry):
    assert search("", registry, db, DOCS) == {}
    assert search("n", registry, db, DOCS) == {}


def test_search_finds_a_program_by_name(db, registry):
    results = search("퍼널", registry, db, DOCS)
    titles = [hit.title for hit in results.get("프로그램", [])]
    assert any("퍼널 빌더" in title for title in titles)


def test_search_reaches_into_manual_bodies(db, registry):
    """매뉴얼 본문까지 찾아야 쓸모가 있다. 제목만 훑으면 대부분 놓친다."""
    results = search("이탈률", registry, db, DOCS)
    assert results.get("매뉴얼"), "매뉴얼 본문에서 찾지 못했습니다"
    assert any(hit.snippet for hit in results["매뉴얼"])


def test_search_finds_faq_and_steps(db, registry):
    results = search("손익분기", registry, db, DOCS)
    subtitles = [hit.subtitle for hit in results.get("프로그램", [])]
    assert any(sub in ("자주 묻는 질문", "이용 순서") for sub in subtitles)


def test_search_finds_editable_files(db, registry):
    results = search("mapping.yaml", registry, db, DOCS)
    assert results.get("설정·파일")


def test_search_finds_members(db, registry):
    db.add_member("박민준 (예시)", "minjun@example.com", source="크몽")
    results = search("민준", registry, db, DOCS)
    assert results.get("고객")
    assert results["고객"][0].href.startswith("/members/")


def test_search_ranks_title_matches_above_body_matches(db, registry):
    results = search("수익 시뮬레이터", registry, db, DOCS)
    hits = results.get("프로그램", [])
    assert hits and hits[0].score >= 50


def test_search_caps_each_group(db, registry):
    for index in range(MAX_PER_GROUP + 5):
        db.add_member(f"공구 고객 {index}", f"g{index}@example.com")
    results = search("공구", registry, db, DOCS)
    for group, hits in results.items():
        assert len(hits) <= MAX_PER_GROUP, group


def test_search_groups_come_in_a_fixed_order(db, registry):
    results = search("크몽", registry, db, DOCS)
    assert list(results) == [g for g in GROUPS if g in results]


def test_search_returns_nothing_for_gibberish(db, registry):
    assert search("쀍쀍쀍쀍", registry, db, DOCS) == {}


# --------------------------------------------------------------- 실행 이력
def test_runs_can_be_filtered_by_status(db):
    failed = db.start_run("n8n-gen", "dry")
    db.finish_run(failed, "failed", 1, "", "")
    ok = db.start_run("n8n-gen", "real")
    db.finish_run(ok, "success", 0, "", "")

    assert [row["id"] for row in db.search_runs(status="failed")] == [failed]
    assert [row["id"] for row in db.search_runs(mode="real")] == [ok]
    assert db.count_runs(status="failed") == 1
    assert db.count_runs() == 2


def test_runs_paginate_newest_first(db):
    made = [db.start_run("n8n-gen", "dry") for _ in range(5)]
    first_page = db.search_runs(limit=2, offset=0)
    second_page = db.search_runs(limit=2, offset=2)
    assert [row["id"] for row in first_page] == made[::-1][:2]
    assert [row["id"] for row in second_page] == made[::-1][2:4]


# ------------------------------------------------------------------ 화면
def test_home_shows_the_checklist(client):
    body = client.get("/").text
    assert "오늘 볼 것" in body


def test_home_hides_duplicate_banners(client):
    """같은 말을 띠로도 목록으로도 보여 주면 둘 다 안 읽게 된다."""
    home = client.get("/").text
    elsewhere = client.get("/members").text
    assert "접속 코드가 기본값 그대로입니다." not in home
    assert "접속 코드가 기본값 그대로입니다." in elsewhere


def test_home_draws_charts_without_any_cdn(client, tmp_path):
    """인터넷이 없어도 열려야 한다. 밖에서 받아 오는 것이 없어야 한다."""
    app_client = TestClient(create_app(tmp_path / "chart.db"))
    app_client.post("/login", data={"code": auth.access_code()})
    database = Database(tmp_path / "chart.db")
    _buyer(database, price=550000)

    body = app_client.get("/").text
    assert "<svg" in body and 'class="bars"' in body
    assert "cdnjs" not in body and "cdn.jsdelivr" not in body
    assert "<script src=" not in body


def test_home_shows_the_last_run_on_each_card(client, tmp_path):
    body = client.get("/").text
    assert "아직 한 번도 안 돌렸습니다" in body


def test_search_page_renders_results(client):
    body = client.get("/search", params={"q": "이탈률"}).text
    assert "찾았습니다" in body


def test_search_page_says_when_it_finds_nothing(client):
    body = client.get("/search", params={"q": "쀍쀍쀍쀍"}).text
    assert "찾지 못했습니다" in body


def test_search_page_without_a_query_offers_examples(client):
    body = client.get("/search").text
    assert "두 글자 이상" in body


def test_runs_page_filters_and_paginates(client, tmp_path):
    response = client.get("/runs", params={"status": "failed"})
    assert response.status_code == 200
    assert "실행 이력" in response.text


def test_runs_page_is_reachable_from_the_sidebar(client):
    assert 'href="/runs"' in client.get("/").text


def test_search_box_sits_in_the_sidebar(client):
    body = client.get("/").text
    assert 'id="nav-search"' in body
    assert 'action="/search"' in body


def test_sidebar_collapses_on_a_phone(client):
    body = client.get("/").text
    assert 'id="side-toggle"' in body
    assert "max-width: 860px" in client.get("/static/style.css").text


def test_new_pages_need_the_access_code(tmp_path):
    guest = TestClient(create_app(tmp_path / "guest.db"), follow_redirects=False)
    for path in ("/runs", "/search?q=크몽"):
        assert guest.get(path).status_code == 303


# ------------------------------------------------------- 설정 한눈에 (/config)
# 프로그램이 아홉 개가 되니 "그 값을 어디서 바꿨더라" 가 잦아졌다.
# 한 장에 모아 보여 주되, **비밀값은 있다/없다만** 보여 주는 것이 규칙이다.
def test_config_collects_every_program(registry, db):
    configs = collect_config(registry, db)
    assert len(configs) == len(registry.programs)
    assert [c.number for c in configs] == sorted(c.number for c in configs)
    # 매니페스트가 가리키는 파일이 실제로 있어야 한다
    for cfg in configs:
        assert cfg.missing == [], f"{cfg.id}: {cfg.missing}"


def test_config_hides_secret_values(registry, db):
    program = next(c for c in collect_config(registry, db) if c.id == "notion-template-kit")
    token = next(row for row in program.settings if row.key == "NOTION_TOKEN")
    assert token.secret and token.shown == "비어 있음"

    db.set_program_setting("notion-template-kit", "NOTION_TOKEN", "secret_실제값123")
    program = next(c for c in collect_config(registry, db) if c.id == "notion-template-kit")
    token = next(row for row in program.settings if row.key == "NOTION_TOKEN")
    assert token.shown == "설정됨", "토큰은 화면에 그대로 싣지 않는다"
    assert "실제값" not in token.shown


def test_config_marks_values_changed_from_default(registry, db):
    db.set_program_setting("notion-template-kit", "SAMPLE_ROWS", "9")
    program = next(c for c in collect_config(registry, db) if c.id == "notion-template-kit")
    rows = {row.key: row for row in program.settings}
    assert rows["SAMPLE_ROWS"].changed and rows["SAMPLE_ROWS"].shown == "9"
    assert not rows["AI_LABEL"].changed
    assert program.changed_count == 1


def test_config_shows_booleans_in_korean(registry, db):
    program = next(c for c in collect_config(registry, db) if c.id == "notion-template-kit")
    label = next(row for row in program.settings if row.key == "AI_LABEL")
    assert label.shown == "켬", "True 라고 적어 두면 무슨 뜻인지 모른다"


def test_env_rows_never_carry_the_value():
    rows = env_rows({"ANTHROPIC_API_KEY": "sk-ant-비밀", "NOTION_TOKEN": "  "})
    by_key = {row.key: row for row in rows}
    assert by_key["ANTHROPIC_API_KEY"].present
    assert not by_key["NOTION_TOKEN"].present, "공백만 있으면 없는 것으로 본다"
    assert all("sk-ant" not in str(row.__dict__) for row in rows)


def test_config_page_lists_manuals_and_files(client):
    text = client.get("/config").text
    assert "설정 한눈에" in text
    assert "/programs/notion-template-kit/manual/client" in text
    assert "/programs/notion-template-kit/file?path=request.yaml" in text
    assert "NOTION_TOKEN" in text


def test_config_page_is_behind_the_access_code(tmp_path):
    stranger = TestClient(create_app(tmp_path / "gate.db"), follow_redirects=False)
    assert stranger.get("/config").status_code == 303


def test_config_is_in_the_sidebar(client):
    assert 'href="/config"' in client.get("/").text
