"""5번 전용 웹 화면 — 입력 → 생성 → 산출물.

이 상품은 **입력 파일을 채우고 돌리는** 모양이라, 껍데기는
`core.webui.generator_webui()` 를 그대로 쓴다. 여기서 정하는 것은 **칸**뿐이다.
2·3차에 화면 모양을 바꿀 때는 그 공통 함수만 고치면 일곱 종이 같이 바뀐다.
"""

from __future__ import annotations

from pathlib import Path

from core.webui import Field, WebUI, generator_webui, read_yaml_fields, write_yaml_fields

BASE_DIR = Path(__file__).resolve().parent
INPUT = BASE_DIR / "service_input.yaml"

INT_KEYS = ()
LIST_KEYS = ('what_you_deliver',)
REQUIRED = ('service_name',)


def _fields() -> list[Field]:
    saved = read_yaml_fields(INPUT)

    def value(key, fallback=""):
        got = saved.get(key, fallback)
        if isinstance(got, list):
            return "\n".join(str(item) for item in got)
        return got if got is not None else fallback

    return [
        Field("service_name", "서비스 이름", "text", default=value("service_name", ""), required=True),
        Field("category", "카테고리", "text", default=value("category", ""), help="예: 디자인 > 로고·브랜딩"),
        Field("who_for", "누구를 위한 서비스인가요", "textarea", default=value("who_for", ""), help="**좁을수록 좋습니다.**"),
        Field("what_you_deliver", "받는 것 (한 줄에 하나)", "textarea", default=value("what_you_deliver", ""), help="2~10개. 파일 형식까지 적으면 좋습니다."),
    ]


def build(program, ctx) -> WebUI:
    return generator_webui(
        program, _fields(),
        input_title="어떤 서비스를 파시나요",
        input_intro="**구매자가 실제로 받는 것**을 구체적으로 적으세요.",
        admin_intro="상세페이지 카피를 만듭니다. 과장 문구는 검사에서 걸립니다.",
        client_intro="서비스 정보를 적으시면 **크몽 상세페이지 문구**를 만들어 드립니다.",
    )


def handle(program, ctx, action: str, form: dict) -> str:
    if action != "save":
        return "error=모르는 동작입니다"
    return write_yaml_fields(INPUT, form, int_keys=INT_KEYS,
                             list_keys=LIST_KEYS, required=REQUIRED)
