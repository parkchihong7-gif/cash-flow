"""프로그램 매니페스트 규격 — `program.yaml`.

모든 상품은 자기 폴더에 `program.yaml` 을 둔다. 대시보드는 이 파일만 읽고
프로그램을 등록하므로, **새 프로그램을 만들 때 대시보드 코드를 고칠 필요가 없다.**

새 프로그램 추가 절차:
    1. products/<이름>/ 폴더를 만든다
    2. program.yaml 을 이 규격대로 작성한다
    3. 대시보드를 새로고침한다 — 끝

필드 설명은 각 클래스의 docstring 과 Field description 에 있다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

__all__ = [
    "ProgramManifest",
    "Step",
    "FaqItem",
    "SettingSpec",
    "EditableFile",
    "OutputSpec",
    "PricingPlan",
    "RunSpec",
    "ScheduleSpec",
    "Manuals",
    "load_manifest",
    "MANIFEST_FILENAME",
]

MANIFEST_FILENAME = "program.yaml"

Status = Literal["ready", "wip", "planned"]
SettingType = Literal["text", "textarea", "number", "boolean", "select"]
Cadence = Literal["manual", "daily", "weekly", "monthly", "continuous"]

STATUS_LABEL = {"ready": "운영 중", "wip": "제작 중", "planned": "계획"}

CADENCE_LABEL = {
    "manual": "필요할 때",
    "daily": "매일",
    "weekly": "매주",
    "monthly": "매달",
    "continuous": "계속 켜 둠",
}

# 이 주기를 넘기면 '밀렸다' 고 본다. 계속 켜 두는 것은 하루로 본다.
CADENCE_DAYS = {"daily": 1, "weekly": 7, "monthly": 31, "continuous": 1}


class Step(BaseModel):
    """이용 순서 한 단계."""

    title: str
    body: str = ""
    estimate: str = Field(default="", description="예상 소요 시간. 예: 10분")


class FaqItem(BaseModel):
    """자주 묻는 질문 한 쌍."""

    q: str
    a: str
    audience: Literal["admin", "client", "both"] = "both"


class SettingSpec(BaseModel):
    """설정 항목 하나. 대시보드가 이 정의로 입력 폼을 그린다."""

    key: str
    label: str
    type: SettingType = "text"
    default: str | int | float | bool | None = None
    options: list[str] = Field(default_factory=list, description="type=select 일 때만")
    help: str = ""

    @model_validator(mode="after")
    def _select_needs_options(self) -> "SettingSpec":
        # field_validator 는 값을 생략하면 돌지 않으므로 모델 단위로 검사한다.
        if self.type == "select" and not self.options:
            raise ValueError(f"'{self.key}' 는 type 이 select 이므로 options 가 필요합니다")
        return self


class EditableFile(BaseModel):
    """대시보드 '수정' 탭에서 직접 편집할 파일."""

    path: str = Field(description="프로그램 폴더 기준 상대 경로")
    label: str
    kind: Literal["markdown", "html", "yaml", "text", "json"] = "text"
    help: str = ""


class OutputSpec(BaseModel):
    """산출물 하나에 대한 설명."""

    path: str
    label: str
    description: str = ""


class PricingPlan(BaseModel):
    """판매 플랜. 회원관리에서 라이선스를 발급할 때 선택지가 된다."""

    plan: str
    price: int = Field(ge=0)
    description: str = ""


class RunSpec(BaseModel):
    """'테스트' 탭에서 프로그램을 실행하는 방법."""

    input_file: str = Field(default="", description="편집 가능한 입력 템플릿 경로")
    command: list[str] = Field(description="실행 명령. {input} 자리에 입력 파일 경로가 들어간다")
    dry_run_command: list[str] = Field(
        default_factory=list,
        description="API 비용 없이 도는 모의 실행 명령. 비우면 모의 실행 버튼이 숨겨진다",
    )
    output_dir: str = Field(default="outputs", description="산출물 상위 폴더")
    timeout_seconds: int = Field(default=600, ge=10, le=3600)


class ScheduleSpec(BaseModel):
    """이 프로그램을 **얼마나 자주 돌려야 하는가.**

    한 번 만들고 끝나는 프로그램이 있고(퍼널·전자책), 매일 돌려야 뜻이 생기는
    프로그램이 있다(니치 리서치는 시계열을 직접 쌓아야 한다). 이 둘을 섞어
    두면 "그거 요즘 돌렸던가" 를 사람이 기억해야 한다. 기억은 샌다.

    `cron` 은 붙여 넣을 수 있는 한 줄로 적는다. 대시보드가 그대로 보여 준다.
    """

    cadence: Cadence = "manual"
    at: str = Field(default="", description="도는 시각. 예: 06:00")
    cron: str = Field(default="", description="크론 한 줄. 그대로 복사해 쓸 수 있게")
    command: str = Field(default="", description="사람이 손으로 돌릴 때의 명령")
    why: str = Field(default="", description="왜 이 주기인가")
    skipped: str = Field(default="", description="거르면 무엇이 깨지는가")
    warmup_days: int = Field(
        default=0, ge=0,
        description="며칠은 쌓아야 결과가 뜻을 가지는가. 0이면 첫 회부터 쓸 수 있다",
    )

    @property
    def cadence_label(self) -> str:
        return CADENCE_LABEL.get(self.cadence, self.cadence)

    @property
    def recurring(self) -> bool:
        return self.cadence != "manual"

    @property
    def grace_days(self) -> int:
        """이만큼 지나면 밀린 것으로 본다. 필요할 때 도는 것은 밀리지 않는다."""
        return CADENCE_DAYS.get(self.cadence, 0)


class Manuals(BaseModel):
    """매뉴얼 파일 경로."""

    admin: str = Field(default="", description="관리자용 매뉴얼 (마크다운)")
    client: str = Field(default="", description="구매자용 매뉴얼 (마크다운)")


class ProgramManifest(BaseModel):
    """프로그램 하나의 전체 정의."""

    model_config = {"extra": "forbid"}

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", description="폴더명과 같게 쓴다")
    number: int = Field(ge=1, description="대시보드 표시 번호")
    name: str
    tagline: str = ""
    status: Status = "wip"
    version: str = "0.1.0"
    owner: str = ""

    summary: str = Field(default="", description="개요. 마크다운 허용")
    steps: list[Step] = Field(default_factory=list)
    faq: list[FaqItem] = Field(default_factory=list)
    settings: list[SettingSpec] = Field(default_factory=list)
    editable_files: list[EditableFile] = Field(default_factory=list)
    outputs: list[OutputSpec] = Field(default_factory=list)
    pricing: list[PricingPlan] = Field(default_factory=list)
    manuals: Manuals = Field(default_factory=Manuals)
    run: RunSpec | None = None
    schedule: ScheduleSpec = Field(default_factory=ScheduleSpec)

    # 로드 시 채워진다. YAML 에는 쓰지 않는다.
    directory: Path = Field(default=Path("."), exclude=True)

    @property
    def status_label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    @property
    def runnable(self) -> bool:
        return self.run is not None

    @property
    def recurring(self) -> bool:
        """매일·매주처럼 되풀이해 돌려야 하는 프로그램인가."""
        return self.schedule.recurring

    def default_settings(self) -> dict[str, object]:
        """설정 항목의 기본값 묶음."""
        return {spec.key: spec.default for spec in self.settings}

    def setting(self, key: str) -> SettingSpec | None:
        return next((spec for spec in self.settings if spec.key == key), None)

    def resolve(self, relative: str) -> Path:
        """프로그램 폴더를 벗어나지 않는 경로만 돌려준다.

        Raises:
            ValueError: 폴더 밖을 가리킬 때 (경로 탈출 차단).
        """
        base = self.directory.resolve()
        target = (base / relative).resolve()
        if base != target and base not in target.parents:
            raise ValueError(f"프로그램 폴더 밖의 경로입니다: {relative}")
        return target


def load_manifest(directory: str | Path) -> ProgramManifest:
    """폴더에서 `program.yaml` 을 읽어 검증한다."""
    directory = Path(directory)
    path = directory / MANIFEST_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"{MANIFEST_FILENAME} 이 없습니다: {directory}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} 의 최상위는 키-값 매핑이어야 합니다")

    manifest = ProgramManifest(**raw)
    manifest.directory = directory.resolve()
    return manifest
