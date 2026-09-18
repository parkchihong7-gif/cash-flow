"""공인중개사 기출 풀이 분석기.

    python cli.py sheet --round 36회            빈 기록표를 만듭니다
    python cli.py report --input data/records.csv
    python cli.py report --demo --dry-run       샘플 자료로 흐름만 봅니다
    python cli.py subjects                      과목·단원 목록
    python cli.py check --input data/records.csv  표가 제대로 적혔는지만 봅니다

**이 프로그램에는 기출문제가 들어 있지 않습니다.** 본인이 푼 결과(O/X·단원·이유)만
넣으면 어디가 약한지 계산합니다. 문제 지문은 넣는 칸조차 없습니다 (README §2).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parents[1]))

from exam_drill.metrics import analyze                              # noqa: E402
from exam_drill.plan import offline_plan, plan_for                  # noqa: E402
from exam_drill.records import (                                    # noqa: E402
    COLUMNS, REASONS, RecordError, load_records, write_blank_sheet,
)
from exam_drill.report import write_html, write_markdown            # noqa: E402
from exam_drill.syllabus import PASS_RULE, SUBJECTS, subject_of     # noqa: E402

DEFAULT_OUT = BASE_DIR / "outputs"
SAMPLE = BASE_DIR / "data" / "samples" / "records_sample.csv"
DEFAULT_INPUT = BASE_DIR / "data" / "records.csv"


def _source(args) -> Path:
    if args.demo:
        return SAMPLE
    return Path(args.input)


def cmd_sheet(args: argparse.Namespace) -> int:
    keys = ([subject_of(name).key for name in args.subject]
            if args.subject else [item.key for item in SUBJECTS])
    path = Path(args.out or (BASE_DIR / "data" / f"records_{args.round_name}.csv"))
    write_blank_sheet(path, args.round_name, keys, questions=args.questions)

    print(f"빈 기록표를 만들었습니다: {path}")
    print(f"  {args.round_name} · 과목 {len(keys)}개 · {len(keys) * args.questions}줄")
    print()
    print("채우는 법:")
    print("  정오   맞았으면 O, 틀렸으면 X (안 푼 줄은 비워 두세요)")
    print(f"  단원   그 문제가 어느 단원인지 (`python cli.py subjects` 로 목록)")
    print(f"  이유   틀렸을 때만. {' / '.join(REASONS)}")
    print("  소요초 잰 사람만. 안 재도 됩니다")
    print()
    print("  ※ 문제 지문을 적는 칸은 없습니다. 적지 마세요 (저작권)")
    return 0


def cmd_subjects(args: argparse.Namespace) -> int:
    print(PASS_RULE)
    print()
    for subject in SUBJECTS:
        print(f"[{subject.round}] {subject.key:<8} {subject.name}"
              f"  ({subject.questions}문항 {subject.minutes}분"
              f" · 문항당 {subject.per_question_seconds}초)")
        for index in range(0, len(subject.units), 3):
            print("           " + " · ".join(subject.units[index:index + 3]))
        print()
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    result = load_records(_source(args))
    analysis = analyze(result.attempts)
    print(f"읽었습니다: {result.count}문항"
          + (f" (아직 안 푼 {len(result.skipped)}줄은 건너뜀)" if result.skipped else ""))
    print(f"  회차 {', '.join(analysis.rounds) or '미상'}"
          f" · 과목 {len(analysis.subjects)}개")
    missing = [item for item in result.attempts if item.wrong and not item.reason]
    if missing:
        print(f"  ⚠ 틀렸는데 이유를 안 적은 문항 {len(missing)}개."
              f" 이유가 없으면 무엇을 해야 할지 못 알려 줍니다")
    no_unit = [item for item in result.attempts if not item.unit]
    if no_unit:
        print(f"  ⚠ 단원을 안 적은 문항 {len(no_unit)}개. 단원별 표에서 빠집니다")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    result = load_records(_source(args))
    analysis = analyze(result.attempts)

    print(f"푼 문항 {analysis.attempts}개 · 과목 {len(analysis.subjects)}개")
    print(f"  {analysis.verdict}")

    plan: list[str] = []
    if not args.no_plan:
        if args.dry_run or not os.getenv("ANTHROPIC_API_KEY"):
            plan = offline_plan(analysis)
            print("  계획: 규칙으로 씁니다 (Claude 를 부르지 않습니다)")
        else:
            from shared.config import DEFAULT_MODEL
            from shared.llm import ask

            model = args.model or DEFAULT_MODEL
            plan = plan_for(analysis, ask, model)
            print(f"  계획: 모델 {model}")

    demo = bool(args.demo)
    md_path = write_markdown(analysis, Path(args.out), plan=plan, demo=demo,
                             ai_label_on=not args.no_ai_label)
    html_path = write_html(analysis, Path(args.out), plan=plan, demo=demo)

    print()
    print(f"  ✓ {md_path.name} ({md_path.stat().st_size:,}B)")
    print(f"  ✓ {html_path.name} ({html_path.stat().st_size:,}B)")
    print(f"  → {md_path.parent}")

    if analysis.failing:
        print()
        for item in analysis.failing:
            print(f"  ⚠ {item.name} {item.score}점 — 과락선까지 {item.margin}점")
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="본인이 푼 기출 결과로 약한 단원을 찾습니다 "
                    "(기출문제 자체는 들어 있지 않습니다)")
    subparsers = parser.add_subparsers(dest="command")

    sheet = subparsers.add_parser("sheet", help="빈 기록표를 만듭니다")
    sheet.add_argument("--round", dest="round_name", default="35회")
    sheet.add_argument("--subject", action="append", default=[],
                       help="과목 키. 여러 번 줄 수 있습니다. 비우면 전 과목")
    sheet.add_argument("--questions", type=int, default=40)
    sheet.add_argument("--out", default="")
    sheet.set_defaults(func=cmd_sheet)

    subjects = subparsers.add_parser("subjects", help="과목·단원 목록")
    subjects.set_defaults(func=cmd_subjects)

    for name, func, help_text in (
        ("check", cmd_check, "표가 제대로 적혔는지만 봅니다"),
        ("report", cmd_report, "보고서를 만듭니다 (md + html)"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--input", default=str(DEFAULT_INPUT))
        sub.add_argument("--demo", action="store_true",
                         help="샘플 기록표로 돕니다 (지어낸 숫자입니다)")
        if name == "report":
            sub.add_argument("--out", default=str(DEFAULT_OUT))
            sub.add_argument("--model", default="")
            sub.add_argument("--no-plan", action="store_true")
            sub.add_argument("--dry-run", action="store_true",
                             help="Claude 를 부르지 않고 규칙으로 계획을 씁니다")
            sub.add_argument("--no-ai-label", action="store_true")
        sub.set_defaults(func=func)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n예: python cli.py report --demo --dry-run", file=sys.stderr)
        return 1
    try:
        return args.func(args)
    except RecordError as exc:
        print(f"기록표를 읽지 못했습니다:\n{exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
