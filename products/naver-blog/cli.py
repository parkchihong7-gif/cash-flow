"""네이버 블로그 포스팅 초안 생성기.

    python cli.py demand --keywords keywords.txt --fixture   수요·경쟁 보기
    python cli.py draft --input request.yaml --dry-run       초안 만들기
    python cli.py review --input outputs/draft_<날짜>.md      올리기 전 검사
    python cli.py disclosure --kind sponsored --name OO상사   대가성 문구 뽑기
    python cli.py policy                                     되는 것과 안 되는 것

**자동 게시는 하지 않습니다.** 네이버는 블로그 글쓰기 공개 API 가 없고,
브라우저를 흉내 내는 방식은 약관 위반이라 계정이 정지됩니다.
초안까지 만들어 드리면 복사해서 붙이시면 됩니다.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parents[1]))

from naver_blog.demand import (                                     # noqa: E402
    DAILY_CALL_LIMIT, DemandError, collect, make_client,
)
from naver_blog.draft import (                                      # noqa: E402
    DRAFT_SYSTEM, Draft, PLACEHOLDER, Request, build_prompt, offline_draft, parse_draft,
)
from naver_blog.policy import (                                     # noqa: E402
    BANNED_AUTOMATION, DISCLOSURE, DISCLOSURE_RULES, DisclosureMissing,
    NO_WRITE_API, SPONSOR_KINDS, disclosure_for,
)
from naver_blog.review import ready, review                         # noqa: E402

DEFAULT_OUT = BASE_DIR / "outputs"
DEFAULT_REQUEST = BASE_DIR / "request.yaml"
FIXTURE_DIR = BASE_DIR / "data" / "fixtures"
KEYWORDS = BASE_DIR / "keywords.txt"


def _client(args):
    if args.fixture:
        return make_client(fixture_dir=FIXTURE_DIR)
    return make_client(os.getenv("NAVER_CLIENT_ID", ""),
                       os.getenv("NAVER_CLIENT_SECRET", ""))


def cmd_policy(args: argparse.Namespace) -> int:
    print("네이버 블로그에서 되는 것과 안 되는 것")
    print()
    print(f"✗ {NO_WRITE_API}")
    print(f"✗ {BANNED_AUTOMATION}")
    print()
    print("○ 검색 API — 그 키워드로 이미 몇 건이 쓰였는지 (하루 25,000회, 무료)")
    print("○ 데이터랩 — 검색어 트렌드의 **상대값**. 절대 검색 수는 안 줍니다")
    print("○ 초안 작성 · 검사 · 대가성 문구 — 전부 이 프로그램 안에서")
    print()
    print("대가성 문구 규칙:")
    for rule in DISCLOSURE_RULES:
        print(f"  - {rule}")
    return 0


def cmd_disclosure(args: argparse.Namespace) -> int:
    if args.kind in ("", "none"):
        print("대가를 받지 않은 글에는 문구가 필요 없습니다.")
        print("받으셨다면: " + " / ".join(k for k in SPONSOR_KINDS if k != "none"))
        return 0
    text = disclosure_for(args.kind, args.name)
    print(text)
    print()
    print("넣는 법:")
    for rule in DISCLOSURE_RULES:
        print(f"  - {rule}")
    return 0


def cmd_demand(args: argparse.Namespace) -> int:
    path = Path(args.keywords)
    if not path.is_file():
        raise ValueError(f"키워드 파일이 없습니다: {path}")
    words = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    if not words:
        raise ValueError("키워드가 하나도 없습니다")

    client = _client(args)
    rows = collect(words, client, months=args.months)

    print(f"키워드 {len(rows)}개 · 호출 {client.calls}회"
          f" (하루 한도 {DAILY_CALL_LIMIT:,}회)")
    if args.fixture:
        print("  ※ 샘플 자료입니다. 실제 값이 아닙니다")
    print()
    print(f"{'키워드':<22}{'이미 쓰인 글':>12}{'경쟁':>12}{'흐름':>12}")
    print("-" * 60)
    for row in rows:
        print(f"{row.word:<22}{row.total_posts:>12,}{row.competition:>12}"
              f"{row.trend_direction:>12}")
    print()
    open_ones = [row for row in rows if not row.crowded and not row.too_quiet]
    if open_ones:
        print(f"덜 붐비는 키워드: {', '.join(row.word for row in open_ones[:3])}")
    quiet = [row for row in rows if row.too_quiet]
    if quiet:
        print(f"너무 한산한 키워드: {', '.join(row.word for row in quiet)}")
        print("  경쟁이 없는 게 아니라 **찾는 사람이 없는 것**일 수 있습니다. "
              "흐름이 오르는 중인지 같이 보세요.")
    print("※ 글 수는 경쟁의 한 가지 신호일 뿐입니다. "
          "붐벼도 각도가 다르면 들어갈 자리가 있습니다.")
    return 0


def _request(path: Path) -> Request:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    known = {"topic", "keyword", "audience", "tone", "sponsor_kind",
             "sponsor_name", "must_include"}
    unknown = [key for key in raw if key not in known]
    if unknown:
        raise ValueError(f"모르는 항목: {', '.join(unknown)}")
    if not (raw.get("topic") or "").strip():
        raise ValueError("topic 이 비어 있습니다. 무엇에 대한 글인지 적으세요")
    return Request(**raw)


def cmd_draft(args: argparse.Namespace) -> int:
    path = Path(args.input)
    if not path.is_file():
        raise ValueError(f"요청 파일이 없습니다: {path}\n  request.yaml 을 본떠 만드세요")
    request = _request(path)

    if args.dry_run or not os.getenv("ANTHROPIC_API_KEY"):
        draft = offline_draft(request)
        print("초안: 뼈대만 만들었습니다 (Claude 를 부르지 않습니다)")
    else:
        from shared.config import DEFAULT_MODEL
        from shared.llm import ask

        model = args.model or DEFAULT_MODEL
        raw = ask(DRAFT_SYSTEM, build_prompt(request), model=model, max_tokens=3000)
        draft = parse_draft(raw, request)
        print(f"초안: 모델 {model}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    body_path = out_dir / f"draft_{today}.md"

    text = draft.full_text()
    if not args.no_ai_label and not args.dry_run:
        from shared.ai_label import add_text_label
        text = add_text_label(text)
    body_path.write_text(text, encoding="utf-8")

    issues = review(draft, paid=request.paid)
    print()
    print(f"  제목: {draft.title}")
    print(f"  본문 {draft.chars:,}자 · 소제목 {len(draft.headings)}개"
          f" · 태그 {len(draft.tags)}개")
    if draft.disclosure:
        print(f"  대가성 문구: {draft.disclosure}")
    print()
    for issue in issues:
        print(f"  {issue.mark} {issue.title}")
        print(f"      {issue.detail}")
    print()
    print(f"  ✓ {body_path.name} ({body_path.stat().st_size:,}B)")
    print(f"  → {body_path.parent}")
    print()
    if not ready(issues):
        print("  아직 올리시면 안 됩니다. 위의 ✗ 를 먼저 고치세요.")
        return 2
    print("  복사해서 네이버 블로그 글쓰기에 붙이시면 됩니다. "
          "(자동 게시는 하지 않습니다)")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    path = Path(args.input)
    if not path.is_file():
        raise ValueError(f"파일이 없습니다: {path}")
    text = path.read_text(encoding="utf-8")

    lines = text.splitlines()
    title = next((line.lstrip("# ").strip() for line in lines
                  if line.startswith("#")), path.stem)
    tags: list[str] = []
    for line in lines:
        if line.startswith("태그:"):
            tags = [tag.strip() for tag in line.split(":", 1)[1].split(",") if tag.strip()]
    draft = Draft(title=title, body=text, tags=tags,
                  disclosure="" if args.kind in ("", "none")
                  else disclosure_for(args.kind, args.name))

    issues = review(draft, paid=args.kind not in ("", "none"))
    print(f"{path.name} · 본문 {draft.chars:,}자")
    print()
    for issue in issues:
        print(f"  {issue.mark} {issue.title}")
        print(f"      {issue.detail}")
    print()
    if ready(issues):
        print("올리셔도 됩니다.")
        return 0
    print("아직 올리시면 안 됩니다.")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="네이버 블로그 초안을 만들고 올리기 전에 검사합니다 "
                    "(자동 게시는 하지 않습니다)")
    subparsers = parser.add_subparsers(dest="command")

    policy = subparsers.add_parser("policy", help="되는 것과 안 되는 것")
    policy.set_defaults(func=cmd_policy)

    disc = subparsers.add_parser("disclosure", help="대가성 문구를 뽑습니다")
    disc.add_argument("--kind", default="sponsored", choices=list(SPONSOR_KINDS))
    disc.add_argument("--name", default="")
    disc.set_defaults(func=cmd_disclosure)

    demand = subparsers.add_parser("demand", help="키워드 수요·경쟁")
    demand.add_argument("--keywords", default=str(KEYWORDS))
    demand.add_argument("--fixture", action="store_true",
                        help="키가 없어도 샘플 자료로 돕니다")
    demand.add_argument("--months", type=int, default=6)
    demand.set_defaults(func=cmd_demand)

    draft = subparsers.add_parser("draft", help="초안을 만듭니다")
    draft.add_argument("--input", default=str(DEFAULT_REQUEST))
    draft.add_argument("--out", default=str(DEFAULT_OUT))
    draft.add_argument("--model", default="")
    draft.add_argument("--dry-run", action="store_true",
                       help="Claude 를 부르지 않고 뼈대만 만듭니다")
    draft.add_argument("--no-ai-label", action="store_true")
    draft.set_defaults(func=cmd_draft)

    rev = subparsers.add_parser("review", help="올리기 전 검사")
    rev.add_argument("--input", required=True)
    rev.add_argument("--kind", default="none", choices=list(SPONSOR_KINDS))
    rev.add_argument("--name", default="")
    rev.set_defaults(func=cmd_review)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n예: python cli.py draft --dry-run", file=sys.stderr)
        return 1
    try:
        return args.func(args)
    except DisclosureMissing as exc:
        print(f"{exc}", file=sys.stderr)
    except DemandError as exc:
        print(f"{exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
