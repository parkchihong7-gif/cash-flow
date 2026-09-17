"""규정 점검 — 프로그램마다 법·정책 장치가 붙어 있는지 본다.

왜 화면으로 만들었나.
    CLAUDE.md §3 의 금지 사항은 **하나만 어겨도 상품을 폐기해야 하는** 것들이다.
    프로그램이 열 개가 되니 "그건 어느 상품에 넣었더라" 가 생겼다.

무엇을 보는가 — **코드에 그 장치가 있는지**다.
    이 화면은 장치가 **붙어 있는지**를 볼 뿐, 잘 도는지를 보지 않는다.
    그건 테스트가 하는 일이다. 여기서 초록이라고 안심하면 안 된다.
    그래서 근거로 **무엇을 찾았는지**(어느 모듈을 부르는지, 어떤 설정이 있는지)를
    같이 보여 준다. 판단은 보는 사람이 한다.

한 가지는 거꾸로 본다.
    비공식 자동화(브라우저 매크로)는 **없어야 통과**다. 있으면 빨간불이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Rule", "RULES", "Finding", "ProgramReport", "audit", "STATUS_LABEL"]

STATUS_LABEL = {
    "ok": "있음",
    "none": "해당 없음",
    "unknown": "확인 필요",
    "bad": "걸림",
}

#: 뒤져 볼 확장자. 소스와 문서만 본다.
SOURCE_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".txt", ".js"}

#: 이만큼까지만 읽는다. 산출물 폴더에 큰 파일이 섞여 들어오는 것을 막는다.
MAX_BYTES = 400_000

#: 훑지 않는 폴더.
SKIP_DIRS = {"outputs", "__pycache__", ".git", "node_modules"}


@dataclass(frozen=True)
class Rule:
    """지켜야 할 것 하나."""

    key: str
    title: str
    law: str                       # 근거가 되는 법·정책
    why: str                       # 안 지키면 무슨 일이 생기는가
    needles: tuple[str, ...]       # 코드에서 찾을 조각
    applies_to: tuple[str, ...] = ()   # 비면 전부에 해당
    inverted: bool = False         # True 면 '찾으면 걸림'


RULES: tuple[Rule, ...] = (
    Rule(
        key="ai_label",
        title="AI 생성물 표시",
        law="인공지능기본법 제31조 (2026-01-22 시행)",
        why=("우리는 AI 프로그램을 파는 쪽이라 '인공지능사업자' 로서 표시 의무가 있습니다. "
             "위반하면 시정명령 후 최대 3,000만 원 과태료입니다."),
        needles=("ai_label", "AI_LABEL", "생성형 AI"),
    ),
    Rule(
        key="banned",
        title="과장 문구 검사",
        law="CLAUDE.md §3-2 · 표시광고법 (소비자원 주의보 2025)",
        why=("고액 부업 강의 피해가 실재합니다. 판매용 문구에 '수익 보장' 류 표현이 "
             "남으면 상품 자체가 분쟁거리가 됩니다."),
        needles=("banned_phrases",),
    ),
    Rule(
        key="disclosure",
        title="대가성 문구 강제",
        law="CLAUDE.md §3-6 · 공정위 추천·보증 심사지침",
        why=("쿠팡파트너스는 문구가 없으면 **경고 없이** 자격을 정지합니다. "
             "유튜브는 유료 프로모션을 알리지 않은 영상을 내립니다."),
        needles=("disclosure", "파트너스"),
        applies_to=("affiliate-matcher",),
    ),
    Rule(
        key="human",
        title="사람 검수 지점",
        law="CLAUDE.md §3-3 · 유튜브 양산형 콘텐츠 정책 (2025-07)",
        why=("사람이 보지 않고 나가는 파이프라인은 만들지 않습니다. "
             "'초안 생성 → 사람 승인 → 발행' 이 원칙입니다."),
        needles=("초안", "사람이", "검수", "고치세요", "확인하세요"),
    ),
    Rule(
        key="no_macro",
        title="비공식 자동화 없음",
        law="CLAUDE.md §3-7 (공식 API·OAuth 만 사용)",
        why=("브라우저 매크로나 비밀번호 저장형 자동화는 계정 정지 사유이고, "
             "고객 계정을 위험에 빠뜨립니다."),
        needles=("selenium", "pyautogui", "undetected_chromedriver", "webdriver"),
        inverted=True,
    ),
)


@dataclass
class Finding:
    """규칙 하나에 대한 판정."""

    rule: Rule
    status: str                    # ok | none | unknown | bad
    hits: list[str] = field(default_factory=list)   # 무엇을 찾았는지

    @property
    def label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    @property
    def evidence(self) -> str:
        return ", ".join(self.hits[:4])


@dataclass
class ProgramReport:
    """프로그램 하나의 점검 결과."""

    id: str
    number: int
    name: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def bad(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "bad"]

    @property
    def unknown(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "unknown"]

    @property
    def clear(self) -> bool:
        return not self.bad and not self.unknown


def _texts(directory: Path) -> str:
    """프로그램 폴더의 소스와 문서를 이어 붙인다. 산출물은 건너뛴다."""
    parts: list[str] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(directory).parts):
            continue
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(parts)


def _judge(rule: Rule, program_id: str, blob: str) -> Finding:
    if rule.applies_to and program_id not in rule.applies_to:
        return Finding(rule=rule, status="none")

    hits = [needle for needle in rule.needles if needle in blob]

    if rule.inverted:
        # 없어야 통과인 규칙. 찾으면 빨간불이다.
        return Finding(rule=rule, status="bad" if hits else "ok", hits=hits)

    return Finding(rule=rule, status="ok" if hits else "unknown", hits=hits)


def audit(registry) -> list[ProgramReport]:
    """등록된 프로그램을 전부 훑는다."""
    reports: list[ProgramReport] = []
    for program in registry.programs:
        blob = _texts(Path(program.directory))
        reports.append(ProgramReport(
            id=program.id,
            number=program.number,
            name=program.name,
            findings=[_judge(rule, program.id, blob) for rule in RULES],
        ))
    return reports
