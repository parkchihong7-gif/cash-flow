"""국제 컨퍼런스 해외 연사 초청 관리.

    python cli.py brief --input event.yaml          연사별 브리프 (md)
    python cli.py brief --demo                      샘플 명부로
    python cli.py visa --paid --days 5 --waiver     체류자격 확인 방향
    python cli.py tax 5000000 --basis net           원천징수 계산
    python cli.py budget --input event.yaml         결재용 예산 (xlsx)
    python cli.py letter --input event.yaml --speaker "Jane Doe"
    python cli.py checklist --input event.yaml      D-120 역산 일정

**법률·세무 자문이 아닙니다.** 체류자격은 출입국·주한공관에,
원천징수는 세무대리인에게 확인하세요.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parents[1]))

from speaker_desk.brief import write_brief                          # noqa: E402
from speaker_desk.budget import build as build_budget, write_xlsx   # noqa: E402
from speaker_desk.checklist import build as build_checklist, overdue_count  # noqa: E402
from speaker_desk.letters import (                                  # noqa: E402
    contract_text, invitation_text, write_docx,
)
from speaker_desk.roster import Event, RosterError, load_event      # noqa: E402
from speaker_desk.tax import (                                      # noqa: E402
    NOT_TAX_ADVICE, TOTAL_RATE, TREATY_DOCS, compute,
)
from speaker_desk.visa import MUST_CONFIRM, assess                  # noqa: E402

DEFAULT_EVENT = BASE_DIR / "event.yaml"
DEFAULT_OUT = BASE_DIR / "outputs"


def _event(args) -> Event:
    path = DEFAULT_EVENT if args.demo else Path(args.input)
    return load_event(path)


def cmd_visa(args: argparse.Namespace) -> int:
    hint = assess(paid=args.paid, days=args.days, visa_waiver=args.waiver,
                  expenses_only=args.expenses_only)
    print(f"확인할 방향: {hint.name}")
    print(f"  해당 조건: {hint.when}")
    print(f"  참고: {hint.note}")
    print()
    print("왜 이쪽인가:")
    for reason in hint.reasons:
        print(f"  - {reason}")
    if hint.warnings:
        print()
        print("⚠ 조심할 것:")
        for item in hint.warnings:
            print(f"  - {item}")
    print()
    print(MUST_CONFIRM)
    return 2 if hint.warnings else 0


def cmd_tax(args: argparse.Namespace) -> int:
    result = compute(args.amount, args.basis, args.treaty)
    print(f"기본 원천징수율 {TOTAL_RATE * 100:.0f}% "
          f"(소득세 20% + 지방소득세 2%)")
    print()
    basis = ("계약서 금액에서 세금을 뗍니다" if args.basis == "gross"
             else "연사 손에 계약서 금액이 가도록 총액을 올립니다")
    print(f"방식: {args.basis} — {basis}")
    print(f"  계약서 금액   {result.contract_amount:>12,}원")
    print(f"  지급 총액     {result.gross:>12,}원")
    print(f"  원천징수      {result.tax:>12,}원  ({result.rate_percent}%)")
    print(f"  연사 수령액   {result.net:>12,}원")
    if result.extra_for_net:
        print(f"  → net 방식이라 주최 측 부담이 {result.extra_for_net:,}원 늘어납니다")
    print()
    if result.treaty:
        print("조세조약 제한세율을 적용한 값입니다. 서류가 지급일 전에 있어야 합니다:")
    else:
        print("조세조약으로 줄이려면 지급일 전에 받아야 할 서류:")
    for index, item in enumerate(TREATY_DOCS, 1):
        print(f"  {index}. {item}")
    print()
    print(NOT_TAX_ADVICE)
    return 0


def cmd_checklist(args: argparse.Namespace) -> int:
    event = _event(args)
    today = date.fromisoformat(args.today) if args.today else date.today()
    print(f"{event.title} · {event.event_date.isoformat()} "
          f"· D-{event.days_until(today)}")
    print()
    total_late = 0
    for speaker in event.speakers:
        tasks = build_checklist(event, speaker)
        late = overdue_count(tasks, today)
        total_late += late
        print(f"[{speaker.name}] 할 일 {len(tasks)}개"
              + (f" · ⚠ 지난 필수 일정 {late}건" if late else ""))
        for task in tasks:
            state = task.state(today)
            if args.all or state in ("late", "soon"):
                mark = {"late": "⚠", "soon": "→", "past": "·", "ahead": " "}[state]
                hard = " (필수)" if task.hard else ""
                print(f"  {mark} {task.dday:>6} {task.due.isoformat()}  "
                      f"{task.title}{hard}")
        print()
    if total_late:
        print(f"지난 필수 일정이 모두 {total_late}건입니다. 되돌리기 어려운 것부터 보세요.")
        return 2
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    event = _event(args)
    today = date.fromisoformat(args.today) if args.today else date.today()
    budgets = {item.speaker: item for item in build_budget(event)}
    out_dir = Path(args.out)

    print(f"{event.title} · 연사 {len(event.speakers)}명 · D-{event.days_until(today)}")
    print()
    total_late = 0
    for speaker in event.speakers:
        tasks = build_checklist(event, speaker)
        late = overdue_count(tasks, today)
        total_late += late
        path = write_brief(event, speaker, tasks, budgets[speaker.name],
                           out_dir, today=today)
        hint = assess(paid=speaker.paid, days=speaker.stay_days or 1,
                      visa_waiver=speaker.visa_waiver,
                      expenses_only=speaker.expenses_only)
        print(f"  ✓ {path.name}")
        print(f"      체류자격 확인 방향: {hint.name}"
              + ("  ⚠" if hint.warnings else ""))
        if speaker.paid:
            result = compute(speaker.fee_krw, speaker.fee_basis, speaker.treaty_rate)
            print(f"      지급 총액 {result.gross:,}원 · "
                  f"원천징수 {result.tax:,}원 · 수령 {result.net:,}원")
        if late:
            print(f"      ⚠ 지난 필수 일정 {late}건")
    print()
    print(f"  → {out_dir}")
    print()
    print("※ 법률·세무 자문이 아닙니다. 체류자격은 출입국·주한공관에, "
          "원천징수는 세무대리인에게 확인하세요.")
    return 2 if total_late else 0


def cmd_budget(args: argparse.Namespace) -> int:
    event = _event(args)
    budgets = build_budget(event)
    path = write_xlsx(event, budgets, Path(args.out))

    print(f"{event.title} · 연사 {len(budgets)}명")
    total = 0
    for item in budgets:
        cash = sum(line.amount for line in item.lines
                   if not line.label.startswith("  "))
        total += cash
        print(f"  {item.speaker:<20}{cash:>12,}원"
              + (f"  (원천징수 {item.tax:,}원)" if item.tax else ""))
    print(f"  {'합계':<20}{total:>12,}원")
    print()
    print(f"  ✓ {path.name} ({path.stat().st_size:,}B)")
    print(f"  → {path.parent}")
    return 0


def cmd_letter(args: argparse.Namespace) -> int:
    event = _event(args)
    speaker = event.speaker(args.speaker) if args.speaker else event.speakers[0]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = speaker.name.replace(" ", "_")

    invitation = invitation_text(event, speaker)
    contract = contract_text(event, speaker)

    made = []
    for text, stem, title in (
        (invitation, f"invitation_{safe}", "Letter of Invitation"),
        (contract, f"contract_{safe}", "Speaker Agreement (draft)"),
    ):
        (out_dir / f"{stem}.txt").write_text(text, encoding="utf-8")
        made.append(out_dir / f"{stem}.txt")
        if not args.no_docx:
            made.append(write_docx(text, out_dir / f"{stem}.docx", title))

    print(f"{speaker.name} 문서를 만들었습니다")
    for path in made:
        print(f"  ✓ {path.name} ({path.stat().st_size:,}B)")
    print(f"  → {out_dir}")
    print()
    print("초청장은 비자 신청에 그대로 냅니다. 계약서는 **초안**이니 "
          "서명 전에 검토를 받으세요.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="해외 연사 초청의 비자·세금·일정·예산을 정리합니다 "
                    "(법률·세무 자문이 아닙니다)")
    subparsers = parser.add_subparsers(dest="command")

    visa = subparsers.add_parser("visa", help="체류자격 확인 방향")
    visa.add_argument("--paid", action="store_true", help="강연료를 지급하는가")
    visa.add_argument("--days", type=int, default=5)
    visa.add_argument("--waiver", action="store_true", help="사증면제 대상국인가")
    visa.add_argument("--expenses-only", action="store_true",
                      help="대가 없이 실비만 지원")
    visa.set_defaults(func=cmd_visa)

    tax = subparsers.add_parser("tax", help="원천징수 계산")
    tax.add_argument("amount", type=int)
    tax.add_argument("--basis", default="gross", choices=["gross", "net"])
    tax.add_argument("--treaty", type=float, default=None,
                     help="조세조약 제한세율. 예: 0.0 (면제) 또는 0.15")
    tax.set_defaults(func=cmd_tax)

    for name, func, help_text in (
        ("brief", cmd_brief, "연사별 브리프를 만듭니다"),
        ("checklist", cmd_checklist, "D-120 역산 일정"),
        ("budget", cmd_budget, "결재용 예산 엑셀"),
        ("letter", cmd_letter, "초청장·계약서 초안"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--input", default=str(DEFAULT_EVENT))
        sub.add_argument("--demo", action="store_true", help="샘플 명부로 돕니다")
        sub.add_argument("--out", default=str(DEFAULT_OUT))
        sub.add_argument("--dry-run", action="store_true",
                         help="이 프로그램은 외부 호출을 하지 않습니다. 호환용입니다")
        if name in ("brief", "checklist"):
            sub.add_argument("--today", default="", help="오늘을 다르게 잡고 봅니다")
        if name == "checklist":
            sub.add_argument("--all", action="store_true", help="여유 있는 것까지 전부")
        if name == "letter":
            sub.add_argument("--speaker", default="")
            sub.add_argument("--no-docx", action="store_true")
        sub.set_defaults(func=func)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n예: python cli.py brief --demo", file=sys.stderr)
        return 1
    try:
        return args.func(args)
    except RosterError as exc:
        print(f"{exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
