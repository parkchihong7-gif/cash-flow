"""통합 관리자 대시보드 (FastAPI).

로컬에서 `python -m dashboard` 로 띄우고 브라우저로 쓴다.

화면 구성
    /                     홈 — 프로그램 1번, 2번… 목록과 현황 숫자
    /programs/{id}        열람 — 개요·이용 순서·FAQ·산출물 설명
    /programs/{id}/edit   수정 — 설정값과 편집 가능한 파일
    /programs/{id}/test   테스트 — 모의/실제 실행과 결과
    /programs/{id}/members  회원관리 — 이 프로그램을 산 고객
    /members              전체 고객
    /settings             기타 설정 — API 키 상태, 기본 모델, 금지 문구
    /manual               매뉴얼 — 관리자용 / 클라이언트용
    /login                접속 코드 입력

프로그램을 새로 만들면 `products/<이름>/program.yaml` 만 넣으면 된다.
이 파일은 고치지 않는다.

접속 코드
    `/static` 과 `/healthz` 를 뺀 모든 화면은 접속 코드를 넣어야 열린다.
    코드는 `.env` 의 `DASHBOARD_ACCESS_CODE` 로 바꾼다. 자세한 것은 `core/auth.py`.
"""

from __future__ import annotations

import html
import json
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse
from typing import Any

import markdown as md
from markupsafe import Markup
from fastapi import FastAPI, Form, Request
from fastapi.responses import (FileResponse, HTMLResponse, PlainTextResponse,
                               RedirectResponse)
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core import auth
from core.db import Database, DEFAULT_DB_PATH
from core.access import collect as collect_access, summarize as access_summary
from core.backup import backup_name, copy_db
from core import keyclient
from core.compliance import audit as compliance_audit, RULES as COMPLIANCE_RULES
from core.health import checklist
from core.search import search as search_index
from core.manifest import ProgramManifest
from core.overview import collect as collect_config, env_rows
from core.registry import Registry
from core.schedule import collect as collect_schedule, summarize as schedule_summary
from core.runner import RunError, run_program
from dashboard.charts import monthly_chart, program_chart
from core.keyauth import (KIND_PRIMARY, KIND_SECONDARY, ROLE_ADMIN, KeyAuth,
                          KeyError_)
from dashboard.clientdoor import DOOR_PREFIX
from dashboard.clientdoor import register as register_door
from dashboard.webapp import register as register_apps
from shared import banned_phrases
from shared.config import ANTHROPIC_API_KEY, DEFAULT_MODEL, ROOT_DIR

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = ROOT_DIR / "docs"

def safe_next(target: str) -> str:
    """로그인 뒤 돌아갈 주소를 고른다.

    주소를 그대로 믿으면 안 된다. `?next=https://남의사이트` 를 붙인 링크를
    보내 놓고 로그인 직후 그쪽으로 튕겨 보내는 수법이 있다.
    그래서 `/` 로 시작하는 우리 쪽 경로만 받는다.
    """
    if not target or not target.startswith("/") or target.startswith("//"):
        return "/"
    if urlparse(target).scheme or urlparse(target).netloc:
        return "/"
    return target


#: 접속 코드 없이 열리는 경로. 로그인 화면 자체와 정적 파일, 상태 확인용 주소뿐이다.
#: 상태 확인용 주소를 열어 두는 이유는 클라우드 호스팅이 "살아 있나" 를
#: 물어볼 때 로그인 화면을 주면 죽은 것으로 보기 때문이다.
OPEN_PATHS = ("/login", "/healthz", "/favicon.ico")
#: 대시보드 접속 코드를 묻지 않는 길.
#: `/c/` 는 고객이 들어오는 문이라 열려 있어야 한다. 대신 그 안에서
#: 이중키를 따로 확인한다 — 열린 것은 문이지 화면이 아니다.
OPEN_PREFIXES = ("/static/", "/c/")

#: 전역 설정 항목 정의. 대시보드가 이걸로 폼을 그린다.
GLOBAL_SETTINGS = [
    {
        "key": "default_model",
        "label": "기본 Claude 모델",
        "type": "select",
        "options": ["claude-sonnet-4-6", "claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5"],
        "default": DEFAULT_MODEL,
        "help": "프로그램에서 따로 정하지 않으면 이 모델을 씁니다.",
    },
    {
        "key": "ai_label",
        "label": "AI 생성물 표시 기본값",
        "type": "boolean",
        "default": "1",
        "help": "인공지능기본법 제31조 대응. 켜두는 것을 권합니다.",
    },
    {
        "key": "business_name",
        "label": "사업자 상호",
        "type": "text",
        "default": "",
        "help": "랜딩 푸터와 계약서 템플릿에 들어갈 이름입니다.",
    },
    {
        "key": "contact_email",
        "label": "고객 문의 이메일",
        "type": "text",
        "default": "",
        "help": "구매자에게 안내할 문의처입니다.",
    },
    {
        "key": "refund_policy",
        "label": "환불 정책 문구",
        "type": "textarea",
        "default": "",
        "help": "전자상거래법상 청약철회 기간·조건·연락처를 적습니다. 랜딩 푸터에 붙여 쓰세요.",
    },
]


def render_markdown(text: str) -> str:
    """마크다운을 HTML 로. 표와 코드블록을 지원한다.

    `Markup` 으로 감싸야 Jinja 가 다시 이스케이프하지 않는다. 안 감싸면
    화면에 `<strong>` 이 글자 그대로 보인다.
    """
    return Markup(md.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"]))


def render_inline(text: str) -> str:
    """한두 줄짜리 글용. **굵게** 정도만 살리고 <p> 로 감싸지 않는다.

    설명 문구를 `<p class="muted">{{ x | md }}</p>` 안에 넣는데, 블록 마크다운을
    쓰면 <p> 안에 <p> 가 들어가 화면이 어긋난다.
    """
    html = md.markdown(str(text or ""), extensions=["sane_lists"])
    if html.startswith("<p>") and html.endswith("</p>") and html.count("<p>") == 1:
        html = html[3:-4]
    return Markup(html)


def create_app(db_path: str | Path = DEFAULT_DB_PATH,
               products_dir: Path | None = None) -> FastAPI:
    """대시보드 앱을 만든다. 테스트에서는 임시 DB 경로를 넘긴다."""
    app = FastAPI(title="통합 관리자 대시보드", docs_url=None, redoc_url=None)
    app.state.db = Database(db_path)
    app.state.registry = Registry(products_dir) if products_dir else Registry()
    app.state.gatekeeper = auth.Gatekeeper()

    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    templates.env.filters["markdown"] = render_markdown
    templates.env.filters["md"] = render_inline
    templates.env.filters["won"] = lambda value: f"{int(value or 0):,}원"
    # 접속키 관리자(앱스 스크립트) 주소. `_tabs.html` 이 여덟 화면에 끼어들기
    # 때문에 각 화면마다 넘기면 반드시 한 군데를 빠뜨린다. 전역으로 둔다.
    # 값은 `.env` 에서 읽는다 — 공개 저장소에 주소를 박지 않으려는 것.
    templates.env.globals["keyserver_url"] = keyclient.admin_page_url
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    def db() -> Database:
        return app.state.db

    def registry() -> Registry:
        return app.state.registry

    def page(request: Request, template: str, **context: Any) -> HTMLResponse:
        """공통 컨텍스트를 얹어 템플릿을 렌더한다."""
        context.setdefault("programs", registry().programs)
        context.setdefault("load_errors", registry().errors)
        context.setdefault("api_key_set", bool(ANTHROPIC_API_KEY))
        context.setdefault("default_code", auth.is_default_code())
        return templates.TemplateResponse(request, template, context)

    # ------------------------------------------------------------ 접속 코드
    def is_open(path: str) -> bool:
        return path in OPEN_PATHS or path.startswith(OPEN_PREFIXES)

    def caller(request: Request) -> str:
        """누가 시도했는지 구분할 값.

        클라우드나 터널 뒤에 두면 접속하는 쪽이 전부 프록시 주소로 보인다.
        그래서 프록시가 붙여 주는 `X-Forwarded-For` 의 맨 앞을 먼저 본다.
        """
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def over_https(request: Request) -> bool:
        """HTTPS 로 들어왔는가. 프록시 뒤에서는 헤더를 봐야 안다."""
        if request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https":
            return True
        return request.url.scheme == "https"

    @app.middleware("http")
    async def require_access_code(request: Request, call_next):
        if is_open(request.url.path) or auth.verify_token(
                request.cookies.get(auth.COOKIE_NAME)):
            return await call_next(request)

        wanted = request.url.path
        if request.url.query:
            wanted = f"{wanted}?{request.url.query}"
        target = "/login" if wanted in ("/", "") else f"/login?next={quote(wanted, safe='')}"
        return RedirectResponse(target, status_code=303)

    def login_page(request: Request, error: str = "", remaining: int | None = None,
                   next_path: str = "", status: int = 200) -> HTMLResponse:
        locked = app.state.gatekeeper.locked_for(caller(request))
        return templates.TemplateResponse(
            request, "login.html",
            {
                "error": error,
                "remaining": remaining,
                "locked": bool(locked),
                "locked_minutes": max(1, round(locked / 60)),
                "lockout_minutes": round(auth.LOCKOUT_SECONDS / 60),
                "next_path": safe_next(next_path),
            },
            status_code=status,
        )

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request, next: str = ""):
        if auth.verify_token(request.cookies.get(auth.COOKIE_NAME)):
            return RedirectResponse(safe_next(next), status_code=303)
        return login_page(request, next_path=next)

    @app.post("/login")
    def login_submit(request: Request, code: str = Form(""), next: str = Form("")):
        gate = app.state.gatekeeper
        who = caller(request)

        if gate.locked_for(who):
            return login_page(request, next_path=next, status=429)

        if not auth.check_code(code):
            remaining = gate.record_failure(who)
            return login_page(
                request, error="접속 코드가 맞지 않습니다.",
                remaining=remaining or None, next_path=next, status=401,
            )

        gate.reset(who)
        response = RedirectResponse(safe_next(next), status_code=303)
        response.set_cookie(
            auth.COOKIE_NAME, auth.issue_token(),
            max_age=auth.session_hours() * 3600,
            httponly=True,              # 자바스크립트가 쿠키를 읽지 못하게
            samesite="lax",             # 다른 사이트에서 넘어온 요청에는 딸려가지 않게
            secure=over_https(request),  # HTTPS 로 들어왔으면 HTTPS 에서만 보내게
            path="/",
        )
        return response

    @app.post("/logout")
    def logout():
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(auth.COOKIE_NAME, path="/")
        return response

    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz():
        """호스팅이 '살아 있나' 를 물어볼 때 쓰는 주소. 안의 내용은 알려주지 않는다."""
        return "ok"

    def program_or_404(program_id: str) -> ProgramManifest:
        program = registry().get(program_id)
        if program is None:
            raise KeyError(program_id)
        return program

    # ------------------------------------------------------------------ 홈
    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        database = db()
        names = {p.id: p.name for p in registry().programs}
        return page(
            request, "home.html",
            title="대시보드",
            summary=database.summary(),
            recent_runs=database.list_runs(limit=8),
            tasks=checklist(database, registry(),
                            api_key_set=bool(ANTHROPIC_API_KEY),
                            default_code=auth.is_default_code()),
            monthly=monthly_chart(database.monthly_revenue(12)),
            by_program=program_chart(database.revenue_by_program(), names),
            last_runs=database.last_run_per_program(),
            hide_banners=True,
        )

    # ------------------------------------------------------------ 전체 검색
    @app.get("/search", response_class=HTMLResponse)
    def search_page(request: Request, q: str = ""):
        results = search_index(q, registry(), db(), DOCS_DIR)
        return page(
            request, "search.html",
            title="검색",
            q=q,
            results=results,
            total=sum(len(rows) for rows in results.values()),
        )

    # ---------------------------------------------------------- 실행 이력
    @app.get("/runs", response_class=HTMLResponse)
    def run_list(request: Request, program: str = "", status: str = "",
                 mode: str = "", page_no: int = 1):
        per_page = 30
        page_no = max(1, page_no)
        database = db()
        total = database.count_runs(program, status, mode)
        rows = database.search_runs(program, status, mode,
                                    limit=per_page, offset=(page_no - 1) * per_page)
        return page(
            request, "runs.html",
            title="실행 이력",
            runs=rows,
            total=total,
            page_no=page_no,
            pages=max(1, -(-total // per_page)),
            filters={"program": program, "status": status, "mode": mode},
            names={p.id: p.name for p in registry().programs},
        )

    @app.post("/reload")
    def reload_registry():
        registry().reload()
        return RedirectResponse("/", status_code=303)

    # -------------------------------------------------------- 프로그램 열람
    @app.get("/programs/{program_id}", response_class=HTMLResponse)
    def program_view(request: Request, program_id: str):
        program = program_or_404(program_id)
        return page(
            request, "program_view.html",
            title=program.name,
            program=program,
            tab="view",
            licenses=db().list_licenses(program_id=program_id),
            runs=db().list_runs(program_id, limit=5),
        )

    # -------------------------------------------------------- 프로그램 수정
    @app.get("/programs/{program_id}/edit", response_class=HTMLResponse)
    def program_edit(request: Request, program_id: str, saved: str = "", error: str = ""):
        program = program_or_404(program_id)
        stored = db().get_program_settings(program_id)
        values = {**program.default_settings(), **stored}
        return page(
            request, "program_edit.html",
            title=f"{program.name} 수정",
            program=program, tab="edit", values=values, saved=saved, error=error,
        )

    @app.post("/programs/{program_id}/settings")
    async def save_settings(request: Request, program_id: str):
        program = program_or_404(program_id)
        form = await request.form()
        for spec in program.settings:
            if spec.type == "boolean":
                db().set_program_setting(program_id, spec.key, "1" if form.get(spec.key) else "0")
            elif spec.key in form:
                db().set_program_setting(program_id, spec.key, str(form[spec.key]))
        return RedirectResponse(f"/programs/{program_id}/edit?saved=설정", status_code=303)

    @app.get("/programs/{program_id}/file", response_class=HTMLResponse)
    def file_edit(request: Request, program_id: str, path: str, saved: str = ""):
        program = program_or_404(program_id)
        spec = next((f for f in program.editable_files if f.path == path), None)
        if spec is None:
            return RedirectResponse(
                f"/programs/{program_id}/edit?error=편집 대상이 아닌 파일입니다", status_code=303
            )
        target = program.resolve(path)
        content = target.read_text(encoding="utf-8") if target.is_file() else ""
        return page(
            request, "file_edit.html",
            title=spec.label, program=program, tab="edit",
            spec=spec, content=content, saved=saved,
        )

    @app.post("/programs/{program_id}/file")
    def file_save(program_id: str, path: str = Form(...), content: str = Form(...)):
        program = program_or_404(program_id)
        spec = next((f for f in program.editable_files if f.path == path), None)
        if spec is None:
            return RedirectResponse(
                f"/programs/{program_id}/edit?error=편집 대상이 아닌 파일입니다", status_code=303
            )
        target = program.resolve(path)
        # 실수로 날리는 것을 막기 위해 직전 내용을 .bak 으로 남긴다.
        if target.is_file():
            target.with_suffix(target.suffix + ".bak").write_text(
                target.read_text(encoding="utf-8"), encoding="utf-8"
            )
        target.write_text(content.replace("\r\n", "\n"), encoding="utf-8")
        return RedirectResponse(
            f"/programs/{program_id}/file?path={path}&saved=1", status_code=303
        )

    # ------------------------------------------------------ 프로그램 테스트
    @app.get("/programs/{program_id}/test", response_class=HTMLResponse)
    def program_test(request: Request, program_id: str, run: int | None = None):
        program = program_or_404(program_id)
        outcome = db().get_run(run) if run else None
        return page(
            request, "program_test.html",
            title=f"{program.name} 테스트",
            program=program, tab="test", outcome=outcome,
            members=db().list_members(),
            runs=db().list_runs(program_id, limit=10),
        )

    @app.post("/programs/{program_id}/test")
    def program_run(program_id: str, mode: str = Form("dry"), member_id: str = Form("")):
        program = program_or_404(program_id)
        overrides = db().get_program_settings(program_id)
        env = {key: value for key, value in overrides.items() if key.isupper()}
        if env.get("AI_LABEL") == "0":
            env["AI_LABEL"] = "0"
        try:
            outcome = run_program(
                program, db(), mode=mode,
                member_id=int(member_id) if member_id else None,
                env_overrides=env,
            )
        except RunError as exc:
            run_id = db().start_run(program_id, mode)
            db().finish_run(run_id, "failed", -1, str(exc))
            return RedirectResponse(
                f"/programs/{program_id}/test?run={run_id}", status_code=303
            )
        return RedirectResponse(
            f"/programs/{program_id}/test?run={outcome.run_id}", status_code=303
        )

    @app.get("/programs/{program_id}/outputs", response_class=HTMLResponse)
    def program_outputs(request: Request, program_id: str, run: int):
        """실행 결과로 생긴 산출물 목록과 미리보기."""
        program = program_or_404(program_id)
        record = db().get_run(run)
        files: list[dict[str, Any]] = []
        if record and record["output_dir"]:
            root = Path(record["output_dir"])
            if root.is_dir():
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        files.append({
                            "name": str(path.relative_to(root)),
                            "size": path.stat().st_size,
                            "full": str(path),
                        })
        return page(
            request, "program_outputs.html",
            title="산출물", program=program, tab="test", record=record, files=files,
        )

    @app.get("/preview", response_class=HTMLResponse)
    def preview(path: str):
        """산출물 파일 하나를 브라우저에서 본다. 산출물 폴더 밖은 막는다.

        글자로 앞부분만 견주면 `outputs` 를 허용할 때 `outputs-남의폴더` 까지
        통과한다. 경로 조각 단위로 견주는 `is_relative_to` 를 쓴다.
        """
        target = Path(path).resolve()
        roots = [
            (item.directory / (item.run.output_dir if item.run else "outputs")).resolve()
            for item in registry().programs
        ]
        allowed = any(target.is_relative_to(root) for root in roots)
        if not allowed or not target.is_file():
            return HTMLResponse("<p>볼 수 없는 파일입니다.</p>", status_code=403)
        text = target.read_text(encoding="utf-8", errors="replace")
        if target.suffix == ".html":
            return HTMLResponse(text)
        if target.suffix == ".md":
            return HTMLResponse(
                f'<link rel="stylesheet" href="/static/style.css">'
                f'<article class="wrap prose">{render_markdown(text)}</article>'
            )
        return HTMLResponse(
            f'<link rel="stylesheet" href="/static/style.css">'
            f'<pre class="wrap">{html.escape(text)}</pre>'
        )

    # ---------------------------------------------------------- 실행 이력
    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail(request: Request, run_id: int):
        record = db().get_run(run_id)
        program = registry().get(record["program_id"]) if record else None
        return page(
            request, "run_detail.html",
            title=f"실행 #{run_id}", record=record, program=program, tab="test",
        )

    # ------------------------------------------------------------ 회원관리
    @app.get("/members", response_class=HTMLResponse)
    def members(request: Request, q: str = ""):
        return page(
            request, "members.html",
            title="회원관리", members=db().list_members(q), q=q,
        )

    @app.post("/members")
    def member_add(name: str = Form(...), email: str = Form(...), phone: str = Form(""),
                   source: str = Form(""), memo: str = Form("")):
        member_id = db().add_member(name, email, phone, source, memo)
        return RedirectResponse(f"/members/{member_id}", status_code=303)

    @app.get("/members/{member_id}", response_class=HTMLResponse)
    def member_detail(request: Request, member_id: int):
        member = db().get_member(member_id)
        if member is None:
            return RedirectResponse("/members", status_code=303)
        return page(
            request, "member_detail.html",
            title=member["name"], member=member,
            licenses=db().list_licenses(member_id=member_id),
            notes=db().list_notes(member_id),
            runs=[r for r in db().list_runs(limit=200) if r["member_id"] == member_id][:10],
        )

    @app.post("/members/{member_id}")
    def member_update(member_id: int, name: str = Form(...), email: str = Form(...),
                      phone: str = Form(""), source: str = Form(""), memo: str = Form("")):
        db().update_member(member_id, name=name, email=email, phone=phone,
                           source=source, memo=memo)
        return RedirectResponse(f"/members/{member_id}", status_code=303)

    @app.post("/members/{member_id}/delete")
    def member_delete(member_id: int):
        db().delete_member(member_id)
        return RedirectResponse("/members", status_code=303)

    @app.post("/members/{member_id}/licenses")
    def license_add(member_id: int, program_id: str = Form(...), plan: str = Form(""),
                    price: int = Form(0), expires_at: str = Form(""),
                    retainer: int = Form(0), memo: str = Form("")):
        db().add_license(member_id, program_id, plan, price, expires_at, retainer, memo)
        return RedirectResponse(f"/members/{member_id}", status_code=303)

    @app.post("/licenses/{license_id}/status")
    def license_status(license_id: int, member_id: int = Form(...), status: str = Form(...)):
        db().set_license_status(license_id, status)
        return RedirectResponse(f"/members/{member_id}", status_code=303)

    @app.post("/members/{member_id}/notes")
    def note_add(member_id: int, body: str = Form(...)):
        if body.strip():
            db().add_note(member_id, body)
        return RedirectResponse(f"/members/{member_id}", status_code=303)

    @app.get("/programs/{program_id}/members", response_class=HTMLResponse)
    def program_members(request: Request, program_id: str):
        program = program_or_404(program_id)
        # 접속키를 **역할별로 갈라** 보여 준다. 관리자 권한을 판 사람과
        # 그냥 쓰는 고객은 아예 다른 사람이라, 한 표에 섞으면 누구에게
        # 무엇을 팔았는지가 안 보인다.
        keys = KeyAuth(db().path)
        primary = keys.list_keys(kind=KIND_PRIMARY, program_id=program_id)
        return page(
            request, "program_members.html",
            title=f"{program.name} 회원", program=program, tab="members",
            licenses=db().list_licenses(program_id=program_id),
            all_members=db().list_members(),
            key_admins=[row for row in primary if row.role == ROLE_ADMIN],
            key_clients=[row for row in primary if row.role != ROLE_ADMIN],
            key_devices=keys.list_keys(kind=KIND_SECONDARY, program_id=program_id),
            keyserver_on=bool(keyclient.admin_page_url()),
        )

    # ------------------------------------------------------------ 기타 설정
    @app.get("/settings", response_class=HTMLResponse)
    def settings_view(request: Request, saved: str = "", error: str = ""):
        values = {item["key"]: item["default"] for item in GLOBAL_SETTINGS}
        values.update(db().all_settings())
        return page(
            request, "settings.html",
            title="기타 설정", specs=GLOBAL_SETTINGS, values=values,
            banned=banned_phrases.BANNED, db_path=str(db().path),
            saved=saved, error=error,
            key_counts=KeyAuth(db().path).counts(),
            live_sessions=KeyAuth(db().path).live_sessions(),
        )

    @app.post("/settings")
    async def settings_save(request: Request):
        form = await request.form()
        for item in GLOBAL_SETTINGS:
            if item["type"] == "boolean":
                db().set_setting(item["key"], "1" if form.get(item["key"]) else "0")
            elif item["key"] in form:
                db().set_setting(item["key"], str(form[item["key"]]))
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.get("/keys", response_class=HTMLResponse)
    def keys_overview(request: Request, saved: str = "", error: str = ""):
        """16종 접속키 한눈에 — **키를 만드는 자리로 가는 길.**

        키 발급은 프로그램 안(`/apps/<상품>/admin/t/keys`)에 있다. 프로그램마다
        키가 따로라서 그게 맞는 자리인데, 통합 대시보드 왼쪽에 아무 흔적이
        없으면 **거기 있는 줄을 모른다.** 실제로 못 찾으셨다. 그래서 낸다.
        """
        keys = KeyAuth(db().path)
        rows = []
        for program in registry().programs:
            primary = keys.list_keys(kind=KIND_PRIMARY, program_id=program.id)
            rows.append({
                "program": program,
                # 판 것과 산 사람들이 자기 고객에게 준 것을 갈라 센다.
                "sold": sum(1 for row in primary if row.is_admin),
                "clients": sum(1 for row in primary if not row.is_admin),
                "live": keys.live_sessions(program_id=program.id),
            })
        # 발급한 키가 어디에 남는지가 화면마다 달라 보이면 안 된다.
        # 지금 키 서버가 붙어 있는지 그대로 넘겨 화면이 말하게 한다.
        server = keyclient.from_env()
        return page(request, "keys.html", title="접속키",
                    keyserver_on=server is not None,
                    rows=rows, counts=keys.counts(), live=keys.live_sessions(),
                    saved=saved, error=error)

    @app.post("/keys/reset")
    async def keys_reset_all(request: Request):
        """16종의 접속키를 한 번에 비운다.

        프로그램마다 들어가 지우면 열여섯 번이다. 아직 아무것도 안 파셨을 때
        한 번에 정리하시라고 둔다. 프로그램 하나만 비우는 것은 그 프로그램의
        접속키 화면에 따로 있다.
        """
        form = await request.form()
        try:
            count = KeyAuth(db().path).reset_all(str(form.get("confirm") or ""))
        except KeyError_ as exc:
            return RedirectResponse(f"/keys?error={exc}", status_code=303)
        return RedirectResponse(
            f"/keys?saved=접속키 {count}개를 모두 지웠습니다", status_code=303)

    @app.get("/backup.db")
    def backup_download():
        """고객 DB 를 한 벌 내려받는다. 접속 코드가 있어야 열린다.

        클라우드에 올려 두면 고객 이름·이메일·발급한 키가 전부 그쪽에만
        있다. 호스팅 계정이 잠기면 판 키의 목록이 통째로 사라지므로,
        집 컴퓨터로 한 벌 받아 두는 길을 둔다.

        `tools/home/클라우드_백업받기.bat` 이 이 주소를 부른다.
        """
        name = backup_name()
        temp = Path(tempfile.gettempdir()) / f"cash-flow-{name}"
        copy_db(db().path, temp)
        return FileResponse(
            temp, filename=name, media_type="application/x-sqlite3",
            # 다 보내고 나면 임시 파일을 지운다. 서버에 고객 DB 사본이
            # 쌓이면 그것 자체가 새어 나갈 자리가 된다.
            background=BackgroundTask(temp.unlink, missing_ok=True))

    @app.post("/settings/keys/reset")
    async def settings_keys_reset(request: Request):
        """예전 주소. 접속키는 /keys 로 옮겼다."""
        # 예전 주소. 접속키 이야기는 전부 /keys 로 모았다.
        # 307 은 POST 를 그대로 넘기므로 받는 쪽도 POST 자리여야 한다.
        # /keys 로 보내면 그쪽은 GET 전용이라 405 가 난다.
        return RedirectResponse("/keys/reset", status_code=307)

    # ---------------------------------------------------- 설정 한눈에
    @app.get("/config", response_class=HTMLResponse)
    def config_overview(request: Request):
        """프로그램마다 흩어진 설정·파일·매뉴얼을 한 장에 모아 보여 준다.

        여기서는 **읽기만** 한다. 고치는 곳은 각 프로그램의 '수정' 탭이다.
        """
        configs = collect_config(registry(), db())
        return page(
            request, "config.html",
            title="설정 한눈에",
            configs=configs,
            envs=env_rows(),
            globals_specs=GLOBAL_SETTINGS,
            globals_values={**{item["key"]: item["default"] for item in GLOBAL_SETTINGS},
                            **db().all_settings()},
            db_path=str(db().path),
        )

    # ---------------------------------------------------------- 수입 현황
    @app.get("/revenue", response_class=HTMLResponse)
    def revenue_view(request: Request):
        """한 번 받는 돈과 **매달 들어오는 돈**을 나눠 본다.

        대행업으로 넘어가면 이 구분이 사업의 성격을 정한다. 일회성만 있으면
        매달 새 고객을 찾아야 하고, 고정 수입이 쌓이면 그럴 필요가 준다.
        """
        summary = db().summary()
        retainers = db().retainer_licenses()
        monthly = db().monthly_revenue(12)
        by_program = db().revenue_by_program()
        names = {program.id: program.name for program in registry().programs}

        one_time = sum(row["amount"] for row in by_program)
        recurring = summary["retainer"]
        return page(
            request, "revenue.html",
            title="수입 현황",
            summary=summary,
            retainers=retainers,
            monthly=monthly,
            monthly_chart=monthly_chart(monthly),
            by_program=by_program,
            names=names,
            one_time=one_time,
            recurring=recurring,
            yearly=recurring * 12,
            share=round(recurring * 12 / (one_time + recurring * 12) * 100, 1)
            if (one_time or recurring) else 0.0,
            expiring=db().expiring_licenses(30),
        )

    # ------------------------------------------------------ 권한·환경 점검
    @app.get("/access", response_class=HTMLResponse)
    def access_view(request: Request):
        """**집 컴퓨터에서 되나, 무슨 권한이 필요한가.**

        돈보다 자주 발목을 잡는 것은 심사 기간이다. 카드는 바로 긁히지만
        API 심사는 못 당긴다. 그래서 '받는 데 걸리는 시간' 을 따로 세운다.
        """
        rows = collect_access(registry())
        return page(
            request, "access.html",
            title="권한·환경 점검",
            rows=rows,
            summary=access_summary(rows),
        )

    # -------------------------------------------------------- 정기 실행
    @app.get("/schedule", response_class=HTMLResponse)
    def schedule_view(request: Request):
        """되풀이해 돌려야 하는 프로그램이 제때 돌고 있는지 본다.

        **여기서 돌리지는 않는다.** 스케줄러는 cron 이나 n8n 이고, 대시보드는
        꺼져 있을 수 있다. 실행을 이 화면에 두면 대시보드를 안 켠 날 일이 빈다.
        """
        rows = collect_schedule(registry(), db())
        return page(
            request, "schedule.html",
            title="정기 실행",
            rows=rows,
            summary=schedule_summary(rows),
            recurring=[row for row in rows if row.recurring],
            manual=[row for row in rows if not row.recurring],
        )

    # ---------------------------------------------------------- 규정 점검
    @app.get("/rules", response_class=HTMLResponse)
    def rules_view(request: Request):
        """법·정책 장치가 프로그램마다 붙어 있는지 본다.

        **장치가 있는지**를 보는 화면이지 잘 도는지를 보는 화면이 아니다.
        그건 테스트가 한다. 그래서 무엇을 찾았는지를 같이 보여 준다.
        """
        reports = compliance_audit(registry())
        return page(
            request, "rules.html",
            title="규정 점검",
            reports=reports,
            rules=COMPLIANCE_RULES,
            trouble=[r for r in reports if r.bad],
            unsure=[r for r in reports if r.unknown and not r.bad],
        )

    # -------------------------------------------------------------- 매뉴얼
    @app.get("/manual", response_class=HTMLResponse)
    def manual_hub(request: Request):
        return page(request, "manual_hub.html", title="매뉴얼")

    @app.get("/manual/{audience}", response_class=HTMLResponse)
    def manual(request: Request, audience: str):
        filename = {"admin": "admin-manual.md", "client": "client-manual.md"}.get(audience)
        if filename is None:
            return RedirectResponse("/manual", status_code=303)
        path = DOCS_DIR / filename
        body = path.read_text(encoding="utf-8") if path.is_file() else "# 준비 중입니다"
        heading = "관리자 매뉴얼" if audience == "admin" else "클라이언트 매뉴얼"
        return page(request, "manual.html", title=heading, heading=heading, body=body)

    @app.get("/programs/{program_id}/manual/{audience}", response_class=HTMLResponse)
    def program_manual(request: Request, program_id: str, audience: str):
        program = program_or_404(program_id)
        relative = program.manuals.admin if audience == "admin" else program.manuals.client
        heading = f"{program.name} — {'관리자' if audience == 'admin' else '클라이언트'} 매뉴얼"
        if not relative:
            body = "# 이 프로그램에는 아직 매뉴얼이 없습니다"
        else:
            path = program.resolve(relative)
            body = path.read_text(encoding="utf-8") if path.is_file() else "# 매뉴얼 파일을 찾지 못했습니다"
        return page(
            request, "manual.html",
            title=heading, heading=heading, body=body, program=program, tab="manual",
            audience=audience,
        )

    # -------------------------------------- 상품별 웹 화면 (관리자/클라이언트)
    console_for = register_apps(app, page, registry, db, program_or_404)
    # 클라이언트 문. 대시보드 접속 코드 없이 **이중키만으로** 들어온다.
    register_door(app, templates, registry, db, program_or_404, console_for)

    # ------------------------------------------------------------ 오류 처리
    @app.exception_handler(KeyError)
    def program_not_found(request: Request, exc: KeyError):
        return HTMLResponse(
            '<link rel="stylesheet" href="/static/style.css">'
            '<article class="wrap prose"><h1>등록되지 않은 프로그램입니다</h1>'
            '<p><a href="/">대시보드로 돌아가기</a></p></article>',
            status_code=404,
        )

    return app


app = create_app()
