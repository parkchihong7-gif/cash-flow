"""유튜브 데이터 API v3 — 얇은 껍데기.

부르는 것은 셋뿐이다.

    search.list    키워드로 최근 30일 영상 찾기   (100 유닛)
    videos.list    조회수·좋아요·댓글·길이         (1 유닛)
    channels.list  구독자·총조회수                 (1 유닛)

**한 번에 50개씩**만 받는다. 그게 API 상한이고, 그 이상은 페이지를 넘겨야 하는데
페이지를 넘길 때마다 또 100 유닛이 나간다. 키워드 하나에 50개면 충분하다.

`--fixture` 모드에서는 이 껍데기 대신 `FixtureClient` 가 들어간다. 키가 없어도
전체 흐름을 볼 수 있어야 하기 때문이다.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

__all__ = [
    "API_BASE", "YouTubeClient", "FixtureClient", "YouTubeError",
    "parse_duration", "SHORT_MAX_SECONDS", "RESULTS_PER_KEYWORD", "LOOKBACK_DAYS",
]

API_BASE = "https://www.googleapis.com/youtube/v3"

#: 키워드당 받아 올 영상 수. API 상한이 50이다.
RESULTS_PER_KEYWORD = 50

#: 얼마나 최근 것을 볼 것인가.
LOOKBACK_DAYS = 30

#: 이 길이 이하면 쇼츠로 본다. 유튜브가 쇼츠로 취급하는 상한이다.
SHORT_MAX_SECONDS = 180

TIMEOUT_SECONDS = 20

_DURATION = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


class YouTubeError(RuntimeError):
    """유튜브가 요청을 거절했을 때."""


def parse_duration(text: str) -> int:
    """ISO 8601 길이(`PT4M13S`)를 초로 바꾼다. 못 읽으면 0."""
    match = _DURATION.fullmatch((text or "").strip())
    if not match:
        return 0
    days, hours, minutes, seconds = (int(value or 0) for value in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _explain(status: int, detail: str) -> str:
    hints = {
        403: ("쿼터를 다 썼거나 키가 막혔습니다.\n"
              "  - 하루 10,000 유닛을 넘겼는지 (search 한 번에 100 유닛입니다)\n"
              "  - 구글 클라우드 콘솔에서 YouTube Data API v3 를 켰는지\n"
              "  - 키에 API 제한이 걸려 있지 않은지"),
        400: "요청이 잘못됐습니다. 키워드에 이상한 글자가 섞였는지 보세요.",
        404: "찾는 것이 없습니다. 영상이나 채널이 지워졌을 수 있습니다.",
    }
    hint = hints.get(status, "")
    return f"[HTTP {status}] {detail[:300]}" + (f"\n  {hint}" if hint else "")


@dataclass
class YouTubeClient:
    """공식 API 를 부른다. `opener` 를 갈아 끼우면 테스트가 된다."""

    api_key: str
    base: str = API_BASE
    opener = None

    def _get(self, path: str, params: dict) -> dict:
        query = dict(params)
        query["key"] = self.api_key
        url = f"{self.base}/{path}?{urllib.parse.urlencode(query, doseq=True)}"
        request = urllib.request.Request(url, method="GET")

        opener = self.opener or urllib.request.urlopen
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise YouTubeError(
                _explain(exc.code, exc.read().decode("utf-8", "replace"))) from exc
        except urllib.error.URLError as exc:
            raise YouTubeError(f"유튜브에 닿지 못했습니다: {exc.reason}") from exc

    # -------------------------------------------------------------- search
    def search(self, keyword: str, published_after: str = "",
               limit: int = RESULTS_PER_KEYWORD) -> list[dict]:
        """키워드로 최근 영상을 찾는다. **100 유닛짜리 호출이다.**"""
        if not published_after:
            since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
            published_after = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        payload = self._get("search", {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "order": "date",
            "publishedAfter": published_after,
            "maxResults": min(limit, RESULTS_PER_KEYWORD),
        })
        return payload.get("items", [])

    # -------------------------------------------------------------- videos
    def videos(self, video_ids: list[str]) -> list[dict]:
        """영상의 숫자와 길이. 50개까지 한 번에 받는다 (1 유닛)."""
        if not video_ids:
            return []
        payload = self._get("videos", {
            "part": "statistics,contentDetails,snippet",
            "id": ",".join(video_ids[:50]),
        })
        return payload.get("items", [])

    # ------------------------------------------------------------ channels
    def channels(self, channel_ids: list[str]) -> list[dict]:
        """채널의 구독자·총조회수. 50개까지 한 번에 (1 유닛)."""
        if not channel_ids:
            return []
        payload = self._get("channels", {
            "part": "statistics,snippet",
            "id": ",".join(list(dict.fromkeys(channel_ids))[:50]),
        })
        return payload.get("items", [])


@dataclass
class FixtureClient:
    """키 없이 도는 가짜 클라이언트.

    `data/fixtures/<키워드>.json` 을 읽어 API 응답인 척한다. 없으면 빈 목록.

    이걸 두는 이유는 두 가지다.
      1. **키를 못 받은 사람도 무엇이 나오는지 볼 수 있어야 한다.**
         유튜브 API 키는 구글 클라우드 프로젝트를 만들어야 나온다.
      2. 테스트가 인터넷 없이 돌아야 한다.
    """

    fixture_dir: Path
    calls: list[tuple[str, str]] = None                # (호출, 키워드)

    def __post_init__(self) -> None:
        self.fixture_dir = Path(self.fixture_dir)
        if self.calls is None:
            self.calls = []
        self._current: dict = {}

    def _load(self, keyword: str) -> dict:
        path = self.fixture_dir / f"{keyword}.json"
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def search(self, keyword: str, published_after: str = "",
               limit: int = RESULTS_PER_KEYWORD) -> list[dict]:
        self.calls.append(("search.list", keyword))
        self._current = self._load(keyword)
        return self._current.get("search", [])[:limit]

    def videos(self, video_ids: list[str]) -> list[dict]:
        self.calls.append(("videos.list", ",".join(video_ids[:3])))
        wanted = set(video_ids)
        return [item for item in self._current.get("videos", [])
                if item.get("id") in wanted]

    def channels(self, channel_ids: list[str]) -> list[dict]:
        self.calls.append(("channels.list", ",".join(channel_ids[:3])))
        wanted = set(channel_ids)
        return [item for item in self._current.get("channels", [])
                if item.get("id") in wanted]


def make_client(fixture_dir: Path | None = None, api_key: str = ""):
    """키가 있으면 진짜, 없으면 픽스처. 이 결정을 한 군데서만 한다."""
    api_key = api_key or os.getenv("YOUTUBE_API_KEY", "").strip()
    if fixture_dir is not None:
        return FixtureClient(fixture_dir=fixture_dir)
    if not api_key:
        raise YouTubeError(
            "YOUTUBE_API_KEY 가 없습니다.\n"
            "  키 없이 보시려면 --fixture 로 돌리세요. 샘플 자료로 전체 흐름이 돕니다.\n"
            "  키는 무료입니다: console.cloud.google.com → YouTube Data API v3")
    return YouTubeClient(api_key=api_key)
