"""대시보드에서 무료 키 서버(구글 앱스 스크립트)로 키를 보내는 길.

왜 필요한가
    고객은 사장님 컴퓨터가 꺼져 있어도 키를 넣습니다. 그때 대답할 것이
    있어야 하는데, 집 컴퓨터의 SQLite 는 꺼지면 대답을 못 합니다.
    그래서 **발급은 대시보드에서만** 하되, 만든 키를 구글 시트에 함께
    올려 둡니다. 시트는 24시간 켜져 있어 고객에게 대답합니다.

순서가 중요하다
    **시트에 먼저 넣고, 들어간 뒤에 대시보드에 적습니다.** 반대로 하면
    시트에 못 들어간 키를 고객에게 보내게 되고, 고객은 그 자리에서
    "키가 틀렸다" 는 말을 듣습니다. 이쪽 순서면 최악이라도 시트에만 있고
    대시보드 목록에 안 보이는 키가 생기는데, 그건 고객에게 해가 없습니다.

설정
    `.env` 에 두 줄을 넣으면 켜집니다. 없으면 대시보드는 **지금까지처럼
    자기 SQLite 에만** 적습니다(집에서 혼자 쓰실 때).

        KEYSERVER_URL=https://script.google.com/macros/s/.../exec
        KEYSERVER_PASSWORD=스크립트속성에_넣은_ADMIN_PASSWORD
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

__all__ = ["KeyServer", "KeyServerError", "from_env", "admin_page_url",
           "key_console_url", "SELF_SERVED"]

#: 서버가 느릴 때 화면이 영영 안 돌아오지 않게.
TIMEOUT = 25.0

#: 앱스 스크립트는 리다이렉트를 한 번 거친다. urllib 이 알아서 따라간다.
#: Content-Type 을 text/plain 으로 두는 것은 브라우저 쪽과 맞추기 위한 것이다.
CONTENT_TYPE = "text/plain;charset=utf-8"


class KeyServerError(RuntimeError):
    """키 서버가 거절했거나 닿지 않았을 때."""


@dataclass(frozen=True)
class KeyServer:
    """무료 키 서버 한 대.

    Attributes:
        url: 배포하고 받은 `.../exec` 주소.
        password: 스크립트 속성의 `ADMIN_PASSWORD`.
    """

    url: str
    password: str

    # ────────────────────────────────────────────────────────── 기본
    def _call(self, action: str, **params: Any) -> dict:
        """서버를 한 번 부른다.

        Raises:
            KeyServerError: 닿지 않거나, 서버가 `ok: false` 로 답할 때.
        """
        payload = {"action": action, "token": self.password}
        payload.update({k: v for k, v in params.items() if v not in (None, "")})
        request = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": CONTENT_TYPE},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
                body = answer.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise KeyServerError(f"키 서버가 {exc.code} 로 답했습니다") from exc
        except OSError as exc:
            # 인터넷이 끊겼거나 주소가 틀렸다. 어느 쪽인지 사람은 모르므로
            # 무엇을 보라고 알려 준다.
            raise KeyServerError(
                "키 서버에 닿지 못했습니다. 인터넷과 KEYSERVER_URL 을 봐 주세요"
            ) from exc

        try:
            data = json.loads(body)
        except ValueError as exc:
            # 로그인 화면(HTML)이 내려오는 경우가 여기다. 배포할 때
            # '액세스 권한이 있는 사용자' 를 '모든 사용자' 로 안 두면 그렇다.
            raise KeyServerError(
                "키 서버가 JSON 이 아닌 것을 보냈습니다. 배포 설정에서 "
                "'액세스 권한이 있는 사용자' 를 '모든 사용자' 로 두셨는지 봐 주세요"
            ) from exc

        if not data.get("ok"):
            raise KeyServerError(data.get("message") or f"키 서버가 거절했습니다: {data.get('reason')}")
        return data

    def ping(self) -> bool:
        """살아 있는지만 본다. 비밀번호가 틀려도 True 가 나온다."""
        try:
            request = urllib.request.Request(
                self.url, data=json.dumps({"action": "ping"}).encode("utf-8"),
                headers={"Content-Type": CONTENT_TYPE},
            )
            with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
                return bool(json.loads(answer.read().decode("utf-8")).get("ok"))
        except Exception:
            return False

    def send_text(self, *, email: str, subject: str, body: str,
                  html: str = "", program_id: str = "") -> dict:
        """**손질한 안내문을 그대로** 보낸다.

        발급할 때 서버가 만들어 보내는 글과 다르다. 그 글은 한 글자도 못
        고치는데, 고객마다 덧붙일 말이 다르다. 이 길은 화면에서 고친 글을
        그대로 넘긴다.

        주인 비밀번호로만 된다. 산 분에게 열어 주면 우리 계정으로 아무 글이나
        아무에게나 보낼 수 있게 된다.

        Raises:
            KeyServerError: 닿지 않거나 서버가 거절할 때. 하루 한도를 다
                썼을 때도 여기로 온다.
        """
        return self._call("adminSendText", email=email, subject=subject,
                          body=body, html=html, program=program_id)

    # ────────────────────────────────────────────────────────── 발급
    def issue_set(self, *, program_id: str, name: str, email: str,
                  role: str = "admin", expires_days: int | None = None,
                  base_url: str = "", issued_by: str = "",
                  send_mail: bool = True) -> dict:
        """1차키 1개 + 2차키 3개를 서버에 만든다.

        Returns:
            `primaryKey`, `secondaryKeys`(기기→키), `mailed`, `url` 이 든 dict.

        Raises:
            KeyServerError: 서버가 거절했을 때. **이때는 아무것도 안 만들어진다.**
        """
        return self._call(
            "adminCreateInvite",
            program=program_id, name=name, email=email, role=role,
            expiryDays=str(expires_days) if expires_days else "",
            baseUrl=base_url, issuedBy=issued_by,
            sendMail="1" if send_mail else "",
        )

    # ────────────────────────────────────────────────────────── 조회·손보기
    def list_keys(self, *, program_id: str = "", issuer: str = "") -> list[dict]:
        return list(self._call("adminList", program=program_id, issuer=issuer).get("rows", []))

    def set_status(self, *, program_id: str, key: str, active: bool,
                   issuer: str = "") -> None:
        action = "adminResumeKey" if active else "adminSuspendKey"
        self._call(action, program=program_id, key=key, issuer=issuer)

    def delete_key(self, *, program_id: str, key: str, issuer: str = "") -> int:
        return int(self._call("adminDeleteKey", program=program_id, key=key,
                              issuer=issuer).get("deleted", 0))

    def reset(self, *, program_id: str = "") -> int:
        """되돌릴 수 없다. 그래서 서버가 '초기화' 라는 말을 따로 요구한다."""
        return int(self._call("adminResetAll", program=program_id,
                              confirm="초기화").get("deleted", 0))


def from_env() -> KeyServer | None:
    """`.env` 에 설정이 있으면 키 서버를, 없으면 None 을 준다.

    None 이면 대시보드는 지금까지처럼 자기 SQLite 에만 적는다 —
    집에서 혼자 쓰실 때가 그 경우다.
    """
    url = (os.getenv("KEYSERVER_URL") or "").strip()
    password = (os.getenv("KEYSERVER_PASSWORD") or "").strip()
    if not url or not password:
        return None
    return KeyServer(url=url, password=password)


def admin_page_url() -> str:
    """접속키 관리자 화면 주소. 없으면 빈 글자.

    `from_env()` 와 달리 **비밀번호는 보지 않는다.** 그 화면이 직접 묻기
    때문이다. 비밀번호를 `.env` 에 안 넣으신 분(집에서 손으로만 쓰시는 분)도
    화면에서 버튼은 보여야 한다.

    주소를 `program.yaml` 이 아니라 `.env` 에 두는 이유: 이 저장소는 공개라,
    앱스 스크립트 `/exec` 주소가 박히면 장부의 대문 주소가 같이 공개된다.
    비밀번호와 같은 칸에 둔다.
    """
    return (os.getenv("KEYSERVER_URL") or "").strip()


#: `.env` 가 비어 있을 때 대신 여는 곳. 대시보드가 직접 내주는 관리자 화면이다.
#: 거기서 서버 주소를 한 번 넣으면 브라우저가 기억한다 — 저장소에 비밀이
#: 들어가지 않고, 버튼이 죽지도 않는다.
SELF_SERVED = "/keys/console"


def key_console_url() -> str:
    """[🔑 접속키 발급하기] 가 갈 곳. **언제나 값이 있다.**

    `.env` 에 앱스 스크립트 주소가 있으면 거기로 바로 보내고, 없으면
    대시보드가 직접 내주는 관리자 화면으로 보낸다. 예전에는 주소가 없으면
    버튼 자체를 안 냈는데, 그러면 **키를 어디서 만드는지 알 길이 없었다.**
    """
    return admin_page_url() or SELF_SERVED
