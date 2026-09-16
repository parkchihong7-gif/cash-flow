"""슬라이더로 만져 보는 단일 HTML 대시보드.

파일 하나로 끝난다. 열어서 슬라이더를 움직이면 바로 다시 계산된다.
그래프만 인터넷이 필요하다(Chart.js 를 cdnjs 에서 받는다).

계산은 `formula.js` 가 한다. **터미널의 파이썬과 같은 계산식**을 쓰므로
두 곳의 숫자가 갈리지 않는다. 테스트가 node 로 실제 값을 맞춰 본다.

[색]
카테고리 3색은 dataviz 검증기(scripts/validate_palette.js)를 통과한 조합이다.
  밝은 화면  #2a78d6 #eb6834 #1baf7a
  어두운 화면 #3987e5 #d95926 #199e70
밝은 화면에서 aqua 의 대비가 3:1 아래라 '보조 표시' 가 필요한데,
12개월 표를 같이 싣는 것으로 그 조건을 채운다.
"""

from __future__ import annotations

import json
from pathlib import Path

from income_sim.engine import DISCLAIMER
from income_sim.schema import ModelSpec

__all__ = ["build_dashboard", "CHART_JS", "model_payload"]

#: Chart.js 는 판을 고정해서 받는다. 최신을 받아 쓰면 어느 날 갑자기 모양이 달라진다.
CHART_JS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.3/chart.umd.min.js"

FORMULA_JS = Path(__file__).resolve().parent / "formula.js"


def model_payload(models: dict[str, ModelSpec]) -> list[dict]:
    """화면이 쓸 모양으로 모델을 옮긴다."""
    payload = []
    for spec in models.values():
        payload.append({
            "id": spec.id,
            "number": spec.number,
            "name": spec.name,
            "tagline": spec.tagline,
            "summary": spec.summary.strip(),
            "cautions": spec.cautions,
            "state": [{"key": s.key, "label": s.label, "unit": s.unit,
                       "initial": s.initial, "next": s.next} for s in spec.state],
            "formulas": {"revenue": spec.formulas.revenue,
                         "cost": spec.formulas.cost,
                         "hours": spec.formulas.hours},
            "params": [{
                "key": p.key, "label": p.label, "default": p.default,
                "unit": p.unit, "kind": p.kind, "min": p.minimum,
                "max": p.maximum, "step": p.step, "source": p.source,
                "help": p.help, "uncertain": p.uncertain,
            } for p in spec.params],
        })
    return payload


def build_dashboard(models: dict[str, ModelSpec], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    html = _TEMPLATE
    html = html.replace("/*__FORMULA_JS__*/", FORMULA_JS.read_text(encoding="utf-8"))
    html = html.replace("__MODELS_JSON__",
                        json.dumps(model_payload(models), ensure_ascii=False))
    html = html.replace("__DISCLAIMER__", DISCLAIMER)
    html = html.replace("__CHART_JS__", CHART_JS)

    path.write_text(html, encoding="utf-8")
    return path


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>수익 시뮬레이터</title>
<script src="__CHART_JS__"></script>
<style>
  :root {
    color-scheme: light;
    --ground:      #f2f3f0;
    --surface:     #fcfcfb;
    --raised:      #ffffff;
    --line:        #e0e0da;
    --ink:         #0b0b0b;
    --ink-2:       #52514e;
    --ink-3:       #83827c;
    --accent:      #2a78d6;
    --series-1:    #2a78d6;
    --series-2:    #eb6834;
    --series-3:    #1baf7a;
    --good:        #0f7a4d;
    --bad:         #c0392b;
    --warn-bg:     #fdf3e0;
    --warn-ink:    #7a4a06;
    --warn-line:   #e6c893;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      color-scheme: dark;
      --ground:    #121211;
      --surface:   #1a1a19;
      --raised:    #222221;
      --line:      #34342f;
      --ink:       #ffffff;
      --ink-2:     #c3c2b7;
      --ink-3:     #8f8e86;
      --accent:    #3987e5;
      --series-1:  #3987e5;
      --series-2:  #d95926;
      --series-3:  #199e70;
      --good:      #35b37e;
      --bad:       #e66767;
      --warn-bg:   #2b2418;
      --warn-ink:  #e8c88a;
      --warn-line: #4d3f25;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --ground:    #121211;
    --surface:   #1a1a19;
    --raised:    #222221;
    --line:      #34342f;
    --ink:       #ffffff;
    --ink-2:     #c3c2b7;
    --ink-3:     #8f8e86;
    --accent:    #3987e5;
    --series-1:  #3987e5;
    --series-2:  #d95926;
    --series-3:  #199e70;
    --good:      #35b37e;
    --bad:       #e66767;
    --warn-bg:   #2b2418;
    --warn-ink:  #e8c88a;
    --warn-line: #4d3f25;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--ground);
    color: var(--ink);
    font-family: "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR",
                 system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.6;
  }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 24px 16px 64px; }

  h1 { font-size: 20px; margin: 0 0 4px; letter-spacing: -.01em; }
  .sub { color: var(--ink-2); margin: 0 0 16px; font-size: 13px; }

  .disclaimer {
    background: var(--warn-bg);
    border: 1px solid var(--warn-line);
    color: var(--warn-ink);
    border-radius: 8px;
    padding: 11px 14px;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 20px;
  }
  .disclaimer span { font-weight: 400; display: block; margin-top: 3px; }

  .tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 20px; }
  .tab {
    font: inherit; font-size: 13px;
    background: var(--raised); color: var(--ink-2);
    border: 1px solid var(--line); border-radius: 999px;
    padding: 6px 13px; cursor: pointer;
    display: inline-flex; align-items: center; gap: 6px;
  }
  .tab:hover { border-color: var(--accent); color: var(--ink); }
  .tab:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .tab[aria-pressed="true"] {
    background: var(--accent); border-color: var(--accent);
    color: #fff; font-weight: 600;
  }
  .tab .n { font-variant-numeric: tabular-nums; opacity: .7; font-size: 11px; }
  .tab[aria-pressed="true"] .n { opacity: .85; }

  /* minmax(0, 1fr) 로 둔다. 그냥 1fr 이면 칸의 최소 너비가 '안에 든 것 중
     가장 넓은 것' 이 되어, 표(min-width 620px) 때문에 칸이 줄어들지 못하고
     휴대폰에서 화면이 옆으로 밀린다. */
  .grid {
    display: grid;
    grid-template-columns: 330px minmax(0, 1fr);
    gap: 20px; align-items: start;
  }
  @media (max-width: 900px) { .grid { grid-template-columns: minmax(0, 1fr); } }

  .panel {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 18px;
  }
  .panel + .panel { margin-top: 20px; }
  .panel h2 { font-size: 15px; margin: 0 0 4px; }
  .panel .note { color: var(--ink-2); font-size: 12.5px; margin: 0 0 14px; }

  .field { margin-bottom: 15px; }
  .field-top { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .field label { font-size: 12.5px; font-weight: 600; }
  .field output {
    font-variant-numeric: tabular-nums;
    font-size: 12.5px; color: var(--accent); font-weight: 600;
  }
  .field input[type=range] { width: 100%; margin: 5px 0 0; accent-color: var(--accent); }
  .field input[type=range]:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
  .why {
    font: inherit; font-size: 11.5px; color: var(--ink-3);
    background: none; border: 0; padding: 0; cursor: pointer;
    text-decoration: underline; text-underline-offset: 2px;
  }
  .source {
    font-size: 11.5px; color: var(--ink-2); line-height: 1.55;
    background: var(--raised); border-left: 2px solid var(--line);
    padding: 7px 10px; margin-top: 6px; border-radius: 0 4px 4px 0;
  }

  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
  .tile { background: var(--raised); border: 1px solid var(--line); border-radius: 8px; padding: 13px 15px; }
  .tile .k { font-size: 11.5px; color: var(--ink-2); }
  .tile .v { font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums; margin-top: 2px; }
  .tile .v.pos { color: var(--good); }
  .tile .v.neg { color: var(--bad); }
  .tile .x { font-size: 11px; color: var(--ink-3); margin-top: 1px; }

  .chartbox { position: relative; height: 260px; margin-top: 6px; }
  @media (max-width: 640px) { .chartbox { height: 230px; } }
  .chartfail {
    position: absolute; inset: 0;
    display: grid; place-content: center; text-align: center;
    gap: 4px; padding: 16px;
    color: var(--ink-2); font-size: 12.5px; line-height: 1.6;
    border: 1px dashed var(--line); border-radius: 8px;
  }
  .chartfail strong { color: var(--ink); font-size: 13px; }

  .legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px; color: var(--ink-2); margin-top: 10px; }
  .legend i { width: 11px; height: 11px; border-radius: 2px; display: inline-block; margin-right: 5px; vertical-align: -1px; }

  .scroller { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 12.5px; min-width: 620px; }
  th, td { padding: 6px 9px; text-align: right; border-bottom: 1px solid var(--line); font-variant-numeric: tabular-nums; }
  th { color: var(--ink-2); font-weight: 600; text-align: right; white-space: nowrap; }
  th:first-child, td:first-child { text-align: left; }
  tbody tr:hover { background: var(--raised); }
  td.neg { color: var(--bad); }
  td.pos { color: var(--good); }

  ul.cautions { margin: 8px 0 0; padding-left: 18px; color: var(--ink-2); font-size: 12.5px; }
  ul.cautions li { margin-bottom: 4px; }

  .rowbtns { display: flex; gap: 8px; margin-top: 4px; }
  button.plain {
    font: inherit; font-size: 12.5px; background: var(--raised); color: var(--ink);
    border: 1px solid var(--line); border-radius: 6px; padding: 6px 12px; cursor: pointer;
  }
  button.plain:hover { border-color: var(--accent); }
  [hidden] { display: none !important; }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
</head>
<body>
<div class="wrap">

  <h1>수익 시뮬레이터</h1>
  <p class="sub">부업 모델 8종의 12개월 손익을 견줍니다. 슬라이더를 움직이면 바로 다시 계산됩니다.</p>

  <div class="disclaimer">
    ⚠ __DISCLAIMER__
    <span>기본값은 조사·가정에서 나온 출발점입니다. 각 값 옆의 '근거' 를 열어 보고,
      본인 수치로 바꿔야 쓸모가 있습니다.</span>
  </div>

  <div class="tabs" id="tabs" role="group" aria-label="모델 고르기"></div>

  <div class="grid">
    <div>
      <section class="panel">
        <h2 id="model-name">—</h2>
        <p class="note" id="model-tagline"></p>
        <div id="fields"></div>
        <div class="rowbtns">
          <button type="button" class="plain" id="reset">기본값으로</button>
        </div>
      </section>
    </div>

    <div>
      <section class="panel">
        <h2>12개월 결과</h2>
        <p class="note" id="summary-note"></p>
        <div class="tiles" id="tiles"></div>
      </section>

      <section class="panel">
        <h2>월별 매출·비용·손익</h2>
        <p class="note">그달에 들어오고 나간 돈입니다. 세 값이 모두 같은 단위(원)라 한 축에 그립니다.</p>
        <div class="chartbox"><canvas id="chart-monthly"></canvas>
          <div class="chartfail" id="fail-monthly" hidden></div></div>
        <div class="legend">
          <span><i style="background:var(--series-1)"></i>매출</span>
          <span><i style="background:var(--series-2)"></i>비용</span>
          <span><i style="background:var(--series-3)"></i>손익</span>
        </div>
      </section>

      <section class="panel">
        <h2>누적 잔액</h2>
        <p class="note">초기 투자를 빼고 시작해서 매달 손익을 더한 값입니다.
          0 선을 넘는 달이 <strong>누적 손익분기</strong>입니다.</p>
        <div class="chartbox"><canvas id="chart-cumulative"></canvas>
          <div class="chartfail" id="fail-cumulative" hidden></div></div>
      </section>

      <section class="panel">
        <h2>월별 표</h2>
        <p class="note">그래프와 같은 값입니다. 색으로만 구분되지 않게 숫자도 함께 싣습니다.</p>
        <div class="scroller"><table id="table"></table></div>
      </section>

      <section class="panel">
        <h2>같이 봐야 할 것</h2>
        <ul class="cautions" id="cautions"></ul>
      </section>
    </div>
  </div>
</div>

<script>
/*__FORMULA_JS__*/
</script>

<script>
(function () {
  "use strict";

  var MODELS = __MODELS_JSON__;
  var current = MODELS[0];
  var values = {};
  var charts = {};

  var tabsEl = document.getElementById("tabs");
  var fieldsEl = document.getElementById("fields");
  var tilesEl = document.getElementById("tiles");
  var tableEl = document.getElementById("table");
  var cautionsEl = document.getElementById("cautions");

  // ------------------------------------------------------------ 숫자 표기
  function won(value) {
    if (value === null || value === undefined) { return "—"; }
    return Math.round(value).toLocaleString("ko-KR") + "원";
  }
  function shortWon(value) {
    var abs = Math.abs(value);
    if (abs >= 100000000) { return (value / 100000000).toFixed(1) + "억"; }
    if (abs >= 10000) { return Math.round(value / 10000).toLocaleString("ko-KR") + "만"; }
    return Math.round(value).toLocaleString("ko-KR");
  }
  function showValue(param, value) {
    if (param.kind === "rate") { return (value * 100).toFixed(2).replace(/\.?0+$/, "") + "%"; }
    if (param.kind === "money") { return Math.round(value).toLocaleString("ko-KR") + "원"; }
    var text = value % 1 === 0 ? value.toLocaleString("ko-KR") : value.toFixed(1);
    return text + (param.unit ? " " + param.unit : "");
  }
  function token(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // ------------------------------------------------------------ 화면 만들기
  function buildTabs() {
    MODELS.forEach(function (model) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "tab";
      button.setAttribute("aria-pressed", String(model.id === current.id));
      button.innerHTML = '<span class="n">' + model.number + "</span>" + model.name;
      button.addEventListener("click", function () { select(model); });
      tabsEl.appendChild(button);
    });
  }

  function markTabs() {
    Array.prototype.forEach.call(tabsEl.children, function (button, index) {
      button.setAttribute("aria-pressed", String(MODELS[index].id === current.id));
    });
  }

  function buildFields() {
    fieldsEl.textContent = "";
    current.params.forEach(function (param) {
      var field = document.createElement("div");
      field.className = "field";

      var top = document.createElement("div");
      top.className = "field-top";
      var label = document.createElement("label");
      label.setAttribute("for", "p-" + param.key);
      label.textContent = param.label;
      var output = document.createElement("output");
      output.id = "out-" + param.key;
      output.textContent = showValue(param, values[param.key]);
      top.appendChild(label);
      top.appendChild(output);

      var slider = document.createElement("input");
      slider.type = "range";
      slider.id = "p-" + param.key;
      slider.min = param.min;
      slider.max = param.max;
      slider.step = param.step;
      slider.value = values[param.key];
      slider.addEventListener("input", function () {
        values[param.key] = parseFloat(slider.value);
        output.textContent = showValue(param, values[param.key]);
        recompute();
      });

      var why = document.createElement("button");
      why.type = "button";
      why.className = "why";
      why.textContent = "근거 보기";
      var source = document.createElement("div");
      source.className = "source";
      source.hidden = true;
      source.textContent = param.source + (param.help ? " — " + param.help : "");
      why.addEventListener("click", function () {
        source.hidden = !source.hidden;
        why.textContent = source.hidden ? "근거 보기" : "근거 접기";
      });

      field.appendChild(top);
      field.appendChild(slider);
      field.appendChild(why);
      field.appendChild(source);
      fieldsEl.appendChild(field);
    });
  }

  // ------------------------------------------------------------ 그래프
  function baseOptions(formatter) {
    var ink2 = token("--ink-2");
    var line = token("--line");
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: function (items) { return items[0].label + "개월차"; },
            label: function (item) {
              return item.dataset.label + "  " + won(item.parsed.y);
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: line },
          ticks: { color: ink2, font: { size: 11 } }
        },
        y: {
          grid: { color: line },
          border: { display: false },
          ticks: { color: ink2, font: { size: 11 }, callback: formatter }
        }
      }
    };
  }

  function chartsUnavailable() {
    ["monthly", "cumulative"].forEach(function (which) {
      var box = document.getElementById("fail-" + which);
      if (!box || !box.hidden) { return; }
      box.hidden = false;
      box.innerHTML = "<strong>그래프를 불러오지 못했습니다</strong>"
        + "<span>그래프는 인터넷에서 받아 옵니다(Chart.js). "
        + "인터넷 연결을 확인하세요.</span>"
        + "<span>아래 <strong>월별 표</strong>에 같은 숫자가 다 들어 있습니다.</span>";
      document.getElementById("chart-" + which).hidden = true;
    });
  }

  function drawCharts(result) {
    if (typeof Chart === "undefined") { chartsUnavailable(); return; }
    var labels = result.rows.map(function (row) { return row.month; });
    var tick = function (value) { return shortWon(value); };

    var monthly = {
      labels: labels,
      datasets: [
        { label: "매출", data: result.rows.map(function (r) { return r.revenue; }),
          borderColor: token("--series-1"), backgroundColor: token("--series-1") },
        { label: "비용", data: result.rows.map(function (r) { return r.cost; }),
          borderColor: token("--series-2"), backgroundColor: token("--series-2") },
        { label: "손익", data: result.rows.map(function (r) { return r.profit; }),
          borderColor: token("--series-3"), backgroundColor: token("--series-3") }
      ]
    };
    monthly.datasets.forEach(function (set) {
      set.borderWidth = 2;
      set.pointRadius = 4;
      set.pointHoverRadius = 6;
      set.pointBorderColor = token("--surface");
      set.pointBorderWidth = 2;
      set.tension = 0.25;
    });

    var cumulative = {
      labels: labels,
      datasets: [{
        label: "누적 잔액",
        data: result.rows.map(function (r) { return r.cumulative; }),
        borderColor: token("--series-1"),
        backgroundColor: token("--series-1") + "22",
        borderWidth: 2, pointRadius: 4, pointHoverRadius: 6,
        pointBorderColor: token("--surface"), pointBorderWidth: 2,
        fill: true, tension: 0.25
      }]
    };

    var zeroLine = {
      id: "zeroLine",
      afterDatasetsDraw: function (chart) {
        var y = chart.scales.y;
        if (!y || y.min > 0 || y.max < 0) { return; }
        var ctx = chart.ctx;
        var at = y.getPixelForValue(0);
        ctx.save();
        ctx.strokeStyle = token("--ink-3");
        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(chart.chartArea.left, at);
        ctx.lineTo(chart.chartArea.right, at);
        ctx.stroke();
        ctx.restore();
      }
    };

    if (charts.monthly) { charts.monthly.destroy(); }
    if (charts.cumulative) { charts.cumulative.destroy(); }
    charts.monthly = new Chart(document.getElementById("chart-monthly"),
      { type: "line", data: monthly, options: baseOptions(tick), plugins: [zeroLine] });
    charts.cumulative = new Chart(document.getElementById("chart-cumulative"),
      { type: "line", data: cumulative, options: baseOptions(tick), plugins: [zeroLine] });
  }

  // ------------------------------------------------------------ 결과
  function drawTiles(result) {
    var monthly = result.monthly_breakeven;
    var accrued = result.cumulative_breakeven;
    var tiles = [
      { k: "12개월 손익", v: won(result.total_profit), sign: result.total_profit,
        x: "매출 " + won(result.total_revenue) },
      { k: "최종 잔액", v: won(result.net_after_initial), sign: result.net_after_initial,
        x: "초기 투자 " + won(result.initial_cost) + " 까지 뺀 값" },
      { k: "시간당 수익", v: result.hourly === null ? "—" : won(result.hourly),
        sign: result.hourly,
        x: Math.round(result.total_hours).toLocaleString("ko-KR") + "시간 투입" },
      { k: "누적 손익분기", v: accrued ? accrued + "개월차" : "12개월 안에 못 갚음",
        sign: accrued ? 1 : -1,
        x: monthly ? "월 손익분기는 " + monthly + "개월차" : "매달 손해입니다" }
    ];

    tilesEl.textContent = "";
    tiles.forEach(function (tile) {
      var box = document.createElement("div");
      box.className = "tile";
      var sign = tile.sign === null ? "" : (tile.sign >= 0 ? " pos" : " neg");
      box.innerHTML =
        '<div class="k"></div><div class="v' + sign + '"></div><div class="x"></div>';
      box.children[0].textContent = tile.k;
      box.children[1].textContent = tile.v;
      box.children[2].textContent = tile.x;
      tilesEl.appendChild(box);
    });

    var note = document.getElementById("summary-note");
    if (result.hourly !== null && result.hourly < 10320) {
      note.textContent = result.hourly < 0
        ? "시간당 수익이 마이너스입니다. 시간을 쓸수록 돈이 나갑니다."
        : "시간당 수익이 2026년 최저임금(10,320원)보다 낮습니다.";
    } else {
      note.textContent = "값을 바꾸면 이 숫자들이 바로 따라 바뀝니다.";
    }
  }

  function drawTable(result) {
    var stateKeys = (current.state || []).map(function (s) { return s.key; });
    var head = "<thead><tr><th>월</th><th>매출</th><th>비용</th><th>손익</th>"
      + "<th>누적</th><th>시간</th>"
      + (current.state || []).map(function (s) { return "<th>" + s.label + "</th>"; }).join("")
      + "</tr></thead>";

    var body = result.rows.map(function (row) {
      var cells = [
        "<td>" + row.month + "</td>",
        "<td>" + won(row.revenue) + "</td>",
        "<td>" + won(row.cost) + "</td>",
        '<td class="' + (row.profit >= 0 ? "pos" : "neg") + '">' + won(row.profit) + "</td>",
        '<td class="' + (row.cumulative >= 0 ? "pos" : "neg") + '">' + won(row.cumulative) + "</td>",
        "<td>" + Math.round(row.hours).toLocaleString("ko-KR") + "h</td>"
      ];
      stateKeys.forEach(function (key) {
        cells.push("<td>" + row.state[key].toFixed(1) + "</td>");
      });
      return "<tr>" + cells.join("") + "</tr>";
    }).join("");

    tableEl.innerHTML = head + "<tbody>" + body + "</tbody>";
  }

  function recompute() {
    var result = IncomeSim.simulate(current, values, 12);
    drawTiles(result);
    drawCharts(result);
    drawTable(result);
  }

  function select(model) {
    current = model;
    values = {};
    model.params.forEach(function (param) { values[param.key] = param.default; });
    document.getElementById("model-name").textContent = model.number + ". " + model.name;
    document.getElementById("model-tagline").textContent = model.tagline;
    cautionsEl.textContent = "";
    (model.cautions || []).forEach(function (text) {
      var item = document.createElement("li");
      item.textContent = text;
      cautionsEl.appendChild(item);
    });
    markTabs();
    buildFields();
    recompute();
  }

  document.getElementById("reset").addEventListener("click", function () {
    select(current);
  });

  buildTabs();
  select(current);
})();
</script>
</body>
</html>
"""
