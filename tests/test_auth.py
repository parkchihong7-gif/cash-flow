"""대시보드 접속 코드 잠금 테스트.

대시보드를 인터넷에 열어 두면 주소만 알면 누구나 들어온다.
이 화면에는 고객 이름·연락처·주소가 있으므로, 잠금이 새는 것은
단순한 불편이 아니라 개인정보 사고가 된다. 그래서 다음을 확인한다.

    - 코드 없이 열리는 화면이 정말 로그인·정적 파일뿐인가
    - 쿠키를 고쳐 만들어도 통과하지 못하는가
    - 접속 코드가 쿠키에 담기지 않는가
    - 여러 번 틀리면 잠기는가
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from core import auth
from dashboard.app import create_app, safe_next


@pytest.fixture
def guest(tmp_path):
    """로그인하지 않은 방문자."""
    return TestClient(create_app(tmp_path / "auth.db"), follow_redirects=False)


@pytest.fixture
def member(tmp_path):
    """코드를 넣고 들어온 사람."""
    client = TestClient(create_app(tmp_path / "auth2.db"), follow_redirects=False)
    client.post("/login", data={"code": auth.access_code()})
    return client


# ------------------------------------------------------------------ 접속 코드
def test_default_code_is_the_one_we_documented():
    assert auth.DEFAULT_ACCESS_CODE == "redwind7"
    assert auth.access_code() == "redwind7"


def test_code_can_be_changed_by_environment(monkeypatch):
    monkeypatch.setenv("DASHBOARD_ACCESS_CODE", "다른코드")
    assert auth.access_code() == "다른코드"
    assert auth.check_code("다른코드")
    assert not auth.check_code("redwind7")
    assert not auth.is_default_code()


def test_code_comparison_handles_non_ascii(monkeypatch):
    """한글 코드로 바꾸면 로그인 화면이 통째로 깨지던 문제를 막는다.

    `hmac.compare_digest` 는 ASCII 가 아닌 글자열을 받으면 TypeError 를 낸다.
    """
    monkeypatch.setenv("DASHBOARD_ACCESS_CODE", "붉은바람7")
    assert auth.check_code("붉은바람7") is True
    assert auth.check_code("redwind7") is False


def test_code_ignores_surrounding_spaces():
    """휴대폰에서 붙여넣으면 뒤에 공백이 딸려 오는 일이 흔하다."""
    assert auth.check_code("  redwind7  ")


def test_empty_code_is_rejected():
    assert not auth.check_code("")
    assert not auth.check_code(None)


# --------------------------------------------------------------------- 쿠키
def test_token_round_trip():
    assert auth.verify_token(auth.issue_token())


def test_expired_token_is_rejected():
    assert not auth.verify_token(auth.issue_token(now=time.time() - 30 * 86400))


def test_tampered_expiry_is_rejected():
    """만료 시각만 미래로 고쳐 넣어도 서명이 맞지 않아 걸린다."""
    token = auth.issue_token()
    _, _, signature = token.rpartition(".")
    forged = f"{int(time.time()) + 999999}.{signature}"
    assert not auth.verify_token(forged)


def test_garbage_tokens_are_rejected():
    for junk in ("", None, "aaa", "abc.def", ".", "1789.", "1789"):
        assert not auth.verify_token(junk), junk


def test_token_does_not_contain_the_code():
    assert auth.access_code() not in auth.issue_token()


# ------------------------------------------------------------------ 화면 보호
@pytest.mark.parametrize("path", [
    "/", "/members", "/settings", "/manual", "/manual/admin",
    "/programs/n8n-gen", "/programs/n8n-gen/edit", "/programs/n8n-gen/test",
    "/programs/n8n-gen/members", "/runs/1", "/preview?path=/etc/passwd",
])
def test_pages_need_the_code(guest, path):
    response = guest.get(path)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


@pytest.mark.parametrize("path", ["/reload", "/members", "/settings"])
def test_posting_without_the_code_is_blocked(guest, path):
    """화면만 막고 쓰기 요청을 열어 두면 막은 뜻이 없다."""
    assert guest.post(path, data={}).status_code == 303


@pytest.mark.parametrize("path", ["/login", "/healthz", "/static/style.css"])
def test_only_these_are_open(guest, path):
    assert guest.get(path).status_code == 200


def test_healthz_says_nothing_about_the_inside(guest):
    """호스팅이 살아 있는지 확인하는 주소. 내용이 새면 안 된다."""
    body = guest.get("/healthz").text
    assert body.strip() == "ok"
    assert "대시보드" not in body


# ------------------------------------------------------------------ 로그인
def test_wrong_code_is_rejected_and_counted(guest):
    response = guest.post("/login", data={"code": "아무거나"})
    assert response.status_code == 401
    assert "맞지 않습니다" in response.text
    assert "남은 시도" in response.text
    assert auth.COOKIE_NAME not in response.cookies


def test_right_code_opens_the_door(guest):
    response = guest.post("/login", data={"code": auth.access_code()})
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert guest.get("/").status_code == 200


def test_cookie_is_locked_down(guest):
    header = guest.post("/login", data={"code": auth.access_code()}).headers["set-cookie"]
    assert "HttpOnly" in header, "자바스크립트가 쿠키를 읽을 수 있으면 안 됩니다"
    assert "samesite=lax" in header.lower()
    assert auth.access_code() not in header, "접속 코드가 쿠키에 담기면 안 됩니다"


def test_login_page_does_not_show_the_code(guest):
    assert auth.access_code() not in guest.get("/login").text


def test_returns_to_the_page_you_wanted(guest):
    response = guest.get("/programs/n8n-gen/test")
    assert "next=" in response.headers["location"]

    response = guest.post("/login", data={"code": auth.access_code(),
                                          "next": "/programs/n8n-gen/test"})
    assert response.headers["location"] == "/programs/n8n-gen/test"


def test_query_string_survives_the_detour(guest):
    """산출물 화면은 `?run=3` 이 없으면 열리지 않는다."""
    location = guest.get("/programs/n8n-gen/outputs?run=3").headers["location"]
    assert "run%3D3" in location


@pytest.mark.parametrize("target", [
    "https://evil.example.com/x", "//evil.example.com", "http://evil.example.com",
])
def test_cannot_be_bounced_to_another_site(guest, target):
    """로그인 직후 남의 사이트로 튕겨 보내는 수법을 막는다."""
    response = guest.post("/login", data={"code": auth.access_code(), "next": target})
    assert response.headers["location"] == "/"


def test_safe_next_keeps_our_own_paths():
    assert safe_next("/members") == "/members"
    assert safe_next("/programs/x?tab=1") == "/programs/x?tab=1"
    assert safe_next("") == "/"


def test_logout_closes_the_door(member):
    assert member.get("/").status_code == 200
    assert member.post("/logout").status_code == 303
    assert member.get("/").status_code == 303


def test_already_logged_in_skips_the_form(member):
    response = member.get("/login")
    assert response.status_code == 303
    assert response.headers["location"] == "/"


# ------------------------------------------------------------- 무차별 대입 차단
def test_lockout_after_repeated_failures(guest):
    for _ in range(auth.MAX_ATTEMPTS):
        guest.post("/login", data={"code": "틀린코드"})

    response = guest.post("/login", data={"code": auth.access_code()})
    assert response.status_code == 429, "잠긴 동안은 맞는 코드도 받지 않아야 합니다"
    assert "잠겼습니다" in response.text
    assert guest.get("/").status_code == 303


def test_lockout_counts_down_and_clears():
    gate = auth.Gatekeeper(max_attempts=3, lockout_seconds=60)
    now = 1000.0
    for _ in range(3):
        gate.record_failure("1.2.3.4", now=now)
    assert gate.locked_for("1.2.3.4", now=now) == 60
    assert gate.locked_for("1.2.3.4", now=now + 61) == 0


def test_lockout_is_per_address():
    gate = auth.Gatekeeper(max_attempts=2, lockout_seconds=60)
    gate.record_failure("1.1.1.1")
    gate.record_failure("1.1.1.1")
    assert gate.locked_for("1.1.1.1") > 0
    assert gate.locked_for("2.2.2.2") == 0


def test_success_clears_the_count():
    gate = auth.Gatekeeper(max_attempts=3, lockout_seconds=60)
    gate.record_failure("1.1.1.1")
    gate.record_failure("1.1.1.1")
    gate.reset("1.1.1.1")
    assert gate.record_failure("1.1.1.1") == 2, "세다 말고 처음부터 다시 세야 합니다"


def test_old_failures_do_not_pile_up_forever():
    """어제 한 번 틀린 것이 오늘 잠금에 더해지면 안 된다."""
    gate = auth.Gatekeeper(max_attempts=3, lockout_seconds=60)
    gate.record_failure("1.1.1.1", now=1000)
    assert gate.record_failure("1.1.1.1", now=1000 + 500) == 2


def test_proxy_header_identifies_the_real_visitor(tmp_path):
    """터널이나 클라우드 뒤에 두면 모두가 프록시 주소로 보인다.

    그러면 누가 한 번 틀렸을 때 전부가 같이 잠긴다.
    """
    client = TestClient(create_app(tmp_path / "p.db"), follow_redirects=False)
    for _ in range(auth.MAX_ATTEMPTS):
        client.post("/login", data={"code": "틀림"},
                    headers={"x-forwarded-for": "10.0.0.1, 172.16.0.1"})

    blocked = client.post("/login", data={"code": auth.access_code()},
                          headers={"x-forwarded-for": "10.0.0.1"})
    assert blocked.status_code == 429

    other = client.post("/login", data={"code": auth.access_code()},
                        headers={"x-forwarded-for": "10.0.0.9"})
    assert other.status_code == 303, "다른 사람까지 같이 잠기면 안 됩니다"


# --------------------------------------------------------------------- 안내
def test_dashboard_warns_while_the_default_code_is_in_use(tmp_path):
    client = TestClient(create_app(tmp_path / "d.db"))
    client.post("/login", data={"code": auth.access_code()})
    assert "기본값 그대로" in client.get("/").text


def test_warning_disappears_once_the_code_is_changed(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_ACCESS_CODE", "바꾼코드")
    client = TestClient(create_app(tmp_path / "w.db"))
    client.post("/login", data={"code": "바꾼코드"})
    assert "기본값 그대로" not in client.get("/").text


def test_secret_file_is_not_committed():
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", ".dashboard_secret"],
        capture_output=True, text=True, cwd=str(auth.SECRET_PATH.parent),
    ).stdout.strip()
    assert tracked == "", ".dashboard_secret 이 저장소에 들어갔습니다"
