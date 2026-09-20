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
#:
#: 공인중개사는 여기 없다. 13번(`exam-drill`)이 바로 그 프로그램이라,
#: 따로 두면 키가 두 군데로 갈라진다. 앱스 스크립트의 `DEFAULT_PROGRAM`
#: 을 `exam-drill` 로 두면 그 화면이 보내는 키가 13번으로 들어온다.
OUTSIDE = [
    {"id": "maim", "name": "maim 블로그 (바깥 프로그램)"},
]

HEADER = (
    "/* 키 서버가 다루는 프로그램 목록. dashboard 의 등록부에서 뽑아 만든 것입니다.\n"
    "   `python -m tools.gen_programs_js` 로 다시 만듭니다. 손으로 고치지 마세요. */\n"
)

OUT = Path(__file__).resolve().parent.parent / "web" / "programs.js"


def build() -> list[dict[str, str]]:
    """등록부 + 바깥 프로그램을 합쳐 목록을 만든다."""
    rows = []
    for program in Registry().programs:
        row = {"id": program.id, "name": program.name}
        # 키를 넣고 들어가는 곳. 발급 안내 메일에 이 주소가 실린다.
        # 없으면 고객이 키만 받고 **어디로 가야 하는지 모르게** 된다.
        #
        # 역할마다 주소가 다르다. 관리자로 산 분에게 고객용 주소를 보내면
        # 발급 화면이 안 열리고, 반대면 고객이 남의 관리자 화면을 본다.
        if program.live.client:
            row["url"] = program.live.client
        if program.live.admin:
            row["adminUrl"] = program.live.admin
        rows.append(row)
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
