"""FAQ 원본 — 구글시트(없으면 CSV).

고객이 답변을 고치는 곳은 **구글시트**다. 코드가 아니다.
그게 이 모듈 전체의 설계 이유다. 사장님이 시트 한 줄만 고치면 챗봇 답이 바뀐다.

    시트 이름: FAQ
    칸:        질문 | 답변 | 카테고리 | 수정일

캐시를 5분 두는 까닭
    카카오는 응답을 **5초** 안에 달라고 한다. 질문이 올 때마다 구글시트를 읽으면
    그것만으로 1~2초를 쓴다. 그래서 5분 동안은 읽어 둔 것을 쓴다.
    고객이 시트를 고치고 "왜 안 바뀌죠" 할 때는 최대 5분이라고 답하면 된다.
    급하면 `/reload` 를 부르거나 서버를 다시 띄우면 된다.

시트를 못 읽을 때
    **빈 답을 주는 것보다 예전 것을 주는 편이 낫다.** 그래서 마지막으로 읽은
    것을 계속 쓰고, 그런 상태라는 것을 로그와 `/health` 에 남긴다.
"""

from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Faq", "FaqBook", "load_from_csv", "CACHE_SECONDS", "SHEET_NAME", "COLUMNS"]

#: 시트를 다시 읽는 주기(초).
CACHE_SECONDS = int(os.getenv("FAQ_CACHE_SECONDS", "300"))

#: 읽어 올 시트 이름과 칸.
SHEET_NAME = os.getenv("FAQ_SHEET_NAME", "FAQ")
COLUMNS = ("질문", "답변", "카테고리", "수정일")

#: 구글시트를 읽을 때 쓰는 권한. **읽기 전용**이다.
#: 고객 시트에 쓰기 권한까지 받으면, 실수 한 번으로 고객 자료를 지울 수 있다.
SCOPES = ("https://www.googleapis.com/auth/spreadsheets.readonly",)


@dataclass
class Faq:
    """FAQ 한 줄."""

    question: str
    answer: str
    category: str = ""
    updated: str = ""

    @property
    def valid(self) -> bool:
        return bool(self.question.strip() and self.answer.strip())


def _rows_to_faqs(rows: list[list[str]]) -> list[Faq]:
    """첫 줄을 머리글로 보고 칸 위치를 찾는다.

    칸 순서를 고객이 바꿔 놓는 일이 흔해서, 순서가 아니라 **이름**으로 찾는다.
    """
    if not rows:
        return []
    header = [str(cell).strip() for cell in rows[0]]
    index = {name: header.index(name) for name in COLUMNS if name in header}
    if "질문" not in index or "답변" not in index:
        raise ValueError(
            f"시트 첫 줄에 '질문' 과 '답변' 칸이 있어야 합니다. 지금 첫 줄: {header}")

    faqs: list[Faq] = []
    for row in rows[1:]:
        def cell(name: str) -> str:
            position = index.get(name)
            if position is None or position >= len(row):
                return ""
            return str(row[position]).strip()

        faq = Faq(question=cell("질문"), answer=cell("답변"),
                  category=cell("카테고리"), updated=cell("수정일"))
        if faq.valid:
            faqs.append(faq)
    return faqs


def load_from_csv(path: str | Path) -> list[Faq]:
    """CSV 에서 읽는다. 구글시트를 붙이기 전이나 시연할 때 쓴다."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"FAQ 파일이 없습니다: {path}")
    # 엑셀에서 내보낸 한글 CSV 는 cp949 인 경우가 많다.
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            text = path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        rows = [row for row in csv.reader(text.splitlines()) if any(cell.strip() for cell in row)]
        return _rows_to_faqs(rows)
    raise ValueError(f"{path.name} 의 글자 인코딩을 알아보지 못했습니다")


def load_from_sheet(sheet_id: str, sheet_name: str = SHEET_NAME,
                    credentials_path: str = "") -> list[Faq]:
    """구글시트에서 읽는다. 서비스 계정 JSON 으로 인증한다.

    고객이 할 일은 **시트를 서비스 계정 이메일에 '뷰어' 로 공유**하는 것뿐이다.
    이 한 줄을 설치 가이드에 크게 적어 두었다. 빠뜨리면 403 이 난다.
    """
    from google.oauth2 import service_account                         # 지연 import
    from googleapiclient.discovery import build

    path = credentials_path or os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if not path:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON 이 없습니다 (서비스 계정 키 파일 경로)")
    if not Path(path).is_file():
        raise FileNotFoundError(f"서비스 계정 키 파일이 없습니다: {path}")

    credentials = service_account.Credentials.from_service_account_file(
        path, scopes=list(SCOPES))
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    response = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"{sheet_name}!A:D").execute()
    return _rows_to_faqs(response.get("values", []))


@dataclass
class FaqBook:
    """FAQ 묶음과 5분 캐시.

    `loader` 를 갈아 끼우면 시트 없이도 돈다(테스트·시연).
    """

    loader: object                       # () -> list[Faq]
    cache_seconds: int = CACHE_SECONDS
    faqs: list[Faq] = field(default_factory=list)
    loaded_at: float = 0.0
    last_error: str = ""
    loads: int = 0

    def get(self, now: float | None = None) -> list[Faq]:
        """FAQ 를 돌려준다. 5분이 지났으면 다시 읽는다."""
        now = time.time() if now is None else now
        fresh = self.faqs and (now - self.loaded_at) < self.cache_seconds
        if fresh:
            return self.faqs

        try:
            loaded = list(self.loader())               # type: ignore[operator]
        except Exception as exc:                        # 시트가 잠깐 안 될 수 있다
            self.last_error = f"{type(exc).__name__}: {exc}"
            if self.faqs:
                # 빈 답보다 예전 답이 낫다. 오래된 것을 그대로 쓴다.
                return self.faqs
            raise

        self.faqs = loaded
        self.loaded_at = now
        self.loads += 1
        self.last_error = ""
        return self.faqs

    def invalidate(self) -> None:
        """다음 질문 때 시트를 다시 읽게 한다."""
        self.loaded_at = 0.0

    @property
    def age_seconds(self) -> float:
        return 0.0 if not self.loaded_at else time.time() - self.loaded_at

    def as_prompt(self, limit: int = 60) -> str:
        """Claude 에게 넘길 FAQ 목록. 번호는 1부터다."""
        lines = []
        for number, faq in enumerate(self.faqs[:limit], start=1):
            category = f" [{faq.category}]" if faq.category else ""
            lines.append(f"{number}.{category} {faq.question}")
        return "\n".join(lines)
