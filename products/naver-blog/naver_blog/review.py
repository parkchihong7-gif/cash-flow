"""올리기 전 검사 — **사람이 읽을 자리를 남겼는지부터 본다.**

이 검사기는 품질을 재지 않는다. 그건 사람이 한다. 여기서는 **올리면 탈이
나는 것**만 본다.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared import banned_phrases

from naver_blog.draft import Draft, PLACEHOLDER
from naver_blog.policy import DISCLOSURE_RULES

__all__ = ["Issue", "review", "MIN_CHARS", "MAX_CHARS", "MIN_HEADINGS", "MAX_TAGS"]

MIN_CHARS = 1000       # 이보다 짧으면 체류시간이 안 나온다
MAX_CHARS = 4000       # 이보다 길면 끝까지 안 읽는다
MIN_HEADINGS = 3
MAX_TAGS = 10          # 태그를 많이 단다고 노출이 늘지 않는다


@dataclass
class Issue:
    """검사 결과 한 줄."""

    level: str          # block / warn / note
    title: str
    detail: str

    @property
    def blocking(self) -> bool:
        return self.level == "block"

    @property
    def mark(self) -> str:
        return {"block": "✗", "warn": "⚠", "note": "·"}[self.level]


def review(draft: Draft, paid: bool = False) -> list[Issue]:
    """올리기 전에 볼 것. block 이 하나라도 있으면 올리면 안 된다."""
    issues: list[Issue] = []

    # 1) 사람이 채울 자리 — 이게 이 상품의 핵심이다
    if draft.placeholders:
        issues.append(Issue(
            "block", f"채우지 않은 자리가 {draft.placeholders}곳 있습니다",
            f"'{PLACEHOLDER}' 를 본인 경험으로 바꾸세요. "
            f"네이버 검색은 원본성을 봅니다. 이 자리를 지우기만 하면 "
            f"일반론만 남은 글이 됩니다"))
    else:
        issues.append(Issue(
            "note", "빈칸을 모두 채우셨습니다",
            "직접 겪은 내용이 들어갔는지 한 번 더 보세요"))

    # 2) 대가성 문구
    if paid:
        if not draft.disclosure:
            issues.append(Issue(
                "block", "대가성 문구가 없습니다",
                "대가를 받은 글은 경제적 이해관계를 공개해야 합니다(표시광고법)"))
        else:
            issues.append(Issue(
                "note", "대가성 문구가 맨 위에 들어갑니다",
                " / ".join(DISCLOSURE_RULES[:2])))

    # 3) 길이
    if draft.chars < MIN_CHARS:
        issues.append(Issue(
            "warn", f"본문이 {draft.chars:,}자로 짧습니다",
            f"{MIN_CHARS:,}자는 넘기는 편이 좋습니다. 짧으면 들어왔다 바로 나갑니다"))
    elif draft.chars > MAX_CHARS:
        issues.append(Issue(
            "warn", f"본문이 {draft.chars:,}자로 깁니다",
            f"{MAX_CHARS:,}자를 넘으면 끝까지 읽는 사람이 줄어듭니다. 나눠 쓰세요"))

    # 4) 소제목
    if len(draft.headings) < MIN_HEADINGS:
        issues.append(Issue(
            "warn", f"소제목이 {len(draft.headings)}개뿐입니다",
            f"{MIN_HEADINGS}개 이상으로 나누세요. 한 덩어리가 길면 읽다가 나갑니다"))

    # 5) 태그
    if len(draft.tags) > MAX_TAGS:
        issues.append(Issue(
            "warn", f"태그가 {len(draft.tags)}개입니다",
            f"{MAX_TAGS}개 이하로 줄이세요. 많이 단다고 노출이 늘지 않고, "
            f"주제와 먼 태그는 오히려 손해입니다"))
    elif not draft.tags:
        issues.append(Issue("warn", "태그가 없습니다", "5~8개 정도 다세요"))

    # 6) 과장 문구
    hits = banned_phrases.check(draft.full_text())
    if hits:
        issues.append(Issue(
            "block", f"과장 문구가 {len(hits)}개 있습니다",
            f"{', '.join(hits[:5])} — 고쳐야 올릴 수 있습니다"))

    # 7) 제목
    if len(draft.title) > 40:
        issues.append(Issue(
            "note", f"제목이 {len(draft.title)}자입니다",
            "검색 결과에서 잘릴 수 있습니다. 30자 안팎이 무난합니다"))

    order = {"block": 0, "warn": 1, "note": 2}
    return sorted(issues, key=lambda item: order[item.level])


def ready(issues: list[Issue]) -> bool:
    return not any(item.blocking for item in issues)
