"""분석기 — 쌓인 자료를 지표로 바꾼다.

    python analyzer.py run                    보고서 만들기 (md + html)
    python analyzer.py run --demo             샘플 자료 3일치로 만들어 보기
    python analyzer.py run --no-commentary    Claude 해설 없이
    python analyzer.py show                   터미널에서 표만 보기

**개별 영상을 추천하지 않는다.** 키워드와 포맷 단위 지표만 본다.
노아AI 전례(CLAUDE.md §3-1)를 피하려고 처음부터 그렇게 설계했다.
자세한 것은 README 의 '노아AI 전례와 설계 차이' 를 보세요.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parents[1]))

from niche.commentary import commentary_for                         # noqa: E402
from niche.metrics import analyze_all                               # noqa: E402
from niche.report import write_html, write_markdown                 # noqa: E402
from niche.store import Store                                       # noqa: E402

DEFAULT_DB = Path(os.getenv("NICHE_DB_PATH", str(BASE_DIR / "niche.db")))
DEFAULT_OUT = BASE_DIR / "outputs"
FIXTURE_DIR = BASE_DIR / "data" / "fixtures"


def _load_store(args) -> tuple[Store, bool]:
    """자료 창고를 연다. `--demo` 면 샘플 3일치를 채워서 연다."""
    if args.demo:
        from niche.demo import seed_demo

        store = Store(args.db)
        if store.counts()["days"] == 0:
            seed_demo(store, FIXTURE_DIR)
        return store, True
    return Store(args.db), False


def cmd_run(args: argparse.Namespace) -> int:
    store, demo = _load_store(args)
    counts = store.counts()

    if counts["videos"] == 0:
        print("모은 자료가 없습니다.", file=sys.stderr)
        print("  먼저 `python collector.py run --fixture` 로 한 번 모아 보세요.",
              file=sys.stderr)
        return 1

    print(f"자료 {counts['days']}일치 · 키워드 {counts['keywords']}개"
          f" · 영상 {counts['videos']:,}개")
    metrics = analyze_all(store)

    commentary: list[str] = []
    if not args.no_commentary:
        if args.dry_run or not os.getenv("ANTHROPIC_API_KEY"):
            from niche.commentary import offline_commentary

            commentary = offline_commentary(metrics, counts["days"])
            print("  해설: 규칙으로 씁니다 (Claude 를 부르지 않습니다)")
        else:
            from shared.config import DEFAULT_MODEL
            from shared.llm import ask

            commentary = commentary_for(metrics, counts["days"], ask,
                                        args.model or DEFAULT_MODEL)
            print(f"  해설: 모델 {args.model or DEFAULT_MODEL} · 5줄")

    md_path = write_markdown(metrics, Path(args.out), counts["days"],
                             commentary=commentary, demo=demo,
                             ai_label_on=not args.no_ai_label)
    html_path = write_html(metrics, Path(args.out), counts["days"],
                           commentary=commentary, demo=demo)

    print()
    print(f"  ✓ {md_path.name} ({md_path.stat().st_size:,}B)")
    print(f"  ✓ {html_path.name} ({html_path.stat().st_size:,}B)")
    print(f"  → {md_path.parent}")

    print()
    top = metrics[0] if metrics else None
    if top:
        print(f"  공백 지수 1위: {top.keyword} ({top.gap:,.1f})")
        friendly = [item.keyword for item in metrics if item.entry_friendly]
        if friendly:
            print(f"  소형 채널이 뚫고 있는 키워드: {', '.join(friendly)}")
        else:
            print("  소형 채널이 뚫은 키워드가 없습니다. 지금은 들어가기 어려운 자리입니다")

    if counts["days"] < 3:
        print()
        print("  ⚠ 아직 며칠치가 안 됩니다. 추이 지표는 며칠 더 모아야 뜻이 생깁니다.")
        return 2
    if demo:
        print()
        print("  ※ 샘플 자료로 만든 보고서입니다. 숫자는 지어낸 것입니다.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store, _ = _load_store(args)
    counts = store.counts()
    if counts["videos"] == 0:
        print("모은 자료가 없습니다. 먼저 collector 를 돌리세요.", file=sys.stderr)
        return 1

    metrics = analyze_all(store)
    print(f"{counts['days']}일치 · 키워드 {len(metrics)}개 (공백 지수 높은 순)")
    print()
    print(f"{'키워드':<20}{'공백':>9}{'영상':>6}{'중앙값':>10}{'소형뚫림':>9}{'쇼츠':>7}")
    print("-" * 64)
    for item in metrics:
        mark = " *" if item.entry_friendly else ""
        print(f"{item.keyword:<20}{item.gap:>9,.1f}{item.videos:>6}"
              f"{item.median_views:>10,}{item.breakout_rate:>8.1f}%"
              f"{item.shorts_ratio:>6.1f}%{mark}")
    print()
    print("* = 소형 채널이 뚫고 있는 키워드 (성과율 20% 이상)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyzer.py",
        description="쌓인 자료를 키워드·포맷 단위 지표로 바꿉니다 "
                    "(개별 영상 추천은 하지 않습니다)")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="보고서를 만듭니다 (md + html)")
    run.add_argument("--demo", action="store_true",
                     help="샘플 자료 3일치를 채워 넣고 봅니다 (키가 없어도 됩니다)")
    run.add_argument("--out", default=str(DEFAULT_OUT))
    run.add_argument("--model", default="")
    run.add_argument("--no-commentary", action="store_true", help="해설을 빼고 만듭니다")
    run.add_argument("--dry-run", action="store_true",
                     help="Claude 를 부르지 않고 규칙으로 해설을 씁니다")
    run.add_argument("--no-ai-label", action="store_true")
    run.set_defaults(func=cmd_run)

    show = subparsers.add_parser("show", help="터미널에서 표만 봅니다")
    show.add_argument("--demo", action="store_true")
    show.set_defaults(func=cmd_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n예: python analyzer.py run --demo --dry-run", file=sys.stderr)
        return 1
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"파일을 찾지 못했습니다: {exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
