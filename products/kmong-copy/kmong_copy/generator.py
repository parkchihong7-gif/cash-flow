"""크몽 상세페이지 카피 생성기 — 섹션별 생성과 정책 검사.

호출 순서
    1. 상세페이지 본문 (헤드라인·추천 대상·제공 내용·프로세스·차별점·FAQ·정책)
    2. 패키지 3단 + 제목 10안 + 태그 20개 (상세페이지를 컨텍스트로)
    3. 문의 응답 템플릿 8종

검사 두 가지가 생성 뒤에 붙는다.
    - 금지 문구 (:mod:`shared.banned_phrases`) — 성과를 단정하는 표현
    - 외부 연락처 유도 (:mod:`kmong_copy.policy`) — 크몽 정책

둘 중 하나라도 걸리면 해당 섹션만 최대 2회 다시 만들고, 그래도 남으면
compliance_report.md 에 경고로 남긴다. 조용히 넘어가지 않는다.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from kmong_copy.policy import ContactFinding, check_contact_lure  # noqa: E402
from kmong_copy.schema import (  # noqa: E402
    FAQ_COUNT, HEADLINE_LIMIT, NO_PROOF_TEXT, PACKAGE_DESC_LIMIT,
    PACKAGE_TITLE_LIMIT, PACKAGE_TIERS, PROCESS_STEPS, SCRIPT_COUNT,
    ServiceInput, TAG_COUNT, TITLE_COUNT, TITLE_LIMIT, truncate,
)
from shared import banned_phrases  # noqa: E402
from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import ask as default_ask  # noqa: E402

__all__ = ["KmongGenerator", "SectionResult", "CopyResult", "BASE_DIR"]

#: 상품 폴더 (이 패키지의 부모).
BASE_DIR = Path(__file__).resolve().parents[1]
PROMPTS_DIR = BASE_DIR / "prompts"

MAX_REGENERATIONS = 2


@dataclass
class SectionResult:
    """섹션 하나의 생성 결과와 검사 이력."""

    name: str
    data: dict[str, Any]
    attempts: int = 1
    banned: list[str] = field(default_factory=list)
    contact: list[ContactFinding] = field(default_factory=list)
    length_fixes: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.banned or self.contact or self.length_fixes)


@dataclass
class CopyResult:
    """서비스 하나의 전체 생성 결과."""

    data: ServiceInput
    sections: dict[str, SectionResult]
    model: str
    generated_at: datetime

    @property
    def detail(self) -> dict[str, Any]:
        return self.sections["detail"].data

    @property
    def packages(self) -> dict[str, Any]:
        return self.sections["packages"].data

    @property
    def scripts(self) -> dict[str, Any]:
        return self.sections["scripts"].data

    @property
    def warnings(self) -> list[SectionResult]:
        return [section for section in self.sections.values() if not section.clean]


def _collect_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _collect_strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _collect_strings(item)]
    return []


class KmongGenerator:
    """입력 하나로 크몽 등록 자료 5종을 만든다.

    Args:
        data: 검증된 입력.
        model: Claude 모델 ID.
        ask_fn: LLM 호출 함수. 테스트·모의 실행에서 교체한다.
    """

    def __init__(
        self,
        data: ServiceInput,
        model: str = DEFAULT_MODEL,
        ask_fn: Callable[..., Any] = default_ask,
    ) -> None:
        self.data = data
        self.model = model
        self.ask_fn = ask_fn
        self.common = (PROMPTS_DIR / "common.md").read_text(encoding="utf-8")
        self.detail_rules = (PROMPTS_DIR / "detail_page.md").read_text(encoding="utf-8")
        self.package_rules = (PROMPTS_DIR / "packages.md").read_text(encoding="utf-8")
        self.inquiry_rules = (PROMPTS_DIR / "inquiry.md").read_text(encoding="utf-8")
        self.sections: dict[str, SectionResult] = {}

    # ------------------------------------------------------------- 프롬프트
    def _brief(self) -> str:
        deliver = "\n".join(f"  - {item}" for item in self.data.what_you_deliver)
        diff = "\n".join(f"  - {item}" for item in self.data.differentiators)
        proof = (
            "\n".join(f"  - {item}" for item in self.data.proof)
            if self.data.has_proof
            else f"  (없음 — 성과 자리에 '{NO_PROOF_TEXT}' 를 쓰고 수치를 만들지 말 것)"
        )
        seed = (
            "\n".join(f"  - {item}" for item in self.data.faq_seed)
            if self.data.faq_seed else "  (없음)"
        )
        return (
            f"[서비스] {self.data.service_name}\n"
            f"[카테고리] {self.data.category}\n"
            f"[대상] {self.data.who_for}\n"
            f"[산출물]\n{deliver}\n"
            f"[차별점]\n{diff}\n"
            f"[기본 작업일] {self.data.turnaround_days}일\n"
            f"[가격] BASIC {self.data.price_text('BASIC')} / "
            f"STANDARD {self.data.price_text('STANDARD')} / "
            f"PREMIUM {self.data.price_text('PREMIUM')}\n"
            f"[실적·후기]\n{proof}\n"
            f"[넣고 싶은 FAQ 질문]\n{seed}\n"
        )

    # -------------------------------------------------------- 생성 + 검사
    def _generate(
        self,
        name: str,
        rules: str,
        instruction: str,
        length_check: Callable[[dict], list[str]] | None = None,
    ) -> SectionResult:
        """섹션을 만들고 금지 문구·외부 연락처·길이 위반이 있으면 다시 만든다."""
        system = f"{self.common}\n\n---\n\n{rules}"
        base_user = f"{self._brief()}\n{instruction}"
        user = base_user
        data: dict[str, Any] = {}
        banned: list[str] = []
        contact: list[ContactFinding] = []
        too_long: list[str] = []

        for attempt in range(1, MAX_REGENERATIONS + 2):
            data = self.ask_fn(system, user, model=self.model, json_mode=True)
            text = "\n".join(_collect_strings(data))
            banned = banned_phrases.check(text)
            contact = check_contact_lure(text)
            too_long = length_check(data) if length_check else []

            if not (banned or contact or too_long):
                return SectionResult(name=name, data=data, attempts=attempt)

            problems = []
            if banned:
                problems.append(f"금지 문구가 들어갔습니다: {', '.join(banned)}")
            if contact:
                labels = ", ".join(sorted({f.label for f in contact}))
                problems.append(
                    f"크몽 정책상 쓸 수 없는 외부 연락처 유도가 있습니다: {labels}. "
                    "'크몽 메시지로 문의 주세요' 로 바꾸세요."
                )
            if too_long:
                shown = too_long[:5]
                problems.append(
                    "글자 수 제한을 넘겼습니다: " + " / ".join(shown)
                    + (f" 외 {len(too_long) - 5}건" if len(too_long) > 5 else "")
                )
            user = (
                f"{base_user}\n\n[재작성 요청]\n"
                + "\n".join(f"- {p}" for p in problems)
                + "\n해당 부분을 고쳐서 처음부터 다시 쓰세요."
            )

        return SectionResult(
            name=name, data=data, attempts=MAX_REGENERATIONS + 1,
            banned=banned, contact=contact, length_fixes=too_long,
        )

    # ------------------------------------------------------------ 섹션 정의
    def _detail(self) -> SectionResult:
        return self._generate(
            "detail", self.detail_rules,
            f"크몽 상세페이지 본문을 만드세요.\n"
            f"- headline 은 {HEADLINE_LIMIT}자 이내\n"
            f"- summary 3줄, recommended_for 4~5개, not_for 2개\n"
            f"- deliverables 는 주어진 산출물 개수만큼\n"
            f"- process 는 정확히 {PROCESS_STEPS}단계\n"
            f"- differentiators 는 주어진 3개를 각각 풀어서\n"
            f"- faq 는 정확히 {FAQ_COUNT}개\n"
            f"- policy 는 전자상거래법상 필수 표기이니 빠짐없이",
            length_check=self._check_detail,
        )

    def _check_detail(self, data: dict) -> list[str]:
        headline = str(data.get("headline", ""))
        violations = []
        if len(headline) > HEADLINE_LIMIT:
            violations.append(f"헤드라인 {len(headline)}자 (최대 {HEADLINE_LIMIT})")
        return violations

    def _packages(self, detail: dict[str, Any]) -> SectionResult:
        return self._generate(
            "packages", self.package_rules,
            f"상세페이지 요약: {json.dumps(detail, ensure_ascii=False)[:900]}\n\n"
            f"패키지 3단과 제목 10안, 검색 태그를 만드세요.\n"
            f"- packages 는 {', '.join(PACKAGE_TIERS)} 순서로 3개\n"
            f"- 패키지 제목 {PACKAGE_TITLE_LIMIT}자, 설명 {PACKAGE_DESC_LIMIT}자 이내\n"
            f"- days 는 BASIC 이 {self.data.turnaround_days}일 기준, 상위로 갈수록 같거나 짧게\n"
            f"- titles 는 {TITLE_COUNT}개, 각 {TITLE_LIMIT}자 이내, 검색 키워드를 앞에\n"
            f"- tags 는 {TAG_COUNT}개",
            length_check=self._check_packages,
        )

    def _check_packages(self, data: dict) -> list[str]:
        violations = []
        for package in data.get("packages", []):
            tier = package.get("tier", "?")
            title = str(package.get("title", ""))
            description = str(package.get("description", ""))
            if len(title) > PACKAGE_TITLE_LIMIT:
                violations.append(f"{tier} 제목 {len(title)}자")
            if len(description) > PACKAGE_DESC_LIMIT:
                violations.append(f"{tier} 설명 {len(description)}자")
        for index, title in enumerate(data.get("titles", []), start=1):
            text = str(title.get("text", ""))
            if len(text) > TITLE_LIMIT:
                violations.append(f"제목 {index}안 {len(text)}자")
        return violations

    def _scripts(self, detail: dict[str, Any]) -> SectionResult:
        return self._generate(
            "scripts", self.inquiry_rules,
            f"상세페이지 요약: {json.dumps(detail, ensure_ascii=False)[:700]}\n\n"
            f"문의 응답 템플릿 {SCRIPT_COUNT}종을 만드세요.\n"
            "규칙에 적힌 8가지 상황을 순서대로 다룹니다.\n"
            "외부 연락처를 절대 쓰지 마세요. '크몽 메시지로 문의 주세요' 로 통일합니다.",
        )

    # ------------------------------------------------------------------ 실행
    def build(self) -> CopyResult:
        """섹션을 순서대로 생성한다. 앞 결과가 뒤 프롬프트의 컨텍스트가 된다."""
        detail = self._detail()
        if detail.length_fixes:
            detail.data["headline"] = truncate(
                detail.data.get("headline", ""), HEADLINE_LIMIT
            )
        self.sections["detail"] = detail

        packages = self._packages(detail.data)
        if packages.length_fixes:
            for package in packages.data.get("packages", []):
                package["title"] = truncate(package.get("title", ""), PACKAGE_TITLE_LIMIT)
                package["description"] = truncate(
                    package.get("description", ""), PACKAGE_DESC_LIMIT
                )
            for title in packages.data.get("titles", []):
                title["text"] = truncate(title.get("text", ""), TITLE_LIMIT)
        self.sections["packages"] = packages

        self.sections["scripts"] = self._scripts(detail.data)

        return CopyResult(
            data=self.data, sections=self.sections, model=self.model,
            generated_at=datetime.now().astimezone(),
        )
