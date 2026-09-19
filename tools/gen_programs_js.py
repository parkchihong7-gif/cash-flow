"""`web/programs.js` 를 등록부에서 다시 만든다.

프로그램을 더하거나 이름을 바꾸면 관리자 화면의 고르는 칸도 따라와야 한다.
손으로 두 군데를 고치면 반드시 한쪽을 잊는다.

    python -m tools.gen_programs_js
"""

from __future__ import annotations

import json
from pathlib import Path

from core.registry import Registry

#: 이 저장소 밖에 있지만 **같은 키 서버**를 쓰는 것들.
#: 공인중개사·maim 을 한 키 체계로 묶는 것이 애초의 목적이었다.
OUTSIDE = [
    {"id": "exam", "name": "공인중개사 기출문제 (바깥 프로그램)"},
    {"id": "maim", "name": "maim 블로그 (바깥 프로그램)"},
]

HEADER = (
    "/* 키 서버가 다루는 프로그램 목록. dashboard 의 등록부에서 뽑아 만든 것입니다.\n"
    "   `python -m tools.gen_programs_js` 로 다시 만듭니다. 손으로 고치지 마세요. */\n"
)

OUT = Path(__file__).resolve().parent.parent / "web" / "programs.js"


def build() -> list[dict[str, str]]:
    """등록부 + 바깥 프로그램을 합쳐 목록을 만든다."""
    rows = [{"id": p.id, "name": p.name} for p in Registry().programs]
    return rows + OUTSIDE


def render(rows: list[dict[str, str]]) -> str:
    return HEADER + "window.PROGRAMS = " + json.dumps(rows, ensure_ascii=False, indent=2) + ";\n"


def main() -> None:
    rows = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(rows), encoding="utf-8")
    print(f"{OUT.relative_to(Path.cwd())} 에 {len(rows)}개를 적었습니다.")


if __name__ == "__main__":
    main()
