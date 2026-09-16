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

프로그램을 새로 만들면 `products/<이름>/program.yaml` 만 넣으면 된다.
이 파일은 고치지 않는다.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import markdown as md
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.db import Database, DEFAULT_DB_PATH
from core.manifest import ProgramManifest
from core.registry import Registry
from core.runner import RunError, run_program
from shared import banned_phrases
from shared.config import ANTHROPIC_API_KEY, DEFAULT_MODEL, ROOT_DIR

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = ROOT_DIR / "docs"

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
    """마크다운을 HTML 로. 표와 코드블록을 지원한다."""
    return md.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"])


def create_app(db_path: str | Path = DEFAULT_DB_PATH,
               products_dir: Path | None = None) -> FastAPI:
    """대시보드 앱을 만든다. 테스트에서는 임시 DB 경로를 넘긴다."""
    app = FastAPI(title="통합 관리자 대시보드", docs_url=None, redoc_url=None)
    app.state.db = Database(db_path)
    app.state.registry = Registry(products_dir) if products_dir else Registry()

    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    templates.env.filters["markdown"] = render_markdown
    templates.env.filters["won"] = lambda value: f"{int(value or 0):,}원"
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
        return templates.TemplateResponse(request, template, context)

    def program_or_404(program_id: str) -> ProgramManifest:
        program = registry().get(program_id)
        if program is None:
            raise KeyError(program_id)
        return program

    # ------------------------------------------------------------------ 홈
    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        recent = db().list_runs(limit=8)
        return page(
            request, "home.html",
            title="대시보드",
            summary=db().summary(),
            recent_runs=recent,
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
        """산출물 파일 하나를 브라우저에서 본다. 산출물 폴더 밖은 막는다."""
        target = Path(path).resolve()
        allowed = any(
            str(target).startswith(str((p.directory / (p.run.output_dir if p.run else "outputs")).resolve()))
            for p in registry().programs
        )
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
        return page(
            request, "program_members.html",
            title=f"{program.name} 회원", program=program, tab="members",
            licenses=db().list_licenses(program_id=program_id),
            all_members=db().list_members(),
        )

    # ------------------------------------------------------------ 기타 설정
    @app.get("/settings", response_class=HTMLResponse)
    def settings_view(request: Request, saved: str = ""):
        values = {item["key"]: item["default"] for item in GLOBAL_SETTINGS}
        values.update(db().all_settings())
        return page(
            request, "settings.html",
            title="기타 설정", specs=GLOBAL_SETTINGS, values=values,
            banned=banned_phrases.BANNED, db_path=str(db().path), saved=saved,
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
        )

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
