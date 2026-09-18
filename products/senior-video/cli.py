"""시니어 영상 제작 비용 견적·절감기.

    python cli.py estimate --input plan.yaml     견적서 만들기
    python cli.py estimate --demo                샘플 기획으로
    python cli.py rates                          단가표와 출처
    python cli.py spec                           시니어 시청자 규격
    python cli.py quota --monthly 60             업로드 한도 계산
    python cli.py queue add "제목" --chars 1500  승인 대기열에 초안 넣기
    python cli.py queue list
    python cli.py approve 3 --by 박치홍           **사람이 승인**해야 올릴 수 있습니다

**승인 없이 올리는 경로는 없습니다.** 유튜브 2025.7 양산형 콘텐츠 정책 때문입니다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parents[1]))

from senior_video.estimate import VideoPlan, estimate                    # noqa: E402
from senior_video.rates import RateError, load_rates                     # noqa: E402
from senior_video.report import write_report                             # noqa: E402
from senior_video.savings import suggest                                 # noqa: E402
from senior_video.senior import RULES, SPEC_SUMMARY, check_plan, grade   # noqa: E402
from senior_video.upload import (                                        # noqa: E402
    AUDIT_NOTE, MAX_UPLOADS_PER_DAY, Queue, QueueError, UPLOAD_UNITS, uploads_possible,
)

RATES_PATH = BASE_DIR / "data" / "unit_costs.yaml"
DEFAULT_PLAN = BASE_DIR / "plan.yaml"
DEFAULT_OUT = BASE_DIR / "outputs"
DEFAULT_QUEUE = BASE_DIR / "queue.db"

#: --demo 에 쓰는 기획. 일부러 규격을 몇 개 어겨 두었다. 경고가 어떻게 뜨는지 보여 준다.
DEMO_PLAN = {
    "title": "어르신을 위한 스마트폰 사용법 (샘플)",
    "script_chars": 1500, "images": 12, "monthly_videos": 20,
    "tts": "elevenlabs", "image_source": "ai-image", "script_source": "claude-opus",
    "subtitle_px": 48, "subtitle_chars": 22, "speech_rate": 340,
    "bgm_db": -10, "scene_seconds": 2.5, "contrast": 3.0, "length_minutes": 9,
}


def _load_plan(args) -> VideoPlan:
    if args.demo:
        return VideoPlan(**DEMO_PLAN)
    path = Path(args.input)
    if not path.is_file():
        raise ValueError(
            f"기획 파일이 없습니다: {path}\n"
            f"  `plan.yaml` 을 본떠 만드시거나 `--demo` 로 먼저 보세요")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    known = VideoPlan().__dict__.keys()
    unknown = [key for key in raw if key not in known]
    if unknown:
        raise ValueError(
            f"모르는 항목이 있습니다: {', '.join(unknown)}\n"
            f"  쓸 수 있는 항목: {', '.join(known)}")
    return VideoPlan(**raw)


def cmd_estimate(args: argparse.Namespace) -> int:
    rates = load_rates(RATES_PATH)
    plan = _load_plan(args)
    est = estimate(plan, rates)
    savings = suggest(est, rates)
    findings = check_plan(plan.as_check())

    print(f"{plan.title} · 월 {plan.monthly_videos}편")
    if est.free:
        print(f"  청구서 0원 — 무료 조합입니다 (전기값 {est.per_video:,.0f}원 별도)")
    else:
        print(f"  편당 {est.per_video:,.0f}원 · 월 {est.per_month:,.0f}원"
              f" · 연 {est.per_year:,.0f}원")
        biggest = est.biggest
        if biggest:
            print(f"  가장 큰 줄: {biggest.label} ({est.share(biggest)}%)")

    if savings:
        top = savings[0]
        print(f"  가장 큰 절감: {top.title} — 연 {top.yearly_won:,.0f}원")
        unsafe = [item for item in savings if not item.senior_safe]
        if unsafe:
            print(f"  ⚠ 시니어에게 불리한 절감안 {len(unsafe)}개 (견적서에 대가를 적었습니다)")

    print(f"  규격: {grade(findings)}")

    quota = uploads_possible(plan.monthly_videos)
    if not quota["fits"]:
        print(f"  ⚠ 월 {plan.monthly_videos}편은 API 쿼터를 넘습니다"
              f" (최대 월 {quota['max_monthly']}편)")

    path = write_report(est, savings, findings, Path(args.out),
                        note="샘플 기획으로 만든 견적입니다." if args.demo else "")
    print()
    print(f"  ✓ {path.name} ({path.stat().st_size:,}B)")
    print(f"  → {path.parent}")

    warns = [item for item in findings if item.warn]
    return 2 if (warns or not quota["fits"]) else 0


def cmd_rates(args: argparse.Namespace) -> int:
    rates = load_rates(RATES_PATH)
    print(f"단가표 기준일 {rates.asof} · 환율 {rates.fx:,}원")
    print(f"※ {rates.caution}")
    print()
    for group, rows, unit in (("음성(TTS)", rates.tts, "1,000자"),
                              ("이미지", rates.image, "장"),
                              ("대본", rates.script, "편")):
        print(f"[{group}]")
        for row in rows:
            fit = f" 시니어 {row.fit_stars}" if row.senior_fit else ""
            print(f"  {row.key:<16} {row.won:>8,.1f}원/{unit}{fit}")
            print(f"  {'':<16} 출처: {row.source}")
        print()
    print(f"렌더(전기) 편당 {rates.render_won:,.0f}원"
          f" · 보관 GB당 월 {rates.storage_won:,.0f}원")
    return 0


def cmd_spec(args: argparse.Namespace) -> int:
    print("시니어 시청자 규격 — 취향이 아니라 몸이 달라서 생기는 기준입니다.")
    print()
    for rule in RULES:
        print(f"● {rule.title}")
        print(f"  권장: {rule.recommended}")
        for line in _wrap(rule.why, 66):
            print(f"  {line}")
        print()
    print(f"한 줄 요약: {SPEC_SUMMARY}")
    return 0


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def cmd_quota(args: argparse.Namespace) -> int:
    quota = uploads_possible(args.monthly)
    print(f"유튜브 Data API 하루 10,000 유닛 · 업로드 한 번 {UPLOAD_UNITS:,} 유닛")
    print(f"  → 하루 최대 {MAX_UPLOADS_PER_DAY}편, 월 {quota['max_monthly']}편")
    print()
    print(f"계획하신 월 {quota['monthly']}편 = 하루 {quota['per_day']}편"
          f" ({quota['units_per_day']:,} 유닛)")
    print(f"  {'쿼터 안에 들어갑니다' if quota['fits'] else '⚠ 쿼터를 넘습니다'}")
    print()
    print(AUDIT_NOTE)
    return 0 if quota["fits"] else 2


def cmd_queue(args: argparse.Namespace) -> int:
    queue = Queue(args.db)
    if args.action == "add":
        item_id = queue.add_draft(args.title, args.chars)
        print(f"초안으로 넣었습니다: {item_id}번 {args.title}")
        print("  승인 전에는 올릴 수 없습니다."
              f" `python cli.py approve {item_id} --by <이름>`")
        return 0

    items = queue.list(args.status)
    if not items:
        print("큐가 비어 있습니다.")
        return 0
    print(f"{'번호':<5}{'상태':<18}{'승인자':<10}제목")
    print("-" * 64)
    for item in items:
        print(f"{item.id:<5}{item.status_label:<18}{item.approved_by or '—':<10}{item.title}")
    counts = queue.counts()
    print()
    print(" · ".join(f"{key} {value}" for key, value in sorted(counts.items())))
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    queue = Queue(args.db)
    item = queue.approve(args.item_id, args.by, args.note)
    print(f"승인했습니다: {item.id}번 {item.title}")
    print(f"  승인자 {item.approved_by} · {item.approved_at}")
    print("  올리기 전에 대본을 소리 내어 한 번 읽어 보세요.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="시니어 대상 영상의 제작 비용을 견적하고 줄일 곳을 찾습니다 "
                    "(승인 없는 자동 업로드는 하지 않습니다)")
    subparsers = parser.add_subparsers(dest="command")

    est = subparsers.add_parser("estimate", help="견적서를 만듭니다")
    est.add_argument("--input", default=str(DEFAULT_PLAN))
    est.add_argument("--demo", action="store_true", help="샘플 기획으로 돕니다")
    est.add_argument("--out", default=str(DEFAULT_OUT))
    est.add_argument("--dry-run", action="store_true",
                     help="이 프로그램은 원래 외부 호출을 하지 않습니다. 호환용입니다")
    est.set_defaults(func=cmd_estimate)

    rates = subparsers.add_parser("rates", help="단가표와 출처")
    rates.set_defaults(func=cmd_rates)

    spec = subparsers.add_parser("spec", help="시니어 시청자 규격")
    spec.set_defaults(func=cmd_spec)

    quota = subparsers.add_parser("quota", help="업로드 한도 계산")
    quota.add_argument("--monthly", type=int, default=20)
    quota.set_defaults(func=cmd_quota)

    queue = subparsers.add_parser("queue", help="승인 대기열")
    queue.add_argument("action", choices=["add", "list"])
    queue.add_argument("title", nargs="?", default="")
    queue.add_argument("--chars", type=int, default=0)
    queue.add_argument("--status", default="")
    queue.add_argument("--db", default=str(DEFAULT_QUEUE))
    queue.set_defaults(func=cmd_queue)

    approve = subparsers.add_parser("approve", help="사람이 승인합니다")
    approve.add_argument("item_id", type=int)
    approve.add_argument("--by", required=True, help="승인한 사람 이름")
    approve.add_argument("--note", default="")
    approve.add_argument("--db", default=str(DEFAULT_QUEUE))
    approve.set_defaults(func=cmd_approve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n예: python cli.py estimate --demo", file=sys.stderr)
        return 1
    try:
        return args.func(args)
    except (RateError, QueueError) as exc:
        print(f"{exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
