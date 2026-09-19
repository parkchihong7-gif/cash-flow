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
        input_label="영상 주제", input_icon="🎬",
        output_label="후크·대본", output_icon="🎤",
        output_intro="멈추게 하는 후크 10개와 타임코드가 붙은 대본 초안이 나옵니다.",
        make_label="후크 뽑기",
        todos=[
            Todo("어떤 영상인지 적기", tab="input"),
            Todo("후크 10개 중 **내가 실제로 말할 수 있는 것**을 고르기",
                 tab="out", by_hand=True,
                 detail="입에 안 붙는 문장은 읽는 티가 납니다."),
            Todo("대본을 소리 내어 읽어 보기", by_hand=True,
                 detail="눈으로 읽어 괜찮은 문장이 입으로는 안 되는 일이 많습니다."),
        ],
        manual_tasks=[
            ManualTask(
                task="촬영과 편집",
                where="직접",
                why="대본까지입니다. 말투·표정·편집 리듬은 사람마다 달라 "
                    "글로 옮길 수 없습니다."),
            ManualTask(
                task="후크 고르기",
                where="나온 10개 중에서",
                why="**10개를 다 쓰지 마세요.** 내 말투에 맞는 한둘을 고르라고 "
                    "여러 개를 냅니다. 안 맞는 후크를 억지로 읽으면 첫 3초에 "
                    "바로 나갑니다."),
        ],
        troubles=[
            Trouble("후크가 자극적이다",
                    "안 쓰시면 됩니다. 낚시성 후크는 조회수는 잠깐 오르지만 "
                    "**시청 지속시간이 떨어져 결국 손해**입니다."),
            Trouble("대본이 너무 길다/짧다",
                    "목표 길이를 입력에 적어 주세요. 안 적으면 기본값으로 잡습니다."),
            Trouble("타임코드가 실제와 안 맞는다",
                    "말하는 속도는 사람마다 다릅니다. 한 번 찍어 보시고 "
                    "본인 속도를 입력에 적으시면 맞아 갑니다."),
        ],
        files=[
            FileLoc("입력", "products/hook-script/input.yaml"),
            FileLoc("만든 대본", "products/hook-script/outputs/"),
        ],
    )
