"""시니어 시청자 규격 — **이 상품이 '싼 영상 공장' 과 갈리는 지점.**

값싸게 많이 만드는 도구는 이미 많다. 이 상품이 다른 것은 **누가 보는지를
정해 놓고 만든다**는 점이다. 60대 이상이 보는 영상은 20대가 보는 영상과
만드는 법이 다르다. 취향이 아니라 몸이 달라서다.

근거가 되는 사실:

* **노인성 난청은 고주파부터 온다.** 4kHz 대역이 먼저 나빠진다. 자음(ㅅ·ㅊ·ㅋ)이
  그 대역에 몰려 있어 "말은 들리는데 무슨 말인지 모르겠다" 가 된다
* **소음 속 말소리 분리가 특히 어려워진다.** 그래서 배경음악을 평소보다 더
  낮춰야 한다. 젊은 시청자 기준(-12dB)으로는 부족하다
* **노안으로 작은 글씨를 못 읽는다.** 자막이 장식이 아니라 본문이 된다
* **빠른 화면 전환을 따라가기 어렵다.** 장면이 4초 안에 바뀌면 내용을 놓친다

아래 값은 **권장값이지 법이 아니다.** 다만 지키면 시청 지속 시간이 달라진다.
이 규격 자체가 이 상품에서 파는 것의 큰 부분이다.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["RULES", "Rule", "check_plan", "Finding", "SPEC_SUMMARY", "grade"]


@dataclass
class Rule:
    """규격 한 줄."""

    key: str
    title: str
    recommended: str
    why: str
    field: str = ""
    minimum: float | None = None
    maximum: float | None = None

    @property
    def measurable(self) -> bool:
        """숫자로 잴 수 있는 규칙인가. 목소리 높낮이 같은 것은 못 잰다."""
        return bool(self.field)

    def judge(self, value) -> str:
        """ok / warn / na / advice"""
        if not self.measurable:
            # 숫자로 못 재는 항목까지 '안 적었다' 고 하면 잔소리가 된다.
            return "advice"
        if value is None or value == "":
            return "na"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "na"
        if self.minimum is not None and number < self.minimum:
            return "warn"
        if self.maximum is not None and number > self.maximum:
            return "warn"
        return "ok"


RULES: tuple[Rule, ...] = (
    Rule(
        key="subtitle_px",
        title="자막 글자 크기",
        recommended="1080p 기준 64px 이상 (화면 높이의 6% 이상)",
        why="노안으로 작은 글씨를 못 읽습니다. 시니어 영상에서 자막은 장식이 "
            "아니라 본문입니다. 소리를 줄이고 자막만 읽는 시청자가 많습니다",
        field="subtitle_px", minimum=64,
    ),
    Rule(
        key="subtitle_chars",
        title="자막 한 줄 글자 수",
        recommended="한국어 16자 이하, 최대 2줄",
        why="한 줄이 길면 눈이 줄을 놓칩니다. 짧게 끊어 여러 장 넘기는 편이 "
            "길게 한 장 띄우는 것보다 낫습니다",
        field="subtitle_chars", maximum=16,
    ),
    Rule(
        key="speech_rate",
        title="말 속도",
        recommended="분당 300음절 이하",
        why="한국어 뉴스 앵커가 분당 330~360음절쯤 됩니다. 시니어 대상은 그보다 "
            "느려야 합니다. 빠르면 들리기는 해도 뜻이 안 남습니다",
        field="speech_rate", maximum=300,
    ),
    Rule(
        key="bgm_db",
        title="배경음악 크기",
        recommended="말소리 대비 -18dB 이하",
        why="노인성 난청은 소음 속에서 말소리를 골라내기가 특히 어렵습니다. "
            "젊은 시청자 기준(-12dB)으로는 부족합니다. 아예 빼는 것도 좋습니다",
        field="bgm_db", maximum=-18,
    ),
    Rule(
        key="scene_seconds",
        title="장면 유지 시간",
        recommended="한 장면 4초 이상",
        why="화면이 빨리 바뀌면 내용을 놓칩니다. 쇼츠 문법을 그대로 가져오면 "
            "이 시청자층에서는 역효과입니다",
        field="scene_seconds", minimum=4,
    ),
    Rule(
        key="contrast",
        title="글자와 배경 명도 대비",
        recommended="4.5:1 이상 (흰 글자 + 검은 테두리나 반투명 띠)",
        why="대비가 낮으면 글자가 배경에 묻힙니다. 밝은 사진 위 흰 글자가 "
            "가장 흔한 실수입니다",
        field="contrast", minimum=4.5,
    ),
    Rule(
        key="voice_pitch",
        title="화자 목소리",
        recommended="중저음 화자",
        why="고주파부터 안 들리기 시작하므로 높은 목소리가 불리합니다. "
            "또렷한 발음이 성우 느낌보다 중요합니다",
    ),
    Rule(
        key="length_minutes",
        title="영상 길이",
        recommended="8~15분",
        why="너무 짧으면 내용이 안 남고, 20분을 넘기면 끝까지 보기 어렵습니다. "
            "쇼츠는 이 시청자층에 잘 맞지 않습니다",
        field="length_minutes", minimum=8, maximum=15,
    ),
)

SPEC_SUMMARY = (
    "자막 64px 이상 · 한 줄 16자 · 분당 300음절 이하 · 배경음 -18dB 이하 · "
    "장면 4초 이상 · 대비 4.5:1 이상 · 8~15분"
)


@dataclass
class Finding:
    rule: Rule
    value: object
    status: str

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def warn(self) -> bool:
        return self.status == "warn"

    @property
    def label(self) -> str:
        return {"ok": "맞습니다", "warn": "권장값을 벗어납니다",
                "na": "안 적었습니다", "advice": "참고하세요"}[self.status]


def check_plan(plan: dict) -> list[Finding]:
    """기획안이 시니어 규격에 맞는지 본다. 숫자가 없는 항목은 넘긴다."""
    findings: list[Finding] = []
    for rule in RULES:
        value = plan.get(rule.field) if rule.field else None
        findings.append(Finding(rule=rule, value=value, status=rule.judge(value)))
    return findings


def grade(findings: list[Finding]) -> str:
    """한 줄 판정."""
    warns = [item for item in findings if item.warn]
    unset = [item for item in findings if item.status == "na"]  # 잴 수 있는데 안 적은 것
    if warns:
        names = ", ".join(item.rule.title for item in warns)
        return f"권장값을 벗어난 항목이 {len(warns)}개 있습니다: {names}"
    if unset:
        return (f"어긴 것은 없습니다. 다만 {len(unset)}개 항목을 적지 않아 "
                f"확인하지 못했습니다")
    return "시니어 규격을 모두 맞췄습니다"
