"""정기 실행 — "그거 요즘 돌렸던가" 를 화면이 대신 기억한다.

프로그램이 열두 개가 되면서 성격이 갈렸다.

* **한 번 만들고 끝나는 것** — 퍼널·전자책·강의 슬라이드·상세페이지 카피
* **되풀이해 돌려야 뜻이 생기는 것** — 니치 리서치(매일), 주간 보고서(매주),
  인스타 예약 게시(계속 켜 둠)

뒤쪽은 거르면 조용히 망가진다. 니치 리서치를 사흘 빼먹으면 그 사흘은 영영
비어 있다. **유튜브 API 는 지난 날의 값을 돌려주지 않기 때문이다.** 화면에
빨간 줄이 뜨지 않으면 아무도 모른다. 그래서 이 화면을 만들었다.

이 모듈은 **읽기만 한다.** 여기서 프로그램을 돌리지 않는다. 스케줄러는 cron
이나 n8n 이 맡고, 대시보드는 "밀렸는지" 만 본다. 대시보드가 꺼져 있는 동안에도
cron 은 돌아야 하므로, 실행을 여기에 두면 오히려 약해진다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

__all__ = ["ScheduleRow", "collect", "parse_when", "days_since", "SUMMARY_KEYS"]

SUMMARY_KEYS = ("recurring", "late", "never", "fresh")


def parse_when(value: str) -> datetime | None:
    """DB 에 적힌 시각 문자열을 날짜로. 못 읽으면 None."""
    text = (value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None)


def days_since(when: datetime | None, today: date | None = None) -> int | None:
    """며칠 전인가. 한 번도 안 돌았으면 None."""
    if when is None:
        return None
    base = today or date.today()
    return max(0, (base - when.date()).days)


@dataclass
class ScheduleRow:
    """프로그램 한 개의 정기 실행 상태."""

    id: str
    number: int
    name: str
    status_label: str
    cadence: str
    cadence_label: str
    recurring: bool
    at: str
    cron: str
    command: str
    why: str
    skipped: str
    warmup_days: int
    last_run: str = ""
    last_status: str = ""
    last_mode: str = ""
    age_days: int | None = None
    grace_days: int = 0

    @property
    def never(self) -> bool:
        return self.recurring and self.age_days is None

    @property
    def late(self) -> bool:
        """정해진 주기를 넘겼는가. 한 번도 안 돈 것은 따로 센다."""
        if not self.recurring or self.age_days is None:
            return False
        return self.age_days > self.grace_days

    @property
    def state(self) -> str:
        if not self.recurring:
            return "manual"
        if self.never:
            return "never"
        return "late" if self.late else "fresh"

    @property
    def state_label(self) -> str:
        return {
            "manual": "필요할 때",
            "never": "아직 한 번도",
            "late": "밀렸습니다",
            "fresh": "제때 돌고 있습니다",
        }[self.state]

    @property
    def last_run_label(self) -> str:
        """화면에 실을 시각. 초와 'T' 는 떼고 분까지만."""
        return self.last_run[:16].replace("T", " ") if self.last_run else ""

    @property
    def age_label(self) -> str:
        if self.age_days is None:
            return "기록 없음"
        if self.age_days == 0:
            return "오늘"
        return f"{self.age_days}일 전"


def collect(registry, db, today: date | None = None) -> list[ScheduleRow]:
    """프로그램마다 주기와 마지막 실행을 묶는다.

    되풀이하는 것이 앞, 그중에서도 밀린 것이 맨 앞에 온다. 화면을 열었을 때
    손대야 할 것이 위에 있어야 한다.
    """
    last = db.last_run_per_program()
    rows: list[ScheduleRow] = []
    for program in registry.programs:
        spec = program.schedule
        record = last.get(program.id) or {}
        when = parse_when(str(record.get("started_at") or ""))
        rows.append(ScheduleRow(
            id=program.id,
            number=program.number,
            name=program.name,
            status_label=program.status_label,
            cadence=spec.cadence,
            cadence_label=spec.cadence_label,
            recurring=spec.recurring,
            at=spec.at,
            cron=spec.cron,
            command=spec.command,
            why=spec.why,
            skipped=spec.skipped,
            warmup_days=spec.warmup_days,
            last_run=str(record.get("started_at") or ""),
            last_status=str(record.get("status") or ""),
            last_mode=str(record.get("mode") or ""),
            age_days=days_since(when, today),
            grace_days=spec.grace_days,
        ))

    order = {"late": 0, "never": 1, "fresh": 2, "manual": 3}
    rows.sort(key=lambda row: (order[row.state], row.number))
    return rows


def summarize(rows: list[ScheduleRow]) -> dict[str, int]:
    """윗줄에 띄울 숫자."""
    return {
        "recurring": sum(1 for row in rows if row.recurring),
        "late": sum(1 for row in rows if row.late),
        "never": sum(1 for row in rows if row.never),
        "fresh": sum(1 for row in rows if row.state == "fresh"),
    }
