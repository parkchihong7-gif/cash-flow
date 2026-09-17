"""산출물 세 개를 쓴다.

    matches.json     전체 결과. 다른 도구에 넘길 때 쓴다.
    insert_plan.md   어느 문단 뒤에 무엇을 어떤 문장으로 넣을지 — **사람이 보는 표**
    disclosure.txt   대가성 문구. 채널별로 어디에 넣는지까지

세 파일 모두 **맨 위에 대가성 문구가 붙는다.** 옵션이 아니다.
파일을 쓰기 직전에 문구가 살아 있는지 한 번 더 확인하고, 없으면 저장하지 않는다
(`disclosure.assert_disclosed`). 링크만 있고 문구가 없는 글은 쿠팡파트너스
자격 정지 사유이고, 그건 경고 없이 온다.

insert_plan 에는 **구매 의도 3 이상만** 들어간다. 걸러진 것도 표 아래에
"왜 뺐는지" 와 함께 남겨 둔다. 지워 버리면 쓰는 사람이 프로그램이 놓친 줄 안다.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from affiliate import disclosure                                     # noqa: E402
from affiliate.schema import MatchResult, ScoredMention              # noqa: E402
from shared import ai_label                                          # noqa: E402

__all__ = ["OUTPUT_FILES", "write_outputs", "insert_plan_markdown", "build_result"]

OUTPUT_FILES: tuple[str, ...] = ("matches.json", "insert_plan.md", "disclosure.txt")


def _won(value: int | float) -> str:
    return f"{int(round(value)):,}원"


def build_result(*, extraction, scored: list[ScoredMention], links: dict,
                 table, source_file: str, paragraph_count: int,
                 dry_run: bool, api_used: bool, warnings: list[str]) -> MatchResult:
    """검증된 결과 하나로 묶는다. 대가성 문구가 없으면 여기서 막힌다."""
    return MatchResult(
        disclosure=disclosure.COUPANG,
        source_file=source_file,
        title=extraction.title,
        summary=extraction.summary,
        medium=extraction.medium,
        paragraph_count=paragraph_count,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        rates_as_of=table.as_of,
        dry_run=dry_run,
        api_used=api_used,
        matches=scored,
        links=links,
        warnings=warnings,
    )


def _plan_rows(result: MatchResult) -> list[str]:
    rows = []
    for item in result.planned:
        mention = item.mention
        keywords = " / ".join(mention.keywords)
        rows.append(
            f"| {mention.paragraph} 뒤 | {item.matched_category} | {mention.intent} | "
            f"{keywords} | {_won(item.expected_commission)} | {item.score:,.0f} |")
    return rows


def insert_plan_markdown(result: MatchResult, paragraphs: list[str]) -> str:
    """사람이 보고 그대로 작업할 수 있는 표."""
    lines: list[str] = []
    lines.append("# 삽입 계획")
    lines.append("")
    lines.append(f"> {disclosure.COUPANG}")
    lines.append(">")
    lines.append("> 이 문구를 **본문 맨 위**에 함께 올리셔야 합니다. "
                 "자세한 자리는 `disclosure.txt` 에 있습니다.")
    lines.append("")

    if result.dry_run:
        lines.append("> ⚠️ **모의 실행 결과입니다.** 원고를 실제로 읽지 않은 예시값입니다.")
        lines.append("")

    lines.append(f"- 원고: `{result.source_file}` ({result.medium}, 문단 {result.paragraph_count}개)")
    if result.title:
        lines.append(f"- 제목: {result.title}")
    if result.summary:
        lines.append(f"- 내용: {result.summary}")
    lines.append(f"- 수수료율 표 기준일: {result.rates_as_of}")
    lines.append(f"- 링크: {'쿠팡 API 로 찾은 실제 상품' if result.api_used else '검색 주소만 (API 키 없음)'}")
    lines.append("")

    planned = result.planned
    if not planned:
        lines.append("## 넣을 자리가 없습니다")
        lines.append("")
        lines.append("구매 의도가 3 이상인 대목이 없습니다. **이 원고에는 링크를 붙이지 "
                     "않는 편이 낫습니다.** 억지로 넣으면 본문과 겉돌고, 그런 글은 "
                     "한 번 읽히고 끝납니다.")
    else:
        lines.append("## 넣을 자리")
        lines.append("")
        lines.append("| 자리 | 카테고리 | 의도 | 검색 키워드 | 1건 수수료 추정 | 우선순위 |")
        lines.append("|---|---|---|---|---|---|")
        lines += _plan_rows(result)
        lines.append("")
        lines.append("우선순위는 **1건 수수료 × 구매 의도 가중치**입니다. "
                     "전환율을 아는 계산이 아니라 순서를 정하는 눈금입니다.")
        lines.append("")

        lines.append("## 자리마다 무엇을 어떻게")
        lines.append("")
        for order, item in enumerate(planned, start=1):
            mention = item.mention
            lines.append(f"### {order}. {mention.paragraph}번 문단 뒤 "
                         f"— {item.matched_category} (의도 {mention.intent})")
            lines.append("")
            excerpt = paragraphs[mention.paragraph] if mention.paragraph < len(paragraphs) else ""
            if excerpt:
                head = excerpt.strip().replace("\n", " ")
                lines.append(f"> …{head[-90:]}" if len(head) > 90 else f"> {head}")
                lines.append("")
            lines.append(f"**넣을 문장**")
            lines.append("")
            lines.append(f"> {mention.insert_sentence}")
            lines.append("")
            if mention.reason:
                lines.append(f"- 이 강도로 본 이유: {mention.reason}")
            lines.append(f"- 수수료율 {item.rate * 100:.1f}% · 객단가 추정 {_won(item.avg_price)}"
                         f" → 1건 {_won(item.expected_commission)}")
            lines.append(f"- 근거: {item.rate_source}")
            lines.append("")
            candidates = []
            for keyword in mention.keywords:
                candidates += result.links.get(keyword, [])
            if candidates:
                lines.append("**링크 후보**")
                lines.append("")
                for candidate in candidates[:6]:
                    mark = "🔗" if candidate.kind == "api" else "🔍"
                    price = f" · {_won(candidate.price)}" if candidate.price else ""
                    tail = f" — {candidate.note}" if candidate.note else ""
                    lines.append(f"- {mark} [{candidate.title or candidate.url}]"
                                 f"({candidate.url}){price}{tail}")
                lines.append("")

    dropped = [item for item in result.matches if not item.in_plan]
    if dropped:
        lines.append("## 뺀 것")
        lines.append("")
        lines.append("본문과 이어지지 않아 넣지 않은 대목입니다. "
                     "프로그램이 못 본 것이 아니라 **일부러 뺀 것**입니다.")
        lines.append("")
        lines.append("| 자리 | 무엇 | 의도 | 뺀 이유 |")
        lines.append("|---|---|---|---|")
        for item in dropped:
            lines.append(f"| {item.mention.paragraph} | {item.matched_category} | "
                         f"{item.mention.intent} | {item.excluded_because} |")
        lines.append("")

    if result.warnings:
        lines.append("## 확인하실 것")
        lines.append("")
        for warning in result.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("## 올리기 전에")
    lines.append("")
    lines.append("- [ ] 대가성 문구를 **본문 맨 위**에 넣었습니다")
    lines.append("- [ ] 유튜브라면 업로드 화면의 '유료 프로모션 포함' 을 켰습니다")
    lines.append("- [ ] 삽입 문장을 **내 말투로** 고쳤습니다")
    lines.append("- [ ] 링크한 상품을 실제로 열어 보고, 품절·가격을 확인했습니다")
    lines.append("- [ ] 써 보지 않은 물건을 써 본 것처럼 쓰지 않았습니다")
    lines.append("- [ ] 효능·안전을 단정하는 문장이 없습니다")
    lines.append("")
    lines.append("마지막 두 줄이 제일 중요합니다. 한 번 어긴 채널은 댓글로 먼저 알려집니다.")

    return "\n".join(lines)


def write_outputs(result: MatchResult, paragraphs: list[str], out_dir: Path,
                  ai_label_on: bool = True) -> Path:
    """산출물 세 개를 쓴다. 문구가 빠진 파일은 저장하지 않는다."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 대가성 문구 — 가장 먼저 쓴다. 나머지가 실패해도 이건 남아야 한다.
    block = disclosure.disclosure_block(result.medium)
    disclosure.assert_disclosed(block, "disclosure.txt")
    (out_dir / "disclosure.txt").write_text(block + "\n", encoding="utf-8")

    # 2) 삽입 계획
    plan = insert_plan_markdown(result, paragraphs)
    disclosure.assert_disclosed(plan, "insert_plan.md")
    if ai_label_on:
        plan = ai_label.add_text_label(plan)
    (out_dir / "insert_plan.md").write_text(plan + "\n", encoding="utf-8")

    # 3) 전체 결과
    payload = json.loads(result.model_dump_json())
    payload["disclosure_notice"] = {
        "coupang": disclosure.COUPANG,
        "youtube": disclosure.YOUTUBE_DESCRIPTION,
        "instagram": disclosure.INSTAGRAM,
        "rule": "링크를 쓰는 모든 화면에 위 문구가 함께 있어야 합니다.",
    }
    if ai_label_on:
        payload["ai_generated"] = True
        payload["ai_notice"] = ai_label.label_text_for("ko")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    disclosure.assert_disclosed(text, "matches.json")
    (out_dir / "matches.json").write_text(text + "\n", encoding="utf-8")

    return out_dir
