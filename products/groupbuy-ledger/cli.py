"""공구 정산 엑셀 자동 생성기 CLI.

    python cli.py new --name "9월 공구" --products samples/products.csv
    python cli.py import-orders outputs/groupbuy_9월-공구.xlsx samples/orders.csv
    python cli.py report outputs/groupbuy_9월-공구.xlsx

`import-orders` 는 기존 파일을 열어 고치는 것이 아니라, 데이터를 읽어 합친 뒤
**전체를 다시 만든다.** openpyxl 로 읽고 다시 쓰면 차트가 사라지기 때문이다.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from groupbuy_ledger.calc import compute                                # noqa: E402
from groupbuy_ledger.lint import scan_formulas                          # noqa: E402
from groupbuy_ledger.importer import (                                  # noqa: E402
    ImportError_, import_orders, read_products_csv,
)
from groupbuy_ledger.reader import LedgerFileError, read_ledger         # noqa: E402
from groupbuy_ledger.recalc import RecalcUnavailable, recalculate       # noqa: E402
from groupbuy_ledger.report import (                                    # noqa: E402
    gather, insight_lines, write_report, write_shipping_csv,
)
from groupbuy_ledger.schema import Ledger, Product, Settings, slugify   # noqa: E402
from groupbuy_ledger.workbook import build_workbook                     # noqa: E402
from shared.config import DEFAULT_MODEL                                 # noqa: E402
from shared.llm import LLMError                                         # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = BASE_DIR / "outputs"
DEFAULT_MAPPING = BASE_DIR / "mapping.yaml"
DEFAULT_PRODUCTS = BASE_DIR / "samples" / "products.csv"


def _parse_date(text: str, field: str) -> date:
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"{field} 을(를) 날짜로 읽지 못했습니다: {text} (예: 2026-09-01)")


# ------------------------------------------------------------------- new
def cmd_new(args: argparse.Namespace) -> int:
    products_csv = Path(args.products)
    start = _parse_date(args.start, "--start") if args.start else date.today()
    end = _parse_date(args.end, "--end") if args.end else start + timedelta(days=13)

    settings = Settings(
        name=args.name,
        round_label=args.round or slugify(args.name),
        start=start, end=end,
        default_cost=args.cost, default_price=args.price,
        shipping_fee=args.shipping, payment_fee_rate=args.payment_fee,
        platform_fee_rate=args.platform_fee,
        vat_included=not args.no_vat, vat_rate=args.vat_rate,
    )
    products = [Product(**row) for row in
                read_products_csv(products_csv, args.cost, args.price)]
    ledger = Ledger(settings=settings, products=products, orders=[])

    path = Path(args.out) / ledger.filename
    build_workbook(ledger, path)

    print(f"빈 장부를 만들었습니다: {path}")
    print(f"  공구명 {settings.name} · 회차 {settings.round_label}")
    print(f"  기간 {settings.start} ~ {settings.end} ({settings.days}일)")
    print(f"  상품 {len(products)}개 · 기본 마진율 {settings.margin_rate:.1%}")

    lint = scan_formulas(path)
    if lint.ok:
        print(f"  수식 {lint.formula_count}개 · 모두 엑셀 2010 호환 함수")
    else:
        print("  ✗ 수식 검사에 걸렸습니다:")
        print("    " + lint.report().replace("\n", "\n    "))
        return 2
    print()
    print("다음: 주문 CSV 를 받아 아래처럼 넣으세요.")
    print(f'  python cli.py import-orders "{path}" 주문.csv')
    return 0


# ---------------------------------------------------------- import-orders
def cmd_import(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    ledger = read_ledger(path)
    before = len(ledger.orders)

    merged, result = import_orders(ledger, Path(args.orders), Path(args.mapping))
    build_workbook(merged, path)

    print(f"{path.name} 을 갱신했습니다 (주문 {before} → {len(merged.orders)}건)")
    for line in result.report_lines():
        print(line)

    if args.verbose:
        print("\n  컬럼 매핑:")
        for field, header in result.matched_columns.items():
            mark = "  " if field == header else "→ "
            print(f"    {mark}{field:<8} ← {header}")
        unused = [h for h in result.csv_headers
                  if h not in result.matched_columns.values()]
        if unused:
            print(f"    쓰지 않은 컬럼: {', '.join(unused)}")

    print()
    print("다음: 정산 리포트를 만드세요.")
    print(f'  python cli.py report "{path}"')
    return 2 if result.needs_attention else 0


# ---------------------------------------------------------------- report
def cmd_report(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    ledger = read_ledger(path)

    if args.dry_run:
        from groupbuy_ledger.sample_content import fake_ask

        ask_fn, model = fake_ask, "dry-run"
        print("모의 실행 — Claude 를 부르지 않습니다 (비용 없음)")
    else:
        from shared.llm import ask

        ask_fn, model = ask, args.model
        print(f"모델 {model} 로 코멘트를 받습니다")

    print("엑셀을 다시 계산하는 중입니다. 잠시 걸립니다.")
    data = gather(ledger, path, use_recalc=not args.no_recalc)
    print(f"  숫자 출처: {data.source}")

    lines, warnings = insight_lines(data, ask_fn, model)

    out_dir = Path(args.out)
    report_path = out_dir / f"report_{slugify(ledger.settings.round_label)}.md"
    write_report(ledger, data, report_path, lines, warnings,
                 datetime.now().astimezone(), ai_label=not args.no_ai_label)

    shipping_path, waiting = write_shipping_csv(
        ledger, out_dir / f"발송목록_{slugify(ledger.settings.round_label)}.csv")

    totals = compute(ledger)
    summary = data.summary
    print()
    print(f"  순매출 {summary['net']:,.0f}원 · 순이익 {summary['profit']:,.0f}원"
          f" · 순마진율 {(summary['margin'] or 0):.1%}")
    print(f"  주문 {summary['orders']:.0f}건 (취소·환불 {summary['void_orders']:.0f}건)"
          f" · 발송 대기 {summary['waiting']:.0f}건")
    if totals.low_stock_products:
        print("  ⚠ 재고 경고: "
              + ", ".join(f"{p.label} {p.stock}개" for p in totals.low_stock_products))
    if data.formula_errors:
        print(f"  ✗ 수식 오류 {len(data.formula_errors)}건 — 리포트를 확인하세요")
    if data.mismatches:
        print(f"  ⚠ 엑셀과 파이썬 계산이 {len(data.mismatches)}곳 다릅니다")
    for warning in warnings:
        print(f"  ! {warning}")
    print(f"  → {report_path}")
    print(f"  → {shipping_path} (발송 대기 {waiting}건)")

    if args.dry_run:
        print("※ 모의 실행 결과입니다. 코멘트는 예시 문장입니다.")
    return 2 if (data.formula_errors or data.mismatches or warnings) else 0


# -------------------------------------------------------------------- demo
def cmd_demo(args: argparse.Namespace) -> int:
    """new → import-orders → report 를 한 번에 돌린다.

    통합 대시보드의 '테스트' 버튼과, 처음 써 보는 사람이 전체 흐름을
    한 번에 보고 싶을 때 쓴다. 세 단계를 따로 치는 것과 결과가 같다.
    """
    orders_csv = Path(args.orders)
    if not orders_csv.is_file():
        raise FileNotFoundError(f"주문 CSV 가 없습니다: {orders_csv}")

    print("[1/3] 빈 장부 만들기")
    code = cmd_new(args)
    if code:
        return code

    ledger_path = Path(args.out) / Ledger(
        settings=Settings(
            name=args.name, round_label=args.round or slugify(args.name),
            start=_parse_date(args.start, "--start") if args.start else date.today(),
            end=(_parse_date(args.end, "--end") if args.end
                 else (_parse_date(args.start, "--start") if args.start
                       else date.today()) + timedelta(days=13)),
            default_cost=args.cost, default_price=args.price,
        ),
        products=[Product(**row) for row in
                  read_products_csv(Path(args.products), args.cost, args.price)],
    ).filename

    print()
    print("[2/3] 주문 CSV 넣기")
    import_args = argparse.Namespace(
        ledger=str(ledger_path), orders=str(orders_csv),
        mapping=args.mapping, verbose=args.verbose)
    import_code = cmd_import(import_args)

    print()
    print("[3/3] 정산 리포트")
    report_args = argparse.Namespace(
        ledger=str(ledger_path), dry_run=args.dry_run, no_recalc=args.no_recalc,
        model=args.model, no_ai_label=args.no_ai_label, out=args.out)
    report_code = cmd_report(report_args)

    print()
    print(f"끝났습니다. 산출물 폴더: {args.out}")
    return max(import_code, report_code)


# ------------------------------------------------------------------ 검증
def cmd_verify(args: argparse.Namespace) -> int:
    """엑셀 계산값과 파이썬 계산값을 맞춰 본다. 납품 전 점검용."""
    from groupbuy_ledger import layout as L

    path = Path(args.ledger)
    ledger = read_ledger(path)
    mine = compute(ledger).as_summary()
    result = recalculate(path)

    print(f"엔진 {result.engine} · 셀 {len(result.values)}개를 계산했습니다")
    print()

    bad = 0
    for key, row in L.SUMMARY.items():
        excel = result.get(L.SHEET_LEDGER, f"B{row}")
        value = mine[key]
        if isinstance(excel, str) and not excel.strip():
            excel = None
        same = (value is None and excel is None) or (
            value is not None and isinstance(excel, (int, float))
            and abs(float(excel) - float(value)) < 0.5)
        bad += 0 if same else 1
        mark = "✓" if same else "✗"
        shown = f"{float(excel):,.2f}" if isinstance(excel, (int, float)) else repr(excel)
        print(f"  {mark} {L.SUMMARY_LABELS[key][0]:<14} 엑셀 {shown:>16}"
              f"   파이썬 {value if value is None else f'{float(value):,.2f}'}")

    lint = scan_formulas(path)
    print()
    print("  " + lint.report().replace("\n", "\n  "))

    errors = result.errors()
    print()
    if errors:
        print(f"✗ 수식 오류 {len(errors)}건")
        for sheet, cell, value in errors[:20]:
            print(f"    {sheet}!{cell} → {value}")
    else:
        print("✓ 수식 오류 0건 (#REF!·#NAME? 없음)")

    if bad or not lint.ok:
        if bad:
            print(f"✗ 값이 다른 항목 {bad}개")
        return 2
    print("✓ 정산 요약 16개 항목이 모두 일치합니다")
    return 0


# ------------------------------------------------------------------ 진입점
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="공구 주문·정산·재고 엑셀 생성기 (정산 확정 전 사람 검수 필수)",
    )
    subparsers = parser.add_subparsers(dest="command")

    new = subparsers.add_parser("new", help="빈 장부를 만듭니다")
    new.add_argument("--name", required=True, help='공구명. 예: "9월 원두 공구"')
    new.add_argument("--products", default=str(DEFAULT_PRODUCTS),
                     help="상품 CSV (상품코드,옵션,공급가,판매가,초기재고)")
    new.add_argument("--round", default="", help="회차. 파일 이름에 들어갑니다")
    new.add_argument("--start", default="", help="시작일 (기본: 오늘)")
    new.add_argument("--end", default="", help="종료일 (기본: 시작일 + 13일)")
    new.add_argument("--cost", type=int, default=0, help="기본 공급가")
    new.add_argument("--price", type=int, default=10000, help="기본 판매가")
    new.add_argument("--shipping", type=int, default=3000, help="건당 배송비")
    new.add_argument("--payment-fee", type=float, default=0.032, help="결제수수료율")
    new.add_argument("--platform-fee", type=float, default=0.0, help="플랫폼수수료율")
    new.add_argument("--vat-rate", type=float, default=0.1, help="부가세율")
    new.add_argument("--no-vat", action="store_true", help="부가세를 빼지 않습니다")
    new.add_argument("--out", default=str(DEFAULT_OUT), help="저장 폴더")
    new.set_defaults(func=cmd_new)

    imp = subparsers.add_parser("import-orders", help="주문 CSV 를 장부에 넣습니다")
    imp.add_argument("ledger", help="장부 xlsx 경로")
    imp.add_argument("orders", help="주문 CSV 경로")
    imp.add_argument("--mapping", default=str(DEFAULT_MAPPING),
                     help="컬럼 매핑 파일 (기본: mapping.yaml)")
    imp.add_argument("--verbose", action="store_true", help="컬럼 매핑 결과를 보여줍니다")
    imp.set_defaults(func=cmd_import)

    rep = subparsers.add_parser("report", help="정산 리포트를 만듭니다")
    rep.add_argument("ledger", help="장부 xlsx 경로")
    rep.add_argument("--dry-run", action="store_true",
                     help="Claude 를 부르지 않고 예시 코멘트로 만듭니다")
    rep.add_argument("--no-recalc", action="store_true",
                     help="엑셀 재계산을 건너뛰고 파이썬 계산값을 씁니다 (빠름)")
    rep.add_argument("--model", default=DEFAULT_MODEL, help=f"기본: {DEFAULT_MODEL}")
    rep.add_argument("--no-ai-label", action="store_true", help="AI 생성물 표시를 끕니다")
    rep.add_argument("--out", default=str(DEFAULT_OUT), help="저장 폴더")
    rep.set_defaults(func=cmd_report)

    demo = subparsers.add_parser(
        "demo", help="new → import-orders → report 를 한 번에 돌립니다")
    demo.add_argument("--name", default="샘플 공구", help="공구명")
    demo.add_argument("--products", default=str(DEFAULT_PRODUCTS), help="상품 CSV")
    demo.add_argument("--orders", default=str(BASE_DIR / "samples" / "orders.csv"),
                      help="주문 CSV")
    demo.add_argument("--round", default="", help="회차")
    demo.add_argument("--start", default="2026-09-01", help="시작일")
    demo.add_argument("--end", default="2026-09-14", help="종료일")
    demo.add_argument("--cost", type=int, default=9000, help="기본 공급가")
    demo.add_argument("--price", type=int, default=15000, help="기본 판매가")
    demo.add_argument("--shipping", type=int, default=3000, help="건당 배송비")
    demo.add_argument("--payment-fee", type=float, default=0.032)
    demo.add_argument("--platform-fee", type=float, default=0.0)
    demo.add_argument("--vat-rate", type=float, default=0.1)
    demo.add_argument("--no-vat", action="store_true")
    demo.add_argument("--mapping", default=str(DEFAULT_MAPPING), help="컬럼 매핑 파일")
    demo.add_argument("--verbose", action="store_true", help="컬럼 매핑 결과를 보여줍니다")
    demo.add_argument("--dry-run", action="store_true",
                      help="Claude 를 부르지 않고 예시 코멘트로 만듭니다")
    demo.add_argument("--no-recalc", action="store_true", help="엑셀 재계산을 건너뜁니다")
    demo.add_argument("--model", default=DEFAULT_MODEL)
    demo.add_argument("--no-ai-label", action="store_true")
    demo.add_argument("--out", default=str(DEFAULT_OUT), help="저장 폴더")
    demo.set_defaults(func=cmd_demo)

    ver = subparsers.add_parser("verify", help="엑셀 계산값과 파이썬 계산값을 맞춰 봅니다")
    ver.add_argument("ledger", help="장부 xlsx 경로")
    ver.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        print('\n예: python cli.py new --name "9월 공구" --products samples/products.csv',
              file=sys.stderr)
        return 1

    try:
        return args.func(args)
    except (ImportError_, LedgerFileError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
    except RecalcUnavailable as exc:
        print(f"재계산할 수 없습니다:\n{exc}", file=sys.stderr)
    except FileNotFoundError as exc:
        print(f"파일을 찾지 못했습니다: {exc}", file=sys.stderr)
    except LLMError as exc:
        print(f"코멘트 생성 실패: {exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"입력이 잘못되었습니다: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
