"""9번 전용 웹 화면 — 입력 → 생성 → 산출물.

이 상품은 **입력 파일을 채우고 돌리는** 모양이라, 껍데기는
`core.webui.generator_webui()` 를 그대로 쓴다. 여기서 정하는 것은 **칸**뿐이다.
2·3차에 화면 모양을 바꿀 때는 그 공통 함수만 고치면 일곱 종이 같이 바뀐다.
"""

from __future__ import annotations

from pathlib import Path

from core.webui import Field, WebUI, generator_webui, read_yaml_fields, write_yaml_fields

BASE_DIR = Path(__file__).resolve().parent
INPUT = BASE_DIR / "request.yaml"

INT_KEYS = ()
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
        Field("topic", "무엇을 관리하는 템플릿인가요", "text", default=value("topic", ""), required=True),
        Field("audience", "누가 쓰나요", "textarea", default=value("audience", ""), help="**좁을수록 좋습니다.** '1인 사업자' 보다 '브랜딩만 하는 1인 디자이너'"),
    ]


def build(program, ctx) -> WebUI:
    return generator_webui(
        program, _fields(),
        input_title="어떤 템플릿인가요",
        input_intro="두 줄이면 됩니다.",
        admin_intro="템플릿 구조와 설명서를 만듭니다. 노션 토큰이 있으면 바로 만들어 줍니다.",
        client_intro="주제를 적으시면 **노션 템플릿 설계와 설명서**를 만들어 드립니다.",
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
        input_label="템플릿 기획", input_icon="🗂",
        output_label="구조·판매문구·설명서", output_icon="📐",
        output_intro="데이터베이스 구조 설계, 판매 문구, 구매자용 설명서가 나옵니다.",
        make_label="템플릿 기획하기",
        todos=[
            Todo("어떤 일을 도와주는 템플릿인지 적기", tab="input"),
            Todo("나온 구조대로 **노션에서 직접 만들기**", by_hand=True,
                 detail="설계도까지 드립니다. 만드는 것은 노션에서 하셔야 합니다."),
            Todo("구매자 설명서를 템플릿 안에 넣기", by_hand=True,
                 detail="설명서가 없으면 환불 문의가 늘어납니다."),
        ],
        manual_tasks=[
            ManualTask(
                task="노션에서 실제로 만들기",
                where="노션",
                why="노션은 템플릿을 만드는 공개 API 가 제한적이고, 데이터베이스 "
                    "뷰·수식·연결은 손으로 짜야 합니다. **설계도와 문구까지** "
                    "드리고 조립은 사람이 합니다.",
                someday="노션 API 가 뷰와 수식까지 열면 일부는 자동으로 할 수 "
                        "있습니다. 지금은 안 됩니다."),
            ManualTask(
                task="템플릿 복제 링크 만들기",
                where="노션 → 공유 → 웹에 게시 → 템플릿 복제 허용",
                why="이 설정을 안 켜면 산 사람이 복제하지 못합니다. "
                    "가장 흔한 환불 사유입니다."),
        ],
        troubles=[
            Trouble("구매자가 복제가 안 된다고 한다",
                    "노션 공유 설정에서 **'템플릿 복제 허용'** 을 켜셔야 합니다. "
                    "웹에 게시만 하면 보기만 됩니다."),
            Trouble("구조가 너무 복잡하다",
                    "기획에 **쓰는 사람의 수준**을 적어 주세요. 처음 쓰는 사람용과 "
                    "익숙한 사람용은 구조가 달라야 합니다."),
            Trouble("비슷한 템플릿이 이미 많다",
                    "구조로는 차별화가 어렵습니다. **설명서와 사용 예시**에서 "
                    "갈립니다 — 그래서 설명서를 같이 만들어 드립니다."),
        ],
        files=[
            FileLoc("템플릿 기획", "products/notion-template-kit/input.yaml"),
            FileLoc("만든 설계", "products/notion-template-kit/outputs/"),
        ],
    )
