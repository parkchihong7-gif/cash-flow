"""프로그램 실행기 — 대시보드 '테스트' 탭에서 쓴다.

매니페스트의 `run.command` 를 서브프로세스로 돌리고 결과를 DB 에 남긴다.
모의 실행(dry) 은 `run.dry_run_command` 를 쓰며 외부 API 를 부르지 않아 비용이 들지 않는다.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.db import Database
from core.manifest import ProgramManifest

__all__ = ["RunOutcome", "run_program", "RunError"]

#: 로그가 길어져도 DB 와 화면이 감당할 수 있게 자른다.
MAX_LOG_CHARS = 20000


class RunError(RuntimeError):
    """실행을 시작조차 못 했을 때."""


@dataclass
class RunOutcome:
    """실행 한 건의 결과."""

    run_id: int
    status: str          # success | warning | failed
    exit_code: int
    log: str
    output_dir: str

    @property
    def ok(self) -> bool:
        return self.status in {"success", "warning"}


def _truncate(text: str) -> str:
    if len(text) <= MAX_LOG_CHARS:
        return text
    return text[:MAX_LOG_CHARS] + f"\n\n... (로그가 길어 {MAX_LOG_CHARS}자에서 잘렸습니다)"


def _latest_output(program: ProgramManifest) -> str:
    """산출물 폴더에서 가장 최근에 바뀐 하위 폴더를 찾는다."""
    if program.run is None:
        return ""
    root = program.directory / program.run.output_dir
    if not root.is_dir():
        return ""
    folders = [p for p in root.iterdir() if p.is_dir()]
    if not folders:
        return str(root)
    return str(max(folders, key=lambda p: p.stat().st_mtime))


def run_program(
    program: ProgramManifest,
    db: Database,
    mode: str = "dry",
    input_path: str | None = None,
    member_id: int | None = None,
    env_overrides: dict[str, str] | None = None,
) -> RunOutcome:
    """프로그램을 한 번 실행하고 이력을 남긴다.

    Args:
        program: 실행할 프로그램.
        db: 이력을 기록할 DB.
        mode: ``dry`` 면 모의 실행(비용 없음), ``real`` 이면 실제 실행.
        input_path: 입력 파일 경로. 없으면 매니페스트의 `run.input_file`.
        member_id: 어떤 고객을 위한 실행인지 (선택).
        env_overrides: 자식 프로세스에 넘길 추가 환경 변수 (프로그램 설정값 등).

    Raises:
        RunError: 실행 정의가 없거나, 모의 실행을 지원하지 않거나,
            `paused` 로 막아 둔 프로그램일 때.
    """
    # 손보는 중인 프로그램은 여기서 막는다. **화면에서 버튼을 감추는 것만으로는
    # 부족하다** — 주소를 직접 치거나 예약 실행이 부르면 그대로 돈다. 실행으로
    # 가는 길이 여럿(상세 화면·운영 콘솔·예약)이라 길목 하나에서 닫는다.
    if program.blocked:
        raise RunError(f"{program.name} 은(는) 지금 실행을 막아 두었습니다 — {program.paused.strip()}")
    if program.run is None:
        raise RunError(f"{program.name} 에는 실행 정의(run)가 없습니다.")

    spec = program.run
    if mode == "dry" and not spec.dry_run_command:
        raise RunError(f"{program.name} 은 모의 실행을 지원하지 않습니다.")

    template = spec.dry_run_command if mode == "dry" else spec.command
    resolved_input = input_path or spec.input_file
    command = [part.replace("{input}", resolved_input) for part in template]

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    if env_overrides:
        env.update({key: str(value) for key, value in env_overrides.items()})

    run_id = db.start_run(program.id, mode, member_id)
    try:
        completed = subprocess.run(
            command,
            cwd=str(program.directory),
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
            env=env,
        )
        log = _truncate((completed.stdout or "") + (completed.stderr or ""))
        exit_code = completed.returncode
        # 종료 코드 2는 "만들어졌지만 사람이 고쳐야 함" 이라는 약속이다.
        status = {0: "success", 2: "warning"}.get(exit_code, "failed")
    except subprocess.TimeoutExpired:
        log = f"{spec.timeout_seconds}초 안에 끝나지 않아 중단했습니다."
        exit_code, status = -1, "failed"
    except FileNotFoundError as exc:
        log = f"실행 명령을 찾지 못했습니다: {exc}"
        exit_code, status = -1, "failed"

    output_dir = _latest_output(program) if status != "failed" else ""
    db.finish_run(run_id, status, exit_code, log, output_dir)
    return RunOutcome(run_id=run_id, status=status, exit_code=exit_code, log=log,
                      output_dir=output_dir)
