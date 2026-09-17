"""지표 다섯 가지 — **키워드·포맷 단위로만** 본다.

이 파일에 없는 것이 이 상품의 정체성이다.

    ❌ "이 영상이 터졌으니 따라 만드세요"
    ❌ "이 채널의 포맷을 베끼세요"
    ❌ 영상 제목·채널명으로 순위 매기기

노아AI(주언규)가 "터진 영상 찾아서 따라 만들기" 로 표절 논란을 겪고 2023년 2월에
서비스를 닫고 전액 환불했다(CLAUDE.md §3-1). 같은 길을 가지 않는다.

여기서 보는 것은 **시장의 모양**이다.

    1. 공급 증가율     이 키워드에 새 영상이 늘고 있나 줄고 있나
    2. 공백 지수       수요(중앙값 조회수) 대비 공급(영상 수)
    3. 소형 채널 성과율 구독자 1만 이하가 구독자의 5배 넘게 본 비율
    4. 쇼츠 vs 롱폼    어느 쪽이 더 보이나
    5. 채널 성장률     구독자가 7일 동안 얼마나 늘었나

3번이 제일 중요하다. **작은 채널이 뚫고 있는 키워드**가 지금 들어갈 만한 곳이다.
큰 채널만 잘되는 곳은 이미 자리가 굳은 곳이다.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

__all__ = [
    "SMALL_CHANNEL_MAX", "BREAKOUT_MULTIPLE", "GROWTH_WINDOW_DAYS",
    "KeywordMetrics", "analyze_keyword", "analyze_all", "gap_index",
]

#: 이 수 이하를 '소형 채널' 로 본다.
SMALL_CHANNEL_MAX = 10_000

#: 구독자의 몇 배를 넘겨 봐야 '뚫었다' 고 볼 것인가.
BREAKOUT_MULTIPLE = 5

#: 채널 성장률을 며칠 간격으로 볼 것인가.
GROWTH_WINDOW_DAYS = 7

#: 주간 추이를 만들 최소 주 수.
MIN_WEEKS = 2


def gap_index(median_views: int, new_videos: int) -> float:
    """수요 대비 공급 지수. **높을수록 공백**이다.

    중앙값 조회수를 신규 영상 수로 나눈다. 사람들이 많이 보는데 만드는 사람이
    적으면 커진다.

    평균이 아니라 중앙값을 쓰는 이유는, 영상 하나가 크게 터지면 평균이 통째로
    끌려가기 때문이다. 그 하나는 시장의 모양이 아니라 예외다.
    """
    if new_videos <= 0:
        return 0.0
    return round(median_views / new_videos, 1)


@dataclass
class KeywordMetrics:
    """키워드 하나의 지표 묶음."""

    keyword: str
    snapshot_date: str = ""
    videos: int = 0                       # 최근 30일 신규 영상 수
    channels: int = 0

    # 1. 공급 증가율
    weekly_counts: list[dict] = field(default_factory=list)
    supply_growth: float = 0.0            # 최근 주 / 직전 주 - 1 (%)

    # 2. 공백 지수
    median_views: int = 0
    gap: float = 0.0

    # 3. 소형 채널 성과율
    small_channel_videos: int = 0
    small_channel_breakouts: int = 0
    breakout_rate: float = 0.0            # %

    # 4. 쇼츠 vs 롱폼
    shorts: int = 0
    longform: int = 0
    shorts_median: int = 0
    longform_median: int = 0

    # 5. 채널 성장률
    channel_growth: float = 0.0           # 7일 구독자 증가율 중앙값 (%)
    growth_samples: int = 0

    notes: list[str] = field(default_factory=list)

    @property
    def shorts_ratio(self) -> float:
        total = self.shorts + self.longform
        return round(self.shorts / total * 100, 1) if total else 0.0

    @property
    def entry_friendly(self) -> bool:
        """지금 들어갈 만한가. **소형 채널이 뚫고 있는가**가 기준이다."""
        return self.breakout_rate >= 20 and self.videos > 0

    def as_row(self) -> dict:
        return {
            "키워드": self.keyword,
            "신규 영상": self.videos,
            "중앙값 조회수": self.median_views,
            "공백 지수": self.gap,
            "소형 채널 성과율": self.breakout_rate,
            "쇼츠 비중": self.shorts_ratio,
            "공급 증가율": self.supply_growth,
            "채널 성장률": self.channel_growth,
        }


def _median(values: list[int]) -> int:
    return int(statistics.median(values)) if values else 0


def _weekly_counts(published: list[str], today: date, weeks: int = 4) -> list[dict]:
    """주 단위 신규 영상 수. 최근 주가 마지막에 온다."""
    buckets: list[dict] = []
    for index in range(weeks - 1, -1, -1):
        end = today - timedelta(days=7 * index)
        start = end - timedelta(days=6)
        count = 0
        for stamp in published:
            try:
                when = datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
            except ValueError:
                continue
            if start <= when <= end:
                count += 1
        buckets.append({"start": start.isoformat(), "end": end.isoformat(),
                        "count": count})
    return buckets


def analyze_keyword(keyword: str, rows: list, store=None,
                    today: date | None = None) -> KeywordMetrics:
    """키워드 하나를 지표로 바꾼다.

    Args:
        keyword: 키워드.
        rows: `Store.videos_for()` 결과 (그날 스냅샷이 붙은 영상들).
        store: 채널 성장률을 보려면 필요하다. 없으면 그 지표만 0.
        today: 주 단위를 자를 기준 날. 비우면 오늘.
    """
    today = today or date.today()
    metrics = KeywordMetrics(keyword=keyword, videos=len(rows))
    if not rows:
        metrics.notes.append("이 키워드로 모은 영상이 없습니다")
        return metrics

    metrics.snapshot_date = str(rows[0]["snapshot_date"]) if "snapshot_date" in \
        rows[0].keys() else ""

    views = [int(row["views"] or 0) for row in rows]
    metrics.median_views = _median(views)
    metrics.gap = gap_index(metrics.median_views, metrics.videos)

    # 1. 공급 증가율 — 최근 주와 직전 주를 견준다
    metrics.weekly_counts = _weekly_counts(
        [str(row["published_at"]) for row in rows], today)
    if len(metrics.weekly_counts) >= 2:
        latest = metrics.weekly_counts[-1]["count"]
        previous = metrics.weekly_counts[-2]["count"]
        if previous:
            metrics.supply_growth = round((latest / previous - 1) * 100, 1)
        elif latest:
            metrics.supply_growth = 100.0
            metrics.notes.append("직전 주에 영상이 없어 증가율은 참고만 하세요")

    # 3. 소형 채널 성과율
    for row in rows:
        subscribers = int(row["subscribers"] or 0)
        if not subscribers or subscribers > SMALL_CHANNEL_MAX:
            continue
        metrics.small_channel_videos += 1
        if int(row["views"] or 0) >= subscribers * BREAKOUT_MULTIPLE:
            metrics.small_channel_breakouts += 1
    if metrics.small_channel_videos:
        metrics.breakout_rate = round(
            metrics.small_channel_breakouts / metrics.small_channel_videos * 100, 1)
    else:
        metrics.notes.append("구독자 1만 이하 채널의 영상이 없어 진입 가능성은 못 봤습니다")

    # 4. 쇼츠 vs 롱폼
    short_views = [int(row["views"] or 0) for row in rows if row["is_short"]]
    long_views = [int(row["views"] or 0) for row in rows if not row["is_short"]]
    metrics.shorts = len(short_views)
    metrics.longform = len(long_views)
    metrics.shorts_median = _median(short_views)
    metrics.longform_median = _median(long_views)

    # 5. 채널 성장률 — 7일 전 스냅샷과 견준다
    if store is not None:
        rates: list[float] = []
        for channel_id in {str(row["channel_id"]) for row in rows}:
            snapshots = store.channel_snapshots(channel_id)
            if len(snapshots) < 2:
                continue
            last = snapshots[-1]
            target = date.fromisoformat(str(last["snapshot_date"])) - timedelta(
                days=GROWTH_WINDOW_DAYS)
            # 7일 전에 가장 가까운 스냅샷을 쓴다. 없으면 가장 오래된 것.
            older = min(
                snapshots[:-1],
                key=lambda row: abs(date.fromisoformat(str(row["snapshot_date"])) - target))
            before = int(older["subscribers"] or 0)
            after = int(last["subscribers"] or 0)
            if before > 0:
                rates.append((after / before - 1) * 100)
        if rates:
            metrics.channel_growth = round(statistics.median(rates), 2)
            metrics.growth_samples = len(rates)
        else:
            metrics.notes.append(
                "채널 스냅샷이 아직 이틀치가 안 돼 성장률은 못 봤습니다")

    return metrics


def analyze_all(store, keywords: list[str] | None = None,
                today: date | None = None) -> list[KeywordMetrics]:
    """전체 키워드를 지표로 바꾼다. **공백 지수 높은 순**으로 돌려준다."""
    names = keywords or [str(row["keyword"]) for row in store.keywords()]
    snapshot_date = store.latest_snapshot_date()

    results: list[KeywordMetrics] = []
    for keyword in names:
        rows = store.videos_for(keyword, snapshot_date)
        metrics = analyze_keyword(keyword, rows, store=store, today=today)
        metrics.snapshot_date = snapshot_date
        results.append(metrics)

    results.sort(key=lambda item: item.gap, reverse=True)
    return results
