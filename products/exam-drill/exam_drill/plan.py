"""학습 계획 — Claude 에게 **숫자와 단원 이름만** 준다.

문제 본문을 주지 않는 이유는 두 가지다.

1. 애초에 이 프로그램은 문제 본문을 들고 있지 않다 (records.py 참조)
2. 들고 있더라도 주지 않을 것이다. 주면 "이 문제 비슷한 걸 만들어 줄까" 가 되고,
   그건 다른 사람의 저작물을 다시 쓰는 일이다

그래서 모델이 받는 것은 이런 모양이다.

    부동산공법 28.3점(과락) · 약한 단원: 국토계획법 총칙 8.3%, 개발행위허가 16.7%
    · 틀린 이유: 몰라서 60%

이 정도로도 "무엇부터 볼지" 는 충분히 말할 수 있다. 그 이상은 사람이 한다.
"""

from __future__ import annotations

from exam_drill.metrics import Analysis, PASS_AVERAGE, PASS_SUBJECT, TARGET_SECONDS
from exam_drill.records import REASON_FIX

__all__ = ["PLAN_SYSTEM", "facts_for", "offline_plan", "plan_for", "BANNED", "banned_hits"]

#: 나오면 안 되는 말. 시험 결과를 약속하거나, 문제를 옮겨 쓰자는 쪽이다.
BANNED: tuple[str, ...] = (
    "합격을 보장", "반드시 합격", "무조건 합격", "합격 보장",
    "문제를 그대로", "기출을 복사", "지문을 옮겨", "족보",
)

PLAN_SYSTEM = """당신은 공인중개사 시험을 준비하는 사람의 학습 코치입니다.

받는 것은 과목별 점수와 약한 단원 목록, 틀린 이유 분포뿐입니다.
문제 본문은 받지 않습니다. 그것만으로 2주 계획을 세우세요.

규칙:
- 과락(40점 미만) 과목이 있으면 그 과목을 가장 먼저 다룹니다. 평균보다 과락이 급합니다
- 틀린 이유에 맞는 처방을 씁니다. '몰라서' 와 '실수' 는 해야 할 일이 다릅니다
- 단원 이름과 숫자로만 말합니다. 특정 문제·지문·교재를 지어내지 않습니다
- 합격을 약속하지 않습니다. "이렇게 하면 붙는다" 는 말을 쓰지 않습니다
- 하루에 할 수 있는 양으로 씁니다. 지키지 못할 계획은 계획이 아닙니다
- 각 줄은 '무엇을 · 얼마나' 가 드러나게 씁니다

형식: 줄마다 하나씩, 번호나 기호 없이 8줄 이내. 한국어."""


def banned_hits(text: str) -> list[str]:
    return [word for word in BANNED if word in (text or "")]


def facts_for(analysis: Analysis) -> str:
    """모델에 넘길 사실만. 여기 없는 것은 모델도 모른다."""
    lines = [f"푼 문항 {analysis.attempts}개 · 회차 {', '.join(analysis.rounds) or '미상'}",
             f"전 과목 평균 {analysis.average}점 (합격선 {PASS_AVERAGE}점)"]
    for subject in analysis.subjects:
        mark = " ← 과락" if subject.failing else ""
        weak = ", ".join(f"{unit.unit} {unit.rate}%"
                         for unit in subject.weak_units[:3]) or "없음"
        reason = subject.top_reason or "적지 않음"
        lines.append(
            f"- {subject.name}: {subject.score}점{mark} · 약한 단원: {weak}"
            f" · 가장 잦은 이유: {reason} · 문항당 {subject.median_seconds}초")
    if analysis.untouched:
        names = ", ".join(item.name for item in analysis.untouched)
        lines.append(f"아직 한 문제도 안 푼 과목: {names}")
    return "\n".join(lines)


def offline_plan(analysis: Analysis) -> list[str]:
    """Claude 없이 규칙으로 쓰는 계획. 모의 실행과 키 없는 환경에서 쓴다."""
    lines: list[str] = []

    for subject in analysis.failing:
        weak = subject.weak_units[:2]
        units = ", ".join(unit.unit for unit in weak) or "전 단원"
        lines.append(
            f"{subject.name} {subject.score}점 — 과락선 {PASS_SUBJECT}점까지 "
            f"{subject.margin}점 모자랍니다. {units} 를 먼저 다시 봅니다")

    if not analysis.failing and analysis.average < PASS_AVERAGE:
        lines.append(
            f"과락은 없습니다. 평균 {analysis.average}점에서 합격선까지 "
            f"{analysis.average_margin}점입니다. 약한 단원부터 올립니다")

    for unit in analysis.weakest[:3]:
        fix = REASON_FIX.get(unit.top_reason, "그 단원을 다시 봅니다")
        lines.append(f"{unit.unit} {unit.rate}% ({unit.total}문항) — {fix}")

    slow = [item for item in analysis.subjects if item.too_slow]
    if slow:
        names = ", ".join(f"{item.name} {item.median_seconds}초" for item in slow)
        lines.append(
            f"시간이 깁니다: {names}. 기준은 문항당 {TARGET_SECONDS}초입니다. "
            f"시간을 재고 푸는 연습을 하루 20문항씩 넣으세요")

    if analysis.untouched:
        names = ", ".join(item.name for item in analysis.untouched)
        lines.append(f"{names} 은 아직 한 문제도 풀지 않았습니다. 평균에 안 잡혀 있습니다")

    top = analysis.reasons.most_common(1)
    if top:
        reason, count = top[0]
        share = round(count / max(1, sum(analysis.reasons.values())) * 100)
        lines.append(
            f"틀린 이유의 {share}%가 '{reason}' 입니다. {REASON_FIX[reason]}")

    lines.append("2주 뒤에 같은 회차를 다시 풀어 이 표를 새로 만들어 보세요")
    return lines[:8]


def plan_for(analysis: Analysis, ask_fn, model: str) -> list[str]:
    """Claude 로 계획을 쓴다. 금지어가 섞인 줄은 규칙 문장으로 바꾼다."""
    raw = ask_fn(PLAN_SYSTEM, facts_for(analysis), model=model, max_tokens=900)
    lines = [line.strip(" -•*\t") for line in str(raw).splitlines() if line.strip()]

    fallback = offline_plan(analysis)
    cleaned: list[str] = []
    for index, line in enumerate(lines[:8]):
        if banned_hits(line):
            # 약속하는 말이 나오면 그 줄만 규칙 문장으로 갈아 끼운다.
            cleaned.append(fallback[index] if index < len(fallback) else fallback[-1])
        else:
            cleaned.append(line)
    return cleaned or fallback
