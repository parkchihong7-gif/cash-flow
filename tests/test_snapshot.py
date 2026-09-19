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
from dashboard.snapshot import PAGE_DIR, build, local_name, should_follow


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
