"""설정 한눈에 — 프로그램마다 흩어진 값을 한 장으로 모은다.

프로그램이 열두 개가 되니 "그 값을 어디서 바꿨더라" 가 잦아졌다.
설정은 프로그램마다, 파일은 폴더마다, 매뉴얼은 또 다른 곳에 있다.

이 모듈은 **읽기만 한다.** 값을 바꾸는 곳은 여전히 각 프로그램의 '수정' 탭이다.
한 화면에서 다 고치게 만들면 어느 프로그램을 건드리는지 모른 채 바꾸게 된다.

비밀값(토큰·API 키)은 **있다/없다만** 보여 준다. 값은 절대 화면에 싣지 않는다.
대시보드는 터널로 열 수 있고, 화면은 어깨너머로도 보인다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "SettingRow",
    "FileRow",
    "ManualRow",
    "ProgramConfig",
    "EnvRow",
    "collect",
    "first_line",
    "env_rows",
    "SECRET_HINTS",
    "ENV_KEYS",
]

# 이 조각이 키 이름에 있으면 값이 아니라 설정 여부만 보여 준다.
SECRET_HINTS = ("TOKEN", "KEY", "SECRET", "PASSWORD", "PASSWD", "CODE")

# 대시보드 자체가 쓰는 환경변수. 값은 보여 주지 않는다.
ENV_KEYS: tuple[tuple[str, str], ...] = (
    ("ANTHROPIC_API_KEY", "Claude 호출용 키. 없으면 모의 실행만 됩니다."),
    ("DASHBOARD_ACCESS_CODE", "접속 코드. 기본값 그대로면 홈에서 경고합니다."),
    ("DASHBOARD_SECRET", "접속 쿠키 서명용. 비우면 자동으로 만들어 파일에 둡니다."),
    ("DASHBOARD_DATA_DIR", "DB 와 비밀 파일을 둘 곳. 도커·클라우드에서 씁니다."),
    ("DASHBOARD_SESSION_HOURS", "한 번 들어오면 얼마나 유지할지(시간). 기본 72시간입니다."),
    ("NOTION_TOKEN", "9번 노션 자동 생성용. 없어도 손으로 만들 수 있습니다."),
    ("NOTION_PARENT_PAGE_ID", "9번이 만들 자리. 그 페이지에 통합을 연결해야 합니다."),
    ("COUPANG_ACCESS_KEY", "10번 쿠팡파트너스 링크용. 없으면 검색 URL 만 만듭니다."),
    ("COUPANG_SECRET_KEY", "10번 서명용. 액세스 키와 짝입니다."),
    ("GOOGLE_CREDENTIALS_JSON", "11번 구글시트 읽기용 서비스 계정 파일 경로."),
    ("SLACK_WEBHOOK_URL", "11번 주간 보고서를 슬랙으로 보낼 때만."),
    ("IG_ACCESS_TOKEN", "11번 인스타 예약 게시용. 60일마다 갱신해야 합니다."),
    ("IG_USER_ID", "11번이 올릴 비즈니스 계정 번호."),
    ("YOUTUBE_API_KEY", "12번 니치 리서치 수집용. 무료입니다."),
)


def is_secret(key: str) -> bool:
    upper = key.upper()
    return any(hint in upper for hint in SECRET_HINTS)


def first_line(text: str) -> str:
    """도움말의 첫 줄만, 마크다운 표시를 걷어내고 돌려준다.

    표 한 칸에 들어갈 길이여야 해서 한 줄만 쓴다. 전체는 '수정' 탭에 있다.
    """
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line.replace("**", "").replace("`", "").strip()


def _display(key: str, value: Any) -> str:
    """화면에 실을 문자열. 비밀값은 내용을 감춘다."""
    if isinstance(value, bool):
        return "켬" if value else "끔"
    text = "" if value is None else str(value)
    if text in ("1", "true", "True"):
        text = "켬"
    elif text in ("0", "false", "False"):
        text = "끔"
    if is_secret(key):
        return "설정됨" if text.strip() else "비어 있음"
    if not text.strip():
        return "비어 있음"
    if len(text) > 60:
        return text[:57] + "…"
    return text


@dataclass
class SettingRow:
    """설정 한 줄. `changed` 가 True 면 기본값에서 바뀐 값이다."""

    key: str
    label: str
    type: str
    shown: str
    default_shown: str
    changed: bool
    secret: bool
    help: str = ""


@dataclass
class FileRow:
    """'수정' 탭에서 고칠 수 있는 파일 한 줄."""

    path: str
    label: str
    kind: str
    exists: bool
    size: int
    help: str = ""

    @property
    def size_label(self) -> str:
        return f"{self.size:,}B" if self.exists else "없음"


@dataclass
class ManualRow:
    audience: str          # admin | client
    label: str
    path: str
    exists: bool
    chars: int


@dataclass
class ProgramConfig:
    """프로그램 한 개의 설정·파일·매뉴얼 묶음."""

    id: str
    number: int
    name: str
    status_label: str
    version: str
    settings: list[SettingRow] = field(default_factory=list)
    files: list[FileRow] = field(default_factory=list)
    manuals: list[ManualRow] = field(default_factory=list)
    outputs: int = 0
    steps: int = 0
    faq: int = 0
    runnable: bool = False
    dry_runnable: bool = False
    missing: list[str] = field(default_factory=list)

    @property
    def changed_count(self) -> int:
        return sum(1 for row in self.settings if row.changed)


@dataclass
class EnvRow:
    key: str
    note: str
    present: bool


def _manual_row(program, audience: str, relative: str) -> ManualRow | None:
    if not relative:
        return None
    label = "관리자용" if audience == "admin" else "고객용"
    try:
        path = program.resolve(relative)
    except ValueError:
        # 폴더 밖을 가리키는 매뉴얼은 열지 않는다. 없는 것으로 본다.
        return ManualRow(audience=audience, label=label, path=relative, exists=False, chars=0)
    if not path.is_file():
        return ManualRow(audience=audience, label=label, path=relative, exists=False, chars=0)
    return ManualRow(
        audience=audience, label=label, path=relative, exists=True,
        chars=len(path.read_text(encoding="utf-8")),
    )


def collect(registry, db) -> list[ProgramConfig]:
    """프로그램마다 지금 값을 모은다.

    Args:
        registry: `core.registry.Registry`
        db: `core.db.Database` — 저장된 설정을 읽기만 한다.
    """
    result: list[ProgramConfig] = []
    for program in registry.programs:
        stored = db.get_program_settings(program.id)
        defaults = program.default_settings()

        rows: list[SettingRow] = []
        for spec in program.settings:
            value = stored.get(spec.key, defaults.get(spec.key))
            default = defaults.get(spec.key)
            rows.append(SettingRow(
                key=spec.key,
                label=spec.label,
                type=spec.type,
                shown=_display(spec.key, value),
                default_shown=_display(spec.key, default),
                changed=str(value or "") != str(default or ""),
                secret=is_secret(spec.key),
                help=first_line(spec.help),
            ))

        files: list[FileRow] = []
        missing: list[str] = []
        for item in program.editable_files:
            try:
                path = program.resolve(item.path)
            except ValueError:
                missing.append(item.path)
                continue
            exists = path.is_file()
            if not exists:
                missing.append(item.path)
            files.append(FileRow(
                path=item.path, label=item.label, kind=item.kind,
                exists=exists, size=path.stat().st_size if exists else 0,
                help=first_line(item.help),
            ))

        manuals = [row for row in (
            _manual_row(program, "admin", program.manuals.admin),
            _manual_row(program, "client", program.manuals.client),
        ) if row is not None]
        missing += [row.path for row in manuals if not row.exists]

        result.append(ProgramConfig(
            id=program.id,
            number=program.number,
            name=program.name,
            status_label=program.status_label,
            version=program.version,
            settings=rows,
            files=files,
            manuals=manuals,
            outputs=len(program.outputs),
            steps=len(program.steps),
            faq=len(program.faq),
            runnable=program.runnable,
            dry_runnable=bool(program.run and program.run.dry_run_command),
            missing=missing,
        ))
    return result


def env_rows(environ: dict[str, str] | None = None) -> list[EnvRow]:
    """환경변수가 채워져 있는지만 본다. 값은 읽어도 화면에 싣지 않는다."""
    source = os.environ if environ is None else environ
    return [
        EnvRow(key=key, note=note, present=bool((source.get(key) or "").strip()))
        for key, note in ENV_KEYS
    ]
