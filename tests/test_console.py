"""운영 콘솔 테스트 — 탭·타일·오늘 할 일, 그리고 **모드 사이의 벽**.

참조한 관리자 세 개(유튜브 12탭·컨퍼런스·공인중개사/maim)의 공통 문법을 따라
한 장짜리 폼을 왼쪽 탭 콘솔로 바꿨다. 여기서 확인할 것은 두 가지다.

    1. 16종이 하나도 빠짐없이, 두 모드 모두 뜨는가
    2. 클라이언트가 **주소를 직접 쳐도** 관리자 자리에 못 닿는가

2번이 특히 중요하다. 화면에서 메뉴를 감추는 것은 잠금이 아니다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core import auth, console as console_mod, presets as presets_mod
from core.console import Console, Tab, Todo, Stat, ManualTask, Trouble
from core.keyauth import KeyAuth
from core.registry import Registry
from core.webui import MODES, Field, Panel, default_webui, load_webui
from dashboard.app import create_app

ALL = [program.id for program in Registry().programs]


@pytest.fixture
def client(tmp_path):
    client = TestClient(create_app(tmp_path / "console.db"))
    assert client.post("/login", data={"code": auth.access_code()}).status_code == 200
    return client


# ───────────────────────────────────────────── 16종이 콘솔로 다 뜬다
@pytest.mark.parametrize("program_id", ALL)
@pytest.mark.parametrize("mode", MODES)
def test_모든_프로그램이_콘솔로_뜬다(client, program_id, mode):
    response = client.get(f"/apps/{program_id}/{mode}")
    assert response.status_code == 200, f"{program_id}/{mode}"
    assert "불러오지 못했습니다" not in response.text, f"{program_id} 콘솔이 깨졌다"


@pytest.mark.parametrize("program_id", ALL)
def test_공통_탭은_16종_전부에_있다(client, program_id):
    """16종을 번갈아 쓰는 사람이 매번 다른 곳을 뒤지지 않게."""
    body = client.get(f"/apps/{program_id}/admin").text
    for label in ("자동 실행", "접속키", "기본 세팅"):
        assert label in body, f"{program_id} 에 '{label}' 탭이 없다"


@pytest.mark.parametrize("program_id", ALL)
def test_탭마다_주소가_따로_있다(client, program_id):
    """팝업으로 따로 열 수 있어야 하고, 주소로 자리를 가리킬 수 있어야 한다."""
    for tab in ("keys", "presets", "auto"):
        response = client.get(f"/apps/{program_id}/admin/t/{tab}")
        assert response.status_code == 200, f"{program_id}/{tab}"


def test_없는_탭을_치면_첫_화면으로(client):
    """주소를 잘못 쳐도 빈 화면이 아니라 쓸 수 있는 자리로 보낸다.

    첫 탭 이름은 상품마다 다르므로(문항 채우기·기획 수치·키워드 수요…)
    이름으로 보지 않고 **그 상품의 첫 탭과 같은 것이 떴는지**로 본다.
    """
    from core.webui import load_console

    first = load_console(Registry().require("exam-drill"), {}).tabs[0]
    response = client.get("/apps/exam-drill/admin/t/그런탭없음")

    assert response.status_code == 200
    assert first.label in response.text, "첫 탭으로 보내지 않았다"


# ─────────────────────────────────── 클라이언트는 관리자 자리에 못 닿는다
@pytest.mark.parametrize("program_id", ALL)
def test_클라이언트_화면에는_접속키_탭이_없다(client, program_id):
    """키를 발급하는 자리는 **판 사람의 것**이다."""
    body = client.get(f"/apps/{program_id}/client").text
    assert "/client/t/keys" not in body
    assert "/client/t/presets" not in body


@pytest.mark.parametrize("tab", ["keys", "presets", "files"])
def test_주소를_직접_쳐도_관리자_탭은_안_열린다(client, tab):
    """메뉴에서 감추는 것은 잠금이 아니다. 주소로 들어오는 길까지 닫는다."""
    response = client.get(f"/apps/exam-drill/client/t/{tab}")
    assert response.status_code == 200
    assert "발급하고 안내문" not in response.text
    assert "전부 지우기" not in response.text
    assert "모든 값 기본 세팅으로" not in response.text


def test_키_발급은_클라이언트_주소로는_안_된다(client):
    """POST 주소 자체가 /admin/ 아래에 있어 닿지 않는다."""
    response = client.post("/apps/exam-drill/client/keys/issue",
                           data={"name": "홍길동", "email": "hong@example.com"},
                           follow_redirects=False)
    assert response.status_code == 404


# ───────────────────────────────────────────────── 콘솔 조립 규칙
def test_클라이언트_콘솔은_관리자_것만_빠진_같은_화면():
    """따로 만들면 한쪽만 고치게 된다. 같은 것에서 덜어낸다."""
    full = Console(
        program_id="x", title="x",
        tabs=[
            Tab(key="a", label="모두"),
            Tab(key="b", label="나만", admin_only=True),
        ],
        todos=[Todo("같이 봄"), Todo("나만 봄", admin_only=True)],
        stats=[Stat("보임", "1"), Stat("숨김", "2", tab="b")],
    )
    client_view = full.for_mode("client")

    assert [t.key for t in client_view.tabs] == ["a"]
    assert [t.text for t in client_view.todos] == ["같이 봄"]
    assert [s.label for s in client_view.stats] == ["보임"], (
        "관리자 전용 탭으로 가는 타일이 고객 화면에 남았다")
    assert full.for_mode("admin") is full


def test_관리자_전용_칸은_클라이언트_패널에서_빠진다():
    tab = Tab(key="a", label="a", panels=[Panel(
        key="p", title="p", fields=[
            Field(key="open", label="열림"),
            Field(key="secret", label="숨김", admin_only=True),
        ])])
    stripped = Console(program_id="x", title="x", tabs=[tab]).for_mode("client")
    keys = [f.key for f in stripped.tabs[0].panels[0].fields]
    assert keys == ["open"]


def test_고객에게_내_폴더_구조를_보여_주지_않는다():
    from core.console import FileLoc
    full = Console(program_id="x", title="x",
                   files=[FileLoc("인증 파일", "secrets/")])
    assert full.for_mode("client").files == []


def test_빈_공통탭은_붙이지_않는다():
    """빈 탭이 있으면 '아직 안 만들었나' 싶어 오히려 신뢰를 깎는다."""
    built = console_mod.add_standard_tabs(Console(program_id="x", title="x"))
    keys = [tab.key for tab in built.tabs]

    assert "trouble" not in keys and "hand" not in keys
    assert "keys" in keys and "presets" in keys, (
        "접속키·기본 세팅은 비어 있는 것 자체가 봐야 할 정보라 늘 붙인다")


def test_내용이_있으면_붙는다():
    built = console_mod.add_standard_tabs(Console(
        program_id="x", title="x",
        manual_tasks=[ManualTask("댓글 고정", "스튜디오", "API 미지원")],
        troubles=[Trouble("안 열림", "서버를 켜세요")],
    ))
    keys = [tab.key for tab in built.tabs]
    assert "hand" in keys and "trouble" in keys


def test_상품이_콘솔을_안_만들어도_화면은_뜬다():
    """1차에서 만든 화면이 하나도 안 깨지고 새 껍데기로 들어온다."""
    program = Registry().require("funnel-builder")
    built = console_mod.from_webui(program, load_webui(program))

    assert built.tabs, "탭이 하나도 없다"
    assert built.tabs[0].panels, "패널이 비었다"
    assert built.custom is False


# ───────────────────────────────────────────── 손으로 할 일 / 문제 해결
def test_손으로_할_일에는_이유가_함께_적힌다(client):
    """이유 없는 수동 작업은 불만만 쌓인다."""
    body = client.get("/apps/senior-video/admin/t/hand").text
    if "프로그램이 대신 못 하는 일" in body:
        assert "왜 손으로 하는가" in body


# ─────────────────────────────────────────────────── 검증값 기본 세팅
def test_값을_바꾸면_노랗게_뜨고_되돌릴_수_있다(client):
    program = Registry().require("senior-video")
    key = program.settings[0].key

    body = client.get("/apps/senior-video/admin/t/presets").text
    assert "☑" in body, "안 바꿨는데 체크가 꺼져 있다"

    client.post("/apps/senior-video/admin/settings",
                data={key: "일부러 바꾼 값"}, follow_redirects=False)
    body = client.get("/apps/senior-video/admin/t/presets").text
    assert "☐" in body and "바꿈" in body
    assert "모든 값 기본 세팅으로" in body

    client.post("/apps/senior-video/admin/presets/restore", follow_redirects=False)
    body = client.get("/apps/senior-video/admin/t/presets").text
    assert "☑" in body, "되돌렸는데 여전히 바뀐 상태로 보인다"


def test_한_값만_되돌릴_수_있다(client):
    program = Registry().require("senior-video")
    first, second = program.settings[0].key, program.settings[1].key
    client.post("/apps/senior-video/admin/settings",
                data={first: "바꿈1", second: "바꿈2"}, follow_redirects=False)

    client.post("/apps/senior-video/admin/presets/restore",
                data={"key": first}, follow_redirects=False)

    body = client.get("/apps/senior-video/admin/t/presets").text
    assert "바꿈2" in body, "안 건드린 값까지 되돌아갔다"
    assert "바꿈1" not in body


# ─────────────────────────────────────────────────────────── 접속키 화면
def test_키를_발급하면_안내문이_한_번_나온다(client):
    """키가 주소에 실리면 브라우저 기록과 서버 로그에 남는다."""
    response = client.post("/apps/exam-drill/admin/keys/issue",
                           data={"name": "발급시험자", "email": "hong@example.com"},
                           follow_redirects=False)
    assert response.status_code == 303
    location = response.headers["location"]
    assert "EV" not in location.upper().replace("EXAM", "")  # 키가 주소에 없다

    body = client.get(location).text
    assert "님께 보낼 안내문" in body
    assert "1차 인증키" in body and "2차 인증키" in body
    assert "PC :" in body and "노트북 :" in body and "휴대폰 :" in body

    again = client.get(location).text
    assert "님께 보낼 안내문" not in again, "안내문이 두 번 보인다"


def test_이름_없이_발급하면_이유를_알려_준다(client):
    from urllib.parse import unquote
    response = client.post("/apps/exam-drill/admin/keys/issue",
                           data={"name": "", "email": "hong@example.com"},
                           follow_redirects=False)
    assert "error=" in response.headers["location"]
    assert "이름" in unquote(response.headers["location"])


def test_초기화는_글자를_정확히_쳐야_한다(client):
    # 발급 폼의 placeholder 가 '홍길동' 이라 그 이름으로는 지워졌는지 알 수 없다.
    who = "초기화시험자"
    client.post("/apps/exam-drill/admin/keys/issue",
                data={"name": who, "email": "hong@example.com"},
                follow_redirects=False)

    bad = client.post("/apps/exam-drill/admin/keys/reset",
                      data={"confirm": "지워줘"}, follow_redirects=False)
    assert "error=" in bad.headers["location"]
    assert who in client.get("/apps/exam-drill/admin/t/keys").text, "실패했는데 지워졌다"

    ok = client.post("/apps/exam-drill/admin/keys/reset",
                     data={"confirm": "초기화"}, follow_redirects=False)
    assert "error=" not in ok.headers["location"]
    assert who not in client.get("/apps/exam-drill/admin/t/keys").text


def test_프로그램마다_키가_따로_논다(client):
    """16종이 한 저장소를 쓴다. 한 프로그램을 비워도 남은 곳은 멀쩡해야 한다."""
    for pid in ("exam-drill", "naver-blog"):
        client.post(f"/apps/{pid}/admin/keys/issue",
                    data={"name": f"{pid}씨", "email": "a@example.com"},
                    follow_redirects=False)

    client.post("/apps/exam-drill/admin/keys/reset",
                data={"confirm": "초기화"}, follow_redirects=False)

    assert "naver-blog씨" in client.get("/apps/naver-blog/admin/t/keys").text
    assert "exam-drill씨" not in client.get("/apps/exam-drill/admin/t/keys").text


# ───────────────────────────────────── 전용 콘솔이 조용히 죽지 않는가
#
# `load_console()` 은 상품 코드가 깨져도 화면이 뜨도록 기본 화면으로 갈아끼운다.
# 그 덕에 대시보드가 안 죽지만, **깨진 줄 모르고 지나갈 수 있다.** 실제로
# 14번 콘솔을 쓰다가 속성 이름을 세 번 잘못 짚었는데(level·monthly_won·
# DAILY_UNITS) 화면은 200 으로 멀쩡히 떴다. 그래서 따로 본다.

CUSTOM = ALL           # 16종 전부 전용 콘솔을 갖는다


@pytest.mark.parametrize("program_id", CUSTOM)
def test_전용_콘솔이_기본_화면으로_떨어지지_않는다(program_id):
    from core.webui import load_console

    program = Registry().require(program_id)
    built = load_console(program, {})

    assert built is not None, f"{program_id} 에 console() 이 없다"
    assert built.custom is True, (
        f"{program_id} 의 console() 이 오류로 기본 화면으로 떨어졌다. "
        f"첫 패널: {built.tabs[0].panels[0].note if built.tabs[0].panels else '?'}")
    assert len(built.tabs) >= 3, f"{program_id} 탭이 너무 적다"


@pytest.mark.parametrize("program_id", CUSTOM)
def test_전용_콘솔에는_손으로_할_일과_문제_해결이_있다(program_id):
    """팔 물건이다. '왜 자동이 아니냐', '이럴 땐 어쩌냐' 는 반드시 온다."""
    from core.webui import load_console

    built = load_console(Registry().require(program_id), {})
    assert built.manual_tasks, f"{program_id} 에 손으로 할 일이 비어 있다"
    assert built.troubles, f"{program_id} 에 문제 해결이 비어 있다"
    for task in built.manual_tasks:
        assert task.why.strip(), f"{program_id}: '{task.task}' 에 이유가 없다"


@pytest.mark.parametrize("program_id", CUSTOM)
def test_한_콘솔_안에_같은_이름의_탭이_없다(program_id):
    from core.webui import load_console

    labels = [tab.label for tab in load_console(Registry().require(program_id), {}).tabs]
    assert len(labels) == len(set(labels)), f"{program_id} 에 같은 이름의 탭이 있다"


def test_프로그램마다_탭_구성이_다르다():
    """참조한 관리자의 탭을 통째로 복사해 붙이지 않았는지.

    낱말로 거르지 않는다. 처음에는 '비자' 라는 낱말을 금지어로 뒀는데,
    16번은 **실제로 해외 연사 비자가 업무**라 정당한 탭을 잡아냈다.
    베끼기의 증거는 낱말이 아니라 **탭 구성이 통째로 겹치는 것**이다.
    """
    from core.webui import load_console

    sets = {}
    for program_id in CUSTOM:
        built = load_console(Registry().require(program_id), {})
        sets[program_id] = frozenset(tab.label for tab in built.tabs)

    seen: dict[frozenset, str] = {}
    for program_id, labels in sets.items():
        twin = seen.get(labels)
        assert twin is None, f"{program_id} 와 {twin} 의 탭이 완전히 같다"
        seen[labels] = program_id

    for program_id, labels in sets.items():
        for other_id, other in sets.items():
            if program_id >= other_id:
                continue
            shared = labels & other
            assert len(shared) <= 2, (
                f"{program_id} 와 {other_id} 가 탭을 {len(shared)}개 공유한다: {shared}")


def test_올려도_되나_타일이_검사_결과와_어긋나지_않는다():
    """타일과 검사가 다른 말을 하면 둘 다 못 믿게 된다.

    실제로 `Issue.level` 을 'bad' 로 걸러서(진짜 값은 'block') 빈칸이 세 곳
    남았는데도 '올려도 됩니다' 라고 띄운 적이 있다. 화면은 멀쩡해 보였다.
    """
    import sys
    sys.path.insert(0, str(Registry().require("naver-blog").directory))
    from naver_blog.review import ready
    from core.webui import load_console

    built = load_console(Registry().require("naver-blog"), {})
    tile = next((item for item in built.stats if item.label == "올려도 되나"), None)
    if tile is None:
        return                      # 초안이 아직 없는 상태

    import importlib
    webui = importlib.import_module("webui_naver_blog") if \
        "webui_naver_blog" in sys.modules else None
    del webui

    blocked = tile.value == "아직"
    assert (tile.tone == "bad") is blocked, "타일 색과 문구가 어긋난다"


# ──────────────────────────────────── 화면에 이상한 것이 그려지지 않는가
#
# 테스트가 다 통과했는데 화면은 깨져 있던 적이 있다. 16번 비자 탭의 설명에
# 문장 하나를 목록으로 착각하고 `"\n".join(...)` 을 걸어, **한 글자씩** 세로로
# 늘어놓았다. 눈으로 보고서야 알았다. 같은 실수를 자동으로 잡는다.

@pytest.mark.parametrize("program_id", ALL)
def test_설명글이_한_글자씩_쪼개지지_않는다(program_id):
    """`"\\n".join(문자열)` 은 글자 사이에 줄바꿈을 넣는다.

    목록인 줄 알고 문자열에 join 을 걸면 화면에 글자가 세로로 쏟아진다.
    한 글자짜리 줄이 여러 개 이어지면 그 일이 난 것이다.
    """
    from core.webui import load_console

    built = load_console(Registry().require(program_id), {})
    for tab in built.tabs:
        for panel in tab.panels:
            for text in _texts(panel):
                runs = _single_char_runs(text)
                assert runs < 4, (
                    f"{program_id}/{tab.key}/{panel.key}: 한 글자짜리 줄이 "
                    f"{runs}개 이어집니다. 문자열에 join 을 걸었는지 보세요.\n"
                    f"{text[:120]}")


def _texts(panel) -> list[str]:
    out = [panel.intro, panel.note]
    out += list(panel.lines)
    out += [note.body for note in panel.notes]
    if panel.table is not None:
        out.append(panel.table.note)
    return [item for item in out if item]


def _single_char_runs(text: str) -> int:
    """한 글자짜리 줄이 연달아 몇 개나 나오는가."""
    best = run = 0
    for line in text.splitlines():
        stripped = line.strip().lstrip("-*• ").strip()
        if len(stripped) == 1:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best
