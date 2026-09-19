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
        input_label="상품 적기", input_icon="📝",
        output_label="랜딩·이메일", output_icon="📧",
        output_intro="랜딩 페이지 HTML 한 장과 이메일 5통 초안이 나옵니다.",
        make_label="퍼널 만들기",
        todos=[
            Todo("파실 상품과 타깃을 **구체적으로** 적기", tab="input",
                 detail="'직장인' 보다 '이직 준비 3년차 개발자' 가 낫습니다."),
            Todo("모의로 먼저 만들어 모양 보기", tab="make"),
            Todo("나온 문구에서 **과장된 표현을 직접 지우기**", by_hand=True,
                 detail="'수익 보장', '무조건' 같은 말은 소비자 피해로 이어집니다."),
        ],
        manual_tasks=[
            ManualTask(
                task="결제 연결",
                where="크몽·스마트스토어·페이 서비스",
                why="결제는 계정과 정산이 걸려 있어 사람이 직접 붙여야 합니다. "
                    "링크 자리는 비워 두었습니다."),
            ManualTask(
                task="이메일 발송 설정",
                where="스티비·메일침프 등",
                why="초안 5통을 만들어 드립니다. **보내는 것은 발송 서비스**에 "
                    "붙이셔야 합니다. 직접 대량 발송하면 스팸으로 분류됩니다."),
            ManualTask(
                task="문구에서 과장 표현 걷어내기",
                where="나온 초안",
                why="AI 는 팔리는 문장을 쓰려다 '보장' 쪽으로 기웁니다. **고액 "
                    "부업 강의 소비자 피해가 2025년에만 42건**이고 소비자원 주의보가 "
                    "나왔습니다. 마지막으로 사람이 봐야 합니다."),
        ],
        troubles=[
            Trouble("문구가 내 말투가 아니다",
                    "타깃과 상품 설명을 더 자세히 적어 보세요. 그래도 안 맞으면 "
                    "**초안으로 쓰시고 고치시는 편**이 빠릅니다."),
            Trouble("'수익 보장' 같은 말이 들어가 있다",
                    "지우세요. 그런 표현은 광고 심의와 소비자 피해로 이어집니다. "
                    "'시간 절약', '반복 작업 자동화' 처럼 **할 수 있는 것**만 쓰세요."),
            Trouble("랜딩 페이지가 휴대폰에서 깨진다",
                    "나온 HTML 을 그대로 쓰시면 대부분 괜찮습니다. 편집기에 "
                    "붙이면서 스타일이 빠졌을 수 있으니 파일째로 올려 보세요."),
        ],
        files=[
            FileLoc("입력", "products/funnel-builder/input.yaml"),
            FileLoc("만든 퍼널", "products/funnel-builder/outputs/"),
        ],
    )
