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
        input_label="전자책 기획", input_icon="📚",
        output_label="목차·원고·워드", output_icon="📘",
        output_intro="목차 → 원고 → 워드(.docx) 순으로 나옵니다. "
                     "**단계마다 멈춰 보실 수 있습니다.**",
        make_label="원고 만들기",
        todos=[
            Todo("주제와 읽는 사람을 적기", tab="input"),
            Todo("목차부터 만들어 **뼈대를 먼저** 보기", tab="make",
                 detail="목차가 틀리면 원고를 다 써도 못 씁니다."),
            Todo("원고에 **내 사례를 직접 넣기**", by_hand=True,
                 detail="사례가 없으면 어디서 본 듯한 책이 됩니다."),
        ],
        manual_tasks=[
            ManualTask(
                task="내 경험·사례 채우기",
                where="나온 원고",
                why="AI 는 겪지 않은 일을 지어냅니다. 그대로 팔면 **거짓말이 "
                    "되고**, 읽는 사람도 금방 압니다. 사례 자리는 비워 둡니다."),
            ManualTask(
                task="사실 확인",
                where="직접",
                why="숫자·법령·날짜는 틀릴 수 있습니다. 파는 물건이라 "
                    "틀린 정보가 들어가면 환불 사유가 됩니다."),
            ManualTask(
                task="표지 만들기",
                where="캔바 등",
                why="표지는 이 프로그램이 만들지 않습니다. 전자책은 표지에서 "
                    "절반이 갈리니 따로 챙기세요."),
        ],
        troubles=[
            Trouble("원고가 뻔하다",
                    "기획에 **내 관점**을 적으셨는지 보세요. 주제만 적으면 "
                    "일반론이 나옵니다. '나는 이렇게 생각한다' 를 넣으면 달라집니다."),
            Trouble("워드 파일이 안 열린다",
                    "`python-docx` 가 설치돼 있어야 합니다. `requirements.txt` 로 "
                    "한 번 설치하시면 됩니다."),
            Trouble("분량이 모자라다",
                    "목차 단계에서 꼭지를 늘리세요. 원고 단계에서 늘리면 "
                    "같은 말을 반복하게 됩니다."),
        ],
        files=[
            FileLoc("기획", "products/ebook-gen/input.yaml"),
            FileLoc("만든 원고", "products/ebook-gen/outputs/"),
        ],
    )
