"""수집기 — 하루 한 번 돌린다.

    python collector.py run                    키가 있을 때
    python collector.py run --fixture          키 없이 샘플 자료로
    python collector.py status                 얼마나 쌓였는지
    python collector.py keywords               지켜보는 키워드 목록

왜 매일 돌려야 하는가
    **유튜브 API 는 시계열을 주지 않는다.** "어제 조회수가 몇이었는지" 를 물을
    방법이 없고, 지금 값만 준다. 그래서 매일 한 번 찍어 두는 것 말고는
    "이 키워드가 뜨고 있는지" 를 알 길이 없다.

    하루 이틀은 아무것도 안 보인다. **2주쯤 지나야** 뭔가 보이기 시작한다.
    이게 이 상품에서 가장 정직하게 말해야 하는 부분이다.

쿼터
    하루 10,000 유닛. search 한 번에 100 유닛이라 키워드 80개가 상한이다.
    넘치면 버리지 않고 다음 날로 넘긴다(`state.json`).

cron 으로 매일 돌리기

    0 6 * * *  cd /path/to/niche-research && /usr/bin/python3 collector.py run >> collect.log 2>&1

n8n 으로 돌리기
    Schedule Trigger(매일 06:00) → Execute Command(위 명령) 두 노드면 됩니다.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parents[1]))

from niche.quota import (                                            # noqa: E402
    DAILY_UNITS, DEFAULT_KEYWORD_LIMIT, QuotaExceeded, QuotaState, plan_today,
)
from niche.store import Store, VideoRow                              # noqa: E402
from niche.youtube import (                                          # noqa: E402
    LOOKBACK_DAYS, SHORT_MAX_SECONDS, YouTubeError, make_client, parse_duration,
)

DEFAULT_KEYWORDS = BASE_DIR / "keywords.txt"
DEFAULT_DB = Path(os.getenv("NICHE_DB_PATH", str(BASE_DIR / "niche.db")))
DEFAULT_STATE = Path(os.getenv("NICHE_STATE_PATH", str(BASE_DIR / "state.json")))
FIXTURE_DIR = BASE_DIR / "data" / "fixtures"


def read_keywords(path: str | Path = DEFAULT_KEYWORDS) -> list[str]:
    """키워드 목록. `#` 로 시작하는 줄과 빈 줄은 건너뛴다."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"키워드 파일이 없습니다: {path}")

    words: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line not in words:
            words.append(line)
    return words


def _to_rows(search_items: list[dict], detail_items: list[dict]) -> list[VideoRow]:
    """search 결과와 videos 결과를 합쳐 한 줄씩 만든다."""
    details = {item.get("id"): item for item in detail_items}
    rows: list[VideoRow] = []

    for item in search_items:
        video_id = (item.get("id") or {}).get("videoId", "")
        if not video_id:
            continue
        snippet = item.get("snippet") or {}
        detail = details.get(video_id, {})
        stats = detail.get("statistics") or {}
        content = detail.get("contentDetails") or {}
        seconds = parse_duration(content.get("duration", ""))

        rows.append(VideoRow(
            video_id=video_id,
            channel_id=snippet.get("channelId", ""),
            title=snippet.get("title", ""),
            published_at=snippet.get("publishedAt", ""),
            duration_sec=seconds,
            # 길이를 못 읽은 것은 쇼츠로 치지 않는다. 모르면 아니라고 보는 편이
            # 낫다 — 쇼츠 비중이 부풀면 판단이 틀어진다.
            is_short=0 < seconds <= SHORT_MAX_SECONDS,
            views=int(stats.get("viewCount", 0) or 0),
            likes=int(stats.get("likeCount", 0) or 0),
            comments=int(stats.get("commentCount", 0) or 0),
        ))
    return rows


def _channel_rows(items: list[dict]) -> list[dict]:
    rows = []
    for item in items:
        stats = item.get("statistics") or {}
        snippet = item.get("snippet") or {}
        rows.append({
            "channel_id": item.get("id", ""),
            "title": snippet.get("title", ""),
            "created_at": snippet.get("publishedAt", ""),
            "subscribers": int(stats.get("subscriberCount", 0) or 0),
            "total_views": int(stats.get("viewCount", 0) or 0),
            "video_count": int(stats.get("videoCount", 0) or 0),
        })
    return rows


def collect_one(keyword: str, client, store: Store, state: QuotaState,
                snapshot_date: str = "") -> dict:
    """키워드 하나를 훑는다. 유닛은 **쓰기 전에** 확인한다."""
    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
             ).strftime("%Y-%m-%dT%H:%M:%SZ")

    state.spend("search.list")
    found = client.search(keyword, published_after=since)

    video_ids = [(item.get("id") or {}).get("videoId", "") for item in found]
    video_ids = [value for value in video_ids if value]

    details: list[dict] = []
    if video_ids:
        state.spend("videos.list")
        details = client.videos(video_ids)

    rows = _to_rows(found, details)
    store.save_videos(keyword, rows, snapshot_date)

    channel_ids = [row.channel_id for row in rows if row.channel_id]
    channels: list[dict] = []
    if channel_ids:
        state.spend("channels.list")
        channels = _channel_rows(client.channels(channel_ids))
        store.save_channels(channels, snapshot_date)

    state.finish(keyword)
    return {"keyword": keyword, "videos": len(rows), "channels": len(channels)}


def cmd_run(args: argparse.Namespace) -> int:
    keywords = read_keywords(args.keywords)
    store = Store(args.db)
    snapshot_date = args.date or date.today().isoformat()
    # `--date` 는 "그날인 셈 치고" 돌리는 스위치다. 쿼터 상태의 날짜도 같이
    # 옮겨야 지난 날짜를 메울 때 오늘 몫을 잡아먹지 않는다.
    state = QuotaState.load(args.state, limit=args.limit, today=snapshot_date)

    try:
        client = make_client(FIXTURE_DIR if args.fixture else None)
    except YouTubeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.fixture:
        print("샘플 자료로 돕니다 (--fixture) — 유튜브를 부르지 않습니다")

    today, carried = plan_today(keywords, state)
    print(f"키워드 {len(keywords)}개 중 오늘 {len(today)}개를 봅니다"
          f" (상한 {state.limit}개 · 남은 유닛 {state.remaining_units:,})")
    if carried:
        print(f"  {len(carried)}개는 내일로 넘깁니다: "
              f"{', '.join(carried[:5])}{' …' if len(carried) > 5 else ''}")

    collected = []
    for index, keyword in enumerate(today, start=1):
        try:
            result = collect_one(keyword, client, store, state, snapshot_date)
        except QuotaExceeded as exc:
            print(f"\n{exc}", file=sys.stderr)
            carried = today[index - 1:] + carried
            break
        except YouTubeError as exc:
            # 키워드 하나가 실패해도 나머지는 계속한다. 하루가 통째로 빠지는
            # 것보다 한 줄이 비는 편이 낫다.
            print(f"  ✗ {keyword} — {str(exc).splitlines()[0]}")
            continue
        collected.append(result)
        print(f"  [{index}/{len(today)}] {keyword} — 영상 {result['videos']}개"
              f" · 채널 {result['channels']}개")

    state.carried = list(dict.fromkeys(carried))
    state.save()

    counts = store.counts()
    print()
    print(f"오늘 {len(collected)}개 키워드 · 유닛 {state.used_units:,}/{DAILY_UNITS:,}")
    print(f"쌓인 것: 영상 {counts['videos']:,}개 · 스냅샷 {counts['video_snapshots']:,}줄"
          f" · **{counts['days']}일치**")

    if counts["days"] < 3:
        print()
        print("  아직 며칠치가 안 쌓였습니다. 분석은 3일치부터 뜻이 생기고,")
        print("  주간 추이는 2주쯤 지나야 보입니다. 매일 한 번씩 돌려 주세요.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = Store(args.db)
    state = QuotaState.load(args.state, limit=args.limit)
    counts = store.counts()
    dates = store.snapshot_dates()

    print(f"자료 창고: {store.path}")
    print(f"  키워드 {counts['keywords']}개 · 영상 {counts['videos']:,}개"
          f" · 채널 {counts['channels']:,}개")
    print(f"  스냅샷 {counts['video_snapshots']:,}줄 · {counts['days']}일치")
    if dates:
        print(f"  기간: {dates[0]} ~ {dates[-1]}")

        # 빠진 날이 있는지 본다. 구멍이 있으면 추이가 왜곡된다.
        first = date.fromisoformat(dates[0])
        last = date.fromisoformat(dates[-1])
        expected = (last - first).days + 1
        if expected > len(dates):
            missing = expected - len(dates)
            print(f"  ⚠ 빠진 날이 {missing}일 있습니다. 매일 돌려야 추이가 맞습니다")

    print()
    print(f"오늘 쓴 유닛: {state.used_units:,}/{DAILY_UNITS:,}"
          f" · 더 볼 수 있는 키워드 {state.remaining_keywords}개")
    if state.carried:
        print(f"내일로 밀린 키워드 {len(state.carried)}개: {', '.join(state.carried[:5])}")
    return 0


def cmd_keywords(args: argparse.Namespace) -> int:
    keywords = read_keywords(args.keywords)
    store = Store(args.db)
    known = {row["keyword"]: row["added_at"] for row in store.keywords()}

    print(f"{len(keywords)}개 (파일: {args.keywords})")
    print()
    for keyword in keywords:
        added = known.get(keyword, "")
        mark = f"  {added}부터" if added else "  아직 안 봄"
        print(f"  {keyword:<24}{mark}")

    if len(keywords) > args.limit:
        print()
        print(f"⚠ 하루 상한 {args.limit}개를 넘습니다. "
              f"{len(keywords) - args.limit}개는 다음 날로 넘어갑니다.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collector.py",
        description="유튜브에서 키워드별 영상·채널 지표를 매일 모읍니다")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--keywords", default=str(DEFAULT_KEYWORDS))
    parser.add_argument("--limit", type=int, default=DEFAULT_KEYWORD_LIMIT,
                        help=f"하루에 볼 키워드 수 상한 (기본 {DEFAULT_KEYWORD_LIMIT})")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="오늘치를 모읍니다")
    run.add_argument("--fixture", action="store_true",
                     help="유튜브를 부르지 않고 샘플 자료로 돕니다 (키가 없어도 됩니다)")
    run.add_argument("--date", default="", help="스냅샷 날짜를 직접 지정 (YYYY-MM-DD)")
    run.set_defaults(func=cmd_run)

    status = subparsers.add_parser("status", help="얼마나 쌓였는지 봅니다")
    status.set_defaults(func=cmd_status)

    keywords = subparsers.add_parser("keywords", help="지켜보는 키워드 목록")
    keywords.set_defaults(func=cmd_keywords)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n예: python collector.py run --fixture", file=sys.stderr)
        return 1
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"파일을 찾지 못했습니다: {exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
