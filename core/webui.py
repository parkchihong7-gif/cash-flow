"""웹 화면 정의 — **[관리자모드] / [클라이언트 모드] 두 벌.**

왜 따로 두는가
--------------

통합 대시보드의 '테스트' 탭은 *내가 프로그램을 돌려 보는* 자리다. 버튼 하나로
정해진 입력을 돌린다. 그것만으로는 **팔기 전에 고칠 곳을 못 찾는다.**
값을 바꿔 가며 눌러 봐야 어디가 불편한지 나온다.

그래서 화면을 두 벌 만든다.

* **관리자 모드** — 내가 본다. 설정·파일·실제 실행·로그·산출물이 다 보인다
* **클라이언트 모드** — 산 사람이 본다. 그 사람이 할 일만 보인다

둘을 한 화면에 섞으면 안 된다. 섞으면 고객이 건드리면 안 되는 값을 건드리고,
나는 내가 필요한 걸 못 찾는다. **같은 프로그램의 다른 얼굴**로 둔다.

2·3차 수정을 전제로 한 구조
---------------------------

이 파일은 **화면의 뼈대만** 정의한다. 실제 모양은 세 겹으로 정해진다.

1. `default_webui(program)` — `program.yaml` 만 보고 만드는 기본 화면.
   아무것도 안 해도 16종 전부 화면이 뜬다
2. `products/<상품>/webui.py` 의 `build(program, ctx)` — 상품이 자기 화면을
   직접 정의한다. 있으면 1번을 덮어쓴다
3. 그 안에서 `default_webui()` 를 불러 일부만 바꿔도 된다

2차·3차에 특정 상품만 갈아끼워도 나머지가 흔들리지 않는다.
**껍데기(뒤로가기·모드 전환·실행 버튼)는 공용이라 한 번 고치면 전부 반영된다.**
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "Field", "Panel", "WebUI", "Table", "Note", "MODES", "MODE_LABEL",
    "default_webui", "generator_webui", "load_webui", "load_handler",
    "field_from_setting", "yaml_input_panel", "outputs_panel",
    "write_yaml_fields", "read_yaml_fields", "load_console",
]

MODES = ("admin", "client")

MODE_LABEL = {"admin": "관리자 모드", "client": "클라이언트 모드"}

#: 상품 폴더에서 찾는 화면 정의 파일.
WEBUI_FILENAME = "webui.py"

#: 이 종류는 `<input type=...>` 로 그대로 나간다.
INPUT_KINDS = {"text": "text", "number": "number", "date": "date", "password": "password"}


@dataclass
class Field:
    """입력 한 칸."""

    key: str
    label: str
    kind: str = "text"          # text / textarea / number / select / boolean / date / info
    default: Any = ""
    options: list[str] = field(default_factory=list)
    help: str = ""
    placeholder: str = ""
    required: bool = False
    rows: int = 6
    #: 관리자만 봐야 하는 값인가. 클라이언트 화면에서는 빠진다.
    admin_only: bool = False

    @property
    def input_type(self) -> str:
        return INPUT_KINDS.get(self.kind, "text")

    @property
    def shown_default(self) -> str:
        if isinstance(self.default, bool):
            return "1" if self.default else ""
        return "" if self.default is None else str(self.default)


@dataclass
class Table:
    """화면에 그릴 표. **상품이 HTML 을 손으로 쓰지 않게** 하려고 둔다.

    손으로 쓴 HTML 은 이스케이프를 빠뜨리기 쉽고, 나중에 껍데기 모양을 바꿀 때
    상품마다 따로 고쳐야 한다.
    """

    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    #: 줄마다 붙일 색. 비우거나 "" 면 기본. ok / warn / bad
    tones: list[str] = field(default_factory=list)
    note: str = ""
    #: 오른쪽 정렬할 열 번호(0부터). 숫자 열에 쓴다.
    numeric: list[int] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.rows

    def tone_of(self, index: int) -> str:
        return self.tones[index] if index < len(self.tones) else ""


@dataclass
class Note:
    """짚어 줄 한 줄. 과락 경고처럼 **맨 위에 와야 하는 것**에 쓴다."""

    title: str
    body: str = ""
    tone: str = ""          # "" / ok / warn / bad

    @property
    def mark(self) -> str:
        return {"ok": "✓", "warn": "⚠", "bad": "✗"}.get(self.tone, "·")


@dataclass
class Panel:
    """화면의 한 덩어리. 카드 하나로 그려진다."""

    key: str
    title: str
    intro: str = ""
    fields: list[Field] = field(default_factory=list)
    #: 이 패널의 버튼. 비우면 버튼 없는 설명 카드가 된다.
    action: str = ""
    action_label: str = "실행"
    #: 'dry' 면 모의 실행, 'real' 이면 실제 실행, '' 면 실행이 아님.
    run_mode: str = ""
    note: str = ""
    tone: str = ""              # "" / ok / warn / bad

    #: 계산해서 보여 줄 것들. 입력 칸 아래에 그려진다.
    notes: list[Note] = field(default_factory=list)
    table: "Table | None" = None
    lines: list[str] = field(default_factory=list)
    #: 파일 내려받기 링크 (라벨, 경로).
    downloads: list[tuple[str, str]] = field(default_factory=list)

    @property
    def runs(self) -> bool:
        return bool(self.run_mode)

    @property
    def custom_action(self) -> str:
        """`do:이름` 꼴이면 그 이름. 상품이 직접 처리하는 동작이다."""
        return self.action[3:] if self.action.startswith("do:") else ""

    @property
    def form_path(self) -> str:
        """이 패널의 폼이 갈 주소 조각."""
        name = self.custom_action
        return f"do/{name}" if name else self.action


@dataclass
class WebUI:
    """프로그램 한 개의 화면 두 벌."""

    program_id: str
    title: str
    admin: list[Panel] = field(default_factory=list)
    client: list[Panel] = field(default_factory=list)
    #: 클라이언트 화면 맨 위에 두는 한 문단. 산 사람이 처음 보는 글이다.
    client_intro: str = ""
    admin_intro: str = ""
    #: 상품이 직접 만든 화면인가 (2·3차에서 채워진다).
    custom: bool = False

    def panels(self, mode: str) -> list[Panel]:
        return self.admin if mode == "admin" else self.client

    def intro(self, mode: str) -> str:
        return self.admin_intro if mode == "admin" else self.client_intro


def field_from_setting(spec) -> Field:
    """`program.yaml` 의 설정 한 줄을 입력 칸으로."""
    kind = spec.type
    if kind == "boolean":
        kind = "boolean"
    return Field(
        key=spec.key,
        label=spec.label,
        kind=kind,
        default=spec.default,
        options=list(spec.options),
        help=spec.help,
    )


def default_webui(program) -> WebUI:
    """`program.yaml` 만 보고 만드는 기본 화면.

    상품이 자기 화면을 안 만들었어도 **16종 전부 뜬다.** 모양은 수수하지만
    실제로 돌아가고, 값도 바뀐다. 2·3차에서 상품별로 갈아끼운다.
    """
    run_spec = program.run

    # ---- 관리자 모드 ----
    admin: list[Panel] = []

    if run_spec is not None:
        admin.append(Panel(
            key="run",
            title="돌려 보기",
            intro="입력 파일을 고르고 눌러 보세요. **모의 실행은 돈이 들지 않습니다.**",
            fields=[Field(
                key="input_path", label="입력 파일",
                kind="text", default=run_spec.input_file,
                help="프로그램 폴더 기준 상대 경로입니다. 비우면 기본값을 씁니다.",
                placeholder=run_spec.input_file,
            )],
            action="run", action_label="모의 실행", run_mode="dry",
            note="실제 실행은 아래 '실제로 돌리기' 에 있습니다. API 비용이 듭니다.",
        ))
        if run_spec.command:
            admin.append(Panel(
                key="run_real",
                title="실제로 돌리기",
                intro="외부 API 를 부릅니다. **비용이 듭니다.**",
                fields=[Field(
                    key="input_path", label="입력 파일",
                    kind="text", default=run_spec.input_file,
                )],
                action="run", action_label="실제 실행", run_mode="real",
                tone="warn",
            ))

    if program.settings:
        admin.append(Panel(
            key="settings",
            title="설정",
            intro="값을 바꾸고 저장하면 다음 실행부터 적용됩니다.",
            fields=[field_from_setting(spec) for spec in program.settings],
            action="settings", action_label="저장",
        ))

    # 편집할 파일 목록은 껍데기(app_shell.html)가 직접 그린다. 여기서 또
    # 만들면 같은 카드가 두 번 나온다.

    # ---- 클라이언트 모드 ----
    client: list[Panel] = []
    if run_spec is not None:
        client.append(Panel(
            key="run",
            title="만들기",
            intro="아래 버튼을 누르면 결과물이 만들어집니다.",
            fields=[],
            action="run", action_label="만들기", run_mode="dry",
        ))

    # 고객이 바꿔도 되는 설정만 골라 준다. 키·모델 같은 것은 뺀다.
    safe = [spec for spec in program.settings
            if not any(hint in spec.key.upper()
                       for hint in ("KEY", "TOKEN", "SECRET", "MODEL", "PASSWORD"))]
    if safe:
        client.append(Panel(
            key="settings",
            title="내 설정",
            intro="바꾸셔도 되는 값입니다.",
            fields=[field_from_setting(spec) for spec in safe],
            action="settings", action_label="저장",
        ))

    return WebUI(
        program_id=program.id,
        title=program.name,
        admin=admin,
        client=client,
        admin_intro=(
            f"**{program.name}** 의 관리자 화면입니다. "
            f"팔기 전에 여기서 값을 바꿔 가며 돌려 보고 고칠 곳을 찾으세요."),
        client_intro=program.tagline or f"{program.name} 입니다.",
    )


def _product_module(program):
    """상품 폴더의 `webui.py` 를 싣는다. 없거나 깨졌으면 None."""
    path = Path(program.directory) / WEBUI_FILENAME
    if not path.is_file():
        return None
    module_name = f"webui_{program.id.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_handler(program):
    """상품이 자기 동작을 처리하는 함수. 규격은 이렇다.

        def handle(program, ctx, action, form) -> str
            # 돌려주는 값은 화면으로 돌아갈 때 붙일 질의 문자열.
            # 예: "saved=1" 또는 "error=무엇이 잘못됐는지"

    없으면 None. 그러면 그 동작은 거절된다.
    """
    try:
        module = _product_module(program)
    except Exception:
        return None
    return getattr(module, "handle", None) if module else None


def load_console(program, ctx: dict | None = None):
    """상품이 자기 운영 콘솔을 정의해 뒀으면 그것을.

        # products/<상품>/webui.py
        def console(program, ctx):
            return Console(...)

    없으면 None 을 돌려준다. 부르는 쪽이 `WebUI` 를 콘솔로 감싸므로,
    **상품이 아무것도 안 해도 화면은 뜬다.** 콘솔을 정의한 상품부터 차례로
    깊어진다 — 16종을 한꺼번에 갈아엎지 않아도 되게 하려는 것이다.
    """
    if not (Path(program.directory) / WEBUI_FILENAME).is_file():
        return None
    try:
        module = _product_module(program)
        builder = getattr(module, "console", None)
        if builder is None:
            return None
        return builder(program, ctx or {})
    except Exception as exc:       # 콘솔 하나가 깨져도 나머지는 떠야 한다
        from core.console import Console, Tab
        broken = Console(
            program_id=program.id, title=program.name,
            tabs=[Tab(key="work", label="작업", icon="📋", panels=[Panel(
                key="broken", title="이 상품의 콘솔을 불러오지 못했습니다",
                intro=f"`{WEBUI_FILENAME}` 의 `console()` 에서 오류가 났습니다.",
                note=str(exc), tone="bad")])],
        )
        return broken


def load_webui(program, ctx: dict | None = None) -> WebUI:
    """상품이 자기 화면을 만들어 뒀으면 그것을, 아니면 기본 화면을.

    상품 쪽 규격은 이렇다.

        # products/<상품>/webui.py
        def build(program, ctx):
            ...
            return WebUI(...)

    `ctx` 로는 DB 나 지금 설정값 같은 것을 넘긴다. 상품이 안 쓰면 그만이다.
    """
    if not (Path(program.directory) / WEBUI_FILENAME).is_file():
        return default_webui(program)

    try:
        module = _product_module(program)
        builder: Callable = getattr(module, "build")
        result = builder(program, ctx or {})
    except Exception as exc:  # 상품 하나가 깨져도 나머지 화면은 떠야 한다
        broken = default_webui(program)
        broken.admin.insert(0, Panel(
            key="broken", title="이 상품의 전용 화면을 불러오지 못했습니다",
            intro=f"`{WEBUI_FILENAME}` 에서 오류가 났습니다. 기본 화면으로 대신 띄웁니다.",
            note=str(exc), tone="bad",
        ))
        return broken

    if not isinstance(result, WebUI):
        return default_webui(program)
    result.custom = True
    return result


# ─────────────────────────────────────────────────────────────────────
# 생성기 상품용 공통 화면
#
# 1~6·9번(퍼널·후킹·전자책·강의·크몽카피·n8n·노션)은 하는 일의 모양이 같다.
#
#     입력 파일(yaml)을 채운다 → 돌린다 → 산출물을 본다
#
# 상품마다 다른 것은 **입력 칸**뿐이다. 그래서 껍데기를 여기 한 번 만들고
# 상품은 칸만 넘긴다. 2·3차에 화면 모양을 바꿀 때도 여기만 고치면 일곱 종이
# 같이 바뀐다.
# ─────────────────────────────────────────────────────────────────────

def yaml_input_panel(title: str, intro: str, fields: list[Field],
                     action: str = "do:save", label: str = "저장하기") -> Panel:
    """입력 파일을 채우는 패널."""
    return Panel(key="input", title=title, intro=intro, fields=fields,
                 action=action, action_label=label)


def outputs_panel(program, latest: list[tuple[str, str]] | None = None) -> Panel:
    """산출물 설명 + 최근에 만든 것 링크."""
    rows = [[item.label, f"`{item.path}`", item.description]
            for item in program.outputs]
    return Panel(
        key="outputs", title="나오는 것",
        table=Table(headers=["무엇", "어디에", "설명"], rows=rows),
        downloads=latest or [],
        note="산출물은 `outputs/` 폴더에 쌓입니다.")


def generator_webui(program, input_fields: list[Field], *,
                    admin_intro: str = "", client_intro: str = "",
                    input_title: str = "무엇을 만들까요",
                    input_intro: str = "",
                    client_fields: list[Field] | None = None,
                    extra_admin: list[Panel] | None = None,
                    latest: list[tuple[str, str]] | None = None) -> WebUI:
    """입력 → 생성 → 산출물 꼴의 상품에 쓰는 공통 화면.

    Args:
        input_fields: 관리자 화면의 입력 칸.
        client_fields: 고객 화면의 입력 칸. 비우면 `input_fields` 에서
            `admin_only` 를 뺀 것을 쓴다.
    """
    run_admin = Panel(
        key="run", title="만들어 보기",
        intro="**모의 실행은 Claude 를 부르지 않아 비용이 0원입니다.** "
              "값이 제대로 들어갔는지 먼저 이걸로 보세요.",
        action="run", action_label="모의 실행", run_mode="dry",
        note="실제 실행은 아래에 있습니다. API 비용이 듭니다.")
    run_real = Panel(
        key="run_real", title="실제로 만들기",
        intro="Claude 를 부릅니다. **비용이 듭니다.**",
        action="run", action_label="실제 실행", run_mode="real", tone="warn")

    admin = [
        yaml_input_panel(input_title, input_intro, input_fields),
        run_admin,
        run_real,
        outputs_panel(program, latest),
    ]
    if extra_admin:
        admin += extra_admin

    shown = client_fields if client_fields is not None else [
        field for field in input_fields if not field.admin_only]
    client = [
        yaml_input_panel(input_title, input_intro, shown),
        Panel(key="run", title="만들기",
              intro="누르시면 결과물이 만들어집니다.",
              action="run", action_label="만들기", run_mode="dry"),
        outputs_panel(program, latest),
    ]

    return WebUI(
        program_id=program.id, title=program.name,
        admin=admin, client=client,
        admin_intro=admin_intro or f"**{program.name}** 의 관리자 화면입니다.",
        client_intro=client_intro or (program.tagline or program.name),
    )


def read_yaml_fields(path) -> dict:
    """입력 파일을 읽는다. 없거나 깨졌으면 빈 dict."""
    import yaml as _yaml

    path = Path(path)
    if not path.is_file():
        return {}
    try:
        return _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def write_yaml_fields(path, form: dict, *, int_keys: tuple = (),
                      list_keys: tuple = (), required: tuple = (),
                      allowed: tuple = ()) -> str:
    """폼 값을 입력 yaml 에 합쳐 저장한다.

    생성기 상품 일곱 종이 똑같이 하는 일이라 한 곳에 모았다. 돌려주는 값은
    화면에 띄울 질의 문자열이다.

    Args:
        int_keys: 숫자로 바꿀 키.
        list_keys: 줄바꿈으로 나눠 목록으로 만들 키.
        required: 비면 거절할 키.
        allowed: 이 키들만 받는다. 비우면 폼에 온 것을 다 받는다.
    """
    import yaml as _yaml

    path = Path(path)
    payload = read_yaml_fields(path)

    for key in required:
        if not str(form.get(key) or "").strip():
            return f"error={key} 를 적어 주세요"

    for key, raw in form.items():
        if allowed and key not in allowed:
            continue
        text = str(raw).strip()
        if key in int_keys:
            if text == "":
                continue
            try:
                payload[key] = int(float(text))
            except ValueError:
                return f"error={key} 는 숫자로 적어 주세요"
        elif key in list_keys:
            payload[key] = [line.strip() for line in text.splitlines() if line.strip()]
        else:
            payload[key] = text

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return "saved=저장했습니다. 아래에서 돌려 보세요"
