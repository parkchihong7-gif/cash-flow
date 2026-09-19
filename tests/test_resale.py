"""파는 키와 쓰는 키 — **두 겹의 판매 구조.**

프로그램을 팔면 산 사람이 그 프로그램의 관리자가 된다. 그 사람도 자기
고객에게 키를 줘야 한다. 학원에 공인중개사 대시보드를 팔면 학원장은 수강생
쉰 명에게 키를 나눠 줘야 하고, 내가 그 쉰 명을 대신 발급해 줄 수는 없다.

    나 (메인 관리자)
     └ role="admin"  → 학원장 (프로그램 관리자). 관리자 화면 + 발급 자리
        └ role="client" → 수강생 (클라이언트). 쓰는 화면만

여기서 지켜야 하는 선은 셋이다.

    1. 학원장은 **자기가 발급한 키만** 본다 (옆 학원 수강생 명단이 보이면 안 된다)
    2. 학원장은 **관리자키를 못 만든다** (허용하면 재판매가 열린다)
    3. 수강생은 **아무것도 발급 못 한다**

화면에서 안 그리는 것으로는 부족해, 주소를 직접 쳐서 들어오는 길까지 본다.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from core import auth
from core.keyauth import KIND_PRIMARY, ROLE_ADMIN, ROLE_CLIENT, KeyAuth
from dashboard.app import create_app

KEY = re.compile(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}")
PROGRAM = "exam-drill"


@pytest.fixture
def shop(tmp_path):
    """가게 하나. 앱과 키 저장소를 같이 들고 있는다."""
    path = tmp_path / "resale.db"
    app = create_app(path)
    owner = TestClient(app)
    assert owner.post("/login", data={"code": auth.access_code()}).status_code == 200

    class Shop:
        def __init__(self):
            self.app = app
            self.owner = owner
            self.keys = KeyAuth(path)

        def issue(self, client, url, **data) -> list[str]:
            """키 한 벌을 발급하고 **안내문에서** 코드를 꺼낸다."""
            response = client.post(url, data=data, follow_redirects=False)
            assert response.status_code == 303, response.status_code
            body = client.get(response.headers["location"]).text
            assert "<textarea" in body, "안내문이 안 나왔다"
            mail = body[body.index("<textarea"):body.index("</textarea>")]
            return KEY.findall(mail)

        def sell(self, name: str, email: str) -> list[str]:
            """내가 판다 — 관리자키."""
            return self.issue(self.owner, f"/apps/{PROGRAM}/admin/keys/issue",
                              role=ROLE_ADMIN, name=name, email=email)

        def enter(self, codes: list[str]) -> TestClient:
            visitor = TestClient(self.app)
            visitor.post(f"/c/{PROGRAM}",
                         data={"primary": codes[0], "secondary": codes[1]})
            return visitor

        def row(self, holder: str):
            return next(row for row in self.keys.list_keys(
                kind=KIND_PRIMARY, program_id=PROGRAM)
                if row.holder_name == holder)

    return Shop()


@pytest.fixture
def boss(shop):
    """학원장 — 내가 판 사람."""
    return shop.enter(shop.sell("학원A원장", "a@academy.kr"))


# ─────────────────────────────────────────── 산 사람은 관리자가 된다
def test_판_사람은_관리자_화면이_열린다(boss):
    body = boss.get(f"/c/{PROGRAM}/t/home").text

    assert "관리자 모드" in body
    assert "/t/keys" in body, "키를 줄 자리가 없으면 고객에게 팔 수가 없다"


def test_판_사람에게_내_자리는_열지_않는다(boss):
    """검증값 기본 세팅과 파일 위치는 **내가 상품을 손보는 자리**다."""
    body = boss.get(f"/c/{PROGRAM}/t/home").text

    assert "/t/presets" not in body
    assert "/t/files" not in body
    assert "통합 대시보드" not in body


def test_산_사람이_자기_고객에게_키를_준다(shop, boss):
    codes = shop.issue(boss, f"/c/{PROGRAM}/keys/issue",
                       name="수강생1", email="s1@academy.kr")

    assert len(codes) == 4, "1차키 1개 + 2차키 3개"
    assert shop.row("수강생1").role == ROLE_CLIENT
    assert shop.row("수강생1").issued_by == shop.row("학원A원장").id


def test_그_고객은_쓰는_화면만_본다(shop, boss):
    codes = shop.issue(boss, f"/c/{PROGRAM}/keys/issue",
                       name="수강생1", email="s1@academy.kr")
    student = shop.enter(codes)
    body = student.get(f"/c/{PROGRAM}/t/home").text

    assert "클라이언트 모드" in body
    assert "/t/keys" not in body, "수강생에게 발급 자리가 보인다"


# ─────────────────────────────────────────────── 재판매는 막는다
def test_산_사람은_관리자키를_못_만든다(shop, boss):
    """허용하면 산 사람이 관리자를 찍어 내며 재판매한다. **파는 것은 나만.**"""
    boss.post(f"/c/{PROGRAM}/keys/issue",
              data={"role": ROLE_ADMIN, "name": "학원C원장", "email": "c@c.kr"},
              follow_redirects=False)

    admins = shop.keys.list_keys(kind=KIND_PRIMARY, program_id=PROGRAM,
                                 role=ROLE_ADMIN)
    assert [row.holder_name for row in admins] == ["학원A원장"], (
        "관리자가 관리자를 만들어 냈다")


def test_모듈에서도_관리자가_관리자키를_못_만든다(shop):
    from core.keyauth import KeyError_

    issuer = shop.keys.issue_set("학원", "a@a.kr", program_id=PROGRAM,
                                 role=ROLE_ADMIN)
    with pytest.raises(KeyError_, match="관리자키는 발급하실 수 없습니다"):
        shop.keys.issue_set("재판매", "x@x.kr", program_id=PROGRAM,
                            role=ROLE_ADMIN, issued_by=issuer.primary_id)


def test_고객은_주소를_쳐도_발급_못_한다(shop, boss):
    codes = shop.issue(boss, f"/c/{PROGRAM}/keys/issue",
                       name="수강생1", email="s1@academy.kr")
    student = shop.enter(codes)

    response = student.post(f"/c/{PROGRAM}/keys/issue",
                            data={"name": "재판매", "email": "x@x.kr"},
                            follow_redirects=False)
    assert "error=" in response.headers["location"]
    assert not [row for row in shop.keys.list_keys(kind=KIND_PRIMARY,
                                                   program_id=PROGRAM)
                if row.holder_name == "재판매"]


# ────────────────────────────────── 옆 학원 것은 보이지도 건드려지지도 않는다
@pytest.fixture
def two_academies(shop):
    """학원 둘. 각자 수강생 하나씩."""
    a = shop.enter(shop.sell("학원A원장", "a@academy.kr"))
    b = shop.enter(shop.sell("학원B원장", "b@academy.kr"))
    shop.issue(a, f"/c/{PROGRAM}/keys/issue", name="A수강생", email="a1@academy.kr")
    shop.issue(b, f"/c/{PROGRAM}/keys/issue", name="B수강생", email="b1@academy.kr")
    return a, b


def test_옆_학원_수강생은_목록에_없다(shop, two_academies):
    a, b = two_academies

    assert "B수강생" not in a.get(f"/c/{PROGRAM}/t/keys").text
    assert "A수강생" not in b.get(f"/c/{PROGRAM}/t/keys").text
    assert "학원B원장" not in a.get(f"/c/{PROGRAM}/t/keys").text, (
        "내가 판 키까지 보인다")


@pytest.mark.parametrize("action", ["toggle", "delete"])
def test_옆_학원_키는_주소를_쳐도_못_건드린다(shop, two_academies, action):
    """화면에서 안 그리는 것은 잠금이 아니다."""
    a, _b = two_academies
    target = shop.row("B수강생")

    response = a.post(f"/c/{PROGRAM}/keys/{target.id}/{action}",
                      follow_redirects=False)
    assert "error=" in response.headers["location"]

    survived = shop.keys.get(target.id)
    assert survived.status == "active", "옆 학원이 내 고객을 정지시켰다"


def test_학원장_초기화는_자기_고객만_지운다(shop, two_academies):
    a, b = two_academies

    a.post(f"/c/{PROGRAM}/keys/reset", data={"confirm": "초기화"},
           follow_redirects=False)

    names = [row.holder_name for row in
             shop.keys.list_keys(kind=KIND_PRIMARY, program_id=PROGRAM)]
    assert "A수강생" not in names, "자기 고객은 지워져야 한다"
    assert "B수강생" in names, "옆 학원 고객까지 지웠다"
    assert "학원A원장" in names, "자기 접속키까지 지웠다"
    assert a.get(f"/c/{PROGRAM}/t/home").status_code == 200, "자기가 못 들어간다"


def test_학원장_초기화도_글자를_정확히_쳐야_한다(shop, two_academies):
    a, _b = two_academies

    response = a.post(f"/c/{PROGRAM}/keys/reset", data={"confirm": "지워줘"},
                      follow_redirects=False)
    assert "error=" in response.headers["location"]
    assert "A수강생" in a.get(f"/c/{PROGRAM}/t/keys").text


# ─────────────────────────────────────────────── 내 화면에서는 다 보인다
def test_내_화면에는_판_것과_그_아래가_모두_보인다(shop, two_academies):
    body = shop.owner.get(f"/apps/{PROGRAM}/admin/t/keys").text

    for name in ("학원A원장", "학원B원장", "A수강생", "B수강생"):
        assert name in body, f"{name} 이 내 화면에 없다"
    assert "판매" in body and "고객용" in body, "무슨 키인지 갈라 보여야 한다"


def test_무엇이_판_키이고_무엇이_고객_키인지_센다(shop, two_academies):
    counts = shop.keys.counts(program_id=PROGRAM)

    assert counts["admins"] == 2, "판 것"
    assert counts["clients"] == 2, "산 사람들이 자기 고객에게 준 것"


def test_내가_직접_고객_키를_줄_수도_있다(shop):
    """한 사람에게 직접 파는 경우. 그 사람은 관리자가 아니다."""
    codes = shop.issue(shop.owner, f"/apps/{PROGRAM}/admin/keys/issue",
                       role=ROLE_CLIENT, name="혼자쓰는분", email="solo@example.com")
    solo = shop.enter(codes)

    assert "/t/keys" not in solo.get(f"/c/{PROGRAM}/t/home").text
    assert shop.row("혼자쓰는분").mine, "내가 준 키로 기록돼야 한다"


# ─────────────────────────────────────────────────── 예전 키도 살아 있다
def test_역할을_안_적고_만든_키는_고객_키로_본다(shop):
    """칸을 새로 더하기 전에 만든 키. 관리자로 승격되면 안 된다."""
    issued = shop.keys.issue_set("예전사람", "old@example.com", program_id=PROGRAM)

    assert shop.row("예전사람").role == ROLE_CLIENT
    assert issued.for_admin is False


# ───────────────────────────────────────── 쓰던 파일이 안 깨지는가
#
# 칸을 더할 때 순서를 틀려 **열려 있던 DB 가 통째로 안 열린** 적이 있다.
# `CREATE INDEX ... ON auth_keys(issued_by)` 가 칸을 더하기 전에 돌아
# '없는 칸에 인덱스' 라며 죽었다. 새 파일로만 시험하면 절대 안 보인다.

OLD_SCHEMA = """
CREATE TABLE auth_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL, code TEXT NOT NULL,
    parent_id INTEGER, device TEXT NOT NULL DEFAULT '',
    holder_name TEXT NOT NULL DEFAULT '', holder_email TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active', expires_at TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL DEFAULT '', UNIQUE (program_id, code));
CREATE TABLE auth_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, key_id INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE, issued_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
    revoked_at TEXT NOT NULL DEFAULT '', revoked_why TEXT NOT NULL DEFAULT '');
INSERT INTO auth_keys (program_id, kind, code, holder_name, created_at)
    VALUES ('exam-drill', 'primary', 'AAAA-BBBB-CCCC', '예전사람', '2026-01-01');
"""


@pytest.fixture
def old_db(tmp_path):
    """역할 칸이 없던 시절의 파일."""
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.commit()
    conn.close()
    return path


def test_예전_파일도_그대로_열린다(old_db):
    keys = KeyAuth(old_db)
    row = keys.find("AAAA-BBBB-CCCC", "exam-drill")

    assert row is not None, "쓰던 키가 사라졌다"
    assert row.holder_name == "예전사람"


def test_예전_키는_고객_키로_잡힌다(old_db):
    """역할을 모르는 키가 관리자로 승격되면, 산 적 없는 사람이 발급 자리를 얻는다."""
    row = KeyAuth(old_db).find("AAAA-BBBB-CCCC", "exam-drill")

    assert row.role == ROLE_CLIENT
    assert row.issued_by is None
    assert row.is_admin is False


def test_예전_파일에도_새로_발급된다(old_db):
    keys = KeyAuth(old_db)
    issued = keys.issue_set("새사람", "new@example.com", program_id="exam-drill",
                            role=ROLE_ADMIN)

    assert len(issued.secondary) == 3
    assert keys.find(issued.primary, "exam-drill").is_admin
