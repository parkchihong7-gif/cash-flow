"""클라이언트 문 — `/c/<상품>`.

왜 문을 따로 내는가
-------------------

통합 대시보드는 **접속 코드 하나로 통째로 잠겨** 있다. 그 안에 내 회원 목록과
매출이 있으니 당연하다. 그런데 프로그램을 판 뒤 고객이 자기 화면을 보려면
바로 그 코드가 필요해진다. 고객에게 내 대시보드 코드를 줄 수는 없다.

그래서 문을 하나 더 낸다. 이 문은 **이중키만 받는다.**

    /c/<상품>            열쇠 넣는 자리
    /c/<상품>/t/<탭>     열고 들어간 뒤의 화면 (관리자 모드에서 관리자 것만 뺀 것)

고객이 받는 안내 메일에 적히는 주소가 이것이다. 대시보드 코드는 나오지 않는다.

세 층
-----

* **메인 관리자** — 통합 대시보드. 접속 코드로 들어온다. 16종을 다 본다
* **프로그램 관리자** — 그 프로그램을 산 사람. 자기 것의 키를 발급한다
* **클라이언트** — 산 사람의 고객. 이 문으로 들어와 결과만 본다

무엇을 주의했는가
-----------------

* 세션은 **쿠키에 토큰만** 담는다. 키 자체를 담으면 쿠키를 흘리는 순간 키가 샌다
* 쿠키는 `/c/` 아래에서만 보내고 `HttpOnly` 다
* 왜 막혔는지 **이유를 말해 준다.** '다른 기기에서 로그인되어…' 를 안 알려 주면
  사람은 프로그램이 고장 났다고 생각한다
* 키가 하나도 없는 프로그램은 이 문이 열리지 않는다. 판 적 없는 것을 열어 둘
  이유가 없다
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.keyauth import KeyAuth, KeyError_
from core.webui import load_handler

__all__ = ["register", "DOOR_PREFIX", "COOKIE_PREFIX"]

DOOR_PREFIX = "/c"

#: 프로그램마다 쿠키를 따로 둔다. 한 사람이 두 프로그램을 동시에 쓸 수 있어야 한다.
COOKIE_PREFIX = "ckey_"

#: 쿠키가 살아 있는 시간(초). 세션은 서버가 따로 들고 있으므로 이건 상한일 뿐이다.
COOKIE_MAX_AGE = 60 * 60 * 12


def cookie_name(program_id: str) -> str:
    return COOKIE_PREFIX + program_id.replace("-", "_")


def register(app, templates, registry, db, program_or_404, console_for) -> None:
    """통합 대시보드 앱에 클라이언트 문을 붙인다.

    Args:
        console_for: `(program, database, mode)` 를 받아 콘솔을 돌려주는 함수.
            관리자 화면과 **같은 것**을 쓴다. 따로 만들면 한쪽만 고치게 된다.
    """

    def _keys() -> KeyAuth:
        return KeyAuth(db().path)

    def _door(request: Request, program, error: str = "", notice: str = "",
              status: int = 200) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "door.html",
            {"program": program, "error": error, "notice": notice,
             "next_tab": request.query_params.get("t", "")},
            status_code=status)

    def _session(request: Request, program_id: str) -> tuple[str, str]:
        """(토큰, 막힌 이유). 토큰이 비면 못 들어온 것이다."""
        token = request.cookies.get(cookie_name(program_id), "")
        if not token:
            return "", ""
        alive, why = _keys().check_session(token)
        return (token, "") if alive else ("", why)

    # ------------------------------------------------------------ 열쇠 넣기
    @app.get(DOOR_PREFIX + "/{program_id}", response_class=HTMLResponse)
    def door(request: Request, program_id: str, t: str = ""):
        program = program_or_404(program_id)
        token, why = _session(request, program_id)
        if token:
            return RedirectResponse(f"{DOOR_PREFIX}/{program_id}/t/{t or 'home'}",
                                    status_code=303)
        return _door(request, program, notice=why)

    @app.post(DOOR_PREFIX + "/{program_id}")
    async def door_open(request: Request, program_id: str):
        program = program_or_404(program_id)
        form = await request.form()
        try:
            token, _used = _keys().authenticate(
                primary_code=str(form.get("primary") or ""),
                secondary_code=str(form.get("secondary") or ""),
                program_id=program.id,
            )
        except KeyError_ as exc:
            # 왜 안 되는지 그대로 보여 준다. '인증 실패' 한 줄로는 사람이
            # 무엇을 고쳐야 할지 모른다.
            return _door(request, program, error=str(exc), status=401)

        wanted = str(form.get("next_tab") or "").strip() or "home"
        response = RedirectResponse(f"{DOOR_PREFIX}/{program.id}/t/{wanted}",
                                    status_code=303)
        response.set_cookie(
            cookie_name(program.id), token,
            max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax",
            path=f"{DOOR_PREFIX}/{program.id}",
        )
        return response

    @app.post(DOOR_PREFIX + "/{program_id}/out")
    def door_close(request: Request, program_id: str):
        program = program_or_404(program_id)
        token = request.cookies.get(cookie_name(program_id), "")
        if token:
            _keys().close_session(token)
        response = RedirectResponse(f"{DOOR_PREFIX}/{program.id}", status_code=303)
        response.delete_cookie(cookie_name(program.id), path=f"{DOOR_PREFIX}/{program.id}")
        return response

    # ------------------------------------------------------------ 들어온 뒤
    @app.get(DOOR_PREFIX + "/{program_id}/t/{tab_key}", response_class=HTMLResponse)
    def door_tab(request: Request, program_id: str, tab_key: str,
                 saved: str = "", error: str = "", flash: str = ""):
        program = program_or_404(program_id)
        token, why = _session(request, program_id)
        if not token:
            return _door(request, program, notice=why, status=401)

        database = db()
        full = console_for(program, database, "client")
        shown = full.for_mode("client")
        current = shown.tab("" if tab_key == "home" else tab_key) or shown.first_tab()

        return templates.TemplateResponse(
            request, "console.html",
            {
                "program": program,
                "mode": "client",
                "mode_label": "클라이언트 모드",
                "other_mode": "client",
                "other_label": "클라이언트 모드",
                "console": shown,
                "current": current,
                "is_home": bool(current and current is shown.first_tab()),
                "values": {**program.default_settings(),
                           **database.get_program_settings(program.id)},
                "runs": [],
                "outcome": None,
                "saved": saved, "error": error, "flash": flash,
                "client_real_run": False,
                # 이 문으로 들어온 사람에게는 통합 대시보드로 가는 길을 그리지 않는다.
                "through_door": True,
                "door_base": f"{DOOR_PREFIX}/{program.id}",
                "programs": [], "load_errors": [],
            })

    # ------------------------------------------------- 문 안에서 누르는 버튼
    @app.post(DOOR_PREFIX + "/{program_id}/do/{action}")
    async def door_do(request: Request, program_id: str, action: str):
        """고객이 자기 화면에서 누르는 버튼.

        관리자 화면과 **같은 `handle()`** 로 간다. 다른 길로 보내면
        "관리자에서는 되는데 고객 화면에서는 안 된다" 가 생긴다.
        모드는 `client` 로 넘기므로, 상품이 고객에게 막고 싶은 동작은
        거기서 거절하면 된다.
        """
        program = program_or_404(program_id)
        token, why = _session(request, program_id)
        if not token:
            return _door(request, program, notice=why, status=401)

        handler = load_handler(program)
        if handler is None:
            return RedirectResponse(
                f"{DOOR_PREFIX}/{program_id}/t/home?error=이 프로그램에는 그 동작이 없습니다",
                status_code=303)

        database = db()
        ctx = {"settings": database.get_program_settings(program.id),
               "db": database, "mode": "client", "through_door": True}
        try:
            query = handler(program, ctx, action, dict(await request.form())) or ""
        except Exception as exc:      # 상품이 깨져도 고객 화면은 살아 있어야 한다
            query = f"error={exc}"
        joiner = "&" if query else ""
        return RedirectResponse(
            f"{DOOR_PREFIX}/{program_id}/t/home?{query}{joiner}".rstrip("&?"),
            status_code=303)

    @app.post(DOOR_PREFIX + "/{program_id}/run")
    async def door_run(request: Request, program_id: str):
        """고객 화면에서는 **실제 실행을 하지 않는다.**

        화면에서 버튼을 감추는 것과 별개로, 주소를 직접 쳐도 막는다.
        산 사람이 모르는 새 API 비용을 쓰는 일을 만들지 않는다.
        """
        program = program_or_404(program_id)
        token, why = _session(request, program_id)
        if not token:
            return _door(request, program, notice=why, status=401)
        return RedirectResponse(
            f"{DOOR_PREFIX}/{program_id}/t/home"
            f"?error=이 화면에서는 실행하지 않습니다. 파신 분께 문의해 주세요",
            status_code=303)
