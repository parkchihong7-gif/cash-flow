"""터미널 출력.

한글은 터미널에서 두 칸을 차지한다. 글자 수로만 맞추면 표가 어긋나므로
`width()` 가 실제 차지하는 칸 수를 센다.
"""

from __future__ import annotations

import unicodedata

from income_sim.engine import DISCLAIMER, Projection
from income_sim.schema import ModelSpec

__all__ = ["width", "pad", "banner", "won", "format_value", "projection_table",
           "model_header", "sources_table"]


def width(text: str) -> int:
    """터미널에서 차지하는 칸 수."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(text))


def pad(text: str, size: int, align: str = "left") -> str:
    """칸 수 기준으로 자리를 맞춘다."""
    text = str(text)
    space = max(0, size - width(text))
    if align == "right":
        return " " * space + text
    if align == "center":
        left = space // 2
        return " " * left + text + " " * (space - left)
    return text + " " * space


def won(value: float | None, unit: str = "원") -> str:
    if value is None:
        return "—"
    return f"{round(value):,}{unit}"


def format_value(spec, value: float) -> str:
    """값 하나를 사람이 읽는 꼴로.

    `%.4g` 같은 것을 쓰면 100만이 `1e+06` 으로 나온다. 조회수를 100만으로
    바꿔 놓고 화면에 `1e+06` 이 뜨면 잘못 들어간 줄 알게 된다.
    """
    if spec.kind == "rate":
        # % 를 붙인 뒤에 0 을 떼면 "20.0000%" 가 그대로 남는다. 떼고 나서 붙인다.
        text = f"{value * 100:.4f}".rstrip("0").rstrip(".")
        return (text or "0") + "%"
    if spec.kind == "money":
        return f"{round(value):,}원"
    if float(value).is_integer():
        text = f"{int(value):,}"
    else:
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return text + (f" {spec.unit}" if spec.unit else "")


def banner() -> str:
    """모든 출력 맨 위에 붙는 고정 문구."""
    line = "─" * 62
    return f"{line}\n  ⚠ {DISCLAIMER}\n{line}"


def model_header(model: ModelSpec, values: dict[str, float]) -> str:
    changed = [
        f"{p.label} {format_value(p, values[p.key])}"
        for p in model.params if values[p.key] != p.default
    ]
    lines = [f"{model.number}. {model.name} — {model.tagline}"]
    if changed:
        lines.append("  바꾼 값: " + " · ".join(changed))
    else:
        lines.append("  전부 기본값입니다. 본인 수치로 바꿔야 쓸모가 있습니다.")
    return "\n".join(lines)


def projection_table(projection: Projection) -> str:
    """12개월 표와 요약."""
    model = projection.model
    state_keys = [spec.key for spec in model.state]
    state_labels = {spec.key: spec.label for spec in model.state}

    columns = [("월", 4, "right"), ("매출", 14, "right"), ("비용", 13, "right"),
               ("손익", 14, "right"), ("누적", 15, "right"), ("시간", 8, "right")]
    for key in state_keys:
        columns.append((state_labels[key], max(10, width(state_labels[key]) + 2), "right"))

    head = " ".join(pad(name, size, "center") for name, size, _ in columns)
    rule = " ".join("─" * size for _, size, _ in columns)
    lines = [head, rule]

    for row in projection.rows:
        cells = [
            pad(row.month, 4, "right"),
            pad(won(row.revenue), 14, "right"),
            pad(won(row.cost), 13, "right"),
            pad(won(row.profit), 14, "right"),
            pad(won(row.cumulative), 15, "right"),
            pad(f"{row.hours:,.0f}h", 8, "right"),
        ]
        for index, key in enumerate(state_keys):
            size = columns[6 + index][1]
            cells.append(pad(f"{row.state[key]:,.1f}", size, "right"))
        lines.append(" ".join(cells))

    lines.append(rule)

    monthly = projection.monthly_breakeven
    cumulative = projection.cumulative_breakeven
    summary = [
        "",
        f"  12개월 매출      {won(projection.total_revenue)}",
        f"  12개월 비용      {won(projection.total_cost)}",
        f"  12개월 손익      {won(projection.total_profit)}",
        f"  초기 투자        {won(-projection.initial_cost)}",
        f"  최종 잔액        {won(projection.net_after_initial)}",
        "",
        f"  월 손익분기      "
        + (f"{monthly}개월차 (그달 매출이 그달 비용을 넘긴 달)"
           if monthly else "12개월 안에 못 넘깁니다"),
        f"  누적 손익분기    "
        + (f"{cumulative}개월차 (초기 투자까지 갚은 달)"
           if cumulative else "12개월 안에 못 갚습니다"),
        "",
        f"  총 투입 시간     {projection.total_hours:,.0f}시간"
        f" (월 평균 {projection.total_hours / max(1, len(projection.rows)):,.1f}시간)",
        f"  시간당 수익      "
        + (won(projection.hourly) if projection.hourly is not None
           else "— (투입 시간이 0 입니다)"),
    ]

    if projection.hourly is not None:
        if projection.hourly < 0:
            summary.append("                   손해입니다. 시간을 쓸수록 돈이 나갑니다.")
        elif projection.hourly < 10032:
            summary.append("                   2026년 최저임금(시급 10,320원)보다 낮습니다.")

    if model.cautions:
        summary.append("")
        summary.append("  같이 봐야 할 것")
        for note in model.cautions:
            summary.append(f"    · {note}")

    return "\n".join(lines + summary)


def sources_table(model: ModelSpec) -> str:
    """기본값과 그 근거. 숫자를 믿기 전에 봐야 하는 표."""
    lines = [f"{model.number}. {model.name} — 기본값과 근거", ""]
    for spec in model.params:
        shown = format_value(spec, spec.default)
        lines.append(f"  {spec.label} = {shown}")
        lines.append(f"    근거: {spec.source}")
        if spec.help:
            lines.append(f"    참고: {spec.help}")
        lines.append("")
    return "\n".join(lines)
