"""보고서 — 마크다운과 HTML.

    outputs/report_<날짜>.md     키워드 순위표
    outputs/report.html          같은 내용 + 차트

차트는 Chart.js 를 cdnjs 에서 받아 씁니다. 인터넷이 없으면 표만 보이고,
**왜 안 보이는지 화면에 적습니다.** 빈 상자만 남기지 않습니다.

여기에도 규칙이 하나 있다. **영상 제목과 채널명을 싣지 않는다.**
지표만 싣는다. 목록을 보여 주는 순간 "이걸 따라 만들라" 는 도구가 된다.
"""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from niche.metrics import (                                          # noqa: E402
    BREAKOUT_MULTIPLE, GROWTH_WINDOW_DAYS, KeywordMetrics, SMALL_CHANNEL_MAX,
)
from shared import ai_label                                          # noqa: E402

__all__ = ["write_markdown", "write_html", "CHART_JS", "DISCLAIMER"]

#: 차트 라이브러리. 판을 못 박아 둔다.
CHART_JS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.3/chart.umd.min.js"

DISCLAIMER = (
    "이 보고서는 **시장의 모양**을 보여 줄 뿐, 무엇을 만들면 된다고 말하지 않습니다. "
    "특정 영상이나 채널을 따라 만들라는 제안은 하지 않습니다."
)


def _table(metrics: list[KeywordMetrics]) -> list[str]:
    lines = [
        "| 키워드 | 공백 지수 | 신규 영상 | 중앙값 조회수 | 소형 채널 성과율 |"
        " 쇼츠 비중 | 공급 증가율 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in metrics:
        mark = " 🟢" if item.entry_friendly else ""
        lines.append(
            f"| {item.keyword}{mark} | {item.gap:,.1f} | {item.videos} |"
            f" {item.median_views:,} | {item.breakout_rate:.1f}% |"
            f" {item.shorts_ratio:.1f}% | {item.supply_growth:+.1f}% |")
    return lines


def write_markdown(metrics: list[KeywordMetrics], out_dir: Path, days: int,
                   commentary: list[str] | None = None,
                   demo: bool = False, ai_label_on: bool = True) -> Path:
    """키워드 순위표."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")

    lines: list[str] = [
        "# 니치 리서치 보고서",
        "",
        f"- 만든 날: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 모은 날수: **{days}일치**",
        f"- 키워드: {len(metrics)}개",
        "",
    ]

    if demo:
        lines += ["> ⚠️ **샘플 자료로 만든 보고서입니다.** 숫자는 지어낸 것이고, "
                  "실제 시장이 아닙니다. 본인 키워드로 2주쯤 모은 뒤에 보세요.", ""]
    if days < 3:
        lines += [f"> ⚠️ 아직 {days}일치뿐입니다. 추이 지표(공급 증가율·채널 성장률)는 "
                  "며칠 더 모아야 뜻이 생깁니다.", ""]

    lines += [f"> {DISCLAIMER}", "", "---", "", "## 키워드 순위 (공백 지수 높은 순)", ""]
    lines += _table(metrics)
    lines += ["", "🟢 = 소형 채널이 뚫고 있는 키워드 (성과율 20% 이상)", ""]

    lines += ["## 지표가 무슨 뜻인가", "",
              "| 지표 | 뜻 | 어떻게 읽나 |", "|---|---|---|",
              "| 공백 지수 | 중앙값 조회수 ÷ 신규 영상 수 | **높을수록 공백.** "
              "보는 사람은 많은데 만드는 사람이 적다는 뜻 |",
              f"| 소형 채널 성과율 | 구독자 {SMALL_CHANNEL_MAX:,} 이하 채널 영상 중 "
              f"조회수가 구독자의 {BREAKOUT_MULTIPLE}배를 넘긴 비율 | "
              "**가장 중요합니다.** 작은 채널이 뚫고 있으면 지금 들어갈 만합니다 |",
              "| 공급 증가율 | 최근 주 ÷ 직전 주 신규 영상 수 | 크게 오르고 있으면 "
              "남들도 들어오고 있다는 뜻 |",
              "| 쇼츠 비중 | 전체 중 3분 이하 영상 비율 | 어떤 포맷이 도는 시장인지 |",
              f"| 채널 성장률 | {GROWTH_WINDOW_DAYS}일 구독자 증가율 중앙값 | "
              "시장 전체가 커지는 중인지 |", ""]

    lines += ["## 포맷 나눠 보기", "",
              "| 키워드 | 쇼츠 수 | 쇼츠 중앙값 | 롱폼 수 | 롱폼 중앙값 |",
              "|---|---:|---:|---:|---:|"]
    for item in metrics:
        lines.append(
            f"| {item.keyword} | {item.shorts} | {item.shorts_median:,} |"
            f" {item.longform} | {item.longform_median:,} |")
    lines.append("")

    if commentary:
        lines += ["## 지표 해설", ""]
        lines += [f"{index}. {line}" for index, line in enumerate(commentary, start=1)]
        lines += ["", "> 해설은 지표를 읽은 것이고, 무엇을 만들지는 본인이 정합니다.", ""]

    notes = [(item.keyword, note) for item in metrics for note in item.notes]
    if notes:
        lines += ["## 확인하실 것", ""]
        for keyword, note in notes:
            lines.append(f"- **{keyword}** — {note}")
        lines.append("")

    lines += [
        "---",
        "",
        "## 이 보고서가 하지 않는 것",
        "",
        "- 특정 영상을 집어 \"이걸 따라 만드세요\" 라고 하지 않습니다",
        "- 채널 이름과 영상 제목을 싣지 않습니다",
        "- 조회수를 예측하지 않습니다",
        "",
        "보는 것은 **시장의 모양**뿐입니다. 무엇을 만들지는 사람이 정합니다.",
    ]

    body = "\n".join(lines)
    if ai_label_on and commentary:
        body = ai_label.add_text_label(body)

    path = out_dir / f"report_{stamp}.md"
    path.write_text(body + "\n", encoding="utf-8")
    return path


def write_html(metrics: list[KeywordMetrics], out_dir: Path, days: int,
               commentary: list[str] | None = None, demo: bool = False) -> Path:
    """같은 내용에 차트를 얹은 한 장짜리 HTML."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = [item.keyword for item in metrics]
    chart_data = {
        "labels": labels,
        "gap": [item.gap for item in metrics],
        "videos": [item.videos for item in metrics],
        "median": [item.median_views for item in metrics],
        "breakout": [item.breakout_rate for item in metrics],
        "shorts": [item.shorts for item in metrics],
        "longform": [item.longform for item in metrics],
        "weekly": [[bucket["count"] for bucket in item.weekly_counts]
                   for item in metrics],
        "weeks": [bucket["end"][5:] for bucket in (metrics[0].weekly_counts
                                                   if metrics else [])],
    }

    pill = '<span class="pill">진입 여지</span>'
    rows = "\n".join(
        f"<tr><td>{html.escape(item.keyword)} "
        f"{pill if item.entry_friendly else ''}</td>"
        f"<td class='n'>{item.gap:,.1f}</td>"
        f"<td class='n'>{item.videos}</td>"
        f"<td class='n'>{item.median_views:,}</td>"
        f"<td class='n'>{item.breakout_rate:.1f}%</td>"
        f"<td class='n'>{item.shorts_ratio:.1f}%</td>"
        f"<td class='n'>{item.supply_growth:+.1f}%</td></tr>"
        for item in metrics)

    notes_html = ""
    lines = [f"<li><b>{html.escape(item.keyword)}</b> — {html.escape(note)}</li>"
             for item in metrics for note in item.notes]
    if lines:
        notes_html = ("<h2>확인하실 것</h2><ul class='notes'>"
                      + "".join(lines) + "</ul>")

    commentary_html = ""
    if commentary:
        items = "".join(f"<li>{html.escape(line)}</li>" for line in commentary)
        commentary_html = (
            "<h2>지표 해설</h2><ol class='commentary'>" + items + "</ol>"
            "<p class='muted'>해설은 지표를 읽은 것이고, 무엇을 만들지는 본인이 "
            "정합니다.</p>")

    demo_banner = ("<div class='warn'><b>샘플 자료로 만든 보고서입니다.</b> "
                   "숫자는 지어낸 것이고 실제 시장이 아닙니다.</div>" if demo else "")
    days_banner = (f"<div class='warn'>아직 <b>{days}일치</b>뿐입니다. 추이 지표는 "
                   "며칠 더 모아야 뜻이 생깁니다.</div>" if days < 3 else "")

    page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>니치 리서치 보고서</title>
<style>
  :root {{
    --bg: #f6f7f9; --card: #ffffff; --ink: #1c2530; --muted: #66707c;
    --line: #dfe3e8; --accent: #2a78d6; --warm: #eb6834; --good: #1baf7a;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #12171d; --card: #1b222a; --ink: #eef2f6; --muted: #9aa6b2;
      --line: #2b343f; --accent: #3987e5; --warm: #d95926; --good: #199e70;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink);
    font-family: "IBM Plex Sans KR", "Apple SD Gothic Neo", system-ui, sans-serif;
    line-height: 1.6; }}
  .wrap {{ max-width: 960px; margin: 0 auto; padding: 28px 16px 64px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  h2 {{ font-size: 16px; margin: 32px 0 10px; }}
  .muted {{ color: var(--muted); font-size: 13px; }}
  .card {{ background: var(--card); border: 1px solid var(--line);
    border-radius: 10px; padding: 16px; margin-top: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; }}
  th {{ font-size: 12px; color: var(--muted); font-weight: 600; }}
  td.n {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .pill {{ background: var(--good); color: #fff; border-radius: 999px;
    padding: 1px 8px; font-size: 11px; }}
  .warn {{ background: color-mix(in srgb, var(--warm) 12%, var(--card));
    border: 1px solid var(--warm); border-radius: 8px; padding: 10px 14px;
    margin-top: 12px; font-size: 13.5px; }}
  .note {{ border-left: 3px solid var(--accent); padding: 8px 14px;
    margin-top: 16px; font-size: 13.5px; }}
  canvas {{ max-height: 300px; }}
  .charts {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
  ul.notes li, ol.commentary li {{ font-size: 13.5px; margin-bottom: 4px; }}
  .fallback {{ display: none; color: var(--muted); font-size: 13px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>니치 리서치 보고서</h1>
  <p class="muted">{datetime.now().strftime('%Y-%m-%d %H:%M')} · 모은 날수 <b>{days}일치</b>
    · 키워드 {len(metrics)}개</p>
  {demo_banner}
  {days_banner}
  <div class="note">{DISCLAIMER}</div>

  <h2>키워드 순위 (공백 지수 높은 순)</h2>
  <div class="card">
    <table>
      <tr><th>키워드</th><th>공백 지수</th><th>신규 영상</th><th>중앙값 조회수</th>
          <th>소형 채널 성과율</th><th>쇼츠 비중</th><th>공급 증가율</th></tr>
      {rows}
    </table>
    <p class="muted">공백 지수 = 중앙값 조회수 ÷ 신규 영상 수. 높을수록 보는 사람 대비
      만드는 사람이 적다는 뜻입니다.</p>
  </div>

  <h2>그림으로</h2>
  <div class="charts">
    <div class="card"><canvas id="gap"></canvas>
      <p class="fallback">차트를 못 받아왔습니다. 위 표를 보세요.</p></div>
    <div class="card"><canvas id="format"></canvas>
      <p class="fallback">차트를 못 받아왔습니다. 위 표를 보세요.</p></div>
    <div class="card"><canvas id="weekly"></canvas>
      <p class="fallback">차트를 못 받아왔습니다. 위 표를 보세요.</p></div>
    <div class="card"><canvas id="breakout"></canvas>
      <p class="fallback">차트를 못 받아왔습니다. 위 표를 보세요.</p></div>
  </div>

  {commentary_html}
  {notes_html}

  <h2>이 보고서가 하지 않는 것</h2>
  <div class="card">
    <ul>
      <li>특정 영상을 집어 "이걸 따라 만드세요" 라고 하지 않습니다</li>
      <li>채널 이름과 영상 제목을 싣지 않습니다</li>
      <li>조회수를 예측하지 않습니다</li>
    </ul>
    <p class="muted">보는 것은 시장의 모양뿐입니다. 무엇을 만들지는 사람이 정합니다.</p>
  </div>
</div>

<script id="data" type="application/json">{json.dumps(chart_data, ensure_ascii=False)}</script>
<script src="{CHART_JS}"></script>
<script>
  (function () {{
    var D = JSON.parse(document.getElementById("data").textContent);

    if (typeof Chart === "undefined") {{
      // 인터넷이 없으면 차트를 못 그린다. 빈 상자만 남기지 말고 이유를 적는다.
      document.querySelectorAll("canvas").forEach(function (el) {{ el.remove(); }});
      document.querySelectorAll(".fallback").forEach(function (el) {{
        el.style.display = "block";
      }});
      return;
    }}

    var ink = getComputedStyle(document.body).getPropertyValue("--ink");
    Chart.defaults.color = ink;
    Chart.defaults.font.family = '"IBM Plex Sans KR", system-ui, sans-serif';

    new Chart(document.getElementById("gap"), {{
      type: "bar",
      data: {{ labels: D.labels,
        datasets: [{{ label: "공백 지수", data: D.gap, backgroundColor: "#2a78d6" }}] }},
      options: {{ plugins: {{ title: {{ display: true, text: "공백 지수 (높을수록 공백)" }},
        legend: {{ display: false }} }} }},
    }});

    new Chart(document.getElementById("format"), {{
      type: "bar",
      data: {{ labels: D.labels, datasets: [
        {{ label: "쇼츠", data: D.shorts, backgroundColor: "#eb6834" }},
        {{ label: "롱폼", data: D.longform, backgroundColor: "#1baf7a" }}] }},
      options: {{ plugins: {{ title: {{ display: true, text: "쇼츠 vs 롱폼 (편수)" }} }},
        scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }} }},
    }});

    new Chart(document.getElementById("weekly"), {{
      type: "line",
      data: {{ labels: D.weeks, datasets: D.labels.map(function (name, index) {{
        return {{ label: name, data: D.weekly[index], tension: 0.25,
          borderColor: ["#2a78d6", "#eb6834", "#1baf7a"][index % 3] }};
      }}) }},
      options: {{ plugins: {{ title: {{ display: true, text: "주간 신규 영상 수" }} }} }},
    }});

    new Chart(document.getElementById("breakout"), {{
      type: "bar",
      data: {{ labels: D.labels, datasets: [{{ label: "소형 채널 성과율(%)",
        data: D.breakout, backgroundColor: "#1baf7a" }}] }},
      options: {{ indexAxis: "y",
        plugins: {{ title: {{ display: true, text: "소형 채널 성과율 (%)" }},
          legend: {{ display: false }} }} }},
    }});
  }})();
</script>
</body>
</html>
"""
    path = out_dir / "report.html"
    path.write_text(page, encoding="utf-8")
    return path
