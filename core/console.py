"""운영 콘솔 — **16종 공통 뼈대.**

왜 화면을 다시 짜는가
---------------------

1차로 만든 `/apps/<상품>/<모드>` 는 **입력 칸 + [실행] 버튼** 한 장이었다.
프로그램을 한 번 돌려 보기에는 충분하지만, 매일 여는 자리로는 틀렸다.
사용자가 이미 쓰고 있는 관리자 세 개를 뜯어 보니 전부 같은 모양이었다.

* 유튜브 자동 제작 (`admin\\MANUAL.html`) — 12개 탭, 왼쪽 메뉴
* 공인중개사 기출문제 — 키 발급·배포 중심, `?admin=1`
* maim 네이버 블로그 — 홈 / 관리자 설정 / 발행 이력

셋 다 **일하는 자리가 여러 개**고, 왼쪽에서 골라 들어간다. 한 장짜리가 아니다.

무엇을 빌리고 무엇을 빌리지 않는가
----------------------------------

빌리는 것은 **문법**이다. 왼쪽 탭, 위쪽 상태 타일, 오늘 할 일, 손으로 할 일,
자동 실행표, 문제 해결표. 이건 업종과 상관없이 '운영 화면' 이면 다 필요하다.

빌리지 않는 것은 **내용**이다. 컨퍼런스 관리자에 '초청 현황·비자·정산' 탭이
있다고 해서 공인중개사 대시보드에 그걸 넣으면 안 된다. 공인중개사에는 '회차별
정답률·단원별 약점' 이 들어가야 한다. **탭의 이름과 개수는 그 사업이 정한다.**

그래서 이 파일에는 업종 이야기가 한 줄도 없다. 탭의 내용은 상품이 채운다.

관리자 / 클라이언트
-------------------

같은 콘솔을 두 번 그린다. 클라이언트 화면은 **관리자 전용 탭과 칸만 빠진 것**
이고, 나머지는 똑같다. 화면을 따로 만들면 반드시 한쪽만 고치게 되고, 그때부터
"고객이 보는 화면은 다르더라" 가 시작된다.

세 층으로 나뉘는 주인
---------------------

* **메인 관리자** — 통합 대시보드. 16종을 다 본다. 파는 사람
* **프로그램 관리자** — 그 프로그램을 산 사람. **자기 것 하나만** 본다
* **클라이언트** — 산 사람의 고객. 결과만 본다

이 파일이 그리는 것은 아래 둘이다. 맨 위는 통합 대시보드가 따로 그린다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.webui import MODE_LABEL, Panel

__all__ = [
    "Stat", "Tab", "Todo", "ManualTask", "Trouble", "FileLoc", "Console",
    "from_webui", "add_standard_tabs", "tabs_from", "generator_console",
    "STANDARD_GROUP",
    "STANDARD_TABS",
]

#: 공통 탭이 묶이는 자리. 상품 고유 탭은 이 위에 온다.
STANDARD_GROUP = "운영"


@dataclass
class Stat:
    """위쪽 상태 타일 한 개.

    숫자만 크게 띄우고 끝내지 않는다. `hint` 로 **그래서 뭘 해야 하는지**를
    같이 적는다. 숫자만 보여 주는 화면은 며칠 지나면 아무도 안 본다.
    """

    label: str
    value: str
    unit: str = ""
    tone: str = ""              # "" / ok / warn / bad
    hint: str = ""
    #: 눌렀을 때 갈 탭.
    tab: str = ""

    @property
    def shown(self) -> str:
        return f"{self.value}{self.unit}"


@dataclass
class Todo:
    """오늘 할 일 한 줄 (유튜브 매뉴얼의 '매일 하는 일 5분')."""

    text: str
    detail: str = ""
    tab: str = ""
    admin_only: bool = False
    #: 사람 손이 꼭 필요한 일인가. 표시를 달리한다.
    by_hand: bool = False


@dataclass
class ManualTask:
    """프로그램이 대신 못 해 주는 일과 **그 이유.**

    이유를 안 적으면 "왜 자동이 아니냐" 는 문의가 계속 온다. 유튜브 매뉴얼은
    `API 미지원`, `OAuth 앱이 미감사` 처럼 이유를 또박또박 적어 두었고,
    그래서 사용자가 납득하고 손으로 한다. 같은 표를 16종 전부에 둔다.
    """

    task: str
    where: str
    why: str
    #: 나중에 자동이 될 수 있는 일인가. 있으면 조건을 적는다.
    someday: str = ""


@dataclass
class Trouble:
    """증상 → 조치. 사람이 당황했을 때 읽는 표라 문장을 짧게 쓴다."""

    symptom: str
    fix: str


@dataclass
class FileLoc:
    """무엇이 어디에 있는가."""

    what: str
    where: str
    note: str = ""


@dataclass
class Tab:
    """일하는 자리 하나. 왼쪽 메뉴의 한 줄."""

    key: str
    label: str
    icon: str = ""
    group: str = ""
    intro: str = ""
    panels: list[Panel] = field(default_factory=list)
    #: 관리자만 들어가는 탭. 클라이언트 화면에서는 메뉴에서도 빠진다.
    admin_only: bool = False
    #: 이 탭에서 자주 누르는 버튼 설명 (유튜브 매뉴얼 3열).
    common_buttons: str = ""
    #: 패널이 아니라 정해진 표를 그리는 탭. 아래 STANDARD_TABS 의 key.
    render: str = ""

    @property
    def title(self) -> str:
        return f"{self.icon} {self.label}".strip()


@dataclass
class Console:
    """프로그램 한 개의 운영 화면."""

    program_id: str
    title: str
    subtitle: str = ""
    tabs: list[Tab] = field(default_factory=list)
    stats: list[Stat] = field(default_factory=list)
    todos: list[Todo] = field(default_factory=list)
    manual_tasks: list[ManualTask] = field(default_factory=list)
    troubles: list[Trouble] = field(default_factory=list)
    files: list[FileLoc] = field(default_factory=list)
    #: 화면 맨 위 한 문단. 모드마다 다르다.
    admin_intro: str = ""
    client_intro: str = ""
    #: 상품이 직접 만든 콘솔인가.
    custom: bool = False

    # ---------------------------------------------------------- 모드별 추리기
    def for_mode(self, mode: str) -> "Console":
        """클라이언트 화면은 **관리자 것만 빠진 같은 화면.**

        따로 만들지 않는다. 따로 만들면 한쪽만 고치게 된다.
        """
        if mode == "admin":
            return self
        return Console(
            program_id=self.program_id,
            title=self.title,
            subtitle=self.subtitle,
            tabs=[self._strip(tab) for tab in self.tabs if not tab.admin_only],
            stats=[stat for stat in self.stats
                   if not self._hidden_tab(stat.tab)],
            todos=[todo for todo in self.todos if not todo.admin_only],
            manual_tasks=list(self.manual_tasks),
            troubles=list(self.troubles),
            files=[],                 # 고객에게 내 폴더 구조를 보여 줄 이유가 없다
            admin_intro=self.admin_intro,
            client_intro=self.client_intro,
            custom=self.custom,
        )

    def _hidden_tab(self, key: str) -> bool:
        if not key:
            return False
        return any(tab.key == key and tab.admin_only for tab in self.tabs)

    @staticmethod
    def _strip(tab: Tab) -> Tab:
        """탭은 남기되 관리자 전용 패널·칸은 덜어낸다."""
        panels = []
        for panel in tab.panels:
            if getattr(panel, "admin_only", False):
                continue
            fields = [f for f in panel.fields if not f.admin_only]
            if fields == panel.fields:
                panels.append(panel)
                continue
            panels.append(Panel(
                key=panel.key, title=panel.title, intro=panel.intro,
                fields=fields, action=panel.action,
                action_label=panel.action_label, run_mode=panel.run_mode,
                note=panel.note, tone=panel.tone, notes=list(panel.notes),
                table=panel.table, lines=list(panel.lines),
                downloads=list(panel.downloads),
            ))
        return Tab(key=tab.key, label=tab.label, icon=tab.icon, group=tab.group,
                   intro=tab.intro, panels=panels, admin_only=False,
                   common_buttons=tab.common_buttons)

    # -------------------------------------------------------------- 찾아보기
    def tab(self, key: str) -> Tab | None:
        for item in self.tabs:
            if item.key == key:
                return item
        return None

    def first_tab(self) -> Tab | None:
        return self.tabs[0] if self.tabs else None

    @property
    def groups(self) -> list[tuple[str, list[Tab]]]:
        """왼쪽 메뉴를 묶음 순서대로. 묶음 이름이 없으면 맨 앞에 둔다."""
        order: list[str] = []
        buckets: dict[str, list[Tab]] = {}
        for tab in self.tabs:
            name = tab.group or ""
            if name not in buckets:
                buckets[name] = []
                order.append(name)
            buckets[name].append(tab)
        return [(name, buckets[name]) for name in order]

    def intro(self, mode: str) -> str:
        return self.admin_intro if mode == "admin" else self.client_intro

    def mode_label(self, mode: str) -> str:
        return MODE_LABEL.get(mode, mode)

    @property
    def hand_todos(self) -> list[Todo]:
        return [todo for todo in self.todos if todo.by_hand]


def from_webui(program, webui, ctx=None) -> Console:
    """상품이 콘솔을 안 만들었어도 **화면은 뜬다.**

    기존 `WebUI` 의 패널을 그대로 한 탭에 담는다. 1차에서 만든 16종 화면이
    하나도 깨지지 않고 새 껍데기 안으로 들어온다. 상품이 자기 콘솔을 정의하면
    그쪽이 이긴다 — 2·3차 수정이 상품 단위로 끝나게 하려는 것이다.
    """
    panels = list(webui.admin)
    client_keys = {panel.key for panel in webui.client}
    for panel in panels:
        # 클라이언트 화면에 없던 패널은 관리자 전용으로 본다.
        if panel.key not in client_keys:
            setattr(panel, "admin_only", True)

    return Console(
        program_id=program.id,
        title=webui.title or program.name,
        subtitle=getattr(program, "one_liner", ""),
        tabs=[Tab(key="work", label="작업", icon="📋", panels=panels)],
        admin_intro=webui.admin_intro,
        client_intro=webui.client_intro,
        custom=False,
    )


# ─────────────────────────────────────────────────────── 16종이 다 갖는 탭
#: (key, 라벨, 아이콘, 관리자전용, 한 줄 설명)
STANDARD_TABS: tuple[tuple[str, str, str, bool, str], ...] = (
    ("hand", "손으로 할 일", "✋", False,
     "프로그램이 대신 못 하는 일과 **그 이유**입니다."),
    ("auto", "자동 실행", "🕒", False,
     "정해진 시각에 저절로 도는 일입니다."),
    ("keys", "접속키", "🔑", True,
     "1차키·2차키를 발급하고 회수합니다."),
    ("presets", "기본 세팅", "⚙️", True,
     "지금 값이 검증값과 같은지 봅니다. 한 번에 되돌릴 수 있습니다."),
    ("trouble", "문제 해결", "🛟", False,
     "증상을 찾아 그 줄대로 하시면 됩니다."),
    ("files", "파일 위치", "📁", True,
     "무엇이 어디에 있는지."),
)


def tabs_from(webui, spec: list[dict]) -> list[Tab]:
    """이미 만들어 둔 패널을 탭으로 **나누기만** 한다.

    대부분의 상품은 1차에서 만든 패널이 이미 옳다. 틀린 것은 그것들이 한 장에
    쏟아져 있다는 점뿐이다. 그래서 패널을 다시 짓지 않고 자리만 나눈다.
    데이터를 다시 읽지 않으니 **필드 이름을 잘못 짚을 일이 없다.**

    Args:
        webui: 상품의 `WebUI`. 관리자 패널 목록에서 골라 쓴다.
        spec: 탭 하나당 딕셔너리. `panels` 에 패널 key 를 순서대로 적는다.

            {"key": "run", "label": "돌리기", "icon": "▶",
             "group": "쓰는 자리", "intro": "...", "panels": ["run", "out"]}

    쓰지 않은 패널은 조용히 버려지지 않는다 — 마지막 탭에 모아 붙인다.
    한 번 만든 화면이 개편 중에 사라지는 일을 막기 위해서다.
    """
    by_key = {panel.key: panel for panel in webui.admin}
    client_keys = {panel.key for panel in webui.client}
    used: set[str] = set()
    tabs: list[Tab] = []

    for item in spec:
        keys = [key for key in item.get("panels", []) if key in by_key]
        used.update(keys)
        panels = [by_key[key] for key in keys]
        for panel in panels:
            # 클라이언트 화면에 없던 패널은 관리자 전용으로 본다.
            if panel.key not in client_keys:
                setattr(panel, "admin_only", True)
        tabs.append(Tab(
            key=item["key"], label=item["label"], icon=item.get("icon", ""),
            group=item.get("group", ""), intro=item.get("intro", ""),
            panels=panels, admin_only=item.get("admin_only", False),
            common_buttons=item.get("buttons", ""),
        ))

    leftover = [panel for panel in webui.admin if panel.key not in used]
    if leftover:
        tabs.append(Tab(key="etc", label="그 밖에", icon="📎",
                        group=STANDARD_GROUP, panels=leftover))
    return tabs


def default_files(program) -> list[FileLoc]:
    """`program.yaml` 만 보고 채우는 '무엇이 어디에' 표.

    상품이 따로 안 적어도 **프로그램 폴더·입력·산출물·설정**은 늘 알려 준다.
    파는 물건이라 고객이 "내가 만든 게 어디 갔냐" 고 물어 오는데, 그때마다
    사람이 답하면 그게 곧 인건비다.
    """
    rows = [FileLoc("프로그램 폴더", f"products/{program.id}/")]
    run = getattr(program, "run", None)
    if run is not None:
        if run.input_file:
            rows.append(FileLoc("입력 파일", f"products/{program.id}/{run.input_file}",
                                "여기를 고치면 결과가 달라집니다."))
        if run.output_dir:
            rows.append(FileLoc("산출물", f"products/{program.id}/{run.output_dir}/",
                                "돌릴 때마다 새 폴더가 생깁니다."))
    for item in getattr(program, "editable_files", []):
        rows.append(FileLoc(item.label or item.path,
                            f"products/{program.id}/{item.path}"))
    rows.append(FileLoc("설정·실행 기록", "data/dashboard.db",
                        "대시보드와 같은 파일을 씁니다. 접속키도 여기 들어갑니다."))
    return rows


def add_standard_tabs(console: "Console", program=None) -> "Console":
    """공통 탭을 뒤에 붙인다.

    상품이 자기 탭을 몇 개 만들든, **마지막 여섯 자리는 항상 같다.** 16종을
    번갈아 쓰는 사람이 매번 다른 곳을 뒤지지 않게 하려는 것이다. 자리를 외우게
    하는 편이 예쁘게 배치하는 것보다 낫다.

    내용이 없는 탭은 붙이지 않는다. 빈 탭이 있으면 '여기는 아직 안 만들었나'
    싶어 오히려 신뢰를 깎는다. 단, 접속키·기본 세팅은 늘 붙는다 — 내용이
    비어 있는 것 자체가 봐야 할 정보다.
    """
    # 파일 위치는 상품이 안 적어도 매니페스트에서 채울 수 있다. 비워 두면
    # '편집할 파일' 로 가는 길이 아예 사라져 기능 하나가 없어진 것처럼 된다.
    if program is not None and not console.files:
        console.files = default_files(program)

    has = {tab.key for tab in console.tabs}
    always = {"keys", "presets"}
    content = {
        "hand": bool(console.manual_tasks),
        "auto": True,
        "trouble": bool(console.troubles),
        "files": bool(console.files),
    }
    for key, label, icon, admin_only, intro in STANDARD_TABS:
        if key in has:
            continue
        if key not in always and not content.get(key, False):
            continue
        console.tabs.append(Tab(
            key=key, label=label, icon=icon, group=STANDARD_GROUP,
            intro=intro, admin_only=admin_only, render=key,
        ))
    return console


def generator_console(program, webui, *, input_label: str, input_icon: str,
                      output_label: str, output_icon: str, output_intro: str = "",
                      make_label: str = "만들기", make_intro: str = "",
                      todos=None, manual_tasks=None, troubles=None, files=None,
                      stats=None, admin_intro: str = "", client_intro: str = "",
                      extra_tabs=None) -> "Console":
    """Claude 를 한 번 불러 문서를 만드는 상품들의 공통 콘솔.

    일곱 상품(퍼널·후크·전자책·강의자료·크몽카피·노션템플릿·n8n)은 **정말로
    같은 모양**이다. 적고 → 만들고 → 받는다. 여기서 억지로 다른 구조를 만들면
    쓰는 사람만 헷갈린다. 그래서 뼈대는 나누고, **탭 이름과 내용은 상품이
    정한다** — 나오는 것이 랜딩 페이지인지 워드 원고인지는 전혀 다른 일이라
    같은 이름을 붙이면 안 된다.

    나중에 한 상품만 깊어지면 이 함수를 안 부르고 자기 `console()` 을 쓰면
    된다. 나머지 여섯은 흔들리지 않는다.
    """
    def pick(*keys):
        by_key = {panel.key: panel for panel in webui.admin}
        return [by_key[key] for key in keys if key in by_key]

    client_keys = {panel.key for panel in webui.client}
    for panel in webui.admin:
        if panel.key not in client_keys:
            setattr(panel, "admin_only", True)

    tabs = [
        Tab(key="input", label=input_label, icon=input_icon, group="적는 자리",
            intro="**여기 적은 것이 결과를 거의 다 정합니다.** 자세히 적을수록 "
                  "고칠 일이 줄어듭니다.",
            panels=pick("input", "tips")),
        Tab(key="make", label=make_label, icon="✨", group="만드는 자리",
            intro=make_intro or "**모의 실행은 뼈대만 만들고 비용이 0원입니다.** "
                                "모양을 먼저 보시고, 마음에 들면 실제로 만드세요.",
            panels=pick("run", "run_real")),
        Tab(key="out", label=output_label, icon=output_icon, group="받는 자리",
            intro=output_intro, panels=pick("outputs")),
    ]
    tabs += list(extra_tabs or [])

    return Console(
        program_id=program.id, title=program.name,
        subtitle=getattr(program, "tagline", ""),
        tabs=tabs,
        stats=list(stats or []),
        todos=list(todos or []),
        manual_tasks=list(manual_tasks or []),
        troubles=list(troubles or []),
        files=list(files or []),
        admin_intro=admin_intro or webui.admin_intro,
        client_intro=client_intro or webui.client_intro,
        custom=True,
    )
