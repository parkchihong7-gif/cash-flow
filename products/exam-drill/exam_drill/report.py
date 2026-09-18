"""보고서 — 과락을 맨 위에 둔다.

`report.html` 은 차트를 붙이지만, 인터넷이 없으면 표만 남는다. 그때 화면이
**왜 안 보이는지 적는다.** 아무 설명 없이 빈 칸이 있으면 고장으로 보인다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from shared.ai_label import add_text_label

from exam_drill.metrics import (
    Analysis, PASS_AVERAGE, PASS_SUBJECT, TARGET_SECONDS, MIN_SAMPLE,
)
from exam_drill.records import REASON_FIX, REASON_LABEL

__all__ = ["write_markdown", "write_html", "DISCLAIMER", "CHART_JS"]

CHART_JS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.3/chart.umd.min.js"

DISCLAIMER = (
    "이 표는 **본인이 적은 풀이 기록**만 가지고 계산한 것입니다. "
    "실제 시험 점수나 합격을 예측하지 않습니다. "
    "문제 지문과 보기는 이 프로그램에 들어 있지 않고, 보고서에도 실리지 않습니다."
)


def _subject_table(analysis: Analysis) -> list[str]:
    lines = ["| 과목 | 푼 문항 | 정답 | 환산 점수 | 과락선까지 | 문항당 | 잦은 이유 |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for item in analysis.subjects:
        mark = " ⚠" if item.failing else ""
        margin = f"{item.margin:+.1f}" if item.failing else "넘김"
        slow = " ⚠" if item.too_slow else ""
        lines.append(
            f"| {item.name}{mark} | {item.total} | {item.correct} | "
            f"**{item.score}점** | {margin} | {item.median_seconds}초{slow} | "
            f"{item.top_reason or '—'} |")
    return lines


def write_markdown(analysis: Analysis, out_dir: str | Path,
                   plan: list[str] | None = None, demo: bool = False,
                   ai_label_on: bool = True) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    lines = [f"# 풀이 기록 분석 — {today}", ""]
    if demo:
        lines += ["> **샘플 자료로 만든 보고서입니다. 숫자는 지어낸 것입니다.**", ""]
    lines += [f"> {DISCLAIMER}", "", "## 한 줄 판정", "", analysis.verdict, ""]

    if analysis.failing:
        lines += ["## ⚠ 과락 위험", "",
                  "공인중개사는 **매 과목 40점 이상**이어야 합니다. "
                  "평균이 아무리 높아도 한 과목이 40점 아래면 불합격입니다.", ""]
        for item in analysis.failing:
            lines.append(f"- **{item.name}** {item.score}점 — {item.margin}점 모자랍니다")
        lines.append("")

    lines += ["## 과목별", ""] + _subject_table(analysis) + [""]
    lines += [f"전 과목 평균 **{analysis.average}점** (합격선 {PASS_AVERAGE}점)"]
    if analysis.untouched:
        names = ", ".join(item.name for item in analysis.untouched)
        lines += ["",
                  f"> 아직 한 문제도 안 푼 과목이 있습니다: **{names}**. "
                  f"위 평균에는 들어 있지 않습니다."]
    lines.append("")

    lines += ["## 약한 단원", "",
              f"{MIN_SAMPLE}문항 이상 푼 단원만 셉니다. "
              f"한두 문제로는 잘하는지 못하는지 알 수 없습니다.", "",
              "| 과목 | 단원 | 푼 문항 | 정답률 | 잦은 이유 |", "|---|---|---:|---:|---|"]
    for unit in analysis.weakest[:12]:
        subject = next((s.name for s in analysis.subjects if s.key == unit.subject), unit.subject)
        lines.append(f"| {subject} | {unit.unit} | {unit.total} | "
                     f"**{unit.rate}%** | {unit.top_reason or '—'} |")
    lines.append("")

    if analysis.reasons:
        total = sum(analysis.reasons.values())
        lines += ["## 왜 틀렸나", "",
                  "이유마다 **해야 할 일이 다릅니다.** 이게 이 표에서 제일 쓸모 있는 부분입니다.", "",
                  "| 이유 | 건수 | 비중 | 해야 할 일 |", "|---|---:|---:|---|"]
        for reason, count in analysis.reasons.most_common():
            share = round(count / total * 100, 1)
            lines.append(f"| {REASON_LABEL.get(reason, reason)} | {count} | "
                         f"{share}% | {REASON_FIX.get(reason, '')} |")
        lines.append("")

    lines += ["## 시간", "",
              f"한 과목 50분에 40문항이니 문항당 **{TARGET_SECONDS}초**가 기준입니다.", ""]
    for item in analysis.subjects:
        if item.median_seconds:
            verdict = "느립니다" if item.too_slow else "괜찮습니다"
            lines.append(f"- {item.name}: 중앙값 {item.median_seconds}초 — {verdict}")
    lines.append("")

    if plan:
        lines += ["## 다음 2주", ""] + [f"{index}. {line}" for index, line in enumerate(plan, 1)] + [""]

    lines += ["---", "",
              "### 이 프로그램이 하지 않는 것", "",
              "- 기출문제 지문·보기·정답을 담거나 배포하지 않습니다",
              "- 시험 점수를 예측하거나 합격을 약속하지 않습니다",
              "- 문제를 새로 지어내지 않습니다 (틀린 문제와 비슷한 문제를 만들어 주지 않습니다)", ""]

    body = "\n".join(lines)
    if ai_label_on and plan:
        body = add_text_label(body)

    path = out_dir / f"report_{today}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _bar_data(pairs: list[tuple[str, float]]) -> tuple[str, str]:
    labels = ", ".join(f'"{name}"' for name, _ in pairs)
    values = ", ".join(str(value) for _, value in pairs)
    return labels, values


def write_html(analysis: Analysis, out_dir: str | Path,
               plan: list[str] | None = None, demo: bool = False) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    subject_labels, subject_values = _bar_data(
        [(item.name, item.score) for item in analysis.subjects])
    colors = ", ".join(
        '"#c1341f"' if item.failing else '"#1f5eff"' for item in analysis.subjects)
    unit_labels, unit_values = _bar_data(
        [(unit.unit, unit.rate) for unit in analysis.weakest[:8]])
    reason_labels, reason_values = _bar_data(
        [(REASON_LABEL.get(name, name), float(count))
         for name, count in analysis.reasons.most_common()])

    rows = "".join(
        f"<tr><td>{item.name}</td><td class='n'>{item.total}</td>"
        f"<td class='n'><b>{item.score}</b></td>"
        f"<td class='n'>{item.median_seconds}초</td>"
        f"<td>{item.top_reason or '—'}</td>"
        f"<td>{'⚠ 과락 위험' if item.failing else '통과'}</td></tr>"
        for item in analysis.subjects)

    plan_html = ("<ol>" + "".join(f"<li>{line}</li>" for line in plan) + "</ol>") if plan else ""
    demo_html = ('<p class="warn">샘플 자료로 만든 보고서입니다. 숫자는 지어낸 것입니다.</p>'
                 if demo else "")

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>풀이 기록 분석 {today}</title>
<script src="{CHART_JS}"></script>
<style>
  body {{ font-family: -apple-system, "Malgun Gothic", sans-serif; margin: 0;
         background: #f7f8fa; color: #1a1d23; }}
  .wrap {{ max-width: 900px; margin: 0 auto; padding: 28px 20px 60px; }}
  h1 {{ font-size: 24px; margin: 0 0 4px; }}
  .card {{ background: #fff; border: 1px solid #e4e7ec; border-radius: 10px;
           padding: 18px 20px; margin-bottom: 14px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th, td {{ padding: 8px 6px; border-bottom: 1px solid #eef0f4; text-align: left; }}
  td.n, th.n {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .verdict {{ font-size: 17px; font-weight: 700; }}
  .warn {{ color: #9a6400; background: #fdf3e0; padding: 10px 14px; border-radius: 8px; }}
  .bad {{ color: #c1341f; background: #fdeceb; padding: 10px 14px; border-radius: 8px; }}
  .muted {{ color: #697086; font-size: 13px; }}
  .fallback {{ display: none; }}
  canvas {{ max-height: 260px; }}
</style></head>
<body><div class="wrap">
<h1>풀이 기록 분석</h1>
<p class="muted">{today} · 푼 문항 {analysis.attempts}개 · 회차 {', '.join(analysis.rounds) or '미상'}</p>
{demo_html}

<div class="card">
  <p class="verdict">{analysis.verdict}</p>
  <p class="muted">{DISCLAIMER}</p>
</div>

<div class="card">
  <h2>과목별 환산 점수</h2>
  <canvas id="subjects"></canvas>
  <p class="fallback warn" id="fb1">차트를 불러오지 못했습니다(인터넷이 없거나 막혀 있습니다).
     아래 표의 숫자는 그대로입니다.</p>
  <table>
    <tr><th>과목</th><th class="n">푼 문항</th><th class="n">환산</th>
        <th class="n">문항당</th><th>잦은 이유</th><th>과락</th></tr>
    {rows}
  </table>
  <p class="muted">전 과목 평균 <b>{analysis.average}점</b> · 합격선 {PASS_AVERAGE}점 ·
     과목 과락선 {PASS_SUBJECT}점</p>
</div>

<div class="card">
  <h2>약한 단원</h2>
  <canvas id="units"></canvas>
  <p class="muted">{MIN_SAMPLE}문항 이상 푼 단원만 셉니다.</p>
</div>

<div class="card">
  <h2>왜 틀렸나</h2>
  <canvas id="reasons"></canvas>
  <p class="muted">이유마다 해야 할 일이 다릅니다. 자세한 것은 마크다운 보고서에 있습니다.</p>
</div>

{'<div class="card"><h2>다음 2주</h2>' + plan_html + '</div>' if plan else ''}

<div class="card">
  <h2>이 프로그램이 하지 않는 것</h2>
  <ul>
    <li>기출문제 지문·보기·정답을 담거나 배포하지 않습니다</li>
    <li>시험 점수를 예측하거나 합격을 약속하지 않습니다</li>
    <li>틀린 문제와 비슷한 문제를 지어내지 않습니다</li>
  </ul>
</div>
</div>
<script>
(function () {{
  if (typeof Chart === "undefined") {{
    document.querySelectorAll("canvas").forEach(function (el) {{ el.style.display = "none"; }});
    document.querySelectorAll(".fallback").forEach(function (el) {{ el.style.display = "block"; }});
    return;
  }}
  var bar = function (id, labels, values, colors) {{
    var el = document.getElementById(id);
    if (!el) return;
    new Chart(el, {{
      type: "bar",
      data: {{ labels: labels, datasets: [{{ data: values, backgroundColor: colors }}] }},
      options: {{ plugins: {{ legend: {{ display: false }} }},
                 scales: {{ y: {{ beginAtZero: true }} }} }}
    }});
  }};
  bar("subjects", [{subject_labels}], [{subject_values}], [{colors}]);
  bar("units", [{unit_labels}], [{unit_values}], "#9a6400");
  bar("reasons", [{reason_labels}], [{reason_values}], "#1f5eff");
}})();
</script>
</body></html>
"""
    path = out_dir / f"report_{today}.html"
    path.write_text(html, encoding="utf-8")
    return path
