"""15번 전용 웹 화면 — **수요 보고, 초안 쓰고, 검사까지 한 화면에서.**

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
