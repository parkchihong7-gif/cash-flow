"""3번 전용 웹 화면 — **수요 보고, 초안 쓰고, 검사까지 한 화면에서.**

CLI 는 명령을 세 번 쳐야 한다. `demand` 로 수요를 보고, `request.yaml` 을
메모장으로 고치고, `draft` 를 친다. 그 사이에 파일을 잘못 저장하거나 대가
유형을 안 바꾸고 그냥 돌린다.

화면이 알고 있어야 하는 것
--------------------------

* **자동 게시 버튼은 없다.** 있어야 할 자리에 "왜 없는지" 를 적는다.
  없는 걸 이상하게 여기지 않게 하는 것도 화면의 일이다
* **대가 유형을 고르면 문구가 바로 보인다.** 나중에 보여 주면 이미 늦다
* 검사 결과는 ✗ / ⚠ / · 로. ✗ 가 있으면 "올리시면 안 됩니다" 를 크게
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.webui import Field, Note, Panel, Table, WebUI          # noqa: E402

from naver_blog.demand import (                                  # noqa: E402
    DAILY_CALL_LIMIT, DemandError, collect, make_client,
)
from naver_blog.draft import Draft, PLACEHOLDER, Request, offline_draft   # noqa: E402
from naver_blog.policy import (                                  # noqa: E402
    BANNED_AUTOMATION, DISCLOSURE, DISCLOSURE_RULES, NO_WRITE_API,
    SPONSOR_KINDS, disclosure_for,
)
from naver_blog.review import ready, review                      # noqa: E402

REQUEST = BASE_DIR / "request.yaml"
KEYWORDS = BASE_DIR / "keywords.txt"
FIXTURES = BASE_DIR / "data" / "fixtures"
OUTPUTS = BASE_DIR / "outputs"

KIND_LABEL = {
    "none": "없음 — 받은 것 없음",
    "sponsored": "원고료를 받음",
    "affiliate": "제휴 링크가 있음",
    "paid": "그 밖의 대가를 받음",
    "gift": "제품을 무상으로 받음",
}
KIND_OPTIONS = [KIND_LABEL[k] for k in SPONSOR_KINDS]


def _request() -> Request:
    if not REQUEST.is_file():
        return Request(topic="")
    raw = yaml.safe_load(REQUEST.read_text(encoding="utf-8")) or {}
    known = {"topic", "keyword", "audience", "tone", "sponsor_kind",
             "sponsor_name", "must_include"}
    return Request(**{k: v for k, v in raw.items() if k in known})


def _keywords() -> list[str]:
    if not KEYWORDS.is_file():
        return []
    return [line.strip() for line in KEYWORDS.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def _demand_table() -> Table:
    """키워드 수요. 키가 없으면 샘플 자료로."""
    words = _keywords()
    if not words:
        return Table(note="`keywords.txt` 에 볼 키워드를 적으세요.")
    has_key = bool(os.getenv("NAVER_CLIENT_ID") and os.getenv("NAVER_CLIENT_SECRET"))
    try:
        client = (make_client(os.getenv("NAVER_CLIENT_ID", ""),
                              os.getenv("NAVER_CLIENT_SECRET", ""))
                  if has_key else make_client(fixture_dir=FIXTURES))
        rows_data = collect(words, client)
    except DemandError as exc:
        return Table(note=f"수요를 못 봤습니다: {exc}")

    rows, tones = [], []
    for row in rows_data:
        rows.append([row.word, f"{row.total_posts:,}", row.competition,
                     row.trend_direction])
        tones.append("bad" if row.crowded else ("warn" if row.too_quiet else "ok"))
    note = (f"네이버 검색 API · 하루 {DAILY_CALL_LIMIT:,}회 한도"
            if has_key else
            "**샘플 자료입니다.** 실제 값을 보시려면 `.env` 에 네이버 키를 넣으세요 "
            "(무료·심사 없음).")
    return Table(headers=["키워드", "쓰인 글", "경쟁", "흐름"],
                 rows=rows, tones=tones, numeric=[1], note=note)


def _draft_preview() -> tuple[Draft | None, list]:
    """지금 요청으로 뼈대 초안을 만들어 검사까지."""
    request = _request()
    if not request.topic.strip():
        return None, []
    try:
        draft = offline_draft(request)
    except Exception:
        return None, []
    return draft, review(draft, paid=request.paid)


def _review_table(issues) -> Table:
    rows, tones = [], []
    for item in issues:
        rows.append([item.mark, item.title, item.detail])
        tones.append("bad" if item.level == "block"
                     else ("warn" if item.level == "warn" else ""))
    return Table(headers=["", "무엇", "어떻게"], rows=rows, tones=tones)


def _policy_panel() -> Panel:
    """자동 게시 버튼이 있어야 할 자리. 왜 없는지를 적는다."""
    return Panel(
        key="policy", title="자동 게시 버튼이 없는 이유",
        notes=[Note("네이버는 블로그 글쓰기 API 를 열어 두지 않았습니다",
                    NO_WRITE_API, tone="warn"),
               Note("남은 방법은 비밀번호를 넣어 브라우저를 조작하는 것뿐입니다",
                    BANNED_AUTOMATION, tone="bad")],
        lines=["역설적으로 이게 낫습니다. 네이버 검색은 **원본성**과 체류시간을 봅니다",
               "양산한 글은 어차피 노출이 안 됩니다",
               "붙여넣기 전에 한 번 읽고 고치는 그 과정이 품질을 만듭니다"],
    )


def _disclosure_panel(request: Request) -> Panel:
    text = disclosure_for(request.sponsor_kind, request.sponsor_name)
    notes = []
    if request.paid:
        notes.append(Note("이 글은 대가성 문구가 들어갑니다",
                          f"**{text}**", tone="warn"))
    else:
        notes.append(Note("대가를 받지 않은 글입니다", "문구가 필요 없습니다.", tone="ok"))
    return Panel(
        key="disclosure", title="대가성 문구",
        intro="협찬·제휴·원고료를 받으셨다면 **법으로 정해진 문구**가 필요합니다 "
              "(표시광고법·공정위 심사지침).",
        notes=notes,
        lines=list(DISCLOSURE_RULES),
        note="문구 없이는 산출물이 아예 나오지 않습니다. 우회 경로를 두지 않았습니다.",
    )


def _request_fields(client_mode: bool = False) -> list[Field]:
    request = _request()
    fields = [
        Field("topic", "무엇에 대해 쓰시나요", "text", default=request.topic,
              placeholder="전세 계약할 때 확인할 것", required=True),
        Field("keyword", "노리는 검색어", "text", default=request.keyword,
              placeholder="전세 계약 주의사항"),
        Field("audience", "읽는 사람", "text", default=request.audience,
              placeholder="처음 전세를 구하는 사회 초년생"),
        Field("sponsor_kind", "대가를 받으셨나요", "select",
              default=KIND_LABEL.get(request.sponsor_kind, KIND_LABEL["none"]),
              options=KIND_OPTIONS,
              help="**받으셨다면 반드시 바꾸세요.** 문구 없이는 산출물이 안 나옵니다."),
        Field("sponsor_name", "광고주 이름", "text", default=request.sponsor_name,
              placeholder="OO상사", help="대가를 받으셨다면 적어 주세요."),
    ]
    if not client_mode:
        fields.append(Field("tone", "말투", "text", default=request.tone,
                            placeholder="차분하고 담백하게"))
    return fields


def build(program, ctx) -> WebUI:
    request = _request()
    draft, issues = _draft_preview()
    blocked = bool(issues) and not ready(issues)

    state_notes: list[Note] = []
    if draft:
        state_notes.append(Note(
            f"초안 뼈대 준비됨 · 본문 {draft.chars:,}자 · 빈칸 {draft.placeholders}곳",
            f"제목: {draft.title}", tone="warn" if blocked else "ok"))
        if blocked:
            state_notes.append(Note(
                "아직 올리시면 안 됩니다",
                f"`{PLACEHOLDER}` 를 본인 이야기로 바꾸셔야 합니다. "
                f"**두세 줄이면 충분합니다.**", tone="bad"))
    else:
        state_notes.append(Note("주제를 먼저 적어 주세요",
                                "아래 '초안 요청' 에서 무엇에 대해 쓰실지 적으시면 됩니다."))

    request_panel = Panel(
        key="request", title="초안 요청",
        intro="적으시고 저장하면 **바로 아래에서 검사 결과까지** 보입니다.",
        fields=_request_fields(),
        action="do:request", action_label="저장하고 미리 보기")

    demand_panel = Panel(
        key="demand", title="키워드 수요",
        intro="그 키워드로 **이미 몇 건이 쓰였는지**와 검색 흐름입니다.",
        table=_demand_table(),
        lines=["붐빈다고 꼭 피하실 것은 없습니다. 각도를 좁히면 자리가 있습니다",
               "**너무 한산하면 오히려 의심하세요.** 찾는 사람이 없는 것일 수 있습니다"],
        fields=[Field("words", "볼 키워드 (한 줄에 하나)", "textarea",
                      default="\n".join(_keywords()), rows=5)],
        action="do:keywords", action_label="키워드 저장")

    admin = [
        Panel(key="state", title="지금 상태", notes=state_notes),
        request_panel,
        _disclosure_panel(request),
    ]
    if issues:
        admin.append(Panel(
            key="review", title="올리기 전 검사",
            intro="**올리면 탈이 나는 것**만 봅니다. 품질은 사람이 봅니다.",
            table=_review_table(issues),
            note="✗ 고쳐야 합니다 · ⚠ 보시는 게 좋습니다 · · 참고"))
    admin += [
        demand_panel,
        Panel(key="run", title="초안 파일 만들기",
              intro="`outputs/` 에 마크다운으로 저장합니다. "
                    "**모의 실행은 뼈대만 만들고 비용이 0원입니다.**",
              action="run", action_label="초안 만들기 (모의)", run_mode="dry"),
        _policy_panel(),
    ]

    client = [
        Panel(key="state", title="내 글", notes=state_notes),
        Panel(key="request", title="무엇을 쓰실까요",
              intro="적으시고 저장하면 초안 뼈대가 만들어집니다.",
              fields=_request_fields(client_mode=True),
              action="do:request", action_label="저장하고 미리 보기"),
        _disclosure_panel(request),
    ]
    if issues:
        client.append(Panel(
            key="review", title="올리기 전 확인",
            table=_review_table(issues),
            note="✗ 가 하나도 없으면 복사해서 네이버 블로그에 붙이시면 됩니다."))
    client += [
        Panel(key="run", title="초안 받기",
              action="run", action_label="초안 만들기", run_mode="dry"),
        _policy_panel(),
    ]

    return WebUI(
        program_id=program.id, title=program.name,
        admin=admin, client=client,
        admin_intro="수요 보고 초안 쓰고 검사까지 **한 화면에서** 됩니다. "
                    "자동 게시는 일부러 안 만들었습니다.",
        client_intro="**빈칸만 채우시면 되게** 만들어 드립니다. "
                     "올리는 것은 직접 하셔야 합니다.",
    )


# ------------------------------------------------------------------ 동작
def _kind_key(label: str) -> str:
    for key, text in KIND_LABEL.items():
        if text == label:
            return key
    return "none"


def handle(program, ctx, action: str, form: dict) -> str:
    if action == "request":
        return _save_request(form)
    if action == "keywords":
        return _save_keywords(form)
    return "error=모르는 동작입니다"


def _save_request(form: dict) -> str:
    topic = (form.get("topic") or "").strip()
    if not topic:
        return "error=무엇에 대해 쓰실지 적어 주세요"

    kind = _kind_key((form.get("sponsor_kind") or "").strip())
    name = (form.get("sponsor_name") or "").strip()
    if kind != "none" and not name:
        # 광고주 이름이 없으면 문구에 OO 가 그대로 남는다. 그건 표시한 게 아니다.
        return ("error=대가를 받으셨다면 광고주 이름을 적어 주세요. "
                "이름이 없으면 문구에 OO 가 그대로 남습니다")

    payload = {
        "topic": topic,
        "keyword": (form.get("keyword") or "").strip(),
        "audience": (form.get("audience") or "일반 독자").strip(),
        "tone": (form.get("tone") or "차분하고 담백하게").strip(),
        "sponsor_kind": kind,
        "sponsor_name": name,
        "must_include": _request().must_include,
    }
    REQUEST.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    extra = f" · 대가성 문구: {DISCLOSURE[kind]}" if kind != "none" else ""
    return f"saved=초안 요청을 저장했습니다{extra}"


def _save_keywords(form: dict) -> str:
    words = [line.strip() for line in (form.get("words") or "").splitlines()
             if line.strip()]
    if not words:
        return "error=키워드를 한 줄에 하나씩 적어 주세요"
    KEYWORDS.write_text(
        "# 수요를 볼 키워드. 한 줄에 하나씩. # 로 시작하면 건너뜁니다.\n"
        + "\n".join(words) + "\n", encoding="utf-8")
    return f"saved=키워드 {len(words)}개를 저장했습니다"


# ══════════════════════════════════════════════════════════ 운영 콘솔
#
# 탭은 **블로그를 쓰는 일**에서 나온다. 이 사람이 한 편을 올리기까지 하는 일.
#
#     무엇을 쓸지 고른다(수요) → 초안을 받는다 → 내 이야기를 채운다
#     → 대가를 받았으면 표시한다 → 올리기 전에 검사한다 → 손으로 올린다
#
# 그래서 '대가 표시' 가 독립된 탭이다. 다른 프로그램에는 없는 자리인데,
# 이것만은 빠뜨리면 **과태료**라 초안 옆에 묻어 두면 안 된다.
# 마지막 '올리기' 는 버튼이 아니라 설명이다. 네이버가 글쓰기 API 를 열지
# 않아서다 — 자동 게시를 안 만든 것이 아니라 **만들면 안 되는** 것이다.

from core.console import Console, FileLoc, ManualTask, Stat, Tab, Todo, Trouble  # noqa: E402

from naver_blog.demand import DAILY_CALL_LIMIT                    # noqa: E402
from naver_blog.review import MAX_CHARS, MIN_CHARS, MIN_HEADINGS, MAX_TAGS  # noqa: E402


def _stats(request, draft, issues) -> list[Stat]:
    """위쪽 타일. **올려도 되는가**가 맨 앞이다.

    글자 수나 키워드 수를 앞에 두면 정작 중요한 걸 못 본다. 빈칸이 남은 채
    올리면 AI 가 쓴 티가 그대로 나고, 대가 표시를 빠뜨리면 과태료다.
    """
    # Issue.level 은 block/warn/note 다. 'bad' 로 거르면 하나도 안 잡혀서
    # 빈칸이 남았는데도 '올려도 됩니다' 라고 말하게 된다. `blocking` 을 쓴다.
    blockers = [item for item in issues if item.blocking] if issues else []
    tiles = []

    if draft is None:
        return [Stat("초안", "없음", tone="warn",
                     hint="무엇에 대해 쓰실지부터 적어 주세요", tab="request")]

    tiles.append(Stat(
        "올려도 되나", "아직" if blockers else "됩니다",
        tone="bad" if blockers else "ok",
        hint=f"고칠 곳 {len(blockers)}군데" if blockers else "검사를 통과했습니다",
        tab="review"))
    tiles.append(Stat(
        "내가 채울 빈칸", str(draft.placeholders), "곳",
        tone="bad" if draft.placeholders else "ok",
        hint="직접 겪은 일을 두세 줄만 넣으시면 됩니다" if draft.placeholders
             else "다 채우셨습니다",
        tab="draft"))
    tiles.append(Stat(
        "본문", f"{draft.chars:,}", "자",
        tone="warn" if not (MIN_CHARS <= draft.chars <= MAX_CHARS) else "",
        hint=f"{MIN_CHARS:,}~{MAX_CHARS:,}자 사이가 좋습니다", tab="review"))

    if request.sponsor_kind and request.sponsor_kind != "none":
        tiles.append(Stat(
            "대가 표시", KIND_LABEL.get(request.sponsor_kind, request.sponsor_kind),
            tone="warn", hint="본문 **맨 위**에 넣으셔야 합니다", tab="disclosure"))
    return tiles


def console(program, ctx) -> Console:
    """3번 운영 콘솔."""
    request = _request()
    draft, issues = _draft_preview()
    ui = build(program, ctx)

    def panel(key: str):
        return next((item for item in ui.admin if item.key == key), None)

    tabs = [
        Tab(key="demand", label="키워드 수요", icon="🔍", group="고르는 자리",
            intro="그 키워드로 **이미 몇 건이 쓰였는지** 봅니다. "
                  "붐빈다고 꼭 피하실 것은 없습니다 — 각도를 좁히면 자리가 있습니다.",
            panels=[p for p in [panel("demand")] if p],
            common_buttons="`키워드 저장` — 저장해 두면 다음에도 이 목록으로 봅니다."),
        Tab(key="request", label="초안 요청", icon="✍️", group="쓰는 자리",
            intro="무엇에 대해 쓰실지 적으시면 **뼈대**를 만들어 드립니다.",
            panels=[p for p in [panel("state"), panel("request")] if p]),
    ]

    if draft:
        tabs.append(Tab(
            key="draft", label="초안 채우기", icon="📝", group="쓰는 자리",
            intro=f"`{PLACEHOLDER}` 가 {draft.placeholders}곳 있습니다. "
                  f"**여기에 직접 겪은 일을 넣으셔야 합니다.**",
            panels=[Panel(
                key="body", title=draft.title or "초안",
                intro="아래 글을 복사해 네이버 블로그 편집기에 붙이시고, "
                      "빈칸을 채우시면 됩니다.",
                fields=[Field("body", "본문", "textarea",
                              default=draft.body, rows=24)],
                note="이 칸은 보시라고 띄운 것입니다. 고치실 것은 "
                     "**블로그 편집기에서** 하시는 편이 편합니다."
                     if draft.placeholders else "",
                tone="warn" if draft.placeholders else "")]))

    tabs.append(Tab(
        key="disclosure", label="대가 표시", icon="⚖️", group="쓰는 자리",
        intro="원고료·제품·제휴 수수료를 받으셨다면 **반드시** 표시해야 합니다. "
              "빠뜨리면 과태료 대상입니다.",
        panels=[p for p in [panel("disclosure")] if p]))

    if issues:
        tabs.append(Tab(
            key="review", label="올리기 전 검사", icon="✅", group="올리는 자리",
            intro="**올리면 탈이 나는 것**만 봅니다. 글이 좋은지는 사람이 봅니다.",
            panels=[p for p in [panel("review")] if p]))

    tabs += [
        Tab(key="publish", label="올리기", icon="📤", group="올리는 자리",
            intro="이 자리에는 **버튼이 없습니다.** 아래 이유를 읽어 주세요.",
            panels=[Panel(
                key="publish", title="왜 자동 게시 버튼이 없는가",
                intro=NO_WRITE_API,
                lines=[BANNED_AUTOMATION,
                       "초안을 **복사해서** 네이버 블로그 편집기에 붙이시면 됩니다",
                       "사진은 직접 찍으신 것을 넣으세요. 남의 사진은 넣지 마세요"],
                tone="warn")]),
        Tab(key="file", label="초안 파일", icon="📄", group="내보내기",
            panels=[p for p in [panel("run")] if p]),
        Tab(key="policy", label="지켜야 할 것", icon="📜", group="올리는 자리",
            panels=[p for p in [panel("policy")] if p]),
    ]

    return Console(
        program_id=program.id,
        title=program.name,
        subtitle=program.tagline,
        tabs=tabs,
        stats=_stats(request, draft, issues),
        todos=[
            Todo("오늘 쓸 키워드를 고르기", tab="demand",
                 detail="**너무 한산한 키워드는 오히려 의심하세요.** 찾는 사람이 "
                        "없는 것일 수 있습니다."),
            Todo("초안의 빈칸을 **내 이야기로** 채우기", tab="draft", by_hand=True,
                 detail="두세 줄이면 충분합니다. 이 부분이 없으면 AI 가 쓴 티가 "
                        "그대로 납니다."),
            Todo("대가를 받았으면 문구를 본문 맨 위에 넣기", tab="disclosure",
                 by_hand=True),
            Todo("검사에서 ✗ 를 없애고 복사해 붙이기", tab="review"),
        ],
        manual_tasks=[
            ManualTask(
                task="블로그에 글 올리기",
                where="네이버 블로그 편집기 (직접 복사해 붙이기)",
                why=NO_WRITE_API + " " + BANNED_AUTOMATION,
                someday="네이버가 글쓰기 API 를 열면 그때 붙입니다. 지금은 없습니다."),
            ManualTask(
                task="빈칸에 직접 겪은 일 넣기",
                where="초안 채우기 탭",
                why="겪지 않은 일을 AI 가 지어내면 **거짓말이 됩니다.** 게다가 "
                    "읽는 사람은 금방 압니다. 이 자리는 비워 두는 것이 설계입니다."),
            ManualTask(
                task="대가 표시 문구 넣기",
                where="본문 맨 위 (블로그 편집기)",
                why="공정위 표시 지침입니다. **맨 아래나 '더보기' 안에 숨기면 "
                    "표시한 것으로 보지 않습니다.** 프로그램이 문구는 만들어 "
                    "드리지만, 편집기에 넣는 것은 손으로 하셔야 합니다."),
            ManualTask(
                task="사진 넣기",
                where="블로그 편집기",
                why="직접 찍으신 사진을 쓰셔야 합니다. 남의 사진을 가져오면 "
                    "저작권 문제가 되고, AI 로 만든 사진은 표시가 필요합니다."),
            ManualTask(
                task="이웃·댓글 관리",
                where="네이버 블로그",
                why="자동 이웃추가·자동 댓글은 **약관 위반**이라 계정이 정지됩니다. "
                    "만들지 않습니다."),
        ],
        troubles=[
            Trouble("검사에서 ✗ 가 안 없어진다",
                    f"빈칸(`{PLACEHOLDER}`)이 남아 있거나, 본문이 {MIN_CHARS:,}자보다 "
                    f"짧거나, 소제목이 {MIN_HEADINGS}개보다 적을 때입니다. "
                    "검사 탭에 어느 줄인지 나옵니다."),
            Trouble("대가 표시 문구가 안 만들어진다",
                    "**광고주 이름을 적어야** 문구가 나옵니다. 'OO' 그대로 두면 "
                    "표시한 것으로 보지 않습니다."),
            Trouble("키워드 수요가 안 나온다",
                    "네이버 검색 API 키가 없으면 **예시 자료**로 보여 드립니다. "
                    "실제 값을 보시려면 네이버 개발자센터에서 키를 받아 "
                    "`.env` 에 넣으세요. 무료입니다."),
            Trouble("키워드를 많이 넣었더니 막힌다",
                    f"네이버 검색 API 는 하루 {DAILY_CALL_LIMIT:,}회까지입니다. "
                    "넘으면 다음 날로 넘어갑니다. 재시도하면 더 깎이니 "
                    "기다리시는 편이 맞습니다."),
            Trouble("태그를 많이 달면 더 노출되나",
                    f"아닙니다. {MAX_TAGS}개를 넘으면 검사에서 경고가 뜹니다. "
                    "관계없는 태그는 오히려 손해입니다."),
            Trouble("글이 검색에 안 잡힌다",
                    "이 프로그램이 답할 수 있는 범위를 넘습니다. 네이버 노출은 "
                    "체류시간·이웃·꾸준함이 크게 작용하고, **보장할 수 있는 "
                    "방법은 없습니다.** 여기서는 '탈이 나는 것' 만 걸러 드립니다."),
        ],
        files=[
            FileLoc("초안 요청", "products/naver-blog/request.yaml"),
            FileLoc("볼 키워드", "products/naver-blog/keywords.txt"),
            FileLoc("예시 자료", "products/naver-blog/data/fixtures/",
                    "API 키가 없을 때 쓰는 자료입니다."),
            FileLoc("만든 초안", "products/naver-blog/outputs/"),
        ],
        admin_intro="수요 보고 초안 쓰고 검사까지 **한 화면에서** 됩니다. "
                    "자동 게시는 일부러 안 만들었습니다 — '올리기' 탭에 이유가 있습니다.",
        client_intro="**빈칸만 채우시면 되게** 만들어 드립니다. "
                     "올리는 것은 직접 하셔야 합니다.",
        custom=True,
    )
