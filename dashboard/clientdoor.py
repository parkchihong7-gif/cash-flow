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

**아래 둘이 같은 문으로 들어온다.** 무엇이 열리는지는 키가 정한다.

    role="admin"    관리자 화면 + 자기 고객에게 키를 주는 자리
    role="client"   쓰는 화면만

산 사람에게 내 대시보드 코드를 줄 수는 없는데, 그 사람도 자기 고객에게 키를
줘야 한다. 학원에 팔면 학원장이 수강생 쉰 명에게 나눠 줘야 하고, 내가 그
쉰 명을 대신 발급해 줄 수는 없다. 그래서 **문 안에 발급 자리를 둔다.**

무엇을 막아 두었나
------------------

* 관리자는 **자기가 발급한 키만** 본다. 내 키도, 옆 관리자의 키도 안 보인다
* 관리자는 **관리자키를 못 만든다.** 파는 것은 나만 한다 — 허용하면 산 사람이
  관리자를 찍어 내며 재판매한다
* 손대는 길마다 `owns()` 를 지난다. 화면에서 안 그리는 것만으로는 부족하다

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

import secrets
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.keyauth import (
    KIND_PRIMARY, KIND_SECONDARY, ROLE_ADMIN, ROLE_CLIENT, KeyAuth, KeyError_,
)
from core.webui import load_handler

__all__ = ["register", "DOOR_PREFIX", "COOKIE_PREFIX"]

DOOR_PREFIX = "/c"

#: 프로그램마다 쿠키를 따로 둔다. 한 사람이 두 프로그램을 동시에 쓸 수 있어야 한다.
COOKIE_PREFIX = "ckey_"

#: 쿠키가 살아 있는 시간(초). 세션은 서버가 따로 들고 있으므로 이건 상한일 뿐이다.
COOKIE_MAX_AGE = 60 * 60 * 12


def cookie_name(program_id: str) -> str:
    return COOKIE_PREFIX + program_id.replace("-", "_")


def register(app, templates, registry, db, program_or_404, console_for) -> None:  # noqa: C901
    """통합 대시보드 앱에 클라이언트 문을 붙인다.

    Args:
        console_for: `(program, database, mode)` 를 받아 콘솔을 돌려주는 함수.
            관리자 화면과 **같은 것**을 쓴다. 따로 만들면 한쪽만 고치게 된다.
    """

    def _keys() -> KeyAuth:
        return KeyAuth(db().path)

    #: 방금 발급한 키를 한 번 보여 주려고 잠깐 들고 있는 자리.
    #: 키를 주소에 실으면 브라우저 기록과 서버 로그에 그대로 남는다.
    _fresh: dict[str, Any] = {}

    def _stash(value: Any) -> str:
        token = secrets.token_urlsafe(8)
        _fresh[token] = value
        while len(_fresh) > 64:
            _fresh.pop(next(iter(_fresh)))
        return token

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

    def _who(token: str):
        """이 세션이 누구인가. (역할, 그 사람의 1차키 id).

        2차키로 들어왔어도 **1차키가 그 사람**이다. 발급한 키를 1차키 id 로
        묶어 두었으므로 여기서 거슬러 올라간다.
        """
        keys = _keys()
        with keys._conn() as conn:
            row = conn.execute(
                "SELECT k.role AS role, k.id AS id, k.parent_id AS parent_id"
                " FROM auth_sessions s JOIN auth_keys k ON k.id = s.key_id"
                " WHERE s.token = ?", (token,)).fetchone()
        if row is None:
            return ROLE_CLIENT, 0
        return row["role"], (row["parent_id"] or row["id"])

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

        role, issuer_id = _who(token)
        database = db()

        # 산 사람(관리자키)에게는 관리자 화면을 연다. 그 사람은 이 프로그램의
        # 주인이고, 자기 고객에게 키를 줘야 한다.
        mode = "admin" if role == ROLE_ADMIN else "client"
        full = console_for(program, database, mode)
        shown = full.for_mode(mode)

        if role == ROLE_ADMIN:
            # 관리자 전용 탭 중 **내 것**만 남긴다. 기본 세팅과 파일 위치는
            # 내(메인 관리자) 자리라 산 사람에게 열지 않는다.
            shown.tabs = [tab for tab in shown.tabs
                          if tab.key not in ("presets", "files")]

        current = shown.tab("" if tab_key == "home" else tab_key) or shown.first_tab()

        extra: dict[str, Any] = {}
        if current is not None and current.render == "keys":
            keys = _keys()
            want = str(request.query_params.get("k") or "primary")
            kind = KIND_SECONDARY if want == "secondary" else KIND_PRIMARY
            extra = {
                "key_tab": want,
                # 자기가 발급한 것만. 옆 학원 수강생 명단이 보이면 안 된다.
                "key_rows": keys.list_keys(kind=kind, program_id=program.id,
                                           issued_by=issuer_id),
                "key_counts": keys.counts(program_id=program.id,
                                          issued_by=issuer_id),
                "live_sessions": 0,
                "issued": _fresh.pop(
                    str(request.query_params.get("issued") or ""), None),
                "bulk_codes": None,
            }

        return templates.TemplateResponse(
            request, "console.html",
            {
                "program": program,
                "mode": mode,
                "mode_label": "관리자 모드" if role == ROLE_ADMIN else "클라이언트 모드",
                "other_mode": mode,
                "other_label": "",
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
                "door_role": role,
                "programs": [], "load_errors": [],
                **extra,
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

    # ══════════════════════════ 산 사람이 자기 고객에게 키를 준다
    #
    # 이 아래는 **관리자키로 들어온 사람만** 지난다. 손대는 키마다 `owns()`
    # 를 확인한다 — 화면에서 안 그리는 것만으로는 부족하고, 주소를 직접 쳐서
    # 옆 학원 수강생 키를 정지시키는 길까지 닫아야 한다.

    def _as_admin(request: Request, program_id: str):
        """(토큰, 발급자 id, 막혔을 때 돌려줄 응답)."""
        token, why = _session(request, program_id)
        if not token:
            return "", 0, _door(request, program_or_404(program_id),
                                notice=why, status=401)
        role, issuer_id = _who(token)
        if role != ROLE_ADMIN:
            return "", 0, RedirectResponse(
                f"{DOOR_PREFIX}/{program_id}/t/home"
                f"?error=이 화면에서는 키를 만들 수 없습니다", status_code=303)
        return token, issuer_id, None

    def _back(program_id: str, tab: str = "primary", **extra) -> str:
        parts = [f"k={tab}"] + [f"{k}={v}" for k, v in extra.items() if v]
        return f"{DOOR_PREFIX}/{program_id}/t/keys?" + "&".join(parts)

    @app.post(DOOR_PREFIX + "/{program_id}/keys/issue")
    async def door_keys_issue(request: Request, program_id: str):
        """산 사람이 자기 고객에게 키 한 벌을 준다."""
        program = program_or_404(program_id)
        _token, issuer_id, blocked = _as_admin(request, program_id)
        if blocked is not None:
            return blocked

        form = await request.form()
        days = str(form.get("expires_days") or "").strip()
        try:
            issued = _keys().issue_set(
                name=str(form.get("name") or ""),
                email=str(form.get("email") or ""),
                program_id=program.id,
                service_url=str(request.base_url).rstrip("/")
                            + f"{DOOR_PREFIX}/{program.id}",
                expires_days=int(days) if days else None,
                role=ROLE_CLIENT,          # 관리자키는 나만 만든다
                issued_by=issuer_id,
            )
        except (KeyError_, ValueError) as exc:
            return RedirectResponse(_back(program_id, error=str(exc)),
                                    status_code=303)
        return RedirectResponse(_back(program_id, issued=_stash(issued)),
                                status_code=303)

    @app.post(DOOR_PREFIX + "/{program_id}/keys/{key_id}/toggle")
    async def door_keys_toggle(request: Request, program_id: str, key_id: int):
        program_or_404(program_id)
        _token, issuer_id, blocked = _as_admin(request, program_id)
        if blocked is not None:
            return blocked

        keys = _keys()
        if not keys.owns(key_id, issuer_id):
            # 내가 준 키가 아니다. 있는지 없는지도 알려 주지 않는다.
            return RedirectResponse(
                _back(program_id, error="그 키는 고객님 것이 아닙니다"),
                status_code=303)
        row = keys.get(key_id)
        if row.status == "suspended":
            keys.resume(key_id)
            msg = f"{row.code} 를 다시 쓸 수 있게 했습니다."
        else:
            keys.suspend(key_id)
            msg = f"{row.code} 를 사용중지했습니다. 접속해 있던 기기도 끊었습니다."
        tab = "secondary" if row.kind == KIND_SECONDARY else "primary"
        return RedirectResponse(_back(program_id, tab, flash=msg), status_code=303)

    @app.post(DOOR_PREFIX + "/{program_id}/keys/{key_id}/delete")
    async def door_keys_delete(request: Request, program_id: str, key_id: int):
        program_or_404(program_id)
        _token, issuer_id, blocked = _as_admin(request, program_id)
        if blocked is not None:
            return blocked

        keys = _keys()
        if not keys.owns(key_id, issuer_id):
            return RedirectResponse(
                _back(program_id, error="그 키는 고객님 것이 아닙니다"),
                status_code=303)
        row = keys.get(key_id)
        removed = keys.delete(key_id)
        extra = f" (딸린 2차키 {removed - 1}개 포함)" if removed > 1 else ""
        tab = "secondary" if row.kind == KIND_SECONDARY else "primary"
        return RedirectResponse(
            _back(program_id, tab,
                  flash=f"{row.code} 를 지웠습니다{extra}.", flash_tone="warn"),
            status_code=303)

    @app.post(DOOR_PREFIX + "/{program_id}/keys/reset")
    async def door_keys_reset(request: Request, program_id: str):
        """자기가 발급한 키만 비운다. 내 키는 건드리지 못한다."""
        program = program_or_404(program_id)
        _token, issuer_id, blocked = _as_admin(request, program_id)
        if blocked is not None:
            return blocked

        form = await request.form()
        try:
            count = _keys().reset_all(str(form.get("confirm") or ""),
                                      program_id=program.id,
                                      issued_by=issuer_id)
        except KeyError_ as exc:
            return RedirectResponse(_back(program_id, error=str(exc)),
                                    status_code=303)
        return RedirectResponse(
            _back(program_id, flash=f"고객 키 {count}개를 모두 지웠습니다.",
                  flash_tone="warn"),
            status_code=303)
