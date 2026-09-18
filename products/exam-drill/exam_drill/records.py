"""풀이 기록 — **내가 푼 결과만** 담는다. 문제 본문은 담지 않는다.

한 줄이 한 문항이다. 적는 것은 다섯 가지뿐이다.

    회차 · 과목 · 문항번호 · 맞았나 · 왜 틀렸나

문제 지문도, 보기도, 정답도 적지 않는다. 적을 칸조차 두지 않았다.
칸이 있으면 언젠가 채우게 되고, 채우면 그건 기출문제 사본이 된다
(시험문제는 어문저작물로 보호받는다 — README §2).

`단원` 은 본인이 고르는 값이다. 어느 단원인지는 문제를 보면 알 수 있고,
그건 사실의 분류이지 문제의 복제가 아니다.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from exam_drill.syllabus import subject_of

__all__ = [
    "Attempt", "REASONS", "REASON_LABEL", "REASON_FIX", "COLUMNS",
    "load_records", "write_blank_sheet", "RecordError",
]

#: 틀린 이유. **처방이 서로 다르기 때문에** 나눈다.
REASONS: tuple[str, ...] = ("몰라서", "헷갈려서", "실수", "시간부족")

REASON_LABEL = {
    "몰라서": "아예 모르던 것",
    "헷갈려서": "비슷한 것과 섞임",
    "실수": "알았는데 틀림",
    "시간부족": "시간이 모자람",
}

#: 이유별로 해야 할 일이 다르다. 이게 이 프로그램의 핵심이다.
REASON_FIX = {
    "몰라서": "그 단원을 처음부터 다시 봅니다. 문제를 더 푸는 것은 나중입니다",
    "헷갈려서": "섞이는 둘을 나란히 놓고 차이만 적은 비교표를 만듭니다",
    "실수": "지문에 조건을 표시하며 읽는 습관을 들입니다. 개념 공부는 필요 없습니다",
    "시간부족": "시간을 재고 풉니다. 한 문제 75초를 넘기면 넘어가는 연습을 합니다",
}

#: 기록표의 열. 순서까지 이대로 쓴다.
COLUMNS = ("회차", "과목", "문항번호", "정오", "단원", "이유", "소요초")


class RecordError(ValueError):
    """기록표를 읽지 못했을 때."""


class Attempt(BaseModel):
    """한 문항을 푼 결과."""

    model_config = {"extra": "forbid"}

    round_name: str = Field(description="회차. 예: 35회 또는 2024-1차")
    subject: str = Field(description="과목 키")
    number: int = Field(ge=1, le=40, description="문항번호 1~40")
    correct: bool
    unit: str = Field(default="", description="단원. 본인이 고른다")
    reason: str = Field(default="", description="틀렸을 때만. REASONS 중 하나")
    seconds: int = Field(default=0, ge=0, le=3600)

    @field_validator("subject")
    @classmethod
    def _known_subject(cls, value: str) -> str:
        return subject_of(value).key

    @field_validator("reason")
    @classmethod
    def _known_reason(cls, value: str) -> str:
        text = (value or "").strip()
        if text and text not in REASONS:
            raise ValueError(f"이유는 {'/'.join(REASONS)} 중 하나로 적으세요: {text}")
        return text

    @model_validator(mode="after")
    def _reason_only_when_wrong(self) -> "Attempt":
        # 맞은 문제에 이유가 붙어 있으면 대개 줄을 밀려 적은 것이다.
        if self.correct and self.reason:
            raise ValueError(
                f"{self.round_name} {self.number}번: 맞은 문제에 이유가 적혀 있습니다. "
                "줄이 밀리지 않았는지 보세요")
        return self

    @property
    def wrong(self) -> bool:
        return not self.correct


def _to_bool(value: str) -> bool:
    text = (value or "").strip().upper()
    if text in {"O", "0", "○", "정답", "맞음", "TRUE", "1"}:
        # 손으로 적을 때 O 와 0 을 섞어 쓴다. 둘 다 맞음으로 본다.
        return True
    if text in {"X", "×", "오답", "틀림", "FALSE"}:
        return False
    raise RecordError(f"정오 칸은 O 또는 X 로 적으세요: {value!r}")


@dataclass
class LoadResult:
    attempts: list[Attempt]
    skipped: list[str]

    @property
    def count(self) -> int:
        return len(self.attempts)


def load_records(path: str | Path) -> LoadResult:
    """기록표 CSV 를 읽는다.

    **아직 안 푼 줄(정오 칸이 빈 줄)은 조용히 건너뛴다.** 빈 표를 미리 뽑아
    두고 푸는 대로 채우는 쓰임을 전제로 하기 때문이다.
    """
    path = Path(path)
    if not path.is_file():
        raise RecordError(
            f"기록표가 없습니다: {path}\n"
            f"  `python cli.py sheet --round 35회` 로 빈 표를 먼저 만드세요")

    attempts: list[Attempt] = []
    skipped: list[str] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in ("회차", "과목", "문항번호", "정오")
                   if name not in (reader.fieldnames or [])]
        if missing:
            raise RecordError(
                f"기록표에 없는 열이 있습니다: {', '.join(missing)}\n"
                f"  열 이름은 {', '.join(COLUMNS)} 입니다")

        for line, row in enumerate(reader, start=2):
            mark = (row.get("정오") or "").strip()
            if not mark:
                skipped.append(f"{line}줄")
                continue
            try:
                attempts.append(Attempt(
                    round_name=(row.get("회차") or "").strip(),
                    subject=(row.get("과목") or "").strip(),
                    number=int((row.get("문항번호") or "0").strip() or 0),
                    correct=_to_bool(mark),
                    unit=(row.get("단원") or "").strip(),
                    reason=(row.get("이유") or "").strip(),
                    seconds=int((row.get("소요초") or "0").strip() or 0),
                ))
            except (ValueError, RecordError) as exc:
                raise RecordError(f"{path.name} {line}줄: {exc}") from exc

    if not attempts:
        raise RecordError(
            f"푼 기록이 하나도 없습니다 ({path.name}).\n"
            f"  정오 칸에 O 나 X 를 적은 줄이 있어야 합니다")
    return LoadResult(attempts=attempts, skipped=skipped)


def write_blank_sheet(path: str | Path, round_name: str,
                      subjects: list[str], questions: int = 40) -> Path:
    """빈 기록표를 만든다. 문항번호만 박아 두고 나머지는 사람이 채운다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for key in subjects:
            subject = subject_of(key)
            for number in range(1, questions + 1):
                writer.writerow([round_name, subject.key, number, "", "", "", ""])
    return path
