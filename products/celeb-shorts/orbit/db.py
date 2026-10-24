"""SQLite 한 파일(`data/orbit.db`) — 표 만들기, 설정 읽고 쓰기, 작업 기록, 백업/복원.

표 구조는 설계 문서 6장 그대로다. 아직 화면이 없는 표도 미리 만들어 둔다 —
나중 조각이 표를 고치지 않고 화면만 붙이게 하려고.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import sqlite3
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE_DIR / "data" / "orbit.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS celebrity (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS product (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, brand TEXT DEFAULT '', model TEXT DEFAULT '',
    category TEXT NOT NULL DEFAULT '기타'
        CHECK (category IN ('뷰티','패션','라이프스타일','디지털','건강식품','기타')),
    price INTEGER, price_source TEXT DEFAULT '', price_checked_at TEXT,
    available INTEGER, keyword TEXT DEFAULT '', created_at TEXT NOT NULL
);
-- 연예인 본인 영상은 «그 시간대» 가 근거라 timestamp 를 함께 둔다. 영상은 받지 않고 링크만.
CREATE TABLE IF NOT EXISTS source (
    id INTEGER PRIMARY KEY, url TEXT NOT NULL, title TEXT DEFAULT '', publisher TEXT DEFAULT '',
    published_at TEXT, kind TEXT NOT NULL DEFAULT '기사'
        CHECK (kind IN ('기사','공식SNS','연예인 본인 영상','브랜드','방송정보','기타')),
    timestamp TEXT DEFAULT '',
    added_at TEXT NOT NULL
);
-- 연예인-상품 관계. '추정' 이 아닌 값은 사람이 확인해야만 들어간다(verified_by).
CREATE TABLE IF NOT EXISTS claim (
    id INTEGER PRIMARY KEY,
    celebrity_id INTEGER NOT NULL REFERENCES celebrity(id),
    product_id INTEGER NOT NULL REFERENCES product(id),
    source_id INTEGER REFERENCES source(id),
    relation TEXT NOT NULL DEFAULT '추정'
        CHECK (relation IN ('추천확인','사용확인','등장','추정')),
    verified_by TEXT DEFAULT '', verified_at TEXT, note TEXT DEFAULT '',
    CHECK (relation = '추정' OR (verified_by <> '' AND source_id IS NOT NULL))
);
-- 라이선스 기록이 없는 파일은 렌더에 못 쓴다.
CREATE TABLE IF NOT EXISTS asset (
    id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES product(id),
    path TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('image','music','font')),
    license TEXT NOT NULL
        CHECK (license IN ('직접촬영','브랜드허락','제휴제공','무료라이선스','자체제작')),
    license_proof TEXT DEFAULT '', expires_at TEXT, added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS affiliate_link (
    id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES product(id),
    platform TEXT NOT NULL DEFAULT '쿠팡파트너스', url TEXT NOT NULL,
    added_by TEXT NOT NULL, created_by_api INTEGER NOT NULL DEFAULT 0, added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS script (
    id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES product(id),
    variant INTEGER NOT NULL, body_json TEXT NOT NULL, issues_json TEXT DEFAULT '[]',
    approved_by TEXT DEFAULT '', approved_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS video (
    id INTEGER PRIMARY KEY, script_id INTEGER NOT NULL REFERENCES script(id),
    template TEXT NOT NULL, path TEXT DEFAULT '', duration REAL, checks_json TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT '렌더됨'
        CHECK (status IN ('렌더됨','검사실패','승인됨','업로드됨')),
    approved_by TEXT DEFAULT '', approved_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS upload (
    id INTEGER PRIMARY KEY, video_id INTEGER NOT NULL REFERENCES video(id),
    youtube_id TEXT DEFAULT '', privacy TEXT NOT NULL DEFAULT 'private',
    scheduled_at TEXT, status TEXT NOT NULL DEFAULT '대기'
);
CREATE TABLE IF NOT EXISTS metric (
    id INTEGER PRIMARY KEY, video_id INTEGER NOT NULL REFERENCES video(id), date TEXT NOT NULL,
    views INTEGER, clicks INTEGER, orders INTEGER, commission INTEGER,
    source TEXT NOT NULL CHECK (source IN ('api','수동'))
);
CREATE TABLE IF NOT EXISTS job (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT '대기' CHECK (status IN ('대기','실행중','완료','실패')),
    tries INTEGER NOT NULL DEFAULT 0, last_error TEXT DEFAULT '', message TEXT DEFAULT '',
    created_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

TABLES = ("celebrity", "product", "source", "claim", "asset", "affiliate_link",
          "script", "video", "upload", "metric", "job", "setting")

#: 처음 설정. 색은 브랜드 팔레트 초기값(요청서 2장), 슬로건은 설계 0장 결정.
DEFAULT_SETTINGS: dict[str, str] = {
    "channel_name": "셀럽오르빗",
    "channel_name_en": "CELEB ORBIT",
    "slogan": "스타 스타일, 여기서 찾기",
    "color_navy": "#123A50",
    "color_mustard": "#F4B942",
    "color_coral": "#E85B4A",
    "color_pink": "#E89BA5",
    "color_cream": "#F6E7C8",
    "video_seconds": "20",
    "daily_upload_cap": "2",
}

COLOR_KEYS = ("color_navy", "color_mustard", "color_coral", "color_pink", "color_cream")
COLOR_LABELS = {"color_navy": "딥 네이비", "color_mustard": "머스터드 옐로", "color_coral": "코랄 레드",
                "color_pink": "빈티지 핑크", "color_cream": "크림"}

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
MAX_TRIES = 3


class SettingError(ValueError):
    """설정 값이 규칙에 맞지 않을 때."""


class RestoreError(ValueError):
    """복원 파일이 셀럽오르빗 백업이 아닐 때."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class OrbitDB:
    def __init__(self, path: Path | str = DEFAULT_DB) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()
        with self.connect() as con:
            con.executescript(SCHEMA)
            for key, value in DEFAULT_SETTINGS.items():
                con.execute("INSERT OR IGNORE INTO setting(key, value) VALUES (?, ?)", (key, value))

    def _migrate(self) -> None:
        """① 뼈대로 만든 DB 를 지금 표 모양으로 맞춘다. 데이터는 그대로 옮긴다.

        SQLite 는 CHECK 를 고칠 수 없어 표를 새로 만들어 옮긴다. 외래 키를 잠시 끈다.
        """
        if not self.path.exists():
            return
        con = sqlite3.connect(self.path)
        try:
            cols = {row[1] for row in con.execute("PRAGMA table_info(source)")}
            if cols and "timestamp" not in cols:
                con.execute("PRAGMA foreign_keys = OFF")
                con.executescript("""
                    ALTER TABLE source RENAME TO source_old;
                    CREATE TABLE source (
                        id INTEGER PRIMARY KEY, url TEXT NOT NULL, title TEXT DEFAULT '',
                        publisher TEXT DEFAULT '', published_at TEXT,
                        kind TEXT NOT NULL DEFAULT '기사'
                            CHECK (kind IN ('기사','공식SNS','연예인 본인 영상','브랜드','방송정보','기타')),
                        timestamp TEXT DEFAULT '', added_at TEXT NOT NULL);
                    INSERT INTO source(id, url, title, publisher, published_at, kind, added_at)
                        SELECT id, url, title, publisher, published_at, kind, added_at FROM source_old;
                    DROP TABLE source_old;
                """)
                con.commit()
        finally:
            con.close()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------ 설정
    def settings(self) -> dict[str, str]:
        with self.connect() as con:
            saved = {row["key"]: row["value"] for row in con.execute("SELECT key, value FROM setting")}
        return {**DEFAULT_SETTINGS, **saved}

    def save_settings(self, form: dict[str, str]) -> dict[str, str]:
        """알려진 키만 받는다. 값이 틀리면 하나도 저장하지 않는다."""
        clean: dict[str, str] = {}
        for key in DEFAULT_SETTINGS:
            if key not in form:
                continue
            value = str(form[key]).strip()
            if key in COLOR_KEYS:
                if not _HEX.match(value):
                    raise SettingError(f"{COLOR_LABELS[key]} 색은 #RRGGBB 형식이어야 합니다: {value!r}")
                value = value.upper()
            elif key == "video_seconds":
                if not value.isdigit() or not 15 <= int(value) <= 60:
                    raise SettingError("영상 길이는 15~60초 사이 숫자로 적어 주세요")
            elif key == "daily_upload_cap":
                if not value.isdigit() or not 0 <= int(value) <= 10:
                    raise SettingError("하루 업로드 상한은 0~10 사이로 적어 주세요 (양산형 판정 주의)")
            elif not value:
                raise SettingError(f"{key} 를 비울 수 없습니다")
            clean[key] = value
        with self.connect() as con:
            con.executemany("INSERT INTO setting(key, value) VALUES (?, ?) "
                            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", clean.items())
        self.log("설정", f"{len(clean)}개 저장: {', '.join(clean)}")
        return self.settings()

    # ------------------------------------------------------------ 작업 기록
    def log(self, kind: str, message: str, status: str = "완료") -> int:
        with self.connect() as con:
            cur = con.execute("INSERT INTO job(kind, status, message, created_at, finished_at) "
                              "VALUES (?, ?, ?, ?, ?)", (kind, status, message, now(), now()))
            return cur.lastrowid

    def run_job(self, kind: str, func, payload: dict | None = None):
        """작업 하나를 최대 3번까지 돌리고 결과를 기록한다.

        쿼터 초과처럼 «기다려야 하는» 실패는 func 가 `WaitError` 를 내면 다시 하지 않는다.
        """
        with self.connect() as con:
            job_id = con.execute("INSERT INTO job(kind, payload, status, created_at) VALUES (?, ?, '실행중', ?)",
                                 (kind, json.dumps(payload or {}, ensure_ascii=False), now())).lastrowid
        last = ""
        for attempt in range(1, MAX_TRIES + 1):
            try:
                result = func()
            except WaitError as exc:
                last = f"대기 필요: {exc}"
                break
            except Exception as exc:  # noqa: BLE001 — 기록이 목적이다
                last = f"{type(exc).__name__}: {exc}"
                with self.connect() as con:
                    con.execute("UPDATE job SET tries = ?, last_error = ? WHERE id = ?", (attempt, last, job_id))
                continue
            with self.connect() as con:
                con.execute("UPDATE job SET status = '완료', tries = ?, finished_at = ? WHERE id = ?",
                            (attempt, now(), job_id))
            return result
        with self.connect() as con:
            con.execute("UPDATE job SET status = '실패', last_error = ?, finished_at = ? WHERE id = ?",
                        (last, now(), job_id))
        return None

    def jobs(self, limit: int = 100) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute("SELECT * FROM job ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def counts(self) -> dict[str, int]:
        with self.connect() as con:
            return {
                "검증 대기": con.execute("SELECT COUNT(*) FROM claim WHERE relation = '추정'").fetchone()[0],
                # 대본은 상품 단위로 센다 — 한 안을 승인하면 나머지 안은 할 일이 아니다.
                "대본 승인 대기": con.execute(
                    "SELECT COUNT(DISTINCT product_id) FROM script WHERE product_id NOT IN"
                    " (SELECT product_id FROM script WHERE approved_by <> '')").fetchone()[0],
                "영상 승인 대기": con.execute("SELECT COUNT(*) FROM video WHERE status IN ('렌더됨', '검사실패')").fetchone()[0],
                # 최종 승인을 받았고 아직 올리지 않은 영상 (업로드 연결 전에는 스튜디오에서 직접 올린다)
                "올릴 영상": con.execute("SELECT COUNT(*) FROM video WHERE status = '승인됨'").fetchone()[0],
                "실패한 작업": con.execute("SELECT COUNT(*) FROM job WHERE status = '실패'").fetchone()[0],
            }

    # ------------------------------------------------------------ 백업/복원
    def backup_bytes(self) -> bytes:
        """DB 를 일관된 상태로 떠서 zip 으로. 안에 orbit.db 와 settings.json."""
        snapshot = self.path.with_suffix(".backup-tmp")
        try:
            with sqlite3.connect(self.path) as src, sqlite3.connect(snapshot) as dst:
                src.backup(dst)
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(snapshot, "orbit.db")
                zf.writestr("settings.json", json.dumps(self.settings(), ensure_ascii=False, indent=2))
                zf.writestr("README.txt", "셀럽오르빗 백업. 설정 → 복원에서 이 파일을 그대로 올리세요.\n")
        finally:
            snapshot.unlink(missing_ok=True)
        self.log("백업", f"{len(buffer.getvalue()):,}바이트")
        return buffer.getvalue()

    def restore_bytes(self, data: bytes) -> Path:
        """백업 zip 으로 되돌린다. 지금 DB 는 `orbit.db.before-restore-<시각>` 으로 남긴다."""
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise RestoreError("zip 파일이 아닙니다") from exc
        if "orbit.db" not in zf.namelist():
            raise RestoreError("셀럽오르빗 백업이 아닙니다 (orbit.db 가 없음)")
        incoming = self.path.with_suffix(".restore-tmp")
        incoming.write_bytes(zf.read("orbit.db"))
        try:
            with sqlite3.connect(incoming) as con:
                names = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.DatabaseError as exc:
            incoming.unlink(missing_ok=True)
            raise RestoreError("백업 안의 DB 가 깨져 있습니다") from exc
        missing = set(TABLES) - names
        if missing:
            incoming.unlink(missing_ok=True)
            raise RestoreError(f"셀럽오르빗 DB 가 아닙니다 (없는 표: {', '.join(sorted(missing))})")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        kept = self.path.with_name(f"{self.path.name}.before-restore-{stamp}")
        shutil.copy2(self.path, kept)
        shutil.move(incoming, self.path)
        self.log("복원", f"이전 DB 는 {kept.name} 로 남김")
        return kept


class WaitError(RuntimeError):
    """쿼터 초과 등 — 다시 시도하지 말고 기다려야 하는 실패."""
