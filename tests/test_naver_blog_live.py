"""3번 — **자기 서버에 세워 쓰는 상품**이라는 것이 화면·안내문·매뉴얼에
빠짐없이 반영돼 있는가.

한동안은 주소가 하나였다. 관리자도 고객도 우리 maim 으로 들어오고 넣는
키로만 갈렸다. **그것을 뒤집었다.** 그 구조에서는 산 분의 고객이 쓴 글이
전부 우리 서버에 쌓인다 — 팔아 놓고 데이터는 우리가 들고 있는 꼴이라
팔 수가 없다.

지금은 이렇게 갈린다.

    판매(관리자)  주소가 **안 나간다.** 설치 안내서가 대신 간다.
                  그분이 자기 Cloud Run 에 세우고, 글은 그분 자리에 쌓인다
    체험(고객용)  **우리 주소.** 기간을 둔 맛보기다. 기간이 끝나거나
                  중간에 끊으면 그분이 남긴 것은 우리 서버에서 지워진다

이 파일은 그 뒤집힘이 어느 한 군데서 되돌아가지 않도록 지킨다.
"""

from __future__ import annotations

import pytest

from core.registry import Registry


def _p():
    return Registry().require("naver-blog")


def test_it_points_at_maim():
    program = _p()
    assert program.live.elsewhere, "본체가 밖에 있다고 표시되어야 한다"
    assert "maim" in program.live.demo, "체험이 여는 곳은 우리 maim(체험용 자리)이다"
    assert program.live.demo.startswith("https://"), "키를 넣는 화면이다. http 는 안 된다"


def test_the_buyer_gets_no_address():
    """**산 분에게 우리 주소를 보내지 않는다.**

    이 한 줄이 이 상품의 전부다. 여기에 주소가 들어가는 순간 산 분의
    고객이 쓴 글이 전부 우리 서버로 들어오고, 그러면 "사장님 데이터는
    사장님 것" 이라는 말이 거짓이 된다.
    """
    program = _p()
    assert program.live.self_hosted, "자기 서버에 세워 쓰는 상품이어야 한다"
    assert program.live.admin == "", (
        "산 분에게 나갈 주소가 적혀 있습니다. 비워 두어야 설치 안내서가 대신 갑니다")
    # 빈 값이 door(대시보드 안의 흉내 화면)로 슬쩍 메워지면 안 된다.
    assert program.entrance(for_admin=True, door="https://dash.example/p/naver-blog") == ""
    assert program.entrance(for_admin=False, door="https://dash.example/p/naver-blog") \
        == program.live.demo


def test_체험은_따로_세운_자리로_간다():
    """**맛보러 오신 분을 사장님 일감 옆에 앉히지 않는다.**

    한동안은 같은 주소였다. 칸막이(owner_key)를 쳐 두었어도 같은 서버의
    메모리와 Claude 한도를 나눠 쓴다. 체험 몇 분이 몰리면 사장님 아침
    글이 늦어지고, 그쪽에서 탈이 나면 사장님 것이 같이 멈춘다.

    그리고 이 자리가 **비면 안 된다.** 비면 `client` 로, 거기도 비면 빈
    글자로 떨어져서, 주소 없는 안내문이 체험 회원에게 나간다.
    """
    program = _p()
    assert program.live.demo, (
        "체험이 열 주소가 비어 있습니다. 비면 주소 없는 안내문이 나갑니다")
    assert program.live.demo.startswith("https://")
    assert program.entrance(for_admin=False) == program.live.demo, (
        "체험은 demo 로만 가야 합니다")


def test_the_buyer_mail_sends_the_install_guide_instead():
    """주소가 없는 자리에 **무엇이 대신 가는지**까지 지킨다.

    주소만 비워 두고 안내문이 «(서비스 주소)» 같은 빈 자리를 보이면,
    받는 분은 무엇을 해야 할지 모른 채 문의부터 하신다.
    """
    from core.keyauth import IssuedSet, ROLE_ADMIN, ROLE_CLIENT
    from core.keymail import mail_html

    program = _p()
    산분 = IssuedSet(holder_name="박사장", holder_email="a@b.c", primary="AAAA-BBBB",
                    secondary={"PC": "P1"}, role=ROLE_ADMIN,
                    service_url=program.entrance(for_admin=True))
    글 = 산분.mail_body(program.name)
    assert "설치 안내서" in 글
    assert "(서비스 주소)" not in 글, "빈 주소 자리가 그대로 보입니다"
    assert "run.app" not in 글, "산 분 안내문에 우리 주소가 들어갔습니다"

    꾸민판 = mail_html(program_name=program.name, issued=산분, note=글, manual="")
    assert "프로그램 열기" not in 꾸민판, "누를 수 없는 버튼을 내고 있습니다"
    assert "먼저 설치가 필요합니다" in 꾸민판

    체험 = IssuedSet(holder_name="김체험", holder_email="a@b.c", primary="CCCC-DDDD",
                    secondary={"PC": "P2"}, role=ROLE_CLIENT,
                    service_url=program.entrance(for_admin=False))
    assert program.live.demo in 체험.mail_body(program.name), "체험에는 주소가 가야 한다"


def test_keys_come_from_one_ledger():
    """접속키는 **한 장부**에서만 나온다.

    예전에는 이 프로그램이 자기 접속 코드를 따로 만들어 썼다. 모양은 같았지만
    장부가 달라서, 대시보드에서 판 키가 여기서는 "없는 코드" 로 나왔다. 파는
    곳과 여는 곳이 갈라져 있으면 누구에게 무엇을 팔았는지 한 군데서 볼 수가
    없다.

    (이 시험은 예전에 "메일로 보내는 기능이 아직 없다" 를 지키던 자리다.
    그 사실이 바뀌었으므로 지킬 것도 바뀐다.)
    """
    program = _p()
    안내 = program.live.note
    assert "접속키" in 안내
    assert "아직 없습니다" not in 안내, "이미 되는 것을 안 된다고 적어 두었습니다"

    조심 = " ".join(program.requirements.cautions)
    assert "대시보드에서만 발급" in 조심
    # 설정이 빠지면 고객이 못 들어온다. 그 사실을 적어 둬야 한다.
    assert "KEYSERVER_URL" in 조심


def test_the_manual_says_where_keys_come_from():
    """매뉴얼도 같은 말을 해야 한다. 화면과 문서가 다르면 문서가 진다."""
    program = _p()
    글 = program.resolve(program.manuals.admin).read_text(encoding="utf-8")
    assert "라이선스" in 글, "받은 키가 무엇에 쓰이는지 안 적혀 있습니다"
    assert "KEYSERVER_URL" in 글, "설정이 빠졌을 때 무엇을 할지 안 적혀 있습니다"


def test_the_old_cli_is_gone():
    """옛 파이썬 초안 생성기 이야기가 한 줄도 남으면 안 된다."""
    program = _p()
    글 = " ".join([
        program.summary,
        " ".join(s.title + " " + s.body for s in program.steps),
        " ".join(q.q + " " + q.a for q in program.faq),
        " ".join(s.key + " " + s.label for s in program.settings),
    ])
    for 옛것 in ("cli.py", "keywords.txt", "request.yaml", "데이터랩", "--fixture"):
        assert 옛것 not in 글, f"옛 CLI 내용이 남았습니다: {옛것}"


def test_auto_publishing_stays_off():
    """자동 발행을 넣었다가 **계정 보호조치**가 걸렸다. 되살리면 안 된다."""
    program = _p()
    조심 = " ".join(program.requirements.cautions)
    assert "자동 발행을 하지 않습니다" in 조심
    assert "계정 보호조치" in 조심
    assert "비밀번호를 이 프로그램에 넣지 않습니다" in 조심


def test_console_matches_the_real_program():
    from core.webui import load_console

    화면 = load_console(_p(), {})
    라벨 = [t.label for t in 화면.tabs]
    for 필요 in ("어디서 도나", "접속 코드", "블로그 쓰는 법", "꼭 지킬 것", "자주 오는 문의"):
        assert 필요 in 라벨, f"'{필요}' 탭이 없습니다 (지금: {라벨})"

    글 = " ".join([화면.admin_intro, 화면.client_intro,
                   " ".join(t.intro for t in 화면.tabs),
                   " ".join(m.task + " " + m.why for m in 화면.manual_tasks),
                   " ".join(t.symptom + " " + t.fix for t in 화면.troubles)])
    assert "같은 주소" in 글, "두 모드가 같은 주소라고 말해야 한다"
    assert "이 화면이 아닙니다" in 화면.client_intro
    for 옛것 in ("cli.py", "keywords.txt", "데이터랩"):
        assert 옛것 not in 글, f"콘솔에 옛 내용이 남았습니다: {옛것}"


def test_hidden_panel_is_explained_as_normal():
    """«접속 코드 관리가 안 보인다» 가 제일 많이 올 문의다. 정상이라고 말해야 한다."""
    from core.webui import load_console

    화면 = load_console(_p(), {})
    고침 = " ".join(t.symptom + " " + t.fix for t in 화면.troubles)
    assert "안 보인다" in 고침 and "정상" in 고침


@pytest.mark.parametrize("pid,자기서버냐", [("naver-blog", True), ("exam-drill", False)])
def test_the_screen_matches_how_the_program_splits(pid, 자기서버냐):
    """프로그램마다 가르는 방식이 다르다. 버튼이 그것을 따라야 한다."""
    from core import auth
    from fastapi.testclient import TestClient

    from dashboard.app import app

    client = TestClient(app)
    client.cookies.set(auth.COOKIE_NAME, auth.issue_token())
    body = client.get(f"/programs/{pid}", follow_redirects=True).text

    if 자기서버냐:
        # 이 주소를 [관리자 모드] 라고 내면, 그걸 눌러 본 뒤 그대로 산 분께
        # 보내게 된다. 이름이 곧 안전장치다.
        assert "체험 화면 열기 ↗" in body
        assert "관리자 모드 ↗" not in body, (
            "산 분에게는 열 주소가 없다. 우리 주소를 [관리자 모드] 로 내면 안 된다")
        assert "파실 때 보내는 주소가 아닙니다" in body, (
            "이 주소가 체험용이라는 말이 화면에 없으면, 판매 키에 이 주소를 넣게 된다")
        assert "접속키 발급하기 ↗" not in body, (
            "키는 이 대시보드의 [접속키] 탭에서 만든다. 바깥으로 보내는 버튼을 "
            "또 두면 «어느 쪽에서 만들지» 가 된다"
        )
    else:
        assert "관리자 모드 ↗" in body and "클라이언트 모드 ↗" in body
        assert "접속키 발급하기 ↗" in body


def test_바깥_주소_설명이_별표째_찍히지_않는다():
    """`**굵게**` 가 글자 그대로 보이면 안 된다.

    한 번 데였다. `_tabs.html` 에는 마크다운 거르개를 걸어 뒀는데
    `console_base.html` 에는 안 걸어서, 콘솔 화면에서만 별표가 그대로
    찍혔다. 같은 글을 두 군데서 내면 한쪽을 빠뜨린다.
    """
    from pathlib import Path
    import re

    for 자리 in ("dashboard/templates/console_base.html",
                 "dashboard/templates/_tabs.html"):
        글 = Path(자리).read_text(encoding="utf-8")
        for m in re.finditer(r"\{\{\s*program\.live\.note[^}]*\}\}", 글):
            assert "| md" in m.group(0) or "|md" in m.group(0), (
                f"{자리} 에서 마크다운을 안 걸었습니다: {m.group(0)}")
