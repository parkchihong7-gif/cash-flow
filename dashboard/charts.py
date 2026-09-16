"""막대그래프를 직접 그린다.

그래프 라이브러리를 쓰지 않는다. 이 대시보드는 내 PC 에서 도는 도구라
**인터넷이 없어도 열려야 한다.** CDN 에서 받아 오는 라이브러리를 쓰면
비행기 안이나 회사 방화벽 뒤에서 그래프가 빈칸이 된다.

막대 몇 개를 그리는 데 필요한 것은 사각형 좌표 계산뿐이라, 파이썬에서 자리를
잡아 템플릿이 SVG 로 그린다. 값이 서버에서 이미 정해지므로 화면에서 계산할 것도 없다.

색은 한 가지만 쓴다. 막대의 색이 무엇을 뜻하지 않고 **길이만 뜻하기** 때문이다.
여러 색을 쓰면 색이 뜻을 갖는 줄 알게 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Bar", "BarChart", "monthly_chart", "program_chart"]

#: 그림판 크기. viewBox 안에서만 그리므로 화면 크기와는 무관하다.
WIDTH = 720
HEIGHT = 190
PAD_TOP = 18
PAD_BOTTOM = 26
BAR_GAP = 6


@dataclass
class Bar:
    x: float
    y: float
    width: float
    height: float
    label: str
    value: int
    caption: str = ""
    highlight: bool = False


@dataclass
class BarChart:
    bars: list[Bar] = field(default_factory=list)
    width: int = WIDTH
    height: int = HEIGHT
    baseline: float = HEIGHT - PAD_BOTTOM
    peak: int = 0
    total: int = 0
    empty: bool = True


def _nice_peak(values: list[int]) -> int:
    """가장 큰 값보다 조금 위에서 눈금을 끊는다. 막대가 천장에 닿지 않게."""
    top = max(values or [0])
    return int(top * 1.15) if top > 0 else 1


def monthly_chart(series: list[dict]) -> BarChart:
    """월별 매출 세로 막대. `db.monthly_revenue()` 결과를 받는다."""
    chart = BarChart()
    if not series:
        return chart

    amounts = [row["amount"] for row in series]
    chart.peak = _nice_peak(amounts)
    chart.total = sum(amounts)
    chart.empty = chart.total == 0

    usable = HEIGHT - PAD_TOP - PAD_BOTTOM
    slot = WIDTH / len(series)
    bar_width = max(6.0, slot - BAR_GAP)
    last = len(series) - 1

    for index, row in enumerate(series):
        height = (row["amount"] / chart.peak) * usable if chart.peak else 0
        # 0원인 달도 자리는 있어야 추이가 안 왜곡된다. 아주 낮은 막대로 둔다.
        height = max(height, 1.5)
        chart.bars.append(Bar(
            x=index * slot + BAR_GAP / 2,
            y=chart.baseline - height,
            width=bar_width,
            height=height,
            label=row["label"],
            value=row["amount"],
            caption=f"{row['month']} · {row['deals']}건",
            highlight=index == last,
        ))
    return chart


def program_chart(rows: list[dict], names: dict[str, str],
                  limit: int = 8) -> BarChart:
    """프로그램별 매출 가로 막대. 많이 판 순서."""
    rows = [row for row in rows if row["amount"] > 0][:limit]
    chart = BarChart(height=max(40, len(rows) * 30 + 8))
    if not rows:
        return chart

    chart.peak = _nice_peak([row["amount"] for row in rows])
    chart.total = sum(row["amount"] for row in rows)
    chart.empty = False

    label_width = 200
    track = WIDTH - label_width - 110       # 오른쪽에 금액을 적을 자리를 남긴다

    for index, row in enumerate(rows):
        width = (row["amount"] / chart.peak) * track if chart.peak else 0
        chart.bars.append(Bar(
            x=label_width,
            y=index * 30 + 4,
            width=max(2.0, width),
            height=20,
            label=names.get(row["program_id"], row["program_id"]),
            value=row["amount"],
            caption=f"{row['deals']}건",
            highlight=index == 0,
        ))
    return chart
