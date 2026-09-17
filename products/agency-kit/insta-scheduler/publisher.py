"""인스타그램 공식 발행 — 컨테이너 방식.

Instagram Graph API 는 두 걸음으로 올린다.

    1. POST /{ig-user-id}/media          미디어 주소와 캡션으로 **컨테이너**를 만든다
    2. POST /{ig-user-id}/media_publish  그 컨테이너를 **발행**한다

릴스(동영상)는 1번 뒤에 처리 시간이 있어, 다 됐는지 물어보며 기다린다
(`GET /{container-id}?fields=status_code`).

**이 모듈에 없는 기능**
    팔로우·언팔로우·좋아요·DM 발송. 만들지 않았다.
    Meta 정책 위반이라 계정이 정지되고, 그건 고객 자산을 잃는 일이다.
    README 에 이유를 적어 두었다(CLAUDE.md §3-4).

토큰
    60일짜리 장기 토큰을 쓴다. 만료 전에 `manage.py refresh-token` 으로 갱신한다.
    갱신을 잊으면 어느 날 조용히 멈춘다. 리테이너 계약의 월 점검 항목이다.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

__all__ = [
    "GRAPH_VERSION", "GRAPH_BASE", "InstagramClient", "InstagramError",
    "credentials", "PublishResult", "MEDIA_TYPES",
]

#: 그래프 API 판. 올라가면 여기만 고친다.
GRAPH_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

MEDIA_TYPES = ("IMAGE", "REELS")

#: 릴스가 다 처리될 때까지 물어보는 간격과 횟수.
POLL_SECONDS = 5
POLL_TRIES = 24                                    # 최대 2분

TIMEOUT_SECONDS = 30


class InstagramError(RuntimeError):
    """인스타가 요청을 거절했을 때."""


@dataclass
class PublishResult:
    ok: bool
    media_id: str = ""
    container_id: str = ""
    detail: str = ""


def credentials() -> tuple[str, str]:
    """환경변수에서 토큰과 계정 번호를 읽는다. 없으면 빈 문자열."""
    return (
        (os.getenv("IG_ACCESS_TOKEN") or "").strip(),
        (os.getenv("IG_USER_ID") or "").strip(),
    )


def _explain(status: int, detail: str) -> str:
    """거절 이유를 사람 말로 바꾼다. 처음 붙일 때 대부분 여기서 막힌다."""
    hints = {
        190: ("토큰이 만료됐거나 잘못됐습니다.\n"
              "  `python manage.py refresh-token` 으로 갱신하세요.\n"
              "  60일이 지나면 만료됩니다."),
        200: ("권한이 모자랍니다.\n"
              "  앱에 instagram_content_publish · instagram_basic ·"
              " pages_read_engagement 권한이 있어야 합니다."),
        100: ("보낸 값이 잘못됐습니다.\n"
              "  미디어 주소가 **공개된 https 주소**인지 확인하세요.\n"
              "  구글드라이브 공유 링크는 안 됩니다. 인스타가 직접 받아 갈 수 있어야 합니다."),
        4: "호출 한도를 넘었습니다. **재시도하지 말고 기다리세요**(CLAUDE.md §7).",
        9: "게시 한도를 넘었습니다. 인스타는 24시간에 25건까지만 허용합니다.",
    }
    try:
        payload = json.loads(detail)
        error = payload.get("error", {})
        code = int(error.get("code", 0))
        message = error.get("message", "")
    except Exception:
        code, message = 0, detail[:300]

    hint = hints.get(code, "")
    text = f"[HTTP {status}] {message}"
    return f"{text}\n  {hint}" if hint else text


@dataclass
class InstagramClient:
    """Graph API 를 부르는 얇은 껍데기. `opener` 를 갈아 끼우면 테스트가 된다."""

    access_token: str
    ig_user_id: str
    base: str = GRAPH_BASE
    opener = None
    sleeper = staticmethod(time.sleep)

    def _post(self, path: str, data: dict) -> dict:
        url = f"{self.base}/{path}"
        payload = dict(data)
        payload["access_token"] = self.access_token
        body = urllib.parse.urlencode(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, method="POST")
        return self._send(request)

    def _get(self, path: str, params: dict) -> dict:
        query = dict(params)
        query["access_token"] = self.access_token
        url = f"{self.base}/{path}?{urllib.parse.urlencode(query)}"
        return self._send(urllib.request.Request(url, method="GET"))

    def _send(self, request) -> dict:
        opener = self.opener or urllib.request.urlopen
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise InstagramError(
                _explain(exc.code, exc.read().decode("utf-8", "replace"))) from exc
        except urllib.error.URLError as exc:
            raise InstagramError(f"인스타에 닿지 못했습니다: {exc.reason}") from exc

    # ------------------------------------------------------------ 1단계
    def create_container(self, media_url: str, caption: str,
                         media_type: str = "IMAGE") -> str:
        """미디어 컨테이너를 만든다. 아직 올라간 것은 아니다."""
        if media_type not in MEDIA_TYPES:
            raise ValueError(f"미디어 종류는 {' 또는 '.join(MEDIA_TYPES)} 입니다")

        data: dict[str, str] = {"caption": caption}
        if media_type == "REELS":
            data["media_type"] = "REELS"
            data["video_url"] = media_url
        else:
            data["image_url"] = media_url

        response = self._post(f"{self.ig_user_id}/media", data)
        container_id = str(response.get("id", ""))
        if not container_id:
            raise InstagramError(f"컨테이너 번호를 받지 못했습니다: {response}")
        return container_id

    def container_status(self, container_id: str) -> str:
        """FINISHED / IN_PROGRESS / ERROR / PUBLISHED."""
        response = self._get(container_id, {"fields": "status_code"})
        return str(response.get("status_code", "")).upper()

    def wait_ready(self, container_id: str, tries: int = POLL_TRIES) -> None:
        """릴스는 처리 시간이 걸린다. 다 될 때까지 물어본다."""
        for attempt in range(tries):
            status = self.container_status(container_id)
            if status in {"FINISHED", "PUBLISHED", ""}:
                return
            if status == "ERROR":
                raise InstagramError(
                    "인스타가 미디어를 처리하지 못했습니다.\n"
                    "  영상 규격(길이·해상도·코덱)을 확인하세요.")
            self.sleeper(POLL_SECONDS)
        raise InstagramError(
            f"미디어 처리가 {tries * POLL_SECONDS}초 안에 끝나지 않았습니다. "
            "잠시 뒤 다시 시도하세요.")

    # ------------------------------------------------------------ 2단계
    def publish(self, container_id: str) -> str:
        """컨테이너를 실제로 올린다. 게시물 번호를 돌려준다."""
        response = self._post(f"{self.ig_user_id}/media_publish",
                              {"creation_id": container_id})
        media_id = str(response.get("id", ""))
        if not media_id:
            raise InstagramError(f"게시물 번호를 받지 못했습니다: {response}")
        return media_id

    # ------------------------------------------------------------ 한 번에
    def publish_post(self, media_url: str, caption: str,
                     media_type: str = "IMAGE") -> PublishResult:
        """컨테이너 만들기 → (릴스면 기다리기) → 발행."""
        container_id = self.create_container(media_url, caption, media_type)
        if media_type == "REELS":
            self.wait_ready(container_id)
        media_id = self.publish(container_id)
        return PublishResult(ok=True, media_id=media_id, container_id=container_id)

    # ------------------------------------------------------------ 토큰
    def refresh_long_lived_token(self, app_id: str, app_secret: str) -> dict:
        """60일짜리 장기 토큰으로 바꾼다.

        결과의 `access_token` 을 `.env` 의 `IG_ACCESS_TOKEN` 에 넣으면 된다.
        **60일마다 해야 한다.** 달력에 적어 두세요.
        """
        return self._get("oauth/access_token", {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": self.access_token,
        })

    def token_info(self, app_id: str = "", app_secret: str = "") -> dict:
        """토큰이 언제까지인지 본다."""
        app_token = f"{app_id}|{app_secret}" if app_id and app_secret else self.access_token
        query = urllib.parse.urlencode({
            "input_token": self.access_token, "access_token": app_token})
        request = urllib.request.Request(f"{self.base}/debug_token?{query}", method="GET")
        return self._send(request)
