"""maim 화면 색판 — 대시보드와 같은 디자인인가.

maim 은 저장소가 따로 있다. 여기 있는 것은 **사본**이고, 사장님이 그쪽에
옮겨 붙이신다. 사본이 대시보드에서 떨어져 나가면 옮겨 붙이는 순간 두 화면이
다시 달라진다 — 그래서 여기서 잡아 둔다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

여기 = Path("products/naver-blog/maim-화면")
사본 = 여기 / "style.css"
대시보드 = Path("dashboard/static/style.css")


def _규칙만(글: str) -> str:
    """설명글(`/* … */`)을 덜어 낸다.

    설명에 «예전에는 `color-scheme: dark` 였다» 처럼 적어 두면 찾기가
    그것까지 집어낸다. 규칙만 봐야 한다.
    """
    return re.sub(r"/\*.*?\*/", "", 글, flags=re.S)


def _뿌리(글: str) -> dict[str, str]:
    """`:root { … }` 안의 `--이름: 값` 을 읽는다."""
    시작 = 글.index(":root {")
    안 = 글[시작:글.index("}", 시작)]
    return {이름: 값.strip()
            for 이름, 값 in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", 안)}


def test_사본이_있다():
    assert 사본.is_file(), "maim 에 옮겨 붙일 파일이 없습니다"
    assert (여기 / "README.md").is_file(), "옮겨 붙이는 법이 없습니다"


@pytest.mark.parametrize("maim이름,대시보드이름", [
    ("--gold", "--accent"),
    ("--text", "--ink"),
    ("--text-muted", "--ink-soft"),
    ("--text-faint", "--ink-faint"),
    ("--border", "--line"),
    ("--bg", "--bg-soft"),
    ("--bg-sunk", "--bg-sunk"),
    ("--gold-soft", "--accent-soft"),
    ("--success", "--ok"),
    ("--danger", "--bad"),
])
def test_색이_대시보드와_같다(maim이름, 대시보드이름):
    """이름은 달라도 **값은 같아야** 한다.

    maim 의 변수 이름은 일부러 그대로 뒀다. `--gold` 는 이제 금색이 아니라
    파랑이지만, 이름을 고치면 1,100줄을 다 건드려야 하고 그만큼 잘못 건드릴
    자리가 늘어난다.
    """
    저쪽 = _뿌리(사본.read_text(encoding="utf-8"))
    이쪽 = _뿌리(대시보드.read_text(encoding="utf-8"))
    assert 저쪽[maim이름].lower() == 이쪽[대시보드이름].lower()


def test_어두운_화면_흔적이_남지_않았다():
    글 = _규칙만(사본.read_text(encoding="utf-8"))
    assert "color-scheme: dark" not in 글
    for 옛색 in ("#13151c", "#1a1d27", "#20232f", "#2c3040", "#0e1016",
                 "#6366f1", "#818cf8", "#e9eaf2"):
        assert 옛색 not in 글.lower(), f"{옛색} 이 남아 있습니다"


def test_색을_뿌리에서만_정한다():
    """`:root` 밖에 색을 박으면 다음에 색판을 갈 때 그 자리만 남는다.

    한 번 데였다. 어두운 화면 시절의 `rgba(99, 102, 241, …)` 열세 군데가
    본문에 박혀 있어서, 뿌리만 갈았을 때 그 자리들만 인디고로 남았다.
    """
    글 = _규칙만(사본.read_text(encoding="utf-8"))
    본문 = 글[글.index("}", 글.index(":root {")):]
    남은것 = [m.group(0) for m in re.finditer(r"#[0-9a-fA-F]{3,8}\b|rgba?\([\d\s,.]+\)", 본문)]
    assert not 남은것, f"뿌리 밖에 박힌 색: {남은것}"


def test_마우스_올린_면이_보인다():
    """밝은 바탕에서 가장 쉽게 사라지는 것.

    어두운 화면에서는 «더 밝은 면»이 떠 보였다. 그 자리를 그대로 두고 색만
    갈면 **흰 위에 흰**이 되어 마우스를 올려도 아무 일도 안 일어난다.
    """
    글 = _규칙만(사본.read_text(encoding="utf-8"))
    for 자리 in (".sidebar-nav-item:hover", ".btn-secondary:hover:not(:disabled)"):
        칸 = 글[글.index(자리):]
        칸 = 칸[:칸.index("}")]
        assert "var(--bg-sunk)" in 칸, f"{자리} 가 눌린 면을 쓰지 않습니다"
