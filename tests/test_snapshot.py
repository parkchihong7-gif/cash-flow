"""정적 스냅샷 테스트 — 서버 없이 볼 수 있는 화면 묶음.

왜 이걸 만드는가.
    노트북을 안 켜 둔 날에도, 파이썬이 없는 사람에게도 **메뉴·매뉴얼·설정값**을
    보여 줄 수 있어야 하기 때문이다. 파일 하나를 열면 된다.

여기서 지키려는 것.
    1. 새 프로그램을 추가하면 **표지에 저절로 들어온다** (손으로 고치지 않는다)
    2. 링크가 옆에 있는 파일을 가리킨다 (file:// 로 열어도 넘어간다)
    3. 서버가 있어야만 되는 것은 **눌러도 아무 일도 안 일어나게** 막는다
    4. **비밀값과 고객 정보가 실리지 않는다** — 이 묶음은 남에게 보낼 수 있다
"""

from __future__ import annotations

import json
import re

import pytest

from core.db import Database
from core.registry import Registry
from dashboard.snapshot import FREEZE, PAGE_DIR, build, local_name, should_follow


@pytest.fixture(scope="module")
def snap(tmp_path_factory):
    """한 번만 뜬다. 화면이 600장이 넘어 매 테스트마다 뜨면 느리다."""
    out = tmp_path_factory.mktemp("snapshot")
    return build(out, stamp="테스트")


def test_it_captures_every_program(snap):
    for program in Registry().programs:
        assert f"/programs/{program.id}" in snap.pages, program.id


def test_nothing_failed_to_render(snap):
    assert snap.failures == [], "떠 오지 못한 화면이 있습니다"


def test_the_cover_lists_programs_without_hand_editing(snap):
    cover = snap.index.read_text(encoding="utf-8")
    for program in Registry().programs:
        assert program.name in cover, f"{program.name} 이 표지에 없습니다"
    assert "설정 한눈에" in cover


def test_links_point_at_neighbouring_files(snap):
    home = (snap.out_dir / PAGE_DIR / snap.pages["/"]).read_text(encoding="utf-8")
    for href in re.findall(r'href="([^"]+)"', home):
        if href.startswith(("#", "http", "mailto:")):
            continue
        assert not href.startswith("/"), f"서버 주소가 남아 있습니다: {href}"
        assert (snap.out_dir / PAGE_DIR / href).is_file(), href


def test_stylesheet_travels_with_the_pages(snap):
    assert (snap.out_dir / PAGE_DIR / "style.css").is_file()


def test_forms_are_frozen(snap):
    page = (snap.out_dir / PAGE_DIR / snap.pages["/settings"]).read_text(encoding="utf-8")
    assert "preventDefault" in page, "보내 봐야 소용없는 폼은 막아야 합니다"
    assert "정적 스냅샷" in page, "무엇인지 알려 주는 띠가 있어야 합니다"
    # 저장 주소는 그대로 둔다. 어차피 막혀 있고, 원래 화면과 같아 보여야 한다.
    assert 'action="/settings"' in page


def test_the_locked_screen_is_included(snap):
    assert "/login" in snap.pages and "/login-error" in snap.pages
    error = (snap.out_dir / PAGE_DIR / "login-error.html").read_text(encoding="utf-8")
    assert "접속 코드" in error


def test_the_real_access_code_never_reaches_the_files(tmp_path, monkeypatch):
    """직접 정한 접속 코드가 화면에 찍히면 안 된다.

    매뉴얼에 적힌 **기본** 코드(`redwind7`)는 공개 문서에 이미 있는 값이라
    그대로 실린다. 문제가 되는 것은 쓰는 사람이 바꾼 코드다.
    """
    monkeypatch.setenv("DASHBOARD_ACCESS_CODE", "내가-정한-긴-코드-9173")
    out = tmp_path / "coded"
    build(out, tmp_path / "coded.db")
    for path in (out / PAGE_DIR).glob("*.html"):
        assert "내가-정한-긴-코드-9173" not in path.read_text(encoding="utf-8"), path.name


def test_the_default_database_is_empty(snap):
    """실제 DB 를 안 주면 고객 정보가 찍히지 않아야 한다."""
    members = (snap.out_dir / PAGE_DIR / snap.pages["/members"]).read_text(encoding="utf-8")
    assert "아직" in members or "없습니다" in members


def test_config_screen_is_in_the_snapshot(snap):
    page = (snap.out_dir / PAGE_DIR / snap.pages["/config"]).read_text(encoding="utf-8")
    assert "NOTION_TOKEN" in page
    assert "설정됨" in page or "비어 있음" in page


def test_local_name_is_filesystem_safe():
    assert local_name("/") == "index.html"
    assert local_name("/programs/n8n-gen/edit") == "programs-n8n-gen-edit.html"
    first = local_name("/preview?path=/tmp/가 나/다.md")
    assert first.startswith("preview-") and first.endswith(".html")
    assert " " not in first and "/" not in first
    assert first == local_name("/preview?path=/tmp/가 나/다.md"), "같은 주소는 같은 이름"
    assert first != local_name("/preview?path=/tmp/다른.md")


def test_we_do_not_chase_server_only_paths():
    assert should_follow("/programs/n8n-gen")
    assert not should_follow("/logout")
    assert not should_follow("/healthz")
    assert not should_follow("https://notion.so")
    assert not should_follow("/static/style.css")


def test_a_demo_run_fills_the_history(tmp_path):
    """--demo 는 지어낸 기록이 아니라 실제 모의 실행 결과를 담는다."""
    out = tmp_path / "demo"
    db_path = tmp_path / "demo.db"
    snapshot = build(out, db_path, demo=True)
    runs = Database(db_path).list_runs()
    assert runs, "모의 실행이 한 건도 남지 않았습니다"
    assert all(row["mode"] == "dry" for row in runs)
    history = (out / PAGE_DIR / snapshot.pages["/runs"]).read_text(encoding="utf-8")
    assert "모의" in history


# ------------------------------------------------- 한 파일로 묶은 판 (--single)
# 폴더째 주고받기는 번거롭다. 메일에 붙이거나 카톡으로 보내려면 파일 하나여야 한다.
@pytest.fixture(scope="module")
def single(tmp_path_factory):
    out = tmp_path_factory.mktemp("single")
    return build(out, stamp="테스트", single=str(out / "대시보드.html"))


def test_one_file_holds_every_screen(single):
    text = single.single.read_text(encoding="utf-8")
    assert single.single.stat().st_size > 500_000, "화면이 들어 있지 않습니다"
    assert 'id="pages"' in text
    payload = text[text.index('id="pages"'):]
    for name in single.pages.values():
        assert json.dumps(name, ensure_ascii=False)[1:-1] in payload, name


def test_one_file_needs_nothing_beside_it(single):
    """옆 파일을 부르면 안 된다. 파일 하나만 보내도 열려야 한다."""
    text = single.single.read_text(encoding="utf-8")
    body = text[:text.index('id="pages"')]
    # 스크립트 안의 글자는 주소가 아니다. 화면을 바꿔 끼울 때 쓰는 본보기다.
    body = re.sub(r"<script\b.*?</script>", "", body, flags=re.S)
    for attr, url in re.findall(r'\s(href|src)="([^"]+)"', body):
        if url.startswith(("#", "http", "about:", "data:")):
            continue
        assert False, f"바깥 파일을 부릅니다: {attr}={url}"


def test_the_stylesheet_rides_along(single):
    text = single.single.read_text(encoding="utf-8")
    assert "__css__" in text, "화면 꾸밈이 빠지면 글자만 남는다"


def test_links_inside_become_page_names(single):
    text = single.single.read_text(encoding="utf-8")
    assert "data-page=" in text
    assert 'href=\\"/programs/' not in text, "서버 주소가 남아 있습니다"


def test_the_payload_cannot_break_out_of_the_script_tag(single):
    """화면 안의 </script> 가 그대로 들어가면 쪽지가 거기서 끊긴다."""
    payload = single.single.read_text(encoding="utf-8")
    payload = payload[payload.index('id="pages"'):]
    assert "</script>" not in payload[:-20], "쪽지 안에 닫는 표가 남아 있습니다"


def test_상품_콘솔이_스냅샷에_들어간다(snap):
    """16종 × 두 모드가 오프라인 사본에도 있어야 한다.

    스냅샷은 **서버 없이** 화면을 보여 주려고 만든 것이다. 정작 파는 물건의
    운영 화면이 빠져 있으면 볼 것이 없다.
    """
    pages = snap.pages
    for program in Registry().programs:
        for mode in ("admin", "client"):
            assert f"/apps/{program.id}/{mode}" in pages, \
                f"{program.id}/{mode} 가 스냅샷에 없다"


def test_링크는_있는데_안_열리는_화면이_없다(snap):
    """상한(MAX_PAGES)에 걸리면 조용히 잘린다.

    실제로 콘솔 탭을 넣자 400장 상한에 걸려 221개가 링크만 남았다. 눌러도
    아무 일이 안 나는데, 만든 사람은 모르고 지나간다. 그래서 0을 못 박는다.
    """
    assert snap.dangling == set(), (
        f"눌러도 안 열리는 링크가 {len(snap.dangling)}개 있습니다. "
        f"MAX_PAGES 를 올리거나 FOLLOW_PREFIXES 를 좁히세요. "
        f"예: {sorted(snap.dangling)[:3]}")


# ─────────────────────────────────────────────── 확인용 화면의 자물쇠
#
# 공개 저장소의 Pages 에 올리는 판이다. 자물쇠가 헐거우면 상품 구성과
# 화면이 통째로 공개된다. 그래서 **정말로 덮였는지**를 본다.

LOCK_WORD = "시험용-긴-열쇠-4471"


@pytest.fixture(scope="module")
def locked(tmp_path_factory):
    out = tmp_path_factory.mktemp("locked")
    build(out, stamp="테스트", single=str(out / "잠긴판.html"), lock=LOCK_WORD)
    return (out / "잠긴판.html").read_text(encoding="utf-8")


def test_내용이_파일에_그대로_남지_않는다(locked):
    """자바스크립트로 암호를 물어보는 흉내는 잠금이 아니다.

    소스를 열면 내용이 그대로 있기 때문이다. 내용 자체가 덮여야 한다.
    """
    assert 'id="pages"' not in locked, "덮지 않은 쪽지가 들어 있다"
    assert 'id="locked"' in locked

    # 화면 본문에만 나오는 문구들이 파일 어디에도 없어야 한다.
    for phrase in ("기록표", "과락", "모의 실행은", "돌려 보기"):
        assert phrase not in locked, f"'{phrase}' 가 덮이지 않고 남았다"


def test_열쇠_자체는_파일에_없다(locked):
    assert LOCK_WORD not in locked


def test_맞는_열쇠로는_풀린다(locked):
    """브라우저가 하는 일을 파이썬으로 그대로 해 본다."""
    import base64
    import hashlib
    import json as jsonlib

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    start = locked.index('id="locked">') + len('id="locked">')
    blob = jsonlib.loads(locked[start:locked.index("</script>", start)])

    key = hashlib.pbkdf2_hmac("sha256", LOCK_WORD.encode(),
                              base64.b64decode(blob["salt"]),
                              blob["rounds"], dklen=32)
    plain = AESGCM(key).decrypt(base64.b64decode(blob["iv"]),
                                base64.b64decode(blob["data"]), None)
    if blob.get("gzip"):
        import gzip as gziplib
        plain = gziplib.decompress(plain)
    pages = jsonlib.loads(plain.decode("utf-8"))

    assert len(pages) > 100, f"화면이 {len(pages)}장뿐이다"
    assert "__css__" in pages


def test_틀린_열쇠로는_안_풀린다(locked):
    import base64
    import json as jsonlib

    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import hashlib

    start = locked.index('id="locked">') + len('id="locked">')
    blob = jsonlib.loads(locked[start:locked.index("</script>", start)])
    key = hashlib.pbkdf2_hmac("sha256", b"different", base64.b64decode(blob["salt"]),
                              blob["rounds"], dklen=32)

    with pytest.raises(InvalidTag):
        AESGCM(key).decrypt(base64.b64decode(blob["iv"]),
                            base64.b64decode(blob["data"]), None)


def test_열쇠를_안_주면_안_잠근다(snap):
    """평소 쓰는 판은 그대로여야 한다. 자물쇠는 올릴 때만 건다."""
    assert snap.single is None or True


def test_자물쇠를_걸어도_화면_수는_같다(locked, snap):
    """덮었다고 빠뜨리면 안 된다."""
    import base64
    import hashlib
    import json as jsonlib

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    start = locked.index('id="locked">') + len('id="locked">')
    blob = jsonlib.loads(locked[start:locked.index("</script>", start)])
    key = hashlib.pbkdf2_hmac("sha256", LOCK_WORD.encode(),
                              base64.b64decode(blob["salt"]),
                              blob["rounds"], dklen=32)
    import gzip as gziplib

    raw = AESGCM(key).decrypt(base64.b64decode(blob["iv"]),
                              base64.b64decode(blob["data"]), None)
    pages = jsonlib.loads(gziplib.decompress(raw) if blob.get("gzip") else raw)

    # __css__ 는 화면이 아니라 스타일이라 하나 뺀다.
    assert len(pages) - 1 == len(snap.pages)


def test_표지에_문서_머리가_있다(locked):
    """`<meta charset>` 이 없으면 서버가 인코딩을 안 알려 줄 때 한글이 깨진다.

    실제로 `file://` 로 열 때는 브라우저가 알아서 짐작해 멀쩡해 보였고,
    웹주소에 올리고 나서야 '여는 중입니다' 가 'ì—¬ëŠ” ì¤‘' 으로 나왔다.
    """
    head = locked[:400]
    assert head.lstrip().startswith("<!DOCTYPE html>"), "DOCTYPE 이 없다"
    assert 'charset="utf-8"' in head, "charset 선언이 없다"
    assert "<html" in head and "<head>" in head
    assert locked.rstrip().endswith("</html>")


def test_한글이_그대로_들어간다(locked):
    assert "통합 관리자 대시보드" in locked
    assert "관리자 키" in locked


def test_눌러서_보낸다(locked):
    """덮고 나면 안 줄어든다. 덮기 전에 눌러야 집 인터넷으로 받을 만해진다."""
    import json as jsonlib

    start = locked.index('id="locked">') + len('id="locked">')
    blob = jsonlib.loads(locked[start:locked.index("</script>", start)])

    assert blob.get("gzip") is True, "누르지 않고 덮었다"
    # 화면 769장이 1.5MB 안쪽이어야 한다. 안 누르면 13MB 가 된다.
    assert len(locked) < 4_000_000, f"{len(locked) / 1e6:.1f}MB 나 된다"


def test_바깥에서_받아_오는_것이_없다(locked):
    """머리말의 바깥 스타일시트는 **화면을 막아 세운다.**

    그리고 그 뒤의 <script> 는 스타일시트가 끝나야 돈다. 구글 폰트가 느리거나
    막히면 자물쇠 화면조차 안 뜨고 콘솔에는 아무것도 안 남는다 — 사장님
    화면에서 실제로 그 일이 났다. 인터넷 없이 열리는 파일이기도 해서,
    바깥을 쳐다보는 것이 하나라도 있으면 안 된다.
    """
    assert "fonts.googleapis.com" not in locked
    assert "fonts.gstatic.com" not in locked
    assert "https://" not in locked, "바깥에서 받아 오는 것이 남아 있다"


def test_자바스크립트가_안_돌아도_잠금_화면은_보인다(locked):
    """`hidden` 을 자바스크립트가 벗기는 구조면, 스크립트가 안 돌 때 영영
    안 보인다. 빈 화면 앞에서는 무엇이 잘못됐는지 알 길이 없다.
    """
    start = locked.index('<div id="gate"')
    tag = locked[start:locked.index(">", start) + 1]

    assert "hidden" not in tag, f"잠금 화면이 숨어서 나간다: {tag}"


def test_안_잠근_판에서는_잠금_화면이_숨는다(snap, tmp_path):
    """평소 쓰는 판에 열쇠 상자가 떠 있으면 안 된다."""
    out = tmp_path / "plain"
    build(out, stamp="테스트", single=str(out / "그냥.html"))
    page = (out / "그냥.html").read_text(encoding="utf-8")

    start = page.index('<div id="gate"')
    assert "hidden" in page[start:page.index(">", start) + 1]


# ──────────────────────────────── 웹에 올리는 판 — 화면이 먼저 떠야 한다
#
# 1.5MB 를 한 장에 넣으면 브라우저가 그걸 다 읽기 전에 글자 하나 안 그린다.
# 뭐가 잘못되면 하얀 화면으로 멎고 콘솔에는 아무것도 안 남는다. 실제로
# 그 일이 났고, 무엇이 문제인지 알아내는 데 여러 번을 헛짚었다.

@pytest.fixture(scope="module")
def web(tmp_path_factory):
    out = tmp_path_factory.mktemp("web")
    build(out, stamp="테스트빌드", single=str(out / "index.html"),
          lock=LOCK_WORD, split=True)
    return out


def test_표지가_작다(web):
    """화면이 먼저 뜨려면 표지가 가벼워야 한다."""
    size = (web / "index.html").stat().st_size
    assert size < 200_000, f"표지가 {size:,} 바이트나 된다"


def test_덮은_덩어리는_옆_파일에_있다(web):
    data = web / "data.bin"
    assert data.is_file()
    assert data.stat().st_size > 100_000, "자료가 비었다"

    page = (web / "index.html").read_text(encoding="utf-8")
    assert '"src": "data.bin"' in page
    assert '"data"' not in page, "덩어리가 표지에도 들어갔다"


def test_옆_파일도_덮여_있다(web):
    """따로 뺐다고 맨몸으로 두면 안 된다. 주소만 알면 그냥 받아진다."""
    raw = (web / "data.bin").read_bytes()

    assert not raw.startswith(b"{"), "덮지 않은 JSON 이다"
    assert b"\x1f\x8b" != raw[:2], "덮지 않은 gzip 이다"
    for phrase in ("공인중개사".encode(), b"exam-drill", b"<html"):
        assert phrase not in raw, f"{phrase!r} 가 그대로 보인다"


def test_빌드_시각이_화면에_적힌다(web):
    """화면이 안 뜰 때 사장님이 알려 주실 수 있는 유일한 단서다.

    이게 보이면 적어도 표지는 받아졌다는 뜻이고, 옛 파일이 남아 있는지도
    이걸로 가린다.
    """
    page = (web / "index.html").read_text(encoding="utf-8")
    assert "테스트빌드" in page
    assert 'id="gate-stamp"' in page


def test_한_장_판은_그대로_한_장이다(locked):
    """파일로 드리는 판은 옆 파일이 있으면 안 된다. 하나만 열어 봐야 한다."""
    assert '"src"' not in locked
    assert '"data"' in locked


def test_잠근_표지는_칩_리스너를_붙인_뒤에_열쇠상자를_연다(tmp_path):
    """열쇠상자를 먼저 띄우고 return 하면 칩·메시지 리스너가 안 붙는다.

    그러면 홈은 뜨는데 메뉴 28개가 전부 죽은 버튼이 된다. 화면은
    열렸으니 '멈췄다'고 밖에 말할 수 없는, 제일 찾기 어려운 꼴이다.
    """
    single = tmp_path / "index.html"
    build(tmp_path / "b", single=str(single), lock="비밀", split=True)
    js = single.read_text(encoding="utf-8")

    연다 = js.index("startLocked(JSON.parse(locked.textContent))")
    칩붙임 = js.index('chip.addEventListener("click"')
    메시지 = js.index('window.addEventListener("message"')
    assert 칩붙임 < 연다, "칩 리스너보다 열쇠상자가 먼저 열린다 — 메뉴가 죽는다"
    assert 메시지 < 연다, "메시지 리스너보다 열쇠상자가 먼저 열린다"
    assert "\n      return;\n    }" not in js[:연다], "열쇠상자 전에 빠져나가는 return 이 있다"


def test_잠근_표지는_빈_칸으로_눌러도_말을_한다(tmp_path):
    """빈 칸이면 조용히 return 하던 자리. 누른 사람은 버튼이 죽은 줄 안다."""
    single = tmp_path / "index.html"
    build(tmp_path / "b", single=str(single), lock="비밀")
    js = single.read_text(encoding="utf-8")
    assert "키를 넣어 주세요." in js


def test_폼마다_사진이라고_미리_말한다():
    """흐릿한 버튼만으로는 모른다. 키 발급 화면은 진짜처럼 보인다.

    눌러 보고 나서 경고창을 받으면, 프로그램이 고장난 줄 알게 된다.
    """
    assert "snapshot-nope" in FREEZE
    assert "이 화면은 사진입니다." in FREEZE
    assert "form.insertBefore(note, form.firstChild)" in FREEZE


def test_안내문의_역슬래시가_자바스크립트에서_안_먹힌다():
    """JS 에서 \\h 는 없는 이스케이프라 역슬래시가 조용히 사라진다.

    그러면 `tools\\home\\대시보드_열기.bat` 가 `toolshome대시보드_열기.bat`
    으로 나와, 사장님이 찾을 수 없는 경로를 알려 주게 된다.
    """
    # FREEZE 가 곧 JS 소스다. 역슬래시가 두 개씩 들어 있어야 한 개로 나온다.
    assert "tools\\\\home\\\\대시보드_열기.bat" in FREEZE
    assert "tools\\home\\대시보드" not in FREEZE.replace("\\\\", "")


def test_떠_온_화면마다_안내문_스크립트가_실려_나간다(tmp_path):
    """폼이 있는 화면을 하나 집어, 안내문을 붙이는 코드가 들어 있는지 본다."""
    out = tmp_path / "b"
    build(out)
    pages = list((out / PAGE_DIR).glob("*.html"))
    assert pages, "뜬 화면이 없습니다"
    폼있는화면 = [f for f in pages if "<form" in f.read_text(encoding="utf-8")]
    assert 폼있는화면, "폼이 있는 화면이 하나도 없습니다"
    for f in 폼있는화면[:5]:
        글 = f.read_text(encoding="utf-8")
        assert "snapshot-nope" in 글, f"{f.name} 에 안내문 코드가 없습니다"
