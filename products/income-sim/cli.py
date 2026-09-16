"""수익 시뮬레이터 CLI.

    python cli.py run agency_retainer
    python cli.py run youtube_long --monthly_views=500000 --rpm=3000
    python cli.py compare agency_retainer ebook_course groupbuy
    python cli.py montecarlo saas_subscription --n 1000 --seed 42
    python cli.py html
    python cli.py models          # 모델 목록
    python cli.py sources <model> # 기본값과 근거

모든 출력 맨 위에 "추정치이며 실제 수익을 보장하지 않습니다" 가 붙습니다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from income_sim.compare import DEFAULT_BUDGET, compare_models      # noqa: E402
from income_sim.dashboard import build_dashboard                    # noqa: E402
from income_sim.engine import DISCLAIMER, simulate                  # noqa: E402
from income_sim.expr import ExpressionError                         # noqa: E402
from income_sim.montecarlo import run_montecarlo                    # noqa: E402
from income_sim.report import (                                     # noqa: E402
    banner, model_header, pad, projection_table, sources_table, width, won,
)
from income_sim.schema import ModelSpec, load_all                   # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = BASE_DIR / "outputs"


def _models() -> dict[str, ModelSpec]:
    return load_all()


def _pick(models: dict[str, ModelSpec], name: str) -> ModelSpec:
    if name in models:
        return models[name]
    by_number = {str(spec.number): spec for spec in models.values()}
    if name in by_number:
        return by_number[name]
    raise ValueError(
        f"모르는 모델입니다: {name}\n"
        f"  쓸 수 있는 모델: {', '.join(models)}\n"
        f"  목록을 보려면: python cli.py models")


def _overrides(extra: list[str], model: ModelSpec) -> dict[str, float]:
    """`--monthly_views=500000` 꼴을 읽는다."""
    values: dict[str, float] = {}
    for item in extra:
        if not item.startswith("--") or "=" not in item:
            raise ValueError(
                f"값은 `--이름=숫자` 꼴로 주세요: {item}\n"
                f"  예: --monthly_views=500000")
        key, _, raw = item[2:].partition("=")
        key = key.strip().replace("-", "_")
        text = raw.strip().replace(",", "").replace("원", "").replace("%", "")
        try:
            number = float(text)
        except ValueError:
            raise ValueError(f"숫자로 읽지 못했습니다: {item}") from None
        if raw.strip().endswith("%"):
            number /= 100
        values[key] = number
    model.with_overrides(values)          # 여기서 모르는 이름을 걸러낸다
    return values


# --------------------------------------------------------------------- 명령
def cmd_models(args: argparse.Namespace) -> int:
    models = _models()
    print(banner())
    print()
    print("부업 모델 8종")
    print()
    for spec in models.values():
        projection = simulate(spec)
        hourly = projection.hourly
        print(f"  {spec.number}. {pad(spec.name, 22)} {pad(spec.id, 20)}"
              f" 기본값 기준 시간당 {won(hourly) if hourly is not None else '—':>12}")
    print()
    print("  자세히 보려면:  python cli.py run <모델>")
    print("  근거를 보려면:  python cli.py sources <모델>")
    print()
    print("  ※ 위 숫자는 전부 기본값 기준입니다. 본인 수치로 바꿔야 뜻이 있습니다.")
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    model = _pick(_models(), args.model)
    print(banner())
    print()
    print(sources_table(model))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    model = _pick(_models(), args.model)
    overrides = _overrides(args.extra, model)
    projection = simulate(model, overrides)

    if args.json:
        print(json.dumps(projection.as_dict(), ensure_ascii=False, indent=2))
        return 0

    print(banner())
    print()
    print(model_header(model, projection.values))
    print()
    print(projection_table(projection))
    print()
    print("  근거를 보려면: python cli.py sources " + model.id)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    models = _models()
    chosen = [_pick(models, name) for name in args.models]
    if len(chosen) < 2:
        raise ValueError("두 개 이상을 적어 주세요. 예: python cli.py compare 7 6 5")

    rows = compare_models(chosen, budget_hours=args.hours)

    if args.json:
        print(json.dumps([{
            "model": row.model.id,
            "hourly": row.projection.hourly,
            "monthly_hours": row.monthly_hours,
            "total_profit": row.projection.total_profit,
            "net_after_initial": row.projection.net_after_initial,
            "scaled_monthly_profit": row.scaled_monthly_profit,
        } for row in rows], ensure_ascii=False, indent=2))
        return 0

    print(banner())
    print()
    print(f"같은 시간을 넣으면 어느 쪽이 나은가 — 월 {args.hours:,.0f}시간 기준")
    print()

    columns = [("모델", 24, "left"), ("시간당", 13, "right"), ("월 투입", 10, "right"),
               (f"월 {args.hours:,.0f}h 환산", 16, "right"),
               ("12개월 잔액", 16, "right"), ("누적 손익분기", 14, "right")]
    print(" ".join(pad(name, size, "center") for name, size, _ in columns))
    print(" ".join("─" * size for _, size, _ in columns))

    for rank, row in enumerate(rows, start=1):
        projection = row.projection
        breakeven = projection.cumulative_breakeven
        print(" ".join([
            pad(f"{rank}. {row.model.name}", 24),
            pad(won(projection.hourly), 13, "right"),
            pad(f"{row.monthly_hours:,.0f}h", 10, "right"),
            pad(won(row.scaled_monthly_profit), 16, "right"),
            pad(won(projection.net_after_initial), 16, "right"),
            pad(f"{breakeven}개월" if breakeven else "못 넘김", 14, "right"),
        ]))

    print()
    print("  정렬 기준은 12개월 손익이 아니라 **시간당 수익**입니다.")
    print("  손익이 커도 시간을 네 배 쓰고 있으면 더 나은 선택이 아니기 때문입니다.")
    print()
    print("  ⚠ '환산' 칸은 시간당 수익 × 시간인 단순 비례값입니다. 참고로만 보세요.")
    print("     고정비는 시간을 줄여도 줄지 않고,")
    print("     시간을 두 배 넣는다고 조회수가 두 배가 되지도 않습니다.")
    return 0


def cmd_montecarlo(args: argparse.Namespace) -> int:
    model = _pick(_models(), args.model)
    overrides = _overrides(args.extra, model)
    result = run_montecarlo(model, overrides, runs=args.n, seed=args.seed)

    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 0

    print(banner())
    print()
    print(model_header(model, result.base.values))
    print()
    print(f"값을 흔들어 {result.runs:,}번 돌렸습니다 (seed {result.seed})")
    print(f"  흔든 값: " + ", ".join(
        f"{model.param_map[key].label} ±{model.param_map[key].uncertain:.0%}"
        for key in result.shaken))
    print()

    print("  12개월 최종 잔액 (초기 투자까지 뺀 값)")
    print(f"    P10  {won(result.net.p10):>16}   열 번 중 한 번은 이보다 나쁩니다")
    print(f"    P50  {won(result.net.p50):>16}   한가운데")
    print(f"    P90  {won(result.net.p90):>16}   열 번 중 한 번은 이보다 좋습니다")
    print()
    print("  시간당 수익")
    print(f"    P10  {won(result.hourly.p10):>16}")
    print(f"    P50  {won(result.hourly.p50):>16}")
    print(f"    P90  {won(result.hourly.p90):>16}")
    print()
    print(f"  12개월 뒤 손해로 끝날 확률  {result.loss_rate:.1%}")
    print()
    print("  ※ 이 폭은 모델 파일에 적어 둔 가정(uncertain)에서 나온 것이지,")
    print("     실제 시장을 관측해서 얻은 분포가 아닙니다.")
    return 0


def cmd_html(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    path = build_dashboard(_models(), out_dir / "dashboard.html")
    print(banner())
    print()
    print(f"대시보드를 만들었습니다: {path}")
    print(f"  크기 {path.stat().st_size / 1024:.0f} KB · 파일 하나로 끝납니다")
    print()
    print("  브라우저로 열어서 슬라이더를 움직이면 바로 다시 계산됩니다.")
    print("  인터넷이 되어야 그래프가 그려집니다 (Chart.js 를 CDN 에서 받습니다).")
    return 0


# ------------------------------------------------------------------ 진입점
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description=f"부업 모델별 손익 추정. {DISCLAIMER}",
    )
    subparsers = parser.add_subparsers(dest="command")

    listing = subparsers.add_parser("models", help="모델 8종 목록")
    listing.set_defaults(func=cmd_models)

    sources = subparsers.add_parser("sources", help="기본값과 그 근거를 봅니다")
    sources.add_argument("model")
    sources.set_defaults(func=cmd_sources)

    run = subparsers.add_parser("run", help="모델 하나를 12개월 돌립니다")
    run.add_argument("model")
    run.add_argument("--json", action="store_true", help="결과를 JSON 으로")
    run.set_defaults(func=cmd_run)

    compare = subparsers.add_parser("compare", help="모델을 시간당 수익으로 견줍니다")
    compare.add_argument("models", nargs="+")
    compare.add_argument("--hours", type=float, default=DEFAULT_BUDGET,
                         help=f"환산 기준 월 시간 (기본 {DEFAULT_BUDGET:.0f})")
    compare.add_argument("--json", action="store_true")
    compare.set_defaults(func=cmd_compare)

    monte = subparsers.add_parser("montecarlo", help="값을 흔들어 P10/P50/P90 를 봅니다")
    monte.add_argument("model")
    monte.add_argument("--n", type=int, default=1000, help="몇 번 돌릴지 (기본 1000)")
    monte.add_argument("--seed", type=int, default=20260916,
                       help="같은 값을 주면 결과가 항상 같습니다")
    monte.add_argument("--json", action="store_true")
    monte.set_defaults(func=cmd_montecarlo)

    html = subparsers.add_parser("html", help="슬라이더 대시보드 HTML 을 만듭니다")
    html.add_argument("--out", default=str(DEFAULT_OUT), help="저장 폴더")
    html.set_defaults(func=cmd_html)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    args.extra = extra

    if not getattr(args, "command", None):
        parser.print_help()
        print("\n예: python cli.py run agency_retainer", file=sys.stderr)
        return 1

    if extra and args.command not in ("run", "montecarlo"):
        print(f"오류: 모르는 옵션입니다: {' '.join(extra)}", file=sys.stderr)
        return 1

    try:
        return args.func(args)
    except (ValueError, ExpressionError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
    except FileNotFoundError as exc:
        print(f"파일을 찾지 못했습니다: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
