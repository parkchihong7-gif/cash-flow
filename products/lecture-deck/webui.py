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
