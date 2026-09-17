"""자료 창고 — SQLite.

**이 상품의 값어치는 여기 쌓이는 시간에 있다.**

유튜브 API 는 "어제 조회수가 몇이었는지" 를 알려 주지 않는다. 지금 값만 준다.
그래서 매일 한 번씩 찍어 두는 것 말고는 시계열을 가질 방법이 없다.
하루 이틀은 아무것도 안 보이고, 2주가 지나야 뭔가 보이기 시작한다.

    keywords           지켜볼 말
    videos             영상 (제목·길이·쇼츠 여부) — 한 번만 넣는다
    video_snapshots    영상의 조회수·좋아요·댓글 — **매일 덧붙인다**
    channels           채널
    channel_snapshots  채널의 구독자·총조회수 — **매일 덧붙인다**

스냅샷은 (id, 날짜)로 묶어 하루에 한 줄만 남긴다. 같은 날 두 번 돌려도
덮어쓰기만 되고 줄이 늘지 않는다.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path

__all__ = ["Store", "VideoRow", "SCHEMA", "DEFAULT_DB"]

DEFAULT_DB = "niche.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS keywords (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword   TEXT NOT NULL UNIQUE,
    added_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    video_id     TEXT PRIMARY KEY,
    channel_id   TEXT NOT NULL,
    keyword_id   INTEGER NOT NULL,
    title        TEXT NOT NULL,
    published_at TEXT NOT NULL,
    duration_sec INTEGER NOT NULL DEFAULT 0,
    is_short     INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (keyword_id) REFERENCES keywords(id)
);
CREATE INDEX IF NOT EXISTS idx_videos_keyword ON videos(keyword_id, published_at);

CREATE TABLE IF NOT EXISTS video_snapshots (
    video_id      TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    views         INTEGER NOT NULL DEFAULT 0,
    likes         INTEGER NOT NULL DEFAULT 0,
    comments      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (video_id, snapshot_date),
    FOREIGN KEY (video_id) REFERENCES videos(video_id)
);

CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS channel_snapshots (
    channel_id    TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    subscribers   INTEGER NOT NULL DEFAULT 0,
    total_views   INTEGER NOT NULL DEFAULT 0,
    video_count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (channel_id, snapshot_date),
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
);
"""


@dataclass
class VideoRow:
    """영상 한 편. 수집기가 만들어 창고에 넣는다."""

    video_id: str
    channel_id: str
    title: str
    published_at: str
    duration_sec: int = 0
    is_short: bool = False
    views: int = 0
    likes: int = 0
    comments: int = 0


class Store:
    """자료 창고."""

    def __init__(self, path: str | Path = DEFAULT_DB) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    # ------------------------------------------------------------ 키워드
    def keyword_id(self, keyword: str) -> int:
        """키워드를 넣고 번호를 돌려준다. 이미 있으면 그 번호."""
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("빈 키워드입니다")
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO keywords (keyword, added_at) VALUES (?, ?)",
                (keyword, date.today().isoformat()))
            connection.commit()
            row = connection.execute(
                "SELECT id FROM keywords WHERE keyword = ?", (keyword,)).fetchone()
        return int(row["id"])

    def keywords(self) -> list[sqlite3.Row]:
        with closing(self._connect()) as connection:
            return connection.execute(
                "SELECT * FROM keywords ORDER BY id").fetchall()

    # -------------------------------------------------------------- 영상
    def save_videos(self, keyword: str, rows: list[VideoRow],
                    snapshot_date: str = "") -> int:
        """영상과 오늘의 스냅샷을 넣는다. 넣은 스냅샷 수를 돌려준다.

        영상 자체는 한 번만 넣는다(제목은 바뀌면 갱신). 숫자는 **날마다** 넣는다.
        """
        snapshot_date = snapshot_date or date.today().isoformat()
        key_id = self.keyword_id(keyword)

        with closing(self._connect()) as connection:
            for row in rows:
                connection.execute(
                    "INSERT INTO videos (video_id, channel_id, keyword_id, title,"
                    " published_at, duration_sec, is_short) VALUES (?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(video_id) DO UPDATE SET title = excluded.title",
                    (row.video_id, row.channel_id, key_id, row.title,
                     row.published_at, row.duration_sec, int(row.is_short)))
                connection.execute(
                    "INSERT INTO video_snapshots (video_id, snapshot_date, views,"
                    " likes, comments) VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(video_id, snapshot_date) DO UPDATE SET"
                    " views = excluded.views, likes = excluded.likes,"
                    " comments = excluded.comments",
                    (row.video_id, snapshot_date, row.views, row.likes, row.comments))
            connection.commit()
        return len(rows)

    def save_channels(self, channels: list[dict], snapshot_date: str = "") -> int:
        """채널과 오늘의 스냅샷을 넣는다."""
        snapshot_date = snapshot_date or date.today().isoformat()
        with closing(self._connect()) as connection:
            for channel in channels:
                connection.execute(
                    "INSERT INTO channels (channel_id, title, created_at)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(channel_id) DO UPDATE SET title = excluded.title",
                    (channel["channel_id"], channel.get("title", ""),
                     channel.get("created_at", "")))
                connection.execute(
                    "INSERT INTO channel_snapshots (channel_id, snapshot_date,"
                    " subscribers, total_views, video_count) VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(channel_id, snapshot_date) DO UPDATE SET"
                    " subscribers = excluded.subscribers,"
                    " total_views = excluded.total_views,"
                    " video_count = excluded.video_count",
                    (channel["channel_id"], snapshot_date,
                     int(channel.get("subscribers", 0)),
                     int(channel.get("total_views", 0)),
                     int(channel.get("video_count", 0))))
            connection.commit()
        return len(channels)

    # -------------------------------------------------------------- 조회
    def latest_snapshot_date(self) -> str:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT MAX(snapshot_date) AS d FROM video_snapshots").fetchone()
        return str(row["d"] or "")

    def snapshot_dates(self) -> list[str]:
        """찍어 둔 날짜들. **며칠치가 쌓였는지**가 분석의 전제다."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT DISTINCT snapshot_date FROM video_snapshots"
                " ORDER BY snapshot_date").fetchall()
        return [str(row["snapshot_date"]) for row in rows]

    def videos_for(self, keyword: str, snapshot_date: str = "") -> list[sqlite3.Row]:
        """키워드 하나의 영상과 그날 숫자."""
        snapshot_date = snapshot_date or self.latest_snapshot_date()
        with closing(self._connect()) as connection:
            return connection.execute(
                "SELECT v.*, s.views, s.likes, s.comments, c.title AS channel_title,"
                "       cs.subscribers"
                " FROM videos v"
                " JOIN keywords k ON k.id = v.keyword_id"
                " LEFT JOIN video_snapshots s"
                "        ON s.video_id = v.video_id AND s.snapshot_date = ?"
                " LEFT JOIN channels c ON c.channel_id = v.channel_id"
                " LEFT JOIN channel_snapshots cs"
                "        ON cs.channel_id = v.channel_id AND cs.snapshot_date = ?"
                " WHERE k.keyword = ?"
                " ORDER BY v.published_at DESC",
                (snapshot_date, snapshot_date, keyword)).fetchall()

    def channel_snapshots(self, channel_id: str) -> list[sqlite3.Row]:
        with closing(self._connect()) as connection:
            return connection.execute(
                "SELECT * FROM channel_snapshots WHERE channel_id = ?"
                " ORDER BY snapshot_date", (channel_id,)).fetchall()

    def counts(self) -> dict[str, int]:
        with closing(self._connect()) as connection:
            def scalar(sql: str) -> int:
                row = connection.execute(sql).fetchone()
                return int(row[0] or 0)

            return {
                "keywords": scalar("SELECT COUNT(*) FROM keywords"),
                "videos": scalar("SELECT COUNT(*) FROM videos"),
                "video_snapshots": scalar("SELECT COUNT(*) FROM video_snapshots"),
                "channels": scalar("SELECT COUNT(*) FROM channels"),
                "channel_snapshots": scalar("SELECT COUNT(*) FROM channel_snapshots"),
                "days": scalar(
                    "SELECT COUNT(DISTINCT snapshot_date) FROM video_snapshots"),
            }
