"""초안 — **붙여넣기 직전까지.** 올리는 것은 사람이 한다.

네이버 검색 노출 로직(C-Rank·D.I.A.+)이 보는 것은 대체로 이렇다.

* **원본성** — 남의 글과 얼마나 다른가
* **체류시간** — 들어와서 얼마나 머무는가
* **주제 일관성** — 이 블로그가 한 분야를 꾸준히 쓰는가

세 가지 모두 양산과 반대 방향이다. 그래서 이 모듈은 한 번에 한 편만 쓰고,
사람이 고칠 자리를 일부러 남긴다. `[여기에 직접 겪은 일을 쓰세요]` 같은 자리다.
빈칸이 남아 있으면 검사기가 경고한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from naver_blog.policy import assert_disclosed, disclosure_for

__all__ = [
    "DRAFT_SYSTEM", "Draft", "Request", "build_prompt", "parse_draft",
    "PLACEHOLDER", "offline_draft",
]

#: 사람이 채워야 하는 자리. 남아 있으면 검사기가 잡는다.
PLACEHOLDER = "[직접 겪은 일을 여기에 쓰세요]"

DRAFT_SYSTEM = """당신은 네이버 블로그 글의 초안을 쓰는 사람입니다.

네이버 검색은 원본성과 체류시간, 주제 일관성을 봅니다. 그래서 다음을 지킵니다.

- 남의 글을 옮기지 않습니다. 일반론만 쓰고, 구체적인 경험은 빈칸으로 둡니다
- 빈칸은 정확히 이 문자열로 둡니다: [직접 겪은 일을 여기에 쓰세요]
- 소제목을 4~6개로 나눕니다. 한 덩어리가 길면 읽다가 나갑니다
- 첫 문단에서 이 글이 무엇을 해결하는지 말합니다
- 과장하지 않습니다. "무조건", "100%", "반드시" 같은 말을 쓰지 않습니다
- 수익이나 효과를 보장하는 말을 쓰지 않습니다
- 법·세금·의료에 관한 내용이면 "확인이 필요하다" 고 적습니다

출력 형식(이 순서 그대로, 다른 말 없이):

제목: <한 줄>
---
<본문. 소제목은 ## 로>
---
태그: <쉼표로 구분한 5~8개>
"""


@dataclass
class Request:
    """초안 요청."""

    topic: str
    keyword: str = ""
    audience: str = "일반 독자"
    tone: str = "차분하고 담백하게"
    sponsor_kind: str = "none"
    sponsor_name: str = ""
    must_include: list[str] = field(default_factory=list)

    @property
    def paid(self) -> bool:
        return self.sponsor_kind not in ("", "none")


@dataclass
class Draft:
    """초안 한 편."""

    title: str
    body: str
    tags: list[str] = field(default_factory=list)
    disclosure: str = ""

    @property
    def chars(self) -> int:
        return len(self.body)

    @property
    def headings(self) -> list[str]:
        return [line.lstrip("# ").strip()
                for line in self.body.splitlines() if line.startswith("##")]

    @property
    def placeholders(self) -> int:
        return self.body.count(PLACEHOLDER)

    def full_text(self) -> str:
        """올릴 때 쓰는 전체 글. **대가성 문구가 맨 위에 온다.**"""
        parts = []
        if self.disclosure:
            parts += [self.disclosure, ""]
        parts += [self.body.strip(), "", "태그: " + ", ".join(self.tags)]
        return "\n".join(parts)


def build_prompt(request: Request) -> str:
    lines = [f"주제: {request.topic}"]
    if request.keyword:
        lines.append(f"노리는 검색어: {request.keyword}")
    lines += [f"읽는 사람: {request.audience}", f"말투: {request.tone}"]
    if request.must_include:
        lines.append("꼭 다룰 것: " + ", ".join(request.must_include))
    if request.paid:
        lines.append(
            "이 글은 대가를 받고 쓰는 글입니다. 본문 맨 위에 대가성 문구가 "
            "따로 들어가므로, 본문에서 광고가 아닌 척하지 마세요.")
    lines.append("본문은 1,500자 이상 2,500자 이하로 씁니다.")
    return "\n".join(lines)


def parse_draft(raw: str, request: Request) -> Draft:
    """모델 응답을 초안으로 바꾼다. 형식이 어긋나도 최대한 살린다."""
    text = str(raw or "").strip()
    title, body, tags = "", text, []

    blocks = [part.strip() for part in text.split("---")]
    if len(blocks) >= 2:
        head = blocks[0]
        title = head.split("제목:", 1)[-1].strip() if "제목:" in head else head.strip()
        body = blocks[1]
        if len(blocks) >= 3 and "태그:" in blocks[2]:
            raw_tags = blocks[2].split("태그:", 1)[-1]
            tags = [tag.strip().lstrip("#") for tag in raw_tags.split(",") if tag.strip()]
    elif "제목:" in text:
        head, _, rest = text.partition("\n")
        title = head.split("제목:", 1)[-1].strip()
        body = rest.strip()

    draft = Draft(
        title=title or request.topic,
        body=body.strip(),
        tags=tags or ([request.keyword] if request.keyword else []),
        disclosure=disclosure_for(request.sponsor_kind, request.sponsor_name),
    )
    # 대가를 받은 글은 문구가 없으면 여기서 막힌다.
    assert_disclosed(draft.full_text(), request.sponsor_kind)
    return draft


def offline_draft(request: Request) -> Draft:
    """Claude 없이 뼈대만 만든다. 모의 실행과 키 없는 환경에서 쓴다."""
    keyword = request.keyword or request.topic
    body = "\n".join([
        f"{request.topic}에 대해 정리했습니다. "
        f"처음 알아보시는 분이 헷갈리기 쉬운 것 위주로 적었습니다.",
        "",
        "## 무엇부터 봐야 하나",
        f"{keyword}를 알아보실 때 가장 먼저 확인할 것을 적었습니다.",
        PLACEHOLDER,
        "",
        "## 자주 하는 실수",
        "여기에 흔한 오해 두세 가지를 적습니다.",
        PLACEHOLDER,
        "",
        "## 직접 겪어 보니",
        PLACEHOLDER,
        "",
        "## 정리",
        "확인이 필요한 부분은 담당 기관이나 전문가에게 다시 물어보시는 것이 좋습니다.",
    ])
    draft = Draft(
        title=f"{request.topic}, 처음 알아보시는 분을 위해 정리했습니다",
        body=body,
        tags=[keyword, request.topic, "정리", "후기", "초보"][:5],
        disclosure=disclosure_for(request.sponsor_kind, request.sponsor_name),
    )
    assert_disclosed(draft.full_text(), request.sponsor_kind)
    return draft
