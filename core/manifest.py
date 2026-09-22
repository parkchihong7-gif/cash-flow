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
from pydantic import BaseModel, Field, field_validator, model_validator

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
    "Requirements",
    "AccountNeed",
    "SoftwareNeed",
    "Manuals",
    "load_manifest",
    "MANIFEST_FILENAME",
]

MANIFEST_FILENAME = "program.yaml"

Status = Literal["ready", "wip", "planned"]
SettingType = Literal["text", "textarea", "number", "boolean", "select"]
Cadence = Literal["manual", "daily", "weekly", "monthly", "continuous"]
HomePc = Literal["yes", "partial", "no"]
Internet = Literal["none", "optional", "needed"]
LeadTime = Literal["즉시", "하루 이틀", "심사 필요"]

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

HOME_PC_LABEL = {
    "yes": "집 컴퓨터로 됩니다",
    "partial": "집 컴퓨터로 되지만 준비가 있습니다",
    "no": "집 컴퓨터로는 어렵습니다",
}

INTERNET_LABEL = {
    "none": "인터넷 없이도 됩니다",
    "optional": "인터넷이 없어도 모의 실행은 됩니다",
    "needed": "인터넷이 있어야 합니다",
}


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


class AccountNeed(BaseModel):
    """이 프로그램을 쓰려면 **따로 만들어야 하는 계정·권한** 하나.

    돈보다 자주 발목을 잡는 것이 이쪽이다. 코드는 다 됐는데 API 심사가
    2주 걸려서 못 판 적이 있다. 그래서 `lead_time` 을 따로 둔다.
    """

    name: str
    why: str = Field(default="", description="이게 없으면 무엇이 안 되는가")
    cost: str = Field(default="무료", description="비용. 모르면 '확인 필요'")
    lead_time: LeadTime = Field(default="즉시", description="받는 데 걸리는 시간")
    how: str = Field(default="", description="어디서 어떻게 받나")
    env_key: str = Field(default="", description="받은 값을 넣을 .env 키 이름")
    blocking: bool = Field(default=True, description="없으면 아예 못 쓰는가")


class SoftwareNeed(BaseModel):
    """따로 **깔아야 하는 프로그램** 하나 (pip 로 안 깔리는 것)."""

    name: str
    why: str = ""
    how: str = Field(default="", description="설치 명령이나 받는 곳")
    bundled: bool = Field(
        default=False,
        description="requirements.txt 로 같이 깔리면 True. 그러면 따로 안내하지 않는다",
    )


class Requirements(BaseModel):
    """**쓰기 전에 무엇이 필요한가.**

    상세페이지에 "설치만 하면 바로" 라고 써 놓고 실제로는 API 심사가 필요하면
    환불로 돌아온다. 사기까지는 아니어도 신뢰는 거기서 끝난다. 그래서 필요한
    것을 상품 자신이 들고 있게 하고, 대시보드가 한 장에 모아 보여 준다.
    """

    home_pc: HomePc = "yes"
    home_pc_note: str = Field(default="", description="'되지만/어렵다' 면 이유를 쓴다")

    @field_validator("home_pc", mode="before")
    @classmethod
    def _yaml_bool(cls, value):
        """YAML 은 따옴표 없는 `yes` 를 참, `no` 를 거짓으로 읽는다.

        여기서는 그게 바로 우리가 뜻한 값이므로 되돌려 준다. 이 한 줄이 없으면
        `home_pc: yes` 라고 쓴 사람이 영문 모를 오류를 본다.
        """
        if isinstance(value, bool):
            return "yes" if value else "no"
        return value
    internet: Internet = "optional"
    accounts: list[AccountNeed] = Field(default_factory=list)
    software: list[SoftwareNeed] = Field(default_factory=list)
    limits: list[str] = Field(default_factory=list, description="쿼터·한도")
    cautions: list[str] = Field(default_factory=list, description="법·정책상 조심할 것")

    @model_validator(mode="after")
    def _explain_when_not_easy(self) -> "Requirements":
        # "집에서 어렵다" 고만 적고 이유를 안 쓰면 화면이 아무 도움이 안 된다.
        if self.home_pc != "yes" and not self.home_pc_note.strip():
            raise ValueError("home_pc 가 yes 가 아니면 home_pc_note 에 이유를 쓰세요")
        return self

    @property
    def home_pc_label(self) -> str:
        return HOME_PC_LABEL.get(self.home_pc, self.home_pc)

    @property
    def internet_label(self) -> str:
        return INTERNET_LABEL.get(self.internet, self.internet)

    @property
    def blocking_accounts(self) -> list[AccountNeed]:
        """없으면 아예 못 쓰는 계정."""
        return [item for item in self.accounts if item.blocking]

    @property
    def reviewed_accounts(self) -> list[AccountNeed]:
        """심사를 기다려야 하는 계정. 일정이 여기서 밀린다."""
        return [item for item in self.accounts if item.lead_time == "심사 필요"]

    @property
    def extra_software(self) -> list[SoftwareNeed]:
        """pip 말고 따로 깔아야 하는 것."""
        return [item for item in self.software if not item.bundled]

    @property
    def starts_today(self) -> bool:
        """오늘 받아서 오늘 쓸 수 있는가."""
        return not self.reviewed_accounts and self.home_pc != "no"

    @property
    def signup_free(self) -> bool:
        """가입 없이 바로 되는가."""
        return not self.blocking_accounts


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


class LiveSite(BaseModel):
    """이 프로그램이 **저장소 밖에서** 실제로 도는 곳.

    13번 공인중개사처럼, 프로그램 본체가 다른 곳(GitHub Pages 등)에 이미
    올라가 있는 경우가 있다. 그때 대시보드의 [관리자 모드]·[클라이언트 모드]
    는 흉내가 아니라 **그 진짜 주소**를 열어야 한다.

    **비밀번호는 여기 적지 않는다.** 이 저장소는 공개라, 적는 순간
    주소를 아는 누구나 들어온다. 비밀번호는 사장님이 따로 보관하신다.
    """

    model_config = {"extra": "forbid"}

    admin: str = Field(default="", description="관리자 모드 주소 (https://…)")
    client: str = Field(default="", description="클라이언트 모드 주소")
    note: str = Field(default="", description="화면에 함께 보일 한 줄")

    @field_validator("admin", "client")
    @classmethod
    def _https_only(cls, value: str) -> str:
        """http:// 를 막는다. 키를 넣는 화면이라 가로채이면 안 된다."""
        value = value.strip()
        if value and not value.startswith("https://"):
            raise ValueError("주소는 https:// 로 시작해야 합니다")
        return value

    @property
    def elsewhere(self) -> bool:
        """저장소 밖에서 도는 프로그램인가."""
        return bool(self.admin or self.client)

    @property
    def one_door(self) -> bool:
        """관리자와 고객이 **같은 주소**로 들어가는가.

        프로그램마다 갈래가 다르다. 주소로 가르는 것(`?admin=1`)도 있고,
        **넣는 키로** 가르는 것도 있다 — 뒤쪽은 주소가 하나다.

        그때 버튼을 둘로 두면 똑같은 것이 두 개 있는 셈이라, 누른 사람이
        «왜 같은 화면이 뜨지» 하게 된다. 화면이 그 차이를 말해야 한다.
        """
        return bool(self.admin) and self.admin == self.client


class ProgramManifest(BaseModel):
    """프로그램 하나의 전체 정의."""

    model_config = {"extra": "forbid"}

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", description="폴더명과 같게 쓴다")
    number: int = Field(ge=1, description="대시보드 표시 번호")
    name: str
    tagline: str = ""
    status: Status = "wip"
    #: 값이 있으면 **실행을 막고** 그 이유를 화면에 보여 준다.
    #:
    #: `status` 와 다르다. `status` 는 상품이 어디까지 왔는지고, 이건
    #: "지금 돌리지 마세요" 다. 손보는 중인 프로그램을 실수로 돌려서
    #: 산출물이 덮이거나 바깥 API 를 부르는 일을 막는다.
    #:
    #: 한 줄로 **왜** 막았는지 적는다. 이유 없이 막으면 나중에 자기도
    #: 왜 안 되는지 모른다.
    paused: str = Field(default="", description="비면 정상. 값이 있으면 실행을 막고 그 이유를 보여 준다")
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
    requirements: Requirements = Field(default_factory=Requirements)
    #: 저장소 밖에서 도는 프로그램이면 그 진짜 주소. 비밀번호는 안 담는다.
    live: LiveSite = Field(default_factory=LiveSite)

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

    @property
    def blocked(self) -> bool:
        """지금 돌리면 안 되는 프로그램인가."""
        return bool(self.paused.strip())

    @property
    def runs_at_home(self) -> bool:
        """집 컴퓨터에서 그대로 도는가."""
        return self.requirements.home_pc == "yes"

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
