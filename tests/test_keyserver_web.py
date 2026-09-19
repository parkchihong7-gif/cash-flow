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


def test_대시보드_접속키_화면이_어느_장부인지_말한다(tmp_path):
    """장부가 둘(이 컴퓨터 / 구글 시트)이라, 섞어 쓰면 고객이 못 들어온다.

    여기서 만든 키는 이 컴퓨터가 켜져 있을 때만 먹는다는 것을 화면이
    먼저 말해 주어야 한다.
    """
    from fastapi.testclient import TestClient
    from core import auth
    from dashboard.app import create_app

    client = TestClient(create_app(tmp_path / "app.db"))
    client.post("/login", data={"code": auth.access_code()})
    page = client.get("/keys").text

    assert "이 컴퓨터의 장부입니다" in page
    assert "섞어 발급하지 마세요" in page
    assert "server/README.md" in page
