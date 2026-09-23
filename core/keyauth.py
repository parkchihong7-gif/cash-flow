"""이중키 인증 — **16종 공통 표준.**

규격은 지어낸 것이 아니다. 이미 돌아가고 있는 두 프로그램의 관리자 매뉴얼
(공인중개사 기출문제 대시보드 / maim 네이버 블로그)에서 그대로 뽑았다.
프로그램마다 인증이 제각각이면 파는 사람이 관리를 못 한다.

    마스터 토큰   영구 · 본인만 · 절대 배포하지 않는다
     ├ 1차키      사람 1명당 1개 · 동시접속 제한 없음 · 이메일로 배포
     │  └ 2차키   PC·노트북·휴대폰 3개 · **기기당 1세션** · 중복 시 기존 기기 잠김
     └ 레거시     1차키 칸에 단독 입력 (예전에 뿌린 키를 계속 쓰게)

왜 두 겹인가
------------

한 겹이면 키 하나가 새는 순간 몇 명이 쓰는지 알 수 없다. 두 겹이면
**1차키는 사람을, 2차키는 기기를** 붙잡는다. 키를 빌려줘도 기기 수만큼만
쓸 수 있고, 같은 2차키로 다른 기기에서 들어오면 먼저 있던 쪽이 끊긴다.

되돌릴 수 있는 것과 없는 것
---------------------------

* **사용중지** 는 되돌릴 수 있다. 잠깐 막을 때 쓴다
* **삭제** 는 못 되돌린다. 그래서 화면에서 두 번 눌러야 한다
* **전체 초기화** 는 더 못 되돌린다. 그래서 '초기화' 를 정확히 타이핑해야 한다

이 세 단계는 매뉴얼에 적힌 그대로다. 손이 미끄러져서 지워지는 일이 없어야 한다.
"""

from __future__ import annotations

import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path

__all__ = [
    "manual_for_mail",
    "KeyAuth", "KeyError_", "IssuedSet", "KeyRow", "SessionRow",
    "DEVICES", "KIND_PRIMARY", "KIND_SECONDARY", "KIND_LEGACY",
    "ROLE_ADMIN", "ROLE_CLIENT", "ROLE_LABEL",
    "RESET_WORD", "MAX_BULK", "format_key", "normalize",
]

#: 2차키가 붙는 기기. 매뉴얼의 메일 문구 순서 그대로.
DEVICES: tuple[str, ...] = ("PC", "노트북", "휴대폰")

KIND_PRIMARY = "primary"
KIND_SECONDARY = "secondary"
KIND_LEGACY = "legacy"

#: 이 키로 무엇이 열리는가.
ROLE_ADMIN = "admin"      # 프로그램 관리자 — 산 사람. 자기 고객에게 키를 준다
ROLE_CLIENT = "client"    # 클라이언트 — 그 관리자의 고객. 쓰는 화면만

ROLE_LABEL = {ROLE_ADMIN: "관리자", ROLE_CLIENT: "클라이언트"}

#: 전체 초기화를 실행하려면 이 글자를 정확히 쳐야 한다.
RESET_WORD = "초기화"

#: 일괄 생성 상한. 매뉴얼 기준.
MAX_BULK = 500
DEFAULT_BULK = 10

#: 키 모양: XXXX-XXXX-XXXX. 헷갈리는 글자(0·O·1·I·L)는 뺀다.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_BLOCK, _BLOCKS = 4, 3

STATUS_LABEL = {"active": "사용중", "suspended": "사용중지", "expired": "만료"}


class KeyError_(RuntimeError):
    """키 규칙을 어겼을 때. (내장 KeyError 와 겹치지 않게 밑줄을 붙였다.)"""


SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_keys (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id   TEXT NOT NULL DEFAULT '',   -- '' 면 전 프로그램 공용
    kind         TEXT NOT NULL,              -- primary | secondary | legacy
    role         TEXT NOT NULL DEFAULT 'client',  -- admin | client
    issued_by    INTEGER,                    -- 발급한 관리자의 1차키. 비면 내가 준 것
    code         TEXT NOT NULL,
    parent_id    INTEGER,                    -- 2차키가 딸린 1차키
    device       TEXT NOT NULL DEFAULT '',   -- 2차키만
    holder_name  TEXT NOT NULL DEFAULT '',
    holder_email TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'active',   -- active | suspended
    expires_at   TEXT NOT NULL DEFAULT '',   -- '' 면 무제한
    note         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    last_used_at TEXT NOT NULL DEFAULT '',
    UNIQUE (program_id, code)
);

CREATE INDEX IF NOT EXISTS idx_auth_keys_parent ON auth_keys(parent_id);
CREATE INDEX IF NOT EXISTS idx_auth_keys_program ON auth_keys(program_id, kind);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id       INTEGER NOT NULL,           -- 2차키(또는 레거시) id
    token        TEXT NOT NULL UNIQUE,
    issued_at    TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at   TEXT NOT NULL DEFAULT '',
    revoked_why  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_key ON auth_sessions(key_id);
"""

#: 새로 더한 칸을 쓰는 인덱스. **표를 고친 뒤에** 만든다.
LATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_auth_keys_issuer ON auth_keys(issued_by);
CREATE INDEX IF NOT EXISTS idx_auth_keys_role ON auth_keys(program_id, role);
"""

REVOKED_MESSAGE = "다른 기기에서 로그인되어 세션이 종료되었습니다"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def format_key(raw: str = "") -> str:
    """XXXX-XXXX-XXXX 한 벌을 만든다."""
    if raw:
        return raw
    blocks = ["".join(secrets.choice(_ALPHABET) for _ in range(_BLOCK))
              for _ in range(_BLOCKS)]
    return "-".join(blocks)


def normalize(code: str) -> str:
    """사람이 친 것을 비교할 수 있는 꼴로.

    소문자·공백·하이픈 빠뜨림을 모두 받아 준다. 키를 손으로 옮겨 적다 보면
    반드시 생기는 일이라, 여기서 받아 주지 않으면 문의가 늘어난다.
    """
    cleaned = "".join(ch for ch in (code or "").upper()
                      if ch.isascii() and ch.isalnum())
    if len(cleaned) != _BLOCK * _BLOCKS:
        return cleaned
    return "-".join(cleaned[i:i + _BLOCK] for i in range(0, len(cleaned), _BLOCK))


@dataclass
class KeyRow:
    """키 한 줄."""

    id: int
    program_id: str
    kind: str
    role: str
    issued_by: int | None
    code: str
    parent_id: int | None
    device: str
    holder_name: str
    holder_email: str
    status: str
    expires_at: str
    note: str
    created_at: str
    last_used_at: str

    @property
    def expired(self) -> bool:
        if not self.expires_at:
            return False
        return date.fromisoformat(self.expires_at) < date.today()

    @property
    def usable(self) -> bool:
        return self.status == "active" and not self.expired

    @property
    def state(self) -> str:
        if self.expired:
            return "expired"
        return self.status

    @property
    def state_label(self) -> str:
        return STATUS_LABEL.get(self.state, self.state)

    @property
    def kind_label(self) -> str:
        return {KIND_PRIMARY: "1차키", KIND_SECONDARY: "2차키",
                KIND_LEGACY: "레거시"}.get(self.kind, self.kind)

    @property
    def role_label(self) -> str:
        return ROLE_LABEL.get(self.role, self.role)

    @property
    def is_admin(self) -> bool:
        """이 키로 관리자 화면이 열리는가."""
        return self.role == ROLE_ADMIN

    @property
    def mine(self) -> bool:
        """내가(메인 관리자가) 직접 준 키인가."""
        return self.issued_by is None


@dataclass
class SessionRow:
    id: int
    key_id: int
    token: str
    issued_at: str
    last_seen_at: str
    revoked_at: str
    revoked_why: str

    @property
    def live(self) -> bool:
        return not self.revoked_at


@dataclass
class IssuedSet:
    """한 사람에게 발급한 한 벌 — 1차키 1개 + 2차키 3개."""

    holder_name: str
    holder_email: str
    primary: str
    secondary: dict[str, str]      # 기기 → 키
    program_id: str = ""
    service_url: str = ""
    role: str = ROLE_CLIENT
    primary_id: int = 0

    @property
    def for_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    def mail_subject(self, product: str) -> str:
        return f"[{product}] 접속 안내"

    def mail_body(self, product: str) -> str:
        """매뉴얼의 메일 문구를 그대로 따른다.

        **주소가 없을 수도 있다.** 자기 서버에 직접 세워 쓰는 상품을 산
        분께는 열 주소가 아직 없다 — 그분이 세우고 나서야 생긴다. 그때는
        주소 자리에 설치 안내서를 가리킨다. 우리 주소를 대신 넣으면
        그분 고객의 글이 우리 서버에 쌓인다.
        """
        자기서버 = self.for_admin and not self.service_url
        if 자기서버:
            머리 = (f"{self.holder_name}님, 이 프로그램은 **사장님 서버에 직접 세워** "
                    f"쓰십니다. 함께 보내 드린 설치 안내서를 따라 한 번만 세우시면, "
                    f"그 뒤로는 글도 설정도 전부 사장님 자리에 쌓입니다.")
            자리 = "설치를 마치신 뒤, 그 화면에서 아래 인증키를 넣어 주세요."
        else:
            머리 = (f"{self.holder_name}님, 아래 링크로 접속하시면 1차, 2차 인증 후 "
                    f"이용 가능합니다."
                    + (" 관리자 화면이 열리며, 고객께 드릴 키를 직접 발급하실 수 "
                       "있습니다." if self.for_admin else ""))
            자리 = self.service_url or "(서비스 주소)"
        lines = [
            머리,
            "",
            자리,
            "",
            f"* 1차 인증키 : {self.primary}",
            "",
            "* 2차 인증키",
        ]
        lines += [f"- {device} : {self.secondary[device]}"
                  for device in DEVICES if device in self.secondary]
        return "\n".join(lines)

    def copy_text(self, product: str) -> str:
        """보낼 글 전체. 제목 한 줄 + 본문."""
        return f"{self.mail_subject(product)}\n\n{self.mail_body(product)}"

    def plain_mail(self, note: str, manual: str = "") -> str:
        """**글자판 대비.** HTML 을 못 읽는 메일 앱에서 대신 보일 글.

        본판은 :func:`core.keymail.mail_html` 이 만드는 꾸민 판이다. 여기는
        그것이 통하지 않을 때만 쓰인다 — 그래서 모양을 내려 애쓰지 않는다.
        예전에는 `────────` 로 칸을 갈랐는데 받는 분 화면에서는 영문 모를
        줄로만 보였다. 빈 줄과 이름표면 충분하다.

        :param note: 사람이 고친 접속키 안내 글.
        :param manual: 붙일 매뉴얼. 관리자냐 고객이냐에 따라 다른 것이 와야
            한다 — 고객에게 관리자 매뉴얼을 보내면 «접속 코드 관리» 같은,
            그분 화면에 없는 것을 찾게 된다.
        """
        글 = note.strip()
        if manual.strip():
            이름 = "관리자 매뉴얼" if self.for_admin else "사용 설명서"
            글 += f"\n\n\n[{이름}]\n\n{manual.strip()}"
        return 글


class KeyAuth:
    """이중키 저장소. 같은 SQLite 파일을 대시보드와 나눠 쓴다."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            # 칸을 먼저 더하고 인덱스를 만든다. 순서가 바뀌면 예전 파일에서
            # '없는 칸에 인덱스' 라며 통째로 죽는다 — 열려 있던 DB 가 못 열린다.
            self._add_missing_columns(conn)
            conn.executescript(LATE_INDEXES)

    @staticmethod
    def _add_missing_columns(conn) -> None:
        """예전에 만든 파일에 새 칸을 더한다.

        `CREATE TABLE IF NOT EXISTS` 는 이미 있는 표를 건드리지 않는다.
        키를 새로 발급받게 하지 않으려면 여기서 채워 넣어야 한다.
        """
        have = {row["name"] for row in conn.execute("PRAGMA table_info(auth_keys)")}
        if "role" not in have:
            conn.execute("ALTER TABLE auth_keys ADD COLUMN "
                         "role TEXT NOT NULL DEFAULT 'client'")
        if "issued_by" not in have:
            conn.execute("ALTER TABLE auth_keys ADD COLUMN issued_by INTEGER")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ────────────────────────────────────────────────────────── 발급
    def issue_set(self, name: str, email: str, program_id: str = "",
                  service_url: str = "", expires_days: int | None = None,
                  note: str = "", role: str = ROLE_CLIENT,
                  issued_by: int | None = None) -> IssuedSet:
        """한 사람에게 1차키 1개 + 2차키 3개를 한 번에.

        매뉴얼의 '이메일로 배포' 가 하는 일이다. 이름과 이메일만 받는다.

        Args:
            role: `admin` 이면 그 사람이 **그 프로그램의 관리자**가 되어
                자기 고객에게 키를 발급할 수 있다. 파는 키다.
            issued_by: 발급한 관리자의 1차키 id. 비우면 내가 준 것.

        Raises:
            KeyError_: 관리자키를 관리자가 만들려 할 때. **파는 것은 나만** 한다.
        """
        if role not in (ROLE_ADMIN, ROLE_CLIENT):
            raise KeyError_(f"모르는 역할입니다: {role}")
        if role == ROLE_ADMIN and issued_by is not None:
            # 이걸 허용하면 산 사람이 관리자를 찍어 내며 재판매할 수 있다.
            raise KeyError_("관리자키는 발급하실 수 없습니다. 고객용 키만 만드실 수 있습니다")
        name = (name or "").strip()
        email = (email or "").strip()
        if not name:
            raise KeyError_("이름을 적어 주세요. 누구에게 준 키인지 남아야 합니다")
        if "@" not in email:
            raise KeyError_("이메일 주소를 확인해 주세요")

        expires = self._expiry(expires_days)
        with self._conn() as conn:
            primary = self._insert(conn, program_id, KIND_PRIMARY,
                                   holder_name=name, holder_email=email,
                                   expires_at=expires, note=note,
                                   role=role, issued_by=issued_by)
            secondary: dict[str, str] = {}
            for device in DEVICES:
                # 역할과 발급자를 2차키에도 그대로 적는다. 2차키만 보고도
                # 무엇이 열리는지 알 수 있어야 한다.
                code = self._insert(conn, program_id, KIND_SECONDARY,
                                    parent_id=primary[0], device=device,
                                    holder_name=name, holder_email=email,
                                    expires_at=expires, note=note,
                                    role=role, issued_by=issued_by)[1]
                secondary[device] = code
        return IssuedSet(holder_name=name, holder_email=email,
                         primary=primary[1], secondary=secondary,
                         program_id=program_id, service_url=service_url,
                         role=role, primary_id=primary[0])

    def adopt_set(self, *, primary_code: str, secondary: dict[str, str],
                  name: str, email: str, program_id: str = "",
                  service_url: str = "", expires_days: int | None = None,
                  note: str = "", role: str = ROLE_CLIENT,
                  issued_by: int | None = None) -> IssuedSet:
        """**다른 곳에서 만든** 한 벌을 그대로 이 장부에 받아 적는다.

        키 서버(구글 시트)가 만든 코드를 대시보드 목록에도 보이게 하려고
        둔다. 코드를 여기서 새로 뽑으면 **고객이 받은 키와 달라져** 그
        자리에서 못 들어온다. 그래서 받은 코드를 그대로 쓴다.

        Args:
            primary_code: 서버가 만든 1차키.
            secondary: 기기 이름 → 서버가 만든 2차키.

        Raises:
            KeyError_: 같은 코드가 이미 있을 때. 두 번 적으면 목록이 겹친다.
        """
        if not primary_code:
            raise KeyError_("받아 적을 1차키가 없습니다")
        expires = self._expiry(expires_days)
        with self._conn() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO auth_keys (program_id, kind, role, issued_by, code,"
                    " parent_id, device, holder_name, holder_email, expires_at,"
                    " note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (program_id, KIND_PRIMARY, role, issued_by, primary_code,
                     None, "", name, email, expires, note, _now()))
                primary_id = int(cursor.lastrowid)
                for device, code in secondary.items():
                    conn.execute(
                        "INSERT INTO auth_keys (program_id, kind, role, issued_by, code,"
                        " parent_id, device, holder_name, holder_email, expires_at,"
                        " note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (program_id, KIND_SECONDARY, role, issued_by, code,
                         primary_id, device, name, email, expires, note, _now()))
            except sqlite3.IntegrityError as exc:
                raise KeyError_("이미 적혀 있는 키입니다") from exc
        return IssuedSet(holder_name=name, holder_email=email,
                         primary=primary_code, secondary=dict(secondary),
                         program_id=program_id, service_url=service_url,
                         role=role, primary_id=primary_id)

    def bulk_legacy(self, count: int = DEFAULT_BULK, program_id: str = "",
                    expires_days: int | None = None) -> list[str]:
        """이름 없이 코드만 미리 찍어 둔다 (매뉴얼의 '키 일괄 생성').

        1차/2차 구분이 없는 단독 키다. 현장에서 종이로 나눠 줄 때 쓴다.
        """
        if count < 1:
            raise KeyError_("개수는 1 이상이어야 합니다")
        if count > MAX_BULK:
            raise KeyError_(f"한 번에 {MAX_BULK}개까지만 만들 수 있습니다")

        expires = self._expiry(expires_days)
        made: list[str] = []
        with self._conn() as conn:
            for _ in range(count):
                made.append(self._insert(conn, program_id, KIND_LEGACY,
                                         expires_at=expires)[1])
        return made

    def _expiry(self, days: int | None) -> str:
        if days is None or days == 0:
            return ""            # 비우면 무제한
        if days < 0:
            raise KeyError_("유효기간은 0 이상이어야 합니다")
        return (date.today() + timedelta(days=days)).isoformat()

    def _insert(self, conn, program_id: str, kind: str, *, parent_id: int | None = None,
                device: str = "", holder_name: str = "", holder_email: str = "",
                expires_at: str = "", note: str = "", role: str = ROLE_CLIENT,
                issued_by: int | None = None) -> tuple[int, str]:
        """키 하나를 넣는다. 코드가 겹치면 다시 뽑는다."""
        for _ in range(12):
            code = format_key()
            try:
                cursor = conn.execute(
                    "INSERT INTO auth_keys (program_id, kind, role, issued_by, code,"
                    " parent_id, device, holder_name, holder_email, expires_at,"
                    " note, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (program_id, kind, role, issued_by, code, parent_id, device,
                     holder_name, holder_email, expires_at, note, _now()))
                return int(cursor.lastrowid), code
            except sqlite3.IntegrityError:
                continue         # 같은 코드가 나왔다. 사실상 안 생기지만 대비한다.
        raise KeyError_("키를 만들지 못했습니다. 다시 시도해 주세요")

    # ────────────────────────────────────────────────────────── 조회
    def get(self, key_id: int) -> KeyRow:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM auth_keys WHERE id = ?", (key_id,)).fetchone()
        if row is None:
            raise KeyError_(f"없는 키입니다: {key_id}")
        return self._row(row)

    def find(self, code: str, program_id: str = "") -> KeyRow | None:
        """코드로 찾는다. 프로그램 전용 키를 먼저, 없으면 공용 키를."""
        wanted = normalize(code)
        if not wanted:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM auth_keys WHERE code = ? AND program_id IN (?, '')"
                " ORDER BY CASE program_id WHEN ? THEN 0 ELSE 1 END LIMIT 1",
                (wanted, program_id, program_id)).fetchone()
        return self._row(row) if row else None

    #: `issued_by` 를 안 넘겼다는 뜻. None 은 '내가 준 것만' 이라는 뜻이라
    #: 기본값으로 쓸 수 없어 따로 둔다.
    ANY_ISSUER = object()

    def list_keys(self, kind: str = "", program_id: str | None = None,
                  parent_id: int | None = None, role: str = "",
                  issued_by=ANY_ISSUER) -> list[KeyRow]:
        """키 목록.

        Args:
            issued_by: 넘기면 **그 사람이 발급한 것만.** `None` 은 내가 준 것만.
                안 넘기면 전부 — 메인 관리자 화면에서만 쓴다.
        """
        sql = "SELECT * FROM auth_keys WHERE 1=1"
        params: list = []
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if program_id is not None:
            sql += " AND program_id = ?"
            params.append(program_id)
        if parent_id is not None:
            sql += " AND parent_id = ?"
            params.append(parent_id)
        if role:
            sql += " AND role = ?"
            params.append(role)
        if issued_by is not self.ANY_ISSUER:
            if issued_by is None:
                sql += " AND issued_by IS NULL"
            else:
                sql += " AND issued_by = ?"
                params.append(issued_by)
        sql += " ORDER BY id DESC"
        with self._conn() as conn:
            return [self._row(row) for row in conn.execute(sql, params)]

    def owns(self, key_id: int, issuer_id: int) -> bool:
        """`issuer_id` 관리자가 이 키를 건드려도 되는가.

        옆 학원의 수강생 키를 정지시키거나 지울 수 있으면 안 된다. 화면에서
        안 그리는 것과 별개로, 손대는 길마다 여기를 지난다.
        """
        try:
            row = self.get(key_id)
        except KeyError_:
            return False
        return row.issued_by == issuer_id

    def counts(self, program_id: str | None = None,
               issued_by=ANY_ISSUER) -> dict[str, int]:
        rows = self.list_keys(program_id=program_id, issued_by=issued_by)
        primary = [row for row in rows if row.kind == KIND_PRIMARY]
        return {
            "primary": len(primary),
            "secondary": sum(1 for row in rows if row.kind == KIND_SECONDARY),
            "legacy": sum(1 for row in rows if row.kind == KIND_LEGACY),
            "suspended": sum(1 for row in rows if row.status == "suspended"),
            "expired": sum(1 for row in rows if row.expired),
            "holders": len({row.holder_email for row in primary if row.holder_email}),
            "admins": sum(1 for row in primary if row.is_admin),
            "clients": sum(1 for row in primary if not row.is_admin),
        }

    @staticmethod
    def _row(row: sqlite3.Row) -> KeyRow:
        return KeyRow(
            id=row["id"], program_id=row["program_id"], kind=row["kind"],
            role=row["role"], issued_by=row["issued_by"],
            code=row["code"], parent_id=row["parent_id"], device=row["device"],
            holder_name=row["holder_name"], holder_email=row["holder_email"],
            status=row["status"], expires_at=row["expires_at"], note=row["note"],
            created_at=row["created_at"], last_used_at=row["last_used_at"])

    # ────────────────────────────────────────────────────────── 관리
    def suspend(self, key_id: int) -> KeyRow:
        """되돌릴 수 있는 일시정지."""
        return self._set_status(key_id, "suspended")

    def resume(self, key_id: int) -> KeyRow:
        return self._set_status(key_id, "active")

    def _set_status(self, key_id: int, status: str) -> KeyRow:
        with self._conn() as conn:
            changed = conn.execute("UPDATE auth_keys SET status = ? WHERE id = ?",
                                   (status, key_id)).rowcount
        if not changed:
            raise KeyError_(f"없는 키입니다: {key_id}")
        if status == "suspended":
            # 1차키를 정지했는데 그 사람이 2차키로 들어와 있으면 그대로 남는다.
            # 정지 버튼이 지금 들어와 있는 사람을 못 내보내면 의미가 없다.
            for target in self._family(key_id):
                self._revoke_sessions_of(target, "키가 사용중지되었습니다")
        return self.get(key_id)

    def _family(self, key_id: int) -> list[int]:
        """키 자신과, 1차키라면 딸린 2차키까지."""
        with self._conn() as conn:
            rows = conn.execute("SELECT id FROM auth_keys WHERE parent_id = ?",
                                (key_id,)).fetchall()
        return [key_id, *(row["id"] for row in rows)]

    def delete(self, key_id: int) -> int:
        """영구 삭제. 1차키를 지우면 딸린 2차키도 같이 간다.

        2차키 하나만 지우면 **1차키와 나머지 2차키는 그대로 남는다.**
        기기 하나를 잃어버렸을 때 그 몫만 정리하는 쓰임이다 (매뉴얼).
        """
        row = self.get(key_id)
        with self._conn() as conn:
            ids = [key_id]
            if row.kind == KIND_PRIMARY:
                ids += [item["id"] for item in conn.execute(
                    "SELECT id FROM auth_keys WHERE parent_id = ?", (key_id,))]
            marks = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM auth_sessions WHERE key_id IN ({marks})", ids)
            conn.execute(f"DELETE FROM auth_keys WHERE id IN ({marks})", ids)
        return len(ids)

    def reset_all(self, confirm: str, program_id: str | None = None,
                  issued_by=ANY_ISSUER) -> int:
        """전부 지운다. **'초기화' 를 정확히 쳐야 한다.**

        Args:
            program_id: 비우면 **16종 전부.** 프로그램을 주면 그것만.
            issued_by: 넘기면 **그 사람이 발급한 것만.** 프로그램 관리자가
                자기 고객 키를 정리할 때 쓴다. 안 넘기면 전부 — 나만 한다.
        """
        if (confirm or "").strip() != RESET_WORD:
            raise KeyError_(
                f"전체 초기화를 하려면 '{RESET_WORD}' 라고 정확히 적어 주세요. "
                f"되돌릴 수 없습니다")

        rows = self.list_keys(program_id=program_id, issued_by=issued_by)
        ids = [row.id for row in rows]
        if not ids:
            return 0
        with self._conn() as conn:
            marks = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM auth_sessions WHERE key_id IN ({marks})", ids)
            conn.execute(f"DELETE FROM auth_keys WHERE id IN ({marks})", ids)
        return len(ids)

    # ────────────────────────────────────────────────────────── 인증
    def authenticate(self, primary_code: str, secondary_code: str = "",
                     program_id: str = "", device_lock: bool = True
                     ) -> tuple[str, KeyRow]:
        """1차키(+2차키)로 들어온다. 세션 토큰과 쓰인 키를 돌려준다.

        Args:
            device_lock: 끄면 2차키를 받되 기존 기기를 끊지 않는다.
                여럿이 한 화면을 같이 보는 곳(학회 사무국 같은)을 위한 것이다.

        Raises:
            KeyError_: 키가 없거나, 정지·만료됐거나, 짝이 안 맞을 때.
        """
        primary = self.find(primary_code, program_id)
        if primary is None:
            raise KeyError_("1차 인증키가 맞지 않습니다")
        if not primary.usable:
            raise KeyError_(
                "만료된 키입니다" if primary.expired else "사용중지된 키입니다")

        # 레거시 단일키는 1차키 칸만으로 통과시킨다 (하위호환).
        if primary.kind == KIND_LEGACY:
            self._touch(primary.id)
            return self._open_session(primary.id, device_lock=False), primary

        if primary.kind != KIND_PRIMARY:
            raise KeyError_("1차 인증키 칸에는 1차키를 넣어 주세요")

        secondary = self.find(secondary_code, program_id)
        if secondary is None:
            raise KeyError_("2차 인증키가 맞지 않습니다")
        if secondary.kind != KIND_SECONDARY:
            raise KeyError_("2차 인증키 칸에는 2차키를 넣어 주세요")
        if secondary.parent_id != primary.id:
            # 남의 2차키를 끼워 넣는 경우. 둘 다 맞아야 통과한다.
            raise KeyError_("1차키와 2차키가 서로 짝이 아닙니다")
        if not secondary.usable:
            raise KeyError_(
                "만료된 2차키입니다" if secondary.expired else "사용중지된 2차키입니다")

        self._touch(primary.id)
        self._touch(secondary.id)
        return self._open_session(secondary.id, device_lock), secondary

    def _touch(self, key_id: int) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE auth_keys SET last_used_at = ? WHERE id = ?",
                         (_now(), key_id))

    def _open_session(self, key_id: int, device_lock: bool) -> str:
        """세션을 연다. 기기 잠금이 켜져 있으면 먼저 있던 세션을 끊는다."""
        if device_lock:
            self._revoke_sessions_of(key_id, REVOKED_MESSAGE)
        token = secrets.token_urlsafe(24)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO auth_sessions (key_id, token, issued_at, last_seen_at)"
                " VALUES (?,?,?,?)", (key_id, token, _now(), _now()))
        return token

    def _revoke_sessions_of(self, key_id: int, why: str) -> int:
        with self._conn() as conn:
            return conn.execute(
                "UPDATE auth_sessions SET revoked_at = ?, revoked_why = ?"
                " WHERE key_id = ? AND revoked_at = ''",
                (_now(), why, key_id)).rowcount

    def check_session(self, token: str) -> tuple[bool, str]:
        """세션이 아직 살아 있는가. 죽었으면 **왜 죽었는지**도 돌려준다.

        끊긴 이유를 말해 주지 않으면 쓰는 사람이 고장으로 여긴다.
        """
        if not token:
            return False, "로그인이 필요합니다"
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM auth_sessions WHERE token = ?",
                               (token,)).fetchone()
            if row is None:
                return False, "로그인이 필요합니다"
            if row["revoked_at"]:
                return False, row["revoked_why"] or "세션이 종료되었습니다"
            key = conn.execute("SELECT * FROM auth_keys WHERE id = ?",
                               (row["key_id"],)).fetchone()
            if key is None:
                return False, "키가 삭제되었습니다"
            conn.execute("UPDATE auth_sessions SET last_seen_at = ? WHERE id = ?",
                         (_now(), row["id"]))
        key_row = self._row(key)
        for row in self._chain(key_row):
            if not row.usable:
                return False, ("만료된 키입니다" if row.expired
                               else "사용중지된 키입니다")
        return True, ""

    def _chain(self, key: KeyRow) -> list[KeyRow]:
        """이 키와, 2차키라면 그 위의 1차키까지.

        사람(1차키)을 정지했으면 기기(2차키)가 멀쩡해도 막아야 한다.
        """
        chain = [key]
        if key.parent_id:
            try:
                chain.append(self.get(key.parent_id))
            except KeyError_:
                pass
        return chain

    def close_session(self, token: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE auth_sessions SET revoked_at = ?, revoked_why = ?"
                " WHERE token = ? AND revoked_at = ''",
                (_now(), "로그아웃했습니다", token))

    def sessions_of(self, key_id: int) -> list[SessionRow]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM auth_sessions WHERE key_id = ? ORDER BY id DESC",
                (key_id,)).fetchall()
        return [SessionRow(id=r["id"], key_id=r["key_id"], token=r["token"],
                           issued_at=r["issued_at"], last_seen_at=r["last_seen_at"],
                           revoked_at=r["revoked_at"], revoked_why=r["revoked_why"])
                for r in rows]

    def live_sessions(self, program_id: str | None = None) -> int:
        with self._conn() as conn:
            if program_id is None:
                row = conn.execute(
                    "SELECT COUNT(*) c FROM auth_sessions WHERE revoked_at = ''"
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) c FROM auth_sessions s"
                    " JOIN auth_keys k ON k.id = s.key_id"
                    " WHERE s.revoked_at = '' AND k.program_id = ?",
                    (program_id,)).fetchone()
        return int(row["c"])

    # ────────────────────────────────────────────────── 마스터 토큰
    @staticmethod
    def master_matches(given: str, expected: str) -> bool:
        """마스터 토큰 비교. 글자 수로 답이 새지 않게 상수 시간으로 본다."""
        return hmac.compare_digest(
            sha256((given or "").strip().encode()).hexdigest(),
            sha256((expected or "").strip().encode()).hexdigest())


#: 안내문에 붙일 매뉴얼의 최대 길이.
#:
#: 매뉴얼이 통째로 들어가면 메일이 스크롤 지옥이 된다. 받는 분은 키를 보러
#: 열었는데 본문이 5천 자다. 앞부분만 넣고 나머지는 화면에서 보시게 한다.
MANUAL_IN_MAIL = 2500


def manual_for_mail(program, for_admin: bool) -> str:
    """안내문에 붙일 매뉴얼 글.

    관리자에게는 관리자 매뉴얼, 고객에게는 사용 설명서. 반대로 보내면
    그분 화면에 없는 기능을 찾게 된다.

    마크다운 기호는 덜어 낸다. 메일은 글자 그대로 보이는 곳이라
    `## 1. 무엇` 이 제목으로 안 보이고 `#` 이 그냥 찍힌다.
    """
    상대 = program.manuals.admin if for_admin else program.manuals.client
    if not 상대:
        return ""
    path = program.resolve(상대)
    if not path.is_file():
        return ""

    쓸것 = []
    for 줄 in path.read_text(encoding="utf-8").split("\n"):
        벗김 = 줄.lstrip("#").strip() if 줄.lstrip().startswith("#") else 줄
        쓸것.append(벗김.replace("**", "").replace("`", ""))
    글 = "\n".join(쓸것).strip()

    if len(글) > MANUAL_IN_MAIL:
        글 = 글[:MANUAL_IN_MAIL].rstrip() + "\n\n(줄임 — 나머지는 프로그램 안 매뉴얼에서 보세요)"
    return 글
