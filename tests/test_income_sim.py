"""products/income-sim 테스트.

가장 중요한 두 가지를 먼저 본다.

    손익분기   월 손익분기와 누적 손익분기를 섞으면 안 된다.
               매달 남는데도 초기 투자를 못 갚은 상태가 흔하기 때문이다.
    이탈률     고객이 쌓이는 계산은 한 달만 틀려도 12개월 뒤 크게 벌어진다.
               직접 손으로 센 값과 맞춰 본다.

그리고 대시보드의 자바스크립트가 파이썬과 **같은 숫자**를 내는지
node 로 실제로 돌려서 확인한다. 계산식을 두 곳에 적지 않고 한 곳에만 둔
설계가 실제로 지켜지는지 보는 검사다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import load_product_cli
from income_sim.compare import compare_models
from income_sim.dashboard import CHART_JS, build_dashboard, model_payload
from income_sim.engine import DISCLAIMER, simulate
from income_sim.expr import ExpressionError, check_expression, evaluate
from income_sim.montecarlo import percentile, run_montecarlo
from income_sim.report import banner, projection_table, sources_table, width
from income_sim.schema import MODELS_DIR, MONTHS, ModelSpec, load_all
from shared import banned_phrases

sim_cli = load_product_cli("income-sim")
BASE_DIR = Path(sim_cli.BASE_DIR)

#: 사양에 적힌 모델 8종.
REQUIRED = ("youtube_long", "youtube_shorts", "youtube_shopping", "coupang_partners",
            "groupbuy", "ebook_course", "agency_retainer", "saas_subscription")

NODE = shutil.which("node") or "/opt/node22/bin/node"


@pytest.fixture(scope="session")
def models() -> dict[str, ModelSpec]:
    return load_all()


def _spec(models, key) -> ModelSpec:
    return models[key]


def _toy(**overrides) -> ModelSpec:
    """테스트용 최소 모델. 계산 규칙만 보고 싶을 때 쓴다."""
    data = {
        "id": "toy", "number": 99, "name": "시험용",
        "params": [
            {"key": "revenue_per_month", "label": "월 매출", "default": 100,
             "maximum": 10000, "step": 1, "source": "테스트용 값입니다"},
            {"key": "monthly_cost", "label": "월 비용", "default": 40,
             "maximum": 10000, "step": 1, "source": "테스트용 값입니다"},
            {"key": "initial_cost", "label": "초기 투자", "default": 0,
             "maximum": 100000, "step": 1, "source": "테스트용 값입니다"},
            {"key": "hours", "label": "월 시간", "default": 10, "kind": "hours",
             "maximum": 500, "step": 1, "source": "테스트용 값입니다"},
        ],
        "formulas": {"revenue": "revenue_per_month", "cost": "monthly_cost",
                     "hours": "hours"},
    }
    data.update(overrides)
    return ModelSpec(**data)


# ------------------------------------------------------------------ 계산식
def test_expression_does_arithmetic():
    assert evaluate("a / 1000 * b", {"a": 1000, "b": 2500}) == 2500
    assert evaluate("max(0, a - b)", {"a": 1, "b": 5}) == 0
    assert evaluate("min(a, b) * 2", {"a": 3, "b": 9}) == 6


def test_expression_divides_by_zero_as_zero():
    """자바스크립트는 Infinity 를 내놓는다. 맞춰 두지 않으면 두 계산이 갈린다."""
    assert evaluate("a / b", {"a": 5, "b": 0}) == 0


@pytest.mark.parametrize("source", [
    '__import__("os").system("ls")', 'open("/etc/passwd")', "a if b else c",
    "a and b", "[a, b]", "a.b", "a > b",
])
def test_expression_refuses_anything_but_arithmetic(source):
    """설정 파일에 적힌 글자를 그대로 실행하면 안 된다."""
    with pytest.raises(ExpressionError):
        evaluate(source, {"a": 1, "b": 2, "c": 3})


def test_expression_reports_missing_values():
    with pytest.raises(ExpressionError, match="찾지 못했습니다"):
        evaluate("a + missing", {"a": 1})


def test_check_expression_lists_names():
    assert check_expression("max(a, b) + c") == {"a", "b", "c"}


# ------------------------------------------------------------------ 모델 정의
def test_all_eight_models_exist(models):
    """완료 기준: 모델 8종."""
    assert set(models) == set(REQUIRED)
    assert sorted(spec.number for spec in models.values()) == list(range(1, 9))


def test_every_default_has_a_source(models):
    """근거 없는 기본값 금지. 이 검사가 그 규칙을 지킨다."""
    for spec in models.values():
        for param in spec.params:
            assert len(param.source.strip()) >= 8, f"{spec.id}.{param.key}"


def test_model_rejects_a_default_without_a_source():
    with pytest.raises(ValidationError, match="근거"):
        ModelSpec(**{
            "id": "x", "number": 1, "name": "x",
            "params": [{"key": "a", "label": "a", "default": 1,
                        "maximum": 10, "source": "짧음"}],
            "formulas": {"revenue": "a", "cost": "a", "hours": "a"},
        })


def test_model_rejects_a_formula_naming_something_unknown():
    with pytest.raises(ValidationError, match="모르는 이름"):
        ModelSpec(**{
            "id": "x", "number": 1, "name": "x",
            "params": [{"key": "a", "label": "a", "default": 1, "maximum": 10,
                        "source": "테스트용 값입니다"}],
            "formulas": {"revenue": "a * ghost", "cost": "a", "hours": "a"},
        })


def test_model_rejects_a_default_outside_its_range():
    with pytest.raises(ValidationError, match="밖입니다"):
        ModelSpec(**{
            "id": "x", "number": 1, "name": "x",
            "params": [{"key": "a", "label": "a", "default": 99, "maximum": 10,
                        "source": "테스트용 값입니다"}],
            "formulas": {"revenue": "a", "cost": "a", "hours": "a"},
        })


def test_rates_must_be_written_as_fractions():
    with pytest.raises(ValidationError, match="0~1"):
        ModelSpec(**{
            "id": "x", "number": 1, "name": "x",
            "params": [{"key": "a", "label": "a", "default": 20, "kind": "rate",
                        "maximum": 100, "source": "테스트용 값입니다"}],
            "formulas": {"revenue": "a", "cost": "a", "hours": "a"},
        })


def test_model_files_carry_source_comments():
    """YAML 맨 위에 기본값 근거를 적어 둔다. 파일만 열어도 보이게."""
    for path in MODELS_DIR.glob("*.yaml"):
        head = path.read_text(encoding="utf-8")[:900]
        assert "근거" in head, f"{path.name} 에 근거 주석이 없습니다"


def test_overrides_reject_unknown_names(models):
    with pytest.raises(ValueError, match="없는 값입니다"):
        _spec(models, "groupbuy").with_overrides({"없는값": 1})


def test_overrides_reject_a_rate_given_as_a_percent(models):
    """20% 를 20 으로 넣으면 결과가 100배 틀어진다. 막고 알려 준다."""
    with pytest.raises(ValueError, match="0~1"):
        _spec(models, "groupbuy").with_overrides({"margin_rate": 20})


# ------------------------------------------------------------------ 12개월 계산
@pytest.mark.parametrize("model_id", REQUIRED)
def test_every_model_runs_twelve_months(models, model_id):
    """완료 기준: 8개 모델 run 성공."""
    projection = simulate(_spec(models, model_id))
    assert len(projection.rows) == MONTHS
    assert projection.rows[0].month == 1 and projection.rows[-1].month == 12
    for row in projection.rows:
        assert row.profit == pytest.approx(row.revenue - row.cost)


def test_cumulative_is_the_running_sum_minus_initial_cost():
    projection = simulate(_toy(), {"revenue_per_month": 100, "monthly_cost": 40,
                                   "initial_cost": 300})
    assert projection.rows[0].cumulative == pytest.approx(-300 + 60)
    assert projection.rows[4].cumulative == pytest.approx(-300 + 60 * 5)
    assert projection.net_after_initial == pytest.approx(60 * 12 - 300)


# ------------------------------------------------------------------ 손익분기
def test_monthly_and_cumulative_breakeven_are_not_the_same_thing():
    """매달 남는데도 초기 투자를 아직 못 갚은 상태. 가장 흔한 오해다."""
    projection = simulate(_toy(), {"revenue_per_month": 100, "monthly_cost": 40,
                                   "initial_cost": 300})
    assert projection.monthly_breakeven == 1, "1개월차부터 그달은 남는다"
    assert projection.cumulative_breakeven == 6, "300원을 갚으려면 60원씩 6달"


def test_breakeven_is_none_when_it_never_happens():
    projection = simulate(_toy(), {"revenue_per_month": 10, "monthly_cost": 40})
    assert projection.monthly_breakeven is None
    assert projection.cumulative_breakeven is None


def test_breakeven_needs_to_pass_zero_not_merely_reach_it():
    """딱 0 은 아직 갚은 것이 아니다. 12개월째에 정확히 0이 되는 경우."""
    projection = simulate(_toy(), {"revenue_per_month": 100, "monthly_cost": 40,
                                   "initial_cost": 720})
    assert projection.rows[-1].cumulative == pytest.approx(0)
    assert projection.cumulative_breakeven is None


def test_breakeven_with_no_initial_cost_is_the_first_profitable_month():
    projection = simulate(_toy(), {"revenue_per_month": 100, "monthly_cost": 40,
                                   "initial_cost": 0})
    assert projection.cumulative_breakeven == 1


def test_hourly_is_profit_over_hours():
    projection = simulate(_toy(), {"revenue_per_month": 100, "monthly_cost": 40,
                                   "hours": 10})
    assert projection.hourly == pytest.approx(60 * 12 / (10 * 12))


def test_hourly_is_none_when_no_time_is_spent():
    assert simulate(_toy(), {"hours": 0}).hourly is None


# ------------------------------------------------------------- 이탈률 누적
def _churn_model() -> ModelSpec:
    return ModelSpec(**{
        "id": "churn", "number": 98, "name": "이탈 시험",
        "params": [
            {"key": "joiners", "label": "월 신규", "default": 10,
             "maximum": 1000, "source": "테스트용 값입니다"},
            {"key": "churn_rate", "label": "이탈률", "default": 0.1, "kind": "rate",
             "maximum": 1, "step": 0.01, "source": "테스트용 값입니다"},
            {"key": "fee", "label": "구독료", "default": 1000,
             "maximum": 100000, "source": "테스트용 값입니다"},
        ],
        "state": [{"key": "users", "label": "고객", "initial": "joiners",
                   "next": "prev * (1 - churn_rate) + joiners"}],
        "formulas": {"revenue": "users * fee", "cost": "0", "hours": "0"},
    })


def test_churn_accumulates_month_by_month():
    """손으로 센 값과 맞춘다. 10 → 19 → 27.1 → 34.39 …"""
    projection = simulate(_churn_model())
    users = [row.state["users"] for row in projection.rows]
    assert users[0] == pytest.approx(10)
    assert users[1] == pytest.approx(10 * 0.9 + 10)         # 19
    assert users[2] == pytest.approx(19 * 0.9 + 10)         # 27.1
    assert users[3] == pytest.approx(27.1 * 0.9 + 10)       # 34.39


def test_churn_settles_at_joiners_over_churn_rate():
    """쌓이는 계산의 천장은 '월 신규 ÷ 이탈률' 이다. 넘지 못한다."""
    projection = simulate(_churn_model(), months=200)
    ceiling = 10 / 0.1
    final = projection.rows[-1].state["users"]
    assert final < ceiling
    assert final == pytest.approx(ceiling, rel=1e-6)


def test_churn_is_monotonic_when_joiners_are_steady():
    users = [row.state["users"] for row in simulate(_churn_model()).rows]
    assert all(b > a for a, b in zip(users, users[1:]))


def test_no_churn_means_it_just_piles_up():
    projection = simulate(_churn_model(), {"churn_rate": 0})
    users = [row.state["users"] for row in projection.rows]
    assert users == pytest.approx([10 * (i + 1) for i in range(12)])


def test_total_churn_holds_everyone_leaves():
    """이탈률 100% 면 매달 새로 온 사람만 남는다."""
    projection = simulate(_churn_model(), {"churn_rate": 1})
    assert all(row.state["users"] == pytest.approx(10) for row in projection.rows)


def test_retainer_model_starts_from_existing_clients_only(models):
    """이번 달 납품한 고객이 이번 달부터 유지비를 내지는 않는다."""
    spec = _spec(models, "agency_retainer")
    projection = simulate(spec, {"starting_retainer_clients": 3})
    assert projection.rows[0].state["retainer_clients"] == pytest.approx(3)
    values = projection.values
    expected = 3 * (1 - values["churn_rate"]) + (
        values["new_deals_per_month"] * values["retainer_conversion_rate"])
    assert projection.rows[1].state["retainer_clients"] == pytest.approx(expected)


def test_saas_converts_signups_in_the_first_month(models):
    spec = _spec(models, "saas_subscription")
    projection = simulate(spec)
    values = projection.values
    assert projection.rows[0].state["paid_users"] == pytest.approx(
        values["monthly_signups"] * values["paid_conversion_rate"])


# ------------------------------------------------------------------ 비교
def test_compare_sorts_by_hourly_not_by_profit(models):
    """손익이 커도 시간을 네 배 쓰면 더 나은 선택이 아니다."""
    chosen = [_spec(models, key)
              for key in ("groupbuy", "ebook_course", "agency_retainer")]
    rows = compare_models(chosen)
    hourlies = [row.projection.hourly for row in rows]
    assert hourlies == sorted(hourlies, reverse=True)


def test_compare_scales_by_the_hour_budget(models):
    chosen = [_spec(models, key) for key in ("groupbuy", "ebook_course")]
    rows = compare_models(chosen, budget_hours=80)
    for row in rows:
        assert row.scaled_monthly_profit == pytest.approx(row.projection.hourly * 80)


def test_compare_rejects_a_zero_budget(models):
    with pytest.raises(ValueError, match="0보다"):
        compare_models([_spec(models, "groupbuy")], budget_hours=0)


def test_compare_puts_models_without_hours_last(models):
    chosen = [_spec(models, "groupbuy"), _toy()]
    rows = compare_models(chosen, overrides={"toy": {"hours": 0}})
    assert rows[-1].model.id == "toy"


# ------------------------------------------------------------- 몬테카를로
def test_montecarlo_is_reproducible_with_a_seed(models):
    """완료 기준: --seed 로 재현됩니다."""
    spec = _spec(models, "saas_subscription")
    first = run_montecarlo(spec, runs=200, seed=42)
    second = run_montecarlo(spec, runs=200, seed=42)
    assert vars(first.net) == vars(second.net)
    assert vars(first.hourly) == vars(second.hourly)
    assert first.loss_rate == second.loss_rate


def test_montecarlo_differs_with_another_seed(models):
    spec = _spec(models, "saas_subscription")
    assert (vars(run_montecarlo(spec, runs=200, seed=1).net)
            != vars(run_montecarlo(spec, runs=200, seed=2).net))


def test_montecarlo_percentiles_are_ordered(models):
    result = run_montecarlo(_spec(models, "groupbuy"), runs=300, seed=7)
    assert result.net.p10 <= result.net.p50 <= result.net.p90


def test_montecarlo_only_shakes_params_marked_uncertain(models):
    spec = _spec(models, "groupbuy")
    result = run_montecarlo(spec, runs=50, seed=7)
    marked = {p.key for p in spec.params if p.uncertain > 0}
    assert set(result.shaken) == marked and marked


def test_montecarlo_keeps_values_inside_their_range(models):
    """흔들다가 비율이 1 을 넘으면 말이 안 되는 결과가 나온다."""
    spec = _spec(models, "saas_subscription")
    result = run_montecarlo(spec, {"paid_conversion_rate": 0.49}, runs=200, seed=3)
    assert result.net.p90 >= result.net.p10


def test_montecarlo_refuses_a_model_with_nothing_to_shake():
    with pytest.raises(ValueError, match="흔들 값이 없습니다"):
        run_montecarlo(_toy(), runs=10)


def test_montecarlo_rejects_zero_runs(models):
    with pytest.raises(ValueError, match="1 이상"):
        run_montecarlo(_spec(models, "groupbuy"), runs=0)


def test_percentile_interpolates():
    assert percentile([0, 10], 0.5) == pytest.approx(5)
    assert percentile([0, 10, 20], 0.0) == 0
    assert percentile([0, 10, 20], 1.0) == 20


# ------------------------------------------------------- 파이썬 ↔ 자바스크립트
@pytest.mark.parametrize("model_id", REQUIRED)
def test_javascript_gives_the_same_numbers_as_python(models, model_id, tmp_path):
    """계산식을 한 곳에만 두기로 한 설계가 실제로 지켜지는지 본다.

    터미널과 대시보드의 숫자가 다르면 어느 쪽을 믿을지 알 수 없게 된다.
    """
    if not Path(NODE).exists():
        pytest.fail("node 가 없어 대시보드 계산을 확인할 수 없습니다")

    spec = _spec(models, model_id)
    payload = model_payload({model_id: spec})[0]
    payload["values"] = spec.defaults()

    script = tmp_path / "run.js"
    script.write_text(
        f"const S = require({str(BASE_DIR / 'income_sim' / 'formula.js')!r});\n"
        "const m = JSON.parse(process.argv[2]);\n"
        "console.log(JSON.stringify(S.simulate(m, m.values, 12)));\n",
        encoding="utf-8")

    done = subprocess.run(
        [NODE, str(script), json.dumps(payload, ensure_ascii=False)],
        capture_output=True, text=True, check=True)
    js = json.loads(done.stdout)
    py = simulate(spec)

    assert js["total_profit"] == pytest.approx(py.total_profit, rel=1e-9, abs=1e-6)
    assert js["total_hours"] == pytest.approx(py.total_hours, rel=1e-9, abs=1e-6)
    assert js["net_after_initial"] == pytest.approx(py.net_after_initial,
                                                   rel=1e-9, abs=1e-6)
    assert js["cumulative_breakeven"] == py.cumulative_breakeven
    assert js["monthly_breakeven"] == py.monthly_breakeven
    for js_row, py_row in zip(js["rows"], py.rows):
        assert js_row["cumulative"] == pytest.approx(py_row.cumulative,
                                                    rel=1e-9, abs=1e-6)
        for key, value in py_row.state.items():
            assert js_row["state"][key] == pytest.approx(value, rel=1e-9, abs=1e-6)


# ------------------------------------------------------------------ 대시보드
@pytest.fixture(scope="session")
def dashboard(tmp_path_factory, models) -> str:
    path = build_dashboard(models, tmp_path_factory.mktemp("sim") / "dashboard.html")
    return path.read_text(encoding="utf-8")


def test_dashboard_is_one_file_with_everything_inside(dashboard):
    assert "IncomeSim" in dashboard, "계산기가 파일 안에 들어 있어야 합니다"
    assert dashboard.count("<script") >= 3
    assert "__MODELS_JSON__" not in dashboard and "/*__FORMULA_JS__*/" not in dashboard


def test_dashboard_loads_chartjs_from_cdnjs(dashboard):
    assert CHART_JS in dashboard
    assert CHART_JS.startswith("https://cdnjs.cloudflare.com/")
    assert "/4.4.3/" in CHART_JS, "판을 고정해야 어느 날 모양이 달라지지 않습니다"


def _embedded_models(dashboard: str) -> list[dict]:
    """대시보드 안에 심어 둔 모델 정보를 도로 꺼낸다.

    글자로 찾으면 따옴표가 든 근거 문장이 JSON 에서 `\\"` 로 바뀌어 있어 헛돈다.
    파싱해서 값으로 견주는 편이 정확하다.
    """
    marker = "var MODELS = "
    start = dashboard.index(marker) + len(marker)
    end = dashboard.index(";\n", start)
    return json.loads(dashboard[start:end])


def test_dashboard_has_a_slider_for_every_param(dashboard, models):
    assert 'slider.type = "range"' in dashboard, "슬라이더를 만드는 코드가 없습니다"
    embedded = {item["id"]: item for item in _embedded_models(dashboard)}
    assert set(embedded) == set(models)
    for spec in models.values():
        keys = [param["key"] for param in embedded[spec.id]["params"]]
        assert keys == [param.key for param in spec.params], spec.id


def test_dashboard_carries_every_source_string(dashboard, models):
    """근거를 화면에서도 볼 수 있어야 합니다."""
    embedded = {item["id"]: item for item in _embedded_models(dashboard)}
    for spec in models.values():
        sources = {param["key"]: param["source"]
                   for param in embedded[spec.id]["params"]}
        for param in spec.params:
            assert sources[param.key] == param.source, f"{spec.id}.{param.key}"


def test_dashboard_shows_the_disclaimer(dashboard):
    assert DISCLAIMER in dashboard


def test_dashboard_explains_itself_when_the_chart_cannot_load(dashboard):
    """인터넷이 안 되면 그래프가 빈칸으로 남는다. 왜인지 알려 줘야 한다."""
    assert "불러오지 못했습니다" in dashboard
    assert "chartsUnavailable" in dashboard


def test_dashboard_ships_a_table_beside_the_charts(dashboard):
    """밝은 화면에서 초록의 대비가 낮아, 색 말고 숫자로도 읽을 수 있어야 한다."""
    assert 'id="table"' in dashboard


def test_dashboard_defines_colors_for_both_themes(dashboard):
    assert "prefers-color-scheme: dark" in dashboard
    assert '[data-theme="dark"]' in dashboard
    for slot in ("--series-1", "--series-2", "--series-3"):
        assert dashboard.count(slot) >= 3


def test_dashboard_has_no_banned_phrases(dashboard):
    assert banned_phrases.check(dashboard) == []


# ------------------------------------------------------------------ 출력
def test_every_output_starts_with_the_disclaimer():
    assert DISCLAIMER in banner()


def test_projection_table_shows_both_breakevens(models):
    text = projection_table(simulate(_spec(models, "agency_retainer")))
    assert "월 손익분기" in text and "누적 손익분기" in text
    assert "시간당 수익" in text


def test_projection_table_warns_below_minimum_wage(models):
    text = projection_table(simulate(_spec(models, "youtube_shorts")))
    assert "손해입니다" in text


def test_sources_table_lists_every_default(models):
    spec = _spec(models, "coupang_partners")
    text = sources_table(spec)
    for param in spec.params:
        assert param.label in text and param.source[:20] in text


def test_width_counts_korean_as_two_columns():
    assert width("가나") == 4
    assert width("ab") == 2


def test_reports_have_no_banned_phrases(models):
    for spec in models.values():
        blob = projection_table(simulate(spec)) + sources_table(spec)
        assert banned_phrases.check(blob) == [], spec.id


# ------------------------------------------------------------------ CLI
def test_cli_runs_every_model(capsys, models):
    for model_id in REQUIRED:
        assert sim_cli.main(["run", model_id]) == 0
    out = capsys.readouterr().out
    assert out.count(DISCLAIMER) == len(REQUIRED)


def test_cli_accepts_overrides(capsys):
    assert sim_cli.main(["run", "youtube_long", "--monthly_views=1000000"]) == 0
    assert "1,000,000" in capsys.readouterr().out


def test_cli_accepts_percent_shorthand(capsys):
    assert sim_cli.main(["run", "groupbuy", "--margin_rate=30%", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["values"]["margin_rate"] == pytest.approx(0.3)


def test_cli_rejects_an_unknown_model(capsys):
    assert sim_cli.main(["run", "없는모델"]) == 1
    assert "모르는 모델" in capsys.readouterr().err


def test_cli_rejects_a_malformed_override(capsys):
    assert sim_cli.main(["run", "groupbuy", "--margin_rate"]) == 1
    assert "--이름=숫자" in capsys.readouterr().err


def test_cli_compare_prints_a_table(capsys):
    assert sim_cli.main(["compare", "7", "6", "5"]) == 0
    out = capsys.readouterr().out
    assert DISCLAIMER in out
    assert "시간당" in out and "환산" in out


def test_cli_compare_needs_two_models(capsys):
    assert sim_cli.main(["compare", "7"]) == 1
    assert "두 개 이상" in capsys.readouterr().err


def test_cli_montecarlo_is_reproducible(capsys):
    assert sim_cli.main(["montecarlo", "groupbuy", "--n", "100", "--seed", "5",
                         "--json"]) == 0
    first = capsys.readouterr().out
    assert sim_cli.main(["montecarlo", "groupbuy", "--n", "100", "--seed", "5",
                         "--json"]) == 0
    assert first == capsys.readouterr().out


def test_cli_html_writes_one_file(tmp_path, capsys):
    assert sim_cli.main(["html", "--out", str(tmp_path)]) == 0
    path = tmp_path / "dashboard.html"
    assert path.is_file() and path.stat().st_size > 20000
    assert "대시보드를 만들었습니다" in capsys.readouterr().out


def test_cli_models_lists_all_eight(capsys):
    assert sim_cli.main(["models"]) == 0
    out = capsys.readouterr().out
    for model_id in REQUIRED:
        assert model_id in out


def test_cli_sources_shows_the_grounds(capsys):
    assert sim_cli.main(["sources", "1"]) == 0
    out = capsys.readouterr().out
    assert "근거:" in out and "CLAUDE.md" in out


def test_cli_without_a_command_shows_help(capsys):
    assert sim_cli.main([]) == 1
    assert "run" in capsys.readouterr().out


# ------------------------------------------------------------------ 문서
def test_readme_covers_the_commands_and_is_clean():
    text = (BASE_DIR / "README.md").read_text(encoding="utf-8")
    for token in ("cli.py run", "compare", "montecarlo", "cli.py html",
                  "--seed", "근거"):
        assert token in text, token
    assert DISCLAIMER in text
    assert banned_phrases.check(text) == []


def test_product_manuals_are_detailed_and_clean():
    for name in ("admin.md", "client.md"):
        path = BASE_DIR / "docs" / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert len(text) > 4000, f"{name} 이 너무 짧습니다"
        assert banned_phrases.check(text) == []


def test_model_yaml_files_have_no_banned_phrases():
    for path in MODELS_DIR.glob("*.yaml"):
        assert banned_phrases.check(path.read_text(encoding="utf-8")) == [], path.name
