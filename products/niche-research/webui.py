"""12번 전용 웹 화면 — **안 돌린 날이 보여야 한다.**

이 상품의 전제는 "매일 찍어 쌓는다" 인데, 안 쌓이고 있다는 걸 알아채기가
어렵다. 두 달 뒤 보고서를 열고 나서야 듬성듬성한 걸 본다. 그래서 화면 맨
위에 **며칠치가 쌓였고 어느 날이 비었는지**를 띄운다.

쿼터도 같이 보여 준다. 하루 80개 키워드가 상한이라 목록을 늘리다 보면
말없이 잘린다.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.webui import Field, Note, Panel, Table, WebUI          # noqa: E402

from niche.metrics import analyze_all                            # noqa: E402
from niche.quota import (                                        # noqa: E402
    DEFAULT_KEYWORD_LIMIT, UNITS_PER_KEYWORD, DAILY_UNITS,
)
from niche.store import Store                                    # noqa: E402

KEYWORDS = BASE_DIR / "keywords.txt"
DB = BASE_DIR / "niche.db"
MIN_DAYS = 3


def _keywords() -> list[str]:
    if not KEYWORDS.is_file():
        return []
    return [line.strip() for line in KEYWORDS.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def _store() -> Store | None:
    return Store(DB) if DB.is_file() else None


def _state_notes(store) -> list[Note]:
    if store is None:
        return [Note("아직 한 번도 모으지 않았습니다",
                     "`--fixture` 로 샘플 자료를 넣어 흐름부터 보세요.", tone="warn")]
    counts = store.counts()
    days = counts["days"]
    notes = [Note(f"{days}일치 · 키워드 {counts['keywords']}개 · 영상 {counts['videos']:,}개",
                  "")]
    if days < MIN_DAYS:
        notes.append(Note(f"{MIN_DAYS}일치는 모여야 지표가 나옵니다",
                          "하루 이틀은 아무것도 안 보이는 게 정상입니다.", tone="warn"))
    else:
        notes.append(Note("지표를 계산할 수 있습니다",
                          "2주쯤 지나야 추이가 보입니다.", tone="ok"))

    dates = store.snapshot_dates()
    if len(dates) >= 2:
        from datetime import date as _date, timedelta
        first = _date.fromisoformat(dates[0])
        last = _date.fromisoformat(dates[-1])
        span = (last - first).days + 1
        missing = span - len(dates)
        if missing > 0:
            notes.append(Note(
                f"빈 날이 {missing}일 있습니다",
                "**거른 날은 영영 빕니다.** 유튜브는 지난 값을 돌려주지 않습니다. "
                "cron 이 살아 있는지 보세요.", tone="bad"))
    return notes


def _quota_panel(words: list[str]) -> Panel:
    count = len(words)
    units = count * UNITS_PER_KEYWORD
    over = count > DEFAULT_KEYWORD_LIMIT
    return Panel(
        key="quota", title="쿼터",
        notes=[
            Note(f"키워드 {count}개 = {units:,} 유닛 / 하루 {DAILY_UNITS:,} 유닛",
                 f"키워드 하나에 {UNITS_PER_KEYWORD} 유닛입니다 "
                 f"(search.list 100 + videos/channels).",
                 tone="bad" if over else "ok"),
            Note(f"하루 상한 {DEFAULT_KEYWORD_LIMIT}개",
                 "넘친 키워드는 버리지 않고 **다음 날 맨 앞에** 세웁니다."
                 if over else "여유가 있습니다.",
                 tone="warn" if over else ""),
        ],
        lines=["쿼터는 **태평양 시간 자정**에 초기화됩니다. 수집은 새벽에 거세요"])


def _gap_table(store) -> Table:
    if store is None or store.counts()["videos"] == 0:
        return Table(note="아직 모은 자료가 없습니다.")
    try:
        metrics = analyze_all(store)
    except Exception as exc:
        return Table(note=f"지표를 계산하지 못했습니다: {exc}")
    rows, tones = [], []
    for item in metrics[:12]:
        rows.append([item.keyword, f"{item.gap:,.1f}", str(item.videos),
                     f"{item.median_views:,}", f"{item.breakout_rate:.1f}%",
                     f"{item.shorts_ratio:.1f}%"])
        tones.append("ok" if item.entry_friendly else "")
    return Table(
        headers=["키워드", "공백 지수", "영상", "중앙값 조회", "소형 뚫림", "쇼츠"],
        rows=rows, tones=tones, numeric=[1, 2, 3, 4, 5],
        note="초록 줄 = 소형 채널이 뚫고 있는 키워드(성과율 20% 이상). "
             "**공백 지수보다 이쪽을 먼저 보세요.**")


def build(program, ctx) -> WebUI:
    words = _keywords()
    store = _store()

    state = Panel(key="state", title="쌓인 자료", notes=_state_notes(store))
    keywords = Panel(
        key="keywords", title="볼 키워드",
        intro="한 줄에 하나씩. **내가 만들 수 없는 주제의 공백은 내 공백이 아닙니다.**",
        fields=[Field("words", "키워드", "textarea",
                      default="\n".join(words), rows=8)],
        action="do:keywords", action_label="키워드 저장")
    gap = Panel(key="gap", title="공백이 큰 키워드", table=_gap_table(store))
    collect = Panel(
        key="collect", title="오늘 모으기",
        intro="유튜브 API 키가 없어도 **샘플 자료로** 흐름을 볼 수 있습니다.",
        action="run", action_label="모아서 보고서 만들기 (샘플)", run_mode="dry",
        note="실제 수집은 cron 으로 매일 새벽에 거는 것이 맞습니다. "
             "이 버튼은 확인용입니다.")
    nocopy = Panel(
        key="nocopy", title="이 도구가 하지 않는 것",
        lines=["특정 영상을 집어 \"이걸 따라 만드세요\" 라고 하지 않습니다",
               "조회수 높은 영상 목록을 보여 주지 않습니다",
               "채널 이름·영상 제목을 보고서에 싣지 않습니다",
               "조회수를 예측하지 않습니다"],
        notes=[Note("없는 것은 따라 만들 수 없습니다",
                    "Claude 에 영상 제목·채널명을 **주지 않습니다.** "
                    "입력에서부터 뺐습니다 (노아AI 전례).", tone="ok")])

    admin = [state, _quota_panel(words), keywords, gap, collect, nocopy]
    client = [state, gap,
              Panel(key="collect", title="보고서 받기",
                    action="run", action_label="보고서 만들기", run_mode="dry"),
              nocopy]

    return WebUI(
        program_id=program.id, title=program.name,
        admin=admin, client=client,
        admin_intro="**매일 안 돌리면 그날은 영영 빕니다.** 빈 날이 있으면 "
                    "맨 위에 알려 드립니다.",
        client_intro="유튜브에서 **공급이 비어 있는 자리**를 찾습니다. "
                     "특정 영상을 따라 만들라고 하지 않습니다.")


def handle(program, ctx, action: str, form: dict) -> str:
    if action != "keywords":
        return "error=모르는 동작입니다"
    words = [line.strip() for line in (form.get("words") or "").splitlines()
             if line.strip()]
    if not words:
        return "error=키워드를 한 줄에 하나씩 적어 주세요"
    KEYWORDS.write_text(
        "# 볼 키워드. 한 줄에 하나씩. # 로 시작하면 건너뜁니다.\n"
        + "\n".join(words) + "\n", encoding="utf-8")
    if len(words) > DEFAULT_KEYWORD_LIMIT:
        return (f"saved={len(words)}개 저장했습니다. 다만 하루 상한이 "
                f"{DEFAULT_KEYWORD_LIMIT}개라 나머지는 다음 날로 넘어갑니다")
    return f"saved=키워드 {len(words)}개를 저장했습니다"


# ══════════════════════════════════════════════════════════ 운영 콘솔
#
# 탭은 **니치를 찾는 일**에서 나온다. 매일 조금씩 모아서 쌓고, 쌓인 것으로
# 공백을 본다. 하루치만으로는 아무것도 못 본다는 것이 이 상품의 전제라,
# '쌓인 자료' 와 '오늘 모으기' 가 서로 다른 탭이다.
#
# '하지 않는 것' 탭을 굳이 남겨 두었다. 노아AI 가 '터진 영상 따라 만들기' 로
# 표절 논란을 부르고 서비스를 접은 전례가 있어, 이 도구가 무엇을 안 하는지를
# 사는 사람이 먼저 보게 해야 한다.

from core.console import (                                        # noqa: E402
    Console, FileLoc, ManualTask, Stat, Tab, Todo, Trouble, tabs_from,
)


def console(program, ctx) -> Console:
    ui = build(program, ctx)
    store = _store()
    words = _keywords()

    # getattr 로 슬쩍 넘기지 않는다. 없으면 없다고 화면에 적어야 한다.
    counts = store.counts() if store is not None else None
    stats = [Stat("보는 키워드", str(len(words)), "개", tab="keywords")]
    if counts is None:
        stats.append(Stat("쌓은 자료", "없음", tone="warn",
                          hint="아직 한 번도 모으지 않았습니다", tab="collect"))
    else:
        days = counts["days"]
        stats += [
            Stat("쌓은 날", str(days), "일",
                 tone="warn" if days < MIN_DAYS else "ok",
                 hint=f"{MIN_DAYS}일치는 모여야 지표가 나옵니다" if days < MIN_DAYS
                      else "지표를 계산할 수 있습니다",
                 tab="state"),
            Stat("모은 영상", f"{counts['videos']:,}", "개", tab="state"),
        ]

    return Console(
        program_id=program.id, title=program.name, subtitle=program.tagline,
        tabs=tabs_from(ui, [
            {"key": "state", "label": "쌓인 자료", "icon": "🗄", "group": "보는 자리",
             "intro": "**하루치로는 아무것도 못 봅니다.** 며칠 쌓여야 흐름이 나옵니다.",
             "panels": ["state"]},
            {"key": "gap", "label": "공백", "icon": "🕳", "group": "보는 자리",
             "intro": "찾는 사람에 견줘 **만든 사람이 적은** 자리입니다.",
             "panels": ["gap"]},
            {"key": "keywords", "label": "볼 키워드", "icon": "🔤", "group": "모으는 자리",
             "panels": ["keywords"]},
            {"key": "collect", "label": "오늘 모으기", "icon": "📥", "group": "모으는 자리",
             "intro": "하루 한 번이면 충분합니다. 더 눌러도 같은 날 자료가 덮일 뿐입니다.",
             "panels": ["collect", "quota"]},
            {"key": "nocopy", "label": "하지 않는 것", "icon": "🚫", "group": "보는 자리",
             "intro": "사시기 전에 **이 도구가 무엇을 안 하는지** 먼저 보세요.",
             "panels": ["nocopy"]},
        ]),
        stats=stats,
        todos=[
            Todo("오늘 자료 모으기", tab="collect",
                 detail="하루 한 번이면 됩니다. 쿼터를 아껴 쓰는 편이 오래 갑니다."),
            Todo("공백이 큰 키워드를 보고 **각도**를 정하기", tab="gap",
                 detail="키워드를 그대로 쓰지 마시고, 그 안에서 아직 아무도 안 다룬 "
                        "각도를 잡으세요."),
        ],
        manual_tasks=[
            ManualTask(
                task="영상 기획과 제작",
                where="직접",
                why="이 도구는 **어느 자리가 비었는지**까지만 말합니다. "
                    "무엇을 어떻게 만들지는 사람이 정합니다."),
            ManualTask(
                task="유튜브 API 키 발급",
                where="Google Cloud Console → YouTube Data API v3",
                why="키는 계정마다 발급받으셔야 합니다. 무료이고 하루 10,000 유닛을 "
                    "줍니다. 대신 키를 공유해 드릴 수는 없습니다."),
        ],
        troubles=[
            Trouble("공백 표가 비어 있다",
                    "자료가 아직 모자랍니다. **사흘 이상** 모으셔야 흐름이 나옵니다. "
                    "하루치로는 '지금 많다/적다' 밖에 말할 수 없습니다."),
            Trouble("오늘 더 못 모은다고 나온다",
                    "유튜브 API 하루 쿼터를 다 쓰셨습니다. **기다리시는 것이 맞습니다** — "
                    "재시도하면 다음 날 몫까지 깎입니다. 키워드 수를 줄이면 오래 갑니다."),
            Trouble("잘 나가는 영상을 찾아 주지 않는다",
                    "일부러 안 만들었습니다. '터진 영상 따라 만들기' 를 추천하던 도구가 "
                    "표절 논란으로 서비스를 접은 전례가 있습니다. 여기서는 **키워드·"
                    "포맷의 공백**만 말합니다."),
            Trouble("수치가 실제 유튜브와 다르다",
                    "검색량 자체는 API 로 받을 수 없어, **검색 결과 수와 조회수 분포**로 "
                    "가늠한 값입니다. 절대값이 아니라 **키워드끼리 견주는 용도**입니다."),
        ],
        files=[
            FileLoc("볼 키워드", "products/niche-research/keywords.txt"),
            FileLoc("쌓인 자료", "products/niche-research/data/snapshots.db",
                    "날마다 한 줄씩 쌓입니다. 지우면 흐름이 사라집니다."),
            FileLoc("보고서", "products/niche-research/outputs/"),
        ],
        admin_intro="**공급이 비어 있는 자리**를 찾습니다. 잘 나가는 영상을 "
                    "따라 만들라고는 하지 않습니다.",
        client_intro="찾는 사람에 견줘 만든 사람이 적은 자리를 알려 드립니다.",
        custom=True,
    )
