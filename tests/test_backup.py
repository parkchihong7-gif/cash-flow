"""클라우드에 올린 대시보드에서 고객 DB 를 집으로 받아 오는 길.

고객 이름·이메일·발급한 키가 전부 클라우드에만 있게 된다. 호스팅 계정이
잠기면 판 키의 목록이 통째로 사라지므로, 받아 오는 길이 막히지 않는지
여기서 지킨다.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from core import auth
from core.backup import backup_name, copy_db
from core.keyauth import KeyAuth
from dashboard.app import create_app


@pytest.fixture
def db_with_keys(tmp_path):
    """키가 몇 개 들어 있는 DB 를 만든다."""
    path = tmp_path / "app.db"
    keys = KeyAuth(path)
    keys.issue_set(name="홍길동", email="hong@example.com",
                   program_id="agency-kit")
    return path


def test_쓰는_중에_떠도_깨지지_않는다(db_with_keys, tmp_path):
    """cp 로 복사하면 반쯤 쓰다 만 파일이 나온다. 그래서 온라인 백업을 쓴다."""
    dest = tmp_path / "받은것.db"
    conn = sqlite3.connect(db_with_keys)
    conn.execute("begin")
    conn.execute("insert into auth_keys (program_id, kind, role, code, status,"
                 " created_at) values ('x','primary','client','AAAA','active','')")
    # 커밋하지 않은 채로 떠낸다 — 진행 중인 쓰기가 섞여 들어오면 안 된다.
    size = copy_db(db_with_keys, dest)
    conn.rollback()
    conn.close()

    assert size > 0
    받은것 = sqlite3.connect(dest)
    assert 받은것.execute("select count(*) from auth_keys").fetchone()[0] == 4
    assert 받은것.execute(
        "select count(*) from auth_keys where code = 'AAAA'").fetchone()[0] == 0


def test_원본이_없으면_말해_준다(tmp_path):
    with pytest.raises(FileNotFoundError):
        copy_db(tmp_path / "없는것.db", tmp_path / "나온것.db")


def test_파일_이름에_날짜가_들어간다():
    이름 = backup_name(datetime(2026, 9, 19, 13, 39))
    assert 이름 == "dashboard-20260919-1339.db"
    # 날짜가 없으면 덮어써서, 어제 것으로 되살릴 수가 없다.
    assert backup_name(datetime(2026, 9, 20, 13, 39)) != 이름


def test_접속_코드_없이는_고객_DB_를_못_받는다(tmp_path):
    """이 한 줄이 뚫리면 주소만 알면 누구나 고객 명단을 가져간다."""
    client = TestClient(create_app(tmp_path / "app.db"), follow_redirects=False)
    답 = client.get("/backup.db")
    assert 답.status_code in (302, 303, 307)
    assert "/login" in 답.headers["location"]


def test_코드를_넣으면_진짜_DB_가_내려온다(tmp_path):
    path = tmp_path / "app.db"
    KeyAuth(path).issue_set(name="홍길동", email="hong@example.com",
                            program_id="agency-kit")
    client = TestClient(create_app(path))
    client.post("/login", data={"code": auth.access_code()})

    답 = client.get("/backup.db")
    assert 답.status_code == 200
    assert 답.content[:13] == b"SQLite format", "DB 가 아니라 다른 것이 내려왔습니다"
    assert "attachment" in 답.headers.get("content-disposition", "")

    받은것 = tmp_path / "받은것.db"
    받은것.write_bytes(답.content)
    conn = sqlite3.connect(받은것)
    assert conn.execute("select count(*) from auth_keys").fetchone()[0] == 4


def test_서버에_사본이_쌓이지_않는다(tmp_path):
    """내려보낸 임시 파일을 안 지우면 그 자체가 새어 나갈 자리가 된다."""
    import tempfile
    from pathlib import Path

    client = TestClient(create_app(tmp_path / "app.db"))
    client.post("/login", data={"code": auth.access_code()})
    client.get("/backup.db")

    남은것 = list(Path(tempfile.gettempdir()).glob("cash-flow-dashboard-*.db"))
    assert not 남은것, f"임시 사본이 남았습니다: {남은것}"
