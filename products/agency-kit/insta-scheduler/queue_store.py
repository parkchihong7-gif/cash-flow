"""발행 큐 — SQLite.

한 줄의 일생

    초안(draft) → **사람 승인(approved)** → 발행됨(published)
                                        ↘ 실패(failed) → 다시 승인 대기

`approved` 를 거치지 않은 줄은 **절대 발행되지 않는다.** 이건 옵션이 아니다.
사람이 안 본 글이 고객 계정에서 나가는 일은 만들지 않는다(CLAUDE.md §3-3).
승인은 사람이 손으로 누르는 것이고, 누가 언제 승인했는지 남긴다.

큐를 CSV 가 아니라 SQLite 에 두는 이유
    CSV 는 두 곳에서 동시에 열면 한쪽이 지워진다. 스케줄러가 돌면서 상태를
    바꾸는데 사람이 엑셀로 열어 두면 그런 일이 생긴다. 시작은 CSV 로 받되
    (`queue.csv`), 들어오면 SQLite 에 쌓는다.
"""

from __future__ import annotations

import csv
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

__all__ = ["QueueStore", "Post", "STATUSES", "DEFAULT_DB", "load_csv_rows"]

DEFAULT_DB = "queue.db"

#: 상태. 이 밖의 값은 넣지 않는다.
STATUSES = ("draft", "approved", "published", "failed", "canceled")

SCHEMA = """
CREATE TABLE IF NOT EXISTS post (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    publish_at   TEXT NOT NULL,          -- 언제 올릴지 (YYYY-MM-DD HH:MM)
    media_url    TEXT NOT NULL,          -- 공개 이미지/영상 주소
    media_type   TEXT NOT NULL DEFAULT 'IMAGE',   -- IMAGE | REELS
    caption      TEXT NOT NULL DEFAULT '',
    hashtags     TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'draft',
    approved_by  TEXT NOT NULL DEFAULT '',
    approved_at  TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    media_id     TEXT NOT NULL DEFAULT '',   -- 인스타가 준 게시물 번호
    last_error   TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_post_status ON post(status, publish_at);
"""


@dataclass
class Post:
    """큐에 든 게시물 한 건."""

    id: int
    publish_at: str
    media_url: str
    media_type: str
    caption: str
    hashtags: str
    status: str
    approved_by: str = ""
    approved_at: str = ""
    published_at: str = ""
    media_id: str = ""
    last_error: str = ""
    created_at: str = ""

    @property
    def full_caption(self) -> str:
        """캡션과 해시태그를 합친 것. 인스타에 실제로 올라가는 글."""
        tags = self.hashtags.strip()
        if not tags:
            return self.caption.strip()
        return f"{self.caption.strip()}\n\n{tags}"

    @property
    def approved(self) -> bool:
        return self.status == "approved"


def _to_post(row: sqlite3.Row) -> Post:
    return Post(**{key: row[key] for key in row.keys()})


def load_csv_rows(path: str | Path) -> list[dict]:
    """`queue.csv` 를 읽는다. 칸: 발행시각, 미디어URL, 캡션, 해시태그."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"큐 파일이 없습니다: {path}")

    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            text = path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        rows = list(csv.DictReader(text.splitlines()))
        cleaned = []
        for row in rows:
            tidy = {(key or "").strip(): (value or "").strip()
                    for key, value in row.items() if key}
            if tidy.get("미디어URL") or tidy.get("media_url"):
                cleaned.append(tidy)
        return cleaned
    raise ValueError(f"{path.name} 의 글자 인코딩을 알아보지 못했습니다")


class QueueStore:
    """발행 큐."""

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

    # ------------------------------------------------------------- 넣기
    def add(self, publish_at: str, media_url: str, caption: str = "",
            hashtags: str = "", media_type: str = "IMAGE") -> int:
        """초안으로 넣는다. **바로 발행되지 않는다.**"""
        if not media_url.strip():
            raise ValueError("미디어 주소가 비어 있습니다")
        if media_type not in {"IMAGE", "REELS"}:
            raise ValueError(f"미디어 종류는 IMAGE 또는 REELS 입니다 (받은 값: {media_type})")

        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "INSERT INTO post (publish_at, media_url, media_type, caption,"
                " hashtags, status, created_at) VALUES (?, ?, ?, ?, ?, 'draft', ?)",
                (publish_at.strip(), media_url.strip(), media_type, caption.strip(),
                 hashtags.strip(), datetime.now().isoformat(timespec="seconds")),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def import_csv(self, path: str | Path) -> list[int]:
        """CSV 를 읽어 초안으로 넣는다. 같은 주소·시각이면 건너뛴다."""
        added: list[int] = []
        existing = {(post.publish_at, post.media_url) for post in self.all()}
        for row in load_csv_rows(path):
            publish_at = row.get("발행시각") or row.get("publish_at", "")
            media_url = row.get("미디어URL") or row.get("media_url", "")
            if (publish_at, media_url) in existing:
                continue
            added.append(self.add(
                publish_at=publish_at,
                media_url=media_url,
                caption=row.get("캡션") or row.get("caption", ""),
                hashtags=row.get("해시태그") or row.get("hashtags", ""),
                media_type=(row.get("종류") or row.get("media_type") or "IMAGE").upper(),
            ))
        return added

    # ------------------------------------------------------------- 읽기
    def all(self, status: str = "") -> list[Post]:
        query = "SELECT * FROM post"
        params: tuple = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY publish_at, id"
        with closing(self._connect()) as connection:
            return [_to_post(row) for row in connection.execute(query, params)]

    def get(self, post_id: int) -> Post | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM post WHERE id = ?", (post_id,)).fetchone()
        return _to_post(row) if row else None

    def due(self, now: str = "") -> list[Post]:
        """지금 올릴 때가 된 것. **승인된 것만** 돌려준다."""
        now = now or datetime.now().strftime("%Y-%m-%d %H:%M")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM post WHERE status = 'approved' AND publish_at <= ?"
                " ORDER BY publish_at, id", (now,)).fetchall()
        return [_to_post(row) for row in rows]

    def counts(self) -> dict[str, int]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS n FROM post GROUP BY status").fetchall()
        return {row["status"]: int(row["n"]) for row in rows}

    # ------------------------------------------------------------- 고치기
    def set_caption(self, post_id: int, caption: str, hashtags: str = "") -> None:
        """캡션을 고친다. **고치면 승인이 풀린다.**

        승인한 문장과 다른 글이 나가면 안 되기 때문이다.
        """
        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE post SET caption = ?, hashtags = COALESCE(NULLIF(?, ''), hashtags),"
                " status = CASE WHEN status = 'published' THEN status ELSE 'draft' END,"
                " approved_by = '', approved_at = '' WHERE id = ?",
                (caption.strip(), hashtags.strip(), post_id))
            connection.commit()

    def approve(self, post_id: int, who: str) -> Post:
        """사람이 승인한다. 누가 언제 했는지 남긴다."""
        if not who.strip():
            raise ValueError("승인자 이름이 필요합니다. 누가 봤는지 남겨야 합니다")

        post = self.get(post_id)
        if post is None:
            raise ValueError(f"{post_id}번 글이 없습니다")
        if post.status == "published":
            raise ValueError(f"{post_id}번은 이미 올라간 글입니다")
        if not post.caption.strip():
            raise ValueError(f"{post_id}번은 캡션이 비어 있습니다. 먼저 채우세요")

        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE post SET status = 'approved', approved_by = ?, approved_at = ?,"
                " last_error = '' WHERE id = ?",
                (who.strip(), datetime.now().isoformat(timespec="seconds"), post_id))
            connection.commit()
        return self.get(post_id)                     # type: ignore[return-value]

    def unapprove(self, post_id: int) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE post SET status = 'draft', approved_by = '', approved_at = ''"
                " WHERE id = ? AND status = 'approved'", (post_id,))
            connection.commit()

    def cancel(self, post_id: int) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE post SET status = 'canceled' WHERE id = ? AND status != 'published'",
                (post_id,))
            connection.commit()

    def mark_published(self, post_id: int, media_id: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE post SET status = 'published', media_id = ?, published_at = ?,"
                " last_error = '' WHERE id = ?",
                (media_id, datetime.now().isoformat(timespec="seconds"), post_id))
            connection.commit()

    def mark_failed(self, post_id: int, error: str) -> None:
        """실패하면 **승인을 풀지 않는다.** 고치고 다시 돌리면 그대로 나간다."""
        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE post SET status = 'failed', last_error = ? WHERE id = ?",
                (error[:500], post_id))
            connection.commit()

    def retry(self, post_id: int) -> None:
        """실패한 것을 다시 승인 대기로 돌린다."""
        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE post SET status = 'approved' WHERE id = ? AND status = 'failed'",
                (post_id,))
            connection.commit()
