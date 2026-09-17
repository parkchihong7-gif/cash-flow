"""인스타 예약 발행 — 운영 명령.

    python manage.py import queue.csv            CSV 를 큐에 넣는다 (초안)
    python manage.py draft 3 --note "사진 설명"   캡션 초안을 만든다
    python manage.py list                         큐를 본다
    python manage.py show 3                       한 건을 자세히 본다
    python manage.py approve 3 --by "홍길동"       **사람이 승인한다**
    python manage.py run --dry-run                올릴 때가 된 것을 처리한다
    python manage.py refresh-token                60일 토큰을 갱신한다

**승인 없이는 아무것도 올라가지 않는다.** 이 프로그램에서 양보하지 않는 한 가지다.
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

from captions import draft_caption                                   # noqa: E402
from publisher import InstagramClient, credentials                   # noqa: E402
from queue_store import QueueStore                                   # noqa: E402
from scheduler import Runner, run_forever                            # noqa: E402

DEFAULT_DB = os.getenv("QUEUE_DB_PATH", str(BASE_DIR / "queue.db"))
DEFAULT_CSV = BASE_DIR / "queue.csv"

STATUS_LABEL = {
    "draft": "초안(승인 대기)",
    "approved": "승인됨",
    "published": "올라감",
    "failed": "실패",
    "canceled": "취소",
}


def _store(args) -> QueueStore:
    return QueueStore(args.db)


def cmd_import(args) -> int:
    store = _store(args)
    added = store.import_csv(args.path)
    print(f"{len(added)}건을 큐에 넣었습니다. 모두 **초안** 상태입니다.")
    if added:
        print("  다음: 캡션을 확인하고 `manage.py approve <번호> --by \"이름\"`")
    else:
        print("  새로 넣을 것이 없었습니다 (같은 시각·주소는 건너뜁니다).")
    return 0


def cmd_add(args) -> int:
    store = _store(args)
    post_id = store.add(args.at, args.media, caption=args.caption,
                        hashtags=args.hashtags, media_type=args.type)
    print(f"{post_id}번으로 넣었습니다 (초안).")
    return 0


def cmd_draft(args) -> int:
    """캡션 초안을 만들어 넣는다. **승인은 따로 받는다.**"""
    store = _store(args)
    post = store.get(args.id)
    if post is None:
        print(f"{args.id}번 글이 없습니다.", file=sys.stderr)
        return 1

    if args.dry_run:
        from sample_captions import fake_ask

        ask_fn, model = fake_ask, "dry-run"
        print("모의 실행 — Claude 를 부르지 않습니다 (비용 없음)")
    else:
        from shared.config import DEFAULT_MODEL
        from shared.llm import ask

        ask_fn, model = ask, args.model or DEFAULT_MODEL

    note = args.note or post.caption or "사진 설명이 없습니다"
    caption, hashtags, warnings = draft_caption(
        note, ask_fn, model, brand=args.brand, sponsored=args.sponsored)

    if not caption:
        print("캡션을 만들지 못했습니다. 직접 쓰세요.", file=sys.stderr)
        return 1

    store.set_caption(args.id, caption, hashtags)
    print()
    print(caption)
    if hashtags:
        print()
        print(hashtags)
    print()
    for warning in warnings:
        print(f"  ! {warning}")
    print(f"{args.id}번 캡션을 넣었습니다. **아직 초안입니다.**")
    print(f"  읽어 보시고 괜찮으면: manage.py approve {args.id} --by \"이름\"")
    return 2 if warnings else 0


def cmd_list(args) -> int:
    store = _store(args)
    posts = store.all(args.status)
    if not posts:
        print("큐가 비어 있습니다." if not args.status else f"'{args.status}' 인 글이 없습니다.")
        return 0

    print(f"{'번호':>4} {'발행시각':<17} {'상태':<14} {'종류':<6} 캡션")
    print("-" * 78)
    for post in posts:
        head = (post.caption or "(캡션 없음)").replace("\n", " ")[:28]
        print(f"{post.id:>4} {post.publish_at:<17} "
              f"{STATUS_LABEL.get(post.status, post.status):<14} {post.media_type:<6} {head}")

    counts = store.counts()
    print()
    print(" · ".join(f"{STATUS_LABEL.get(key, key)} {value}건"
                     for key, value in sorted(counts.items())))
    waiting = counts.get("draft", 0)
    if waiting:
        print(f"⚠ 승인을 기다리는 글이 {waiting}건 있습니다. 승인 전에는 올라가지 않습니다.")
    return 0


def cmd_show(args) -> int:
    store = _store(args)
    post = store.get(args.id)
    if post is None:
        print(f"{args.id}번 글이 없습니다.", file=sys.stderr)
        return 1

    print(f"{post.id}번 · {STATUS_LABEL.get(post.status, post.status)}")
    print(f"발행시각  {post.publish_at}")
    print(f"미디어    {post.media_url} ({post.media_type})")
    if post.approved_by:
        print(f"승인      {post.approved_by} · {post.approved_at}")
    if post.published_at:
        print(f"올라감    {post.published_at} · 게시물 {post.media_id}")
    if post.last_error:
        print(f"마지막 오류 {post.last_error}")
    print()
    print(post.full_caption or "(캡션 없음)")
    return 0


def cmd_approve(args) -> int:
    """사람이 승인한다. 이 명령 없이는 아무것도 올라가지 않는다."""
    store = _store(args)
    try:
        post = store.approve(args.id, args.by)
    except ValueError as exc:
        print(f"승인하지 못했습니다: {exc}", file=sys.stderr)
        return 1

    print(f"{post.id}번을 승인했습니다. ({post.approved_by}, {post.approved_at})")
    print(f"  {post.publish_at} 에 올라갑니다.")
    print("  올린 뒤에는 캡션을 못 고칩니다. 지금 한 번 더 읽어 보세요.")
    return 0


def cmd_unapprove(args) -> int:
    _store(args).unapprove(args.id)
    print(f"{args.id}번 승인을 풀었습니다. 다시 초안입니다.")
    return 0


def cmd_cancel(args) -> int:
    _store(args).cancel(args.id)
    print(f"{args.id}번을 취소했습니다.")
    return 0


def cmd_run(args) -> int:
    store = _store(args)
    token, user_id = credentials()

    client = None
    if args.dry_run:
        print("모의 실행 — 실제로 올리지 않습니다.")
    elif token and user_id:
        client = InstagramClient(access_token=token, ig_user_id=user_id)
        print(f"인스타 계정 {user_id[:6]}… 로 올립니다.")
    else:
        print("IG_ACCESS_TOKEN / IG_USER_ID 가 없습니다 → 모의 실행으로 돕니다.")
        print("  큐와 승인 흐름은 그대로 확인하실 수 있습니다. 오류가 아닙니다.")

    runner = Runner(store=store, client=client, dry_run=args.dry_run or client is None)

    if args.once:
        result = runner.tick()
        for post_id in result.published:
            print(f"  ✓ {post_id}번 올렸습니다")
        for post_id, error in result.failed:
            print(f"  ✗ {post_id}번 실패 — {error}")
        for post_id, reason in result.skipped:
            print(f"  · {post_id}번 건너뜀 — {reason}")
        if result.quiet:
            print("  올릴 때가 된 글이 없습니다.")

        waiting = runner.pending()
        if waiting:
            print(f"  ⚠ 발행 시각이 지났는데 승인 안 된 글이 {len(waiting)}건 있습니다")
            for post in waiting[:5]:
                print(f"     {post.id}번 · {post.publish_at}")
        return 0

    run_forever(runner, seconds=args.every)
    return 0


def cmd_refresh_token(args) -> int:
    token, user_id = credentials()
    app_id = os.getenv("FB_APP_ID", "").strip()
    app_secret = os.getenv("FB_APP_SECRET", "").strip()

    if not token:
        print("IG_ACCESS_TOKEN 이 없습니다.", file=sys.stderr)
        return 1
    if not (app_id and app_secret):
        print("FB_APP_ID / FB_APP_SECRET 이 필요합니다.", file=sys.stderr)
        print("  Meta 개발자 화면 → 앱 → 설정 → 기본에서 볼 수 있습니다.", file=sys.stderr)
        return 1

    client = InstagramClient(access_token=token, ig_user_id=user_id)
    try:
        result = client.refresh_long_lived_token(app_id, app_secret)
    except Exception as exc:
        print(f"갱신하지 못했습니다: {exc}", file=sys.stderr)
        return 1

    new_token = result.get("access_token", "")
    expires = int(result.get("expires_in", 0))
    if not new_token:
        print(f"토큰을 받지 못했습니다: {result}", file=sys.stderr)
        return 1

    print("새 토큰을 받았습니다.")
    print(f"  유효기간 약 {expires // 86400}일")
    print()
    print("  .env 의 IG_ACCESS_TOKEN 을 아래 값으로 바꾸세요:")
    print(f"  {new_token[:12]}…{new_token[-6:]}  (전체 길이 {len(new_token)}자)")
    print()
    print("  ⚠ 토큰 전체는 화면에 찍지 않습니다. 아래 파일에 저장했습니다.")
    out = BASE_DIR / ".token.new"
    out.write_text(new_token, encoding="utf-8")
    out.chmod(0o600)
    print(f"  {out} (읽고 나면 지우세요)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manage.py", description="인스타 예약 발행 관리")
    parser.add_argument("--db", default=DEFAULT_DB)
    subparsers = parser.add_subparsers(dest="command")

    importer = subparsers.add_parser("import", help="CSV 를 큐에 넣습니다")
    importer.add_argument("path", nargs="?", default=str(DEFAULT_CSV))
    importer.set_defaults(func=cmd_import)

    adder = subparsers.add_parser("add", help="한 건 직접 넣습니다")
    adder.add_argument("--at", required=True, help="발행시각 YYYY-MM-DD HH:MM")
    adder.add_argument("--media", required=True, help="공개된 https 이미지/영상 주소")
    adder.add_argument("--caption", default="")
    adder.add_argument("--hashtags", default="")
    adder.add_argument("--type", default="IMAGE", choices=["IMAGE", "REELS"])
    adder.set_defaults(func=cmd_add)

    drafter = subparsers.add_parser("draft", help="캡션 초안을 만듭니다")
    drafter.add_argument("id", type=int)
    drafter.add_argument("--note", default="", help="사진 설명·메모")
    drafter.add_argument("--brand", default="", help="가게 이름")
    drafter.add_argument("--sponsored", action="store_true", help="광고·협찬입니다")
    drafter.add_argument("--model", default="")
    drafter.add_argument("--dry-run", action="store_true")
    drafter.set_defaults(func=cmd_draft)

    lister = subparsers.add_parser("list", help="큐를 봅니다")
    lister.add_argument("--status", default="", choices=["", *STATUS_LABEL])
    lister.set_defaults(func=cmd_list)

    shower = subparsers.add_parser("show", help="한 건을 자세히 봅니다")
    shower.add_argument("id", type=int)
    shower.set_defaults(func=cmd_show)

    approver = subparsers.add_parser("approve", help="사람이 승인합니다")
    approver.add_argument("id", type=int)
    approver.add_argument("--by", required=True, help="승인하는 사람 이름")
    approver.set_defaults(func=cmd_approve)

    unapprover = subparsers.add_parser("unapprove", help="승인을 풉니다")
    unapprover.add_argument("id", type=int)
    unapprover.set_defaults(func=cmd_unapprove)

    canceller = subparsers.add_parser("cancel", help="취소합니다")
    canceller.add_argument("id", type=int)
    canceller.set_defaults(func=cmd_cancel)

    runner = subparsers.add_parser("run", help="때가 된 것을 올립니다")
    runner.add_argument("--dry-run", action="store_true")
    runner.add_argument("--once", action="store_true", help="한 번만 훑고 끝냅니다")
    runner.add_argument("--every", type=int, default=60, help="몇 초마다 볼지")
    runner.set_defaults(func=cmd_run)

    refresher = subparsers.add_parser("refresh-token", help="60일 토큰을 갱신합니다")
    refresher.set_defaults(func=cmd_refresh_token)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n승인 없이는 아무것도 올라가지 않습니다.", file=sys.stderr)
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
