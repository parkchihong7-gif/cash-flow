"""관리자 웹 화면 — 대시보드 · 설정(브랜드) · 백업/복원 · 작업 기록.

로컬 PC 에서만 연다(127.0.0.1). 메뉴는 설계 5장의 순서를 따르고, 아직 없는 메뉴는
«준비 중» 으로 보이게 둔다 — 무엇이 되고 안 되는지 화면에서 바로 알게 하려고.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import COLOR_KEYS, COLOR_LABELS, OrbitDB, RestoreError, SettingError

HERE = Path(__file__).resolve().parent

#: (주소, 이름, 지금 쓸 수 있나)
MENU = [
    ("/", "대시보드", True),
    ("/products", "상품", False),
    ("/studio", "영상 제작", False),
    ("/calendar", "일정", False),
    ("/metrics", "성과", False),
    ("/settings", "설정", True),
    ("/logs", "작업 기록", True),
]


def create_app(db: OrbitDB | None = None) -> FastAPI:
    app = FastAPI(title="셀럽오르빗 관리자", docs_url=None, redoc_url=None)
    app.state.db = db or OrbitDB()
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    def page(request: Request, name: str, **ctx):
        settings = app.state.db.settings()
        ctx.update(request=request, s=settings, menu=MENU, path=request.url.path,
                   flash=request.query_params.get("msg", ""), error=request.query_params.get("error", ""))
        return templates.TemplateResponse(request, name, ctx)

    def back(path: str, msg: str = "", error: str = "") -> RedirectResponse:
        query = f"?msg={quote(msg)}" if msg else f"?error={quote(error)}" if error else ""
        return RedirectResponse(path + query, status_code=303)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        return page(request, "dashboard.html", counts=app.state.db.counts(),
                    recent=app.state.db.jobs(5))

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        return page(request, "settings.html", color_keys=COLOR_KEYS, color_labels=COLOR_LABELS)

    @app.post("/settings")
    async def settings_save(request: Request):
        form = {k: str(v) for k, v in (await request.form()).items()}
        try:
            app.state.db.save_settings(form)
        except SettingError as exc:
            return back("/settings", error=str(exc))
        return back("/settings", msg="저장했습니다")

    @app.get("/backup")
    def backup():
        data = app.state.db.backup_bytes()
        name = f"celeb-orbit-backup-{datetime.now():%Y%m%d-%H%M}.zip"
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/restore")
    async def restore(file: UploadFile = File(...), confirm: str = Form("")):
        if confirm.strip() != "복원":
            return back("/settings", error="복원하려면 확인 칸에 '복원' 이라고 적어 주세요")
        try:
            kept = app.state.db.restore_bytes(await file.read())
        except RestoreError as exc:
            return back("/settings", error=str(exc))
        return back("/settings", msg=f"복원했습니다. 이전 DB 는 {kept.name} 로 남겨 두었습니다")

    @app.get("/logs", response_class=HTMLResponse)
    def logs(request: Request):
        return page(request, "logs.html", jobs=app.state.db.jobs(200))

    @app.get("/{name}", response_class=HTMLResponse)
    def not_yet(request: Request, name: str):
        known = {path.strip("/"): label for path, label, ready in MENU if not ready}
        if name not in known:
            return HTMLResponse("없는 화면입니다", status_code=404)
        return page(request, "not_yet.html", label=known[name])

    return app
