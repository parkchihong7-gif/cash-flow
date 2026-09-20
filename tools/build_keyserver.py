"""붙여 넣을 앱스 스크립트 파일 **한 장**을 만든다.

왜
    사장님이 구글 편집기에 파일을 두 개 만들어 각각 붙여 넣으셔야 하면,
    그것부터가 설치가 아니라 숙제다. 서버(`keyserver.gs`)와 관리자
    화면(`web/admin.html`)을 한 파일로 묶어, **한 번 복사 → 한 번 붙여넣기**
    로 끝나게 한다.

    묶인 파일: `server/keyserver.bundle.gs`

    손으로 고치지 마세요. 서버나 화면을 고치신 뒤 이것을 다시 돌리면 됩니다.

        python -m tools.build_keyserver
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server" / "keyserver.gs"
PAGE = ROOT / "web" / "admin.html"
PROGRAMS = ROOT / "web" / "programs.js"
OUT = ROOT / "server" / "keyserver.bundle.gs"

#: 파일 맨 끝에 두는 표. 붙여넣기가 잘렸는지 **눈으로** 알 수 있게 한다.
#: 잘린 파일은 어차피 문법이 깨져 "Unexpected end of input" 이 나는데,
#: 그 말만으로는 무엇을 하라는 건지 알 수가 없다.
TAIL_MARK = "// ⛳ 여기가 마지막 줄입니다. 이 줄이 안 보이면 붙여넣기가 잘린 것입니다."

HEAD = """// ═══════════════════════════════════════════════════════════════════
//  접속키 서버 — 구글 앱스 스크립트에 붙여 넣는 **한 장짜리** 판입니다.
//
//  ■ 붙여넣기 전에 꼭 보세요
//    이 파일은 {lines:,}줄입니다. 맨 아래에 ⛳ 표가 있습니다.
//    붙여 넣은 뒤 **맨 아래에 그 ⛳ 표가 보이는지** 확인하세요.
//    안 보이면 잘린 것이고, 그대로 저장하면
//      구문 오류: SyntaxError: Unexpected end of input
//    이 납니다. 그때는 GitHub 화면에서 Ctrl+A 하지 마시고
//    파일 위쪽의 [Raw] 또는 복사 아이콘을 쓰세요.
//    (GitHub 은 긴 파일을 보이는 만큼만 그려서, Ctrl+A 가 잘립니다.)
//
//  이 파일은 만들어진 것입니다. 손으로 고치지 마세요.
//    읽기 좋은 원본: server/keyserver.gs + web/admin.html
//    다시 만들기   : python -m tools.build_keyserver
//
//  설치 (세 단계)
//    1. script.google.com → 새 프로젝트 → 이 파일을 통째로 붙여넣기
//    2. 함수 고르는 칸에서 `처음설정` 을 고르고 [실행]
//       → 장부 시트·서명값·관리자 비밀번호를 만들어 알려 줍니다
//    3. [배포] → [새 배포] → 웹 앱
//       실행: 나 / 권한: 모든 사용자
//       → 나온 주소를 열면 관리자 화면이 바로 뜹니다
// ═══════════════════════════════════════════════════════════════════

"""


def strip_js(src: str) -> str:
    """주석과 빈 줄을 걷어낸다. 문자열 안은 건드리지 않는다.

    붙여 넣을 양이 줄면 잘릴 일도 준다. 읽기 좋은 원본은 그대로 두고,
    **만들어지는 판만** 줄인다.
    """
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'`":                      # 문자열 안의 // 나 /* 는 주석이 아니다
            quote, j = c, i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == quote:
                    j += 1
                    break
                j += 1
            out.append(src[i:j])
            i = j
            continue
        if src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if src.startswith("//", i):
            end = src.find("\n", i)
            i = n if end < 0 else end
            continue
        out.append(c)
        i += 1
    text = "".join(out)
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())


def strip_html(src: str) -> str:
    """주석과 빈 줄만 걷어낸다. 눌러야 하는 것은 하나도 안 건드린다."""
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    return "\n".join(line for line in (x.rstrip() for x in src.splitlines()) if line.strip())


def page_source() -> str:
    """관리자 화면 HTML. `programs.js` 는 안으로 끌어넣는다.

    앱스 스크립트가 내어 주는 화면은 `<script src="programs.js">` 같은
    옆 파일을 못 부른다. 그래서 그 자리에 내용을 그대로 넣는다.
    """
    html = PAGE.read_text(encoding="utf-8")
    programs = PROGRAMS.read_text(encoding="utf-8")
    inlined = re.sub(
        r'<script src="programs\.js"></script>',
        "<script>\n" + strip_js(programs) + "\n</script>",
        html,
    )
    if inlined == html:
        raise SystemExit("admin.html 에서 programs.js 를 부르는 줄을 못 찾았습니다")
    return strip_html(inlined)


def as_js_string(text: str) -> str:
    """HTML 을 자바스크립트 글자 하나로 바꾼다.

    작은따옴표 대신 **역따옴표**를 쓴다. HTML 안에 따옴표가 많아 그쪽이
    덜 깨진다. 역따옴표와 `${` 만 피해 주면 된다.
    """
    safe = (text.replace("\\", "\\\\")
                .replace("`", "\\`")
                .replace("${", "\\${"))
    return "`" + safe + "`"


def build() -> str:
    server = SERVER.read_text(encoding="utf-8")
    # 노드 시험용 꼬리는 구글에서 뜻이 없다. 넣어도 해롭진 않지만 뺀다.
    server = re.sub(
        r"\n// 노드에서 시험할 때만 쓴다\.[\s\S]*$", "\n", server)
    block = ("var ADMIN_HTML = " + as_js_string(page_source()) + ";\n\n")
    body = block + strip_js(server) + "\n\n" + TAIL_MARK + "\n"
    # 머리말에 줄 수를 적는다. 머리말 자체도 세어야 해서 두 번 만든다.
    rough = HEAD.format(lines=0) + body
    return HEAD.format(lines=len(rough.splitlines())) + body


def main() -> None:
    OUT.write_text(build(), encoding="utf-8")
    size = OUT.stat().st_size
    print(f"{OUT.relative_to(ROOT)} 에 {size:,}바이트를 적었습니다.")
    print("구글 편집기에 이 파일 하나만 붙여 넣으시면 됩니다.")


if __name__ == "__main__":
    main()
