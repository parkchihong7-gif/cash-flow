"""시트 이름과 셀 주소를 한 곳에 모은다.

수식을 만드는 쪽(`workbook.py`)과 값을 읽는 쪽(`reader.py`·테스트)이
같은 상수를 보게 해서, 한쪽만 고쳐 어긋나는 일을 막는다.
"""

from __future__ import annotations

__all__ = [
    "SHEET_SETTINGS", "SHEET_PRODUCTS", "SHEET_ORDERS",
    "SHEET_LEDGER", "SHEET_SHIPPING", "SHEET_DASHBOARD", "SHEET_ORDER",
    "SET", "PRODUCT_COLUMNS", "ORDER_COLUMNS", "SHIPPING_COLUMNS",
    "PRODUCT_HEADER_ROW", "PRODUCT_FIRST_ROW", "ORDER_HEADER_ROW", "ORDER_FIRST_ROW",
    "SUMMARY", "PRODUCT_TABLE_TITLE_ROW", "PRODUCT_TABLE_HEADER_ROW",
    "PRODUCT_TABLE_FIRST_ROW", "PRODUCT_TABLE_COLUMNS",
    "DASH", "SPARE_PRODUCT_ROWS", "SPARE_ORDER_ROWS", "MAX_DAY_ROWS", "TOP_PRODUCTS",
]

SHEET_SETTINGS = "설정"
SHEET_PRODUCTS = "상품"
SHEET_ORDERS = "주문"
SHEET_LEDGER = "정산"
SHEET_SHIPPING = "배송"
SHEET_DASHBOARD = "대시보드"

#: 통합 문서에 들어가는 순서. 사양의 시트 1~6 과 같다.
SHEET_ORDER = (
    SHEET_SETTINGS, SHEET_PRODUCTS, SHEET_ORDERS,
    SHEET_LEDGER, SHEET_SHIPPING, SHEET_DASHBOARD,
)

# ----------------------------------------------------------------- 시트 1 설정
#: 항목 이름 → (행, 설명). 값은 항상 B열에 들어간다.
SET = {
    "name": 3,
    "round": 4,
    "start": 5,
    "end": 6,
    "days": 7,
    "cost": 9,
    "price": 10,
    "margin": 11,
    "shipping_fee": 12,
    "payment_fee": 13,
    "platform_fee": 14,
    "vat_on": 15,
    "vat_rate": 16,
}

SET_LABELS = {
    "name": ("공구명", "상세페이지와 리포트에 그대로 들어갑니다"),
    "round": ("회차", "파일 이름에 쓰입니다. 예: 9월-공구"),
    "start": ("시작일", "대시보드 일별 매출표가 이 날부터 시작합니다"),
    "end": ("종료일", "시작일보다 빠르면 안 됩니다"),
    "days": ("기간(일)", "자동 계산"),
    "cost": ("기본 공급가", "상품 시트에서 개별로 덮어씁니다"),
    "price": ("기본 판매가", "상품 시트에서 개별로 덮어씁니다"),
    "margin": ("기본 마진율", "자동 계산 = 1 - 공급가 / 판매가"),
    "shipping_fee": ("배송비(건당)", "취소·환불을 뺀 유효 주문 건수만큼 곱합니다"),
    "payment_fee": ("결제수수료율", "PG·간편결제 수수료. 보통 2~3.5%"),
    "platform_fee": ("플랫폼수수료율", "자체 폼으로 받으면 0%"),
    "vat_on": ("부가세 적용", "예 = 판매가에 부가세가 포함되어 있다는 뜻"),
    "vat_rate": ("부가세율", "일반과세자 10%. 간이과세·면세면 0 으로 두세요"),
}


def setting_cell(key: str, absolute: bool = True) -> str:
    """`설정!$B$13` 같은 참조 문자열."""
    row = SET[key]
    ref = f"$B${row}" if absolute else f"B{row}"
    return f"{SHEET_SETTINGS}!{ref}"


# ----------------------------------------------------------------- 시트 2 상품
PRODUCT_HEADER_ROW = 1
PRODUCT_FIRST_ROW = 2
SPARE_PRODUCT_ROWS = 20

#: (열 문자, 머리글, 너비). 사양의 여섯 칸이 앞에 오고 도우미 칸이 뒤에 붙는다.
PRODUCT_COLUMNS = (
    ("A", "상품코드", 16),
    ("B", "옵션", 18),
    ("C", "공급가", 12),
    ("D", "판매가", 12),
    ("E", "초기재고", 10),
    ("F", "현재재고", 10),
    ("G", "유효판매수량", 12),
    ("H", "취소·환불수량", 13),
    ("I", "재고경고순번", 12),
    ("J", "조회키", 20),
)

# ----------------------------------------------------------------- 시트 3 주문
ORDER_HEADER_ROW = 1
ORDER_FIRST_ROW = 2
SPARE_ORDER_ROWS = 100

#: 사양의 열두 칸을 순서대로 두고, 택배 양식에 필요한 주소와 도우미 칸을 뒤에 붙인다.
ORDER_COLUMNS = (
    ("A", "주문일", 12),
    ("B", "주문번호", 18),
    ("C", "고객명", 10),
    ("D", "연락처", 15),
    ("E", "상품코드", 14),
    ("F", "옵션", 16),
    ("G", "수량", 7),
    ("H", "결제금액", 12),
    ("I", "결제수단", 11),
    ("J", "배송상태", 10),
    ("K", "송장번호", 16),
    ("L", "메모", 20),
    ("M", "주소", 34),
    ("N", "발송순번", 10),
    ("O", "조회키", 18),
)

# ----------------------------------------------------------------- 시트 4 정산
#: 항목 → 행. 값은 B열.
SUMMARY = {
    "gross": 3,
    "void": 4,
    "net": 5,
    "payment_fee": 6,
    "platform_fee": 7,
    "cost": 8,
    "shipping": 9,
    "vat": 10,
    "profit": 11,
    "margin": 12,
    "orders": 14,
    "void_orders": 15,
    "active_orders": 16,
    "refund_rate": 17,
    "waiting": 18,
    "avg_order": 19,
}

SUMMARY_LABELS = {
    "gross": ("총매출", "주문 시트 결제금액 전부. 취소·환불도 일단 포함합니다"),
    "void": ("취소·환불 차감", "배송상태가 취소 또는 환불인 주문 금액"),
    "net": ("순매출", "총매출 - 취소·환불 차감"),
    "payment_fee": ("결제수수료", "순매출 × 설정의 결제수수료율"),
    "platform_fee": ("플랫폼수수료", "순매출 × 설정의 플랫폼수수료율"),
    "cost": ("공급원가", "아래 상품별 실적표의 공급원가 합계"),
    "shipping": ("배송비", "유효 주문 건수 × 설정의 건당 배송비"),
    "vat": ("부가세", "부가세 적용이 '예' 일 때 순매출에서 뽑아낸 세액"),
    "profit": ("순이익", "순매출에서 위 다섯 가지를 모두 뺀 값"),
    "margin": ("순마진율", "순이익 / 순매출"),
    "orders": ("총 주문건수", ""),
    "void_orders": ("취소·환불 건수", ""),
    "active_orders": ("유효 주문건수", "총 주문건수 - 취소·환불 건수"),
    "refund_rate": ("환불률", "취소·환불 건수 / 총 주문건수"),
    "waiting": ("발송 대기건수", "배송 시트에 뽑히는 건수와 같습니다"),
    "avg_order": ("평균 객단가", "순매출 / 유효 주문건수"),
}

PRODUCT_TABLE_TITLE_ROW = 21
PRODUCT_TABLE_HEADER_ROW = 22
PRODUCT_TABLE_FIRST_ROW = 23

PRODUCT_TABLE_COLUMNS = (
    ("A", "상품코드", 16),
    ("B", "옵션", 18),
    ("C", "판매수량", 10),
    ("D", "매출", 14),
    ("E", "취소·환불", 13),
    ("F", "공급원가", 14),
    ("G", "이익", 14),
    ("H", "이익률", 10),
    ("I", "순위", 7),
)

# ----------------------------------------------------------------- 시트 5 배송
#: 택배사 업로드 양식 순서. 이 시트는 그대로 CSV 로 저장해 올릴 수 있게 머리글만 둔다.
SHIPPING_COLUMNS = (
    ("A", "받는분성명", 12),
    ("B", "받는분전화번호", 16),
    ("C", "받는분주소", 40),
    ("D", "품목명", 26),
    ("E", "수량", 7),
    ("F", "배송메시지", 20),
    ("G", "주문번호", 18),
    ("H", "송장번호", 16),
)

# --------------------------------------------------------------- 시트 6 대시보드
#: 일별 매출표가 차지할 최대 줄 수. 기간이 이보다 길면 잘린다.
MAX_DAY_ROWS = 92

#: 이익 순위에 보여줄 상품 수.
TOP_PRODUCTS = 10

DASH = {
    "daily_title": 3,
    "daily_header": 4,
    "daily_first": 5,
}


def dash_rank_rows(day_rows: int) -> dict[str, int]:
    """일별 매출표 길이에 따라 아래 표들의 시작 줄을 계산한다."""
    after_daily = DASH["daily_first"] + day_rows + 1
    rank_title = after_daily
    rank_header = rank_title + 1
    rank_first = rank_header + 1
    stock_title = rank_first + TOP_PRODUCTS + 1
    stock_header = stock_title + 1
    stock_first = stock_header + 1
    return {
        "rank_title": rank_title,
        "rank_header": rank_header,
        "rank_first": rank_first,
        "stock_title": stock_title,
        "stock_header": stock_header,
        "stock_first": stock_first,
        "chart_anchor_daily": f"F{DASH['daily_header']}",
        "chart_anchor_rank": f"F{rank_header}",
    }
