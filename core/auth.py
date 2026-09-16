"""대시보드 접속 코드 잠금.

대시보드를 인터넷에 열어 두면 **주소만 알면 누구나 들어옵니다.** 이 모듈이
그 앞에 접속 코드를 하나 세웁니다.

    코드 입력 → 맞으면 서명된 쿠키를 준다 → 그 쿠키가 있는 동안만 화면이 열린다

쿠키에는 **만료 시각과 서명만** 들어갑니다. 접속 코드 자체는 쿠키에 담기지
않으므로, 쿠키를 훔쳐봐도 코드를 알아낼 수 없습니다. 서명은 서버만 아는
비밀값으로 만들기 때문에 만료 시각을 고쳐 넣어도 통과하지 못합니다.

비밀값은 이 순서로 정합니다.

1. 환경변수 `DASHBOARD_SECRET`
2. 저장소의 `.dashboard_secret` 파일 (없으면 만들고, 커밋되지 않습니다)

여러 대에 나눠 띄울 때는 1번을 같은 값으로 맞춰야 한쪽에서 받은 쿠키가
다른 쪽에서도 통합니다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from shared.config import DATA_DIR

__all__ = [
    "COOKIE_NAME", "DEFAULT_ACCESS_CODE", "SECRET_PATH",
    "access_code", "is_default_code", "check_code", "session_hours",
    "issue_token", "verify_token", "Gatekeeper",
    "MAX_ATTEMPTS", "LOCKOUT_SECONDS",
]

#: 쿠키 이름. 다른 사이트의 쿠키와 겹치지 않게 접두어를 붙였다.
COOKIE_NAME = "cashflow_gate"

#: 환경변수로 바꾸지 않았을 때 쓰는 접속 코드.
DEFAULT_ACCESS_CODE = "redwind7"

#: 서명용 비밀값을 두는 파일. `.gitignore` 에 들어 있다.
SECRET_PATH = DATA_DIR / ".dashboard_secret"

#: 한 아이피에서 이만큼 틀리면 잠깁니다.
MAX_ATTEMPTS = 7

#: 잠기는 시간(초).
LOCKOUT_SECONDS = 600


def access_code() -> str:
    """지금 쓰는 접속 코드."""
    return (os.getenv("DASHBOARD_ACCESS_CODE") or DEFAULT_ACCESS_CODE).strip()


def is_default_code() -> bool:
    """기본 코드를 그대로 쓰고 있는가. 공개 주소라면 바꾸는 편이 안전하다."""
    return access_code() == DEFAULT_ACCESS_CODE


def session_hours() -> int:
    """한 번 들어가면 몇 시간 동안 유지되는가."""
    try:
        hours = int(os.getenv("DASHBOARD_SESSION_HOURS", "12"))
    except ValueError:
        return 12
    return max(1, min(hours, 24 * 30))


def check_code(given: str) -> bool:
    """입력한 코드가 맞는가.

    `==` 대신 `compare_digest` 를 쓴다. 문자열 비교는 다른 글자가 나오는 순간
    멈추기 때문에, 걸린 시간을 재면 앞에서 몇 글자가 맞았는지 알 수 있다.

    바이트로 바꿔서 넘긴다. `compare_digest` 는 글자열을 받으면 ASCII 가 아닌
    글자에서 `TypeError` 를 낸다. 접속 코드를 한글로 정하는 경우가 있어서
    그대로 넘기면 로그인 화면이 통째로 깨진다.
    """
    return hmac.compare_digest(
        (given or "").strip().encode("utf-8"),
        access_code().encode("utf-8"),
    )


# ------------------------------------------------------------------- 비밀값
def _load_secret() -> bytes:
    from_env = os.getenv("DASHBOARD_SECRET", "").strip()
    if from_env:
        return from_env.encode("utf-8")

    if SECRET_PATH.is_file():
        saved = SECRET_PATH.read_text(encoding="utf-8").strip()
        if saved:
            return saved.encode("utf-8")

    fresh = secrets.token_urlsafe(48)
    try:
        SECRET_PATH.write_text(fresh + "\n", encoding="utf-8")
        SECRET_PATH.chmod(0o600)
    except OSError:
        pass          # 쓰기가 막힌 환경이면 이번 실행 동안만 쓴다
    return fresh.encode("utf-8")


_SECRET: bytes | None = None


def _secret() -> bytes:
    global _SECRET
    if _SECRET is None:
        _SECRET = _load_secret()
    return _SECRET


def _sign(payload: str) -> str:
    digest = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


# --------------------------------------------------------------------- 토큰
def issue_token(now: float | None = None) -> str:
    """`만료시각.서명` 꼴의 쿠키 값을 만든다."""
    expires = int((now if now is not None else time.time()) + session_hours() * 3600)
    payload = str(expires)
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str | None, now: float | None = None) -> bool:
    """쿠키가 우리가 준 것이고 아직 살아 있는가."""
    if not token or "." not in token:
        return False
    payload, _, signature = token.rpartition(".")
    if not payload.isdigit():
        return False
    if not hmac.compare_digest(signature, _sign(payload)):
        return False
    return int(payload) > (now if now is not None else time.time())


# ------------------------------------------------------------- 무차별 대입 차단
@dataclass
class Gatekeeper:
    """같은 곳에서 코드를 계속 틀리면 잠시 막는다.

    여덟 글자 코드는 사람이 손으로는 못 맞히지만 프로그램은 초당 수천 번
    시도할 수 있다. 몇 번 틀리면 잠그는 것만으로 그 방법이 통하지 않게 된다.

    기억은 메모리에만 둔다. 서버를 다시 띄우면 지워진다. 그 정도면 충분하고,
    잠금 기록을 디스크에 남기면 그것대로 지워 줄 방법이 필요해진다.
    """

    max_attempts: int = MAX_ATTEMPTS
    lockout_seconds: int = LOCKOUT_SECONDS
    _failures: dict[str, list[float]] = field(default_factory=dict)
    _locked_until: dict[str, float] = field(default_factory=dict)

    def locked_for(self, who: str, now: float | None = None) -> int:
        """남은 잠금 시간(초). 0 이면 잠기지 않았다."""
        now = now if now is not None else time.time()
        until = self._locked_until.get(who, 0)
        return max(0, int(until - now))

    def record_failure(self, who: str, now: float | None = None) -> int:
        """틀렸다고 알린다. 남은 시도 횟수를 돌려준다."""
        now = now if now is not None else time.time()
        window = now - self.lockout_seconds
        recent = [t for t in self._failures.get(who, []) if t > window]
        recent.append(now)
        self._failures[who] = recent

        if len(recent) >= self.max_attempts:
            self._locked_until[who] = now + self.lockout_seconds
            self._failures[who] = []
            return 0
        return self.max_attempts - len(recent)

    def reset(self, who: str) -> None:
        """맞게 들어왔으니 기록을 지운다."""
        self._failures.pop(who, None)
        self._locked_until.pop(who, None)
