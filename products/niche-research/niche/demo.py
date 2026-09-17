"""시연용 자료 — 샘플 픽스처로 **며칠치**를 만들어 준다.

수집기는 하루에 한 번 찍는다. 그래서 갓 설치한 사람은 하루치밖에 없고,
분석기를 돌려도 볼 것이 없다. 그게 정상이지만, **무엇이 나오는지 보기 전에는
설치할 마음이 안 든다.**

그래서 샘플 자료로 여러 날치를 만들어 둔다. 날이 갈수록 조회수와 구독자가
조금씩 느는 곡선을 씌운다.

⚠️ **이건 지어낸 숫자다.** 분석 결과에도 그렇게 적힌다. 진짜 판단은 본인
키워드로 2주쯤 모은 뒤에 하는 것이다.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from niche.store import Store, VideoRow
from niche.youtube import SHORT_MAX_SECONDS, parse_duration

__all__ = ["seed_demo", "DEMO_DAYS", "DAILY_GROWTH"]

#: 만들 날수. 3일이면 분석기의 다섯 지표가 모두 계산된다.
DEMO_DAYS = 3

#: 하루에 이만큼씩 는다고 친다. 키워드마다 다르게 준다.
DAILY_GROWTH = {"자취 요리 10분": 0.04, "소상공인 세금": 0.09,
                "전기차 충전 실사용": 0.06}


def seed_demo(store: Store, fixture_dir: Path, days: int = DEMO_DAYS,
              end: str = "") -> list[str]:
    """샘플 자료로 `days` 일치 스냅샷을 만든다. 만든 날짜들을 돌려준다."""
    fixture_dir = Path(fixture_dir)
    last = date.fromisoformat(end) if end else date.today()
    made: list[str] = []

    for path in sorted(fixture_dir.glob("*.json")):
        keyword = path.stem
        payload = json.loads(path.read_text(encoding="utf-8"))
        details = {item["id"]: item for item in payload.get("videos", [])}
        growth = DAILY_GROWTH.get(keyword, 0.05)

        for offset in range(days - 1, -1, -1):
            day = (last - timedelta(days=offset)).isoformat()
            # 오래된 날일수록 숫자가 작다. 며칠에 걸쳐 는 것처럼 보이게.
            factor = (1 + growth) ** -offset

            rows: list[VideoRow] = []
            for item in payload.get("search", []):
                video_id = item["id"]["videoId"]
                snippet = item["snippet"]
                detail = details.get(video_id, {})
                stats = detail.get("statistics", {})
                seconds = parse_duration(
                    (detail.get("contentDetails") or {}).get("duration", ""))
                views = int(int(stats.get("viewCount", 0)) * factor)
                rows.append(VideoRow(
                    video_id=video_id,
                    channel_id=snippet["channelId"],
                    title=snippet["title"],
                    published_at=snippet["publishedAt"],
                    duration_sec=seconds,
                    is_short=0 < seconds <= SHORT_MAX_SECONDS,
                    views=views,
                    likes=int(int(stats.get("likeCount", 0)) * factor),
                    comments=int(int(stats.get("commentCount", 0)) * factor),
                ))
            store.save_videos(keyword, rows, day)

            channels = []
            for item in payload.get("channels", []):
                stats = item.get("statistics", {})
                channels.append({
                    "channel_id": item["id"],
                    "title": item.get("snippet", {}).get("title", ""),
                    "created_at": item.get("snippet", {}).get("publishedAt", ""),
                    "subscribers": int(int(stats.get("subscriberCount", 0)) * factor),
                    "total_views": int(int(stats.get("viewCount", 0)) * factor),
                    "video_count": int(stats.get("videoCount", 0)),
                })
            store.save_channels(channels, day)

            if day not in made:
                made.append(day)

    return sorted(made)
