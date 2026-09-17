"""쿠팡파트너스 링크 후보 만들기.

두 갈래로 돈다.

    키가 있으면   상품 검색 API 로 후보 5개 + 딥링크(추적 링크) 생성
    키가 없으면   검색 URL 만 만들고 "API 키 필요" 로 표시하고 끝

**키가 없어도 오류가 아니다.** 쿠팡파트너스 API 는 실적 요건이 있어 처음부터
받을 수 있는 것이 아니고(CLAUDE.md §9 미확정 항목), 검색 URL 만으로도
"이 문단에 이 키워드로 찾은 상품을 붙이면 된다" 까지는 알 수 있다.

서명(HMAC)
    쿠팡 공식 문서가 적어 둔 규칙 그대로다.

        message   = signed-date + METHOD + path + query   (물음표는 빼고 붙인다)
        signature = HMAC-SHA256(secret, message) 를 16진수 소문자로
        header    = "CEA algorithm=HmacSHA256, access-key=..., signed-date=..., signature=..."

        signed-date 는 **GMT 기준** `yymmddTHHMMSSZ` 이다.

    ⚠️ 이 환경에서는 api-gateway.coupang.com 에 닿지 못해 **실제 응답으로 검증하지
    못했다.** 규칙대로 조립하는 것까지는 테스트로 고정해 두었으니, 처음 쓰실 때
    401 이 나면 서버 시각부터 확인하세요(시각이 5분 이상 틀어지면 거절합니다).

비공식 자동화는 하지 않는다(CLAUDE.md §3-7). 로그인 매크로도, 아이디·비밀번호
저장도 없다. 공식 API 키와 검색 URL 뿐이다.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from affiliate.schema import LinkCandidate                            # noqa: E402

__all__ = [
    "DOMAIN",
    "SEARCH_PATH",
    "DEEPLINK_PATH",
    "signed_date",
    "signature",
    "authorization",
    "CoupangClient",
    "CoupangError",
    "search_url",
    "candidates_for",
    "credentials",
    "YOUTUBE_SHOPPING_NOTE",
]

DOMAIN = "https://api-gateway.coupang.com"
SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search"
DEEPLINK_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"

#: 쿠팡 검색 화면 주소. 키가 없을 때 이것만 만든다.
SEARCH_URL = "https://www.coupang.com/np/search?q={keyword}"

#: 한 키워드당 후보 개수.
CANDIDATES = 5

#: 쿼터를 넘기면 재시도가 아니라 대기다 (CLAUDE.md §7).
PAUSE_SECONDS = 0.5
TIMEOUT_SECONDS = 15

YOUTUBE_SHOPPING_NOTE = (
    "유튜브 쇼핑 제휴는 공개 API 로 상품을 붙이지 못합니다. "
    "유튜브 스튜디오 → 수익 창출 → 쇼핑에서 손으로 태그하세요. "
    "2026년 3월부터 구독자 500명 + YPP 면 쓸 수 있고 플랫폼 수수료는 없습니다."
)


class CoupangError(RuntimeError):
    """쿠팡이 요청을 거절했을 때."""


def signed_date(now: datetime | None = None) -> str:
    """서명에 쓰는 시각. **GMT 기준** `yymmddTHHMMSSZ`.

    쿠팡은 서버 시각과 5분 이상 차이가 나면 거절한다. 그래서 현지 시각이 아니라
    UTC 로 만든다. 노트북 시계가 틀어져 있으면 여기서부터 어긋난다.
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    return moment.strftime("%y%m%dT%H%M%SZ")


def _message(method: str, url: str, date: str) -> str:
    """서명할 문자열을 만든다. 물음표는 빼고 경로와 질의문을 잇는다."""
    parsed = urllib.parse.urlsplit(url)
    return f"{date}{method.upper()}{parsed.path}{parsed.query}"


def signature(method: str, url: str, secret_key: str, date: str) -> str:
    """HMAC-SHA256 서명값(16진수 소문자)."""
    return hmac.new(
        secret_key.encode("utf-8"),
        _message(method, url, date).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def authorization(method: str, url: str, access_key: str, secret_key: str,
                  date: str | None = None) -> str:
    """Authorization 헤더 한 줄을 통째로 만든다."""
    date = date or signed_date()
    signed = signature(method, url, secret_key, date)
    return (f"CEA algorithm=HmacSHA256, access-key={access_key}, "
            f"signed-date={date}, signature={signed}")


def credentials() -> tuple[str, str]:
    """환경변수에서 키를 읽는다. 없으면 빈 문자열 두 개."""
    return (
        (os.getenv("COUPANG_ACCESS_KEY") or "").strip(),
        (os.getenv("COUPANG_SECRET_KEY") or os.getenv("COUPANG_SECRET") or "").strip(),
    )


def search_url(keyword: str) -> str:
    """키 없이도 만들 수 있는 검색 화면 주소."""
    return SEARCH_URL.format(keyword=urllib.parse.quote(keyword.strip()))


@dataclass
class CoupangClient:
    """공식 API 를 부르는 얇은 껍데기.

    네트워크를 타는 유일한 곳이다. 테스트에서는 `opener` 를 갈아 끼운다.
    """

    access_key: str
    secret_key: str
    domain: str = DOMAIN
    sub_id: str = ""
    opener = None                      # 테스트에서 바꿔 끼우는 자리

    def _request(self, method: str, path_with_query: str, body: dict | None = None) -> dict:
        url = self.domain + path_with_query
        header = authorization(method, path_with_query, self.access_key, self.secret_key)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method.upper())
        request.add_header("Authorization", header)
        request.add_header("Content-Type", "application/json;charset=UTF-8")

        opener = self.opener or urllib.request.urlopen
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise CoupangError(_explain(exc.code, detail)) from exc
        except urllib.error.URLError as exc:
            raise CoupangError(f"쿠팡에 닿지 못했습니다: {exc.reason}\n"
                               "  인터넷을 확인하시고, 그동안은 검색 URL 만으로도"
                               " 어디에 무엇을 붙일지는 정할 수 있습니다.") from exc
        time.sleep(PAUSE_SECONDS)
        return payload

    # ------------------------------------------------------------------ 검색
    def search(self, keyword: str, limit: int = CANDIDATES) -> list[LinkCandidate]:
        """키워드로 상품을 찾는다. 추적 링크(deeplink)가 함께 온다."""
        query = urllib.parse.urlencode({"keyword": keyword, "limit": limit})
        path = f"{SEARCH_PATH}?{query}"
        payload = self._request("GET", path)

        data = payload.get("data") or {}
        items = data.get("productData") if isinstance(data, dict) else None
        if items is None:
            items = payload.get("data") if isinstance(payload.get("data"), list) else []

        found: list[LinkCandidate] = []
        for item in (items or [])[:limit]:
            found.append(LinkCandidate(
                keyword=keyword,
                kind="api",
                title=str(item.get("productName", "")),
                url=str(item.get("productUrl") or item.get("landingUrl") or ""),
                price=int(item.get("productPrice") or 0),
                image=str(item.get("productImage", "")),
                is_rocket=bool(item.get("isRocket")),
            ))
        return found

    # ---------------------------------------------------------------- 딥링크
    def deeplink(self, urls: list[str]) -> dict[str, str]:
        """상품 주소를 내 추적 링크로 바꾼다. {원래주소: 추적링크}."""
        if not urls:
            return {}
        body: dict = {"coupangUrls": urls}
        if self.sub_id:
            body["subId"] = self.sub_id
        payload = self._request("POST", DEEPLINK_PATH, body)
        result: dict[str, str] = {}
        for item in payload.get("data") or []:
            original = str(item.get("originalUrl", ""))
            short = str(item.get("shortenUrl") or item.get("landingUrl") or "")
            if original and short:
                result[original] = short
        return result


def _explain(status: int, detail: str) -> str:
    """거절 이유를 사람이 읽을 수 있게 바꾼다."""
    hints = {
        401: ("서명이 맞지 않습니다.\n"
              "  1. ACCESS/SECRET 키를 바꿔 넣지 않았는지\n"
              "  2. 컴퓨터 시계가 맞는지 — 5분 이상 틀어지면 거절합니다\n"
              "  3. 키 앞뒤에 공백이나 따옴표가 붙지 않았는지"),
        403: ("권한이 없습니다. 파트너스 계정이 API 사용 승인을 받았는지 확인하세요.\n"
              "  실적 요건이 있어 가입 직후에는 안 열릴 수 있습니다."),
        429: ("호출이 너무 잦습니다. **재시도하지 말고 기다리세요**(CLAUDE.md §7).\n"
              "  키워드 수를 줄이거나 내일 다시 돌리시는 편이 낫습니다."),
    }
    hint = hints.get(status, "쿠팡이 요청을 거절했습니다.")
    return f"[HTTP {status}] {hint}\n  서버 응답: {detail}"


def candidates_for(keywords: list[str], client: CoupangClient | None = None,
                   ) -> tuple[dict[str, list[LinkCandidate]], list[str]]:
    """키워드마다 링크 후보를 모은다.

    Args:
        keywords: 찾을 키워드.
        client: 키가 있을 때만 준다. 없으면 검색 URL 만 만든다.

    Returns:
        ({키워드: 후보 목록}, 경고 목록)
    """
    found: dict[str, list[LinkCandidate]] = {}
    warnings: list[str] = []

    for keyword in dict.fromkeys(k.strip() for k in keywords if k and k.strip()):
        if client is None:
            found[keyword] = [LinkCandidate(
                keyword=keyword,
                kind="search_url",
                title=f"'{keyword}' 검색 결과",
                url=search_url(keyword),
                needs_api_key=True,
                note="API 키 필요 — 지금은 검색 화면 주소입니다. 상품을 직접 고르세요.",
            )]
            continue

        try:
            items = client.search(keyword)
        except CoupangError as exc:
            warnings.append(f"'{keyword}' 검색 실패 — {str(exc).splitlines()[0]}")
            found[keyword] = [LinkCandidate(
                keyword=keyword, kind="search_url",
                title=f"'{keyword}' 검색 결과", url=search_url(keyword),
                needs_api_key=True, note="API 호출이 실패해 검색 주소로 대신합니다.",
            )]
            continue

        if not items:
            warnings.append(f"'{keyword}' 로 나온 상품이 없습니다. 키워드를 바꿔 보세요")
        found[keyword] = items or [LinkCandidate(
            keyword=keyword, kind="search_url",
            title=f"'{keyword}' 검색 결과", url=search_url(keyword),
            note="API 로는 나온 상품이 없어 검색 주소를 둡니다.",
        )]

    return found, warnings
