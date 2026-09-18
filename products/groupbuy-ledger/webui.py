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
