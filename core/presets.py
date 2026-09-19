"""검증값 기본 세팅 — **16종 공통 표준.**

이 규격도 지어낸 것이 아니다. 사용자가 이미 쓰고 있는 유튜브 자동 제작 관리자
(`admin\\MANUAL.html`, 12개 탭) 의 약속을 그대로 옮겼다.

    모든 설정 탭 맨 위에는 ☑ 기본 세팅(검증값) 사용 체크가 있습니다.
    초록이면 지금 값이 검증된 기본값과 같고, 노랑이면 사장님이 바꾼 상태입니다.
    체크를 다시 켜면 기본값으로 돌아갑니다.

왜 이게 필요한가
----------------

설정을 만지다 보면 **어디를 건드렸는지 잊는다.** 그러면 프로그램이 이상해졌을 때
원인을 못 찾고, 결국 "처음부터 다시" 가 된다. 파는 물건에서 이 일이 나면
그날로 환불이다.

그래서 값마다 두 가지를 같이 들고 다닌다. **지금 값**과 **검증된 값.** 둘이
다르면 화면이 노랗게 뜨고, 되돌리는 버튼이 그 자리에 있다. 되돌리기가 한 번에
되면 사람이 겁내지 않고 만져 본다. 만져 봐야 자기 것이 된다.

무엇이 '검증된 값' 인가
-----------------------

`program.yaml` 의 `settings[].default` 다. 상품을 만들 때 실제로 돌려 보고
정한 값이라, 최소한 여기서는 동작한다는 뜻이다. 그 이상의 보장은 하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["PresetRow", "PresetState", "collect", "restore_values",
           "GREEN", "YELLOW"]

GREEN = "ok"          # 검증값 그대로
YELLOW = "warn"       # 사람이 바꾼 상태


def _same(current, default) -> bool:
    """두 값이 같은가. YAML 을 거치면 타입이 흔들려서 문자열로 견준다.

    `3` 과 `"3"`, `True` 와 `"1"` 은 사람 눈에 같은 값이다. 타입이 다르다고
    노랗게 띄우면 아무것도 안 바꿨는데 바꿨다고 나온다 — 경고가 무의미해진다.
    """
    if isinstance(default, bool) or isinstance(current, bool):
        return _truthy(current) == _truthy(default)
    return _text(current) == _text(default)


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "켜기", "예"}


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


@dataclass
class PresetRow:
    """설정 한 줄의 지금 상태."""

    key: str
    label: str
    current: str
    default: str
    help: str = ""

    @property
    def changed(self) -> bool:
        return not _same(self.current, self.default)

    @property
    def tone(self) -> str:
        return YELLOW if self.changed else GREEN

    @property
    def label_text(self) -> str:
        return "바꿈" if self.changed else "검증값"

    @property
    def shown_current(self) -> str:
        return _text(self.current) or "(비어 있음)"

    @property
    def shown_default(self) -> str:
        return _text(self.default) or "(비어 있음)"


@dataclass
class PresetState:
    """한 프로그램의 설정 전체."""

    program_id: str
    rows: list[PresetRow] = field(default_factory=list)

    @property
    def changed(self) -> list[PresetRow]:
        return [row for row in self.rows if row.changed]

    @property
    def on_default(self) -> bool:
        """☑ 기본 세팅(검증값) 사용 — 체크 상태."""
        return not self.changed

    @property
    def tone(self) -> str:
        return GREEN if self.on_default else YELLOW

    @property
    def summary(self) -> str:
        if not self.rows:
            return "설정할 값이 없습니다."
        if self.on_default:
            return f"{len(self.rows)}개 값이 모두 검증값 그대로입니다."
        names = ", ".join(row.label for row in self.changed[:3])
        more = f" 외 {len(self.changed) - 3}개" if len(self.changed) > 3 else ""
        return f"{names}{more} 을(를) 바꿔 두셨습니다."

    def defaults(self) -> dict[str, str]:
        """되돌릴 때 쓸 값들."""
        return {row.key: _text(row.default) for row in self.rows}


def collect(program, saved: dict | None = None) -> PresetState:
    """지금 값과 검증값을 나란히 놓는다.

    Args:
        program: `program.yaml` 을 읽은 프로그램.
        saved: 대시보드에 저장된 값. 없는 키는 검증값을 쓴 것으로 본다.
    """
    saved = saved or {}
    rows = [
        PresetRow(
            key=spec.key,
            label=spec.label,
            current=saved.get(spec.key, spec.default),
            default=spec.default,
            help=spec.help,
        )
        for spec in getattr(program, "settings", [])
    ]
    return PresetState(program_id=program.id, rows=rows)


def restore_values(program, keys: list[str] | None = None) -> dict[str, str]:
    """검증값으로 되돌릴 값을 만든다.

    Args:
        keys: 되돌릴 설정. 비우면 **모든 탭 기본 세팅으로** (매뉴얼의 그 버튼).
    """
    state = collect(program)
    if keys is None:
        return state.defaults()
    wanted = set(keys)
    return {key: value for key, value in state.defaults().items() if key in wanted}
