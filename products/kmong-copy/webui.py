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
        input_label="서비스 적기", input_icon="🛍",
        output_label="상세페이지·패키지", output_icon="📄",
        output_intro="상세페이지 문구, 3단 패키지, 자주 오는 문의 응답이 나옵니다. "
                     "**등록 전 정책 위반 검사**도 같이 돕니다.",
        make_label="상세페이지 만들기",
        todos=[
            Todo("파실 서비스와 범위를 적기", tab="input",
                 detail="어디까지 해 드리는지를 적어야 나중에 분쟁이 없습니다."),
            Todo("정책 위반 검사에서 걸린 문구 고치기", tab="out",
                 detail="'수익 보장' 같은 말은 등록이 반려됩니다."),
            Todo("3단 패키지 가격을 **내 시급으로** 다시 보기", by_hand=True),
        ],
        manual_tasks=[
            ManualTask(
                task="크몽에 등록하기",
                where="크몽 전문가 센터",
                why="크몽은 등록 API 를 열지 않습니다. 문구를 복사해 붙이셔야 "
                    "합니다. 브라우저를 흉내 내는 방식은 약관 위반입니다."),
            ManualTask(
                task="가격 정하기",
                where="직접",
                why="경쟁 상품 가격은 참고로 드리지만, **내 시간당 얼마를 받을지**는 "
                    "내가 정합니다. 싸게 시작하면 올리기가 어렵습니다."),
            ManualTask(
                task="포트폴리오 이미지 준비",
                where="직접",
                why="크몽은 이미지에서 클릭률이 갈립니다. 문구만으로는 부족합니다."),
        ],
        troubles=[
            Trouble("등록이 반려됐다",
                    "정책 위반 검사에서 걸린 문구를 지우셨는지 보세요. "
                    "'보장', '100%', '무조건' 은 거의 걸립니다."),
            Trouble("조회수는 있는데 문의가 없다",
                    "패키지 구분이 흐릿할 때 그렇습니다. 기본/표준/프리미엄이 "
                    "**무엇이 다른지** 한 줄로 말할 수 있어야 합니다."),
            Trouble("문의가 와도 계약으로 안 간다",
                    "나온 '문의 응답' 문구를 쓰시되, **첫 답을 빨리** 보내세요. "
                    "크몽은 응답 속도가 노출에 들어갑니다."),
        ],
        files=[
            FileLoc("서비스 정보", "products/kmong-copy/input.yaml"),
            FileLoc("만든 문구", "products/kmong-copy/outputs/"),
        ],
    )
