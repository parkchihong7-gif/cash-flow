"""17번 전용 웹 화면 — 입력 → 기획서 → 승인.

껍데기는 `core.webui.generator_webui()` 를 그대로 쓴다. 여기서 정하는 것은 칸뿐이다.
아이템은 한 줄에 하나(`이름 | 브랜드 | o/x | 가격 | 가격 출처 | 검색어`)로 받는다.
"""

from __future__ import annotations

from pathlib import Path

from core.webui import Field, WebUI, generator_webui, read_yaml_fields, write_yaml_fields

BASE_DIR = Path(__file__).resolve().parent
INPUT = BASE_DIR / "shorts_input.yaml"

INT_KEYS = ("duration_sec",)
LIST_KEYS = ("items",)
REQUIRED = ("items",)


def _fields() -> list[Field]:
    saved = read_yaml_fields(INPUT)

    def value(key, fallback=""):
        got = saved.get(key, fallback)
        if isinstance(got, list):
            return "\n".join(str(item) for item in got)
        return got if got is not None else fallback

    return [
        Field("celebrity", "연예인", "text", default=value("celebrity"),
              help="**문구로만** 나옵니다. 얼굴 사진은 쓰지 않습니다. 출처가 없으면 이름도 빠집니다."),
        Field("occasion", "어디서", "text", default=value("occasion"),
              help="예: 공항 출국, 드라마 ○○ 3화, 본인 SNS"),
        Field("source_url", "출처 주소", "text", default=value("source_url"),
              help="착용 사실을 확인한 기사·공식 SNS. 없으면 '비슷한 스타일' 쇼츠가 됩니다."),
        Field("source_name", "출처 이름", "text", default=value("source_name")),
        Field("duration_sec", "길이(초)", "number", default=value("duration_sec", 15),
              help="기본 15초. 10~60초."),
        Field("items", "아이템 (한 줄에 하나)", "textarea", default=value("items"), required=True,
              help="`이름 | 브랜드 | o/x | 가격 | 가격 출처 | 검색어 | 분류` — "
                   "확인 x 는 '비슷한 스타일' 로만, 가격은 출처가 있을 때만 나옵니다. "
                   "분류는 패션·뷰티·건강식품·기타. 건강식품은 효능을 말할 수 없습니다."),
        Field("cta", "마지막에 시킬 것", "text", default=value("cta", "고정 상품 태그에서 비슷한 제품 보기")),
    ]


def build(program, ctx) -> WebUI:
    return generator_webui(
        program, _fields(),
        input_title="어떤 아이템을 소개하나요",
        input_intro="출처가 있어야 연예인 이름을 씁니다. 화면은 상품 이미지와 글자만 씁니다.",
        admin_intro="연예인 얼굴 없이, 대가성 문구·출처·AI 표시가 붙은 15초 쇼츠 기획서를 만듭니다.",
        client_intro="아이템을 적으시면 **자막·내레이션·상품 목록이 담긴 쇼츠 기획서**를 만들어 드립니다.",
    )


def handle(program, ctx, action: str, form: dict) -> str:
    if action != "save":
        return "error=모르는 동작입니다"
    return write_yaml_fields(INPUT, form, int_keys=INT_KEYS,
                             list_keys=LIST_KEYS, required=REQUIRED)


# ══════════════════════════════════════════════════════════ 운영 콘솔

from core.console import (                                        # noqa: E402
    Console, FileLoc, ManualTask, Todo, Trouble, generator_console,
)


def console(program, ctx) -> Console:
    return generator_console(
        program, build(program, ctx),
        input_label="아이템", input_icon="👜",
        output_label="쇼츠 기획서", output_icon="🎬",
        output_intro="장면표·자막 파일·설명란·상품 목록·확인표가 나옵니다.",
        make_label="기획서 만들기",
        todos=[
            Todo("아이템과 출처 적기", tab="input"),
            Todo("출처 기사를 직접 열어 아이템이 맞는지 보기", by_hand=True,
                 detail="확인 안 되면 o 대신 x 로 두세요. '비슷한 스타일' 로 바뀝니다."),
            Todo("checklist.md 확인 후 승인", tab="out", by_hand=True,
                 detail="승인은 터미널에서 `python cli.py approve <폴더> --name 이름`."),
        ],
        manual_tasks=[
            ManualTask(task="상품 이미지 모으기", where="쇼핑몰·브랜드 제공 이미지",
                       why="연예인 사진·방송 화면은 저작권·퍼블리시티권 문제라 쓰지 않습니다."),
            ManualTask(task="유튜브 쇼핑 상품 태그", where="유튜브 스튜디오 업로드 화면",
                       why="쇼츠 설명란 링크는 눌리지 않습니다. 태그는 공개 API 가 없어 손으로 합니다."),
        ],
        troubles=[
            Trouble("연예인 이름이 빠졌다",
                    "출처 주소가 비어 있어서입니다. 착용 사실을 확인한 기사 주소를 넣으세요."),
            Trouble("'막음' 이 떠서 승인이 안 된다",
                    "plan.md 의 검사 결과를 보세요. 출처 없는 가격·'원가'·'똑같은', "
                    "건강식품 효능 표현, 확인 안 된 '추천' 이 대부분입니다."),
        ],
        files=[
            FileLoc("입력", "products/celeb-shorts/shorts_input.yaml"),
            FileLoc("기획서", "products/celeb-shorts/outputs/"),
        ],
    )
