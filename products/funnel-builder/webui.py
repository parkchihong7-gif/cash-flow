"""1번 전용 웹 화면 — 입력 → 생성 → 산출물.

이 상품은 **입력 파일을 채우고 돌리는** 모양이라, 껍데기는
`core.webui.generator_webui()` 를 그대로 쓴다. 여기서 정하는 것은 **칸**뿐이다.
2·3차에 화면 모양을 바꿀 때는 그 공통 함수만 고치면 일곱 종이 같이 바뀐다.
"""

from __future__ import annotations

from pathlib import Path

from core.webui import Field, WebUI, generator_webui, read_yaml_fields, write_yaml_fields

BASE_DIR = Path(__file__).resolve().parent
INPUT = BASE_DIR / "funnel_input.yaml"

INT_KEYS = ('price',)
LIST_KEYS = ('pain_points',)
REQUIRED = ('product_name',)


def _fields() -> list[Field]:
    saved = read_yaml_fields(INPUT)

    def value(key, fallback=""):
        got = saved.get(key, fallback)
        if isinstance(got, list):
            return "\n".join(str(item) for item in got)
        return got if got is not None else fallback

    return [
        Field("product_name", "상품 이름", "text", default=value("product_name", ""), required=True),
        Field("target", "누구에게 파나요", "textarea", default=value("target", ""), help="**좁을수록 좋습니다.** '직장인' 보다 '혼자 가게를 운영하는 40대 자영업자'"),
        Field("price", "가격(원)", "number", default=value("price", 0)),
        Field("core_promise", "핵심 약속 한 줄", "textarea", default=value("core_promise", ""), help="이 상품을 사면 무엇이 달라지는지. 수치로 쓰면 좋습니다."),
        Field("lead_magnet_title", "무료 미끼 제목", "text", default=value("lead_magnet_title", ""), help="이메일을 받기 위해 먼저 드리는 것입니다."),
        Field("pain_points", "고객의 불편 (한 줄에 하나)", "textarea", default=value("pain_points", ""), help="구체적일수록 문구가 좋아집니다."),
    ]


def build(program, ctx) -> WebUI:
    return generator_webui(
        program, _fields(),
        input_title="어떤 상품의 퍼널인가요",
        input_intro="**타깃을 좁게 쓸수록** 좋은 문구가 나옵니다.",
        admin_intro="랜딩·이메일·리드매그넷을 한 번에 만듭니다. 플랫폼별로 산출물이 다릅니다.",
        client_intro="상품 정보를 적으시면 **랜딩 페이지와 이메일 5통**을 만들어 드립니다.",
    )


def handle(program, ctx, action: str, form: dict) -> str:
    if action != "save":
        return "error=모르는 동작입니다"
    return write_yaml_fields(INPUT, form, int_keys=INT_KEYS,
                             list_keys=LIST_KEYS, required=REQUIRED)
