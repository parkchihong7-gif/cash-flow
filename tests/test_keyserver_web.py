"""무료 키 서버(구글 앱스 스크립트)와 관리자 화면 시험.

왜 파이썬 시험 안에 있나
    서버는 자바스크립트(`server/keyserver.gs`)이고 화면도 자바스크립트다.
    따로 돌리면 `pytest` 만 돌리고 다 됐다고 여기게 된다. 한 번에 걸리게
    여기서 같이 부른다.

무엇이 없으면 건너뛰나
    노드가 없으면 서버 시험을, 크로미움이 없으면 화면 시험을 건너뛴다.
    없다고 실패로 만들면 사장님 컴퓨터에서 늘 빨간불이 뜬다.
"""

from __future__ import annotations

import json
import re
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = ROOT / "server"
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

node = pytest.mark.skipif(shutil.which("node") is None, reason="노드가 없습니다")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@node
def test_키서버_규약_시험이_전부_통과한다():
    """`server/tests/` 의 시험을 그대로 돌린다.

    올릴 파일(`keyserver.gs`) 자체를 돌리는 시험이라, 여기가 초록불이면
    구글에 붙였을 때도 같은 규약으로 움직인다.
    """
    done = subprocess.run(
        ["node", "--test", "server/tests/keyserver.test.js"],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    assert done.returncode == 0, f"키 서버 시험이 깨졌습니다:\n{done.stdout[-3000:]}"
    assert "# fail 0" in done.stdout, done.stdout[-2000:]


@node
def test_설정값을_안_넣으면_아무도_못_들어온다(tmp_path):
    """비밀번호를 안 정해 둔 채 배포해도 목록이 새지 않아야 한다."""
    script = tmp_path / "check.js"
    script.write_text(
        "const {makeServer} = require(%r);\n"
        "const srv = makeServer({});\n"
        "const out = srv.call({action:'adminList'});\n"
        "if (out.ok) { console.error('열렸습니다'); process.exit(1); }\n"
        "if (out.rows) { console.error('목록이 딸려 나왔습니다'); process.exit(1); }\n"
        "console.log('막힘');\n" % str(SERVER_DIR / "tests" / "harness.js"),
        encoding="utf-8",
    )
    done = subprocess.run(["node", str(script)],
                          cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-1500:]


@pytest.fixture
def 시험서버():
    """가짜 키 서버 + `web/` 을 한 주소에서 내어 준다."""
    if shutil.which("node") is None:
        pytest.skip("노드가 없습니다")
    port = free_port()
    proc = subprocess.Popen(
        ["node", "server/tests/serve.js", str(port)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env=dict(os.environ, TEST_PW="주인비밀번호7"),
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(base + "/admin.html", timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("시험 서버가 안 떴습니다")
    try:
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def 부르기(base: str, payload: dict) -> dict:
    req = urllib.request.Request(
        base + "/exec", data=json.dumps(payload).encode(),
        headers={"Content-Type": "text/plain"},
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode())


def test_관리자_화면이_실려_나온다(시험서버):
    """화면이 프로그램 목록과 같은 파일을 부르고 있는지 본다."""
    with urllib.request.urlopen(시험서버 + "/admin.html", timeout=10) as res:
        page = res.read().decode()
    assert 'src="programs.js"' in page
    with urllib.request.urlopen(시험서버 + "/programs.js", timeout=10) as res:
        progs = res.read().decode()
    assert "window.PROGRAMS" in progs
    # 등록부에 있는 16종이 화면의 고르는 칸에 다 들어가 있어야 한다.
    from core.registry import Registry
    for program in Registry().programs:
        assert f'"{program.id}"' in progs, f"{program.id} 가 목록에 없습니다"


def test_화면_없이도_규약이_돈다(시험서버):
    """브라우저가 없어도 서버 쪽은 여기서 끝까지 확인된다."""
    로그인 = 부르기(시험서버, {"action": "adminLogin", "password": "주인비밀번호7"})
    assert 로그인["ok"], 로그인
    표 = 로그인["token"]

    한벌 = 부르기(시험서버, {"action": "adminCreateInvite", "token": 표,
                            "program": "agency-kit", "name": "김학원장",
                            "email": "kim@example.com", "role": "admin"})
    assert 한벌["ok"], 한벌
    assert sorted(한벌["secondaryKeys"]) == sorted(["PC", "노트북", "휴대폰"])

    열림 = 부르기(시험서버, {"action": "validateKeyPair", "program": "agency-kit",
                            "key1": 한벌["primaryKey"], "key2": 한벌["secondaryKeys"]["PC"]})
    assert 열림["ok"], 열림

    # 다른 프로그램 문으로는 같은 키가 안 들어가야 한다.
    넘본다 = 부르기(시험서버, {"action": "validateKeyPair", "program": "funnel-builder",
                              "key1": 한벌["primaryKey"], "key2": 한벌["secondaryKeys"]["PC"]})
    assert not 넘본다["ok"]


@pytest.mark.skipif(not Path(CHROMIUM).exists(), reason="크로미움이 없습니다")
def test_관리자_화면을_눌러서_끝까지_돈다(시험서버):
    """진짜 브라우저로 로그인 → 발급 → 목록 → 정지 → 초기화까지 눌러 본다."""
    playwright = pytest.importorskip("playwright.sync_api")

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page()
        오류: list[str] = []
        page.on("pageerror", lambda e: 오류.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        try:
            page.goto(f"{시험서버}/admin.html", wait_until="domcontentloaded")
            # 처음에는 주소 칸만 보인다.
            assert page.is_hidden("#main")

            page.evaluate(f"localStorage.setItem('keyserver.url', '{시험서버}/exec')")
            page.reload(wait_until="domcontentloaded")

            page.fill("#pw", "틀린것")
            page.click("#loginBtn")
            page.wait_for_timeout(900)
            assert page.is_hidden("#main"), "틀린 비밀번호로 들어가졌습니다"

            page.fill("#pw", "주인비밀번호7")
            page.click("#loginBtn")
            page.wait_for_selector("#main:not(.hide)", timeout=10000)

            page.select_option("#program", "agency-kit")
            page.fill("#name", "김학원장")
            page.fill("#email", "kim@example.com")
            page.click("#issueBtn")
            page.wait_for_selector("#issued:not(.hide)", timeout=10000)
            발급됨 = page.inner_text("#issued")
            assert "1차키" in 발급됨 and "휴대폰" in 발급됨, 발급됨

            page.wait_for_timeout(700)
            assert page.eval_on_selector_all("#list tbody tr", "e => e.length") == 4

            # 다른 프로그램으로 옮기면 비어 있어야 한다 — 섞이면 큰일이다.
            page.select_option("#program", "funnel-builder")
            page.wait_for_timeout(900)
            assert "아직 발급한 키가 없습니다" in page.inner_text("#list")

            page.select_option("#program", "agency-kit")
            page.wait_for_timeout(900)
            page.fill("#confirm", "아무거나")
            page.click("#resetBtn")
            page.wait_for_timeout(700)
            assert page.eval_on_selector_all("#list tbody tr", "e => e.length") == 4, \
                "'초기화' 라고 안 적었는데 지워졌습니다"

            page.fill("#confirm", "초기화")
            page.click("#resetBtn")
            page.wait_for_timeout(1400)
            assert "아직 발급한 키가 없습니다" in page.inner_text("#list")

            assert not 오류, f"화면에서 오류가 났습니다: {오류}"
        finally:
            browser.close()


def test_접속키_화면이_어디에_남는지_말한다(tmp_path, monkeypatch):
    """이것을 안 말해 주면 "어제 산 키가 안 먹는다" 가 되고,
    사장님은 어디를 봐야 할지도 모르게 된다."""
    monkeypatch.delenv("KEYSERVER_URL", raising=False)
    monkeypatch.delenv("KEYSERVER_PASSWORD", raising=False)
    page = 대시보드(tmp_path, monkeypatch).get("/keys").text
    assert "이 컴퓨터의 장부입니다" in page
    assert "켜져 있을 때만" in page
    assert "KEYSERVER_URL" in page, "어떻게 고치라는 말이 없습니다"
    assert "키 서버에 이어져 있습니다" not in page


def test_키서버가_붙으면_화면이_그렇게_말한다(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYSERVER_URL", "https://example.test/exec")
    monkeypatch.setenv("KEYSERVER_PASSWORD", "x")
    from fastapi.testclient import TestClient
    from core import auth
    from dashboard.app import create_app

    client = TestClient(create_app(tmp_path / "app.db"))
    client.post("/login", data={"code": auth.access_code()})
    page = client.get("/keys").text
    assert "키 서버에 이어져 있습니다" in page
    assert "구글 시트에 먼저 올라가고" in page
    assert "이 컴퓨터의 장부입니다" not in page
    # 비밀번호나 주소가 화면에 찍히면 안 된다.
    assert "example.test" not in page


# ── 대시보드 → 키 서버 잇기 ─────────────────────────────────────────
#
# 사장님은 대시보드 한 곳에서만 발급하신다. 만든 키는 구글 시트에 함께
# 올라가고, 고객은 집 컴퓨터가 꺼져 있어도 그 시트에 물어 들어온다.

def 대시보드(tmp_path, monkeypatch, 서버주소=None, 비밀번호="주인비밀번호7"):
    """접속 코드까지 넣은 대시보드 클라이언트를 만든다."""
    from fastapi.testclient import TestClient
    from core import auth
    from dashboard.app import create_app

    if 서버주소:
        monkeypatch.setenv("KEYSERVER_URL", 서버주소 + "/exec")
        monkeypatch.setenv("KEYSERVER_PASSWORD", 비밀번호)
    else:
        monkeypatch.delenv("KEYSERVER_URL", raising=False)
        monkeypatch.delenv("KEYSERVER_PASSWORD", raising=False)

    client = TestClient(create_app(tmp_path / "app.db"))
    client.post("/login", data={"code": auth.access_code()})
    return client


def 발급하기(client, program="agency-kit", **extra):
    data = {"name": "김학원장", "email": "kim@example.com",
            "role": "admin", "expires_days": ""}
    data.update(extra)
    return client.post(f"/apps/{program}/admin/keys/issue", data=data,
                       follow_redirects=False)


def test_키서버를_안_쓰면_지금까지처럼_이_컴퓨터에만_적는다(tmp_path, monkeypatch):
    from core.keyauth import KeyAuth

    client = 대시보드(tmp_path, monkeypatch)
    답 = 발급하기(client)
    assert 답.status_code == 303
    assert "error" not in 답.headers["location"], 답.headers["location"]
    assert len(KeyAuth(tmp_path / "app.db").list_keys(program_id="agency-kit")) == 4


def test_키서버를_쓰면_시트와_대시보드에_같은_코드가_남는다(tmp_path, monkeypatch, 시험서버):
    """코드가 다르면 고객이 받은 키로 문이 안 열린다. 같아야 한다."""
    from core.keyauth import KeyAuth

    client = 대시보드(tmp_path, monkeypatch, 시험서버)
    답 = 발급하기(client)
    assert 답.status_code == 303
    assert "error" not in 답.headers["location"], 답.headers["location"]

    이쪽 = KeyAuth(tmp_path / "app.db").list_keys(program_id="agency-kit")
    로그인 = 부르기(시험서버, {"action": "adminLogin", "password": "주인비밀번호7"})
    저쪽 = 부르기(시험서버, {"action": "adminList", "token": 로그인["token"],
                            "program": "agency-kit"})["rows"]

    assert len(이쪽) == 4 and len(저쪽) == 4
    assert {row.code for row in 이쪽} == {row["key"] for row in 저쪽}, \
        "대시보드와 시트에 적힌 키가 다릅니다 — 고객이 못 들어옵니다"


def test_시트에_넣은_키로_고객이_실제로_들어온다(tmp_path, monkeypatch, 시험서버):
    """집 컴퓨터를 꺼도 되는지가 여기서 갈린다."""
    from core.keyauth import KeyAuth

    client = 대시보드(tmp_path, monkeypatch, 시험서버)
    발급하기(client)
    rows = KeyAuth(tmp_path / "app.db").list_keys(program_id="agency-kit")
    일차 = next(r.code for r in rows if r.kind == "primary")
    이차 = next(r.code for r in rows if r.kind == "secondary")

    열림 = 부르기(시험서버, {"action": "validateKeyPair", "program": "agency-kit",
                            "key1": 일차, "key2": 이차})
    assert 열림["ok"], 열림
    assert 열림["sessionToken"]


def test_시트에_못_넣으면_이_컴퓨터에도_안_적는다(tmp_path, monkeypatch):
    """순서가 거꾸로면 시트에 없는 키를 고객에게 보내게 된다.

    고객은 그 자리에서 '키가 틀렸다' 는 말을 듣고, 사장님 목록에는 멀쩡히
    있어서 무엇이 잘못됐는지 알 수가 없다.
    """
    from core.keyauth import KeyAuth

    # 아무도 없는 주소를 키 서버로 준다.
    죽은주소 = f"http://127.0.0.1:{free_port()}"
    client = 대시보드(tmp_path, monkeypatch, 죽은주소)
    답 = 발급하기(client)

    assert 답.status_code == 303
    assert "error" in 답.headers["location"], "실패했는데 성공처럼 돌아갔습니다"
    assert not KeyAuth(tmp_path / "app.db").list_keys(program_id="agency-kit"), \
        "시트에 못 넣었는데 이 컴퓨터에는 적혔습니다"


def test_키서버_비밀번호가_틀리면_아무것도_안_만든다(tmp_path, monkeypatch, 시험서버):
    from core.keyauth import KeyAuth

    client = 대시보드(tmp_path, monkeypatch, 시험서버, 비밀번호="틀린것")
    답 = 발급하기(client)
    assert "error" in 답.headers["location"]
    assert not KeyAuth(tmp_path / "app.db").list_keys(program_id="agency-kit")
    로그인 = 부르기(시험서버, {"action": "adminLogin", "password": "주인비밀번호7"})
    assert not 부르기(시험서버, {"action": "adminList", "token": 로그인["token"],
                                "program": "agency-kit"})["rows"]


# ── 붙여 넣을 한 장 ─────────────────────────────────────────────────

def test_묶음_파일이_최신이다():
    """서버나 화면만 고치고 묶는 것을 잊으면, 구글에는 옛 판이 올라간다.

    화면은 멀쩡히 뜨는데 방금 고친 것이 안 들어 있어, 무엇이 잘못됐는지
    알기가 가장 어려운 꼴이 된다. 여기서 막는다.
    """
    from tools.build_keyserver import OUT, build

    assert OUT.exists(), "server/keyserver.bundle.gs 가 없습니다"
    지금것 = OUT.read_text(encoding="utf-8")
    다시만든것 = build()
    assert 지금것 == 다시만든것, (
        "묶음 파일이 낡았습니다. `python -m tools.build_keyserver` 를 돌리고 "
        "다시 커밋해 주세요."
    )


def test_묶음_파일에_비밀이_없다():
    """공개 저장소에 올라가는 파일이다."""
    from tools.build_keyserver import OUT

    글 = OUT.read_text(encoding="utf-8")
    assert "redwind7" not in 글
    assert "주인비밀번호" not in 글
    assert not re.search(r"AKfyc[A-Za-z0-9_-]{20,}", 글), "키 서버 주소가 박혀 있습니다"
    assert not re.search(r"ADMIN_PASSWORD['\"]?\s*[:=]\s*['\"][^'\"]+", 글)


def test_묶음_파일_하나만_붙이면_되게_들어_있다():
    """두 파일을 각각 붙이게 하면 그것부터가 숙제다."""
    from tools.build_keyserver import OUT

    글 = OUT.read_text(encoding="utf-8")
    assert "var ADMIN_HTML" in 글, "관리자 화면이 안 들어 있습니다"
    assert 'src="programs.js"' not in 글, "옆 파일을 부르고 있습니다"
    assert "window.PROGRAMS" in 글, "프로그램 목록이 안 들어 있습니다"
    assert "function 처음설정" in 글
    # 등록부의 16종이 다 들어 있어야 고르는 칸에서 보인다.
    from core.registry import Registry
    for program in Registry().programs:
        assert f'"{program.id}"' in 글, f"{program.id} 가 빠졌습니다"


def test_묶음_파일이_잘렸는지_눈으로_알_수_있다():
    """잘린 파일은 문법이 깨져 "Unexpected end of input" 만 나온다.

    그 말만으로는 무엇을 하라는 건지 알 수가 없다. 실제로 사장님이
    150번째 줄에서 잘린 채 붙여 넣으시고 그 오류를 받으셨다.
    맨 아래에 표를 두어, 그 표가 보이는지로 판단하실 수 있게 한다.
    """
    from tools.build_keyserver import OUT, TAIL_MARK

    글 = OUT.read_text(encoding="utf-8")
    줄 = 글.splitlines()
    assert 줄[-1] == TAIL_MARK, "맨 끝 표가 없습니다"
    assert "⛳" in TAIL_MARK

    # 머리말이 말하는 줄 수가 실제와 같아야, 세어 보고 확인하실 수 있다.
    머리 = re.search(r"이 파일은 ([\d,]+)줄입니다", 글)
    assert 머리, "머리말에 줄 수가 없습니다"
    assert int(머리.group(1).replace(",", "")) == len(줄), (
        f"머리말은 {머리.group(1)}줄이라는데 실제는 {len(줄)}줄입니다"
    )

    # 무엇 때문에 잘리는지, 어떻게 하라는지가 파일 안에 있어야 한다.
    assert "Unexpected end of input" in 글, "그 오류가 무슨 뜻인지 안 적혀 있습니다"
    assert "Raw" in 글, "제대로 복사하는 법이 안 적혀 있습니다"


def test_묶음_파일이_붙여_넣을_만큼_작다():
    """붙여 넣을 양이 적을수록 잘릴 일도 적다."""
    from tools.build_keyserver import OUT

    글 = OUT.read_text(encoding="utf-8")
    assert len(글.encode()) < 55_000, f"{len(글.encode()):,}바이트나 됩니다"
    # 읽기 좋은 원본은 그대로 둔다 — 줄인 것은 만들어지는 판뿐이다.
    원본 = (Path(__file__).resolve().parent.parent / "server" / "keyserver.gs")
    assert "왜 이것인가" in 원본.read_text(encoding="utf-8"), "원본의 설명이 사라졌습니다"
