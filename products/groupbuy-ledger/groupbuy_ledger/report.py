"""정산 리포트를 쓴다.

숫자는 **엑셀이 계산한 값**을 쓴다. 파이썬으로 따로 계산한 값과 견줘 보고,
어긋나면 리포트에 그대로 적는다. 조용히 한쪽을 고르지 않는다.

Claude 가 쓰는 세 줄 코멘트도 **[수치] 블록에 있는 숫자만** 쓰게 하고,
그래도 없는 숫자가 나오면 다시 시킨다(최대 2회). 끝내 안 되면 그 줄을 빼고
무엇을 뺐는지 리포트에 적는다.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from groupbuy_ledger import layout as L                        # noqa: E402
from groupbuy_ledger.calc import Totals, compute                # noqa: E402
from groupbuy_ledger.recalc import RecalcUnavailable, recalculate  # noqa: E402
from groupbuy_ledger.schema import STOCK_WARN, Ledger           # noqa: E402
from shared import banned_phrases                               # noqa: E402
from shared.ai_label import add_text_label                      # noqa: E402

__all__ = ["ReportData", "gather", "write_report", "write_shipping_csv",
           "insight_lines", "unknown_numbers", "MAX_RETRY", "SHIPPING_HEADER"]

#: 택배사 업로드 양식 순서. 엑셀 배송 시트와 같다.
SHIPPING_HEADER = ("받는분성명", "받는분전화번호", "받는분주소", "품목명",
                   "수량", "배송메시지", "주문번호", "송장번호")

#: 코멘트를 다시 시키는 횟수.
MAX_RETRY = 2

#: 순위·건수처럼 본문에 자연스럽게 나오는 작은 정수는 허용한다.
SMALL_INTEGERS = set(range(0, 32))

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "insight.md"


@dataclass
class ReportData:
    """리포트에 쓸 숫자와 그 출처."""

    totals: Totals
    summary: dict[str, float | int | None]
    source: str
    engine: str = ""
    mismatches: list[str] = field(default_factory=list)
    formula_errors: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return bool(self.engine) and not self.mismatches and not self.formula_errors


def gather(ledger: Ledger, xlsx_path: Path, use_recalc: bool = True) -> ReportData:
    """엑셀을 다시 계산해 숫자를 모은다. 실패하면 파이썬 계산값으로 넘어간다."""
    totals = compute(ledger)
    fallback = totals.as_summary()

    if not use_recalc:
        return ReportData(totals=totals, summary=fallback, source="파이썬 계산")

    try:
        result = recalculate(Path(xlsx_path))
    except RecalcUnavailable:
        return ReportData(
            totals=totals, summary=fallback,
            source="파이썬 계산 (엑셀 재계산 수단 없음)",
        )

    summary: dict[str, float | int | None] = {}
    mismatches: list[str] = []
    for key, row in L.SUMMARY.items():
        excel = result.get(L.SHEET_LEDGER, f"B{row}")
        mine = fallback[key]
        if isinstance(excel, str) and not excel.strip():
            excel = None
        summary[key] = float(excel) if isinstance(excel, (int, float)) else mine

        both_blank = mine is None and excel is None
        if both_blank:
            continue
        if mine is None or excel is None or abs(float(excel) - float(mine)) > 0.5:
            label = L.SUMMARY_LABELS[key][0]
            mismatches.append(f"{label}: 엑셀 {excel!r} vs 파이썬 {mine!r}")

    return ReportData(
        totals=totals, summary=summary,
        source=f"엑셀 재계산 ({result.engine})", engine=result.engine,
        mismatches=mismatches, formula_errors=result.errors(),
    )


# ------------------------------------------------------------ 숫자 검사
def _number_tokens(text: str) -> list[float]:
    """글에 나온 숫자를 뽑는다. 천 단위 쉼표와 퍼센트를 함께 본다."""
    tokens = []
    for raw in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            tokens.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return tokens


def _allowed_numbers(data: ReportData) -> set[float]:
    """코멘트에 나와도 되는 숫자. 엑셀이 계산한 값에서만 만든다."""
    allowed: set[float] = {float(n) for n in SMALL_INTEGERS}

    def add(value) -> None:
        if value is None:
            return
        number = float(value)
        allowed.add(number)
        allowed.add(round(number))
        allowed.add(round(number, 1))
        allowed.add(round(number * 100, 1))          # 비율을 % 로 쓴 경우
        allowed.add(float(round(number * 100)))
        if abs(number) >= 10000:                      # "12만 원" 처럼 만 단위로 쓴 경우
            allowed.add(round(number / 10000, 1))
            allowed.add(float(round(number / 10000)))

    for value in data.summary.values():
        add(value)
    for product in data.totals.products:
        for value in (product.sold, product.revenue, product.profit,
                      product.stock, product.cost, product.margin, product.rank):
            add(value)
    for day in data.totals.days:
        add(day.revenue)
        add(day.orders)
    add(STOCK_WARN)
    add(len(data.totals.products))
    return allowed


def unknown_numbers(text: str, allowed: set[float]) -> list[float]:
    """엑셀 계산값에 없는 숫자를 찾아낸다."""
    return [n for n in _number_tokens(text)
            if not any(abs(n - a) < 0.05 for a in allowed)]


# ------------------------------------------------------------ Claude 코멘트
def _facts(data: ReportData) -> str:
    """Claude 에게 줄 [수치] 블록. 여기 없는 숫자는 쓰면 안 된다."""
    totals = data.totals
    best = totals.best_seller
    payload = {
        "순매출": data.summary["net"],
        "순이익": data.summary["profit"],
        "순마진율_퍼센트": round((data.summary["margin"] or 0) * 100, 1),
        "총_주문건수": data.summary["orders"],
        "취소환불_건수": data.summary["void_orders"],
        "환불률_퍼센트": round((data.summary["refund_rate"] or 0) * 100, 1),
        "평균_객단가": data.summary["avg_order"],
        "발송_대기건수": data.summary["waiting"],
        "가장_잘_팔린_옵션": (
            {"이름": best.label, "판매수량": best.sold, "이익": best.profit}
            if best else None
        ),
        "상품별": [
            {"이름": p.label, "판매수량": p.sold, "매출": p.revenue,
             "이익": p.profit, "남은재고": p.stock, "순위": p.rank}
            for p in sorted(totals.products, key=lambda x: x.rank)
        ],
        "재고부족_옵션": [
            {"이름": p.label, "남은재고": p.stock} for p in totals.low_stock_products
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def insight_lines(data: ReportData, ask_fn, model: str) -> tuple[list[str], list[str]]:
    """세 줄 코멘트를 받는다. (줄 목록, 경고 목록)."""
    if not PROMPT_PATH.is_file():
        raise FileNotFoundError(f"프롬프트가 없습니다: {PROMPT_PATH}")

    system = PROMPT_PATH.read_text(encoding="utf-8")
    facts = _facts(data)
    allowed = _allowed_numbers(data)
    warnings: list[str] = []
    user = f"[수치]\n{facts}\n\n위 숫자만 써서 세 줄을 써라."

    for attempt in range(1, MAX_RETRY + 2):
        text = ask_fn(system, user, model=model)
        lines = [line.strip() for line in str(text).splitlines() if line.strip().startswith("-")]
        lines = [re.sub(r"^-\s*", "", line) for line in lines][:3]

        strays = unknown_numbers(" ".join(lines), allowed)
        dirty = banned_phrases.check(" ".join(lines))

        if not strays and not dirty and len(lines) == 3:
            if attempt > 1:
                warnings.append(f"코멘트를 {attempt}번째 시도에 받았습니다")
            return lines, warnings

        if attempt > MAX_RETRY:
            break
        problems = []
        if strays:
            problems.append("[수치] 에 없는 숫자를 썼다: "
                            + ", ".join(f"{n:g}" for n in strays[:5]))
        if dirty:
            problems.append("쓰면 안 되는 표현이 있다: " + ", ".join(dirty))
        if len(lines) != 3:
            problems.append(f"세 줄이어야 하는데 {len(lines)}줄이다")
        user = (f"[수치]\n{facts}\n\n앞선 답에 문제가 있었다.\n"
                + "\n".join(f"- {p}" for p in problems)
                + "\n고쳐서 세 줄만 다시 써라.")

    kept = [line for line in lines
            if not unknown_numbers(line, allowed) and not banned_phrases.check(line)]
    warnings.append(
        f"코멘트 {len(lines) - len(kept)}줄을 뺐습니다 — "
        "엑셀 계산값에 없는 숫자나 쓰면 안 되는 표현이 들어 있었습니다"
    )
    return kept, warnings


# ------------------------------------------------------------ 리포트 쓰기
def _won(value) -> str:
    if value is None:
        return "—"
    return f"{round(float(value)):,}원"


def _pct(value) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f}%"


def write_report(ledger: Ledger, data: ReportData, path: Path,
                 lines: list[str], warnings: list[str],
                 generated_at: datetime, ai_label: bool = True) -> Path:
    """report_<회차>.md 를 쓴다."""
    settings = ledger.settings
    totals = data.totals
    summary = data.summary
    parts: list[str] = []

    parts.append(f"# {settings.name} 정산 리포트\n")
    parts.append(
        f"- 회차: {settings.round_label}\n"
        f"- 기간: {settings.start:%Y-%m-%d} ~ {settings.end:%Y-%m-%d} "
        f"({settings.days}일)\n"
        f"- 작성: {generated_at:%Y-%m-%d %H:%M}\n"
        f"- 숫자 출처: {data.source}\n"
    )

    if data.formula_errors:
        parts.append("\n> ⚠️ **수식 오류가 있습니다.** 아래 값을 믿지 마세요.\n>\n"
                     + "".join(f"> - {s}!{c} → {e}\n"
                               for s, c, e in data.formula_errors[:10]))
    if data.mismatches:
        parts.append("\n> ⚠️ **엑셀 계산과 파이썬 계산이 다릅니다.** "
                     "엑셀 파일을 열어 확인하세요.\n>\n"
                     + "".join(f"> - {m}\n" for m in data.mismatches))
    elif data.verified:
        parts.append("\n> ✅ 엑셀 수식 계산값과 파이썬 독립 계산값이 모두 일치합니다. "
                     "수식 오류도 없습니다.\n")

    parts.append("\n## 정산 요약\n")
    parts.append("| 항목 | 금액 |\n|---|--:|\n")
    money_rows = ("gross", "void", "net", "payment_fee", "platform_fee",
                  "cost", "shipping", "vat", "profit")
    for key in money_rows:
        label = L.SUMMARY_LABELS[key][0]
        value = _won(summary[key])
        if key in ("void", "payment_fee", "platform_fee", "cost", "shipping", "vat"):
            value = f"− {value}"
        if key == "profit":
            label, value = f"**{label}**", f"**{value}**"
        parts.append(f"| {label} | {value} |\n")
    parts.append(f"| 순마진율 | {_pct(summary['margin'])} |\n")

    parts.append("\n## 주문 현황\n")
    parts.append("| 항목 | 값 |\n|---|--:|\n")
    parts.append(f"| 총 주문건수 | {summary['orders']:.0f}건 |\n")
    parts.append(f"| 취소·환불 건수 | {summary['void_orders']:.0f}건 |\n")
    parts.append(f"| 유효 주문건수 | {summary['active_orders']:.0f}건 |\n")
    parts.append(f"| 환불률 | {_pct(summary['refund_rate'])} |\n")
    parts.append(f"| 평균 객단가 | {_won(summary['avg_order'])} |\n")
    parts.append(f"| 발송 대기 | {summary['waiting']:.0f}건 |\n")

    parts.append("\n## 상품별 실적\n")
    parts.append("| 순위 | 상품 | 판매 | 매출 | 이익 | 남은재고 |\n|--:|---|--:|--:|--:|--:|\n")
    for product in sorted(totals.products, key=lambda p: p.rank):
        stock = f"{product.stock:,}개"
        if product.low_stock:
            stock = f"⚠️ {stock}"
        parts.append(
            f"| {product.rank} | {product.label} | {product.sold:,}개 | "
            f"{product.revenue:,}원 | {product.profit:,}원 | {stock} |\n"
        )

    if totals.low_stock_products:
        parts.append(f"\n## 재고 경고 ({STOCK_WARN}개 미만)\n\n")
        for product in totals.low_stock_products:
            parts.append(f"- **{product.label}** — {product.stock:,}개 남음\n")
        parts.append("\n추가 발주를 넣거나, 상세페이지에서 품절 표시를 해 두세요.\n")

    if summary["waiting"]:
        parts.append(
            f"\n## 발송 대기 {summary['waiting']:.0f}건\n\n"
            "엑셀의 **배송** 시트를 열면 대기 중인 주문만 택배사 양식 순서로 정리되어 있습니다.\n"
            "그대로 복사해서 택배사 접수 화면에 붙여넣으세요.\n"
        )

    parts.append("\n## 코멘트\n\n")
    if lines:
        for line in lines:
            parts.append(f"- {line}\n")
    else:
        parts.append("- (받지 못했습니다)\n")
    parts.append(
        "\n위 세 줄은 정산 숫자만 보고 쓴 것이라 현장 사정을 모릅니다. "
        "판단의 출발점으로만 쓰시고, 실행 전에 직접 따져 보세요.\n"
    )

    if warnings:
        parts.append("\n## 확인이 필요한 것\n\n")
        for warning in warnings:
            parts.append(f"- {warning}\n")

    parts.append(
        "\n## 다음에 할 일\n\n"
        "1. **배송** 시트의 대기 건을 택배사에 접수하고 송장번호를 주문 시트에 적으세요.\n"
        "2. 취소·환불 건의 실제 환불 처리가 끝났는지 결제 내역에서 확인하세요.\n"
        "3. 재고 경고가 있으면 발주 또는 품절 처리를 하세요.\n"
        "4. 정산 시트의 순이익을 통장 잔액 증감과 맞춰 보세요. "
        "차이가 나면 배송비나 수수료율 설정이 실제와 다른 것입니다.\n"
    )

    text = "".join(parts)
    if ai_label:
        text = add_text_label(text)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_shipping_csv(ledger: Ledger, path: Path) -> tuple[Path, int]:
    """발송 대기 주문만 택배사 양식으로 CSV 에 쓴다.

    엑셀의 배송 시트와 같은 내용이다. 택배사가 CSV 업로드만 받는 경우,
    시트를 '다른 이름으로 저장' 하다 원본을 덮어쓰는 사고가 나기 쉬워
    아예 따로 파일로 내놓는다.

    엑셀에서 쓸 것을 생각해 BOM 을 붙인다. 없으면 한글이 깨져 보인다.
    """
    waiting = [o for o in ledger.orders if o.status == "대기"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(SHIPPING_HEADER)
        for order in waiting:
            writer.writerow([
                order.customer, order.phone, order.address,
                f"{order.code} {order.option}".strip(), order.qty,
                order.memo, order.order_no, order.invoice,
            ])
    return path, len(waiting)
