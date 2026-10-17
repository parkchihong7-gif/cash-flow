"""산출물 쓰기와 사람 승인.

    plan.md           사람이 보는 기획서 (장면표·판정·승인란)
    plan.json         전체 결과. 다음 단계(영상 렌더링)가 읽는다
    subtitles.srt     자막 파일. 편집 프로그램에 그대로 넣는다
    description.txt   설명란 — 대가성 문구 + 본문 + 출처 + AI 표시
    shopping_list.csv 상품 태그·검색용 목록
    checklist.md      올리기 전 사람이 확인할 것

승인(`approve`)은 막음이 없고 이름이 있을 때만 된다. 렌더링은 승인된 기획서만 받는다.
"""

from __future__ import annotations

import csv
import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from shared.ai_label import add_text_label, label_text_for
from shared.banned_phrases import assert_clean

from . import disclosure
from .rules import InputReview, Issue
from .schema import VISUALS, PlanDraft

__all__ = ["OUTPUT_FILES", "write_outputs", "approve", "ApprovalRefused", "coupang_search"]

OUTPUT_FILES = ("plan.md", "plan.json", "subtitles.srt", "description.txt",
                "shopping_list.csv", "checklist.md")


class ApprovalRefused(RuntimeError):
    """승인할 수 없는 기획서."""


def coupang_search(keyword: str) -> str:
    return "https://www.coupang.com/np/search?q=" + urllib.parse.quote(keyword.strip())


def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rest = divmod(ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _srt(plan: PlanDraft) -> str:
    blocks = [f"{n}\n{_ts(s.start)} --> {_ts(s.end)}\n{s.subtitle}\n"
              for n, s in enumerate(plan.scenes, 1)]
    return "\n".join(blocks)


def _description(plan: PlanDraft, review: InputReview, ai_label_on: bool) -> str:
    data = review.data
    lines = [disclosure.description_block(), "", plan.description.strip()]
    if review.name_allowed:
        lines += ["", f"출처: {data.source_name or '기사'} {data.source_url}".strip()]
    lines += ["", "※ 소개한 상품은 착용 제품과 같은 제품이 아닐 수 있습니다. 구매 전 상품 정보를 확인하세요."]
    if plan.hashtags:
        lines += ["", " ".join(plan.hashtags)]
    text = "\n".join(lines).strip()
    if ai_label_on:
        text = add_text_label(text)
    disclosure.assert_disclosed(text)
    return assert_clean(text)


def _item_label(review: InputReview, index: int | None) -> str:
    if index is None:
        return "-"
    item = review.data.items[index]
    return f"{index + 1}. {item.name} ({review.item_mode(index)})"


def _plan_md(plan: PlanDraft, review: InputReview, issues: list[Issue], notes: list[str],
             dry_run: bool, ai_label_on: bool) -> str:
    data = review.data
    blocks = [i for i in issues if i.level == "block"]
    verdict = "⛔ 승인 불가 — 아래 '막음' 을 고친 뒤 다시 만드세요" if blocks else "검토 후 승인 가능"
    who = data.celebrity if review.name_allowed else "(이름 안 씀 — 출처 없음)"
    lines = [
        f"# 쇼츠 기획서 — {plan.title}",
        "",
        f"- 판정: **{verdict}**",
        f"- 길이: {data.duration_sec}초 · 장면 {len(plan.scenes)}개",
        f"- 연예인: {who}",
        f"- 출처: {data.source_name} {data.source_url}".rstrip() if data.has_source else "- 출처: 없음",
        f"- 후크(첫 2초): **{plan.hook.replace(chr(10), ' / ')}**",
    ]
    if dry_run:
        lines.append("- ※ 모의 실행 결과입니다. Claude 를 부르지 않았습니다.")
    lines += ["", "## 장면", "",
              "| 시간 | 자막 | 내레이션 | 화면 | 아이템 |", "|---|---|---|---|---|"]
    for s in plan.scenes:
        lines.append(f"| {s.start:g}–{s.end:g}초 | {s.subtitle.replace(chr(10), '<br>')} | "
                     f"{s.narration} | {VISUALS[s.visual]} | {_item_label(review, s.item_index)} |")
    lines += ["", "## 아이템", ""]
    for i, item in enumerate(data.items):
        price = review.shown_price(i)
        price_txt = f" · {price:,}원 ({item.price_source})" if price is not None else ""
        lines.append(f"{i + 1}. {item.name} [{item.category}] — {review.item_mode(i)}"
                     f"{' · ' + item.brand if item.brand else ''}{price_txt} · 검색어 '{item.search_keyword}'")
    if blocks or issues:
        lines += ["", "## 검사 결과", ""] + [f"- {i.line()}" for i in issues]
    if notes:
        lines += ["", "## 프로그램이 고친 것", ""] + [f"- {n}" for n in notes]
    lines += ["", "## 승인", "",
              "checklist.md 를 다 확인했으면 아래 명령으로 승인합니다. 승인해야 영상으로 만들 수 있습니다.",
              "", "```", "python cli.py approve <이 폴더> --name 승인자이름", "```"]
    text = "\n".join(lines)
    return add_text_label(text) if ai_label_on else text


#: 채널을 처음 만들 때 한 번 해 두는 설정. 유튜브 공식 메뉴 기준(이름은 바뀔 수 있다).
CHANNEL_SETUP = (
    "채널을 **브랜드 계정**으로 만들었다 (관리자 추가·소유권 이전이 됩니다)",
    "유튜브 스튜디오 → 설정 → 업로드 기본설정에서 '유료 프로모션 포함' 을 기본으로 켜 두었다",
    "유튜브 쇼핑 제휴 프로그램에 가입했다 (구독자 500명 + YPP 이후. 그 전에는 채널 프로필 링크)",
    "채널 설명에 '제휴 링크·상품 태그로 수수료를 받는다' 는 문장을 넣었다",
    "다른 사람 채널을 사지 않고 새로 만들었다 (구독자 관심사가 안 맞고 정책 위험)",
)


def _checklist(review: InputReview, issues: list[Issue]) -> str:
    data = review.data
    categories = {item.category for item in data.items}
    lines = ["# 올리기 전 확인 (사람이 직접)", ""]
    if issues:
        lines += ["## 자동 검사에서 나온 것", ""] + [f"- [ ] {i.line()}" for i in issues] + [""]
    lines += [
        "## 매번 확인",
        "",
        "- [ ] 출처 기사·SNS 를 직접 열어 아이템이 맞는지 봤다" if data.has_source
        else "- [ ] 연예인 이름을 쓰지 않았다 (출처 없음)",
        "- [ ] 연예인 얼굴 사진·방송 화면·직캠을 **한 장도** 쓰지 않았다",
        "- [ ] 상품 이미지는 쇼핑몰·브랜드가 허락한 범위에서 썼다 (파트너스·제휴 이미지 조건 확인)",
        "- [ ] '비슷한 스타일' 아이템을 같은 제품처럼 말하지 않았다",
        "- [ ] 화면의 가격이 지금 판매가와 맞다",
        "- [ ] 설명란 첫 줄에 대가성 문구가 있다 (description.txt 그대로)",
        "- [ ] 업로드 화면에서 '유료 프로모션 포함' 을 체크했다",
        "- [ ] 업로드 화면에서 '변경되거나 합성된 콘텐츠' 를 사실대로 체크했다 (AI 음성·이미지를 썼다면 예)",
        "- [ ] 내 말·내 의견을 한 줄 이상 넣었다 (양산형 판정 회피)",
        "- [ ] '추천한·애용·인생템' 같은 말은 출처로 확인된 아이템에만 썼다",
    ]
    if "건강식품" in categories:
        lines += [
            "- [ ] 건강식품: 효능(면역·다이어트·혈당·피로 회복 등)을 말하지 않았다",
            "- [ ] 건강식품: 건강기능식품이면 포장의 인증 마크와 광고 심의 여부를 확인했다",
        ]
    if "뷰티" in categories:
        lines += [
            "- [ ] 화장품: '치료·재생·아토피' 같은 의약품 표현을 쓰지 않았다",
            "- [ ] 화장품: '미백·주름 개선' 을 썼다면 기능성 화장품 인증이 있는 제품이다",
        ]
    lines += [
        "",
        "## 채널 설정 (처음 한 번)",
        "",
        *[f"- [ ] {line}" for line in CHANNEL_SETUP],
        "",
        "## 링크",
        "",
        f"- {disclosure.SHOPPING_NOTE}",
    ]
    return "\n".join(lines)


def write_outputs(out_dir: Path, review: InputReview, plan: PlanDraft, issues: list[Issue],
                  notes: list[str], *, dry_run: bool, ai_label_on: bool, model: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = review.data

    (out_dir / "plan.md").write_text(_plan_md(plan, review, issues, notes, dry_run, ai_label_on),
                                     encoding="utf-8")
    (out_dir / "subtitles.srt").write_text(_srt(plan), encoding="utf-8")
    (out_dir / "description.txt").write_text(_description(plan, review, ai_label_on), encoding="utf-8")
    (out_dir / "checklist.md").write_text(_checklist(review, issues), encoding="utf-8")

    with (out_dir / "shopping_list.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["번호", "아이템", "분류", "소개 방식", "브랜드", "가격", "가격 출처", "검색어", "쿠팡 검색 주소"])
        for i, item in enumerate(data.items):
            price = review.shown_price(i)
            writer.writerow([i + 1, item.name, item.category, review.item_mode(i), item.brand,
                             price if price is not None else "", item.price_source if price is not None else "",
                             item.search_keyword, coupang_search(item.search_keyword)])

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "dry_run": dry_run,
        "ai_generated": True,
        "ai_label": label_text_for("ko") if ai_label_on else "",
        "input": data.model_dump(),
        "name_allowed": review.name_allowed,
        "item_modes": [review.item_mode(i) for i in range(len(data.items))],
        "plan": plan.model_dump(),
        "issues": [i.__dict__ for i in issues],
        "notes": notes,
        "approved": None,
    }
    (out_dir / "plan.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_dir


def approve(out_dir: Path, name: str) -> dict:
    """사람 승인. 막음이 남아 있거나 이름이 없으면 거절한다."""
    path = Path(out_dir) / "plan.json"
    if not path.is_file():
        raise ApprovalRefused(f"기획서가 없습니다: {path}")
    if not name.strip():
        raise ApprovalRefused("승인자 이름을 적어 주세요. 누가 확인했는지 남겨야 합니다.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    blocks = [i for i in payload.get("issues", []) if i.get("level") == "block"]
    if blocks:
        raise ApprovalRefused("막음이 남아 있어 승인할 수 없습니다:\n"
                              + "\n".join(f"  - [{b['where']}] {b['message']}" for b in blocks))
    if payload.get("dry_run"):
        raise ApprovalRefused("모의 실행 결과는 승인할 수 없습니다. 실제 실행으로 다시 만드세요.")
    payload["approved"] = {"by": name.strip(), "at": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload["approved"]
