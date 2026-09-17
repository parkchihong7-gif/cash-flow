"""예약 발행 — 1분마다 큐를 본다.

    python manage.py run                 계속 돌면서 때가 된 것을 올린다
    python manage.py run --dry-run       올리는 척만 한다 (토큰 없어도 됨)
    python manage.py run --once          한 번만 훑고 끝낸다

APScheduler 로 1분마다 `tick()` 을 부른다. 인스타 API 로 예약을 걸지 않고
**우리 쪽에서 때를 기다렸다가 올린다.** Graph API 에 예약 발행이 없기도 하고,
올리기 직전에 사람이 취소할 수 있는 편이 낫기 때문이다.

발행 전에 세 가지를 다시 본다
    1. 상태가 `approved` 인가 — **사람이 승인했는가**
    2. 캡션이 비어 있지 않은가
    3. 하루 한도(기본 25건)를 넘지 않았는가 — 인스타가 24시간에 25건까지 받는다
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from queue_store import Post, QueueStore                            # noqa: E402

__all__ = ["Runner", "TickResult", "DAILY_LIMIT", "run_forever"]

#: 인스타가 24시간에 받아 주는 게시물 수.
DAILY_LIMIT = int(os.getenv("IG_DAILY_LIMIT", "25"))

#: 큐를 보는 간격(초).
TICK_SECONDS = int(os.getenv("TICK_SECONDS", "60"))


@dataclass
class TickResult:
    """한 번 훑은 결과."""

    published: list[int] = field(default_factory=list)
    failed: list[tuple[int, str]] = field(default_factory=list)
    skipped: list[tuple[int, str]] = field(default_factory=list)

    @property
    def quiet(self) -> bool:
        return not (self.published or self.failed or self.skipped)


@dataclass
class Runner:
    """큐를 보고 때가 된 것을 올린다.

    Args:
        store: 발행 큐.
        client: `publisher.InstagramClient`. 없으면 **올리는 척만** 한다.
        dry_run: True 면 실제로 올리지 않는다.
    """

    store: QueueStore
    client: object | None = None
    dry_run: bool = False
    daily_limit: int = DAILY_LIMIT

    def _published_today(self, now: datetime) -> int:
        since = (now - timedelta(hours=24)).isoformat(timespec="seconds")
        return sum(1 for post in self.store.all("published")
                   if post.published_at and post.published_at >= since)

    def tick(self, now: datetime | None = None) -> TickResult:
        """때가 된 것을 올린다. 승인 안 된 것은 건드리지 않는다."""
        now = now or datetime.now()
        result = TickResult()
        used = self._published_today(now)

        for post in self.store.due(now.strftime("%Y-%m-%d %H:%M")):
            # 큐 조회가 이미 approved 만 주지만, 발행 직전에 한 번 더 본다.
            # 이 검사가 이 모듈에서 가장 중요한 줄이다.
            if not post.approved:
                result.skipped.append((post.id, "승인되지 않았습니다"))
                continue
            if not post.caption.strip():
                result.skipped.append((post.id, "캡션이 비어 있습니다"))
                continue
            if used >= self.daily_limit:
                result.skipped.append(
                    (post.id, f"24시간 한도 {self.daily_limit}건을 채웠습니다"))
                continue

            if self.dry_run or self.client is None:
                result.skipped.append((post.id, "모의 실행 — 올리지 않았습니다"))
                continue

            try:
                outcome = self.client.publish_post(          # type: ignore[union-attr]
                    post.media_url, post.full_caption, post.media_type)
            except Exception as exc:
                self.store.mark_failed(post.id, f"{type(exc).__name__}: {exc}")
                result.failed.append((post.id, str(exc).splitlines()[0]))
                continue

            self.store.mark_published(post.id, outcome.media_id)
            result.published.append(post.id)
            used += 1

        return result

    def pending(self, now: datetime | None = None) -> list[Post]:
        """아직 승인을 기다리는 것 중 발행 시각이 지난 것.

        이게 쌓여 있으면 **사람이 승인을 안 하고 있다는 뜻**이다.
        조용히 안 올라가는 것보다 눈에 보이게 하는 편이 낫다.
        """
        now = now or datetime.now()
        stamp = now.strftime("%Y-%m-%d %H:%M")
        return [post for post in self.store.all("draft") if post.publish_at <= stamp]


def run_forever(runner: Runner, seconds: int = TICK_SECONDS, report=print) -> None:
    """APScheduler 로 계속 돈다. Ctrl+C 로 멈춘다."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone=os.getenv("TZ", "Asia/Seoul"))

    def job():
        result = runner.tick()
        for post_id in result.published:
            report(f"  ✓ {post_id}번 올렸습니다")
        for post_id, error in result.failed:
            report(f"  ✗ {post_id}번 실패 — {error}")
        for post_id, reason in result.skipped:
            report(f"  · {post_id}번 건너뜀 — {reason}")

        waiting = runner.pending()
        if waiting:
            report(f"  ⚠ 승인을 기다리는 글이 {len(waiting)}건 있습니다"
                   " (`manage.py list --status draft`)")

    scheduler.add_job(job, "interval", seconds=seconds, next_run_time=datetime.now())
    report(f"{seconds}초마다 큐를 봅니다. 멈추려면 Ctrl+C.")
    if runner.dry_run:
        report("모의 실행 — 실제로 올리지 않습니다.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        report("멈췄습니다.")
