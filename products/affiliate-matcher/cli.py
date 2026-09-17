"""제휴 상품 매칭 CLI.

    python cli.py run data/samples/캠핑_유튜브_대본.md
    python cli.py run 원고.md --dry-run        # Claude 없이 예시값으로
    python cli.py rates                        # 수수료율 표와 근거 보기
    python cli.py check outputs/<slug>/matches.json

쿠팡 API 키(`COUPANG_ACCESS_KEY` / `COUPANG_SECRET_KEY`)가 있으면 실제 상품 후보를
가져오고, **없으면 검색 주소만 만들고 그대로 끝난다. 오류가 아니다.**
키가 없어도 "어느 문단에 어떤 키워드로 무엇을 붙일지" 까지는 나온다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from affiliate import disclosure                                     # noqa: E402
from affiliate.extract import Extractor, split_paragraphs            # noqa: E402
from affiliate.links import (                                        # noqa: E402
    CoupangClient, YOUTUBE_SHOPPING_NOTE, candidates_for, credentials,
)
from affiliate.output import OUTPUT_FILES, write_outputs, build_result   # noqa: E402
from affiliate.schema import MatchResult, slugify                    # noqa: E402
from affiliate.score import load_rates, score_all                    # noqa: E402
from shared.config import DEFAULT_MODEL                              # noqa: E402
from shared.llm import LLMError                                      # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = BASE_DIR / "outputs"
DEFAULT_INPUT = BASE_DIR / "data" / "samples" / "캠핑_유튜브_대본.md"


def _won(value: int | float) -> str:
    return f"{int(round(value)):,}원"


# ----------------------------------------------------------------------- run
def cmd_run(args: argparse.Namespace) -> int:
    source = Path(args.source)
    if not source.is_file():
        raise FileNotFoundError(f"원고 파일이 없습니다: {source}")
    text = source.read_text(encoding="utf-8")

    table = load_rates(args.rates)

    if args.dry_run:
        from affiliate.sample_content import fake_ask

        extractor = Extractor("dry-run", fake_ask)
        print("모의 실행 — Claude 를 부르지 않습니다 (비용 없음)")
    else:
        extractor = Extractor(args.model)
        print(f"모델 {args.model} 로 읽습니다. 호출 1회.")

    print()
    print(f"[1/4] 원고 읽기 — {source.name}")
    extraction, paragraphs = extractor.run(text, medium=args.medium, title=args.title)
    print(f"  문단 {len(paragraphs)}개 · 상품 언급 {len(extraction.mentions)}곳")

    print("[2/4] 점수 매기기")
    scored = score_all(extraction, table)
    kept = [item for item in scored if item.in_plan]
    print(f"  넣을 자리 {len(kept)}곳 · 뺀 자리 {len(scored) - len(kept)}곳"
          f" (구매 의도 {table.min_intent_for_plan} 미만)")

    print("[3/4] 링크 후보")
    access, secret = credentials()
    client = None
    if args.no_api:
        print("  --no-api 라 검색 주소만 만듭니다")
    elif access and secret:
        client = CoupangClient(access_key=access, secret_key=secret, sub_id=args.sub_id)
        print("  쿠팡 API 키를 찾았습니다. 상품을 찾아옵니다")
    else:
        print("  쿠팡 API 키가 없습니다 → 검색 주소만 만듭니다 (오류가 아닙니다)")
        print("     키를 넣으시려면 .env 에 COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY")

    keywords = [word for item in kept for word in item.mention.keywords]
    links, link_warnings = candidates_for(keywords, client)
    print(f"  키워드 {len(links)}개 · 후보 {sum(len(v) for v in links.values())}개")

    # 사람이 손볼 것(warnings)과 그냥 알아 두실 것(notes)을 나눈다.
    # 키가 없는 것은 잘못이 아니라 상태다. 이걸 경고로 세면 늘 경고가 떠 있게 되고,
    # 늘 떠 있는 경고는 아무도 안 본다.
    warnings = list(extractor.warnings) + link_warnings
    notes: list[str] = []
    if client is None:
        notes.append("쿠팡 API 키가 없어 검색 주소만 넣었습니다. 상품은 직접 고르세요.")
    if extraction.medium.startswith("유튜브") or args.medium.startswith("유튜브"):
        notes.append(YOUTUBE_SHOPPING_NOTE)

    print("[4/4] 파일 쓰기")
    result = build_result(
        extraction=extraction, scored=scored, links=links, table=table,
        source_file=source.name, paragraph_count=len(paragraphs),
        dry_run=args.dry_run, api_used=client is not None,
        warnings=warnings + notes,
    )
    slug = args.slug or slugify(extraction.title or source.stem, source.stem)
    out_dir = write_outputs(result, paragraphs, Path(args.out) / slug,
                            ai_label_on=not args.no_ai_label)

    print()
    for name in OUTPUT_FILES:
        path = out_dir / name
        size = f"{path.stat().st_size:,}B" if path.is_file() else "없음"
        print(f"  {'✓' if path.is_file() else '✗'} {name:16} {size:>10}")
    print(f"  → {out_dir}")

    if kept:
        print()
        print("  우선순위")
        for item in result.planned[:3]:
            print(f"    {item.mention.paragraph}번 문단 뒤 · {item.matched_category}"
                  f" · 1건 {_won(item.expected_commission)} · 의도 {item.mention.intent}")

    print()
    for note in notes:
        print(f"  · {note.splitlines()[0]}")
    for warning in warnings:
        print(f"  ! {warning.splitlines()[0]}")

    print()
    print("다음 순서")
    print("  1. insert_plan.md 를 열고 삽입 문장을 **내 말투로** 고치세요")
    print("  2. disclosure.txt 의 문구를 본문 맨 위에 넣으세요 (빠뜨리면 자격 정지)")
    print("  3. 링크한 상품을 실제로 열어 품절·가격을 확인하세요")
    if args.dry_run:
        print("\n※ 모의 실행 결과입니다. 원고를 실제로 읽지 않았습니다.")

    if not kept:
        print("\n넣을 자리가 없습니다. 이 원고에는 링크를 붙이지 않는 편이 낫습니다.")
        return 2
    return 2 if warnings else 0


# --------------------------------------------------------------------- rates
def cmd_rates(args: argparse.Namespace) -> int:
    table = load_rates(args.rates)
    print(f"수수료율 표 — 기준일 {table.as_of}")
    print(f"기본값 {table.default_rate * 100:.1f}% · {table.default_source}")
    print()
    print(f"{'카테고리':<12} {'수수료율':>7} {'객단가':>10} {'1건':>9}")
    print("-" * 46)
    for category in sorted(table.categories, key=lambda c: -c.rate * c.avg_price):
        one = int(round(category.avg_price * category.rate))
        print(f"{category.name:<12} {category.rate * 100:>6.1f}% "
              f"{category.avg_price:>9,}원 {one:>8,}원")
    print()
    print("구매 의도 가중치 (전부 가정값입니다)")
    for level in sorted(table.intent_weights):
        mark = "" if level >= table.min_intent_for_plan else "  ← 계획에서 제외"
        print(f"  {level}점 → {table.intent_weights[level]:.2f}{mark}")
    print()
    print(f"정산: {table.payout_note}")
    if args.sources:
        print()
        for category in table.categories:
            print(f"[{category.name}] {category.source}")
            if category.note:
                print(f"    {category.note}")
    else:
        print("\n근거를 보시려면 --sources")
    return 0


# --------------------------------------------------------------------- check
def cmd_check(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_file():
        raise FileNotFoundError(f"파일이 없습니다: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("disclosure_notice", None)
    raw.pop("ai_generated", None)
    raw.pop("ai_notice", None)
    try:
        result = MatchResult(**raw)
    except ValidationError as exc:
        lines = [f"  - {' → '.join(str(p) for p in item['loc'])}: {item['msg']}"
                 for item in exc.errors()[:10]]
        raise ValueError(f"{path.name} 이 규격에 맞지 않습니다:\n" + "\n".join(lines)) from exc

    disclosure.assert_disclosed(result.disclosure, path.name)
    print(f"{path.name} 은 규격에 맞습니다.")
    print(f"  언급 {len(result.matches)}곳 · 계획에 넣은 것 {len(result.planned)}곳")
    print(f"  링크 키워드 {len(result.links)}개 · 대가성 문구 있음")
    bad = [item for item in result.planned if item.mention.intent < 3]
    if bad:
        print(f"  ✗ 구매 의도 3 미만인데 계획에 들어간 것 {len(bad)}개")
        return 2
    return 0


# ------------------------------------------------------------------- 진입점
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py", description="원고에서 제휴 상품을 붙일 자리를 찾습니다")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="원고 한 편을 읽고 산출물 3종을 만듭니다")
    run.add_argument("source", nargs="?", default=str(DEFAULT_INPUT), help="원고 파일")
    run.add_argument("--medium", default="", help="블로그 / 유튜브 대본 / 릴스 캡션")
    run.add_argument("--title", default="", help="글 제목")
    run.add_argument("--slug", default="", help="산출물 폴더 이름")
    run.add_argument("--out", default=str(DEFAULT_OUT), help="산출물 상위 폴더")
    run.add_argument("--rates", default="", help="수수료율 표 경로")
    run.add_argument("--model", default=DEFAULT_MODEL, help=f"기본: {DEFAULT_MODEL}")
    run.add_argument("--sub-id", default="", help="쿠팡 딥링크 subId (채널 구분용)")
    run.add_argument("--no-api", action="store_true", help="키가 있어도 부르지 않습니다")
    run.add_argument("--dry-run", action="store_true", help="Claude 없이 예시값으로")
    run.add_argument("--no-ai-label", action="store_true", help="AI 생성물 표시를 끕니다")
    run.set_defaults(func=cmd_run)

    rates = subparsers.add_parser("rates", help="수수료율 표와 근거를 봅니다")
    rates.add_argument("--rates", default="", help="수수료율 표 경로")
    rates.add_argument("--sources", action="store_true", help="근거 문장까지 봅니다")
    rates.set_defaults(func=cmd_rates)

    check = subparsers.add_parser("check", help="matches.json 을 다시 검사합니다")
    check.add_argument("path", help="matches.json 경로")
    check.set_defaults(func=cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n예: python cli.py run data/samples/캠핑_유튜브_대본.md --dry-run",
              file=sys.stderr)
        return 1

    if getattr(args, "rates", "") == "":
        from affiliate.score import DEFAULT_RATES_PATH

        args.rates = str(DEFAULT_RATES_PATH)

    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"파일을 찾지 못했습니다: {exc}", file=sys.stderr)
    except disclosure.DisclosureMissing as exc:
        print(f"대가성 문구가 없어 저장하지 않았습니다:\n{exc}", file=sys.stderr)
    except LLMError as exc:
        print(f"추출 실패: {exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
