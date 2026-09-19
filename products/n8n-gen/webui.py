"""6번 전용 웹 화면 — 입력이 yaml 이 아니라 **한 줄에 하나씩 적는 글**이다.

잘 적는 요령 네 가지(언제·어디서·무엇을·어디로)를 화면에 붙여 둔다.
이걸 안 보고 적으면 결과가 뭉개지는데, 파일 맨 위 주석은 아무도 안 읽는다.
"""

from __future__ import annotations

from pathlib import Path

from core.webui import Field, Note, Panel, WebUI, generator_webui

BASE_DIR = Path(__file__).resolve().parent
REQUEST = BASE_DIR / "request.txt"

TIPS = (
    "**언제 시작하나요** — \"매일 아침 9시에\" / \"웹훅으로 주문이 들어오면\"",
    "**어디서 가져오나요** — \"구글시트 매출 탭에서\" / \"결제 API 에서\"",
    "**무엇을 하나요** — \"Claude 로 세 줄 요약해서\" / \"금액이 10만원 넘으면\"",
    "**어디로 보내나요** — \"슬랙 #report 채널에\" / \"고객에게 Gmail 로\"",
)


def _lines() -> str:
    if not REQUEST.is_file():
        return ""
    return "\n".join(
        line for line in REQUEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#"))


def build(program, ctx) -> WebUI:
    ui = generator_webui(
        program,
        [Field("requests", "만들고 싶은 자동화 (한 줄에 하나)", "textarea",
               default=_lines(), rows=8,
               placeholder="매일 아침 9시에 구글시트 매출 탭을 읽어 슬랙 #report 에 요약 보내기")],
        input_title="무엇을 자동화할까요",
        input_intro="한 줄에 하나씩. 여러 줄을 적으면 **여러 개를 한 번에** 만듭니다.",
        admin_intro="n8n 워크플로 JSON 을 만듭니다. credential 은 이름만 들어가고 "
                    "값은 n8n 화면에서 넣습니다.",
        client_intro="하고 싶은 자동화를 적으시면 **n8n 에 바로 올릴 수 있는 파일**을 "
                     "만들어 드립니다.")

    tip = Panel(key="tips", title="잘 적는 요령",
                intro="네 가지를 **한 문장에** 넣으면 결과가 훨씬 정확합니다.",
                lines=list(TIPS),
                notes=[Note("credential 값은 여기 적지 마세요",
                            "만들어진 JSON 에는 이름만 들어갑니다. "
                            "실제 값은 n8n 화면에서 넣으셔야 합니다.", tone="warn")])
    ui.admin.insert(1, tip)
    ui.client.insert(1, tip)
    return ui


def handle(program, ctx, action: str, form: dict) -> str:
    if action != "save":
        return "error=모르는 동작입니다"
    lines = [line.strip() for line in (form.get("requests") or "").splitlines()
             if line.strip()]
    if not lines:
        return "error=만들고 싶은 자동화를 한 줄에 하나씩 적어 주세요"
    REQUEST.write_text(
        "# 만들고 싶은 자동화를 한 줄에 하나씩. # 로 시작하면 건너뜁니다.\n"
        + "\n".join(lines) + "\n", encoding="utf-8")
    return f"saved={len(lines)}개 적었습니다. 아래에서 돌려 보세요"


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
        input_label="자동화 요구 적기", input_icon="🔌",
        output_label="workflow.json", output_icon="⚙️",
        output_intro="n8n 에 **그대로 가져올 수 있는** JSON 이 나옵니다.",
        make_label="워크플로우 만들기",
        todos=[
            Todo("무엇을 자동화할지 한 문장으로 적기", tab="input",
                 detail="'언제 → 무엇을 → 어디로' 순으로 적으면 잘 나옵니다."),
            Todo("나온 JSON 을 n8n 에 가져와 **한 번 돌려 보기**", by_hand=True),
            Todo("자격 증명(키)을 n8n 에서 직접 넣기", by_hand=True,
                 detail="JSON 에는 키를 넣지 않습니다. 넣으면 파일째로 샙니다."),
        ],
        manual_tasks=[
            ManualTask(
                task="n8n 에 가져오기",
                where="n8n → Workflows → Import from File",
                why="JSON 을 만들어 드립니다. 가져오는 것은 한 번 클릭이라 "
                    "굳이 원격으로 붙지 않습니다."),
            ManualTask(
                task="자격 증명(API 키) 넣기",
                where="n8n → Credentials",
                why="**JSON 파일에 키를 넣지 않습니다.** 파일을 주고받다 보면 "
                    "키가 그대로 새어 나갑니다. n8n 안에서 따로 넣으시면 "
                    "워크플로우를 공유해도 키는 안 나갑니다."),
            ManualTask(
                task="실제로 한 번 돌려 보기",
                where="n8n",
                why="노드 이름과 필드는 n8n 판마다 조금씩 다릅니다. "
                    "가져온 뒤 한 번 돌려 보고 빨간 노드가 있으면 고치세요."),
        ],
        troubles=[
            Trouble("가져왔더니 노드가 빨갛다",
                    "자격 증명이 아직 안 들어갔거나, n8n 판이 달라 필드 이름이 "
                    "바뀐 경우입니다. 그 노드를 열어 한 번 다시 고르시면 됩니다."),
            Trouble("원하는 서비스 노드가 안 나온다",
                    "요구를 적으실 때 **서비스 이름을 그대로** 적어 주세요. "
                    "'메신저' 보다 '슬랙' 이 낫습니다."),
            Trouble("워크플로우가 너무 복잡하다",
                    "한 번에 다 적지 마시고 **하나씩** 만들어 이어 붙이세요. "
                    "고장 났을 때 어디가 문제인지 찾기도 쉽습니다."),
        ],
        files=[
            FileLoc("자동화 요구", "products/n8n-gen/input.yaml"),
            FileLoc("만든 JSON", "products/n8n-gen/outputs/"),
        ],
    )
