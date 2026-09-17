"""포맷 아이디어 — 공백 지수 상위 키워드에 대해 3개씩.

    python suggest.py run                  상위 5개 키워드
    python suggest.py run --top 3
    python suggest.py run --demo --dry-run

**표절을 코드 구조로 막는다.**

    Claude 에게 주는 것:  키워드 이름 · 숫자 · 쇼츠/롱폼 비중
    Claude 에게 안 주는 것: **영상 제목 · 채널 이름 · 영상 주소**

    줄 수 있는데 안 준다. 없는 것은 따라 만들 수 없기 때문이다.
    프롬프트로 "베끼지 마라" 고만 하면 언젠가 새어 나간다. 아예 입력에서 뺀다.

노아AI(주언규)는 "터진 영상 찾아서 따라 만들기" 로 표절 논란을 겪고
2023년 2월에 서비스를 닫고 전액 환불했다(CLAUDE.md §3-1).
이 상품은 그 반대 방향으로 설계했다 — **공백을 찾아 주고, 무엇을 만들지는
사람이 정한다.**
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parents[1]))

from niche.commentary import copycat_hits                           # noqa: E402
from niche.metrics import analyze_all                               # noqa: E402
from niche.store import Store                                       # noqa: E402
from shared import ai_label, banned_phrases                         # noqa: E402

DEFAULT_DB = Path(os.getenv("NICHE_DB_PATH", str(BASE_DIR / "niche.db")))
DEFAULT_OUT = BASE_DIR / "outputs"
FIXTURE_DIR = BASE_DIR / "data" / "fixtures"

#: 몇 개 키워드에 대해 아이디어를 낼 것인가.
DEFAULT_TOP = 5

#: 키워드당 아이디어 수.
IDEAS_PER_KEYWORD = 3

SUGGEST_SYSTEM = """당신은 유튜브 채널 기획자다.

받는 것은 **키워드 이름과 숫자뿐**이다. 영상 제목도, 채널 이름도, 주소도 없다.
그것만 보고 포맷 아이디어를 낸다.

포맷 아이디어란
  - 무엇을 찍을지가 아니라 **어떤 틀로 만들지**다
  - 예: "하나를 끝까지 따라가는 기록", "같은 질문을 여러 사람에게",
    "실패한 것만 모아 보기", "숫자 하나를 파고들기"

각 아이디어에 담을 것
  - format: 틀 이름 (짧게)
  - why: 이 지표에서 왜 해 볼 만한지 한 줄. 숫자를 근거로
  - first_episode: 첫 편을 어떻게 시작할지 한 줄
  - length: "쇼츠" 또는 "롱폼" 또는 "둘 다"

절대 하지 않는 것
  - **다른 사람의 영상이나 채널을 따라 만들라는 말** — 그건 이 도구의 반대편이다
  - 조회수 예측
  - "이렇게 하면 됩니다" 같은 단정

쇼츠 비중이 높으면 짧은 틀을, 롱폼 쪽이 잘 보이면 긴 틀을 우선한다.
소형 채널 성과율이 높으면 "지금 시작해도 보일 수 있다" 는 쪽으로 읽는다.

출력은 JSON 하나만.
{"ideas": [{"format": "...", "why": "...", "first_episode": "...", "length": "쇼츠"}]}"""


def _facts(item) -> str:
    """모델에게 넘길 것. **키워드와 숫자뿐이다.**"""
    return (
        f"키워드: {item.keyword}\n"
        f"최근 30일 신규 영상: {item.videos}편\n"
        f"중앙값 조회수: {item.median_views:,}\n"
        f"공백 지수: {item.gap:,.1f} (중앙값 조회수 ÷ 신규 영상 수)\n"
        f"소형 채널 성과율: {item.breakout_rate:.1f}% "
        f"(구독자 1만 이하 채널이 구독자의 5배 넘게 본 비율)\n"
        f"쇼츠 {item.shorts}편(중앙값 {item.shorts_median:,}) / "
        f"롱폼 {item.longform}편(중앙값 {item.longform_median:,})\n"
        f"공급 증가율: {item.supply_growth:+.1f}%"
    )


def offline_ideas(item) -> list[dict]:
    """Claude 없이 내는 아이디어. 모의 실행과 폴백에 쓴다.

    지표를 보고 **틀만** 고른다. 어차피 사람이 고쳐 쓸 초안이다.
    """
    short_heavy = item.shorts_ratio >= 50
    length = "쇼츠" if short_heavy else ("롱폼" if item.shorts_ratio <= 25 else "둘 다")

    return [
        {
            "format": "하나를 끝까지 따라가기",
            "why": f"공백 지수가 {item.gap:,.1f} 로 보는 사람 대비 만드는 사람이 "
                   "적은 편이라, 깊게 파는 쪽이 눈에 띌 수 있습니다.",
            "first_episode": "가장 흔한 고민 하나를 골라 처음부터 끝까지 한 편에 담기",
            "length": length,
        },
        {
            "format": "실패한 것만 모아 보기",
            "why": f"소형 채널 성과율이 {item.breakout_rate:.1f}% 라 "
                   "새로 시작해도 보일 여지가 있습니다. 성공담보다 실패담이 덜 붐빕니다.",
            "first_episode": "직접 해 보고 안 됐던 것 세 가지를 이유와 함께",
            "length": length,
        },
        {
            "format": "숫자 하나를 파고들기",
            "why": f"최근 30일 신규 영상이 {item.videos}편입니다. "
                   "숫자를 근거로 말하는 편이 비슷한 영상 사이에서 갈립니다.",
            "first_episode": "직접 재 보거나 계산한 숫자 하나를 제목에 걸기",
            "length": length,
        },
    ][:IDEAS_PER_KEYWORD]


def ideas_for(item, ask_fn, model: str) -> tuple[list[dict], list[str]]:
    """아이디어 3개를 받는다. 걸리는 것은 버리고 규칙 아이디어로 채운다.

    Returns:
        (아이디어 목록, 경고 목록)
    """
    raw = ask_fn(SUGGEST_SYSTEM,
                 f"[지표]\n{_facts(item)}\n\n"
                 f"이 키워드에 맞는 포맷 아이디어 {IDEAS_PER_KEYWORD}개를 내라.",
                 model=model, json_mode=True)

    found = raw.get("ideas") if isinstance(raw, dict) else None
    fallback = offline_ideas(item)
    if not isinstance(found, list) or not found:
        return fallback, ["아이디어를 받지 못해 규칙으로 만든 것을 넣었습니다"]

    warnings: list[str] = []
    cleaned: list[dict] = []
    for index, idea in enumerate(found[:IDEAS_PER_KEYWORD]):
        if not isinstance(idea, dict):
            continue
        text = " ".join(str(value) for value in idea.values())
        copycat = copycat_hits(text)
        banned = banned_phrases.check(text)
        if copycat or banned:
            warnings.append(
                f"'{idea.get('format', '?')}' 은(는) 빼고 규칙 아이디어로 바꿨습니다"
                f" ({', '.join(copycat + banned)})")
            cleaned.append(fallback[index % len(fallback)])
            continue
        cleaned.append({
            "format": str(idea.get("format", "")).strip(),
            "why": str(idea.get("why", "")).strip(),
            "first_episode": str(idea.get("first_episode", "")).strip(),
            "length": str(idea.get("length", "둘 다")).strip(),
        })

    return (cleaned or fallback), warnings


def write_ideas(rows: list[dict], out_dir: Path, days: int, demo: bool = False,
                warnings: list[str] | None = None, ai_label_on: bool = True) -> Path:
    """`ideas_<날짜>.md` 를 쓴다."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# 포맷 아이디어",
        "",
        f"- 만든 날: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 모은 날수: {days}일치",
        f"- 키워드 {len(rows)}개 × 아이디어 {IDEAS_PER_KEYWORD}개",
        "",
    ]
    if demo:
        lines += ["> ⚠️ **샘플 자료로 만든 것입니다.** 숫자도 아이디어도 예시입니다.", ""]

    lines += [
        "> 이 아이디어는 **지표만 보고** 낸 것입니다. 다른 사람의 영상이나 채널을",
        "> 보고 만든 것이 아닙니다. 모델에게 영상 제목과 채널 이름을 주지 않습니다.",
        "",
        "---",
        "",
    ]

    for row in rows:
        item = row["metrics"]
        lines += [
            f"## {item.keyword}",
            "",
            f"공백 지수 {item.gap:,.1f} · 신규 영상 {item.videos}편 · "
            f"중앙값 조회수 {item.median_views:,} · "
            f"소형 채널 성과율 {item.breakout_rate:.1f}% · "
            f"쇼츠 비중 {item.shorts_ratio:.1f}%",
            "",
        ]
        for index, idea in enumerate(row["ideas"], start=1):
            lines += [
                f"### {index}. {idea.get('format', '')} ({idea.get('length', '')})",
                "",
                f"**왜** — {idea.get('why', '')}",
                "",
                f"**첫 편** — {idea.get('first_episode', '')}",
                "",
            ]
        lines.append("")

    if warnings:
        lines += ["## 확인하실 것", ""]
        lines += [f"- {line}" for line in warnings]
        lines.append("")

    lines += [
        "---",
        "",
        "## 이 문서를 쓰는 법",
        "",
        "- **틀만 가져가시고 내용은 본인 것으로 채우세요.** 남이 만든 영상을 보고",
        "  비슷하게 만드는 것과, 빈자리를 찾아 내 이야기로 채우는 것은 다릅니다",
        "- 세 개 중 하나만 골라 4주만 해 보세요. 세 개를 동시에 하면 다 어중간해집니다",
        "- 아이디어가 마음에 안 들면 지표를 다시 보세요. 아이디어보다 지표가 중요합니다",
        "",
        "이 도구는 특정 영상이나 채널을 따라 만들라고 하지 않습니다. "
        "무엇을 만들지는 사람이 정합니다.",
    ]

    body = "\n".join(lines)
    if ai_label_on:
        body = ai_label.add_text_label(body)

    stamp = datetime.now().strftime("%Y%m%d")
    path = out_dir / f"ideas_{stamp}.md"
    path.write_text(body + "\n", encoding="utf-8")
    return path


def cmd_run(args: argparse.Namespace) -> int:
    store = Store(args.db)
    demo = False
    if args.demo and store.counts()["days"] == 0:
        from niche.demo import seed_demo

        seed_demo(store, FIXTURE_DIR)
        demo = True
    elif args.demo:
        demo = True

    counts = store.counts()
    if counts["videos"] == 0:
        print("모은 자료가 없습니다. 먼저 collector 를 돌리세요.", file=sys.stderr)
        return 1

    metrics = analyze_all(store)[:args.top]
    print(f"공백 지수 상위 {len(metrics)}개 키워드에 아이디어를 냅니다")
    print("  모델에게 주는 것: 키워드와 숫자뿐 (영상 제목·채널명은 주지 않습니다)")
    print()

    if args.dry_run or not os.getenv("ANTHROPIC_API_KEY"):
        ask_fn, model = None, "규칙"
        print("  규칙으로 만듭니다 (Claude 를 부르지 않습니다)")
    else:
        from shared.config import DEFAULT_MODEL
        from shared.llm import ask

        ask_fn, model = ask, args.model or DEFAULT_MODEL

    rows: list[dict] = []
    warnings: list[str] = []
    for item in metrics:
        if ask_fn is None:
            ideas, notes = offline_ideas(item), []
        else:
            ideas, notes = ideas_for(item, ask_fn, model)
        rows.append({"metrics": item, "ideas": ideas})
        warnings += [f"{item.keyword}: {note}" for note in notes]
        print(f"  ✓ {item.keyword} — 아이디어 {len(ideas)}개")

    path = write_ideas(rows, Path(args.out), counts["days"], demo=demo,
                       warnings=warnings, ai_label_on=not args.no_ai_label)
    print()
    print(f"  → {path}")
    for line in warnings:
        print(f"  ! {line}")

    if args.json:
        payload = [{"keyword": row["metrics"].keyword, "ideas": row["ideas"]}
                   for row in rows]
        json_path = Path(args.out) / "ideas.json"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        print(f"  → {json_path}")

    print()
    print("틀만 가져가시고 내용은 본인 것으로 채우세요.")
    return 2 if warnings else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suggest.py",
        description="공백 지수 상위 키워드에 포맷 아이디어를 냅니다 "
                    "(영상·채널을 따라 만들라고 하지 않습니다)")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="아이디어를 냅니다")
    run.add_argument("--top", type=int, default=DEFAULT_TOP,
                     help=f"몇 개 키워드에 낼지 (기본 {DEFAULT_TOP})")
    run.add_argument("--out", default=str(DEFAULT_OUT))
    run.add_argument("--model", default="")
    run.add_argument("--demo", action="store_true", help="샘플 자료로 돌려 봅니다")
    run.add_argument("--dry-run", action="store_true",
                     help="Claude 를 부르지 않고 규칙으로 만듭니다")
    run.add_argument("--json", action="store_true", help="ideas.json 도 만듭니다")
    run.add_argument("--no-ai-label", action="store_true")
    run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n예: python suggest.py run --demo --dry-run", file=sys.stderr)
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
