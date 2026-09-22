"""접속키 안내문 — 고치고, 매뉴얼 붙이고, 바로 보낸다.

예전에는 서버가 만든 글을 **읽기 전용**으로 보여 주고 [전체 복사] /
[메일 앱으로 열기] 만 있었다. 고객마다 덧붙일 말이 다른데 한 글자도 못
고쳤고, 메일 앱이 안 열리는 환경도 있었다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core import auth
from core.keyauth import IssuedSet
from core.registry import Registry
from dashboard.app import app
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    c = TestClient(app)
    c.cookies.set(auth.COOKIE_NAME, auth.issue_token())
    return c


def _issue(client, role="admin"):
    return client.post("/apps/naver-blog/admin/keys/issue",
                       data={"name": "박치홍", "email": "a@b.example",
                             "role": role, "expires_days": ""},
                       follow_redirects=True)


def test_the_notice_can_be_edited(client):
    """완성품이 아니라 **출발점**이다. 읽기 전용이면 안 된다."""
    body = _issue(client).text
    칸 = re.search(r'<textarea id="issued-text"[^>]*>', body)
    assert 칸, "안내문 칸이 없습니다"
    assert "readonly" not in 칸.group(0), "고칠 수 있어야 한다"
    assert 'name="body"' in 칸.group(0), "고친 그대로 보내져야 한다"


def test_old_buttons_are_gone_and_send_is_there(client):
    """못 보낼 때도 **버튼은 보인다.**

    아예 없으면 «어떻게 보내지» 가 되고, 무엇을 준비하면 되는지도 모른다.
    흐리게 두고 이유를 적는다.
    """
    body = _issue(client).text
    assert "전체 복사" not in body
    assert "메일 앱으로 열기" not in body
    assert ">발송</button>" in body


def test_the_notice_keeps_the_shape_we_agreed():
    """사장님이 적어 주신 형식을 지킨다. 바꾸면 고객이 받는 글이 달라진다."""
    s = IssuedSet(holder_name="박치홍", holder_email="a@b.example",
                  primary="J85K-6KE8-W8UB",
                  secondary={"PC": "AAAA-BBBB-CCCC",
                             "노트북": "DDDD-EEEE-FFFF",
                             "휴대폰": "GGGG-HHHH-IIII"},
                  service_url="https://example.test/c/naver-blog", role="admin")
    글 = s.mail_body("네이버 블로그 초안 생성기")
    assert s.mail_subject("네이버 블로그 초안 생성기") == "[네이버 블로그 초안 생성기] 접속 안내"
    assert 글.startswith("박치홍님, 아래 링크로 접속하시면 1차, 2차 인증 후 이용 가능합니다.")
    assert "관리자 화면이 열리며" in 글, "관리자에게는 이 한 줄이 더 붙는다"
    assert "* 1차 인증키 : J85K-6KE8-W8UB" in 글
    assert "* 2차 인증키" in 글
    assert "- PC : AAAA-BBBB-CCCC" in 글
    assert "- 노트북 : DDDD-EEEE-FFFF" in 글
    assert "- 휴대폰 : GGGG-HHHH-IIII" in 글


def test_a_client_notice_drops_the_admin_line():
    """고객에게 «관리자 화면이 열립니다» 를 보내면 안 된다. 안 열린다."""
    s = IssuedSet(holder_name="김고객", holder_email="a@b.example",
                  primary="X", secondary={"PC": "Y"},
                  service_url="https://example.test/", role="client")
    assert "관리자 화면이 열리며" not in s.mail_body("아무거나")


@pytest.mark.parametrize("role,와야할것,오면안될것", [
    ("admin", "관리자 매뉴얼", "사용 설명서"),
    ("client", "사용 설명서", "관리자 매뉴얼"),
])
def test_the_right_manual_is_attached(client, role, 와야할것, 오면안될것):
    """받는 분이 관리자냐 고객이냐에 따라 다른 매뉴얼이 와야 한다.

    고객에게 관리자 매뉴얼을 보내면 «접속 코드 관리» 처럼 그분 화면에
    없는 것을 찾게 된다.
    """
    body = _issue(client, role=role).text
    assert 와야할것 in body
    assert 오면안될것 not in body


@pytest.mark.parametrize("role", ["admin", "client"])
def test_the_edit_box_holds_only_the_keys(client, role):
    """**고치는 곳과 자동인 곳을 가른다.**

    편집 칸에는 접속키 안내 글만 있다. 매뉴얼까지 한 칸에 섞어 놓았더니
    `────────` 같은 영문 모를 줄이 보이고 지저분했다. 게다가 보내는 사람이
    매뉴얼을 고칠 수 있으면 받는 분마다 내용이 달라져, 나중에 «매뉴얼에
    이렇게 쓰여 있었다» 를 확인할 길이 없다.
    """
    body = _issue(client, role=role).text
    칸 = re.search(r'<textarea id="issued-text"[^>]*>(.*?)</textarea>', body, re.S)
    글 = 칸.group(1)

    assert "1차 인증키" in 글, "접속키는 칸 안에 있어야 고칠 수 있습니다"
    assert "관리자 매뉴얼" not in 글 and "사용 설명서" not in 글
    assert "─" not in 글, "영문 모를 줄이 다시 들어왔습니다"
    # 매뉴얼은 칸 **밖**에 미리 보기로 있다.
    assert "mailpreview" in body


def test_the_manual_does_not_swallow_the_mail():
    """매뉴얼이 통째로 들어가면 키를 보러 연 사람이 5천 자를 스크롤한다."""
    from core.keyauth import MANUAL_IN_MAIL, manual_for_mail

    program = Registry().require("naver-blog")
    for 관리자 in (True, False):
        글 = manual_for_mail(program, 관리자)
        assert 글, "매뉴얼이 비었습니다"
        assert len(글) <= MANUAL_IN_MAIL + 60, "너무 깁니다"
        # 메일은 글자 그대로 보이는 곳이다. 마크다운 기호가 찍히면 안 된다.
        assert "**" not in 글
        assert not any(줄.startswith("#") for 줄 in 글.split("\n"))


def test_keys_stay_visible_after_sending(client):
    """보낸 뒤에도 키가 보여야 한다.

    메일이 안 갔을 수도 있고, 카톡으로도 보내실 수 있다. 꺼내는 순간
    지워 버리면 이 화면이 닫히고 키를 다시 볼 수 없다.
    """
    r = _issue(client)
    쪽지 = re.search(r'keys/send\?issued=([\w-]+)', r.text)
    assert 쪽지, "발송 주소에 쪽지가 실려 있어야 한다"

    다시 = client.get(f"/apps/naver-blog/admin/t/keys?issued={쪽지.group(1)}")
    assert "issued-text" in 다시.text, "다시 열어도 안내문이 보여야 한다"


def test_it_says_so_when_mail_is_not_wired(client, monkeypatch):
    """보낼 길이 없으면 **누르기 전에** 말해야 한다."""
    monkeypatch.delenv("KEYSERVER_URL", raising=False)
    monkeypatch.delenv("KEYSERVER_PASSWORD", raising=False)
    body = _issue(client).text
    assert "지금은 발송이 안 됩니다" in body
    assert "KEYSERVER_URL" in body


def test_sending_without_a_server_does_not_crash(client, monkeypatch):
    monkeypatch.delenv("KEYSERVER_URL", raising=False)
    r = client.post("/apps/naver-blog/admin/keys/send",
                    data={"email": "a@b.example", "subject": "x", "body": "y"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "메일 서버가 연결되지 않았습니다" in r.text


def test_a_reseller_cannot_send_with_our_account(client, monkeypatch):
    """**산 분은 우리 계정으로 메일을 못 보낸다.**

    열어 주면 사장님 구글 계정이 남의 발송기가 된다. 화면에서 버튼을
    감추는 것으로 끝내면 안 된다 — 주소를 직접 쳐도 막혀야 한다.
    앱스 스크립트 쪽(`adminSendText`)이 `scope !== 'owner'` 를 거절하고,
    우리 쪽은 애초에 그 길을 문(`/c/`)에 내지 않는다.
    """
    from dashboard.clientdoor import DOOR_PREFIX

    routes = [r.path for r in client.app.routes]
    문에난길 = [p for p in routes if p.startswith(DOOR_PREFIX) and p.endswith("/send")]
    assert not 문에난길, f"문에 발송 길이 있습니다: {문에난길}"


def test_the_gs_refuses_a_reseller():
    """앱스 스크립트가 주인만 보내게 하는지. 화면과 별개로 서버가 막는다."""
    글 = (Path(__file__).resolve().parent.parent
          / "server" / "keyserver.gs").read_text(encoding="utf-8")
    몸통 = 글[글.index("function adminSendText"):]
    몸통 = 몸통[:몸통.index("\nfunction ")]
    assert "who.scope !== 'owner'" in 몸통
    assert "forbidden" in 몸통
    # 하루 한도를 다 썼을 때 무엇을 하면 되는지도 알려 줘야 한다.
    assert "getRemainingDailyQuota" in 몸통
    assert "워크스페이스" in 몸통


def _붙은_매뉴얼(role: str = "admin"):
    from core.keymail import manual_html
    return manual_html(Registry().require("naver-blog"), role == "admin")


def test_the_mail_is_designed_not_bare_text():
    """메일도 화면이다.

    글자만 보내던 시절에는 매뉴얼의 `##` 가 제목으로 안 보이고 `#` 이 그냥
    찍혔다. 기호를 떼고 `────────` 로 칸을 나눴더니 이번에는 그 줄이 영문
    모를 것으로 보였다. 이제는 제목·표·카드 그대로 보낸다.
    """
    from core.keyauth import IssuedSet, ROLE_ADMIN
    from core.keymail import mail_html

    한벌 = IssuedSet(holder_name="박치홍", holder_email="a@b.example",
                     primary="AAAA-1111", secondary={"PC": "BBBB-2222"},
                     service_url="https://example.test/c/x", role=ROLE_ADMIN)
    글 = mail_html(program_name="프로그램", issued=한벌,
                   note=한벌.mail_body("프로그램"), manual=_붙은_매뉴얼())

    assert "─" not in 글, "영문 모를 줄이 다시 들어왔습니다"
    assert "<h2" in 글 or "<h3" in 글, "매뉴얼 제목이 제목으로 나와야 합니다"
    assert "<table" in 글, "매뉴얼 표가 표로 나와야 합니다"
    assert "https://example.test/c/x" in 글


def test_every_style_survives_the_attribute():
    """바깥 CSS 를 믿지 않으므로 `style="…"` 가 **끊기지 않아야** 한다.

    한 번 데였다. 글꼴 이름을 큰따옴표로 감쌌더니 `style="` 가 거기서 끊겨
    꾸민 것이 통째로 무시됐다. 화면에서는 멀쩡하고 메일에서만 날것으로
    보이는, 찾기 어려운 사고였다.
    """
    import core.keymail as keymail

    assert '"' not in keymail._글꼴
    for 태그, 꾸밈 in {**keymail._모양, **keymail._매뉴얼_제목}.items():
        assert '"' not in 꾸밈, f"{태그} 의 꾸밈이 style=\" 를 끊습니다"


def test_the_manual_is_not_taken_from_the_form():
    """보내는 사람이 고친 글에서 매뉴얼을 읽어 오지 않는다.

    매뉴얼은 프로그램에 든 파일 그대로 나가야 한다. 넘어온 글을 그대로
    믿으면 «매뉴얼» 이라는 이름으로 아무 글이나 실어 보낼 수 있다.
    """
    보내는곳 = Path("dashboard/webapp.py").read_text(encoding="utf-8")
    조각 = 보내는곳[보내는곳.index("async def keys_send"):]
    조각 = 조각[:조각.index("@app.post", 10)]
    assert "manual_html(program," in 조각
    assert 'form.get("manual' not in 조각


def test_plain_text_goes_along_for_old_mail_apps():
    """꾸민 판만 보내면 HTML 을 못 읽는 앱에서 글이 통째로 안 보인다."""
    from core.keyauth import IssuedSet

    한벌 = IssuedSet(holder_name="가", holder_email="a@b.example",
                     primary="AAAA", secondary={})
    글 = 한벌.plain_mail("안내 글", "매뉴얼 본문")
    assert "안내 글" in 글 and "매뉴얼 본문" in 글
    assert "─" not in 글 and "<" not in 글
