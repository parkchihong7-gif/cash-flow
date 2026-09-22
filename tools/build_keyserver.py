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
PARTS_DIR = ROOT / "server" / "나눠붙이기"

#: 나눠 붙이는 판 한 장의 크기 한계(바이트).
#:
#: 왜 나누나
#:   한 장짜리 판은 61KB 다. 그 정도면 복사·붙여넣기가 멀쩡히 되는 것이
#:   보통인데, **실제로 잘리는 일이 있었다.** 어디서 잘리는지는 붙이는
#:   사람 쪽 사정(브라우저·편집기·클립보드)이라 여기서 알 길이 없다.
#:   그래서 «얼마면 되나»를 맞히는 대신 **작게 잘라 여러 장**으로 낸다.
#:   앱스 스크립트는 `.gs` 파일 여러 장을 한 덩어리로 읽으므로, 나눠 붙여도
#:   돌아가는 것은 똑같다.
#:
#: **바이트**로 잰다. 글자 수로 재면 한글이 한 글자에 3바이트라서 실제로는
#: 세 배 가까이 큰 파일이 나온다 — 한 번 그렇게 재서 15,000 으로 잡은 것이
#: 19,000바이트짜리가 됐다.
PART_LIMIT = 12000

#: 파일 맨 끝에 두는 표. 붙여넣기가 잘렸는지 **눈으로** 알 수 있게 한다.
#: 잘린 파일은 어차피 문법이 깨져 "Unexpected end of input" 이 나는데,
#: 그 말만으로는 무엇을 하라는 건지 알 수가 없다.
TAIL_MARK = "// ⛳ 여기가 마지막 줄입니다. 이 줄이 안 보이면 붙여넣기가 잘린 것입니다."

PART_HEAD = """// ── 접속키 서버 · 나눠 붙이는 판 {no}번 / 전체 {all}장 ───────────────
//  [+] → 스크립트로 새 파일을 만들고 이름을 `{no}` 로 지은 뒤 통째로 붙이세요.
//  {all}장을 **전부** 붙이셔야 합니다. 차례는 상관없습니다.
//  맨 아래 `⛳ {no}/{all} 끝` 이 보이면 다 들어온 것입니다.
//  손으로 고치지 마세요 — python -m tools.build_keyserver
// ─────────────────────────────────────────────────────────────────

"""

HEAD = """// ═══════════════════════════════════════════════════════════════════
//  접속키 서버 — 구글 앱스 스크립트에 붙여 넣는 **한 장짜리** 판입니다.
//
//  ■ 붙여넣기 전에 꼭 보세요
//    이 파일은 {lines:,}줄입니다. 맨 아래에 ⛳ 표가 있습니다.
//    붙여 넣은 뒤 **맨 아래에 그 ⛳ 표가 보이는지** 확인하세요.
//    안 보이면 잘린 것이고, 그대로 저장하면
//      구문 오류: SyntaxError: Unexpected end of input
//    이 납니다.
//
//    브라우저 화면에서 Ctrl+A 로는 안 됩니다. 브라우저는 긴 글을 화면에
//    보이는 만큼만 그려 두어서, 스크롤한 데까지만 복사됩니다.
//    **파일로 내려받아 메모장에서 Ctrl+A → Ctrl+C 하세요.**
//    메모장은 안 보이는 부분까지 전부 복사합니다.
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


#: 화면 조각을 이어 붙이는 자리. `server/keyserver.gs` 의 표식과 짝이다.
SEAM = ("  // ⟦화면조각⟧ 이 줄과 아래 한 줄을 빌드가 바꿔 넣는다"
        " — tools/build_keyserver.py\n  return '';")


def html_chunks(text: str, limit: int) -> list[str]:
    """화면 HTML 을 `var ADMIN_HTML_n = …;` 여러 개로 자른다.

    **줄 사이에서만** 자른다. 역따옴표 글자 안이라도 줄바꿈 자리는 안전하다 —
    글자 하나를 반으로 가르는 일만 없으면 된다. 반대로 `\\n` 같은 이스케이프
    한가운데서 자르면 그 순간 글이 깨지는데, 줄 끝에서는 그런 일이 없다.
    """
    덩이, 이번, 크기 = [], [], 0
    for 줄 in text.split("\n"):
        잰것 = len(줄.encode()) + 1
        if 이번 and 크기 + 잰것 > limit:
            덩이.append("\n".join(이번))
            이번, 크기 = [], 0
        이번.append(줄)
        크기 += 잰것
    if 이번:
        덩이.append("\n".join(이번))
    return [f"var ADMIN_HTML_{n} = " + as_js_string(조각) + ";"
            for n, 조각 in enumerate(덩이, 1)]


def server_chunks(code: str) -> list[str]:
    """서버 코드를 **함수 사이에서** 자른다.

    맨 앞칸에 붙은 `}` 로 끝나는 것이 최상위 함수의 끝이다. 그 뒤에 맨 앞칸
    에서 시작하는 줄이 나오면 거기가 다음 덩이의 머리다. 함수 한가운데서
    자르면 그 조각 하나만으로는 문법이 깨지므로, 이 자리만 쓴다.
    """
    줄 = code.split("\n")
    덩이, 이번, 닫힌뒤 = [], [], False
    for l in 줄:
        머리다 = (닫힌뒤 and l[:1] not in ("", " ", "\t", ")", "}", "]", ";"))
        if 머리다 and 이번:
            덩이.append("\n".join(이번).rstrip())
            이번 = []
        이번.append(l)
        if l.strip():
            닫힌뒤 = l == "}"
    if 이번:
        덩이.append("\n".join(이번).rstrip())
    return [d for d in 덩이 if d.strip()]


def pieces() -> list[str]:
    """붙여 넣을 조각 전부. 한 장짜리 판도, 나눠 붙이는 판도 여기서 나온다.

    한 군데서 만들어야 **둘이 같은 코드**임이 보장된다. 따로 만들면 언젠가
    한쪽만 고쳐진다.
    """
    server = SERVER.read_text(encoding="utf-8")
    # 노드 시험용 꼬리는 구글에서 뜻이 없다. 넣어도 해롭진 않지만 뺀다.
    server = re.sub(
        r"\n// 노드에서 시험할 때만 쓴다\.[\s\S]*$", "\n", server)

    화면 = html_chunks(page_source(), PART_LIMIT)
    if SEAM not in server:
        raise SystemExit("keyserver.gs 에서 ⟦화면조각⟧ 표식을 못 찾았습니다")
    이음 = "  return " + " + ".join(
        f"ADMIN_HTML_{n}" for n in range(1, len(화면) + 1)) + ";"
    server = server.replace(SEAM, 이음)

    return 화면 + server_chunks(strip_js(server))


def build() -> str:
    body = "\n\n".join(pieces()) + "\n\n" + TAIL_MARK + "\n"
    # 머리말에 줄 수를 적는다. 머리말 자체도 세어야 해서 두 번 만든다.
    rough = HEAD.format(lines=0) + body
    return HEAD.format(lines=len(rough.splitlines())) + body


def build_parts(limit: int = PART_LIMIT) -> list[str]:
    """나눠 붙이는 판. 조각을 **차례대로** 담되 한 장이 한계를 넘지 않게.

    차례를 지키는 것이 중요하다. 조각을 섞으면 함수 한가운데가 다른 장으로
    가서, 모아 놓아도 문법이 안 맞는다.
    """
    # 머리말·꼬리말도 한 장에 들어가는 글이다. 그만큼 미리 빼 두지 않으면
    # 한계를 지켰다고 생각한 장이 실제로는 넘친다.
    여유 = limit - len(PART_HEAD.format(no=9, all=9).encode()) - 80
    장, 이번, 크기 = [], [], 0
    for 조각 in pieces():
        잰것 = len(조각.encode()) + 2
        if 이번 and 크기 + 잰것 > 여유:
            장.append("\n\n".join(이번))
            이번, 크기 = [], 0
        이번.append(조각)
        크기 += 잰것
    if 이번:
        장.append("\n\n".join(이번))

    모두 = len(장)
    return [PART_HEAD.format(no=n, all=모두) + 속
            + f"\n\n// ⛳ {n}/{모두} 끝 — 이 줄이 안 보이면 붙여넣기가 잘린 것입니다.\n"
            for n, 속 in enumerate(장, 1)]


def main() -> None:
    OUT.write_text(build(), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)} 에 {OUT.stat().st_size:,}바이트를 적었습니다.")

    PARTS_DIR.mkdir(exist_ok=True)
    for 낡은 in PARTS_DIR.glob("*.gs"):
        낡은.unlink()
    장 = build_parts()
    for n, 속 in enumerate(장, 1):
        (PARTS_DIR / f"{n}.gs").write_text(속, encoding="utf-8")
    큰것 = max(len(속.encode()) for 속 in 장)
    print(f"{PARTS_DIR.relative_to(ROOT)}/ 에 {len(장)}장을 적었습니다 "
          f"(가장 큰 장 {큰것:,}바이트).")
    print()
    print("한 번에 붙는다면 묶음 파일 하나만 쓰시면 됩니다.")
    print("잘린다면 나눠붙이기 폴더의 1.gs 부터 차례대로 각각 다른 파일에 붙이세요.")


if __name__ == "__main__":
    main()
