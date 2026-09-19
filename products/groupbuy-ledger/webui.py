"""7번 전용 웹 화면 — **정산표는 숫자가 맞는지가 전부다.**

공구 정산에서 사고는 계산이 어려워서 나지 않는다. **원본이 틀려서** 난다.
그래서 화면은 계산 결과보다 먼저 *입력이 성한지*를 본다.
"""

from __future__ import annotations

import csv
from pathlib import Path

from core.webui import Field, Note, Panel, Table, WebUI

BASE_DIR = Path(__file__).resolve().parent
SAMPLES = BASE_DIR / "samples"


def _csv_table(path: Path, limit: int = 8) -> Table:
    if not path.is_file():
        return Table(note=f"{path.name} 이 없습니다.")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return Table(note=f"{path.name} 이 비어 있습니다.")
    header, body = rows[0], rows[1:]
    shown = body[:limit]
    note = f"{len(body):,}줄 중 {len(shown)}줄만 보입니다." if len(body) > limit else \
        f"{len(body):,}줄"
    return Table(headers=header, rows=shown, note=note,
                 numeric=list(range(2, len(header))))


def _check_notes() -> list[Note]:
    """정산 전에 봐야 하는 것. 원본이 틀리면 결과도 틀린다."""
    notes = []
    products = SAMPLES / "products.csv"
    orders = SAMPLES / "orders.csv"
    for path, label in ((products, "상품표"), (orders, "주문서")):
        if not path.is_file():
            notes.append(Note(f"{label}가 없습니다", f"`samples/{path.name}`", tone="bad"))
    if not notes:
        notes.append(Note("입력 파일이 둘 다 있습니다",
                          "숫자는 입력한 그대로 계산합니다. **원본이 틀리면 결과도 틀립니다.**",
                          tone="ok"))
    notes.append(Note("참여자 이름·연락처가 들어가는 파일입니다",
                      "만든 정산표를 공유하실 때 조심하세요.", tone="warn"))
    return notes


def build(program, ctx) -> WebUI:
    admin = [
        Panel(key="check", title="정산 전 점검", notes=_check_notes()),
        Panel(key="products", title="상품표", table=_csv_table(SAMPLES / "products.csv"),
              intro="공급가·판매가·초기재고입니다. 마진이 여기서 정해집니다."),
        Panel(key="orders", title="주문서", table=_csv_table(SAMPLES / "orders.csv"),
              intro="참여자별 주문입니다."),
        Panel(key="run", title="정산표 만들기",
              intro="엑셀로 만듭니다. **외부 API 를 부르지 않아 비용이 0원입니다.**",
              action="run", action_label="정산표 만들기", run_mode="dry"),
        Panel(key="caution", title="조심할 것",
              lines=["숫자는 입력한 주문서 그대로 계산합니다. 원본이 틀리면 결과도 틀립니다",
                     "**참여자 개인정보가 들어갑니다.** 파일 공유에 조심하세요",
                     "정산이 밀리면 공급처와 참여자 양쪽에서 문의가 옵니다"]),
    ]
    client = [
        Panel(key="check", title="정산 전 확인", notes=_check_notes()),
        Panel(key="orders", title="내 주문서", table=_csv_table(SAMPLES / "orders.csv")),
        Panel(key="run", title="정산표 받기",
              action="run", action_label="정산표 만들기", run_mode="dry"),
    ]
    return WebUI(
        program_id=program.id, title=program.name,
        admin=admin, client=client,
        admin_intro="공구 정산표를 엑셀로 만듭니다. **원본이 성한지부터** 보세요.",
        client_intro="주문서를 넣으시면 **참여자별 정산표**를 만들어 드립니다.")


# ══════════════════════════════════════════════════════════ 운영 콘솔
#
# 탭은 **공동구매 한 회차**를 따라간다. 상품표를 짜고 → 주문을 받고 →
# 정산한다. 회차가 끝나면 같은 일을 또 한다.
#
# '정산 전 점검' 이 첫 탭이다. 정산은 **돈이 오간 뒤에 고치기가 가장 어려운**
# 일이라, 숫자를 뽑기 전에 막는 편이 싸다.

from core.console import (                                        # noqa: E402
    Console, FileLoc, ManualTask, Tab, Todo, Trouble, tabs_from,
)


def console(program, ctx) -> Console:
    ui = build(program, ctx)
    return Console(
        program_id=program.id, title=program.name, subtitle=program.tagline,
        tabs=tabs_from(ui, [
            {"key": "check", "label": "정산 전 점검", "icon": "🔎", "group": "정산",
             "intro": "**돈이 오간 뒤에는 고치기 어렵습니다.** 뽑기 전에 봅니다.",
             "panels": ["check"]},
            {"key": "products", "label": "상품표", "icon": "🏷", "group": "자료",
             "panels": ["products"], "admin_only": True},
            {"key": "orders", "label": "주문서", "icon": "🧾", "group": "자료",
             "panels": ["orders"]},
            {"key": "run", "label": "정산표 만들기", "icon": "📊", "group": "정산",
             "panels": ["run"]},
            {"key": "caution", "label": "조심할 것", "icon": "⚠", "group": "정산",
             "panels": ["caution"]},
        ]),
        todos=[
            Todo("주문서에 빠진 줄이 없는지 보기", tab="check",
                 detail="입금 확인이 안 된 줄이 섞여 있으면 정산이 통째로 틀어집니다."),
            Todo("정산표를 뽑아 공급처와 맞춰 보기", tab="run", by_hand=True),
            Todo("환불·교환 건을 따로 표시하기", tab="orders", by_hand=True),
        ],
        manual_tasks=[
            ManualTask(
                task="입금 확인",
                where="은행 앱·계좌 내역",
                why="계좌를 프로그램에 연결하지 않습니다. **비밀번호를 저장하는 "
                    "방식은 만들지 않습니다.** 입금 여부는 눈으로 보고 표에 "
                    "적어 주세요."),
            ManualTask(
                task="공급처와 단가·수량 확정",
                where="공급처와 직접",
                why="공구는 수량에 따라 단가가 바뀌는 일이 잦습니다. 최종 단가는 "
                    "사람이 정해서 상품표에 적어야 합니다."),
            ManualTask(
                task="환불·교환 처리",
                where="직접",
                why="사유마다 처리가 달라 자동으로 하면 사고가 납니다. 표에 "
                    "표시만 해 두시면 정산에서 빼 드립니다."),
        ],
        troubles=[
            Trouble("정산 금액이 안 맞는다",
                    "입금 확인이 안 된 줄이나 환불 건이 섞여 있을 때가 대부분입니다. "
                    "**정산 전 점검** 탭이 그런 줄을 짚어 줍니다."),
            Trouble("주문서를 엑셀에서 열면 깨진다",
                    "CSV 를 엑셀에서 바로 열면 한글이 깨집니다. 엑셀에서 "
                    "'데이터 → 텍스트/CSV 가져오기' 로 UTF-8 을 골라 여세요."),
            Trouble("같은 사람이 여러 번 주문했다",
                    "그대로 두셔도 됩니다. 정산표에서 사람별로 묶어 드립니다."),
            Trouble("마진이 생각보다 적다",
                    "배송비와 포장비를 빼고 보셨는지 확인하세요. 공구 마진은 "
                    "보통 15~30% 인데, 여기에 들인 시간을 나누면 시급이 나옵니다."),
        ],
        files=[
            FileLoc("상품표·주문서 샘플", "products/groupbuy-ledger/data/samples/"),
            FileLoc("만든 정산표", "products/groupbuy-ledger/outputs/"),
        ],
        admin_intro="주문·정산·재고를 엑셀 장부로 만듭니다. "
                    "**정산 전 점검부터** 보세요.",
        client_intro="주문서를 넣으시면 정산표를 만들어 드립니다.",
        custom=True,
    )
