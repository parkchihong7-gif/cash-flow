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
