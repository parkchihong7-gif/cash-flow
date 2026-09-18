"""지표 — **과락부터 본다.**

공인중개사는 절대평가다. 매 과목 40점 이상, 평균 60점 이상이면 붙는다. 그래서
"평균 65점인데 떨어졌다" 는 일이 생긴다. 한 과목이 38점이면 나머지가 아무리
좋아도 끝이다. 화면이 제일 먼저 말해야 하는 것이 그것이다.

문항당 2.5점(40문항 100점)으로 환산한다.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median

from exam_drill.records import Attempt, REASONS
from exam_drill.syllabus import SUBJECTS, Subject, subject_of

__all__ = [
    "POINT_PER_QUESTION", "PASS_SUBJECT", "PASS_AVERAGE", "TARGET_SECONDS",
    "MIN_SAMPLE", "SubjectScore", "UnitScore", "Analysis", "analyze",
]

POINT_PER_QUESTION = 2.5     # 40문항 100점
PASS_SUBJECT = 40            # 과목 과락선
PASS_AVERAGE = 60            # 전 과목 평균
TARGET_SECONDS = 75          # 50분 / 40문항

#: 이만큼은 풀어 봐야 그 단원 정답률을 숫자로 믿을 수 있다.
MIN_SAMPLE = 3


def _rate(correct: int, total: int) -> float:
    return round(correct / total * 100, 1) if total else 0.0


@dataclass
class UnitScore:
    """단원 하나의 성적."""

    subject: str
    unit: str
    total: int
    correct: int
    reasons: Counter = field(default_factory=Counter)

    @property
    def rate(self) -> float:
        return _rate(self.correct, self.total)

    @property
    def enough(self) -> bool:
        """숫자를 믿어도 될 만큼 풀었는가."""
        return self.total >= MIN_SAMPLE

    @property
    def top_reason(self) -> str:
        return self.reasons.most_common(1)[0][0] if self.reasons else ""


@dataclass
class SubjectScore:
    """과목 하나의 성적."""

    key: str
    name: str
    round_name: str
    total: int
    correct: int
    seconds: list[int] = field(default_factory=list)
    reasons: Counter = field(default_factory=Counter)
    units: list[UnitScore] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return _rate(self.correct, self.total)

    @property
    def score(self) -> float:
        """100점 환산. 푼 만큼의 정답률을 40문항에 그대로 미룬 값이다."""
        return round(self.rate, 1)

    @property
    def failing(self) -> bool:
        """과락선 아래인가. 여기 걸리면 다른 건 볼 것도 없다."""
        return self.score < PASS_SUBJECT

    @property
    def margin(self) -> float:
        """과락선까지 남은 점수. 음수면 이미 넘었다."""
        return round(PASS_SUBJECT - self.score, 1)

    @property
    def median_seconds(self) -> int:
        timed = [value for value in self.seconds if value > 0]
        return int(median(timed)) if timed else 0

    @property
    def too_slow(self) -> bool:
        return self.median_seconds > TARGET_SECONDS

    @property
    def weak_units(self) -> list[UnitScore]:
        """충분히 풀었는데 정답률이 낮은 단원. 낮은 순."""
        enough = [unit for unit in self.units if unit.enough]
        return sorted(enough, key=lambda unit: (unit.rate, -unit.total))

    @property
    def top_reason(self) -> str:
        return self.reasons.most_common(1)[0][0] if self.reasons else ""


@dataclass
class Analysis:
    """전체 결과."""

    subjects: list[SubjectScore]
    rounds: list[str]
    attempts: int
    reasons: Counter = field(default_factory=Counter)

    @property
    def average(self) -> float:
        """전 과목 평균. 안 푼 과목은 빼고 센다."""
        if not self.subjects:
            return 0.0
        return round(sum(item.score for item in self.subjects) / len(self.subjects), 1)

    @property
    def failing(self) -> list[SubjectScore]:
        return [item for item in self.subjects if item.failing]

    @property
    def would_pass(self) -> bool:
        """지금 상태로 치면 붙는가. **푼 과목만 가지고 본 것이다.**"""
        return bool(self.subjects) and not self.failing and self.average >= PASS_AVERAGE

    @property
    def untouched(self) -> list[Subject]:
        """아직 한 문제도 안 푼 과목. 평균에서 빠져 있으니 짚어 줘야 한다."""
        done = {item.key for item in self.subjects}
        return [item for item in SUBJECTS if item.key not in done]

    @property
    def weakest(self) -> list[UnitScore]:
        """과목을 가리지 않고 약한 단원 순."""
        pool: list[UnitScore] = []
        for subject in self.subjects:
            pool += subject.weak_units
        return sorted(pool, key=lambda unit: (unit.rate, -unit.total))

    @property
    def average_margin(self) -> float:
        """평균 합격선까지 남은 점수."""
        return round(PASS_AVERAGE - self.average, 1)

    @property
    def verdict(self) -> str:
        """한 줄 판정. 과락이 있으면 평균은 말하지 않는다."""
        if not self.subjects:
            return "아직 푼 기록이 없습니다."
        if self.failing:
            names = ", ".join(item.name for item in self.failing)
            return (f"과락 위험 과목이 있습니다: {names}. "
                    f"평균이 아무리 높아도 한 과목이 40점 아래면 불합격입니다.")
        if self.average < PASS_AVERAGE:
            return (f"과락은 없지만 평균이 {self.average}점입니다. "
                    f"합격선까지 {self.average_margin}점 남았습니다.")
        return (f"지금 푼 범위 안에서는 평균 {self.average}점으로 합격선을 넘습니다. "
                f"다만 이건 **푼 문제만** 가지고 센 값입니다.")


def analyze(attempts: list[Attempt]) -> Analysis:
    """풀이 기록을 지표로 바꾼다."""
    by_subject: dict[str, list[Attempt]] = defaultdict(list)
    for item in attempts:
        by_subject[item.subject].append(item)

    scores: list[SubjectScore] = []
    overall: Counter = Counter()

    for key, rows in by_subject.items():
        subject = subject_of(key)
        reasons = Counter(row.reason for row in rows if row.wrong and row.reason)
        overall.update(reasons)

        units: dict[str, UnitScore] = {}
        for row in rows:
            if not row.unit:
                continue
            slot = units.setdefault(row.unit, UnitScore(
                subject=key, unit=row.unit, total=0, correct=0))
            slot.total += 1
            slot.correct += int(row.correct)
            if row.wrong and row.reason:
                slot.reasons[row.reason] += 1

        round_names = sorted({row.round_name for row in rows if row.round_name})
        scores.append(SubjectScore(
            key=key,
            name=subject.name,
            round_name=", ".join(round_names),
            total=len(rows),
            correct=sum(1 for row in rows if row.correct),
            seconds=[row.seconds for row in rows],
            reasons=reasons,
            units=sorted(units.values(), key=lambda unit: unit.unit),
        ))

    order = {subject.key: index for index, subject in enumerate(SUBJECTS)}
    scores.sort(key=lambda item: order.get(item.key, 99))

    return Analysis(
        subjects=scores,
        rounds=sorted({row.round_name for row in attempts if row.round_name}),
        attempts=len(attempts),
        reasons=overall,
    )
