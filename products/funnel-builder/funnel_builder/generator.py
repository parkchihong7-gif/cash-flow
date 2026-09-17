"""퍼널 생성기 — 섹션별 LLM 호출, 금지 문구 검사, 산출물 5종 쓰기.

호출 순서는 헤드라인 → 랜딩 본문 → FAQ → 리드매그넷 목차 → 이메일이고,
앞 단계 결과를 뒤 단계 프롬프트의 컨텍스트로 넘긴다. 뒤로 갈수록 앞에서 정한
톤·약속·가격을 그대로 이어받게 하기 위해서다.

모든 섹션은 생성 직후 :mod:`shared.banned_phrases` 로 검사하고, 걸리면 해당 섹션만
최대 2회까지 다시 만든다. 그래도 남으면 build_report.md 에 경고로 남긴다.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from jinja2 import Environment, FileSystemLoader, select_autoescape

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from funnel_builder.schema import FunnelInput  # noqa: E402
from shared import banned_phrases  # noqa: E402
from shared.ai_label import add_text_label, label_text_for  # noqa: E402
from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import ask as default_ask  # noqa: E402

__all__ = [
    "FunnelGenerator",
    "SectionResult",
    "FunnelResult",
    "EMAIL_DAYS",
    "write_outputs",
]

#: 상품 폴더 (이 패키지의 부모).
BASE_DIR = Path(__file__).resolve().parents[1]
HOOKS_PATH = BASE_DIR / "prompts" / "hooks.md"
TEMPLATES_DIR = BASE_DIR / "templates"

#: 이메일 발송일 (D+n). 5통 고정.
EMAIL_DAYS = (0, 1, 3, 5, 7)

#: 금지 문구가 남았을 때 섹션당 최대 재생성 횟수.
MAX_REGENERATIONS = 2

_EMAIL_ROLES = (
    "① 리드매그넷 전달 — 약속한 자료를 바로 주고, 어떻게 쓰는지 한 줄로 안내한다.",
    "② 문제 심화 — 지금 방식이 왜 계속 같은 결과를 내는지 짚는다. 상품 얘기는 하지 않는다.",
    "③ 해결 원리 + 사례 — 무엇을 바꾸면 달라지는지 원리를 설명하고 사례를 붙인다.",
    "④ 상품 소개 + 가격 — 구성과 가격을 정확히 말하고, 맞지 않는 사람도 함께 밝힌다.",
    "⑤ 마감 / 손실회피 — 지금 결정하지 않으면 무엇이 그대로인지 담담하게 쓴다.",
)


@dataclass
class SectionResult:
    """섹션 하나의 생성 결과와 검사 이력."""

    name: str
    data: dict[str, Any]
    attempts: int = 1
    remaining_banned: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.remaining_banned


@dataclass
class FunnelResult:
    """퍼널 한 건의 전체 생성 결과."""

    data: FunnelInput
    sections: dict[str, SectionResult]
    model: str
    ai_label: bool
    generated_at: datetime
    #: 어디에 올릴 것인가. own | kmong | instagram (`platforms.PLATFORMS`)
    platform: str = "own"

    @property
    def warnings(self) -> list[SectionResult]:
        return [s for s in self.sections.values() if not s.clean]


def _collect_strings(value: Any) -> list[str]:
    """중첩된 JSON 에서 문자열만 모두 긁어낸다 (금지 문구 검사용)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _collect_strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _collect_strings(item)]
    return []


class FunnelGenerator:
    """입력 하나로 퍼널 산출물 5종을 만든다.

    Args:
        data: 검증된 입력.
        model: 사용할 Claude 모델 ID.
        ask_fn: LLM 호출 함수. 테스트에서 가짜 함수를 주입하기 위해 분리했다.
        ai_label: AI 생성물 표시 여부. CLAUDE.md §7 에 따라 기본 on.
    """

    def __init__(
        self,
        data: FunnelInput,
        model: str = DEFAULT_MODEL,
        ask_fn: Callable[..., Any] = default_ask,
        ai_label: bool = True,
        platform: str = "own",
    ) -> None:
        self.data = data
        self.model = model
        self.ask_fn = ask_fn
        self.ai_label = ai_label
        self.platform = platform
        self.hooks = HOOKS_PATH.read_text(encoding="utf-8")
        self.sections: dict[str, SectionResult] = {}

    # ------------------------------------------------------------- 프롬프트
    def _system(self) -> str:
        return (
            "당신은 강의·전자책 판매 페이지를 쓰는 한국어 카피라이터다.\n"
            "아래 후킹 규칙을 모든 문장에 적용한다. 규칙의 금지 사항은 예외 없이 지킨다.\n\n"
            f"{self.hooks}"
        )

    def _brief(self) -> str:
        """모든 섹션 프롬프트 앞에 붙는 상품 정보."""
        proof = (
            "\n".join(f"  - {p}" for p in self.data.proof)
            if self.data.proof
            else "  (없음 — 실적·후기를 지어내지 말 것)"
        )
        pains = "\n".join(f"  - {p}" for p in self.data.pain_points)
        return (
            f"[상품] {self.data.product_name}\n"
            f"[타깃] {self.data.target}\n"
            f"[가격] {self.data.price_text}\n"
            f"[핵심 약속] {self.data.core_promise}\n"
            f"[리드매그넷] {self.data.lead_magnet_title}\n"
            f"[고객의 통증]\n{pains}\n"
            f"[증거]\n{proof}\n"
        )

    # --------------------------------------------------------- 생성 + 검사
    def _generate(self, name: str, instruction: str) -> SectionResult:
        """한 섹션을 만들고, 금지 문구가 나오면 최대 2회까지 다시 만든다."""
        system = self._system()
        base_user = f"{self._brief()}\n{instruction}"
        user = base_user
        data: dict[str, Any] = {}
        found: list[str] = []

        for attempt in range(1, MAX_REGENERATIONS + 2):
            data = self.ask_fn(system, user, model=self.model, json_mode=True)
            found = banned_phrases.check("\n".join(_collect_strings(data)))
            if not found:
                return SectionResult(name=name, data=data, attempts=attempt)
            user = (
                f"{base_user}\n\n"
                f"[재작성 요청] 직전 시도에 금지 문구가 들어갔습니다: {', '.join(found)}\n"
                "해당 표현을 완전히 빼고, 성과를 단정하지 말고 조건부로 다시 쓰세요."
            )

        return SectionResult(
            name=name, data=data, attempts=MAX_REGENERATIONS + 1, remaining_banned=found
        )

    # ------------------------------------------------------------ 섹션 정의
    def _headlines(self) -> SectionResult:
        return self._generate(
            "headlines",
            "헤드라인 10개와 CTA 버튼 문구 5개를 만드세요.\n"
            "각 헤드라인은 후킹 이유 2개 이상을 결합하고, 사용한 이유를 hooks 배열에 적습니다.\n"
            "10개가 서로 다른 조합이 되게 하세요.\n"
            'JSON 형식: {"headlines": [{"text": "...", "hooks": ["시간", "지위"]}], '
            '"ctas": ["...", "..."]}',
        )

    def _landing(self, headline: str) -> SectionResult:
        return self._generate(
            "landing",
            f"확정된 메인 헤드라인: {headline}\n\n"
            "이 헤드라인에 이어지는 랜딩 페이지 본문을 만드세요. 섹션 순서는 고정입니다.\n"
            "- hero_sub: 헤드라인 아래 한두 문장. 누구를 위한 것인지 분명히.\n"
            "- problem: 고객의 통증을 그대로 되비추는 공감 섹션. items 는 입력 통증 개수만큼.\n"
            "- promise: 무엇이 어떻게 달라지는지. bullets 3~4개.\n"
            "- curriculum: 목차 6~8개. 각 항목에 한 줄 설명.\n"
            "- pricing: 구성 항목 4~6개와 가격 안내 문구.\n"
            "- final_cta: 마지막 행동 유도. 짧게.\n"
            'JSON 형식: {"hero_sub": "...", '
            '"problem": {"title": "...", "lead": "...", "items": [{"title": "...", "body": "..."}]}, '
            '"promise": {"title": "...", "body": "...", "bullets": ["..."]}, '
            '"curriculum": {"title": "...", "items": [{"title": "...", "summary": "..."}]}, '
            '"pricing": {"title": "...", "includes": ["..."], "note": "..."}, '
            '"final_cta": {"title": "...", "body": "...", "button": "..."}}',
        )

    def _faq(self, landing: dict[str, Any]) -> SectionResult:
        return self._generate(
            "faq",
            f"랜딩 본문 요약: {json.dumps(landing, ensure_ascii=False)[:1200]}\n\n"
            "FAQ 5개를 만드세요. 최소 3개는 3대 반론(비싸지 않을까 / 나한테 맞을까 / 믿어도 될까)에\n"
            "정면으로 답합니다. '나한테 맞을까' 항목에는 맞지 않는 사람도 함께 밝히세요.\n"
            "objection 필드에는 price, fit, trust, other 중 하나를 씁니다.\n"
            'JSON 형식: {"items": [{"q": "...", "a": "...", "objection": "price"}]}',
        )

    def _lead_magnet(self, landing: dict[str, Any]) -> SectionResult:
        return self._generate(
            "lead_magnet",
            f"리드매그넷 제목: {self.data.lead_magnet_title}\n"
            f"본상품 목차 참고: {json.dumps(landing.get('curriculum', {}), ensure_ascii=False)}\n\n"
            "무료 리드매그넷의 목차를 7~10개 항목으로 만드세요.\n"
            "본상품을 그대로 요약하지 말고, 혼자서도 바로 해볼 수 있는 범위로 구성합니다.\n"
            "각 항목에 두 줄 분량 요약을 붙입니다.\n"
            'JSON 형식: {"items": [{"title": "...", "summary": "..."}]}',
        )

    def _emails(self, landing: dict[str, Any], faq: dict[str, Any]) -> SectionResult:
        roles = "\n".join(_EMAIL_ROLES)
        return self._generate(
            "emails",
            f"랜딩 본문 요약: {json.dumps(landing, ensure_ascii=False)[:800]}\n"
            f"FAQ 요약: {json.dumps(faq, ensure_ascii=False)[:600]}\n"
            f"발신자 이름: {self.data.sender_name}\n\n"
            f"이메일 5통을 순서대로 만드세요. 각 통의 역할:\n{roles}\n\n"
            f"send_day 는 순서대로 {list(EMAIL_DAYS)} 입니다.\n"
            "본문(body)은 통당 300~500자. 인사와 서명을 포함한 완성된 메일로 씁니다.\n"
            "제목(subject)은 후킹 이유 2개 이상을 결합합니다.\n"
            'JSON 형식: {"emails": [{"subject": "...", "send_day": 0, "body": "..."}]}',
        )

    def _instagram(self, landing: dict[str, Any]) -> SectionResult:
        """릴스 캡션 5개와 DM 문구. `--platform instagram` 일 때만 부른다."""
        return self._generate(
            "instagram",
            f"랜딩 본문 요약: {json.dumps(landing, ensure_ascii=False)[:800]}\n\n"
            "인스타 릴스용 캡션 5개와 DM 문구를 만드세요.\n\n"
            "캡션 규칙\n"
            "- angle: 다섯 개가 서로 다른 각도여야 합니다 (실패담 / 오해 바로잡기 /\n"
            "  과정 공개 / 비교 / 질문 던지기 같은 식으로)\n"
            "- hook: **'더 보기' 앞에서 끝나는 첫 줄.** 여기서 멈추게 못 하면 나머지는 안 읽힙니다\n"
            "- caption: 3~5줄. 광고 문투를 쓰지 말고 직접 겪은 것처럼 씁니다\n"
            "- cta: 댓글 키워드를 남기라는 한 줄. 예: \"'가이드' 댓글 남겨 주시면 DM으로 보내드려요\"\n"
            "- hashtags: 8개 이내. 업종·상황 위주로\n\n"
            "절대 쓰지 말 것\n"
            "- '팔로우 부탁', '맞팔', '좋아요 눌러주세요' — 정책상 위험하고 도달에도 나쁩니다\n"
            "- 성과를 단정하는 표현\n\n"
            "keyword: 댓글로 받을 짧은 한국어 낱말 하나 (2~4글자, 치기 쉬운 말)\n"
            "dm: 댓글을 남긴 사람에게 보낼 문구 3개\n"
            "  greeting(첫 인사), deliver(자료 전달), followup(뒤이어 묻는 말)\n"
            "  **먼저 말을 건 적 없는 사람에게 보내는 문구는 만들지 마세요.**\n"
            'JSON 형식: {"captions": [{"angle": "...", "hook": "...", "caption": "...", '
            '"cta": "...", "hashtags": ["#..."]}], "keyword": "가이드", '
            '"bio_link": {"bio": "...", "link_text": "..."}, '
            '"dm": {"greeting": "...", "deliver": "...", "followup": "..."}}',
        )

    # ------------------------------------------------------------------ 실행
    def build(self) -> FunnelResult:
        """섹션을 순서대로 생성한다. 앞 결과가 뒤 프롬프트의 컨텍스트가 된다."""
        headlines = self._headlines()
        self.sections["headlines"] = headlines

        items = headlines.data.get("headlines") or [{"text": self.data.core_promise}]
        main_headline = items[0].get("text", self.data.core_promise)

        landing = self._landing(main_headline)
        self.sections["landing"] = landing

        faq = self._faq(landing.data)
        self.sections["faq"] = faq

        lead_magnet = self._lead_magnet(landing.data)
        self.sections["lead_magnet"] = lead_magnet

        emails = self._emails(landing.data, faq.data)
        self.sections["emails"] = emails

        if self.platform == "instagram":
            # 인스타로 올릴 때만 부른다. 다른 플랫폼에서는 호출 한 번을 아낀다.
            self.sections["instagram"] = self._instagram(landing.data)

        return FunnelResult(
            data=self.data,
            sections=self.sections,
            model=self.model,
            ai_label=self.ai_label,
            generated_at=datetime.now().astimezone(),
            platform=self.platform,
        )


# ==================================================================== 산출물 쓰기
def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def write_landing(result: FunnelResult, out_dir: Path) -> Path:
    """landing.html — CSS 인라인 단일 파일."""
    landing = result.sections["landing"].data
    headlines = result.sections["headlines"].data.get("headlines") or []
    ctas = result.sections["headlines"].data.get("ctas") or []

    html = _jinja_env().get_template("landing.html.j2").render(
        d=result.data,
        landing=landing,
        faq=result.sections["faq"].data.get("items", []),
        headline=headlines[0]["text"] if headlines else result.data.core_promise,
        cta_text=ctas[0] if ctas else "지금 신청하기",
        ai_label=result.ai_label,
        ai_label_text=label_text_for("ko"),
    )
    path = out_dir / "landing.html"
    path.write_text(html, encoding="utf-8")
    return path


def write_emails(result: FunnelResult, out_dir: Path) -> list[Path]:
    """emails/01~05.md — YAML 프론트매터 + 본문."""
    email_dir = out_dir / "emails"
    email_dir.mkdir(parents=True, exist_ok=True)

    emails = result.sections["emails"].data.get("emails", [])
    written: list[Path] = []
    for index, day in enumerate(EMAIL_DAYS):
        email = emails[index] if index < len(emails) else {}
        subject = str(email.get("subject", f"{result.data.product_name} 안내 {index + 1}"))
        body = str(email.get("body", "")).strip()
        if result.ai_label:
            body = add_text_label(body)

        # 제목에 따옴표가 들어가도 YAML 이 깨지지 않게 이스케이프한다.
        safe_subject = subject.replace('"', '\\"')
        path = email_dir / f"{index + 1:02d}.md"
        path.write_text(
            f'---\nsubject: "{safe_subject}"\nsend_day: {day}\n---\n\n{body}\n',
            encoding="utf-8",
        )
        written.append(path)
    return written


def write_lead_magnet_outline(result: FunnelResult, out_dir: Path) -> Path:
    """lead_magnet_outline.md — 목차 7~10항목 + 각 2줄 요약."""
    items = result.sections["lead_magnet"].data.get("items", [])
    lines = [
        f"# {result.data.lead_magnet_title}",
        "",
        f"> 무료 리드매그넷 목차. 대상: {result.data.target}",
        "",
    ]
    for index, item in enumerate(items, start=1):
        lines.append(f"## {index}. {item.get('title', '')}")
        lines.append("")
        lines.append(str(item.get("summary", "")).strip())
        lines.append("")

    text = "\n".join(lines).rstrip() + "\n"
    if result.ai_label:
        text = add_text_label(text) + "\n"

    path = out_dir / "lead_magnet_outline.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_copy_variants(result: FunnelResult, out_dir: Path) -> Path:
    """copy_variants.json — A/B 테스트용 헤드라인 10개, CTA 5개."""
    headlines = result.sections["headlines"].data
    payload = {
        "product_name": result.data.product_name,
        "generated_at": result.generated_at.isoformat(),
        "headlines": headlines.get("headlines", []),
        "ctas": headlines.get("ctas", []),
    }
    path = out_dir / "copy_variants.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def write_build_report(result: FunnelResult, out_dir: Path) -> Path:
    """build_report.md — 금지 문구 검사 결과, 사용된 후킹 규칙, 생성 시각."""
    lines = [
        f"# 빌드 리포트 — {result.data.product_name}",
        "",
        f"- 생성 시각: {result.generated_at.strftime('%Y-%m-%d %H:%M:%S %z')}",
        f"- 모델: {result.model}",
        f"- AI 생성물 표시: {'on' if result.ai_label else 'off'}",
        f"- 플랫폼: {result.platform}",
        f"- 가격: {result.data.price_text}",
        "",
        "## 금지 문구 검사",
        "",
        f"검사 대상: {len(banned_phrases.BANNED)}개 금지 문구 "
        f"(`shared/banned_phrases.py`). 섹션당 최대 {MAX_REGENERATIONS}회까지 재생성합니다.",
        "",
        "| 섹션 | 생성 시도 | 결과 |",
        "|---|---|---|",
    ]
    for name, section in result.sections.items():
        status = "통과" if section.clean else f"⚠ 남음: {', '.join(section.remaining_banned)}"
        lines.append(f"| {name} | {section.attempts}회 | {status} |")

    warnings = result.warnings
    lines.append("")
    if warnings:
        lines.append(
            f"> **경고 — 발행 전 사람이 고쳐야 합니다.** {len(warnings)}개 섹션에 금지 문구가 "
            "남았습니다. 재생성 한도를 넘겼습니다. 해당 산출물을 직접 수정하세요."
        )
        lines.append("")
        for section in warnings:
            lines.append(f"- `{section.name}`: {', '.join(section.remaining_banned)}")
    else:
        lines.append("> 모든 섹션이 금지 문구 검사를 통과했습니다.")

    lines += [
        "",
        "## 사용된 후킹 규칙",
        "",
        "규칙 원문: `prompts/hooks.md`. 헤드라인은 8가지 이유 중 2개 이상을 결합합니다.",
        "",
        "| # | 헤드라인 | 사용한 이유 |",
        "|---|---|---|",
    ]
    for index, item in enumerate(result.sections["headlines"].data.get("headlines", []), 1):
        hooks = ", ".join(item.get("hooks", []))
        text = str(item.get("text", "")).replace("|", "\\|")
        lines.append(f"| {index} | {text} | {hooks} |")

    faq_items = result.sections["faq"].data.get("items", [])
    covered = {item.get("objection") for item in faq_items}
    lines += [
        "",
        "### FAQ 3대 반론 커버리지",
        "",
        f"- 비싸지 않을까 (price): {'✓' if 'price' in covered else '✗ 미커버'}",
        f"- 나한테 맞을까 (fit): {'✓' if 'fit' in covered else '✗ 미커버'}",
        f"- 믿어도 될까 (trust): {'✓' if 'trust' in covered else '✗ 미커버'}",
        "",
        "## 발행 전 체크리스트",
        "",
        "- [ ] 랜딩 푸터의 환불 정책·사업자 정보를 채웠다 (전자상거래법)",
        "- [ ] 증거 섹션의 실적이 실제 자료와 일치한다",
        "- [ ] 이메일 5통을 사람이 읽고 승인했다 (초안 생성 → 사람 승인 → 발행)",
        "",
    ]

    path = out_dir / "build_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_outputs(result: FunnelResult, out_root: Path) -> Path:
    """산출물을 `out_root/<slug>/` 에 쓰고 그 폴더 경로를 돌려준다.

    이메일·리드매그넷·카피 변형·빌드 리포트는 **어디에 올리든 같다.**
    달라지는 것은 첫 화면뿐이라 플랫폼별로 그것만 갈아 끼운다.

        own         landing.html
        kmong       detail_page.md   (크몽은 HTML 을 못 올린다)
        instagram   reels_captions.md + dm_flow.yaml
    """
    from funnel_builder import platforms                          # 순환 참조를 피한다

    out_dir = out_root / result.data.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    if result.platform == "kmong":
        platforms.write_kmong_detail(result, out_dir)
    elif result.platform == "instagram":
        platforms.write_instagram_pack(result, out_dir)
        platforms.write_dm_flow(result, out_dir)
    else:
        write_landing(result, out_dir)

    write_emails(result, out_dir)
    write_lead_magnet_outline(result, out_dir)
    write_copy_variants(result, out_dir)
    write_build_report(result, out_dir)
    return out_dir
