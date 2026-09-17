"""플랫폼별 산출물 — 크몽 / 인스타 / 내 사이트.

같은 퍼널이라도 **어디에 올리느냐에 따라 형태가 다르다.**

    own         랜딩 페이지(html) — 내 도메인에 올린다
    kmong       상세페이지(md) — 크몽에는 html 을 못 올린다. 글과 이미지뿐이다
    instagram   릴스 캡션 5개 + 프로필 링크 문구 + 댓글 키워드 유도문

인스타에서 특히 조심할 것
    **콜드 DM 은 만들지 않는다.** 먼저 말을 건 적 없는 사람에게 보내는 DM 은
    Meta 정책 위반이고 계정이 정지된다(CLAUDE.md §3-4).

    허용되는 것은 **사용자가 먼저 행동한 대화에 24시간 안에 답하는 것**뿐이다.
    그래서 `dm_flow.yaml` 은 '댓글을 남긴 사람에게' 만 응답하는 시나리오로 만든다.
    24시간이 지나면 보낼 수 없다는 것도 파일에 적어 둔다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "PLATFORMS",
    "DEFAULT_KEYWORD",
    "DM_TOOLS",
    "write_kmong_detail",
    "write_instagram_pack",
    "write_dm_flow",
    "platform_files",
]

#: 고를 수 있는 플랫폼.
PLATFORMS = ("own", "kmong", "instagram")

#: 댓글로 받을 기본 키워드. 짧고 치기 쉬운 말이어야 한다.
DEFAULT_KEYWORD = "가이드"

#: 이 시나리오를 그대로 넣을 수 있는 공식 도구들.
DM_TOOLS = ("ManyChat", "포크레터", "키티챗", "Mirra")

#: 24시간 룰. 이 문장은 산출물 어디서도 빠지지 않는다.
RULE_24H = (
    "Meta 정책상 **사용자가 먼저 보낸 메시지·댓글로부터 24시간 안에만** "
    "자동 응답을 보낼 수 있습니다. 24시간이 지나면 이 흐름은 멈춰야 하며, "
    "먼저 말을 건 적 없는 사람에게 보내는 DM(콜드 DM)은 정책 위반입니다."
)

#: 플랫폼마다 나오는 파일. 테스트와 문서가 이 표를 같이 본다.
platform_files: dict[str, tuple[str, ...]] = {
    "own": ("landing.html",),
    "kmong": ("detail_page.md",),
    "instagram": ("reels_captions.md", "dm_flow.yaml"),
}


def _won(value: int) -> str:
    return f"{int(value):,}원"


# ------------------------------------------------------------------- 크몽
def write_kmong_detail(result, out_dir: Path) -> Path:
    """크몽 상세페이지(detail_page.md).

    크몽에는 HTML 을 못 올린다. 글과 이미지뿐이라 랜딩 대신 이걸 만든다.

    구성 순서는 5번 상품(크몽 상세페이지 카피 생성기)의 `write_detail_page` 와
    같게 맞췄다. 두 상품의 결과를 나란히 놓고 고칠 일이 많기 때문이다.
    """
    data = result.data
    landing = result.sections["landing"].data
    faq = result.sections["faq"].data
    headlines = result.sections["headlines"].data.get("headlines", [])
    head = headlines[0].get("text", data.core_promise) if headlines else data.core_promise

    lines: list[str] = [f"# {head}", ""]
    lines += [f"> {data.product_name} · {data.target}", ""]
    if landing.get("hero_sub"):
        lines += [landing["hero_sub"], ""]

    # ── 이런 분께 추천합니다 (통증을 뒤집어 쓴다)
    lines += ["## 이런 분께 추천합니다", ""]
    for pain in data.pain_points:
        lines.append(f"- {pain}")
    not_for = []
    for item in faq.get("items", []):
        if item.get("objection") == "fit":
            not_for.append(item.get("a", ""))
    if not_for:
        lines += ["", "**이런 경우에는 맞지 않습니다**", ""]
        lines += [f"- {text}" for text in not_for[:2]]
    lines.append("")

    # ── 제공 내용
    lines += ["## 제공 내용", "", "| 항목 | 내용 |", "|---|---|"]
    pricing = landing.get("pricing", {})
    for item in pricing.get("includes", []):
        lines.append(f"| {item} | |")
    lines.append("")

    # ── 진행 순서 (커리큘럼을 순서로 읽는다)
    lines += ["## 진행 순서", ""]
    curriculum = landing.get("curriculum", {}).get("items", [])
    for index, item in enumerate(curriculum, start=1):
        lines.append(f"**{index}. {item.get('title', '')}** — {item.get('summary', '')}")
        lines.append("")

    # ── 차별점
    promise = landing.get("promise", {})
    if promise:
        lines += ["## 이 서비스의 차별점", "", f"### {promise.get('title', '')}", "",
                  promise.get("body", ""), ""]
        for bullet in promise.get("bullets", []):
            lines.append(f"- {bullet}")
        lines.append("")

    # ── 포트폴리오
    lines += ["## 포트폴리오", ""]
    if data.proof:
        lines += [f"- {item}" for item in data.proof]
        lines += ["", "> 위 내용은 판매자가 제공한 자료입니다. "
                      "같은 결과를 보장하지 않으며 조건에 따라 다를 수 있습니다."]
    else:
        lines += [
            "사례 준비 중입니다.",
            "",
            "> **[판매자가 채울 곳]** 작업물 이미지 3~5장을 올리세요. "
            "실적이 없어도 샘플을 만들어 올리는 편이 낫습니다. "
            "**없는 실적을 지어내면 서비스가 내려갑니다.**",
        ]
    lines.append("")

    # ── 가격
    lines += ["## 가격", "", f"**{_won(data.price)}**", ""]
    if pricing.get("note"):
        lines += [pricing["note"], ""]

    # ── FAQ
    lines += ["## 자주 묻는 질문", ""]
    for item in faq.get("items", []):
        lines += [f"**Q. {item.get('q', '')}**", "", item.get("a", ""), ""]

    # ── 등록 전 점검
    lines += [
        "---",
        "",
        "## 등록 전 점검 (판매자용)",
        "",
        "- [ ] 크몽은 **HTML 을 못 올립니다.** 이 글을 상세페이지 편집기에 옮겨 적으세요",
        "- [ ] 이미지 3~5장을 따로 준비하세요. 글만 있으면 클릭이 안 됩니다",
        "- [ ] 수정 횟수·추가 비용·환불 조건을 크몽 서식에 맞게 적으세요 (전자상거래법)",
        "- [ ] 실적 자리를 **비워 두었는지** 확인하세요. 없는 수치를 적지 마세요",
        "- [ ] 패키지 3단(BASIC/STANDARD/PREMIUM)이 필요하면 "
        "5번 상품(크몽 상세페이지 카피 생성기)을 쓰세요. 이 파일은 단일 가격 기준입니다",
        "",
        "이 서비스는 성과를 약속하지 않습니다. 상세페이지에 성과를 단정하는 표현을 "
        "넣지 마세요.",
    ]

    path = out_dir / "detail_page.md"
    body = "\n".join(lines)
    if result.ai_label:
        from shared.ai_label import add_text_label

        body = add_text_label(body)
    path.write_text(body + "\n", encoding="utf-8")
    return path


# ----------------------------------------------------------------- 인스타
def write_instagram_pack(result, out_dir: Path, keyword: str = DEFAULT_KEYWORD) -> Path:
    """릴스 캡션 5개 + 프로필 링크 문구 + 댓글 키워드 유도문."""
    data = result.data
    section = result.sections.get("instagram")
    payload: dict[str, Any] = section.data if section else {}

    captions = payload.get("captions", [])
    bio = payload.get("bio_link", {})
    keyword = (payload.get("keyword") or keyword).strip() or DEFAULT_KEYWORD

    lines: list[str] = [
        "# 인스타 릴스 묶음",
        "",
        f"> {data.product_name} · {data.target}",
        "",
        "릴스 캡션 5개와 프로필 링크 문구, 댓글 키워드 유도문입니다.",
        "**그대로 올리지 마시고 본인 말투로 고치세요.**",
        "",
        "---",
        "",
        "## 릴스 캡션 5개",
        "",
    ]

    for index, item in enumerate(captions, start=1):
        lines += [
            f"### {index}. {item.get('angle', '')}",
            "",
            "**첫 줄 (더 보기 앞에서 끝나는 자리)**",
            "",
            f"> {item.get('hook', '')}",
            "",
            "**캡션**",
            "",
            item.get("caption", ""),
            "",
            f"**댓글 유도** — {item.get('cta', '')}",
            "",
        ]
        tags = item.get("hashtags", [])
        if tags:
            lines += [" ".join(tags), ""]
        lines.append("")

    lines += [
        "---",
        "",
        "## 프로필 링크 문구",
        "",
        f"**소개글**: {bio.get('bio', '')}",
        "",
        f"**링크 문구**: {bio.get('link_text', '')}",
        "",
        f"**링크 주소**: {data.cta_url}",
        "",
        "링크는 프로필에 하나만 걸 수 있습니다. 여러 개가 필요하면 링크 모음 서비스를 "
        "쓰시되, **한 번 더 누르게 되는 만큼 전환이 떨어집니다.**",
        "",
        "---",
        "",
        "## 댓글 키워드 유도문",
        "",
        f"이 퍼널의 키워드는 **`{keyword}`** 입니다.",
        "",
        f"> \"'{keyword}' 댓글 남겨 주시면 DM으로 보내드려요\"",
        "",
        "이렇게 쓰는 이유",
        "",
        "- 댓글을 받으면 **24시간 동안 DM 을 보낼 수 있는 길이 열립니다**",
        "- 댓글 수 자체가 도달에 도움이 됩니다",
        "- 먼저 말을 건 사람에게만 보내므로 **정책에 어긋나지 않습니다**",
        "",
        "### 하지 마셔야 할 것",
        "",
        "- 먼저 말을 건 적 없는 사람에게 DM 보내기 (**콜드 DM — 계정 정지 사유**)",
        "- 자동 팔로우·자동 좋아요",
        "- \"팔로우하고 댓글\" 같은 참여 강요 (도달이 오히려 떨어집니다)",
        "",
        "### 자동 응답을 붙이려면",
        "",
        f"같은 폴더의 `dm_flow.yaml` 을 {' · '.join(DM_TOOLS)} 같은 **공식 도구**에 "
        "넣으세요. 비공식 매크로는 쓰지 마세요(CLAUDE.md §3-7).",
        "",
        f"> {RULE_24H}",
    ]

    path = out_dir / "reels_captions.md"
    body = "\n".join(lines)
    if result.ai_label:
        from shared.ai_label import add_text_label

        body = add_text_label(body)
    path.write_text(body + "\n", encoding="utf-8")
    return path


# ----------------------------------------------------------------- DM 흐름
def write_dm_flow(result, out_dir: Path, keyword: str = DEFAULT_KEYWORD) -> Path:
    """댓글 키워드 → DM 자동응답 시나리오 (`dm_flow.yaml`).

    ManyChat·포크레터 같은 **공식 도구에 그대로 옮겨 적을 수 있는** 모양으로 쓴다.
    도구마다 화면은 다르지만 필요한 것은 같다 — 무엇으로 시작하고(trigger),
    무엇을 보내고(steps), 사람에게 언제 넘기는가(handoff).

    콜드 DM 시나리오는 만들지 않는다. 시작점이 **댓글** 하나뿐인 이유다.
    """
    data = result.data
    section = result.sections.get("instagram")
    payload: dict[str, Any] = section.data if section else {}
    keyword = (payload.get("keyword") or keyword).strip() or DEFAULT_KEYWORD
    dm = payload.get("dm", {})

    greeting = dm.get("greeting") or (
        f"안녕하세요! '{keyword}' 댓글 남겨 주셔서 보내드려요."
    )
    deliver = dm.get("deliver") or (
        f"약속드린 <{data.lead_magnet_title}> 입니다.\n{data.cta_url}"
    )
    followup = dm.get("followup") or (
        "보시다가 막히는 부분 있으면 이 대화창에 그대로 물어봐 주세요. "
        "제가 직접 읽고 답 드립니다."
    )

    flow = {
        "메타": {
            "이름": f"{data.product_name} — 댓글 키워드 자동응답",
            "만든날": datetime.now().strftime("%Y-%m-%d"),
            "넣을_도구": list(DM_TOOLS),
            "쓰는_법": [
                "1. 도구에서 '댓글 자동응답(Comment Automation)' 새로 만들기",
                "2. 아래 trigger 의 keyword 를 그대로 넣기",
                "3. steps 를 순서대로 메시지 블록으로 만들기",
                "4. handoff 조건에 걸리면 사람이 받도록 담당자 알림을 켜기",
                "5. **먼저 테스트 계정으로 한 번 돌려 보고** 켜기",
            ],
        },
        "정책": {
            "24시간_규칙": RULE_24H,
            "콜드_DM": "이 시나리오에는 없습니다. 만들지 마세요. 계정 정지 사유입니다.",
            "자동_팔로우_좋아요": "쓰지 마세요. Meta 정책 위반입니다.",
            "AI_표시": "자동 응답이라는 것을 첫 메시지에 밝힙니다(인공지능기본법 제31조).",
            "사람_검수": "문의가 오면 사람이 읽고 답합니다. 끝까지 자동으로 두지 마세요.",
        },
        "trigger": {
            "type": "instagram_comment",
            "keyword": keyword,
            "match": "contains",
            "case_sensitive": False,
            "note": "댓글을 남긴 사람에게만 DM 이 갑니다. 먼저 보내지 않습니다.",
        },
        "steps": [
            {
                "id": "greet",
                "type": "message",
                "text": f"{greeting}\n\n(이 메시지는 자동 응답입니다)",
                "delay_seconds": 0,
            },
            {
                "id": "deliver",
                "type": "message",
                "text": deliver,
                "delay_seconds": 3,
                "buttons": [
                    {"label": "지금 받기", "type": "url", "url": data.cta_url},
                ],
            },
            {
                "id": "followup",
                "type": "message",
                "text": followup,
                "delay_seconds": 60,
                "note": "24시간이 지나면 보낼 수 없습니다. 도구에서 만료 처리를 켜 두세요.",
            },
        ],
        "handoff": {
            "when": [
                "가격·환불·계약을 묻는 말이 들어올 때",
                "같은 질문을 두 번 이상 다시 물을 때",
                "불만을 말할 때",
            ],
            "action": "담당자에게 알림을 보내고 자동 응답을 멈춥니다",
            "message": "확인하고 제가 직접 답 드릴게요. 잠시만 기다려 주세요.",
        },
        "opt_out": {
            "keyword": "그만",
            "message": "알겠습니다. 더 보내지 않을게요.",
            "note": "이 항목을 빼지 마세요. 그만 받겠다는 사람에게 계속 보내면 신고됩니다.",
        },
        "점검": [
            "댓글 말고 다른 곳에서 시작되는 흐름이 없는지",
            "24시간 만료 처리가 켜져 있는지",
            "첫 메시지에 자동 응답이라고 밝혔는지",
            "'그만' 이 동작하는지",
            "사람에게 넘기는 조건이 살아 있는지",
        ],
    }

    path = out_dir / "dm_flow.yaml"
    header = (
        "# 댓글 키워드 → DM 자동응답 시나리오\n"
        "#\n"
        f"# {RULE_24H}\n"
        "#\n"
        "# 콜드 DM(먼저 말을 건 적 없는 사람에게 보내는 DM)은 이 파일에 없습니다.\n"
        "# 만들지 마세요. 계정이 정지됩니다.\n"
        "#\n"
        f"# 넣을 도구: {' · '.join(DM_TOOLS)} — 공식 도구만 쓰세요.\n\n"
    )
    path.write_text(header + yaml.safe_dump(flow, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return path


def summary_json(result, platform: str) -> str:
    """플랫폼별로 무엇이 나왔는지 한 줄 요약. build_report 가 쓴다."""
    return json.dumps({
        "platform": platform,
        "files": list(platform_files.get(platform, ())),
    }, ensure_ascii=False)
