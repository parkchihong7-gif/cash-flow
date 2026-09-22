"""3번 — 본체가 maim(Cloud Run)이라는 것이 화면에 맞게 반영돼 있는가.

1번(공인중개사)과 **가르는 방식이 다르다.** 1번은 주소로 갈리고(`?admin=1`),
3번은 **넣는 키로** 갈린다 — 주소가 하나다. 그 차이를 화면이 말해야 한다.
"""

from __future__ import annotations

import pytest

from core.registry import Registry


def _p():
    return Registry().require("naver-blog")


def test_it_points_at_maim():
    program = _p()
    assert program.live.elsewhere, "본체가 밖에 있다고 표시되어야 한다"
    assert "maim" in program.live.admin
    assert program.live.admin.startswith("https://"), "키를 넣는 화면이다. http 는 안 된다"


def test_one_address_two_roles():
    """관리자와 고객이 **같은 주소**로 들어간다.

    maim 의 `refreshAccessCodes()` 가 `isMasterSession` 이 아니면
    접속 코드 관리 칸을 `hidden` 으로 숨긴다. 그래서 별도 주소가 필요 없다.
    """
    program = _p()
    assert program.live.one_door, "주소가 하나여야 한다"
    assert program.live.admin == program.live.client


def test_the_mail_gap_is_written_down():
    """접속 코드를 메일로 보내는 기능이 **아직 없다.** 그걸 적어 둬야 한다."""
    program = _p()
    assert "메일" in program.live.note
    assert "예정" in program.live.note
    조심 = " ".join(program.requirements.cautions)
    assert "메일로 보내는 기능이 아직 없습니다" in 조심


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


@pytest.mark.parametrize("pid,하나냐", [("naver-blog", True), ("exam-drill", False)])
def test_the_screen_matches_how_the_program_splits(pid, 하나냐):
    """프로그램마다 가르는 방식이 다르다. 버튼이 그것을 따라야 한다."""
    from core import auth
    from fastapi.testclient import TestClient

    from dashboard.app import app

    client = TestClient(app)
    client.cookies.set(auth.COOKIE_NAME, auth.issue_token())
    body = client.get(f"/programs/{pid}", follow_redirects=True).text

    if 하나냐:
        assert "프로그램 열기 ↗" in body
        assert "관리자 모드 ↗" not in body, "주소가 하나인데 버튼이 둘이면 헷갈린다"
        assert "접속키 발급하기 ↗" not in body, (
            "자기 안에 코드 발급 화면이 있는 프로그램이다. "
            "여기에 또 두면 어느 쪽에서 만들지 헷갈린다"
        )
    else:
        assert "관리자 모드 ↗" in body and "클라이언트 모드 ↗" in body
        assert "접속키 발급하기 ↗" in body
