"""대시보드 화면을 통째로 떠서 **HTML 파일 묶음**으로 만든다.

    python -m dashboard.snapshot                 # dashboard-snapshot/ 에 만든다
    python -m dashboard.snapshot --out /tmp/snap
    python -m dashboard.snapshot --zip           # 압축까지

왜 필요한가.
    서버를 띄우지 않고도 **메뉴·매뉴얼·설정값을 그대로 볼 수** 있어야 하기
    때문이다. 노트북을 안 켜 둔 날에도, 파이썬이 없는 사람에게도, 크몽 문의에
    "화면이 어떻게 생겼나요" 하는 물음에도 파일 하나를 열어 보여 주면 된다.

무엇이 되고 무엇이 안 되는가.
    된다   화면 넘나들기, 매뉴얼 읽기, 설정값 보기, FAQ 읽기
    안 된다 저장·실행·검색·로그인 — **서버가 없기 때문이다.**

    그래서 모든 화면 위에 그렇다는 띠를 붙이고, 누르면 아무 일도 안 일어나는
    버튼은 아예 못 누르게 막는다. 눌러 보고 고장난 줄 아는 편이 더 나쁘다.

비밀값은 실리지 않는다.
    설정 화면은 토큰·키를 '설정됨/비어 있음' 으로만 보여 준다(`core/overview.py`).
    다만 **고객 이름·연락처는 DB 에 있는 그대로 찍힌다.** 그래서 기본값은
    빈 임시 DB 로 뜨고, 실제 DB 로 뜨려면 `--db` 를 직접 줘야 한다.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import base64
import hashlib
import secrets
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

from fastapi.testclient import TestClient

from core import auth
from core.db import Database
from core.registry import Registry
from core.runner import RunError, run_program
from dashboard.app import create_app

__all__ = ["Snapshot", "build", "PAGE_DIR", "MAX_PAGES"]

BASE_DIR = Path(__file__).resolve().parent

#: 화면 파일을 모아 두는 하위 폴더. 표지는 그 위에 둔다.
PAGE_DIR = "app"

#: 안전장치. 링크를 잘못 따라가 폭주하는 일을 막는다.
#: 떠 올 화면 수의 상한. 링크를 따라가다 보면 끝이 없을 수 있어 막아 둔다.
#: 상품마다 운영 콘솔 탭이 열 개 남짓이고 모드가 둘이라, 16종이면 콘솔만
#: 400장이 넘는다. 여기에 대시보드 화면을 더해 잡았다. 이 값이 모자라면
#: 링크는 있는데 안 열리는 화면이 생긴다 — 만든 사람은 모르고 지나간다.
MAX_PAGES = 900

#: 이 접두어로 시작하는 주소만 따라간다.
FOLLOW_PREFIXES = (
    "/", "/programs/", "/manual", "/members", "/settings", "/config",
    "/rules", "/revenue", "/schedule", "/access", "/runs", "/search", "/preview",
    "/keys",
    # 상품별 운영 콘솔. 탭마다 주소가 따로 있어, 씨앗으로 두 모드만 넣어도
    # 왼쪽 메뉴를 따라가며 나머지 탭이 전부 걸린다.
    "/apps/",
)

#: 따라가지 않는 주소. 스냅샷에서 뜻이 없거나 서버가 있어야만 되는 것들.
SKIP_PATHS = {"/logout", "/reload", "/healthz", "/favicon.ico"}

#: 암호에서 열쇠를 만들 때 몇 번 돌릴지. 느릴수록 무차별 대입이 비싸진다.
PBKDF2_ROUNDS = 200_000

LINK = re.compile(r'(href|src|action)="([^"]*)"')

BANNER = """<div class="snapshot-bar">
  <strong>정적 스냅샷</strong>
  화면만 떠 온 것이라 <b>저장·실행·검색·로그인은 되지 않습니다.</b>
  <span>{stamp}</span>
</div>"""

FREEZE = """<style>
.snapshot-bar {
  position: sticky; top: 0; z-index: 99;
  background: #1b2735; color: #f2f6fa;
  font: 13px/1.5 "IBM Plex Sans KR", "Apple SD Gothic Neo", system-ui, sans-serif;
  padding: 7px 14px; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap;
}
.snapshot-bar strong { color: #e0a44a; }
.snapshot-bar b { font-weight: 500; }
.snapshot-bar span { margin-left: auto; opacity: .6; font-size: 12px; }
.snapshot-dead { opacity: .45; cursor: not-allowed; }
/* 아래로 내려가면 위쪽 안내가 안 보인다. 버튼마다 짧게 한 번 더 말한다.
   문단을 폼마다 되풀이하면 그건 안내가 아니라 소음이다. */
.snapshot-dead::after { content: " · 사진"; font-size: .85em; opacity: .8; }
/* 화면마다 **한 번만** 붙는다. 맨 위, 내용이 시작되기 전에. */
.snapshot-nope {
  margin: 0 0 16px; padding: 10px 13px; border-radius: 7px;
  background: #3a2a12; border: 1px solid #6b4e1f; color: #f0d9a8;
  font: 13px/1.55 "Apple SD Gothic Neo", system-ui, sans-serif;
}
.snapshot-nope b { color: #ffc96b; }
.snapshot-nope code {
  background: #241a0b; padding: 1px 5px; border-radius: 4px; font-size: 12px;
}
</style>
<script>
// 서버가 없으니 보내 봐야 소용없다. 눌러 보고 고장난 줄 아는 편이 더 나쁘다.
document.addEventListener("submit", function (event) {
  event.preventDefault();
  alert("정적 스냅샷입니다. 저장·실행·검색은 서버를 띄워야 됩니다.\\n\\n  python -m dashboard");
});
document.addEventListener("DOMContentLoaded", function () {
  // 표지 안에서 볼 때는 위쪽 머리말이 이미 같은 말을 하고 있다. 두 번 하지 않는다.
  if (window.parent !== window) {
    var bar = document.querySelector(".snapshot-bar");
    if (bar) { bar.remove(); }
  }
  document.querySelectorAll("form button, form input[type=submit]").forEach(function (el) {
    el.classList.add("snapshot-dead");
    el.title = "정적 스냅샷에서는 눌러도 아무 일도 일어나지 않습니다";
  });
  // 흐릿한 버튼만으로는 모른다. 키 발급 화면은 진짜처럼 보여서, 눌러 놓고
  // 프로그램이 고장난 줄 알게 된다. 누르기 전에 화면 맨 위에서 한 번 말한다.
  //
  // 폼마다 붙이면 한 화면에 같은 문단이 서너 번 나와 읽히지 않는다.
  // 아래쪽 버튼은 `.snapshot-dead::after` 가 짧게 맡는다.
  var 폼 = document.querySelector("form button, form input[type=submit]");
  if (폼 && !document.querySelector(".snapshot-nope")) {
    var note = document.createElement("p");
    note.className = "snapshot-nope";
    note.innerHTML =
      "<b>이 화면은 사진입니다.</b> 눌러서 돌아다니실 수는 있지만 " +
      "저장\u00B7발급\u00B7실행은 되지 않습니다. 버튼 옆의 " +
      "<b>\u00B7 사진</b> 표시가 그 뜻입니다.<br>" +
      "실제로 하시는 곳 \u2014 " +
      "<b>키 발급\u00B7정지</b>는 <b>웹 관리자 화면</b>(구글 앱스 스크립트 주소), " +
      "<b>저장\u00B7실행</b>은 집 컴퓨터의 " +
      "<code>tools\\\\home\\\\대시보드_열기.bat</code> 입니다.";
    var 자리 = document.querySelector("main") || document.body;
    자리.insertBefore(note, 자리.firstChild);
  }
});
// 한 파일로 묶은 판에는 주소가 없다. 어느 화면으로 가고 싶은지 표지에 알려 준다.
document.addEventListener("click", function (event) {
  var link = event.target.closest ? event.target.closest("a[data-page]") : null;
  if (!link) { return; }
  event.preventDefault();
  parent.postMessage({ snapshotPage: link.dataset.page }, "*");
});
</script>"""


def local_name(url: str) -> str:
    """주소 하나를 파일 이름 하나로 바꾼다.

    `/programs/n8n-gen/edit` → `programs-n8n-gen-edit.html`
    질의문(`?path=...`)이 붙으면 뒤에 짧은 지문을 단다. 한글 경로가 그대로
    파일 이름이 되면 운영체제마다 다르게 저장되기 때문이다.
    """
    split = urlsplit(url)
    path = unquote(split.path).strip("/")
    stem = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", path).strip("-") or "index"
    if split.query:
        digest = hashlib.sha1(split.query.encode("utf-8")).hexdigest()[:6]
        stem = f"{stem}-{digest}"
    return f"{stem}.html"


def should_follow(url: str) -> bool:
    split = urlsplit(url)
    if split.scheme or split.netloc:          # 바깥 주소는 그대로 둔다
        return False
    path = split.path
    if not path.startswith("/") or path in SKIP_PATHS:
        return False
    if path.startswith("/static/"):
        return False
    return True


@dataclass
class Snapshot:
    """만들어진 결과. 테스트와 CLI 가 같은 것을 본다."""

    out_dir: Path
    pages: dict[str, str] = field(default_factory=dict)   # url -> 파일명
    failures: list[tuple[str, int]] = field(default_factory=list)
    dangling: set[str] = field(default_factory=set)
    single: Path | None = None          # 한 파일로 묶은 판 (만들었을 때만)

    @property
    def index(self) -> Path:
        return self.out_dir / "index.html"

    @property
    def count(self) -> int:
        return len(self.pages)


def _seeds(registry: Registry) -> list[str]:
    """반드시 담을 화면. 링크를 따라가면 대부분 걸리지만 순서를 고정한다."""
    urls = ["/", "/config", "/rules", "/access", "/schedule", "/revenue", "/runs",
            "/members", "/keys",
            "/settings",
            "/manual",
            "/manual/admin", "/manual/client"]
    for program in registry.programs:
        urls += [
            f"/programs/{program.id}",
            f"/programs/{program.id}/edit",
            f"/programs/{program.id}/test",
            f"/programs/{program.id}/members",
        ]
        if program.manuals.admin:
            urls.append(f"/programs/{program.id}/manual/admin")
        if program.manuals.client:
            urls.append(f"/programs/{program.id}/manual/client")
        # 두 모드의 첫 화면만 넣는다. 탭은 사이드바 링크를 따라가며 걸린다.
        urls += [f"/apps/{program.id}/admin", f"/apps/{program.id}/client"]
    return urls


def _rewrite(body: str, pages: dict[str, str], dangling: set[str],
             single: bool = False) -> str:
    """페이지 안의 주소를 옆에 있는 파일 이름으로 바꾼다.

    한 파일로 묶는 판(`single`)에서는 열 파일이 없다. 주소 대신 화면 이름만
    붙여 두고, 누르면 표지가 대신 바꿔 끼운다.
    """

    def swap(match: re.Match) -> str:
        attr, url = match.group(1), match.group(2)
        if attr == "action":
            return match.group(0)      # 보내지 못하게 막아 두었으니 그대로 둔다
        if url.startswith("/static/"):
            return f'{attr}="{url[len("/static/"):]}"'
        if not should_follow(url):
            return match.group(0)
        if url in pages:
            if single and attr == "href":
                return f'href="#" data-page="{pages[url]}"'
            return f'{attr}="{pages[url]}"'
        # 못 떠 온 화면이다. 눌러도 파일이 없으니 제자리에 둔다.
        dangling.add(url)
        return f'{attr}="#" data-missing="{url}" title="스냅샷에 없는 화면입니다"'

    return LINK.sub(swap, body)


def _cover(snapshot: Snapshot, registry: Registry, stamp: str,
           payload: str = "", locked: bool = False) -> str:
    """표지. 프로그램 목록에서 칩을 만들어 새 상품이 저절로 들어오게 한다."""
    def chip(url: str, label: str, num: str = "", current: bool = False) -> str:
        name = snapshot.pages.get(url)
        if not name:
            return ""
        if not payload:
            name = f"{PAGE_DIR}/{name}"
        inner = (f'<span class="n">{num}</span>' if num else "") + label
        mark = ' aria-current="true"' if current else ""
        return f'    <button class="chip" data-src="{name}"{mark}>{inner}</button>\n'

    chips = '    <span class="group-label">시작</span>\n'
    chips += chip("/login", "접속 화면")
    chips += chip("/", "홈", current=True)
    chips += chip("/access", "권한·환경")
    chips += chip("/schedule", "정기 실행")
    chips += chip("/config", "설정 한눈에")
    chips += chip("/rules", "규정 점검")

    chips += '\n    <span class="divider" role="presentation"></span>\n'
    chips += '    <span class="group-label">프로그램</span>\n'
    for program in registry.programs:
        chips += chip(f"/programs/{program.id}", program.name, str(program.number))

    chips += '\n    <span class="divider" role="presentation"></span>\n'
    chips += '    <span class="group-label">관리</span>\n'
    chips += chip("/revenue", "수입 현황")
    chips += chip("/runs", "실행 이력")
    chips += chip("/members", "회원관리")
    chips += chip("/settings", "기타 설정")
    chips += chip("/manual/admin", "관리자 매뉴얼")
    chips += chip("/manual/client", "고객 매뉴얼")

    home = snapshot.pages.get("/", "index.html")
    template = (BASE_DIR / "snapshot_cover.html").read_text(encoding="utf-8")
    page = (template
            .replace("{{CHIPS}}", chips.rstrip())
            .replace("{{COUNT}}", str(snapshot.count))
            .replace("{{STAMP}}", stamp))
    # 잠금 화면은 **HTML 에서 이미 보이는 채로** 나간다. 자바스크립트가
    # `hidden` 을 벗기는 구조였는데, 스크립트가 안 돌면 영영 안 보인다.
    page = page.replace("{{GATE_HIDDEN}}", "" if locked else " hidden")

    if payload:
        page = (page
                .replace("{{HOME_SRC}}", "about:blank")
                .replace("{{HOME}}", home)
                .replace("{{FALLBACK}}",
                         "화면이 안 보이면 브라우저를 최신 것으로 열어 보세요."))

        # 쪽지는 </body> **안**에 들어가야 한다. 뒤에 붙이면 문서가 한 번
        # 닫힌 뒤에 태그가 더 나와, 브라우저가 고쳐 읽느라 자리를 옮긴다.
        closing = "\n</body>\n</html>\n"
        if page.rstrip().endswith("</html>"):
            page = page.rstrip()[: -len(closing.strip())].rstrip()
        page = page.rstrip() + "\n\n" + payload + closing
    else:
        page = (page
                .replace("{{HOME_SRC}}", f"{PAGE_DIR}/{home}")
                .replace("{{HOME}}", f"{PAGE_DIR}/{home}")
                .replace("{{FALLBACK}}",
                         f'화면이 안 보이면 <a href="{PAGE_DIR}/{home}">여기를 눌러 직접 여세요</a>.'))
    return page


def demo_runs(app) -> list[str]:
    """모의 실행을 한 번씩 돌려 '실행 이력' 과 '산출물' 화면을 채운다.

    지어낸 기록을 넣지 않는다. **실제로 돌린 결과**만 담는다.
    모의 실행은 Claude 를 부르지 않아 비용이 들지 않는다.
    """
    db: Database = app.state.db
    done: list[str] = []
    for program in app.state.registry.programs:
        if not (program.run and program.run.dry_run_command):
            continue
        try:
            run_program(program, db, mode="dry")
            done.append(program.id)
        except (RunError, OSError):
            # 한 프로그램이 안 돌아도 스냅샷은 만든다. 화면을 보는 것이 목적이다.
            continue
    return done


def _payload(raw: dict[str, str], pages: dict[str, str], dangling: set[str],
             banner: str, css: str, lock: str = "") -> str:
    """화면 전부를 표지 안에 넣을 쪽지 하나로 만든다.

    Args:
        lock: 넣으면 **자물쇠를 건다.** 이 글자를 모르면 못 읽는다.
    """
    text = _bundle_text(raw, pages, dangling, banner, css)

    if lock:
        return _locked_payload(text, lock)

    # </script> 가 글자 그대로 들어가면 쪽지가 거기서 끊긴다.
    return ('<script type="application/json" id="pages">'
            + text.replace("</", "<\\/") + "</script>")


def _bundle_text(raw: dict[str, str], pages: dict[str, str], dangling: set[str],
                 banner: str, css: str) -> str:
    """화면 전부를 글자 하나로 묶는다."""
    bundle = {}
    for url, body in raw.items():
        body = _rewrite(body, pages, dangling, single=True)
        body = body.replace("<body>", "<body>\n" + banner, 1)
        body = body.replace("</body>", FREEZE + "\n</body>", 1)
        bundle[pages[url]] = body
    bundle["__css__"] = css
    return json.dumps(bundle, ensure_ascii=False)


def _locked_blob(text: str, password: str) -> tuple[dict, bytes]:
    """덮은 내용과, 그것을 여는 데 필요한 정보를 따로 돌려준다.

    파일 하나에 다 넣으면 1.5MB 짜리 HTML 이 되고, 브라우저가 그걸 다 읽기
    전에는 **글자 하나 안 그린다.** 뭐가 잘못되면 하얀 화면으로 멎어 있고
    콘솔에는 아무것도 안 남는다. 실제로 그 일이 났다.

    그래서 웹에 올릴 때는 덮은 덩어리를 옆 파일로 뺀다. 화면이 먼저 뜨고,
    받는 동안 몇 퍼센트인지 보이고, 실패하면 왜인지 말할 수 있다.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    packed = gzip.compress(text.encode("utf-8"), compresslevel=9)
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                              PBKDF2_ROUNDS, dklen=32)
    sealed = AESGCM(key).encrypt(nonce, packed, None)

    meta = {
        "salt": base64.b64encode(salt).decode(),
        "iv": base64.b64encode(nonce).decode(),
        "rounds": PBKDF2_ROUNDS,
        "gzip": True,
        "bytes": len(sealed),
    }
    return meta, sealed


def _locked_payload(text: str, password: str) -> str:
    """화면을 **정말로 잠근다.**

    자바스크립트로 "암호가 맞나" 를 물어보는 흉내는 잠금이 아니다. 소스를
    열면 내용이 그대로 있다. 그래서 내용 자체를 AES-GCM 으로 덮는다.
    암호를 모르면 손에 쥐는 것은 **알아볼 수 없는 바이트 덩어리**다.

    암호는 어디에도 저장하지 않는다. 브라우저가 입력받은 글자로 열쇠를 다시
    만들어 풀어 본다. 틀리면 복호화가 실패하고, 그게 곧 '틀렸다' 는 뜻이다.

    한계는 분명히 해 둔다. **암호가 약하면 이 잠금도 약하다.** 파일을 받아
    두고 느긋하게 대입해 볼 수 있어서다. 그래서 PBKDF2 를 20만 번 돌려
    한 번 시도하는 값을 비싸게 만들어 두었지만, 짧은 암호는 여전히 위험하다.

    덮기 전에 **눌러 둔다.** 덮고 나면 무작위에 가까워져 아무리 눌러도 안
    줄고, 주고받을 때도 안 줄어든다. 눌러 두면 13MB 가 2MB 가 된다 —
    집 인터넷으로 받는 시간이 여섯 배 짧아진다.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    packed = gzip.compress(text.encode("utf-8"), compresslevel=9)
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                              PBKDF2_ROUNDS, dklen=32)
    sealed = AESGCM(key).encrypt(nonce, packed, None)

    blob = json.dumps({
        "salt": base64.b64encode(salt).decode(),
        "iv": base64.b64encode(nonce).decode(),
        "data": base64.b64encode(sealed).decode(),
        "rounds": PBKDF2_ROUNDS,
        "gzip": True,
    })
    return f'<script type="application/json" id="locked">{blob}</script>'


def build(out_dir: str | Path, db_path: str | Path | None = None,
          products_dir: Path | None = None, stamp: str = "",
          demo: bool = False, single: str = "", lock: str = "",
          split: bool = False) -> Snapshot:
    """화면을 떠서 `out_dir` 아래에 static HTML 묶음을 만든다.

    Args:
        out_dir: 결과 폴더. 있으면 `app/` 아래를 갈아엎는다.
        db_path: 쓸 DB. 비우면 **빈 임시 DB** 를 만든다(고객 정보가 안 찍힌다).
        products_dir: 프로그램 폴더. 테스트에서만 바꾼다.
        stamp: 표지에 적을 날짜 문자열.
        demo: True 면 프로그램마다 모의 실행을 한 번씩 돌려 실행 이력과
            산출물 화면까지 채운다. 몇 분 걸린다.
        single: 비어 있지 않으면 **화면 전부를 담은 HTML 파일 하나**를
            그 이름으로도 만든다. 메일로 보내거나 카톡으로 넘기기 좋다.
    """
    out_dir = Path(out_dir)
    page_dir = out_dir / PAGE_DIR
    if page_dir.exists():
        shutil.rmtree(page_dir)
    page_dir.mkdir(parents=True, exist_ok=True)

    temp_dir: tempfile.TemporaryDirectory | None = None
    if db_path is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="snapshot-db-")
        db_path = Path(temp_dir.name) / "snapshot.db"

    try:
        app = create_app(db_path, products_dir)
        registry: Registry = app.state.registry
        snapshot = Snapshot(out_dir=out_dir)

        if demo:
            done = demo_runs(app)
            print(f"모의 실행 {len(done)}건 — 실행 이력과 산출물 화면까지 담습니다")

        # 1) 잠긴 화면 — 코드를 넣기 전 모습과 틀렸을 때 모습
        locked = TestClient(app, follow_redirects=False)
        raw: dict[str, str] = {}
        raw["/login"] = locked.get("/login").text
        wrong = locked.post("/login", data={"code": "틀린코드"})
        raw["/login-error"] = wrong.text

        # 2) 코드를 넣고 나머지를 훑는다
        client = TestClient(app)
        client.post("/login", data={"code": auth.access_code()})

        queue = list(_seeds(registry))
        seen: set[str] = {"/login", "/login-error"}
        while queue and len(raw) < MAX_PAGES:
            url = queue.pop(0)
            if url in seen or not should_follow(url):
                continue
            seen.add(url)
            response = client.get(url)
            if response.status_code != 200 or "html" not in \
                    response.headers.get("content-type", ""):
                snapshot.failures.append((url, response.status_code))
                continue
            raw[url] = response.text
            for attr, found in LINK.findall(response.text):
                # form 의 action 은 따라가지 않는다. POST 전용이라 GET 하면
                # 405 가 나고, 스냅샷에서는 어차피 보내지 못하게 막는다.
                if attr == "href" and should_follow(found) and found not in seen:
                    queue.append(found)

        snapshot.pages = {url: local_name(url) for url in raw}
        snapshot.pages["/login-error"] = "login-error.html"

        banner = BANNER.format(stamp=stamp or "")
        for url, body in raw.items():
            body = _rewrite(body, snapshot.pages, snapshot.dangling)
            body = body.replace("<body>", "<body>\n" + banner, 1)
            body = body.replace("</body>", FREEZE + "\n</body>", 1)
            (page_dir / snapshot.pages[url]).write_text(body, encoding="utf-8")

        css = (BASE_DIR / "static" / "style.css").read_text(encoding="utf-8")
        shutil.copy(BASE_DIR / "static" / "style.css", page_dir / "style.css")
        snapshot.index.write_text(_cover(snapshot, registry, stamp), encoding="utf-8")

        if single:
            snapshot.single = Path(single)
            snapshot.single.parent.mkdir(parents=True, exist_ok=True)

            if lock and split:
                # 덮은 덩어리를 옆 파일로 뺀다. 화면이 먼저 뜬다.
                text = _bundle_text(raw, snapshot.pages, snapshot.dangling,
                                    banner, css)
                meta, sealed = _locked_blob(text, lock)
                data_name = "data.bin"
                (snapshot.single.parent / data_name).write_bytes(sealed)
                meta["src"] = data_name
                payload = ('<script type="application/json" id="locked">'
                           + json.dumps(meta) + "</script>")
            else:
                payload = _payload(raw, snapshot.pages, snapshot.dangling, banner,
                                   css, lock=lock)
            snapshot.single.write_text(
                _cover(snapshot, registry, stamp, payload=payload,
                       locked=bool(lock)), encoding="utf-8")
        return snapshot
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dashboard.snapshot",
        description="대시보드 화면을 정적 HTML 묶음으로 떠 냅니다",
    )
    parser.add_argument("--out", default="dashboard-snapshot", help="결과 폴더")
    parser.add_argument("--db", default="", help="쓸 DB 경로. 비우면 빈 임시 DB")
    parser.add_argument("--stamp", default="", help="표지에 적을 날짜")
    parser.add_argument("--demo", action="store_true",
                        help="모의 실행을 한 번씩 돌려 실행 이력·산출물 화면까지 담습니다")
    parser.add_argument(
        "--lock", default="",
        help="확인용 한 장에 자물쇠를 겁니다. 이 글자를 모르면 못 읽습니다. "
             "흉내가 아니라 내용을 AES-GCM 으로 덮습니다. --single 과 같이 쓰세요.")
    parser.add_argument(
        "--split", action="store_true",
        help="덮은 덩어리를 data.bin 으로 따로 뺍니다. 웹에 올릴 때 쓰세요 — "
             "화면이 먼저 뜨고, 받는 동안 몇 퍼센트인지 보입니다.")
    parser.add_argument("--single", nargs="?", const="auto", default="",
                        help="화면 전부를 담은 HTML 파일 하나도 만듭니다")
    parser.add_argument("--zip", action="store_true", help="폴더를 zip 으로도 묶습니다")
    args = parser.parse_args(argv)

    if args.db:
        print("⚠ 실제 DB 로 뜹니다. 고객 이름·연락처가 화면에 그대로 찍힙니다.")

    single = args.single
    if single == "auto":
        single = str(Path(args.out) / "통합-관리자-대시보드.html")
    snapshot = build(args.out, Path(args.db) if args.db else None,
                     stamp=args.stamp, demo=args.demo, single=single,
                     lock=args.lock, split=args.split)
    print(f"화면 {snapshot.count}개 → {snapshot.index}")
    if snapshot.single:
        size = snapshot.single.stat().st_size / 1_000_000
        print(f"한 파일로 묶은 판 → {snapshot.single} ({size:.1f}MB)")
    for url, status in snapshot.failures:
        print(f"  ! {url} 를 뜨지 못했습니다 (HTTP {status})")
    if snapshot.dangling:
        print(f"  · 링크만 있고 뜨지 않은 화면 {len(snapshot.dangling)}개"
              " (눌러도 넘어가지 않습니다)")
    if args.zip:
        archive = shutil.make_archive(str(snapshot.out_dir), "zip", str(snapshot.out_dir))
        print(f"압축 → {archive}")
    print("표지 파일을 브라우저로 여세요. 서버가 없어 저장·실행은 되지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
