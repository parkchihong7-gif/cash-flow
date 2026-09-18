"""8번 전용 웹 화면 — **값을 바꾸면 숫자가 바로 바뀐다.**

시뮬레이터는 값을 바꿔 가며 보는 게 전부인데, CLI 로는 파일을 고치고 명령을
다시 쳐야 한다. 그래서 화면에서 바로 바꾸게 한다.

맨 위에 **추정치라는 것**과 **근거**를 붙인다. 숫자가 그럴듯하면 사람은
그걸 약속으로 읽는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.webui import Field, Note, Panel, Table, WebUI          # noqa: E402

from income_sim.engine import DISCLAIMER, simulate               # noqa: E402
from income_sim.schema import load_all                           # noqa: E402

DEFAULT_MODEL = "agency_retainer"


def _models():
    return load_all()


def _current(ctx) -> str:
    picked = (ctx.get("settings") or {}).get("WEBUI_MODEL", "")
    models = _models()
    return picked if picked in models else (
        DEFAULT_MODEL if DEFAULT_MODEL in models else next(iter(models)))


def _won(value: float) -> str:
    return f"{value:,.0f}원"


def _result_panel(spec, overrides: dict) -> Panel:
    try:
        result = simulate(spec, overrides)
    except Exception as exc:
        return Panel(key="result", title="계산 결과", tone="bad",
                     notes=[Note("계산하지 못했습니다", str(exc), tone="bad")])

    rows = [[str(row.month), _won(row.revenue), _won(row.cost),
             _won(row.profit), _won(row.cumulative)] for row in result.rows]

    notes = [
        Note(f"12개월 순이익 {_won(result.total_profit)}",
             f"마지막 달 {_won(result.last_month_profit)} · "
             f"시간당 {_won(result.hourly)}"),
        Note("추정치입니다", DISCLAIMER, tone="warn"),
    ]
    if result.cumulative_breakeven:
        notes.insert(1, Note(f"{result.cumulative_breakeven}개월째에 본전",
                             f"초기비용 {_won(result.initial_cost)} 을 넘기는 시점입니다.",
                             tone="ok"))
    else:
        notes.insert(1, Note("12개월 안에 본전을 못 넘깁니다",
                             "가정을 바꿔 보시거나 초기비용을 줄여야 합니다.", tone="warn"))

    return Panel(
        key="result", title="계산 결과", notes=notes,
        table=Table(headers=["개월", "매출", "비용", "순이익", "누적"],
                    rows=rows, numeric=[0, 1, 2, 3, 4]),
        lines=list(spec.cautions))


def build(program, ctx) -> WebUI:
    models = _models()
    current = _current(ctx)
    spec = models[current]

    picker = Panel(
        key="pick", title="어떤 모델로 볼까요",
        intro="수익 구조마다 가정이 다릅니다. 고르시면 아래 칸이 바뀝니다.",
        fields=[Field("WEBUI_MODEL", "모델", "select", default=current,
                      options=sorted(models))],
        action="settings", action_label="이 모델로 보기")

    stored = ctx.get("settings") or {}
    fields = [
        Field(param.key, f"{param.label} ({param.unit})", "number",
              default=stored.get(param.key, param.default),
              help=param.help or param.source)
        for param in spec.params
    ]
    inputs = Panel(
        key="vars", title=f"{spec.name} — 가정",
        intro="**본인 숫자로 바꿔 보세요.** 기본값은 조사한 구간의 중간값입니다.",
        fields=fields, action="do:calc", action_label="이 값으로 계산")

    # 저장해 둔 값이 있으면 그걸로 계산한다. 화면을 다시 열어도 유지된다.
    keys = {param.key for param in spec.params}
    overrides: dict[str, float] = {}
    for key, value in stored.items():
        if key in keys:
            try:
                overrides[key] = float(value)
            except (TypeError, ValueError):
                continue
    result = _result_panel(spec, overrides)

    admin = [picker, inputs, result,
             Panel(key="run", title="보고서로 받기",
                   intro="여러 모델을 견주는 HTML 보고서를 만듭니다.",
                   action="run", action_label="보고서 만들기", run_mode="dry")]
    client = [
        Panel(key="pick", title="어떤 수익 구조를 보실까요",
              fields=picker.fields, action="settings", action_label="보기"),
        inputs, result,
    ]

    return WebUI(
        program_id=program.id, title=program.name,
        admin=admin, client=client,
        admin_intro="가정을 바꿔 가며 견주는 도구입니다. **수익을 보장하지 않습니다.**",
        client_intro="숫자를 바꿔 가며 **얼마나 벌 수 있을지 가늠**해 보세요. "
                     "추정치이고 보장이 아닙니다.")


def handle(program, ctx, action: str, form: dict) -> str:
    if action != "calc":
        return "error=모르는 동작입니다"
    database = ctx.get("db")
    saved = 0
    for key, value in form.items():
        text = str(value).strip()
        if not text:
            continue
        try:
            float(text)
        except ValueError:
            return f"error={key} 는 숫자로 적어 주세요"
        if database is not None:
            database.set_program_setting(program.id, key, text)
            saved += 1
    return f"saved={saved}개 값을 바꿔 계산했습니다"
