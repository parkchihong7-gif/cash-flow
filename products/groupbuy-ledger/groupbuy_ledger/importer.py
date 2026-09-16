"""주문 CSV 를 장부의 주문 시트 모양으로 옮긴다.

쇼핑몰·구글폼마다 컬럼 이름이 달라서, 어떤 이름을 어느 칸으로 볼지는
`mapping.yaml` 이 정한다. 코드를 고치지 않고 매핑 파일만 고쳐 쓸 수 있게 한 것이다.

**조용히 넘어가지 않는다.** 못 알아본 컬럼, 모르는 배송상태, 상품 시트에 없는
상품코드, 이미 있는 주문번호는 전부 세어서 알려 준다.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from groupbuy_ledger.schema import STATUSES, Ledger, Order

__all__ = ["ImportResult", "load_mapping", "import_orders", "read_orders_csv",
           "read_products_csv", "ImportError_"]

#: CSV 를 열어 볼 인코딩 순서. 스마트스토어는 cp949 로 내려주는 경우가 많다.
ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr")

#: 장부에 꼭 있어야 하는 칸.
REQUIRED = ("주문일", "주문번호", "상품코드", "수량", "결제금액")

_DATE_PATTERNS = (
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y년 %m월 %d일",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S",
    "%Y.%m.%d %H:%M:%S", "%Y.%m.%d. %H:%M:%S", "%m/%d/%Y", "%m/%d/%Y %H:%M:%S",
)


class ImportError_(RuntimeError):
    """CSV 를 읽을 수 없을 때. 내장 ImportError 와 헷갈리지 않게 밑줄을 붙였다."""


@dataclass
class ImportResult:
    """가져오기 결과. 사람이 확인해야 할 것을 전부 담는다."""

    added: list[Order] = field(default_factory=list)
    duplicated: list[str] = field(default_factory=list)
    unknown_products: list[str] = field(default_factory=list)
    unknown_status: list[str] = field(default_factory=list)
    skipped_rows: list[str] = field(default_factory=list)
    matched_columns: dict[str, str] = field(default_factory=dict)
    missing_columns: list[str] = field(default_factory=list)
    csv_headers: list[str] = field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        return bool(self.duplicated or self.unknown_products
                    or self.unknown_status or self.skipped_rows)

    def report_lines(self) -> list[str]:
        lines = [f"  주문 {len(self.added)}건을 가져왔습니다"]
        if self.duplicated:
            lines.append(f"  · 이미 있는 주문번호 {len(self.duplicated)}건은 건너뛰었습니다"
                         f" ({', '.join(self.duplicated[:5])}"
                         f"{' 외' if len(self.duplicated) > 5 else ''})")
        if self.unknown_products:
            lines.append("  ⚠ 상품 시트에 없는 상품코드가 있습니다: "
                         + ", ".join(self.unknown_products[:5]))
            lines.append("    상품 시트에 추가하지 않으면 공급원가가 0원으로 잡힙니다")
        if self.unknown_status:
            lines.append("  ⚠ 모르는 배송상태를 '대기' 로 두었습니다: "
                         + ", ".join(self.unknown_status[:5]))
            lines.append("    mapping.yaml 의 status 에 추가하면 다음부터 알아봅니다")
        if self.skipped_rows:
            lines.append(f"  ⚠ 읽지 못한 줄 {len(self.skipped_rows)}개: "
                         + "; ".join(self.skipped_rows[:3]))
        return lines


def _normalize(text: str) -> str:
    """컬럼 이름 비교용. 공백과 괄호 안 설명을 지운다."""
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


def load_mapping(path: Path) -> dict:
    """매핑 파일을 읽는다."""
    path = Path(path)
    if not path.is_file():
        raise ImportError_(f"매핑 파일이 없습니다: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "columns" not in data:
        raise ImportError_(f"{path.name} 에 columns 항목이 없습니다")
    return data


def _read_rows(path: Path) -> tuple[list[dict], list[str]]:
    """인코딩을 바꿔 가며 CSV 를 읽는다."""
    path = Path(path)
    if not path.is_file():
        raise ImportError_(f"CSV 파일이 없습니다: {path}")

    last_error: Exception | None = None
    for encoding in ENCODINGS:
        try:
            text = path.read_text(encoding=encoding)
        except (UnicodeDecodeError, LookupError) as exc:
            last_error = exc
            continue
        reader = csv.DictReader(text.splitlines())
        rows = [row for row in reader]
        if reader.fieldnames:
            return rows, [f or "" for f in reader.fieldnames]
    raise ImportError_(
        f"{path.name} 의 인코딩을 알아내지 못했습니다. "
        f"UTF-8 로 저장한 뒤 다시 시도하세요. ({last_error})"
    )


def _match_columns(headers: list[str], columns: dict) -> dict[str, str]:
    """장부 칸 → CSV 컬럼 이름."""
    lookup = {_normalize(h): h for h in headers}
    matched: dict[str, str] = {}
    for field_name, candidates in columns.items():
        for candidate in candidates or []:
            header = lookup.get(_normalize(candidate))
            if header is not None:
                matched[field_name] = header
                break
    return matched


def _flip(groups: dict | None) -> dict[str, str]:
    """{표준값: [별칭들]} 을 {별칭: 표준값} 으로 뒤집는다."""
    flipped: dict[str, str] = {}
    for standard, aliases in (groups or {}).items():
        for alias in aliases or []:
            flipped[_normalize(alias)] = standard
    return flipped


def _parse_date(value: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in _DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    found = re.search(r"(\d{4})[-./년\s]+(\d{1,2})[-./월\s]+(\d{1,2})", text)
    if found:
        year, month, day = (int(g) for g in found.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def _parse_number(value: str, default: int = 0) -> int:
    text = re.sub(r"[^\d.\-]", "", str(value or ""))
    if not text or text in ("-", "."):
        return default
    try:
        return int(round(float(text)))
    except ValueError:
        return default


def read_products_csv(path: Path, default_cost: int, default_price: int) -> list[dict]:
    """상품 CSV 를 읽는다. 컬럼 이름은 상품코드/옵션/공급가/판매가/초기재고."""
    rows, headers = _read_rows(path)
    lookup = {_normalize(h): h for h in headers}
    wanted = {"상품코드": "code", "옵션": "option", "공급가": "cost",
              "판매가": "price", "초기재고": "initial_stock"}
    missing = [k for k in ("상품코드",) if _normalize(k) not in lookup]
    if missing:
        raise ImportError_(
            f"{Path(path).name} 에 '상품코드' 컬럼이 없습니다. "
            f"찾은 컬럼: {', '.join(headers)}"
        )

    products = []
    for row in rows:
        code = str(row.get(lookup[_normalize('상품코드')], "") or "").strip()
        if not code:
            continue
        item = {"code": code, "option": "", "cost": default_cost,
                "price": default_price, "initial_stock": 0}
        for korean, field_name in wanted.items():
            header = lookup.get(_normalize(korean))
            if header is None:
                continue
            raw = row.get(header, "")
            if field_name in ("cost", "price", "initial_stock"):
                fallback = item[field_name]
                item[field_name] = _parse_number(raw, fallback)
            elif field_name == "option":
                item[field_name] = str(raw or "").strip()
        products.append(item)
    if not products:
        raise ImportError_(f"{Path(path).name} 에서 상품을 한 줄도 읽지 못했습니다")
    return products


def read_orders_csv(path: Path, mapping: dict, known_keys: set[str],
                    existing_numbers: set[str]) -> ImportResult:
    """주문 CSV 를 읽어 Order 목록으로 만든다."""
    rows, headers = _read_rows(path)
    result = ImportResult(csv_headers=headers)
    result.matched_columns = _match_columns(headers, mapping["columns"])
    result.missing_columns = [c for c in REQUIRED if c not in result.matched_columns]
    if result.missing_columns:
        raise ImportError_(
            "CSV 에서 꼭 필요한 컬럼을 찾지 못했습니다: "
            + ", ".join(result.missing_columns)
            + f"\n  CSV 의 컬럼: {', '.join(headers)}"
            + "\n  mapping.yaml 의 columns 에 이 이름을 후보로 추가하세요."
        )

    status_alias = _flip(mapping.get("status"))
    method_alias = _flip(mapping.get("method"))
    seen = set(existing_numbers)

    def value(row: dict, field_name: str) -> str:
        header = result.matched_columns.get(field_name)
        return str(row.get(header, "") or "").strip() if header else ""

    for line, row in enumerate(rows, start=2):
        order_no = value(row, "주문번호")
        if not order_no:
            continue
        if order_no in seen:
            result.duplicated.append(order_no)
            continue

        order_date = _parse_date(value(row, "주문일"))
        if order_date is None:
            result.skipped_rows.append(f"{line}번째 줄: 주문일을 읽지 못했습니다")
            continue

        raw_status = value(row, "배송상태")
        status = status_alias.get(_normalize(raw_status), "")
        if not status:
            status = raw_status if raw_status in STATUSES else "대기"
            if raw_status and status == "대기" and raw_status not in STATUSES:
                result.unknown_status.append(raw_status)

        raw_method = value(row, "결제수단")
        method = method_alias.get(_normalize(raw_method)) or (raw_method or "카드")

        try:
            order = Order(
                order_date=order_date, order_no=order_no,
                customer=value(row, "고객명"), phone=value(row, "연락처"),
                code=value(row, "상품코드"), option=value(row, "옵션"),
                qty=max(1, _parse_number(value(row, "수량"), 1)),
                amount=_parse_number(value(row, "결제금액")),
                method=method, status=status,
                invoice=value(row, "송장번호"), memo=value(row, "메모"),
                address=value(row, "주소"),
            )
        except ValueError as exc:
            result.skipped_rows.append(f"{line}번째 줄: {exc}")
            continue

        seen.add(order_no)
        result.added.append(order)
        if known_keys and order.key not in known_keys:
            result.unknown_products.append(order.key.replace("|", " "))

    result.unknown_products = sorted(set(result.unknown_products))
    result.unknown_status = sorted(set(result.unknown_status))
    return result


def import_orders(ledger: Ledger, csv_path: Path, mapping_path: Path) -> tuple[Ledger, ImportResult]:
    """장부에 주문을 합친 새 장부를 돌려준다. 원본은 건드리지 않는다."""
    mapping = load_mapping(mapping_path)
    result = read_orders_csv(
        csv_path, mapping,
        known_keys=ledger.product_keys,
        existing_numbers={o.order_no for o in ledger.orders},
    )
    merged = Ledger(
        settings=ledger.settings,
        products=ledger.products,
        orders=[*ledger.orders, *result.added],
    )
    return merged, result
