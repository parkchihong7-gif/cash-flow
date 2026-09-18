"""2번 전용 웹 화면 — 입력 → 생성 → 산출물.

이 상품은 **입력 파일을 채우고 돌리는** 모양이라, 껍데기는
`core.webui.generator_webui()` 를 그대로 쓴다. 여기서 정하는 것은 **칸**뿐이다.
2·3차에 화면 모양을 바꿀 때는 그 공통 함수만 고치면 일곱 종이 같이 바뀐다.
"""

from __future__ import annotations

from pathlib import Path

from core.webui import Field, WebUI, generator_webui, read_yaml_fields, write_yaml_fields

BASE_DIR = Path(__file__).resolve().parent
INPUT = BASE_DIR / "script_input.yaml"

INT_KEYS = ('duration_sec',)
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
        Field("topic", "주제", "textarea", default=value("topic", ""), required=True),
        Field("format", "포맷", "select", default=value("format", "shorts"), options=['shorts', 'reels', 'long'], help="쇼츠·릴스는 15~60초, 롱폼은 5~20분입니다."),
        Field("duration_sec", "길이(초)", "number", default=value("duration_sec", 30)),
        Field("audience", "보는 사람", "textarea", default=value("audience", ""), help="**좁게 쓰세요.**"),
        Field("tone", "톤", "select", default=value("tone", "정보형"), options=['정보형', '스토리형', '반전형']),
        Field("cta", "마지막에 시킬 것", "select", default=value("cta", "구독"), options=['구독', '링크', '댓글']),
    ]


def build(program, ctx) -> WebUI:
    return generator_webui(
        program, _fields(),
        input_title="어떤 영상을 만드시나요",
        input_intro="포맷과 길이에 따라 대본 구조가 달라집니다.",
        admin_intro="멈추는 이유 8가지를 프롬프트에 넣어 대본을 만듭니다.",
        client_intro="주제를 적으시면 **후킹이 들어간 대본**을 만들어 드립니다.",
    )


def handle(program, ctx, action: str, form: dict) -> str:
    if action != "save":
        return "error=모르는 동작입니다"
    return write_yaml_fields(INPUT, form, int_keys=INT_KEYS,
                             list_keys=LIST_KEYS, required=REQUIRED)
