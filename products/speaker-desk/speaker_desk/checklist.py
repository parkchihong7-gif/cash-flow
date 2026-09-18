"""체크리스트 — **되돌릴 수 없는 일부터 앞에 세운다.**

해외 연사 초청에서 일정이 터지는 이유는 대개 하나다. **비자를 늦게 시작해서.**
초청장은 하루면 쓰지만, 비자 심사는 못 당긴다. 그래서 D-120 부터 역산한다.

각 항목에 `hard` 를 둔 것은 **놓치면 못 되돌리는 일**이라는 뜻이다.
그 날짜가 지났는데 안 끝났으면 화면이 빨갛게 표시한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from speaker_desk.roster import Event, Speaker

__all__ = ["Task", "TEMPLATE", "build", "overdue_count"]


@dataclass(frozen=True)
class TaskSpec:
    days_before: int
    title: str
    detail: str
    hard: bool = False
    only_paid: bool = False
    only_interpreter: bool = False


#: D-day 에서 역산한 표준 일정. 숫자는 여유를 둔 값이다.
TEMPLATE: tuple[TaskSpec, ...] = (
    TaskSpec(120, "연사 확정과 구두 합의",
             "날짜·주제·사례비 수준을 말로 맞춥니다. 문서는 그다음입니다"),
    TaskSpec(110, "체류자격 확인",
             "대가를 주는지, 며칠 머무는지로 어느 자격을 볼지 좁힙니다. "
             "**출입국이나 주한공관에 직접 확인하세요**", hard=True),
    TaskSpec(100, "초청장 발급",
             "영문. 행사명·일정·초청 주체·체류 비용 부담 주체가 들어가야 합니다",
             hard=True),
    TaskSpec(95, "계약서 체결",
             "사례비를 **세전으로 적을지 세후로 적을지** 여기서 정합니다. "
             "안 정하면 지급일에 분쟁이 납니다", hard=True, only_paid=True),
    TaskSpec(90, "비자 신청 시작",
             "연사가 거주국 공관에 신청합니다. 심사 기간은 나라마다 다릅니다",
             hard=True),
    TaskSpec(80, "거주자증명서 요청",
             "조세조약을 적용하려면 연사 거주국 세무당국 발급 원본이 필요합니다. "
             "**받는 데 몇 주 걸리는 나라가 있습니다**", hard=True, only_paid=True),
    TaskSpec(70, "항공권 예약",
             "비자가 나온 뒤가 안전하지만, 요금 때문에 먼저 잡는다면 "
             "변경 가능한 조건으로 하세요"),
    TaskSpec(60, "숙소 예약", "행사장에서 이동 시간 20분 안쪽이 무난합니다"),
    TaskSpec(45, "발표자료 1차 요청",
             "이때 받아야 통역 준비와 번역 시간이 나옵니다"),
    TaskSpec(40, "통역사 섭외",
             "동시통역은 2인 1조가 기본입니다. 전문 분야면 더 일찍 잡으세요",
             only_interpreter=True),
    TaskSpec(30, "비자 발급 확인",
             "안 나왔으면 지금이 대안을 찾을 마지막 시점입니다", hard=True),
    TaskSpec(21, "발표자료 최종본 수령",
             "통역사에게 넘겨 용어집을 만들 시간입니다", only_interpreter=True),
    TaskSpec(14, "리허설 일정 확정",
             "시차를 고려해 잡습니다. 도착 다음 날 오전은 피하세요"),
    TaskSpec(10, "의전 일정표 발송",
             "공항 영접·이동·식사·행사 시간을 연사 현지 시간 병기로"),
    TaskSpec(7, "원천징수 서류 최종 확인",
             "거주자증명서 원본이 손에 있어야 합니다. **지급일 전에** 없으면 "
             "기본 세율로 떼고 나중에 경정청구해야 합니다", hard=True, only_paid=True),
    TaskSpec(3, "입국 정보 확인", "항공편·도착 시각·영접 담당자 연락처"),
    TaskSpec(0, "행사 당일", "리허설·발표·정산 서명"),
    TaskSpec(-7, "사례비 지급과 원천징수 신고",
             "지급일이 속한 달의 다음 달 10일까지 원천징수이행상황신고서를 냅니다",
             hard=True, only_paid=True),
    TaskSpec(-30, "지급명세서 제출 확인",
             "비거주자 지급명세서 제출 기한을 세무대리인과 확인하세요",
             only_paid=True),
)


@dataclass
class Task:
    """체크리스트 한 줄."""

    due: date
    days_before: int
    title: str
    detail: str
    hard: bool
    speaker: str = ""

    def state(self, today: date) -> str:
        if self.due < today:
            return "late" if self.hard else "past"
        if (self.due - today).days <= 7:
            return "soon"
        return "ahead"

    def label(self, today: date) -> str:
        return {"late": "지났습니다", "past": "지난 일정",
                "soon": "곧", "ahead": "여유 있음"}[self.state(today)]

    @property
    def dday(self) -> str:
        if self.days_before > 0:
            return f"D-{self.days_before}"
        if self.days_before == 0:
            return "D-day"
        return f"D+{-self.days_before}"


def build(event: Event, speaker: Speaker | None = None) -> list[Task]:
    """연사별 체크리스트. 연사를 안 주면 행사 전체 공통 항목만."""
    tasks: list[Task] = []
    for spec in TEMPLATE:
        if spec.only_paid and not (speaker and speaker.paid):
            continue
        if spec.only_interpreter and not (speaker and speaker.needs_interpreter):
            continue
        tasks.append(Task(
            due=event.event_date - timedelta(days=spec.days_before),
            days_before=spec.days_before,
            title=spec.title,
            detail=spec.detail,
            hard=spec.hard,
            speaker=speaker.name if speaker else "",
        ))
    return sorted(tasks, key=lambda item: item.due)


def overdue_count(tasks: list[Task], today: date) -> int:
    """놓치면 못 되돌리는 일 중 날짜가 지난 것."""
    return sum(1 for task in tasks if task.state(today) == "late")
