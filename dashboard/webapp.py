"""상품별 웹 화면 — `/apps/<상품>/admin` 과 `/apps/<상품>/client`.

통합 대시보드와 **다른 껍데기**를 쓴다. 고객에게 보여 줄 화면에 내 회원 목록
메뉴가 붙어 있으면 안 되기 때문이다. 대신 껍데기 맨 위에 **항상**

    ← 통합 대시보드   [관리자 모드] [클라이언트 모드]

가 붙는다. 어느 화면에서든 돌아갈 수 있고, 두 모드를 눌러 가며 견줄 수 있다.

실행은 통합 대시보드와 같은 `core.runner` 를 쓴다. 화면이 둘이라고 실행이
둘이면 "관리자에서는 되는데 클라이언트에서는 안 된다" 가 생긴다.

탭마다 주소가 따로 있다
-----------------------

`/apps/<상품>/<모드>/t/<탭>` 이다. 이렇게 둔 이유는 세 가지다.

1. **따로 열 수 있다.** 접속키 화면만 팝업으로 띄워 놓고 발급할 수 있다
2. **자리를 가리킬 수 있다.** "접속키 탭 보세요" 대신 주소를 보내면 된다
3. **뒤로가기가 맞는다.** 탭이 한 주소에 다 들어 있으면 브라우저 뒤로가기가
   탭이 아니라 화면 전체를 되돌려 버린다

주소가 곧 자리이므로, 나중에 프로그램을 팔아 남의 서버에 올려도 안내문에 적은
주소가 그대로 살아 있다.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core import console as console_mod
from dashboard.clientdoor import DOOR_PREFIX
from core import presets as presets_mod
from core import schedule as schedule_mod
from core.db import Database
from core import keyclient
from core.keyauth import (
    DEFAULT_BULK, KIND_LEGACY, KIND_PRIMARY, KIND_SECONDARY, ROLE_ADMIN,
    KeyAuth, KeyError_, manual_for_mail)
from core.keymail import mail_html, manual_html
from core.manifest import ProgramManifest
from core.registry import Registry
from core.runner import RunError, run_program
from core.webui import (
    MODE_LABEL, MODES, load_console, load_handler, load_webui,
)

__all__ = ["register", "APPS_PREFIX"]

APPS_PREFIX = "/apps"

#: 클라이언트 화면에서 실제 실행을 막을지. 기본은 막는다.
#: 산 사람이 실수로 API 비용을 쓰는 일을 만들지 않는다.
CLIENT_REAL_RUN = False


def _mode_or_404(mode: str) -> str:
    if mode not in MODES:
        raise KeyError(f"모르는 모드입니다: {mode}")
    return mode


def register(app, page, registry, db, program_or_404):
    """통합 대시보드 앱에 상품별 화면 라우트를 붙인다.

    Args:
        app: FastAPI 앱.
        page: 통합 대시보드의 템플릿 렌더 함수 (로그인·공통 컨텍스트 포함).
        registry: `Registry` 를 돌려주는 함수.
        db: `Database` 를 돌려주는 함수.
        program_or_404: 상품 id 로 매니페스트를 찾는 함수.

    Returns:
        `(program, database, mode)` 로 콘솔을 만드는 함수. 클라이언트 문이
        **같은 것**을 쓰게 하려고 돌려준다. 문이 자기 콘솔을 따로 만들면
        관리자 화면과 어긋나기 시작한다.
    """

    #: 방금 발급한 키를 한 번 보여 주려고 잠깐 들고 있는 자리.
    _fresh: dict[str, Any] = {}

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

    # --------------------------------------------------------- 콘솔 만들기
    def _console(program: ProgramManifest, database: Database, mode: str):
        """이 프로그램의 운영 콘솔. 없으면 기존 화면을 감싸 만든다."""
        stored = database.get_program_settings(program.id)
        ctx = {"settings": stored, "db": database, "mode": mode}
        built = load_console(program, ctx)
        if built is None:
            built = console_mod.from_webui(program, _ui(program, database), ctx)
        console_mod.add_standard_tabs(built, program)
        return built

    def _keys() -> KeyAuth:
        """접속키 저장소. 대시보드와 같은 SQLite 파일을 쓴다."""
        return KeyAuth(db().path)

    def _stash(value: Any) -> str:
        """방금 만든 키를 **한 번만** 꺼내 볼 수 있게 넣어 둔다.

        키를 주소에 실으면 브라우저 기록과 서버 접근 로그에 그대로 남는다.
        발급 화면은 새로고침 한 번이면 지나가는 자리라 메모리에 두고, 꺼내는
        순간 지운다. 서버를 다시 띄우면 사라지는데 그래도 된다 — 목록에는
        남아 있고, 잃어버린 키는 다시 발급하는 것이 맞다.
        """
        token = secrets.token_urlsafe(8)
        _fresh[token] = value
        while len(_fresh) > 32:           # 안 꺼내 간 것이 쌓이지 않게
            _fresh.pop(next(iter(_fresh)))
        return token

    def _console_context(request: Request, program: ProgramManifest, mode: str,
                         tab_key: str = "", **extra: Any) -> dict:
        database = db()
        full = _console(program, database, mode)
        shown = full.for_mode(mode)

        current = shown.tab(tab_key) if tab_key else shown.first_tab()
        if current is None:
            current = shown.first_tab()

        base = _context(request, program, mode, **extra)
        base.update({
            "console": shown,
            "current": current,
            "is_home": bool(current and current is shown.first_tab()),
        })

        # 공통 탭이 쓰는 재료. 그 탭을 열었을 때만 모은다 — 매 화면마다
        # 일정·키를 다 긁으면 목록이 커질수록 화면이 느려진다.
        render = current.render if current else ""
        if render == "auto":
            rows = schedule_mod.collect(registry(), database)
            base["schedule_rows"] = [r for r in rows if r.id == program.id]
        if render == "presets":
            base["presets"] = presets_mod.collect(
                program, database.get_program_settings(program.id))
        if render == "keys":
            keys = _keys()
            쪽지 = str(request.query_params.get("issued") or "")
            보낼것 = _fresh.get(쪽지)
            base["issued"] = 보낼것
            base["issued_token"] = 쪽지 if 보낼것 else ""
            base["bulk_codes"] = _fresh.pop(
                str(request.query_params.get("bulk") or ""), None)
            want = str(request.query_params.get("k") or "primary")
            kind = KIND_SECONDARY if want == "secondary" else KIND_PRIMARY
            rows = keys.list_keys(kind=kind, program_id=program.id)
            if kind == KIND_PRIMARY:
                rows += keys.list_keys(kind=KIND_LEGACY, program_id=program.id)
            base.update({
                "key_tab": want,
                "key_rows": rows,
                "key_counts": keys.counts(program_id=program.id),
                "live_sessions": keys.live_sessions(program_id=program.id),
            })
            # 안내문에 붙일 매뉴얼. 받는 분이 관리자냐 고객이냐에 따라 다른
            # 것이 와야 한다 — 고객에게 관리자 매뉴얼을 보내면 «접속 코드
            # 관리» 처럼 그분 화면에 없는 것을 찾게 된다.
            보낼것 = base.get("issued")
            base["manual_html"] = (
                manual_html(program, 보낼것.for_admin) if 보낼것 else "")
            base["send_action"] = (
                f"{APPS_PREFIX}/{program.id}/{mode}/keys/send"
                f"?issued={base['issued_token']}")
            base["can_send"] = keyclient.from_env() is not None
            # `app_tab` 이 넘겨준 것이 있으면 그것을 쓴다.
            base.setdefault("mail_sent", "")
            base.setdefault("mail_error", "")
            base.setdefault("mail_left", None)
        return base

    # ------------------------------------------------------------ 화면
    @app.get(APPS_PREFIX + "/{program_id}/{mode}", response_class=HTMLResponse)
    def app_view(request: Request, program_id: str, mode: str,
                 run: int | None = None, saved: str = "", error: str = "",
                 flash: str = "", flash_tone: str = ""):
        """콘솔 첫 화면. 상태 타일과 오늘 할 일이 여기 있다."""
        return _render_tab(request, program_id, mode, "",
                           run=run, saved=saved, error=error,
                           flash=flash, flash_tone=flash_tone)

    @app.get(APPS_PREFIX + "/{program_id}/{mode}/t/{tab_key}",
             response_class=HTMLResponse)
    def app_tab(request: Request, program_id: str, mode: str, tab_key: str,
                run: int | None = None, saved: str = "", error: str = "",
                flash: str = "", flash_tone: str = "",
                mail_sent: str = "", mail_error: str = "", mail_left: str = ""):
        """탭 하나. **주소가 따로 있어 팝업으로 열 수 있다.**"""
        return _render_tab(request, program_id, mode, tab_key,
                           run=run, saved=saved, error=error,
                           flash=flash, flash_tone=flash_tone,
                           mail_sent=mail_sent, mail_error=mail_error,
                           mail_left=int(mail_left) if mail_left.isdigit() else None)

    def _render_tab(request: Request, program_id: str, mode: str, tab_key: str,
                    run: int | None = None, **extra: Any):
        program = program_or_404(program_id)
        mode = _mode_or_404(mode)
        outcome = db().get_run(run) if run else None
        ctx = _console_context(request, program, mode, tab_key,
                               outcome=outcome, **extra)
        current = ctx["current"]
        title = f"{program.name} — {MODE_LABEL[mode]}"
        if current and not ctx["is_home"]:
            title = f"{current.label} · {title}"
        return page(request, "console.html", title=title, **ctx)

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

    # ══════════════════════════════════════════════════ 접속키 (관리자만)
    #
    # 이 아래는 전부 `/admin/` 아래에 둔다. 클라이언트 모드에서는 주소를
    # 직접 쳐도 닿지 않는다 — 키를 발급하는 자리는 **판 사람의 것**이다.

    def _keys_back(program_id: str, tab: str = "primary", **extra) -> str:
        parts = [f"k={tab}"] + [f"{k}={v}" for k, v in extra.items() if v]
        return f"{APPS_PREFIX}/{program_id}/admin/t/keys?" + "&".join(parts)

    @app.post(APPS_PREFIX + "/{program_id}/admin/keys/issue")
    async def keys_issue(request: Request, program_id: str):
        """한 사람에게 1차키 1개 + 2차키 3개. 보낼 안내문까지 같이 만든다."""
        program = program_or_404(program_id)
        form = await request.form()
        days = str(form.get("expires_days") or "").strip()
        name = str(form.get("name") or "")
        email = str(form.get("email") or "")
        # 고객에게 보내는 주소는 **문**이다. `/apps/.../client` 는 대시보드
        # 접속 코드가 있어야 열려서, 그 주소를 적어 보내면 고객은 못 들어온다.
        door = str(request.base_url).rstrip("/") + f"{DOOR_PREFIX}/{program.id}"
        # 판매 키는 산 사람을 그 프로그램의 관리자로 만든다.
        role = str(form.get("role") or ROLE_ADMIN)
        try:
            expires_days = int(days) if days else None
        except ValueError:
            return RedirectResponse(
                _keys_back(program_id, error="유효기간은 숫자로 적어 주세요"),
                status_code=303)

        server = keyclient.from_env()
        try:
            if server is None:
                # 키 서버를 안 쓰실 때. 이 컴퓨터가 켜져 있을 때만 먹는 키다.
                issued = _keys().issue_set(
                    name=name, email=email, program_id=program.id,
                    service_url=door, expires_days=expires_days, role=role)
            else:
                # **시트에 먼저 넣는다.** 여기가 실패하면 아무것도 안 만든다.
                # 반대 순서로 하면 시트에 없는 키를 고객에게 보내게 되고,
                # 고객은 그 자리에서 "키가 틀렸다" 는 말을 듣는다.
                answer = server.issue_set(
                    program_id=program.id, name=name, email=email, role=role,
                    expires_days=expires_days, base_url=door)
                # 들어갔으니 이제 이쪽 목록에도 보이게 같은 코드로 적는다.
                issued = _keys().adopt_set(
                    primary_code=str(answer.get("primaryKey") or ""),
                    secondary=dict(answer.get("secondaryKeys") or {}),
                    name=name, email=email, program_id=program.id,
                    service_url=door, expires_days=expires_days, role=role)
        except keyclient.KeyServerError as exc:
            return RedirectResponse(
                _keys_back(program_id, error=f"키 서버: {exc}"), status_code=303)
        except (KeyError_, ValueError) as exc:
            return RedirectResponse(_keys_back(program_id, error=str(exc)),
                                    status_code=303)

        # 키 자체를 주소에 실어 보내면 브라우저 기록·서버 로그에 남는다.
        # 한 번만 쓰는 쪽지에 넣어 두고 화면에서 꺼내 보여 준다.
        token = _stash(issued)
        return RedirectResponse(_keys_back(program_id, issued=token),
                                status_code=303)

    @app.post(APPS_PREFIX + "/{program_id}/{mode}/keys/send")
    async def keys_send(request: Request, program_id: str, mode: str):
        """화면에서 **고친 그대로** 안내문을 보낸다.

        메일은 구글 앱스 스크립트가 보낸다. 우리 서버에 메일 기능을 붙이면
        SMTP 비밀번호를 하나 더 둬야 하는데, 이미 있는 것으로 된다.

        보낸 뒤에도 **키를 다시 보여 준다.** 메일이 안 갔을 수도 있고,
        카톡으로도 보내실 수 있어서 이 화면을 여기서 닫으면 안 된다.
        """
        program = program_or_404(program_id)
        mode = _mode_or_404(mode)
        form = await request.form()
        token = str(request.query_params.get("issued") or "")

        server = keyclient.from_env()
        if server is None:
            return RedirectResponse(
                _keys_back(program_id, issued=token,
                           mail_error="메일 서버가 연결되지 않았습니다. "
                                      "KEYSERVER_URL 과 KEYSERVER_PASSWORD 를 넣어 주세요"),
                status_code=303)
        # 사람이 고친 것은 **접속키 부분뿐**이다. 매뉴얼은 여기서 붙인다 —
        # 화면에서 고칠 수 없게 한 것과 같은 이유로, 넘어온 글을 믿지 않고
        # 프로그램에 든 파일을 그대로 읽어서 쓴다.
        보낼것 = _fresh.get(token)
        쓴글 = str(form.get("body") or "")
        글자매뉴얼 = (manual_for_mail(program, 보낼것.for_admin)
                      if 보낼것 else "")
        꾸민판 = (mail_html(program_name=program.name, issued=보낼것, note=쓴글,
                            manual=manual_html(program, 보낼것.for_admin))
                  if 보낼것 else "")
        try:
            answer = server.send_text(
                email=str(form.get("email") or "").strip(),
                subject=str(form.get("subject") or "").strip(),
                # 글자판은 HTML 을 못 읽는 메일 앱에서만 보인다. 한쪽만
                # 보내면 그런 앱에서 글이 통째로 안 보인다.
                body=(보낼것.plain_mail(쓴글, 글자매뉴얼) if 보낼것 else 쓴글),
                html=꾸민판,
                program_id=program.id)
        except keyclient.KeyServerError as exc:
            return RedirectResponse(
                _keys_back(program_id, issued=token, mail_error=str(exc)),
                status_code=303)
        left = answer.get("remaining")
        return RedirectResponse(
            _keys_back(program_id, issued=token, mail_sent="1",
                       mail_left="" if left is None else str(left)),
            status_code=303)

    @app.post(APPS_PREFIX + "/{program_id}/admin/keys/bulk")
    async def keys_bulk(request: Request, program_id: str):
        """이름 없이 코드만 미리. 현장에서 종이로 나눠 줄 때."""
        program = program_or_404(program_id)
        form = await request.form()
        days = str(form.get("expires_days") or "").strip()
        try:
            codes = _keys().bulk_legacy(
                count=int(form.get("count") or DEFAULT_BULK),
                program_id=program.id,
                expires_days=int(days) if days else None,
                # 판매 키는 산 사람을 그 프로그램의 관리자로 만든다.
                role=str(form.get("role") or ROLE_ADMIN),
            )
        except (KeyError_, ValueError) as exc:
            return RedirectResponse(_keys_back(program_id, error=str(exc)),
                                    status_code=303)
        return RedirectResponse(_keys_back(program_id, bulk=_stash(codes)),
                                status_code=303)

    @app.post(APPS_PREFIX + "/{program_id}/admin/keys/{key_id}/toggle")
    def keys_toggle(program_id: str, key_id: int):
        """사용중지 ↔ 사용재개. **되돌릴 수 있는 쪽**이라 확인을 묻지 않는다."""
        program_or_404(program_id)
        keys = _keys()
        try:
            row = keys.get(key_id)
            if row.status == "suspended":
                keys.resume(key_id)
                msg = f"{row.code} 를 다시 쓸 수 있게 했습니다."
            else:
                keys.suspend(key_id)
                msg = f"{row.code} 를 사용중지했습니다. 접속해 있던 기기도 끊었습니다."
        except KeyError_ as exc:
            return RedirectResponse(_keys_back(program_id, error=str(exc)),
                                    status_code=303)
        tab = "secondary" if row.kind == KIND_SECONDARY else "primary"
        return RedirectResponse(_keys_back(program_id, tab, flash=msg),
                                status_code=303)

    @app.post(APPS_PREFIX + "/{program_id}/admin/keys/{key_id}/delete")
    def keys_delete(program_id: str, key_id: int):
        """영구 삭제. 화면에서 두 번 눌러야 여기까지 온다."""
        program_or_404(program_id)
        keys = _keys()
        try:
            row = keys.get(key_id)
            removed = keys.delete(key_id)
        except KeyError_ as exc:
            return RedirectResponse(_keys_back(program_id, error=str(exc)),
                                    status_code=303)
        extra = f" (딸린 2차키 {removed - 1}개 포함)" if removed > 1 else ""
        tab = "secondary" if row.kind == KIND_SECONDARY else "primary"
        return RedirectResponse(
            _keys_back(program_id, tab,
                       flash=f"{row.code} 를 지웠습니다{extra}.", flash_tone="warn"),
            status_code=303)

    @app.post(APPS_PREFIX + "/{program_id}/admin/keys/reset")
    async def keys_reset(request: Request, program_id: str):
        """전부 지우기. '초기화' 를 정확히 쳐야 통과한다."""
        program = program_or_404(program_id)
        form = await request.form()
        try:
            count = _keys().reset_all(str(form.get("confirm") or ""),
                                      program_id=program.id)
        except KeyError_ as exc:
            return RedirectResponse(_keys_back(program_id, error=str(exc)),
                                    status_code=303)
        return RedirectResponse(
            _keys_back(program_id,
                       flash=f"키 {count}개를 모두 지웠습니다.", flash_tone="warn"),
            status_code=303)

    # ══════════════════════════════════════════ 검증값으로 되돌리기(관리자만)
    @app.post(APPS_PREFIX + "/{program_id}/admin/presets/restore")
    async def presets_restore(request: Request, program_id: str):
        """검증값으로. 키를 주면 그 값만, 안 주면 전부."""
        program = program_or_404(program_id)
        form = await request.form()
        wanted = form.getlist("key") if hasattr(form, "getlist") else []
        values = presets_mod.restore_values(program, wanted or None)

        database = db()
        for key, value in values.items():
            database.set_program_setting(program.id, key, value)

        what = "모든 값을" if not wanted else f"{len(values)}개 값을"
        return RedirectResponse(
            f"{APPS_PREFIX}/{program_id}/admin/t/presets"
            f"?flash={what} 검증값으로 되돌렸습니다.",
            status_code=303)

    return _console
