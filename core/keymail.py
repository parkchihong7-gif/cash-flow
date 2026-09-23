"""접속 안내 메일을 **관리자 화면과 같은 모습으로** 만든다.

왜 이 파일이 따로 있나
----------------------

예전에는 안내문을 글자 그대로 보냈다. 매뉴얼을 붙이려니 마크다운 기호(`##`,
`**`)가 메일에서 제목으로 안 보이고 `#` 이 그냥 찍혔다. 그래서 기호를 떼고
`────────` 선으로 칸을 나눴는데, 받는 분 화면에서는 그 선이 **영문 모를 줄**
로만 보였다. 지저분했다.

고친 방향은 하나다. **메일도 화면이다.** 화면에서 카드·표·제목으로 보이는
것을 메일에서도 그대로 보이게 만든다.

메일에서만 통하는 규칙
----------------------

* `<style>` 이나 바깥 CSS 파일은 **믿지 않는다.** 지우는 메일 앱이 있다.
  그래서 태그마다 `style="…"` 를 직접 박는다. 손으로 쓰면 빠뜨리므로
  :func:`_입히기` 가 한 번에 발라 준다.
* 색·글꼴·모서리 값은 대시보드 ``style.css`` 의 것을 그대로 옮겼다.
  한쪽만 바꾸면 화면과 메일이 달라 보인다.
* 글자판(plain text)도 **반드시 같이** 보낸다. HTML 을 못 읽는 메일 앱에서
  한쪽만 보내면 글이 통째로 안 보이거나 태그가 그대로 찍힌다.

무엇을 사람이 고치고 무엇이 자동인가
------------------------------------

====================  =========================================
접속키 안내 글        사람이 고친다 (고객마다 덧붙일 말이 다르다)
매뉴얼                자동으로 붙는다. 고칠 수 없다
====================  =========================================

매뉴얼을 고치게 두면 보내는 사람마다 내용이 달라지고, 나중에 "매뉴얼에 이렇게
쓰여 있었다" 는 말을 확인할 수가 없다. 매뉴얼은 프로그램에 든 파일 그대로만
나간다 — 고치려면 파일을 고쳐야 한다.
"""

from __future__ import annotations

import html as _html
import re

import markdown as _md

from core.keyauth import IssuedSet

__all__ = [
    "MANUAL_IN_HTML",
    "manual_markdown",
    "manual_html",
    "mail_html",
]

#: HTML 메일에 담을 매뉴얼 길이 한계.
#:
#: 지메일은 102KB 가 넘으면 뒤를 잘라 내고 «메시지 전체보기» 로 감춘다.
#: 매뉴얼이 12KB 안팎이니 이 값이면 통째로 들어가고도 한참 남는다.
#: 글자판 쪽 :data:`core.keyauth.MANUAL_IN_MAIL` 보다 넉넉한 이유는,
#: 꾸민 판이 이제 **본판**이고 글자판은 못 읽는 앱을 위한 대비이기 때문이다.
MANUAL_IN_HTML = 14000

# style.css 의 값 그대로. 한쪽만 고치면 화면과 메일이 달라 보인다.
_먹 = "#14161a"
_흐린먹 = "#545c6b"
_아주흐린먹 = "#8b93a1"
_선 = "#e4e7ec"
_바탕 = "#ffffff"
_연바탕 = "#f7f8fa"
_눌린바탕 = "#eef0f4"
_강조 = "#1f5eff"
_연강조 = "#eaf0ff"
# 글꼴 이름은 **작은따옴표**로 감싼다. 큰따옴표를 쓰면 `style="…"` 가 거기서
# 끊겨 그 태그의 꾸밈이 통째로 무시된다 — 화면에서는 멀쩡해 보이고 메일에서만
# 날것으로 보이는, 찾기 어려운 사고다.
_글꼴 = ("-apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Pretendard', "
         "'Malgun Gothic', 'Noto Sans KR', sans-serif")

# 글꼴을 문단·칸마다 **되풀이해서** 적는다. 물려받게 두면 아웃룩이 표
# 안에서 제 글꼴(Times New Roman)로 되돌려 버린다 — 표만 세리프로 보이는
# 흔한 사고다.
_ㄱ = f"font-family:{_글꼴};"

#: 태그마다 발라 줄 모양. 메일 앱이 바깥 CSS 를 지워도 살아남는다.
_모양 = {
    "h1": f"margin:0 0 14px;font-size:22px;line-height:1.35;color:{_먹};"
          "letter-spacing:-0.01em;",
    "h2": f"margin:26px 0 10px;font-size:18px;line-height:1.35;color:{_먹};"
          f"padding-bottom:8px;border-bottom:1px solid {_선};letter-spacing:-0.01em;",
    "h3": f"margin:20px 0 8px;font-size:15px;line-height:1.4;color:{_먹};",
    "h4": f"margin:16px 0 6px;font-size:14px;line-height:1.4;color:{_흐린먹};",
    "p": f"margin:0 0 12px;font-size:15px;line-height:1.75;color:{_먹};",
    "ul": "margin:0 0 12px;padding-left:22px;",
    "ol": "margin:0 0 12px;padding-left:22px;",
    "li": f"margin:0 0 6px;font-size:15px;line-height:1.75;color:{_먹};",
    "table": f"border-collapse:collapse;width:100%;margin:0 0 14px;"
             f"border:1px solid {_선};",
    "th": f"border:1px solid {_선};padding:8px 10px;background:{_연바탕};"
          f"font-size:13px;color:{_흐린먹};text-align:left;",
    "td": f"border:1px solid {_선};padding:8px 10px;font-size:14px;color:{_먹};",
    "code": f"background:{_눌린바탕};padding:1px 5px;border-radius:4px;font-size:13px;"
            "font-family:ui-monospace,Menlo,Consolas,monospace;",
    "pre": f"background:{_눌린바탕};padding:14px;border-radius:10px;font-size:13px;"
           "overflow-x:auto;font-family:ui-monospace,Menlo,Consolas,monospace;",
    "blockquote": f"margin:0 0 12px;padding:2px 0 2px 14px;"
                  f"border-left:3px solid {_선};color:{_흐린먹};",
    "h5": f"margin:14px 0 6px;font-size:13px;line-height:1.4;color:{_흐린먹};",
    "h6": f"margin:14px 0 6px;font-size:13px;line-height:1.4;color:{_아주흐린먹};",
    "hr": f"border:0;border-top:1px solid {_선};margin:22px 0;",
    "a": f"color:{_강조};text-decoration:underline;",
    "strong": f"color:{_먹};font-weight:700;",
}

_여는태그 = re.compile(r"<(" + "|".join(_모양) + r")(\s[^>]*)?>", re.I)


#: 매뉴얼 안에서만 쓰는 제목 모양.
#:
#: 매뉴얼의 `# 제목` 은 그 문서 안에서는 맨 위지만 메일에서는 **카드 하나**
#: 안에 든 글이다. 메일 제목과 같은 크기로 두면 어느 것이 본론인지 알 수
#: 없다. 제목을 h2 로 밀어내는 방법도 있었지만, 그러면 아래 단계가 줄줄이
#: 밀려 `####` 가 본문보다 작아진다. 크기만 바꾸는 편이 안전하다.
_매뉴얼_제목 = {
    "h1": f"margin:0 0 14px;padding-bottom:10px;border-bottom:2px solid {_선};"
          f"font-size:20px;line-height:1.35;color:{_먹};letter-spacing:-0.01em;",
}


def _입히기(html: str, 덮어쓰기: dict[str, str] | None = None) -> str:
    """태그마다 `style="…"` 를 박는다.

    이미 `style` 이 붙은 태그는 건드리지 않는다 — 우리가 손으로 쓴 것이
    덮이면 안 된다.
    """
    def 한번(m: re.Match) -> str:
        태그 = m.group(1).lower()
        나머지 = m.group(2) or ""
        if "style=" in 나머지.lower():
            return m.group(0)
        꾸밈 = (덮어쓰기 or {}).get(태그) or _모양[태그]
        return f'<{태그}{나머지} style="{_ㄱ}{꾸밈}">'

    return _여는태그.sub(한번, html)


def manual_markdown(program, for_admin: bool) -> str:
    """붙일 매뉴얼의 **원문**(마크다운).

    관리자에게는 관리자 매뉴얼, 고객에게는 사용 설명서. 반대로 보내면 그분
    화면에 없는 기능을 찾게 된다.
    """
    상대 = program.manuals.admin if for_admin else program.manuals.client
    if not 상대:
        return ""
    path = program.resolve(상대)
    if not path.is_file():
        return ""
    글 = path.read_text(encoding="utf-8").strip()
    if len(글) > MANUAL_IN_HTML:
        글 = (글[:MANUAL_IN_HTML].rstrip()
              + "\n\n*(줄임 — 나머지는 프로그램 안 매뉴얼에서 보세요)*")
    return 글


def manual_html(program, for_admin: bool) -> str:
    """매뉴얼을 **꾸민 판**으로. 화면의 매뉴얼과 같은 모습이 된다."""
    글 = manual_markdown(program, for_admin)
    if not 글:
        return ""
    return _입히기(_md.markdown(
        글, extensions=["tables", "fenced_code", "sane_lists"]),
        덮어쓰기=_매뉴얼_제목)


_주소 = re.compile(r"(https?://[^\s<>\"']+)")


def _글자를_문단으로(글: str) -> str:
    """사람이 친 글을 문단으로 바꾼다.

    빈 줄이 문단을 가르고, 한 줄 바꿈은 `<br>` 로 살린다. 주소는 눌리는
    링크가 된다 — 안내문의 본론이 «여기로 들어오세요» 이므로 이것이
    눌리지 않으면 메일이 제 일을 못 한다.
    """
    문단 = []
    for 덩이 in re.split(r"\n\s*\n", 글.strip()):
        안전 = _html.escape(덩이.strip())
        안전 = _주소.sub(
            lambda m: f'<a href="{m.group(1)}" style="{_모양["a"]}">{m.group(1)}</a>',
            안전)
        문단.append(f'<p style="{_모양["p"]}">' + 안전.replace("\n", "<br>") + "</p>")
    return "\n".join(문단)


def _카드(속: str, *, 연하게: bool = False) -> str:
    바탕 = _연바탕 if 연하게 else _바탕
    return (f'<div style="background:{바탕};border:1px solid {_선};border-radius:10px;'
            f'padding:20px 22px;margin:0 0 14px;">{속}</div>')


def mail_html(*, program_name: str, issued: IssuedSet, note: str,
              manual: str = "") -> str:
    """보낼 메일의 꾸민 판 전체.

    :param note: 사람이 고친 접속키 안내 글. 화면의 편집 칸에 있던 그대로.
    :param manual: :func:`manual_html` 이 만든 매뉴얼. 비면 매뉴얼 칸을 아예
        내지 않는다 — 빈 제목만 덩그러니 남는 것이 더 이상하다.
    """
    제목 = _html.escape(f"{program_name} 접속 안내")
    조각 = [
        f'<h1 style="{_모양["h1"]}">{제목}</h1>',
        _카드(_글자를_문단으로(note)),
    ]

    # 주소는 글 안에도 있지만 **버튼으로 한 번 더** 낸다. 글 속 링크는
    # 지나치기 쉽고, 받는 분이 할 일은 결국 이 버튼 하나를 누르는 것이다.
    if issued.service_url:
        주소 = _html.escape(issued.service_url, quote=True)
        조각.append(
            f'<div style="margin:0 0 22px;"><a href="{주소}" '
            f'style="display:inline-block;background:{_강조};color:#ffffff;'
            'font-size:15px;font-weight:700;text-decoration:none;'
            'padding:12px 24px;border-radius:10px;">프로그램 열기 →</a></div>')
    elif issued.for_admin:
        # **누를 버튼이 없는 것이 맞다.** 자기 서버에 세워 쓰는 상품이라,
        # 이 분이 설치를 마치기 전에는 열 주소가 세상에 없다. 여기에
        # 우리 주소를 넣으면 그분 고객의 글이 우리 서버에 쌓인다.
        조각.append(
            f'<div style="margin:0 0 22px;padding:14px 16px;border-radius:10px;'
            f'background:{_연강조};border:1px solid {_선};">'
            f'<div style="{_ㄱ}font-size:13px;font-weight:700;color:{_강조};'
            'margin:0 0 4px;">먼저 설치가 필요합니다</div>'
            f'<div style="{_ㄱ}font-size:13px;line-height:1.7;color:{_흐린먹};">'
            '아래 <b>설치 안내서</b>를 따라 사장님 서버에 한 번만 세우시면 됩니다. '
            '설치를 마치면 그 주소가 사장님 프로그램 주소가 됩니다.</div></div>')

    if manual:
        이름 = "관리자 매뉴얼" if issued.for_admin else "사용 설명서"
        조각.append(
            f'<div style="margin:30px 0 12px;font-size:12px;font-weight:700;'
            f'letter-spacing:.06em;color:{_아주흐린먹};">{이름}</div>')
        조각.append(_카드(manual))

    조각.append(
        f'<p style="margin:26px 0 0;font-size:12px;line-height:1.7;'
        f'color:{_아주흐린먹};">이 메일은 {_html.escape(program_name)} 관리자 화면에서 '
        '보냈습니다. 접속키는 다른 분과 나눠 쓰지 마세요 — '
        '같은 2차키로 다른 기기에서 들어오면 먼저 쓰던 기기가 잠깁니다.</p>')

    속 = "\n".join(조각)
    return (
        '<!doctype html><html lang="ko"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{제목}</title></head>"
        f'<body style="margin:0;padding:0;background:{_연바탕};">'
        f'<div style="margin:0;padding:24px 16px;background:{_연바탕};'
        f'font-family:{_글꼴};color:{_먹};line-height:1.65;word-break:keep-all;">'
        f'<div style="max-width:680px;margin:0 auto;">{속}</div>'
        "</div></body></html>")
