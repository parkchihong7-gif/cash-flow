"""엑셀 장부를 만든다.

**엑셀 2010 에서 열리는 함수만 쓴다.** SUM / SUMIFS / COUNTIFS / COUNTA /
INDEX / MATCH / IFERROR / IF / ROUND / RANK / AND / OR 까지.
XLOOKUP·FILTER 같은 신형 함수는 2010 에서 `#NAME?` 로 깨지므로 쓰지 않는다.
`lint.py` 의 검사기가 이 규칙을 기계적으로 확인한다.

빈 줄에 잘못된 값이 계산되지 않도록, 줄 단위 수식은 모두
`=IF($A2="","",…)` 로 감싼다. 이렇게 해야 재고 경고나 순위표가
빈 줄을 집어오지 않는다.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from groupbuy_ledger import layout as L
from groupbuy_ledger.schema import (
    PAY_METHODS, STATUSES, STOCK_WARN, VOID_STATUSES, Ledger,
)

__all__ = ["build_workbook", "WON", "PCT", "DATE_FMT"]

WON = '#,##0"원"'
PCT = '0.0%'
DATE_FMT = "yyyy-mm-dd"
INT = "#,##0"

_HEADER_FILL = PatternFill("solid", fgColor="2F4F6F")
_HELPER_FILL = PatternFill("solid", fgColor="8A97A6")
_TITLE_FONT = Font(bold=True, size=14, color="2F4F6F")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_LABEL_FONT = Font(bold=True)
_HINT_FONT = Font(size=9, color="6B7280")
_VOID_FILL = PatternFill("solid", fgColor="D9D9D9")
_WARN_FILL = PatternFill("solid", fgColor="FFC7CE")
_WARN_FONT = Font(color="9C0006", bold=True)
_THIN = Side(style="thin", color="C8CDD4")
_BOX = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

#: 사람이 손대면 안 되는 도우미 열. 머리글에 설명을 붙이고 색을 달리한다.
_HELPER_NOTE = (
    "자동 계산용 도우미 칸입니다. 지우면 다른 시트의 수식이 깨집니다.\n"
    "보기 싫으면 열을 숨기세요. 지우지는 마세요."
)
_HELPER_COLUMNS = {
    L.SHEET_PRODUCTS: ("F", "G", "H", "I", "J"),
    L.SHEET_ORDERS: ("N", "O"),
}


# --------------------------------------------------------------------- 도우미
def _write_header(ws, columns, row: int, sheet_name: str = "") -> None:
    helpers = _HELPER_COLUMNS.get(sheet_name, ())
    for letter, title, width in columns:
        cell = ws[f"{letter}{row}"]
        cell.value = title
        cell.font = _HEADER_FONT
        cell.fill = _HELPER_FILL if letter in helpers else _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _BOX
        ws.column_dimensions[letter].width = width
        if letter in helpers:
            cell.comment = Comment(_HELPER_NOTE, "장부 생성기")
    ws.row_dimensions[row].height = 22


def _title(ws, text: str, cell: str = "A1") -> None:
    ws[cell] = text
    ws[cell].font = _TITLE_FONT


def _range(sheet: str, column: str, first: int, last: int) -> str:
    return f"{sheet}!${column}${first}:${column}${last}"


# --------------------------------------------------------------- 시트 1 설정
def _build_settings(ws, ledger: Ledger) -> None:
    settings = ledger.settings
    _title(ws, "공구 정산 장부 — 설정")
    ws["A2"] = "여기 값을 바꾸면 정산·대시보드가 전부 다시 계산됩니다."
    ws["A2"].font = _HINT_FONT
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 52

    values = {
        "name": settings.name,
        "round": settings.round_label,
        "start": settings.start,
        "end": settings.end,
        "days": f"=IFERROR({L.setting_cell('end')}-{L.setting_cell('start')}+1,\"\")",
        "cost": settings.default_cost,
        "price": settings.default_price,
        "margin": f"=IFERROR(1-{L.setting_cell('cost')}/{L.setting_cell('price')},\"\")",
        "shipping_fee": settings.shipping_fee,
        "payment_fee": settings.payment_fee_rate,
        "platform_fee": settings.platform_fee_rate,
        "vat_on": "예" if settings.vat_included else "아니오",
        "vat_rate": settings.vat_rate,
    }
    formats = {
        "start": DATE_FMT, "end": DATE_FMT, "days": INT,
        "cost": WON, "price": WON, "margin": PCT, "shipping_fee": WON,
        "payment_fee": "0.00%", "platform_fee": "0.00%", "vat_rate": "0.0%",
    }
    computed = {"days", "margin"}

    for key, row in L.SET.items():
        label, hint = L.SET_LABELS[key]
        ws[f"A{row}"] = label
        ws[f"A{row}"].font = _LABEL_FONT
        cell = ws[f"B{row}"]
        cell.value = values[key]
        cell.border = _BOX
        if key in formats:
            cell.number_format = formats[key]
        if key in computed:
            cell.fill = PatternFill("solid", fgColor="EEF2F7")
            hint = f"{hint} · 직접 고치지 마세요"
        ws[f"C{row}"] = hint
        ws[f"C{row}"].font = _HINT_FONT

    yes_no = DataValidation(type="list", formula1='"예,아니오"', allow_blank=False)
    yes_no.error = "'예' 또는 '아니오' 만 넣을 수 있습니다."
    ws.add_data_validation(yes_no)
    yes_no.add(ws[f"B{L.SET['vat_on']}"])


# --------------------------------------------------------------- 시트 2 상품
def _build_products(ws, ledger: Ledger, rows: dict) -> None:
    first, last = L.PRODUCT_FIRST_ROW, rows["product_last"]
    order_last = rows["order_last"]
    qty = _range(L.SHEET_ORDERS, "G", L.ORDER_FIRST_ROW, order_last)
    status = _range(L.SHEET_ORDERS, "J", L.ORDER_FIRST_ROW, order_last)
    okey = _range(L.SHEET_ORDERS, "O", L.ORDER_FIRST_ROW, order_last)

    _write_header(ws, L.PRODUCT_COLUMNS, L.PRODUCT_HEADER_ROW, L.SHEET_PRODUCTS)
    ws.freeze_panes = "A2"

    for index in range(first, last + 1):
        product = ledger.products[index - first] if index - first < len(ledger.products) else None
        if product is not None:
            ws[f"A{index}"] = product.code
            ws[f"B{index}"] = product.option
            ws[f"C{index}"] = product.cost
            ws[f"D{index}"] = product.price
            ws[f"E{index}"] = product.initial_stock

        sold = (f'SUMIFS({qty},{okey},$J{index})'
                f'-SUMIFS({qty},{okey},$J{index},{status},"취소")'
                f'-SUMIFS({qty},{okey},$J{index},{status},"환불")')
        voided = (f'SUMIFS({qty},{okey},$J{index},{status},"취소")'
                  f'+SUMIFS({qty},{okey},$J{index},{status},"환불")')

        ws[f"F{index}"] = f'=IF($A{index}="","",$E{index}-$G{index})'
        ws[f"G{index}"] = f'=IF($A{index}="","",{sold})'
        ws[f"H{index}"] = f'=IF($A{index}="","",{voided})'
        ws[f"I{index}"] = (
            f'=IF($A{index}="","",IF($F{index}<{STOCK_WARN},'
            f'COUNTIFS($F${first}:$F{index},"<{STOCK_WARN}"),""))'
        )
        ws[f"J{index}"] = f'=IF($A{index}="","",$A{index}&"|"&$B{index})'

        for letter, _, _ in L.PRODUCT_COLUMNS:
            ws[f"{letter}{index}"].border = _BOX
        for letter in ("C", "D"):
            ws[f"{letter}{index}"].number_format = WON
        for letter in ("E", "F", "G", "H"):
            ws[f"{letter}{index}"].number_format = INT

    ws.conditional_formatting.add(
        f"F{first}:F{last}",
        FormulaRule(formula=[f'AND($A{first}<>"",$F{first}<{STOCK_WARN})'],
                    fill=_WARN_FILL, font=_WARN_FONT, stopIfTrue=False),
    )


# --------------------------------------------------------------- 시트 3 주문
def _build_orders(ws, ledger: Ledger, rows: dict) -> None:
    first, last = L.ORDER_FIRST_ROW, rows["order_last"]
    product_last = rows["product_last"]

    _write_header(ws, L.ORDER_COLUMNS, L.ORDER_HEADER_ROW, L.SHEET_ORDERS)
    ws.freeze_panes = "C2"

    for index in range(first, last + 1):
        order = ledger.orders[index - first] if index - first < len(ledger.orders) else None
        if order is not None:
            ws[f"A{index}"] = order.order_date
            ws[f"B{index}"] = order.order_no
            ws[f"C{index}"] = order.customer
            ws[f"D{index}"] = order.phone
            ws[f"E{index}"] = order.code
            ws[f"F{index}"] = order.option
            ws[f"G{index}"] = order.qty
            ws[f"H{index}"] = order.amount
            ws[f"I{index}"] = order.method
            ws[f"J{index}"] = order.status
            ws[f"K{index}"] = order.invoice
            ws[f"L{index}"] = order.memo
            ws[f"M{index}"] = order.address

        ws[f"N{index}"] = (
            f'=IF($J{index}="대기",COUNTIFS($J${first}:$J{index},"대기"),"")'
        )
        ws[f"O{index}"] = f'=IF($E{index}="","",$E{index}&"|"&$F{index})'

        ws[f"A{index}"].number_format = DATE_FMT
        ws[f"D{index}"].number_format = "@"   # 010 의 앞자리 0 이 날아가지 않게
        ws[f"K{index}"].number_format = "@"
        ws[f"G{index}"].number_format = INT
        ws[f"H{index}"].number_format = WON
        for letter, _, _ in L.ORDER_COLUMNS:
            ws[f"{letter}{index}"].border = _BOX

    status_dv = DataValidation(
        type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True)
    status_dv.error = "대기 / 발송 / 완료 / 취소 / 환불 중에서 고르세요."
    status_dv.errorTitle = "배송상태"
    ws.add_data_validation(status_dv)
    status_dv.add(f"J{first}:J{last}")

    method_dv = DataValidation(
        type="list", formula1='"' + ",".join(PAY_METHODS) + '"', allow_blank=True)
    method_dv.errorTitle = "결제수단"
    ws.add_data_validation(method_dv)
    method_dv.add(f"I{first}:I{last}")

    code_dv = DataValidation(
        type="list",
        formula1=f"={L.SHEET_PRODUCTS}!$A${L.PRODUCT_FIRST_ROW}:$A${product_last}",
        allow_blank=True)
    code_dv.error = "상품 시트에 있는 상품코드만 넣을 수 있습니다."
    code_dv.errorTitle = "상품코드"
    ws.add_data_validation(code_dv)
    code_dv.add(f"E{first}:E{last}")

    condition = "OR(" + ",".join(f'$J{first}="{s}"' for s in VOID_STATUSES) + ")"
    ws.conditional_formatting.add(
        f"A{first}:O{last}",
        FormulaRule(formula=[condition], fill=_VOID_FILL,
                    font=Font(color="808080", strike=True), stopIfTrue=False),
    )


# --------------------------------------------------------------- 시트 4 정산
def _build_ledger_sheet(ws, ledger: Ledger, rows: dict) -> None:
    order_last = rows["order_last"]
    product_first, product_last = L.PRODUCT_FIRST_ROW, rows["product_last"]
    table_first, table_last = L.PRODUCT_TABLE_FIRST_ROW, rows["table_last"]

    amount = _range(L.SHEET_ORDERS, "H", L.ORDER_FIRST_ROW, order_last)
    qty = _range(L.SHEET_ORDERS, "G", L.ORDER_FIRST_ROW, order_last)
    status = _range(L.SHEET_ORDERS, "J", L.ORDER_FIRST_ROW, order_last)
    numbers = _range(L.SHEET_ORDERS, "B", L.ORDER_FIRST_ROW, order_last)
    okey = _range(L.SHEET_ORDERS, "O", L.ORDER_FIRST_ROW, order_last)
    cost_col = _range(L.SHEET_PRODUCTS, "C", product_first, product_last)
    key_col = _range(L.SHEET_PRODUCTS, "J", product_first, product_last)

    _title(ws, "정산 요약")
    ws["A2"] = "모든 값이 수식입니다. 주문 시트만 채우면 여기가 따라 바뀝니다."
    ws["A2"].font = _HINT_FONT
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 46

    void_amount = "+".join(f'SUMIFS({amount},{status},"{s}")' for s in VOID_STATUSES)
    void_count = "+".join(f'COUNTIFS({status},"{s}")' for s in VOID_STATUSES)

    formulas = {
        "gross": f"=SUM({amount})",
        "void": f"={void_amount}",
        "net": "=$B$3-$B$4",
        "payment_fee": f"=ROUND($B$5*{L.setting_cell('payment_fee')},0)",
        "platform_fee": f"=ROUND($B$5*{L.setting_cell('platform_fee')},0)",
        "cost": f"=SUM($F${table_first}:$F${table_last})",
        "shipping": f"=$B$16*{L.setting_cell('shipping_fee')}",
        "vat": (f'=IF({L.setting_cell("vat_on")}="예",'
                f'ROUND($B$5/(1+{L.setting_cell("vat_rate")})'
                f'*{L.setting_cell("vat_rate")},0),0)'),
        "profit": "=$B$5-$B$6-$B$7-$B$8-$B$9-$B$10",
        "margin": '=IFERROR($B$11/$B$5,"")',
        "orders": f"=COUNTA({numbers})",
        "void_orders": f"={void_count}",
        "active_orders": "=$B$14-$B$15",
        "refund_rate": '=IFERROR($B$15/$B$14,"")',
        "waiting": f'=COUNTIFS({status},"대기")',
        "avg_order": '=IFERROR($B$5/$B$16,"")',
    }
    money = {"gross", "void", "net", "payment_fee", "platform_fee",
             "cost", "shipping", "vat", "profit", "avg_order"}
    rates = {"margin", "refund_rate"}

    for key, row in L.SUMMARY.items():
        label, hint = L.SUMMARY_LABELS[key]
        ws[f"A{row}"] = label
        ws[f"A{row}"].font = _LABEL_FONT
        cell = ws[f"B{row}"]
        cell.value = formulas[key]
        cell.border = _BOX
        cell.number_format = WON if key in money else (PCT if key in rates else INT)
        if key == "profit":
            cell.font = Font(bold=True, size=12)
        if hint:
            ws[f"C{row}"] = hint
            ws[f"C{row}"].font = _HINT_FONT

    _title(ws, "상품별 실적", f"A{L.PRODUCT_TABLE_TITLE_ROW}")
    _write_header(ws, L.PRODUCT_TABLE_COLUMNS, L.PRODUCT_TABLE_HEADER_ROW)

    for index in range(table_first, table_last + 1):
        source = product_first + (index - table_first)
        key_ref = f'$A{index}&"|"&$B{index}'
        sold = (f'SUMIFS({qty},{okey},{key_ref})'
                f'-SUMIFS({qty},{okey},{key_ref},{status},"취소")'
                f'-SUMIFS({qty},{okey},{key_ref},{status},"환불")')
        revenue = (f'SUMIFS({amount},{okey},{key_ref})'
                   f'-SUMIFS({amount},{okey},{key_ref},{status},"취소")'
                   f'-SUMIFS({amount},{okey},{key_ref},{status},"환불")')
        voided = (f'SUMIFS({amount},{okey},{key_ref},{status},"취소")'
                  f'+SUMIFS({amount},{okey},{key_ref},{status},"환불")')

        ws[f"A{index}"] = f'=IF({L.SHEET_PRODUCTS}!$A{source}="","",{L.SHEET_PRODUCTS}!$A{source})'
        ws[f"B{index}"] = f'=IF({L.SHEET_PRODUCTS}!$A{source}="","",{L.SHEET_PRODUCTS}!$B{source})'
        ws[f"C{index}"] = f'=IF($A{index}="","",{sold})'
        ws[f"D{index}"] = f'=IF($A{index}="","",{revenue})'
        ws[f"E{index}"] = f'=IF($A{index}="","",{voided})'
        ws[f"F{index}"] = (f'=IFERROR($C{index}*INDEX({cost_col},'
                           f'MATCH({key_ref},{key_col},0)),0)')
        ws[f"G{index}"] = f'=IF($A{index}="","",$D{index}-$F{index})'
        ws[f"H{index}"] = f'=IFERROR($G{index}/$D{index},"")'
        ws[f"I{index}"] = (
            f'=IF($A{index}="","",RANK($G{index},$G${table_first}:$G${table_last})'
            f'+COUNTIFS($G${table_first}:$G{index},$G{index})-1)'
        )

        for letter in ("D", "E", "F", "G"):
            ws[f"{letter}{index}"].number_format = WON
        ws[f"C{index}"].number_format = INT
        ws[f"H{index}"].number_format = PCT
        for letter, _, _ in L.PRODUCT_TABLE_COLUMNS:
            ws[f"{letter}{index}"].border = _BOX


# --------------------------------------------------------------- 시트 5 배송
def _build_shipping(ws, rows: dict) -> None:
    order_last = rows["order_last"]
    first, last = 2, rows["ship_last"]
    seq = _range(L.SHEET_ORDERS, "N", L.ORDER_FIRST_ROW, order_last)

    _write_header(ws, L.SHIPPING_COLUMNS, 1)
    ws.freeze_panes = "A2"

    #: 배송 시트 열 → 주문 시트 열. 택배사 양식 순서에 맞춘다.
    pulls = {"A": "C", "B": "D", "C": "M", "E": "G", "F": "L", "G": "B", "H": "K"}

    for index in range(first, last + 1):
        nth = index - first + 1

        def pick(column: str, n: int = nth) -> str:
            source = _range(L.SHEET_ORDERS, column, L.ORDER_FIRST_ROW, order_last)
            return f"INDEX({source},MATCH({n},{seq},0))"

        for target, source in pulls.items():
            ws[f"{target}{index}"] = f'=IFERROR({pick(source)},"")'
        ws[f"D{index}"] = f'=IFERROR({pick("E")}&" "&{pick("F")},"")'

        ws[f"B{index}"].number_format = "@"
        ws[f"H{index}"].number_format = "@"
        ws[f"E{index}"].number_format = INT
        for letter, _, _ in L.SHIPPING_COLUMNS:
            ws[f"{letter}{index}"].border = _BOX


# ------------------------------------------------------------- 시트 6 대시보드
def _build_dashboard(ws, ledger: Ledger, rows: dict) -> None:
    order_last = rows["order_last"]
    product_first, product_last = L.PRODUCT_FIRST_ROW, rows["product_last"]
    table_first, table_last = L.PRODUCT_TABLE_FIRST_ROW, rows["table_last"]
    day_rows = rows["day_rows"]
    anchors = L.dash_rank_rows(day_rows)

    amount = _range(L.SHEET_ORDERS, "H", L.ORDER_FIRST_ROW, order_last)
    dates = _range(L.SHEET_ORDERS, "A", L.ORDER_FIRST_ROW, order_last)
    status = _range(L.SHEET_ORDERS, "J", L.ORDER_FIRST_ROW, order_last)

    _title(ws, "대시보드")
    ws["A2"] = "표와 차트 모두 수식입니다. 주문 시트가 바뀌면 같이 바뀝니다."
    ws["A2"].font = _HINT_FONT
    for letter, width in (("A", 16), ("B", 16), ("C", 12), ("D", 16), ("E", 12)):
        ws.column_dimensions[letter].width = width

    # 일별 매출 추이
    _title(ws, "일별 매출 추이", f"A{L.DASH['daily_title']}")
    _write_header(ws, (("A", "일자", 16), ("B", "매출", 16), ("C", "주문건수", 12)),
                  L.DASH["daily_header"])
    daily_first = L.DASH["daily_first"]
    for offset in range(day_rows):
        index = daily_first + offset
        start, end = L.setting_cell("start"), L.setting_cell("end")
        ws[f"A{index}"] = (f'=IFERROR(IF({start}+{offset}>{end},"",{start}+{offset}),"")')
        ws[f"B{index}"] = (
            f'=IF($A{index}="","",SUMIFS({amount},{dates},$A{index})'
            f'-SUMIFS({amount},{dates},$A{index},{status},"취소")'
            f'-SUMIFS({amount},{dates},$A{index},{status},"환불"))'
        )
        ws[f"C{index}"] = f'=IF($A{index}="","",COUNTIFS({dates},$A{index}))'
        ws[f"A{index}"].number_format = DATE_FMT
        ws[f"B{index}"].number_format = WON
        ws[f"C{index}"].number_format = INT
        for letter in ("A", "B", "C"):
            ws[f"{letter}{index}"].border = _BOX

    line = LineChart()
    line.title = "일별 매출 추이"
    line.height, line.width = 7.5, 17
    line.y_axis.title = "매출(원)"
    line.add_data(Reference(ws, min_col=2, min_row=L.DASH["daily_header"],
                            max_row=daily_first + day_rows - 1), titles_from_data=True)
    line.set_categories(Reference(ws, min_col=1, min_row=daily_first,
                                  max_row=daily_first + day_rows - 1))
    ws.add_chart(line, anchors["chart_anchor_daily"])

    # 상품별 이익 순위
    rank_first = anchors["rank_first"]
    _title(ws, "상품별 이익 순위", f"A{anchors['rank_title']}")
    _write_header(ws, (("A", "순위", 8), ("B", "상품코드", 16),
                       ("C", "옵션", 18), ("D", "이익", 16)), anchors["rank_header"])
    rank_col = _range(L.SHEET_LEDGER, "I", table_first, table_last)
    top = min(L.TOP_PRODUCTS, len(ledger.products))
    for nth in range(1, top + 1):
        index = rank_first + nth - 1
        ws[f"A{index}"] = nth
        for target, source in (("B", "A"), ("C", "B"), ("D", "G")):
            column = _range(L.SHEET_LEDGER, source, table_first, table_last)
            ws[f"{target}{index}"] = (
                f'=IFERROR(INDEX({column},MATCH({nth},{rank_col},0)),"")')
        ws[f"D{index}"].number_format = WON
        for letter in ("A", "B", "C", "D"):
            ws[f"{letter}{index}"].border = _BOX

    bar = BarChart()
    bar.type, bar.title = "bar", "상품별 이익 순위"
    bar.height, bar.width = 7.5, 17
    bar.add_data(Reference(ws, min_col=4, min_row=anchors["rank_header"],
                           max_row=rank_first + top - 1), titles_from_data=True)
    bar.set_categories(Reference(ws, min_col=2, min_row=rank_first,
                                 max_row=rank_first + top - 1))
    ws.add_chart(bar, anchors["chart_anchor_rank"])

    # 재고 경고
    stock_first = anchors["stock_first"]
    _title(ws, f"재고 경고 (현재재고 {STOCK_WARN}개 미만)", f"A{anchors['stock_title']}")
    _write_header(ws, (("A", "상품코드", 16), ("B", "옵션", 18), ("C", "현재재고", 12)),
                  anchors["stock_header"])
    warn_col = _range(L.SHEET_PRODUCTS, "I", product_first, product_last)
    for nth in range(1, len(ledger.products) + 1):
        index = stock_first + nth - 1
        for target, source in (("A", "A"), ("B", "B"), ("C", "F")):
            column = _range(L.SHEET_PRODUCTS, source, product_first, product_last)
            ws[f"{target}{index}"] = (
                f'=IFERROR(INDEX({column},MATCH({nth},{warn_col},0)),"")')
        ws[f"C{index}"].number_format = INT
        for letter in ("A", "B", "C"):
            ws[f"{letter}{index}"].border = _BOX

    stock_last = stock_first + len(ledger.products) - 1
    ws.conditional_formatting.add(
        f"A{stock_first}:C{stock_last}",
        FormulaRule(formula=[f'$A{stock_first}<>""'],
                    fill=_WARN_FILL, font=_WARN_FONT, stopIfTrue=False),
    )


# --------------------------------------------------------------------- 진입점
def _row_plan(ledger: Ledger) -> dict:
    """줄 수를 미리 정한다. 빈 줄을 조금 남겨 손으로 추가할 수 있게 한다."""
    product_rows = len(ledger.products) + L.SPARE_PRODUCT_ROWS
    order_rows = len(ledger.orders) + L.SPARE_ORDER_ROWS
    return {
        "product_last": L.PRODUCT_FIRST_ROW + product_rows - 1,
        "order_last": L.ORDER_FIRST_ROW + order_rows - 1,
        "table_last": L.PRODUCT_TABLE_FIRST_ROW + product_rows - 1,
        "ship_last": 1 + order_rows,
        "day_rows": min(ledger.settings.days, L.MAX_DAY_ROWS),
    }


def build_workbook(ledger: Ledger, path: Path) -> Path:
    """장부 전체를 새로 만들어 저장한다."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = {name: workbook.create_sheet(name) for name in L.SHEET_ORDER}
    rows = _row_plan(ledger)

    _build_settings(sheets[L.SHEET_SETTINGS], ledger)
    _build_products(sheets[L.SHEET_PRODUCTS], ledger, rows)
    _build_orders(sheets[L.SHEET_ORDERS], ledger, rows)
    _build_ledger_sheet(sheets[L.SHEET_LEDGER], ledger, rows)
    _build_shipping(sheets[L.SHEET_SHIPPING], rows)
    _build_dashboard(sheets[L.SHEET_DASHBOARD], ledger, rows)

    workbook.properties.title = f"{ledger.settings.name} 공구 정산 장부"
    workbook.properties.creator = "공구 정산 엑셀 자동 생성기"

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path
