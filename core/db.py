"""대시보드 SQLite 저장소.

테이블
    members           구매 고객
    licenses          고객이 산 프로그램 (플랜·기간·상태)
    notes             고객별 문의·응대 기록
    runs              프로그램 실행 이력
    settings          전역 설정 (키-값)
    program_settings  프로그램별 설정 (키-값)

MVP 단계라 SQLite 를 쓴다 (CLAUDE.md §6). 확장 시 PostgreSQL 로 옮긴다.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from shared.config import ROOT_DIR

__all__ = ["Database", "DEFAULT_DB_PATH", "now_iso"]

DEFAULT_DB_PATH = ROOT_DIR / "dashboard.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    phone       TEXT DEFAULT '',
    source      TEXT DEFAULT '',          -- 유입 경로 (크몽, 인스타, 소개 등)
    memo        TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS licenses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    program_id    TEXT NOT NULL,
    plan          TEXT DEFAULT '',
    price         INTEGER DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'active',   -- active | expired | refunded
    purchased_at  TEXT NOT NULL,
    expires_at    TEXT DEFAULT '',
    retainer      INTEGER DEFAULT 0,                -- 월 유지비 (원). 0이면 없음
    memo          TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id  INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id  TEXT NOT NULL,
    mode        TEXT NOT NULL,                      -- real | dry
    status      TEXT NOT NULL,                      -- running | success | warning | failed
    started_at  TEXT NOT NULL,
    finished_at TEXT DEFAULT '',
    exit_code   INTEGER,
    output_dir  TEXT DEFAULT '',
    log         TEXT DEFAULT '',
    member_id   INTEGER REFERENCES members(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS program_settings (
    program_id TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    PRIMARY KEY (program_id, key)
);

CREATE INDEX IF NOT EXISTS idx_licenses_member  ON licenses(member_id);
CREATE INDEX IF NOT EXISTS idx_licenses_program ON licenses(program_id);
CREATE INDEX IF NOT EXISTS idx_runs_program     ON runs(program_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_notes_member     ON notes(member_id, created_at DESC);
"""


def now_iso() -> str:
    """기록용 현재 시각 (로컬 타임존 포함 ISO 8601)."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Database:
    """대시보드가 쓰는 SQLite 래퍼.

    Args:
        path: DB 파일 경로. `:memory:` 를 주면 메모리 DB (테스트용).
    """

    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = str(path)
        self._memory_conn: sqlite3.Connection | None = None
        if self.path == ":memory:":
            self._memory_conn = self._make_conn()
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def _make_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """트랜잭션 하나. 예외가 나면 롤백한다."""
        if self._memory_conn is not None:
            conn = self._memory_conn
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            return

        conn = self._make_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------ 기본 연산
    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params: tuple = ()) -> int:
        """INSERT 면 새 id, 그 외에는 영향받은 행 수를 돌려준다."""
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.lastrowid if cursor.lastrowid else cursor.rowcount

    # -------------------------------------------------------------- 설정
    def get_setting(self, key: str, default: str = "") -> str:
        row = self.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def all_settings(self) -> dict[str, str]:
        return {row["key"]: row["value"] for row in self.query("SELECT key, value FROM settings")}

    def get_program_settings(self, program_id: str) -> dict[str, str]:
        rows = self.query(
            "SELECT key, value FROM program_settings WHERE program_id = ?", (program_id,)
        )
        return {row["key"]: row["value"] for row in rows}

    def set_program_setting(self, program_id: str, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO program_settings (program_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(program_id, key) DO UPDATE SET value = excluded.value",
            (program_id, key, str(value)),
        )

    # -------------------------------------------------------------- 회원
    def add_member(self, name: str, email: str, phone: str = "", source: str = "",
                   memo: str = "") -> int:
        return self.execute(
            "INSERT INTO members (name, email, phone, source, memo, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name.strip(), email.strip(), phone.strip(), source.strip(), memo.strip(), now_iso()),
        )

    def list_members(self, keyword: str = "") -> list[sqlite3.Row]:
        """고객 목록. 각 행에 보유 라이선스 수와 누적 결제액이 붙는다."""
        sql = """
            SELECT m.*,
                   COUNT(l.id) AS license_count,
                   COALESCE(SUM(CASE WHEN l.status = 'active' THEN l.price ELSE 0 END), 0) AS paid
            FROM members m
            LEFT JOIN licenses l ON l.member_id = m.id
            {where}
            GROUP BY m.id
            ORDER BY m.created_at DESC
        """
        if keyword:
            like = f"%{keyword}%"
            return self.query(
                sql.format(where="WHERE m.name LIKE ? OR m.email LIKE ? OR m.memo LIKE ?"),
                (like, like, like),
            )
        return self.query(sql.format(where=""))

    def get_member(self, member_id: int) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM members WHERE id = ?", (member_id,))

    def update_member(self, member_id: int, **fields: str) -> None:
        allowed = {"name", "email", "phone", "source", "memo"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key} = ?" for key in updates)
        self.execute(
            f"UPDATE members SET {assignments} WHERE id = ?",
            (*updates.values(), member_id),
        )

    def delete_member(self, member_id: int) -> None:
        self.execute("DELETE FROM members WHERE id = ?", (member_id,))

    # ------------------------------------------------------------ 라이선스
    def add_license(self, member_id: int, program_id: str, plan: str = "", price: int = 0,
                    expires_at: str = "", retainer: int = 0, memo: str = "") -> int:
        return self.execute(
            "INSERT INTO licenses (member_id, program_id, plan, price, status, "
            "purchased_at, expires_at, retainer, memo) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)",
            (member_id, program_id, plan, price, now_iso(), expires_at, retainer, memo),
        )

    def list_licenses(self, member_id: int | None = None,
                      program_id: str | None = None) -> list[sqlite3.Row]:
        sql = """
            SELECT l.*, m.name AS member_name, m.email AS member_email
            FROM licenses l JOIN members m ON m.id = l.member_id
        """
        clauses, params = [], []
        if member_id is not None:
            clauses.append("l.member_id = ?")
            params.append(member_id)
        if program_id is not None:
            clauses.append("l.program_id = ?")
            params.append(program_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return self.query(sql + " ORDER BY l.purchased_at DESC", tuple(params))

    def set_license_status(self, license_id: int, status: str) -> None:
        self.execute("UPDATE licenses SET status = ? WHERE id = ?", (status, license_id))

    def delete_license(self, license_id: int) -> None:
        self.execute("DELETE FROM licenses WHERE id = ?", (license_id,))

    # -------------------------------------------------------------- 메모
    def add_note(self, member_id: int, body: str) -> int:
        return self.execute(
            "INSERT INTO notes (member_id, body, created_at) VALUES (?, ?, ?)",
            (member_id, body.strip(), now_iso()),
        )

    def list_notes(self, member_id: int) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM notes WHERE member_id = ? ORDER BY created_at DESC", (member_id,)
        )

    # ------------------------------------------------------------ 실행 이력
    def start_run(self, program_id: str, mode: str, member_id: int | None = None) -> int:
        return self.execute(
            "INSERT INTO runs (program_id, mode, status, started_at, member_id) "
            "VALUES (?, ?, 'running', ?, ?)",
            (program_id, mode, now_iso(), member_id),
        )

    def finish_run(self, run_id: int, status: str, exit_code: int, log: str,
                   output_dir: str = "") -> None:
        self.execute(
            "UPDATE runs SET status = ?, exit_code = ?, log = ?, output_dir = ?, "
            "finished_at = ? WHERE id = ?",
            (status, exit_code, log, output_dir, now_iso(), run_id),
        )

    def list_runs(self, program_id: str | None = None, limit: int = 50) -> list[sqlite3.Row]:
        if program_id:
            return self.query(
                "SELECT * FROM runs WHERE program_id = ? ORDER BY started_at DESC LIMIT ?",
                (program_id, limit),
            )
        return self.query("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))

    def get_run(self, run_id: int):
        return self.query_one("SELECT * FROM runs WHERE id = ?", (run_id,))

    # -------------------------------------------------------------- 요약
    def summary(self) -> dict[str, int]:
        """홈 화면 상단 숫자."""
        def scalar(sql: str, params: tuple = ()) -> int:
            row = self.query_one(sql, params)
            return int(row[0]) if row and row[0] is not None else 0

        return {
            "members": scalar("SELECT COUNT(*) FROM members"),
            "active_licenses": scalar("SELECT COUNT(*) FROM licenses WHERE status = 'active'"),
            "revenue": scalar("SELECT SUM(price) FROM licenses WHERE status = 'active'"),
            "retainer": scalar("SELECT SUM(retainer) FROM licenses WHERE status = 'active'"),
            "runs": scalar("SELECT COUNT(*) FROM runs"),
        }
