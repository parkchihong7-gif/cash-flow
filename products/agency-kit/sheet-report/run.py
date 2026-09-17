"""주간 보고서 만들기.

    python run.py --sheet <시트ID> --range "매출!A:F" --period week
    python run.py --csv sample_sales.csv --period week --dry-run
    python run.py --csv sample_sales.csv --slack --email

시트를 못 붙였을 때는 `--csv` 로 돌려 보시면 됩니다. 만들어지는 보고서는 같습니다.
n8n 에서 매주 월요일 아침에 이 명령을 부르게 해 두면 그때부터 손이 안 갑니다
(`workflow.json`).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parents[2]))

from aggregate import ColumnMissing, PERIODS, load_csv, load_sheet, summarize  # noqa: E402
from narrate import narrate                                                    # noqa: E402
from notify import send_email, send_slack                                      # noqa: E402
from writers import report_markdown, write_all                                 # noqa: E402

DEFAULT_OUT = BASE_DIR / "outputs"
SAMPLE_CSV = BASE_DIR / "sample_sales.csv"


def _fake_narration(aggregate):
    """모의 실행용 해석. Claude 를 부르지 않는다.

    **집계에 있는 숫자만** 쓴다. 지어낸 숫자가 없어야 검사도 통과한다.
    """
    from narrate import Narration

    direction = "늘었습니다" if aggregate.delta > 0 else (
        "줄었습니다" if aggregate.delta < 0 else "지난 기간과 비슷합니다")
    top = aggregate.top[0]["name"] if aggregate.top else "주요 항목"

    return Narration(
        reading=[
            f"이번 기간 매출은 직전 기간과 견주어 {direction}.",
            f"{top} 쪽이 가장 큰 몫을 차지했습니다.",
            "건수와 평균 단가를 함께 보시면 어느 쪽이 움직였는지 알 수 있습니다.",
        ],
        actions=[
            f"{top} 재고와 준비 상태를 월요일에 확인하기",
            "지난주에 문의만 하고 결제 안 하신 분들께 안내 한 번 더 보내기",
        ],
        caution="이 숫자는 시트에 적힌 것만 본 결과라, 현금 결제나 누락분은 빠져 있을 수 있습니다.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run.py", description="시트 범위를 읽어 기간 보고서를 만듭니다")
    parser.add_argument("--sheet", default="", help="구글시트 ID")
    parser.add_argument("--range", dest="cell_range", default="매출!A:F",
                        help='읽을 범위. 예: "매출!A:F"')
    parser.add_argument("--csv", default="", help="시트 대신 읽을 CSV 파일")
    parser.add_argument("--period", default="week", choices=sorted(PERIODS),
                        help="week(7일) / month(30일) / quarter(90일)")
    parser.add_argument("--end", default="", help="기준 마지막 날 (YYYY-MM-DD)")
    parser.add_argument("--title", default="", help="보고서 제목")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="산출물 폴더")
    parser.add_argument("--model", default="", help="쓸 Claude 모델")
    parser.add_argument("--slack", action="store_true", help="슬랙으로도 보냅니다")
    parser.add_argument("--email", action="store_true", help="메일로도 보냅니다")
    parser.add_argument("--dry-run", action="store_true", help="Claude 를 부르지 않습니다")
    parser.add_argument("--no-ai-label", action="store_true", help="AI 생성물 표시를 끕니다")
    args = parser.parse_args(argv)

    # ── 1. 자료 읽기
    try:
        if args.sheet:
            source = f"구글시트 {args.sheet[:8]}… / {args.cell_range}"
            print(f"[1/4] 시트 읽기 — {args.cell_range}")
            frame = load_sheet(args.sheet, args.cell_range)
        else:
            path = Path(args.csv or SAMPLE_CSV)
            source = f"CSV {path.name}"
            print(f"[1/4] 파일 읽기 — {path.name}")
            frame = load_csv(path)
    except FileNotFoundError as exc:
        print(f"파일을 찾지 못했습니다: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"자료를 읽지 못했습니다: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("  시트라면 서비스 계정 이메일에 '뷰어' 로 공유했는지 확인하세요.", file=sys.stderr)
        return 1

    print(f"  {len(frame):,}줄 · 칸 {list(frame.columns)}")

    # ── 2. 집계 (숫자는 전부 여기서 나온다)
    print("[2/4] 집계")
    try:
        aggregate = summarize(frame, period=args.period, end_date=args.end)
    except ColumnMissing as exc:
        print(f"칸을 찾지 못했습니다:\n{exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"집계하지 못했습니다: {exc}", file=sys.stderr)
        return 1

    print(f"  {aggregate.start} ~ {aggregate.end} · 합계 {aggregate.total:,}원"
          f" · 직전 대비 {aggregate.delta:+,}원 ({aggregate.delta_ratio:+.1f}%)")

    # ── 3. 해석 (Claude 는 여기서만 말한다)
    print("[3/4] 해석")
    if args.dry_run:
        narration = _fake_narration(aggregate)
        print("  모의 실행 — Claude 를 부르지 않습니다 (비용 없음)")
    else:
        from shared.config import DEFAULT_MODEL
        from shared.llm import ask

        model = args.model or DEFAULT_MODEL
        narration = narrate(aggregate, ask, model)
        mark = "숫자 확인됨" if narration.verified else "⚠ 숫자 확인 실패"
        print(f"  모델 {model} · 호출 {narration.tries}회 · {mark}")

    for warning in narration.warnings:
        print(f"  ! {warning}")

    # ── 4. 파일 쓰기
    print("[4/4] 파일 쓰기")
    stamp = datetime.now().strftime("%Y%m%d")
    md_path, docx_path = write_all(
        aggregate, narration, Path(args.out), title=args.title, source=source,
        ai_label_on=not args.no_ai_label, stamp=stamp)
    print(f"  ✓ {md_path.name} ({md_path.stat().st_size:,}B)")
    print(f"  ✓ {docx_path.name} ({docx_path.stat().st_size:,}B)")
    print(f"  → {md_path.parent}")

    # ── 보내기 (선택)
    if args.slack or args.email:
        print()
        text = report_markdown(aggregate, narration, title=args.title, source=source)
        if args.slack:
            print(f"  {send_slack(text)}")
        if args.email:
            label = {"week": "주간", "month": "월간", "quarter": "분기"}[args.period]
            subject = args.title or f"[{label} 보고] {aggregate.start} ~ {aggregate.end}"
            print(f"  {send_email(subject, text, [md_path, docx_path])}")

    print()
    print("보내기 전에 확인하세요")
    print("  1. 합계가 시트 값과 맞는지 (한 칸만 찍어 보셔도 됩니다)")
    print("  2. 해석에 적힌 숫자가 표와 같은지")
    print("  3. 할 일 2가지가 실제로 할 수 있는 일인지")

    return 0 if narration.verified and not aggregate.notes else 2


if __name__ == "__main__":
    raise SystemExit(main())
