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

    주소로 가르지 않고 **넣는 키로** 가른다. 1번의 `?admin=1` 과 다르다.
    """
    program = _p()
    assert program.live.one_door, "주소가 하나여야 한다"
    assert program.live.admin == program.live.client


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
    assert "자기 접속 코드를 만들지 않습니다" in 글
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
            "주소가 하나인 프로그램이다. 키는 이 대시보드의 [접속키] 탭에서 "
            "만들므로, 바깥 화면으로 보내는 버튼을 또 두면 헷갈린다"
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
