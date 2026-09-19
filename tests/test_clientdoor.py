"""클라이언트 문 테스트 — `/c/<상품>`.

고객은 **내 대시보드 접속 코드를 모른다.** 알아서도 안 된다. 그 안에 회원
목록과 매출이 있기 때문이다. 그래서 문을 따로 내고 이중키만 받는다.

여기서 확인할 것
    - 코드 없이 문 앞까지는 오는가 (그래야 키를 넣는다)
    - 키 없이 **안으로는** 못 들어오는가
    - 들어온 뒤 관리자 자리가 보이지 않는가
    - 끊겼을 때 **왜** 끊겼는지 말해 주는가
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from core import auth
from core.registry import Registry
from dashboard.app import create_app
from dashboard.clientdoor import cookie_name

KEY = re.compile(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}")
PROGRAM = "senior-video"


@pytest.fixture
def owner(tmp_path):
    """주인. 대시보드 코드를 알고, 키를 발급한다."""
    client = TestClient(create_app(tmp_path / "door.db"))
    assert client.post("/login", data={"code": auth.access_code()}).status_code == 200
    client.app_db_path = tmp_path / "door.db"
    return client


@pytest.fixture
def issued(owner):
    """발급된 **고객용** 키 한 벌 (1차키, PC, 노트북, 휴대폰).

    대시보드에서 발급하면 기본이 '판매'(관리자) 라, 고객 화면을 보려면
    역할을 적어 줘야 한다. 파는 쪽은 tests/test_resale.py 에서 본다.
    """
    response = owner.post(f"/apps/{PROGRAM}/admin/keys/issue",
                          data={"name": "박고객", "email": "guest@example.com",
                                "role": "client"},
                          follow_redirects=False)
    body = owner.get(response.headers["location"]).text
    codes = KEY.findall(body)
    assert len(codes) >= 4, "키 네 개가 안 나왔다"
    return codes[:4]


@pytest.fixture
def guest(owner):
    """고객. 같은 앱을 보지만 대시보드 코드는 없다."""
    return TestClient(owner.app)


# ─────────────────────────────────────────────── 문은 코드 없이 열린다
def test_고객은_대시보드_코드_없이_문_앞까지_온다(guest):
    response = guest.get(f"/c/{PROGRAM}")
    assert response.status_code == 200
    assert "1차 인증키" in response.text
    assert "/login" not in response.headers.get("location", "")


def test_고객이_관리자_주소로_가면_막힌다(guest):
    """`/apps/.../client` 는 여전히 대시보드 코드가 필요하다."""
    response = guest.get(f"/apps/{PROGRAM}/client", follow_redirects=False)
    assert response.status_code == 303
    assert "/login" in response.headers["location"]


def test_키_없이는_안으로_못_들어온다(guest):
    response = guest.get(f"/c/{PROGRAM}/t/home")
    assert response.status_code == 401
    assert "1차 인증키" in response.text, "막고 끝내지 말고 키 넣을 자리를 준다"


# ─────────────────────────────────────────────────────── 키로 들어오기
def test_맞는_키로_들어온다(guest, issued):
    primary, pc, _note, _phone = issued
    response = guest.post(f"/c/{PROGRAM}",
                          data={"primary": primary, "secondary": pc},
                          follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/c/{PROGRAM}/t/")
    assert cookie_name(PROGRAM) in response.cookies


def test_쿠키에는_키가_아니라_토큰만_담긴다(guest, issued):
    """쿠키가 새는 순간 키까지 새면 안 된다."""
    primary, pc, _n, _p = issued
    response = guest.post(f"/c/{PROGRAM}",
                          data={"primary": primary, "secondary": pc},
                          follow_redirects=False)
    jar = response.cookies[cookie_name(PROGRAM)]
    assert primary not in jar and pc not in jar
    assert "httponly" in str(response.headers.get("set-cookie", "")).lower()


def test_틀린_키는_이유를_말해_준다(guest, issued):
    """'인증 실패' 한 줄로는 무엇을 고쳐야 할지 모른다."""
    primary, pc, _n, _p = issued

    wrong = guest.post(f"/c/{PROGRAM}",
                       data={"primary": "AAAA-BBBB-CCCC", "secondary": pc})
    assert wrong.status_code == 401
    assert "1차 인증키가 맞지 않습니다" in wrong.text

    swapped = guest.post(f"/c/{PROGRAM}", data={"primary": pc, "secondary": primary})
    assert "1차 인증키 칸에는 1차키" in swapped.text


def test_남의_2차키로는_못_들어온다(owner, guest, issued):
    """키 두 개를 따로 주워도 섞어서는 못 쓴다."""
    primary, _pc, _n, _p = issued
    other = owner.post(f"/apps/{PROGRAM}/admin/keys/issue",
                       data={"name": "김다른", "email": "other@example.com"},
                       follow_redirects=False)
    other_codes = KEY.findall(owner.get(other.headers["location"]).text)

    response = guest.post(f"/c/{PROGRAM}",
                          data={"primary": primary, "secondary": other_codes[1]})
    assert "짝이 아닙니다" in response.text


def test_다른_프로그램의_키로는_못_들어온다(owner, guest, issued):
    """16종이 한 저장소를 쓴다. 산 프로그램만 열려야 한다."""
    primary, pc, _n, _p = issued
    response = guest.post("/c/exam-drill", data={"primary": primary, "secondary": pc})
    assert response.status_code == 401


# ──────────────────────────────────────────── 들어온 뒤에 보이는 것
def test_들어오면_관리자_자리가_안_보인다(guest, issued):
    primary, pc, _n, _p = issued
    guest.post(f"/c/{PROGRAM}", data={"primary": primary, "secondary": pc})
    body = guest.get(f"/c/{PROGRAM}/t/home").text

    assert "통합 대시보드" not in body, "고객 화면에 내 대시보드로 가는 길이 있다"
    assert "발급하고 안내문" not in body
    assert "모든 값 기본 세팅으로" not in body
    assert "관리자 모드" not in body


def test_들어온_뒤_관리자_탭_주소를_쳐도_안_열린다(guest, issued):
    primary, pc, _n, _p = issued
    guest.post(f"/c/{PROGRAM}", data={"primary": primary, "secondary": pc})

    for tab in ("keys", "presets", "files"):
        body = guest.get(f"/c/{PROGRAM}/t/{tab}").text
        assert "발급하고 안내문" not in body
        assert "전부 지우기" not in body


def test_문_안에서는_탭_링크가_문_안으로_간다(guest, issued):
    """`/apps/` 로 나가는 링크가 있으면 고객이 로그인 화면을 만난다."""
    primary, pc, _n, _p = issued
    guest.post(f"/c/{PROGRAM}", data={"primary": primary, "secondary": pc})
    body = guest.get(f"/c/{PROGRAM}/t/home").text
    assert "/apps/" not in body


# ───────────────────────────────────────────────── 기기당 한 세션
def test_다른_기기에서_들어오면_먼저_것이_끊기고_이유가_보인다(owner, issued):
    """매뉴얼이 고객에게 한 약속. 말해 주지 않으면 고장으로 여긴다."""
    primary, pc, _n, _p = issued
    first = TestClient(owner.app)
    second = TestClient(owner.app)

    first.post(f"/c/{PROGRAM}", data={"primary": primary, "secondary": pc})
    assert first.get(f"/c/{PROGRAM}/t/home").status_code == 200

    second.post(f"/c/{PROGRAM}", data={"primary": primary, "secondary": pc})

    kicked = first.get(f"/c/{PROGRAM}/t/home")
    assert kicked.status_code == 401
    assert "다른 기기에서 로그인되어" in kicked.text
    assert second.get(f"/c/{PROGRAM}/t/home").status_code == 200


def test_다른_기기_키는_서로_안_끊는다(owner, issued):
    """PC 와 휴대폰을 같이 켜 두는 것은 정상이다."""
    primary, pc, _note, phone = issued
    desk, hand = TestClient(owner.app), TestClient(owner.app)

    desk.post(f"/c/{PROGRAM}", data={"primary": primary, "secondary": pc})
    hand.post(f"/c/{PROGRAM}", data={"primary": primary, "secondary": phone})

    assert desk.get(f"/c/{PROGRAM}/t/home").status_code == 200
    assert hand.get(f"/c/{PROGRAM}/t/home").status_code == 200


def test_주인이_키를_정지하면_고객이_바로_끊긴다(owner, issued):
    primary, pc, _n, _p = issued
    guest = TestClient(owner.app)
    guest.post(f"/c/{PROGRAM}", data={"primary": primary, "secondary": pc})
    assert guest.get(f"/c/{PROGRAM}/t/home").status_code == 200

    body = owner.get(f"/apps/{PROGRAM}/admin/t/keys").text
    key_id = re.search(r"/admin/keys/(\d+)/toggle", body).group(1)
    owner.post(f"/apps/{PROGRAM}/admin/keys/{key_id}/toggle", follow_redirects=False)

    kicked = guest.get(f"/c/{PROGRAM}/t/home")
    assert kicked.status_code == 401
    assert "사용중지" in kicked.text


def test_나가기를_누르면_세션이_닫힌다(guest, issued):
    primary, pc, _n, _p = issued
    guest.post(f"/c/{PROGRAM}", data={"primary": primary, "secondary": pc})
    guest.post(f"/c/{PROGRAM}/out", follow_redirects=False)
    assert guest.get(f"/c/{PROGRAM}/t/home").status_code == 401


# ────────────────────────────────────────────────────── 안내 메일 주소
def test_안내문의_주소는_문이지_관리자_화면이_아니다(owner):
    """`/apps/.../client` 를 적어 보내면 고객은 들어오지 못한다."""
    response = owner.post(f"/apps/{PROGRAM}/admin/keys/issue",
                          data={"name": "박고객", "email": "guest@example.com"},
                          follow_redirects=False)
    body = owner.get(response.headers["location"]).text
    mail = body[body.index("<textarea"):body.index("</textarea>")]

    assert f"/c/{PROGRAM}" in mail
    assert f"/apps/{PROGRAM}/client" not in mail, (
        "고객에게 대시보드 코드가 필요한 주소를 보내고 있다")


# ──────────────────────────────────────────── 세 층이 정말로 갈리는가
#
# 사용자가 못 박은 것: "통합 관리자 대시보드는 메인 관리자이며 하부 프로그램을
# 판매하게 되면 그 담당자가 또 관리자 / 클라이언트가 되기 때문에 실제 메인
# 관리자 / 프로그램 관리자는 다른 점을 인지하고 완전히 다르게 제작."
#
#     메인 관리자    /                    접속 코드. 16종을 다 본다
#     프로그램 관리자 /apps/<상품>/admin   자기 것의 키를 발급한다
#     클라이언트     /c/<상품>            이중키. 결과만 본다


def test_프로그램_화면에는_다른_상품_메뉴가_없다(owner):
    """산 사람에게 내가 파는 다른 물건 목록을 보여 줄 이유가 없다."""
    body = owner.get(f"/apps/{PROGRAM}/admin").text
    for other in ("/programs/exam-drill", "/members", "/revenue"):
        assert other not in body, f"프로그램 화면에 {other} 가 있다"


def test_문_안에는_회원_매출_메뉴가_없다(guest, issued):
    primary, pc, _n, _p = issued
    guest.post(f"/c/{PROGRAM}", data={"primary": primary, "secondary": pc})
    body = guest.get(f"/c/{PROGRAM}/t/home").text

    for leaked in ("/members", "/revenue", "/settings", "/runs", "/config"):
        assert leaked not in body, f"고객 화면에 {leaked} 가 새어 나갔다"


def test_통합_대시보드는_접속_코드가_있어야_한다(guest):
    """문이 열렸다고 대시보드까지 열리면 안 된다."""
    for path in ("/", "/members", "/revenue", "/config"):
        response = guest.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert "/login" in response.headers["location"], path


def test_고객이_다른_상품의_문을_열_수_없다(owner, guest, issued):
    """한 프로그램을 샀다고 나머지 열다섯이 열리면 안 된다."""
    primary, pc, _n, _p = issued
    guest.post(f"/c/{PROGRAM}", data={"primary": primary, "secondary": pc})
    assert guest.get(f"/c/{PROGRAM}/t/home").status_code == 200

    for other in ("exam-drill", "naver-blog", "funnel-builder"):
        response = guest.get(f"/c/{other}/t/home")
        assert response.status_code == 401, f"{other} 가 열렸다"


def test_16종_모두_문이_있다(guest):
    """어느 상품을 팔든 고객이 들어올 자리가 있어야 한다."""
    for program in Registry().programs:
        response = guest.get(f"/c/{program.id}")
        assert response.status_code == 200, program.id
        assert "1차 인증키" in response.text, program.id


# ──────────────────────────────────────────── 16종 접속키 전체 초기화
#
# 프로그램마다 들어가 지우면 열여섯 번이다. 아직 아무것도 안 파셨을 때
# 한 번에 정리하시라고 설정 화면에 따로 두었다.

def test_통합_대시보드에서_키_만드는_자리를_찾을_수_있다(owner):
    """발급은 프로그램 안에 있다. 그게 맞는 자리인데, 통합 대시보드에 아무
    흔적이 없으면 **거기 있는 줄을 모른다.** 실제로 못 찾으셨다.
    """
    home = owner.get("/").text
    assert 'href="/keys"' in home, "왼쪽 메뉴에 접속키가 없다"

    body = owner.get("/keys").text
    for program in Registry().programs:
        assert f"/apps/{program.id}/admin/t/keys" in body, (
            f"{program.id} 의 키 만드는 자리로 가는 길이 없다")


def test_접속키_화면이_16종_현황을_보여_준다(owner):
    owner.post(f"/apps/{PROGRAM}/admin/keys/issue",
               data={"name": "박구매", "email": "buy@example.com"},
               follow_redirects=False)
    body = owner.get("/keys").text

    assert '<span class="tvalue">1<small>명' in body, "받은 사람 수가 안 올라간다"
    assert "전체 초기화" in body, "키가 있으면 비우는 자리가 나와야 한다"


def test_키가_없으면_초기화_자리를_그리지_않는다(owner):
    """지울 것이 없는데 빨간 상자를 띄워 놓을 이유가 없다."""
    assert "전부 지우기" not in owner.get("/keys").text


def test_초기화_자리가_두_군데_있지_않다(owner):
    """같은 일을 두 곳에 두면 한쪽만 고치게 된다."""
    assert "전부 지우기" not in owner.get("/settings").text
    assert 'href="/keys"' in owner.get("/settings").text, "가는 길은 알려 준다"


def test_16종_키를_한_번에_비운다(owner):
    # 이메일을 서로 다르게 준다. '받은 사람' 은 이메일로 세기 때문에, 같은
    # 주소로 세 번 주면 세 프로그램을 산 한 사람으로 잡힌다 — 그게 맞다.
    for program_id in (PROGRAM, "exam-drill", "naver-blog"):
        owner.post(f"/apps/{program_id}/admin/keys/issue",
                   data={"name": f"{program_id}님",
                         "email": f"{program_id}@example.com"},
                   follow_redirects=False)
    assert '<span class="tvalue">3<small>명' in owner.get("/keys").text

    response = owner.post("/keys/reset",
                          data={"confirm": "초기화"}, follow_redirects=False)
    assert "error=" not in response.headers["location"]

    body = owner.get(response.headers["location"]).text
    assert '<span class="tvalue">0<small>명' in body
    for program_id in (PROGRAM, "exam-drill", "naver-blog"):
        assert f"{program_id}님" not in owner.get(
            f"/apps/{program_id}/admin/t/keys").text


def test_전체_초기화도_글자를_정확히_쳐야_한다(owner):
    owner.post(f"/apps/{PROGRAM}/admin/keys/issue",
               data={"name": "안지워질사람", "email": "a@example.com"},
               follow_redirects=False)

    response = owner.post("/keys/reset",
                          data={"confirm": "지워줘"}, follow_redirects=False)
    assert "error=" in response.headers["location"]
    assert "안지워질사람" in owner.get(f"/apps/{PROGRAM}/admin/t/keys").text


def test_지웠는데_저장했다고_하지_않는다(owner):
    """저장과 삭제는 다른 일이다. 키를 지우고 '저장했습니다' 라고 하면 안 된다."""
    owner.post(f"/apps/{PROGRAM}/admin/keys/issue",
               data={"name": "홍길동", "email": "a@example.com"},
               follow_redirects=False)
    response = owner.post("/keys/reset",
                          data={"confirm": "초기화"}, follow_redirects=False)

    body = owner.get(response.headers["location"]).text
    assert "모두 지웠습니다" in body
    assert "저장했습니다" not in body


def test_초기화_실패는_빨갛게_뜬다(owner):
    """실패를 saved 로 보내면 '저장했습니다' 옆에 실패 사유가 붙는다."""
    response = owner.post("/keys/reset",
                          data={"confirm": ""}, follow_redirects=False)
    body = owner.get(response.headers["location"]).text

    assert "note bad" in body
    assert "저장했습니다" not in body


def test_예전_초기화_주소도_계속_통한다(owner):
    """`/settings/keys/reset` 을 눌러 두신 분이 있을 수 있다."""
    owner.post(f"/apps/{PROGRAM}/admin/keys/issue",
               data={"name": "옛주소", "email": "a@example.com"},
               follow_redirects=False)

    response = owner.post("/settings/keys/reset", data={"confirm": "초기화"})
    assert response.status_code == 200
    assert "옛주소" not in owner.get(f"/apps/{PROGRAM}/admin/t/keys").text


def test_같은_사람이_여러_프로그램을_사면_한_명으로_센다(owner):
    """'받은 사람' 은 이메일로 센다. 세 개를 산 한 사람이 세 명이 되면 안 된다."""
    for program_id in (PROGRAM, "exam-drill", "naver-blog"):
        owner.post(f"/apps/{program_id}/admin/keys/issue",
                   data={"name": "박구매", "email": "buy@example.com"},
                   follow_redirects=False)

    body = owner.get("/keys").text
    assert '<span class="tvalue">1<small>명' in body, "한 사람이 여러 명으로 세어진다"
    assert '<span class="tvalue">3<small>건' in body, "판 것은 프로그램마다 따로 센다"
