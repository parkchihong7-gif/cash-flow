"""관리자 웹 화면 — 대시보드 · 설정(브랜드) · 백업/복원 · 작업 기록.

로컬 PC 에서만 연다(127.0.0.1). 메뉴는 설계 5장의 순서를 따르고, 아직 없는 메뉴는
«준비 중» 으로 보이게 둔다 — 무엇이 되고 안 되는지 화면에서 바로 알게 하려고.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import catalog
from .catalog import CatalogError
from .db import COLOR_KEYS, COLOR_LABELS, OrbitDB, RestoreError, SettingError

HERE = Path(__file__).resolve().parent

#: (주소, 이름, 지금 쓸 수 있나)
MENU = [
    ("/", "대시보드", True),
    ("/products", "상품", True),
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

    # ------------------------------------------------------------ ② 상품
    async def form_of(request: Request) -> dict[str, str]:
        return {k: str(v) for k, v in (await request.form()).items() if not hasattr(v, "read")}

    @app.get("/products", response_class=HTMLResponse)
    def products(request: Request):
        return page(request, "products.html", products=catalog.list_products(app.state.db),
                    categories=catalog.CATEGORIES)

    @app.post("/products")
    async def product_add(request: Request):
        form = await form_of(request)
        try:
            product_id = catalog.add_product(app.state.db, **{k: form.get(k, "") for k in
                                             ("name", "brand", "model", "category", "price", "price_source", "keyword")})
        except CatalogError as exc:
            return back("/products", error=str(exc))
        return back(f"/products/{product_id}", msg="상품을 등록했습니다. 이제 연예인과 출처를 붙이세요")

    @app.get("/products/{product_id}", response_class=HTMLResponse)
    def product_detail(request: Request, product_id: int):
        db = app.state.db
        try:
            product = catalog.get_product(db, product_id)
        except CatalogError:
            return HTMLResponse("없는 상품입니다", status_code=404)
        return page(request, "product.html", p=product, claims=catalog.list_claims(db, product_id),
                    links=catalog.list_links(db, product_id), assets=catalog.list_assets(db, product_id),
                    categories=catalog.CATEGORIES, kinds=catalog.SOURCE_KINDS, relations=catalog.RELATIONS,
                    relation_help=catalog.RELATION_HELP, licenses=catalog.LICENSES, platforms=catalog.PLATFORMS)

    @app.post("/products/{product_id}/{action}")
    async def product_action(request: Request, product_id: int, action: str):
        db, here = app.state.db, f"/products/{product_id}"
        form = await form_of(request)
        try:
            if action == "edit":
                catalog.update_product(db, product_id, **{k: form.get(k, "") for k in
                                       ("name", "brand", "model", "category", "price", "price_source",
                                        "keyword", "available")})
                msg = "저장했습니다"
            elif action == "claim":
                catalog.add_claim(db, product_id, **{k: form.get(k, "") for k in
                                  ("celebrity", "url", "title", "publisher", "published_at", "kind",
                                   "timestamp", "note")})
                msg = "관계를 '추정' 으로 등록했습니다. 출처를 열어 보고 확인 단계를 정하세요"
            elif action == "verify":
                catalog.verify_claim(db, int(form.get("claim_id", 0)), relation=form.get("relation", ""),
                                     verified_by=form.get("verified_by", ""))
                msg = "관계를 바꿨습니다"
            elif action == "link":
                catalog.add_link(db, product_id, platform=form.get("platform", ""), url=form.get("url", ""),
                                 added_by=form.get("added_by", ""))
                msg = "제휴 링크를 등록했습니다"
            elif action == "unlink":
                catalog.delete_link(db, int(form.get("link_id", 0)))
                msg = "링크를 지웠습니다"
            elif action == "image":
                upload = (await request.form()).get("file")
                if upload is None or not hasattr(upload, "read"):
                    raise CatalogError("이미지 파일을 골라 주세요")
                catalog.add_image(db, product_id, filename=upload.filename or "", data=await upload.read(),
                                  license=form.get("license", ""), license_proof=form.get("license_proof", ""))
                msg = "이미지를 등록했습니다"
            elif action == "unimage":
                catalog.delete_asset(db, int(form.get("asset_id", 0)))
                msg = "이미지를 지웠습니다"
            else:
                return back(here, error="모르는 동작입니다")
        except CatalogError as exc:
            return back(here, error=str(exc))
        return back(here, msg=msg)

    @app.get("/assets/{product_id}/{name}")
    def asset_file(product_id: int, name: str):
        root = catalog.assets_dir(app.state.db).resolve()
        path = (root / str(product_id) / name).resolve()
        if root not in path.parents or not path.is_file():
            return HTMLResponse("없는 파일입니다", status_code=404)
        return FileResponse(path)

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
