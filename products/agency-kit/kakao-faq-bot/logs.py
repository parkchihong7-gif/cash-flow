"""대화 기록 — SQLite.

무엇을 남기는가
    시각 · 이용자 **해시** · 질문 · 맞은 FAQ 번호 · 답 · 걸린 시간(ms)

무엇을 남기지 않는가
    **이용자 아이디 원문을 남기지 않는다.** 카카오가 주는 아이디는 그 자체로
    개인을 가리키는 값이라, 해시로 바꿔 저장한다. 해시에 쓰는 소금(salt)은
    `.env` 에 두고, 이게 바뀌면 예전 기록과는 이어지지 않는다. 그게 맞다.

    질문 글에 섞여 들어온 **전화번호·이메일·카드번호·주민번호는 지운다.**
    고객센터 질문에는 이런 것이 자주 딸려 온다. "제 번호 010-1234-5678 로
    연락 주세요" 같은 식으로. 그대로 쌓아 두면 그 파일이 개인정보 파일이 된다.

무엇에 쓰는가
    `manage.py stats` 로 **답 못 한 질문 상위 20개**를 뽑는다. 그게 다음 달에
    시트에 추가할 FAQ 목록이고, 리테이너 계약의 실제 내용물이 된다.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["LogStore", "scrub", "hash_user", "DEFAULT_DB", "PATTERNS"]

DEFAULT_DB = Path(os.getenv("LOG_DB_PATH", "logs.db"))

#: 지울 것들. 순서가 있다 — 긴 것부터 지워야 조각이 남지 않는다.
PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("[주민번호]", re.compile(r"\d{6}\s*[-–]\s*[1-4]\d{6}")),
    ("[카드번호]", re.compile(r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}")),
    ("[계좌번호]", re.compile(r"\d{2,6}[-–]\d{2,6}[-–]\d{2,7}")),
    ("[전화번호]", re.compile(r"01[0-9][\s-]?\d{3,4}[\s-]?\d{4}")),
    ("[전화번호]", re.compile(r"0\d{1,2}[\s-]\d{3,4}[\s-]\d{4}")),
    ("[이메일]", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    user_hash   TEXT NOT NULL,
    question    TEXT NOT NULL,
    matched     INTEGER,              -- 맞은 FAQ 번호(1부터), 못 맞으면 NULL
    answer      TEXT NOT NULL,
    elapsed_ms  INTEGER NOT NULL,
    source      TEXT NOT NULL DEFAULT ''   -- sheet | claude | fallback
);
CREATE INDEX IF NOT EXISTS idx_chat_log_day ON chat_log(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_log_matched ON chat_log(matched);
"""


def scrub(text: str) -> str:
    """질문에서 개인정보로 보이는 것을 지운다.

    완벽하지 않다. 못 잡는 모양이 있을 수 있다. 그래서 매뉴얼에도
    "기록은 상담 개선용이고 오래 두지 않는다" 를 적어 두었다.
    """
    cleaned = text or ""
    for label, pattern in PATTERNS:
        cleaned = pattern.sub(label, cleaned)
    return cleaned


def hash_user(user_id: str, salt: str = "") -> str:
    """이용자 아이디를 되돌릴 수 없게 바꾼다.

    소금이 없으면 같은 아이디가 어디서나 같은 해시가 되어, 다른 곳의 기록과
    맞춰 볼 수 있게 된다. 그래서 `.env` 의 `LOG_SALT` 를 쓴다.
    """
    salt = salt or os.getenv("LOG_SALT", "")
    digest = hashlib.sha256(f"{salt}|{user_id or ''}".encode("utf-8")).hexdigest()
    return digest[:16]


class LogStore:
    """대화 기록 저장소."""

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

    def add(self, *, user_id: str, question: str, answer: str,
            matched: int | None, elapsed_ms: int, source: str = "") -> int:
        """한 건 남긴다. 질문은 지울 것을 지우고, 아이디는 해시로 바꿔 넣는다."""
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "INSERT INTO chat_log (created_at, user_hash, question, matched,"
                " answer, elapsed_ms, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                 hash_user(user_id), scrub(question), matched, answer,
                 int(elapsed_ms), source),
            )
            connection.commit()
            return int(cursor.lastrowid)

    # -------------------------------------------------------------- 통계
    def daily_counts(self, days: int = 14) -> list[sqlite3.Row]:
        """날짜별 질문 수와 못 맞힌 수."""
        with closing(self._connect()) as connection:
            return connection.execute(
                "SELECT substr(created_at, 1, 10) AS day,"
                "       COUNT(*) AS total,"
                "       SUM(CASE WHEN matched IS NULL THEN 1 ELSE 0 END) AS missed,"
                "       AVG(elapsed_ms) AS avg_ms"
                " FROM chat_log GROUP BY day ORDER BY day DESC LIMIT ?",
                (days,),
            ).fetchall()

    def unmatched(self, limit: int = 20) -> list[sqlite3.Row]:
        """못 맞힌 질문을 많이 들어온 순으로. **다음에 시트에 넣을 후보다.**"""
        with closing(self._connect()) as connection:
            return connection.execute(
                "SELECT question, COUNT(*) AS hits, MAX(created_at) AS last_at"
                " FROM chat_log WHERE matched IS NULL"
                " GROUP BY question ORDER BY hits DESC, last_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def slow(self, over_ms: int = 4000, limit: int = 10) -> list[sqlite3.Row]:
        """오래 걸린 것. 카카오는 5초를 넘기면 끊는다."""
        with closing(self._connect()) as connection:
            return connection.execute(
                "SELECT created_at, question, elapsed_ms FROM chat_log"
                " WHERE elapsed_ms >= ? ORDER BY elapsed_ms DESC LIMIT ?",
                (over_ms, limit),
            ).fetchall()

    def totals(self) -> sqlite3.Row:
        with closing(self._connect()) as connection:
            return connection.execute(
                "SELECT COUNT(*) AS total,"
                "       SUM(CASE WHEN matched IS NULL THEN 1 ELSE 0 END) AS missed,"
                "       AVG(elapsed_ms) AS avg_ms, MAX(elapsed_ms) AS max_ms"
                " FROM chat_log"
            ).fetchone()

    def purge_before(self, iso_day: str) -> int:
        """오래된 기록을 지운다. 계약서에 적은 보관 기간을 지키는 손잡이다."""
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "DELETE FROM chat_log WHERE substr(created_at, 1, 10) < ?", (iso_day,))
            connection.commit()
            return cursor.rowcount
