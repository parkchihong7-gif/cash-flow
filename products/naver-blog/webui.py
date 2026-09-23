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
    """3번 운영 콘솔.

    **본체는 여기에 없다.** Cloud Run 에서 돌고, 관리자도 고객도 그 주소로
    들어간다. 그래서 이 화면은 프로그램을 흉내 내지 않는다 — 흉내 내면
    사장님이 여기서 초안을 만들려 들고, 고객에게 이 주소를 보낸다.

    **두 모드가 같은 주소다.** 무엇을 넣느냐로 갈린다. 1번의 `?admin=1` 과는
    다른 방식이라, 화면이 그 차이를 분명히 말해야 한다.

    **키는 여기서만 만든다.** 예전에는 프로그램이 자기 접속 코드를 따로
    만들어서 장부가 둘이었다. 파는 곳과 여는 곳이 갈라지면 누구에게 무엇을
    팔았는지 한 군데서 볼 수가 없다. 그 칸은 프로그램에서 걷어냈다.
    """
    주소 = program.live.admin or "(program.yaml 의 live.admin 이 비었습니다)"

    시작 = Tab(
        key="start", label="어디서 도나", icon="🚪", group="파는 자리",
        intro="본체는 **밖에서 돕니다.** 사장님 컴퓨터가 꺼져 있어도 열립니다. "
              "여기서는 팔고, 키를 주고, 문의에 답하는 일만 하십니다.",
        panels=[
            Panel(key="where", title="주소가 둘이 아닙니다 — 판매용엔 아예 안 갑니다", tone="warn", table=Table(
            headers=["무슨 키", "받는 분", "무엇이 가나"],
            rows=[
                ["판매용", "돈 주고 사신 분", "**주소 없음.** 설치 안내서가 대신 갑니다"],
                ["체험용", "사시기 전 맛만 보실 분",
                 f"**체험 전용 서버** · 기본 1일 · 하루 3건"],
                ["마스터 토큰", "사장님", "전부"],
            ]),
        notes=[Note("", "**판매용에 주소를 넣으면 안 됩니다.** 그 분의 고객이 쓴 글이 "
                        "전부 우리 서버로 들어옵니다 — 팔아 놓고 데이터는 우리가 "
                        "들고 있는 꼴이라 팔 수가 없습니다.", "warn"),
               Note("", f"체험이 여는 곳: {주소}", "info"),
               Note("", "**사장님이 실제로 쓰시는 서버와 달라야 합니다.** 같으면 체험 "
                        "회원이 사장님 Claude 한도와 메모리를 나눠 씁니다 — "
                        "`체험서버-세우기.md` 참고.", "warn"),
               Note("", "체험용 기간이 끝나거나 [⏸ 사용중지] 하시면, 그분이 남긴 "
                        "글·카테고리는 **그 서버에서 지워집니다.** 처음 들어가실 "
                        "때 맛보기 카테고리 셋이 자동으로 깔립니다.", "info")]),
            Panel(key="flow", title="파는 순서",
                  lines=[
                      "1. 여기 **[접속키] 탭**에서 이름·이메일을 넣고 발급",
                      "2. **[발송]** — 키 네 개와 사용 설명서가 한 통에 나갑니다",
                      "3. 고객이 1차키와, 자기 기기에 맞는 2차키를 넣고 들어갑니다",
                      "4. 기기 세 대(PC·노트북·휴대폰)까지 쓰십니다",
                  ]),
        ])

    코드 = Tab(
        key="codes", label="접속 코드", icon="🎟", group="파는 자리",
        admin_only=True,
        intro="키는 **여기 [접속키] 탭에서만** 만듭니다. 프로그램 화면에는 "
              "만드는 칸이 없습니다.",
        panels=[
            Panel(key="two", title="두 단계",
                  table=Table(
                      headers=["단계", "몇 개", "쓰임"],
                      rows=[
                          ["1차 인증키", "1개", "사람 한 명당 하나"],
                          ["2차 인증키", "3개", "PC · 노트북 · 휴대폰. **기기당 한 세션**"],
                      ]),
                  notes=[Note("", "둘 다 **한 번에 만들어 한 통으로** 나갑니다. "
                                  "고객이 1차를 넣어야 2차가 나오는 방식이 아닙니다.", "info"),
                         Note("", "같은 2차키로 다른 기기에서 들어오면 **먼저 쓰던 "
                                  "기기가 잠깁니다.** 화면이 1분마다 확인합니다.", "info")]),
            Panel(key="one", title="장부는 하나입니다", tone="good",
                  lines=[
                      "예전에는 프로그램이 **자기 접속 코드**를 따로 만들었습니다",
                      "모양은 같았지만 장부가 달라서, 여기서 판 키가 "
                      "프로그램에서는 «없는 코드» 로 나왔습니다",
                      "지금은 프로그램이 **이 장부에 물어봅니다** — "
                      "1번 공인중개사도 같은 곳을 봅니다",
                  ],
                  notes=[Note("", "그래서 프로그램의 «4) 접속 코드 관리» 칸은 "
                                  "걷어냈습니다. 두 군데서 만들면 어느 쪽이 진짜인지 "
                                  "알 수 없습니다. 그 자리에는 지금 "
                                  "**«4) 포스팅 예약 설정»** 이 들어가 있습니다 — "
                                  "시각·하루 건수·차례를 정하는 곳입니다.", "info")]),
            Panel(key="mail", title="메일로 나갑니다", tone="good",
                  lines=[
                      "[접속키] 탭에서 이름·이메일을 넣고 [발급하고 안내문 만들기]",
                      "키 네 개와 **사용 설명서가 꾸며진 채로** 한 통에 들어갑니다",
                      "보내기 전에 덧붙일 말을 고치실 수 있습니다 — "
                      "고칠 수 있는 것은 **접속키 부분만**이고 매뉴얼은 자동으로 붙습니다",
                  ]),
            Panel(key="stop", title="정지·삭제", tone="warn",
                  lines=[
                      "**사용중지**는 되돌릴 수 있습니다. 잠깐 막을 때 쓰십시오",
                      "**삭제**는 못 되돌립니다. 그래서 두 번 눌러야 합니다",
                      "정지시키면 이미 들어와 있던 기기도 **1분 안에 끊깁니다**",
            "**체험용을 정지하면 그분 글도 그때 지워집니다** — 되돌릴 수 없습니다",
                  ]),
        ])

    안내 = Tab(
        key="guide", label="블로그 쓰는 법", icon="📖", group="고객에게",
        intro="상담할 때 이 탭을 띄워 놓고 그대로 읽어 드리시면 됩니다.",
        panels=[
            Panel(key="first", title="처음 한 번",
                  lines=[
                      "주소를 엽니다",
                      "**1차(초대) 코드**를 넣습니다 → 기기별 2차 코드 3개가 나옵니다",
                      "**지금 쓰는 기기에 맞는 2차 코드**를 넣습니다",
                      "다른 기기에서는 그 기기용 코드를 넣으시면 됩니다",
                  ],
                  notes=[Note("", "여기서 제일 많이 헤맵니다. PC용을 휴대폰에 "
                                  "넣으면 안 됩니다.", "warn")]),
            Panel(key="screens", title="화면",
                  table=Table(
                      headers=["이름", "하는 일"],
                      rows=[
                          ["🏠 홈", "통계 · 최근 활동 · AI 연결 상태"],
                          ["📁 블로그 관리", "카테고리 등록·수정. 카테고리 하나가 초안 하나"],
                          ["📝 포스팅", "쌓인 초안 카드. 제목·본문·이미지 복사"],
                          ["📜 발행 이력", "올린 기록 · 이미지 출처 CSV"],
                          ["⚙️ 관리자 설정", "AI 연결 · 블로그 주제 · 포스팅 방향"],
                          ["📖 사용법", "화면 안의 설명서"],
                      ])),
            Panel(key="daily", title="매일 하는 일",
                  lines=[
                      "아침에 초안이 **자동으로** 쌓여 있습니다",
                      "[포스팅] 에서 마음에 드는 **후킹 제목**을 고릅니다 (3종)",
                      "제목·본문·이미지를 복사 → **네이버에 붙여넣고 직접 발행**",
                      "올리셨으면 [발행 완료] 를 누릅니다 — 다음 초안이 겹치지 않게",
                  ]),
        ])

    주의 = Tab(
        key="care", label="꼭 지킬 것", icon="⚠️", group="고객에게",
        panels=[
            Panel(key="naver", title="자동 발행은 하지 않습니다", tone="warn",
                  lines=[
                      "예전에 넣었다가 네이버가 자동화를 잡아내 **계정 보호조치**"
                      "(비밀번호 강제 재설정)가 걸렸습니다",
                      "그래서 네이버 로그인·발행 코드를 **통째로 걷어냈습니다**",
                      "이 프로그램에는 네이버 비밀번호를 넣는 칸이 아예 없습니다",
                  ],
                  notes=[Note("", "«자동으로 올려 달라» 는 요청이 와도 하지 마십시오. "
                                  "계정을 잃는 것보다 복사 한 번이 쌉니다.", "warn")]),
            Panel(key="draft", title="AI 가 쓴 것은 초안입니다",
                  lines=[
                      "**직접 겪은 이야기를 더하지 않으면 원본성이 없습니다.** "
                      "네이버 검색이 보는 것이 그것입니다",
                      "AI 생성물 표시를 켜 두시면 본문 끝에 고지 한 줄이 붙습니다 "
                      "(인공지능기본법)",
                  ]),
            Panel(key="image", title="이미지는 찾아 온 것입니다",
                  lines=[
                      "무료 스톡 세 곳에서 가져옵니다. **만들지 않습니다**",
                      "채택한 이미지마다 출처·원본 주소·라이선스·받은 시각을 기록합니다",
                      "[발행 이력] 에서 CSV 로 내려받으실 수 있습니다 — 나중에 "
                      "«그때는 무료였다» 를 증빙하는 자료입니다",
                  ]),
        ])

    문의 = Tab(
        key="ask", label="자주 오는 문의", icon="💬", group="고객에게",
        panels=[
            Panel(key="qa", title="자주 들어오는 것",
                  table=Table(
                      headers=["문의", "답"],
                      rows=[
                          ["자동으로 올려 주나요",
                           "하지 않습니다. 글과 이미지까지 준비해 드리고 복사·발행은 본인이"],
                          ["AI 요금이 나오나요",
                           "**Gemini 를 고르시면 0원**입니다(구글 계정, 하루 1,000건). "
                           "Claude·Codex 는 쓰시던 구독 한도 안에서 돕니다. "
                           "어느 쪽이든 API 종량 과금이 아닙니다"],
                          ["꼭 Claude 여야 하나요",
                           "아닙니다. **Gemini·Claude·Codex 중에 고르십니다.** "
                           "[관리자 설정 → 1단계]에서 바꾸시면 됩니다"],
                          ["이미지가 안 나옵니다",
                           "무료 API 키가 없거나 한도를 넘겼습니다. 홈의 «AI 연결 상태» 확인"],
                          ["접속키를 잃어버렸어요",
                           "보내 드린 메일을 다시 찾아보시게 하고, 없으면 새로 발급합니다"],
                          ["**갑자기 로그아웃됐어요**",
                           "**같은 2차키로 다른 기기에서 들어온 것입니다.** 기기마다 "
                           "제 키를 쓰셔야 합니다"],
                          ["기기를 바꿨습니다",
                           "그 기기 자리(PC·노트북·휴대폰)의 2차키를 쓰시면 됩니다"],
                      ])),
        ])

    return Console(
        program_id=program.id,
        title=program.name,
        subtitle=program.tagline,
        tabs=[시작, 코드, 안내, 주의, 문의],
        stats=[
            Stat(label="이미지 소스", value="3", unit="곳",
                 hint="Unsplash · Pexels · Pixabay (하나만 살아도 됩니다)"),
            Stat(label="후킹 제목", value="3", unit="종", hint="질문형 · 숫자형 · 공감형"),
            Stat(label="기기", value="3", unit="대", hint="PC · 노트북 · 휴대폰"),
            Stat(label="추가 비용", value="0", unit="원", tone="good",
                 hint="AI 계정 하나(Gemini 면 무료) + 무료 이미지 API"),
        ],
        todos=[
            Todo("쌓인 초안에서 제목 골라 네이버에 올리기", tab="guide",
                 by_hand=True,
                 detail="**여기가 사람이 하는 자리입니다.** 복사해서 붙여넣고 "
                        "직접 발행하십니다. 올린 뒤 [발행 완료] 를 눌러 주세요."),
            Todo("새 고객에게 접속키 보내기", tab="codes", admin_only=True,
                 detail="[접속키] 탭에서 이름·이메일을 넣고 [발급하고 안내문 만들기] "
                        "→ [발송]. 키와 사용 설명서가 한 통에 나갑니다."),
            Todo("들어온 문의에 답하기", tab="ask",
                 detail="«갑자기 로그아웃됐다» 가 제일 많습니다 — 같은 2차키를 "
                        "두 기기에서 쓰신 경우입니다."),
        ],
        manual_tasks=[
            ManualTask(
                task="네이버에 붙여넣고 발행하는 것",
                where="네이버 블로그 글쓰기",
                why="자동 발행을 넣었다가 **계정 보호조치**가 걸렸습니다. "
                    "네이버 로그인 코드를 통째로 걷어냈고, 되살릴 생각이 없습니다.",
                someday="네이버가 공개 API 를 열면 그때 다시 볼 일입니다."),
            ManualTask(
                task="직접 겪은 이야기를 더하는 것",
                where="복사한 본문 안",
                why="AI 가 쓴 것은 초안입니다. 원본성이 없으면 네이버 검색에 "
                    "잡히지 않습니다. 이것만은 사람이 해야 합니다."),
        ],
        troubles=[
            Trouble("관리자 설정에 «접속 코드 관리» 가 안 보인다",
                    "**없앴습니다. 정상입니다.** 키는 이 대시보드의 [접속키] 탭에서만 "
                    "만듭니다. 두 군데서 만들면 어느 쪽이 진짜인지 알 수 없습니다."),
            Trouble("고객이 «갑자기 로그아웃됐다» 고 한다",
                    "**같은 2차키로 다른 기기에서 들어온 것입니다.** 2차키는 기기마다 "
                    "다릅니다 — PC 용을 휴대폰에도 넣으면 PC 가 끊깁니다. 받으신 메일의 "
                    "기기 이름을 보고 맞는 것을 넣으시게 안내해 주세요."),
            Trouble("고객이 «등록되지 않은 키» 라고 한다",
                    "프로그램의 `KEYSERVER_URL` 설정이 빠졌거나 다른 곳을 보고 있습니다. "
                    "마스터 토큰으로는 들어가지는데 고객만 못 들어오면 이 경우입니다."),
            Trouble("«지금 생성» 이 가끔 실패한다",
                    "Cloud Run 의 요청 제한에 걸린 것입니다. 글쓰기 재시도와 이미지 "
                    "파이프라인이 길어질 때 납니다. 제한 시간을 늘려 두면 됩니다."),
            Trouble("이미지가 하나도 안 나온다",
                    "무료 API 키가 없거나 전부 한도를 넘겼습니다. 홈 화면의 "
                    "«AI 연결 상태» 카드에 살아 있는 소스 개수가 나옵니다."),
            Trouble("재배포했는데 반영이 안 된다",
                    "배포 자체가 실패했을 수 있습니다. 환경변수가 `YOUR_...` 자리표시자로 "
                    "남아 있는 경우가 잦습니다."),
            Trouble("고객이 접속키를 잃어버렸다",
                    "보내 드린 메일을 다시 찾아보시게 하고, 없으면 [접속키] 탭에서 "
                    "새로 발급해 보내시면 됩니다. 옛 키는 [사용중지] 해 두세요."),
        ],
        files=[
            FileLoc("프로그램 본체", 주소,
                    "이 저장소가 아니라 Cloud Run 에 있습니다."),
            FileLoc("자료 보관", "구글 클라우드 스토리지 버킷",
                    "DB·만든 이미지·로그인 정보가 여기 있습니다. 컨테이너가 접혀도 남습니다."),
            FileLoc("파는 문구 초안", "products/naver-blog/README.md"),
        ],
        admin_intro="**본체는 밖에서 돕니다.** 관리자도 고객도 같은 주소로 들어가고, "
                    "무엇을 넣느냐로 갈립니다. 접속키는 **여기 [접속키] 탭에서만** "
                    "만듭니다 — 프로그램 안에는 만드는 칸이 없습니다.",
        client_intro="고객에게 그대로 읽어 드릴 안내입니다. 고객이 실제로 쓰는 화면은 "
                     "위 [프로그램 열기 ↗] 버튼의 주소입니다 — 이 화면이 아닙니다.",
        custom=True,
    )
