"""4번 전용 웹 화면 — 입력 → 생성 → 산출물.

이 상품은 **입력 파일을 채우고 돌리는** 모양이라, 껍데기는
`core.webui.generator_webui()` 를 그대로 쓴다. 여기서 정하는 것은 **칸**뿐이다.
2·3차에 화면 모양을 바꿀 때는 그 공통 함수만 고치면 일곱 종이 같이 바뀐다.
"""

from __future__ import annotations

from pathlib import Path

from core.webui import Field, WebUI, generator_webui, read_yaml_fields, write_yaml_fields

BASE_DIR = Path(__file__).resolve().parent
INPUT = BASE_DIR / "deck_input.yaml"

INT_KEYS = ('total_minutes',)
LIST_KEYS = ()
REQUIRED = ('course_title',)


def _fields() -> list[Field]:
    saved = read_yaml_fields(INPUT)

    def value(key, fallback=""):
        got = saved.get(key, fallback)
        if isinstance(got, list):
            return "\n".join(str(item) for item in got)
        return got if got is not None else fallback

    return [
        Field("course_title", "강의 제목", "text", default=value("course_title", ""), required=True),
        Field("audience", "누가 듣나요", "textarea", default=value("audience", ""), help="**좁을수록 좋은 커리큘럼이 나옵니다.**"),
        Field("total_minutes", "전체 시간(분)", "number", default=value("total_minutes", 180), help="30~960 사이"),
        Field("instructor", "강사 이름", "text", default=value("instructor", ""), help="비우면 자리만 만듭니다."),
        Field("palette", "색", "select", default=value("palette", "minimal"), options=['minimal', 'bold', 'corporate']),
    ]


def build(program, ctx) -> WebUI:
    return generator_webui(
        program, _fields(),
        input_title="어떤 강의인가요",
        input_intro="전체 시간에 맞춰 커리큘럼을 나눕니다.",
        admin_intro="커리큘럼·슬라이드·실습지를 만듭니다. 색은 palettes.json 에서 고칩니다.",
        client_intro="강의 정보를 적으시면 **슬라이드와 실습지**를 만들어 드립니다.",
    )


def handle(program, ctx, action: str, form: dict) -> str:
    if action != "save":
        return "error=모르는 동작입니다"
    return write_yaml_fields(INPUT, form, int_keys=INT_KEYS,
                             list_keys=LIST_KEYS, required=REQUIRED)


# ══════════════════════════════════════════════════════════ 운영 콘솔
#
# 적는다 → 만든다 → 받는다. 이 상품은 정말로 이 세 걸음이라 탭도 셋이다.
# 억지로 늘리지 않았다. 대신 **탭 이름은 이 상품이 내놓는 것**으로 붙였다 —
# 나오는 것이 무엇인지가 상품마다 전혀 다르기 때문이다.

from core.console import (                                        # noqa: E402
    Console, FileLoc, ManualTask, Tab, Todo, Trouble, generator_console,
)


def console(program, ctx) -> Console:
    return generator_console(
        program, build(program, ctx),
        input_label="강의 기획", input_icon="🎓",
        output_label="커리큘럼·슬라이드·노트", output_icon="🖥",
        output_intro="커리큘럼, 슬라이드(.pptx), 발표자 노트가 한 벌로 나옵니다.",
        make_label="강의 자료 만들기",
        todos=[
            Todo("누구에게 무엇을 가르칠지 적기", tab="input"),
            Todo("커리큘럼을 먼저 보고 **차시 순서**를 고치기", tab="make"),
            Todo("발표자 노트를 보며 **한 번 말해 보기**", by_hand=True,
                 detail="슬라이드는 괜찮은데 말이 안 이어지는 일이 흔합니다."),
        ],
        manual_tasks=[
            ManualTask(
                task="실습 자료·예제 준비",
                where="직접",
                why="강의의 값어치는 실습에서 나옵니다. 슬라이드는 뼈대일 뿐이라 "
                    "실제로 돌려 볼 예제는 만드셔야 합니다."),
            ManualTask(
                task="슬라이드 디자인 다듬기",
                where="파워포인트·키노트",
                why="내용과 구조까지 만들어 드립니다. 글꼴·색·이미지는 "
                    "브랜드마다 달라 손으로 하셔야 합니다."),
        ],
        troubles=[
            Trouble("pptx 가 안 만들어진다",
                    "`python-pptx` 가 필요합니다. `requirements.txt` 로 설치하세요."),
            Trouble("차시 분량이 들쭉날쭉하다",
                    "기획에 **총 시간**을 적어 주세요. 안 적으면 꼭지마다 "
                    "같은 무게로 잡습니다."),
            Trouble("슬라이드에 글이 너무 많다",
                    "발표자 노트로 옮기세요. 슬라이드는 보는 것이고 "
                    "노트는 말하는 것입니다."),
        ],
        files=[
            FileLoc("강의 기획", "products/lecture-deck/input.yaml"),
            FileLoc("만든 자료", "products/lecture-deck/outputs/"),
        ],
    )
