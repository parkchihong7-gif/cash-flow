"""3번 전용 웹 화면 — 입력 → 생성 → 산출물.

이 상품은 **입력 파일을 채우고 돌리는** 모양이라, 껍데기는
`core.webui.generator_webui()` 를 그대로 쓴다. 여기서 정하는 것은 **칸**뿐이다.
2·3차에 화면 모양을 바꿀 때는 그 공통 함수만 고치면 일곱 종이 같이 바뀐다.
"""

from __future__ import annotations

from pathlib import Path

from core.webui import Field, WebUI, generator_webui, read_yaml_fields, write_yaml_fields

BASE_DIR = Path(__file__).resolve().parent
INPUT = BASE_DIR / "ebook_input.yaml"

INT_KEYS = ('pages',)
LIST_KEYS = ()
REQUIRED = ('topic',)


def _fields() -> list[Field]:
    saved = read_yaml_fields(INPUT)

    def value(key, fallback=""):
        got = saved.get(key, fallback)
        if isinstance(got, list):
            return "\n".join(str(item) for item in got)
        return got if got is not None else fallback

    return [
        Field("topic", "주제", "text", default=value("topic", ""), required=True),
        Field("audience", "누가 읽나요", "textarea", default=value("audience", ""), help="**좁을수록 좋은 목차가 나옵니다.** '직장인' 보다 '혼자 일하는 프리랜서 디자이너'"),
        Field("pages", "목표 쪽수", "number", default=value("pages", 40), help="챕터 8~12개 기준 16~40쪽이 무난합니다."),
        Field("author", "표지에 넣을 이름", "text", default=value("author", ""), help="비우면 자리만 만듭니다."),
    ]


def build(program, ctx) -> WebUI:
    return generator_webui(
        program, _fields(),
        input_title="어떤 전자책인가요",
        input_intro="목차를 먼저 만들고, 확인하신 뒤 본문을 씁니다.",
        admin_intro="목차 → 사람 확인 → 본문 순서입니다. 한 번에 다 쓰지 않습니다.",
        client_intro="주제를 적으시면 **목차부터** 만들어 드립니다.",
    )


def handle(program, ctx, action: str, form: dict) -> str:
    if action != "save":
        return "error=모르는 동작입니다"
    return write_yaml_fields(INPUT, form, int_keys=INT_KEYS,
                             list_keys=LIST_KEYS, required=REQUIRED)
