"""크몽 정책 검사 — 외부 연락처 유도 탐지.

크몽은 플랫폼 밖에서 거래를 유도하는 문구를 금지한다. 적발되면 서비스가 내려가고
반복되면 계정이 정지된다. 상세페이지와 문의 응답 템플릿 양쪽을 검사한다.

성과를 단정하는 표현 검사는 :mod:`shared.banned_phrases` 가 맡는다.
이 모듈은 크몽에만 해당하는 규칙을 본다.
"""

from __future__ import annotations

import re

__all__ = ["check_contact_lure", "CONTACT_PATTERNS", "ContactFinding"]


class ContactFinding:
    """탐지된 문구 한 건."""

    def __init__(self, label: str, matched: str, context: str) -> None:
        self.label = label
        self.matched = matched
        self.context = context

    def __repr__(self) -> str:  # 테스트 실패 메시지를 읽기 쉽게
        return f"ContactFinding({self.label!r}, {self.matched!r})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, ContactFinding)
            and (self.label, self.matched) == (other.label, other.matched)
        )


#: (설명, 정규식) 목록. 크몽 정책상 상세페이지·문의 응답에 쓰면 안 되는 것들.
CONTACT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("전화번호", re.compile(r"01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}")),
    ("일반 전화번호", re.compile(r"0(?:2|[3-6]\d)[-.\s]?\d{3,4}[-.\s]?\d{4}")),
    ("이메일 주소", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")),
    ("카카오톡 유도", re.compile(r"카카오\s*톡|카톡|오픈\s*채팅|오픈카톡|카톡\s*아이디")),
    ("다른 메신저 유도", re.compile(r"텔레그램|라인\s*아이디|위챗|왓츠앱|디스코드")),
    ("SNS 계정 유도", re.compile(r"인스타\s*(?:디엠|DM|아이디)|네이버\s*톡톡")),
    ("직거래 유도", re.compile(r"직거래|따로\s*연락|개인적으로\s*연락|외부\s*결제|계좌\s*이체")),
    ("플랫폼 이탈 유도", re.compile(r"크몽\s*(?:밖|외부)에서|수수료\s*아끼|현금가")),
    ("외부 링크", re.compile(r"https?://(?!(?:www\.)?kmong\.com)[\w.-]+")),
)

#: 문맥을 몇 글자씩 보여 줄지.
_CONTEXT_CHARS = 20


def check_contact_lure(text: str) -> list[ContactFinding]:
    """외부 연락처·직거래 유도 문구를 찾는다.

    Args:
        text: 검사할 텍스트.

    Returns:
        찾은 것들. 없으면 빈 리스트.
    """
    if not text:
        return []

    findings: list[ContactFinding] = []
    seen: set[tuple[str, str]] = set()

    for label, pattern in CONTACT_PATTERNS:
        for match in pattern.finditer(text):
            key = (label, match.group(0))
            if key in seen:
                continue
            seen.add(key)

            start = max(0, match.start() - _CONTEXT_CHARS)
            end = min(len(text), match.end() + _CONTEXT_CHARS)
            context = " ".join(text[start:end].split())
            findings.append(ContactFinding(label, match.group(0), context))

    return findings
