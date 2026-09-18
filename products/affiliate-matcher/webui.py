"""10번 전용 웹 화면 — **대본을 붙여 넣으면 바로 본다.**

CLI 는 대본을 파일로 저장해야 돌릴 수 있다. 화면에서는 붙여 넣고 바로 누른다.

대가성 문구는 **화면에도 먼저 보여 준다.** 산출물에만 붙이면 "이게 왜 붙지"
하고 지우는 사람이 생긴다. 지우면 자격이 정지된다는 걸 화면에서 말해야 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.webui import Field, Note, Panel, Table, WebUI          # noqa: E402

from affiliate.disclosure import (                               # noqa: E402
    COUPANG, INSTAGRAM, YOUTUBE_DESCRIPTION, YOUTUBE_SPOKEN,
)
from affiliate.score import load_rates                           # noqa: E402

SAMPLES = BASE_DIR / "data" / "samples"
RATES = BASE_DIR / "data" / "commission_rates.yaml"
DRAFT = BASE_DIR / "data" / "input.txt"


def _rates_table() -> Table:
    try:
        table = load_rates(RATES)
    except Exception as exc:
        return Table(note=f"수수료율 표를 읽지 못했습니다: {exc}")
    rows = [[item.name, f"{item.rate * 100:.1f}%", f"{item.avg_price:,}원", item.source]
            for item in table.categories]
    rows.append(["**그 밖(기본)**", f"{table.default_rate * 100:.1f}%",
                 f"{table.default_avg_price:,}원", table.default_source])
    return Table(
        headers=["카테고리", "수수료율", "평균 객단가", "출처"],
        rows=rows, numeric=[1, 2],
        note=f"기준일 {table.as_of} · 쿠키 {table.cookie_hours}시간. "
             f"**추정 구간입니다.** 실제 정산은 쿠팡 화면 숫자가 기준입니다.")


def _draft_text() -> str:
    if DRAFT.is_file():
        return DRAFT.read_text(encoding="utf-8")
    first = sorted(SAMPLES.glob("*.txt"))
    return first[0].read_text(encoding="utf-8") if first else ""


def build(program, ctx) -> WebUI:
    disclosure = Panel(
        key="disclosure", title="대가성 문구",
        notes=[
            Note("이 문구 없이는 산출물이 나오지 않습니다",
                 f"**{COUPANG}**", tone="warn"),
            Note("빼면 경고 없이 자격이 정지됩니다",
                 "쿠팡파트너스 약관입니다. 지우지 마세요.", tone="bad"),
        ],
        lines=[
            f"유튜브 설명란: {YOUTUBE_DESCRIPTION}",
            f"영상에서 말로도: {YOUTUBE_SPOKEN}",
            f"인스타그램 첫 줄: {INSTAGRAM}",
            "**설명란은 접혀 있어 잘 안 읽힙니다.** 영상에서 말로도 알리는 편이 안전합니다",
        ])

    paste = Panel(
        key="paste", title="대본·글 붙여넣기",
        intro="글에서 **자연스럽게 언급할 수 있는** 상품만 찾습니다. "
              "글과 무관한 상품은 추천하지 않습니다.",
        fields=[Field("text", "본문", "textarea", default=_draft_text(), rows=12)],
        action="do:save", action_label="저장하고 돌릴 준비")

    run = Panel(
        key="run", title="매칭 돌리기",
        intro="**모의 실행은 Claude 를 부르지 않습니다.** 쿠팡 키가 없으면 "
              "검색 URL 만 만듭니다.",
        action="run", action_label="모의 실행", run_mode="dry")

    rules = Panel(
        key="rules", title="이 도구의 규칙",
        lines=["구매 의도가 **2 이하면** 삽입 계획에서 뺍니다",
               "글과 무관한 상품은 추천하지 않습니다",
               "**자가 구매를 부추기는 문구는 만들지 않습니다** (약관 위반)",
               "쿠키 유효기간은 24시간입니다"])

    rates = Panel(key="rates", title="수수료율 (추정)", table=_rates_table())

    admin = [disclosure, paste, run, rates, rules]
    client = [disclosure, paste,
              Panel(key="run", title="상품 찾기",
                    action="run", action_label="찾아보기", run_mode="dry"),
              rules]

    return WebUI(
        program_id=program.id, title=program.name,
        admin=admin, client=client,
        admin_intro="대본을 붙여 넣으면 언급할 만한 제휴 상품을 찾습니다. "
                    "**대가성 문구 없이는 산출물이 안 나옵니다.**",
        client_intro="쓰신 글에 **자연스럽게 넣을 수 있는** 상품을 찾아 드립니다.")


def handle(program, ctx, action: str, form: dict) -> str:
    if action != "save":
        return "error=모르는 동작입니다"
    text = (form.get("text") or "").strip()
    if len(text) < 100:
        return "error=본문이 너무 짧습니다. 100자 이상 붙여 넣어 주세요"
    DRAFT.parent.mkdir(parents=True, exist_ok=True)
    DRAFT.write_text(text, encoding="utf-8")
    return f"saved={len(text):,}자를 저장했습니다. 아래에서 돌려 보세요"
