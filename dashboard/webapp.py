"""상품별 웹 화면 — `/apps/<상품>/admin` 과 `/apps/<상품>/client`.

통합 대시보드와 **다른 껍데기**를 쓴다. 고객에게 보여 줄 화면에 내 회원 목록
메뉴가 붙어 있으면 안 되기 때문이다. 대신 껍데기 맨 위에 **항상**

    ← 통합 대시보드   [관리자 모드] [클라이언트 모드]

가 붙는다. 어느 화면에서든 돌아갈 수 있고, 두 모드를 눌러 가며 견줄 수 있다.

실행은 통합 대시보드와 같은 `core.runner` 를 쓴다. 화면이 둘이라고 실행이
둘이면 "관리자에서는 되는데 클라이언트에서는 안 된다" 가 생긴다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.db import Database
from core.manifest import ProgramManifest
from core.registry import Registry
from core.runner import RunError, run_program
from core.webui import MODE_LABEL, MODES, load_handler, load_webui

__all__ = ["register", "APPS_PREFIX"]

APPS_PREFIX = "/apps"

#: 클라이언트 화면에서 실제 실행을 막을지. 기본은 막는다.
#: 산 사람이 실수로 API 비용을 쓰는 일을 만들지 않는다.
CLIENT_REAL_RUN = False


def _mode_or_404(mode: str) -> str:
    if mode not in MODES:
        raise KeyError(f"모르는 모드입니다: {mode}")
    return mode


def register(app, page, registry, db, program_or_404) -> None:
    """통합 대시보드 앱에 상품별 화면 라우트를 붙인다.

    Args:
        app: FastAPI 앱.
        page: 통합 대시보드의 템플릿 렌더 함수 (로그인·공통 컨텍스트 포함).
        registry: `Registry` 를 돌려주는 함수.
        db: `Database` 를 돌려주는 함수.
        program_or_404: 상품 id 로 매니페스트를 찾는 함수.
    """

    def _ui(program: ProgramManifest, database: Database):
        stored = database.get_program_settings(program.id)
        return load_webui(program, {"settings": stored, "db": database})

    def _context(request: Request, program: ProgramManifest, mode: str,
                 **extra: Any) -> dict:
        database = db()
        ui = _ui(program, database)
        stored = {**program.default_settings(), **database.get_program_settings(program.id)}
        return {
            "program": program,
            "mode": mode,
            "mode_label": MODE_LABEL[mode],
            "other_mode": "client" if mode == "admin" else "admin",
            "other_label": MODE_LABEL["client" if mode == "admin" else "admin"],
            "ui": ui,
            "panels": ui.panels(mode),
            "intro": ui.intro(mode),
            "values": stored,
            "runs": database.list_runs(program.id, limit=5),
            "client_real_run": CLIENT_REAL_RUN,
            **extra,
        }

    # ------------------------------------------------------------ 화면
    @app.get(APPS_PREFIX + "/{program_id}/{mode}", response_class=HTMLResponse)
    def app_view(request: Request, program_id: str, mode: str,
                 run: int | None = None, saved: str = "", error: str = ""):
        """상품 화면. 모드에 따라 보이는 것이 다르다."""
        program = program_or_404(program_id)
        mode = _mode_or_404(mode)
        outcome = db().get_run(run) if run else None
        return page(
            request, "app_shell.html",
            title=f"{program.name} — {MODE_LABEL[mode]}",
            **_context(request, program, mode,
                       outcome=outcome, saved=saved, error=error),
        )

    # ------------------------------------------------------------ 실행
    @app.post(APPS_PREFIX + "/{program_id}/{mode}/run")
    async def app_run(request: Request, program_id: str, mode: str):
        program = program_or_404(program_id)
        mode = _mode_or_404(mode)
        form = await request.form()
        wanted = str(form.get("run_mode") or "dry")

        # 클라이언트 화면에서 실제 실행을 막는 곳. 화면을 숨기는 것만으로는
        # 부족하다. 주소를 직접 쳐서 들어오는 길까지 여기서 닫는다.
        if mode == "client" and wanted == "real" and not CLIENT_REAL_RUN:
            return RedirectResponse(
                f"{APPS_PREFIX}/{program_id}/client"
                f"?error=클라이언트 화면에서는 실제 실행을 하지 않습니다",
                status_code=303)

        input_path = str(form.get("input_path") or "").strip() or None
        try:
            outcome = run_program(program, db(), mode=wanted, input_path=input_path)
        except RunError as exc:
            return RedirectResponse(
                f"{APPS_PREFIX}/{program_id}/{mode}?error={exc}", status_code=303)
        return RedirectResponse(
            f"{APPS_PREFIX}/{program_id}/{mode}?run={outcome.run_id}", status_code=303)

    # ------------------------------------------------------------ 설정 저장
    @app.post(APPS_PREFIX + "/{program_id}/{mode}/settings")
    async def app_settings(request: Request, program_id: str, mode: str):
        program = program_or_404(program_id)
        mode = _mode_or_404(mode)
        form = await request.form()
        database = db()

        allowed = {spec.key for spec in program.settings}
        if mode == "client":
            # 고객 화면에서는 키·모델 같은 값을 못 바꾼다. 화면에 안 그리는
            # 것과 별개로, 넘어와도 여기서 버린다.
            ui = _ui(program, database)
            panel = next((item for item in ui.client if item.key == "settings"), None)
            allowed = {field.key for field in (panel.fields if panel else [])}

        saved = 0
        for key, value in form.items():
            if key in allowed:
                database.set_program_setting(program.id, key, value)
                saved += 1
        return RedirectResponse(
            f"{APPS_PREFIX}/{program_id}/{mode}?saved={saved}", status_code=303)

    # ------------------------------------------- 상품이 직접 처리하는 동작
    @app.post(APPS_PREFIX + "/{program_id}/{mode}/do/{action}")
    async def app_do(request: Request, program_id: str, mode: str, action: str):
        """`do:이름` 패널의 폼을 상품의 `handle()` 로 넘긴다.

        기록표 한 줄 채우기, 견적 다시 계산하기처럼 **그 상품에만 있는 일**을
        여기서 받는다. 껍데기는 무슨 일인지 모르고, 상품만 안다.
        """
        program = program_or_404(program_id)
        mode = _mode_or_404(mode)
        handler = load_handler(program)
        if handler is None:
            return RedirectResponse(
                f"{APPS_PREFIX}/{program_id}/{mode}?error=이 상품에는 그 동작이 없습니다",
                status_code=303)

        form = dict(await request.form())
        database = db()
        ctx = {"settings": database.get_program_settings(program.id),
               "db": database, "mode": mode}
        try:
            query = handler(program, ctx, action, form) or ""
        except Exception as exc:   # 상품 코드가 깨져도 화면은 살아 있어야 한다
            query = f"error={exc}"
        joiner = "&" if query else ""
        return RedirectResponse(
            f"{APPS_PREFIX}/{program_id}/{mode}?{query}{joiner}".rstrip("&?"),
            status_code=303)

    # ------------------------------------------------------ 파일 편집(관리자만)
    @app.get(APPS_PREFIX + "/{program_id}/admin/file", response_class=HTMLResponse)
    def app_file(request: Request, program_id: str, path: str, saved: str = ""):
        program = program_or_404(program_id)
        try:
            target = program.resolve(path)
        except ValueError as exc:
            # 폴더 밖을 가리키는 경로. 고장이 아니라 거절이므로 안내로 돌려보낸다.
            return RedirectResponse(
                f"{APPS_PREFIX}/{program_id}/admin?error={exc}", status_code=303)
        spec = next((item for item in program.editable_files if item.path == path), None)
        return page(
            request, "app_file.html",
            title=f"{program.name} — {path}",
            **_context(request, program, "admin",
                       file_path=path, file_spec=spec,
                       content=target.read_text(encoding="utf-8") if target.is_file() else "",
                       exists=target.is_file(), saved=saved),
        )

    @app.post(APPS_PREFIX + "/{program_id}/admin/file")
    def app_file_save(program_id: str, path: str = Form(...), content: str = Form(...)):
        program = program_or_404(program_id)
        try:
            target = program.resolve(path)
        except ValueError as exc:
            return RedirectResponse(
                f"{APPS_PREFIX}/{program_id}/admin?error={exc}", status_code=303)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return RedirectResponse(
            f"{APPS_PREFIX}/{program_id}/admin/file?path={path}&saved=1", status_code=303)
