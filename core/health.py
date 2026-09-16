"""오늘 볼 것을 모은다.

프로그램이 여덟 개가 되면서 홈 화면의 숫자 여섯 개만으로는
"지금 뭘 해야 하는지" 가 안 보이게 됐다. 실패한 실행, 곧 끝나는 이용권,
아직 한 번도 안 돌려 본 프로그램 같은 것은 **찾아 들어가야** 보였다.

이 모듈이 그걸 대신 찾아서 홈 맨 위에 올린다.
**할 일이 없으면 아무것도 안 보여 준다.** 늘 떠 있는 경고는 곧 안 보게 된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

__all__ = ["Task", "checklist", "LEVELS", "EXPIRY_WINDOW_DAYS", "RECENT_RUNS"]

#: 심각한 순서. 화면에서 이 순서로 정렬한다.
LEVELS = ("bad", "warn", "info")

#: 이용권 만료를 며칠 전부터 알릴지.
EXPIRY_WINDOW_DAYS = 30

#: 실패를 찾을 때 훑어볼 최근 실행 수.
RECENT_RUNS = 40


@dataclass
class Task:
    """관리자가 오늘 확인할 것 하나."""

    level: str
    title: str
    detail: str
    href: str = ""
    action: str = ""

    @property
    def order(self) -> int:
        return LEVELS.index(self.level) if self.level in LEVELS else len(LEVELS)


def _days_left(value: str) -> int | None:
    text = (value or "")[:10]
    if not text:
        return None
    try:
        return (date.fromisoformat(text) - date.today()).days
    except ValueError:
        return None


def checklist(db, registry, api_key_set: bool = True,
              default_code: bool = False) -> list[Task]:
    """지금 손봐야 할 것들. 심각한 순서로 돌려준다."""
    tasks: list[Task] = []

    # ---------------------------------------------------------- 설정 문제
    for error in getattr(registry, "errors", []):
        tasks.append(Task(
            "bad", f"{error.name} 의 program.yaml 을 읽지 못했습니다",
            str(error.message)[:160],
            "/manual/admin", "매뉴얼 5장 보기",
        ))

    if default_code:
        tasks.append(Task(
            "warn", "접속 코드가 기본값 그대로입니다",
            "이 화면에는 고객 이름·연락처가 있습니다. 인터넷에 열어 두셨다면 "
            ".env 의 DASHBOARD_ACCESS_CODE 를 바꾸세요.",
            "/manual/admin", "바꾸는 법",
        ))

    if not api_key_set:
        tasks.append(Task(
            "info", "Claude API 키가 없어 모의 실행만 됩니다",
            "실제 실행을 하시려면 .env 에 ANTHROPIC_API_KEY 를 넣으세요. "
            "8번 수익 시뮬레이터는 키 없이도 돌아갑니다.",
            "/settings", "설정 열기",
        ))

    # ---------------------------------------------------------- 실행 결과
    recent = db.list_runs(limit=RECENT_RUNS)
    failed = [row for row in recent if row["status"] == "failed"]
    warned = [row for row in recent if row["status"] == "warning"]

    if failed:
        first = failed[0]
        tasks.append(Task(
            "bad", f"실패한 실행 {len(failed)}건",
            f"가장 최근은 {first['program_id']} (#{first['id']}). "
            "무엇 때문에 멈췄는지 로그를 보세요.",
            "/runs?status=failed", "실패만 보기",
        ))

    if warned:
        tasks.append(Task(
            "warn", f"사람이 손볼 곳이 있는 실행 {len(warned)}건",
            "파일은 만들어졌지만 검증에 걸린 곳이 있습니다. "
            "그대로 납품하면 안 됩니다.",
            "/runs?status=warning", "경고만 보기",
        ))

    # ------------------------------------------------- 한 번도 안 돌린 프로그램
    last_runs = db.last_run_per_program()
    never_run = [
        program for program in registry.programs
        if program.status == "ready" and program.runnable
        and program.id not in last_runs
    ]
    if never_run:
        names = ", ".join(f"{p.number}. {p.name}" for p in never_run[:4])
        more = f" 외 {len(never_run) - 4}개" if len(never_run) > 4 else ""
        tasks.append(Task(
            "info", f"아직 한 번도 안 돌려 본 프로그램 {len(never_run)}개",
            f"{names}{more}. 모의 실행은 비용이 들지 않습니다.",
            f"/programs/{never_run[0].id}/test", "첫 번째 열기",
        ))

    # ---------------------------------------------------------- 이용권
    expiring = db.expiring_licenses(EXPIRY_WINDOW_DAYS)
    overdue = [row for row in expiring if (_days_left(row["expires_at"]) or 0) < 0]
    soon = [row for row in expiring if row not in overdue]

    if overdue:
        tasks.append(Task(
            "bad", f"기한이 지난 이용권 {len(overdue)}건",
            "아직 '유효' 로 되어 있습니다. 연장하셨으면 기한을 고치고, "
            "끝났으면 상태를 만료로 바꾸세요. 그대로 두면 매출이 부풀어 보입니다.",
            "/members", "회원관리 열기",
        ))

    if soon:
        nearest = min(soon, key=lambda row: row["expires_at"])
        days = _days_left(nearest["expires_at"])
        tasks.append(Task(
            "warn", f"{EXPIRY_WINDOW_DAYS}일 안에 끝나는 이용권 {len(soon)}건",
            f"가장 빠른 건 {nearest['member_name']} 님 "
            f"({nearest['program_id']}, {days}일 남음). 미리 연락하면 연장률이 달라집니다.",
            "/members", "회원관리 열기",
        ))

    tasks.sort(key=lambda task: task.order)
    return tasks
