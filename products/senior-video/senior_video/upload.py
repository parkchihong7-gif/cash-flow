"""업로드 — **사람이 승인해야 올라간다. 예외 없다.**

유튜브는 2025년 7월부터 '양산형(비진정성) 콘텐츠' 를 수익 창출에서 제외하는
방향으로 정책을 정리했다. 사람 손이 안 닿은 대량 업로드는 채널 자체를 위험하게
만든다 (CLAUDE.md §3-3).

그래서 이 모듈은 **큐만 관리한다.** 큐에 들어가려면 사람이 승인해야 하고,
승인 없이 올라가는 경로는 코드에 없다.

그리고 쿼터. 유튜브 Data API 는 하루 10,000 유닛인데 **업로드 한 번이
1,600 유닛**이다. 산술적으로 하루 6편이 끝이다. "하루 20편 자동 업로드" 를
파는 사람들이 이 숫자를 말하지 않는다.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

__all__ = [
    "UPLOAD_UNITS", "DAILY_UNITS", "MAX_UPLOADS_PER_DAY", "AUDIT_NOTE",
    "Item", "Queue", "QueueError", "uploads_possible",
]

#: videos.insert 한 번의 비용. 목록 조회(1 유닛)와 비교하면 터무니없이 비싸다.
UPLOAD_UNITS = 1600
DAILY_UNITS = 10_000
MAX_UPLOADS_PER_DAY = DAILY_UNITS // UPLOAD_UNITS   # 6

AUDIT_NOTE = (
    "새로 만든 구글 API 프로젝트로 올린 영상은 **비공개(private)로 잠깁니다.** "
    "구글에 API 감사(audit)를 신청해 승인을 받아야 공개로 올릴 수 있습니다. "
    "신청부터 답까지 며칠에서 몇 주가 걸립니다. 채널을 열기 전에 먼저 신청하세요."
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  script_chars INTEGER DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft',   -- draft / approved / uploaded / rejected
  approved_by TEXT DEFAULT '',
  approved_at TEXT DEFAULT '',
  note TEXT DEFAULT '',
  plan_json TEXT DEFAULT '{}',
  created_at TEXT NOT NULL
);
"""


class QueueError(RuntimeError):
    """큐 규칙을 어겼을 때."""


@dataclass
class Item:
    id: int
    title: str
    script_chars: int
    status: str
    approved_by: str
    approved_at: str
    note: str
    created_at: str

    @property
    def ready(self) -> bool:
        return self.status == "approved"

    @property
    def status_label(self) -> str:
        return {"draft": "초안 — 승인 대기", "approved": "승인됨 — 올릴 수 있음",
                "uploaded": "올림", "rejected": "반려"}.get(self.status, self.status)


class Queue:
    """업로드 대기열. **승인 없이 'approved' 가 되는 길이 없다.**"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def add_draft(self, title: str, script_chars: int = 0, plan: dict | None = None) -> int:
        """초안을 넣는다. **항상 draft 로 들어간다.**"""
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO items (title, script_chars, status, plan_json, created_at)"
                " VALUES (?, ?, 'draft', ?, ?)",
                (title.strip(), int(script_chars),
                 json.dumps(plan or {}, ensure_ascii=False), date.today().isoformat()))
            return int(cursor.lastrowid)

    def approve(self, item_id: int, who: str, note: str = "") -> Item:
        """사람이 승인한다. **누가 승인했는지 없으면 승인이 아니다.**"""
        if not (who or "").strip():
            raise QueueError(
                "승인한 사람 이름이 필요합니다.\n"
                "  사람이 봤다는 기록이 남아야 '검수' 입니다. "
                "이름 없는 승인은 자동 승인과 다르지 않습니다")
        with self._conn() as conn:
            row = conn.execute("SELECT status FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                raise QueueError(f"큐에 없는 항목입니다: {item_id}")
            if row["status"] == "uploaded":
                raise QueueError("이미 올린 항목입니다")
            conn.execute(
                "UPDATE items SET status = 'approved', approved_by = ?,"
                " approved_at = ?, note = ? WHERE id = ?",
                (who.strip(), date.today().isoformat(), note.strip(), item_id))
        return self.get(item_id)

    def reject(self, item_id: int, note: str = "") -> Item:
        with self._conn() as conn:
            conn.execute("UPDATE items SET status = 'rejected', note = ? WHERE id = ?",
                         (note.strip(), item_id))
        return self.get(item_id)

    def mark_uploaded(self, item_id: int) -> Item:
        """올렸다고 적는다. **승인 안 된 것은 여기서 막는다.**"""
        item = self.get(item_id)
        if not item.ready:
            raise QueueError(
                f"승인되지 않은 항목은 올릴 수 없습니다: {item.title} ({item.status_label})\n"
                f"  사람 검수 없는 대량 업로드는 유튜브 정책 위반입니다")
        with self._conn() as conn:
            conn.execute("UPDATE items SET status = 'uploaded' WHERE id = ?", (item_id,))
        return self.get(item_id)

    def get(self, item_id: int) -> Item:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise QueueError(f"큐에 없는 항목입니다: {item_id}")
        return self._to_item(row)

    def list(self, status: str = "") -> list[Item]:
        sql = "SELECT * FROM items"
        params: tuple = ()
        if status:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY id"
        with self._conn() as conn:
            return [self._to_item(row) for row in conn.execute(sql, params)]

    def counts(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM items GROUP BY status")
            return {row["status"]: row["n"] for row in rows}

    @staticmethod
    def _to_item(row: sqlite3.Row) -> Item:
        return Item(
            id=row["id"], title=row["title"], script_chars=row["script_chars"],
            status=row["status"], approved_by=row["approved_by"],
            approved_at=row["approved_at"], note=row["note"],
            created_at=row["created_at"])


def uploads_possible(monthly_videos: int) -> dict:
    """이 편수가 쿼터 안에 들어가는지."""
    per_day = monthly_videos / 30
    return {
        "monthly": monthly_videos,
        "per_day": round(per_day, 2),
        "max_per_day": MAX_UPLOADS_PER_DAY,
        "max_monthly": MAX_UPLOADS_PER_DAY * 30,
        "units_per_day": round(per_day * UPLOAD_UNITS),
        "fits": per_day <= MAX_UPLOADS_PER_DAY,
    }
