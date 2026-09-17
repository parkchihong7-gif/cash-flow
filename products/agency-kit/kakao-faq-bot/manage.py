"""운영 명령.

    python manage.py stats                  최근 14일 현황
    python manage.py stats --days 30
    python manage.py unmatched              못 맞힌 질문 상위 20개 (시트 추가 후보)
    python manage.py purge --before 2026-06-01   오래된 기록 지우기
    python manage.py ask "영업시간이요"      서버 없이 답만 만들어 보기 (점검용)

`stats` 가 리테이너의 실제 내용물이다.
    매달 고객에게 보여 줄 것은 "이만큼 응대했고, 이건 못 답했으니 시트에
    이렇게 추가하시죠" 다. 그게 월 유지비를 받는 근거가 된다.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parents[2]))

from logs import LogStore                                            # noqa: E402

__all__ = ["main", "build_parser"]


def _bar(value: int, biggest: int, width: int = 24) -> str:
    if biggest <= 0:
        return ""
    return "█" * max(1, round(value / biggest * width))


def cmd_stats(args: argparse.Namespace) -> int:
    store = LogStore(args.db)
    rows = store.daily_counts(args.days)
    totals = store.totals()

    if not rows:
        print("아직 쌓인 기록이 없습니다.")
        print("  챗봇이 한 번도 안 불렸거나, LOG_DB_PATH 가 다른 곳을 보고 있습니다.")
        return 0

    print(f"최근 {len(rows)}일 — 기록 파일 {store.path}")
    print()
    biggest = max(int(row["total"]) for row in rows)
    print(f"{'날짜':<12}{'질문':>6}{'못 답함':>8}{'평균ms':>8}  ")
    print("-" * 52)
    for row in rows:
        missed = int(row["missed"] or 0)
        print(f"{row['day']:<12}{int(row['total']):>6}{missed:>8}"
              f"{int(row['avg_ms'] or 0):>8}  {_bar(int(row['total']), biggest)}")

    total = int(totals["total"] or 0)
    missed = int(totals["missed"] or 0)
    rate = (total - missed) / total * 100 if total else 0.0
    print()
    print(f"누적 {total:,}건 · 답한 비율 {rate:.1f}% · 평균 {int(totals['avg_ms'] or 0)}ms"
          f" · 최대 {int(totals['max_ms'] or 0)}ms")

    slow = store.slow(over_ms=4000, limit=5)
    if slow:
        print()
        print(f"⚠ 4초를 넘긴 응답 {len(slow)}건 — 카카오는 5초를 넘기면 끊습니다")
        for row in slow:
            print(f"   {row['elapsed_ms']:>6}ms  {row['question'][:40]}")

    print()
    return cmd_unmatched(args, store=store)


def cmd_unmatched(args: argparse.Namespace, store: LogStore | None = None) -> int:
    store = store or LogStore(args.db)
    rows = store.unmatched(getattr(args, "limit", 20))
    if not rows:
        print("못 답한 질문이 없습니다. 시트가 잘 맞고 있습니다.")
        return 0

    print(f"시트에 추가할 후보 {len(rows)}개 (많이 들어온 순)")
    print()
    print(f"{'건수':>4}  질문")
    print("-" * 60)
    for row in rows:
        print(f"{int(row['hits']):>4}  {row['question'][:56]}")

    print()
    print("이대로 시트에 넣으시면 됩니다 — 답변 칸만 채우세요")
    print()
    print("질문,답변,카테고리,수정일")
    today = datetime.now().strftime("%Y-%m-%d")
    for row in rows[:10]:
        question = str(row["question"]).replace('"', "'")
        print(f'"{question}","(답변을 적어 주세요)",미분류,{today}')
    return 0


def cmd_purge(args: argparse.Namespace) -> int:
    store = LogStore(args.db)
    removed = store.purge_before(args.before)
    print(f"{args.before} 이전 기록 {removed:,}건을 지웠습니다.")
    print("  계약서에 적은 보관 기간을 지키는 손잡이입니다.")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    """서버를 띄우지 않고 답만 만들어 본다. 설치 직후 점검용."""
    from fastapi.testclient import TestClient

    from app import create_app

    ask_fn = None
    if args.dry_run:
        from sample_content import fake_ask

        ask_fn = fake_ask

    client = TestClient(create_app(ask_fn=ask_fn, store=LogStore(args.db)))
    payload = {
        "userRequest": {"utterance": args.question, "user": {"id": "manage-cli"}},
        "bot": {"id": "local"}, "action": {"name": "faq"},
    }
    response = client.post("/skill", json=payload)
    body = response.json()
    print(body["template"]["outputs"][0]["simpleText"]["text"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manage.py", description="카카오 FAQ 챗봇 운영 명령")
    parser.add_argument("--db", default=os.getenv("LOG_DB_PATH", str(BASE_DIR / "logs.db")),
                        help="기록 파일 경로")
    subparsers = parser.add_subparsers(dest="command")

    stats = subparsers.add_parser("stats", help="일별 질문 수와 못 맞힌 질문")
    stats.add_argument("--days", type=int, default=14)
    stats.add_argument("--limit", type=int, default=20)
    stats.set_defaults(func=cmd_stats)

    unmatched = subparsers.add_parser("unmatched", help="못 맞힌 질문만")
    unmatched.add_argument("--limit", type=int, default=20)
    unmatched.set_defaults(func=cmd_unmatched)

    purge = subparsers.add_parser("purge", help="오래된 기록 지우기")
    purge.add_argument("--before", required=True, help="이 날짜(YYYY-MM-DD) 이전을 지웁니다")
    purge.set_defaults(func=cmd_purge)

    ask = subparsers.add_parser("ask", help="서버 없이 답만 만들어 봅니다")
    ask.add_argument("question")
    ask.add_argument("--dry-run", action="store_true", help="Claude 를 부르지 않습니다")
    ask.set_defaults(func=cmd_ask)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
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
