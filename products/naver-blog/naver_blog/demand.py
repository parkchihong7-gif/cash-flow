"""수요 확인 — **읽는 API 만 쓴다.**

쓸 수 있는 네이버 공개 API 는 이 둘이다.

* **검색 API** (`openapi.naver.com/v1/search/blog.json`) — 그 키워드로 이미 몇 건이
  쓰였는지. 하루 25,000회, 무료. 개발자센터에서 앱 등록만 하면 바로 나온다
* **데이터랩 검색어 트렌드** (`openapi.naver.com/v1/datalab/search`) — 검색량의
  **상대값**. 절대 검색 수는 주지 않는다

절대 검색량이 필요하면 **네이버 검색광고 API** 를 써야 하는데, 그건 광고주
가입이 따로 필요하다. 그래서 여기서는 **선택**으로 두었다.

키가 없어도 `--fixture` 로 샘플 자료를 써서 전체 흐름을 볼 수 있다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

__all__ = [
    "SEARCH_URL", "TREND_URL", "DAILY_CALL_LIMIT", "Keyword", "NaverClient",
    "FixtureClient", "make_client", "DemandError", "competition_label",
]

SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"
TREND_URL = "https://openapi.naver.com/v1/datalab/search"

#: 검색 API 하루 한도. 넘으면 재시도가 아니라 다음 날을 기다린다.
DAILY_CALL_LIMIT = 25_000


class DemandError(RuntimeError):
    """수요 조회에 실패했을 때."""


@dataclass
class Keyword:
    """키워드 한 개의 수요·경쟁."""

    word: str
    total_posts: int = 0
    recent_posts: int = 0
    trend: list[float] = field(default_factory=list)
    note: str = ""

    @property
    def trend_direction(self) -> str:
        """오르는 중인지. 데이터랩 값은 상대값이라 방향만 본다."""
        if len(self.trend) < 4:
            return "알 수 없음"
        half = len(self.trend) // 2
        early = sum(self.trend[:half]) / max(1, half)
        late = sum(self.trend[half:]) / max(1, len(self.trend) - half)
        if early == 0:
            return "알 수 없음"
        change = (late - early) / early * 100
        if change > 15:
            return "오르는 중"
        if change < -15:
            return "내려가는 중"
        return "비슷함"

    @property
    def competition(self) -> str:
        return competition_label(self.total_posts)

    @property
    def crowded(self) -> bool:
        return self.total_posts >= 300_000

    @property
    def too_quiet(self) -> bool:
        """경쟁이 없는 게 아니라 찾는 사람이 없는 것일 수 있다."""
        return self.total_posts < 5_000


def competition_label(total: int) -> str:
    """이미 쓰인 글 수로 본 경쟁 정도. **절대적인 기준은 아니다.**"""
    if total >= 1_000_000:
        return "아주 붐빔"
    if total >= 300_000:
        return "붐빔"
    if total >= 50_000:
        return "보통"
    if total >= 5_000:
        return "한산함"
    # 너무 한산하면 경쟁이 없는 게 아니라 찾는 사람이 없는 것일 수 있다.
    return "아주 한산함"


class NaverClient:
    """네이버 공개 API 클라이언트. **읽기만 한다.**"""

    def __init__(self, client_id: str, client_secret: str, opener=None) -> None:
        if not client_id or not client_secret:
            raise DemandError(
                "네이버 API 키가 없습니다.\n"
                "  developers.naver.com 에서 앱을 등록하고 "
                "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 을 .env 에 넣으세요.\n"
                "  무료이고 바로 발급됩니다. 키 없이 보시려면 `--fixture` 를 쓰세요")
        self.client_id = client_id
        self.client_secret = client_secret
        self._open = opener or urllib.request.urlopen
        self.calls = 0

    def _headers(self) -> dict:
        return {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }

    def _get(self, url: str) -> dict:
        request = urllib.request.Request(url, headers=self._headers())
        return self._read(request)

    def _post(self, url: str, body: dict) -> dict:
        payload = json.dumps(body).encode("utf-8")
        headers = {**self._headers(), "Content-Type": "application/json"}
        return self._read(urllib.request.Request(url, data=payload, headers=headers))

    def _read(self, request) -> dict:
        self.calls += 1
        try:
            with self._open(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise DemandError(self._explain(exc.code)) from exc
        except urllib.error.URLError as exc:
            raise DemandError(f"네이버에 연결하지 못했습니다: {exc.reason}") from exc

    @staticmethod
    def _explain(code: int) -> str:
        hints = {
            401: "키가 틀렸습니다. NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 을 다시 보세요",
            403: "이 앱에 그 API 사용 권한이 없습니다. "
                 "개발자센터 앱 설정에서 '검색'과 '데이터랩' 을 추가하세요",
            429: f"하루 한도({DAILY_CALL_LIMIT:,}회)를 넘었습니다. "
                 f"재시도하지 말고 내일 도세요",
        }
        return hints.get(code, f"네이버 API 오류 {code}")

    def blog_count(self, word: str) -> int:
        """그 키워드로 이미 쓰인 블로그 글 수."""
        query = urllib.parse.urlencode({"query": word, "display": 1})
        data = self._get(f"{SEARCH_URL}?{query}")
        return int(data.get("total") or 0)

    def trend(self, word: str, months: int = 6) -> list[float]:
        """검색어 트렌드. **상대값이다.** 절대 검색 수가 아니다."""
        end = date.today()
        start = end - timedelta(days=30 * months)
        data = self._post(TREND_URL, {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "timeUnit": "month",
            "keywordGroups": [{"groupName": word, "keywords": [word]}],
        })
        results = data.get("results") or []
        if not results:
            return []
        return [float(point.get("ratio") or 0) for point in results[0].get("data", [])]


class FixtureClient:
    """샘플 자료용. 키가 없어도 흐름을 다 볼 수 있게 한다."""

    def __init__(self, fixture_dir: str | Path) -> None:
        self.dir = Path(fixture_dir)
        self.calls = 0

    def _load(self, word: str) -> dict:
        path = self.dir / f"{word}.json"
        if not path.is_file():
            raise DemandError(
                f"샘플 자료가 없습니다: {path.name}\n"
                f"  있는 것: {', '.join(sorted(p.stem for p in self.dir.glob('*.json'))) or '없음'}")
        return json.loads(path.read_text(encoding="utf-8"))

    def blog_count(self, word: str) -> int:
        self.calls += 1
        return int(self._load(word).get("total") or 0)

    def trend(self, word: str, months: int = 6) -> list[float]:
        self.calls += 1
        return [float(value) for value in self._load(word).get("trend") or []]


def make_client(client_id: str = "", client_secret: str = "",
                fixture_dir: str | Path | None = None):
    """키가 있으면 진짜, 없으면 샘플."""
    if fixture_dir is not None:
        return FixtureClient(fixture_dir)
    return NaverClient(client_id, client_secret)


def collect(words: list[str], client, months: int = 6) -> list[Keyword]:
    """키워드마다 글 수와 트렌드를 모은다. 경쟁이 한산한 순."""
    rows: list[Keyword] = []
    for word in words:
        word = word.strip()
        if not word:
            continue
        rows.append(Keyword(
            word=word,
            total_posts=client.blog_count(word),
            trend=client.trend(word, months),
        ))
    return sorted(rows, key=lambda row: row.total_posts)
