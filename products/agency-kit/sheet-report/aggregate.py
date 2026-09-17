"""집계 — **숫자는 전부 여기서 나온다.**

Claude 는 숫자를 만들지 않는다. 해석만 쓴다(`narrate.py`).
그 경계가 이 모듈의 존재 이유다. 보고서에 적힌 숫자가 사람이 검산할 수 있는
값이어야 하기 때문이다. 모델이 더한 숫자는 검산할 수 없다.

계산하는 것
    - 기간 합계 · 건수 · 평균 단가
    - 직전 같은 길이 기간과 견준 증감(액수·비율)
    - 채널/상품 상위 5개와 각각의 비중·증감
    - 일별 추이

칸 이름을 고객 시트에 맞추지 않는다
    고객 시트는 '날짜' 일 수도 '일자' 일 수도 'date' 일 수도 있다. 그래서
    **이름 후보를 여러 개 두고 찾는다.** 못 찾으면 무엇이 없는지 말해 준다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pandas as pd

__all__ = [
    "DATE_NAMES", "AMOUNT_NAMES", "GROUP_NAMES", "QTY_NAMES",
    "PERIODS", "Aggregate", "load_csv", "load_sheet", "summarize",
]

#: 칸 이름 후보. 앞에 있는 것부터 찾는다.
DATE_NAMES = ("날짜", "일자", "date", "일시", "주문일", "결제일")
AMOUNT_NAMES = ("매출", "금액", "amount", "총액", "결제금액", "판매액", "매출액")
GROUP_NAMES = ("채널", "상품", "카테고리", "구분", "품목", "channel", "product")
QTY_NAMES = ("수량", "건수", "qty", "quantity", "판매수량")

#: 기간 이름 → 며칠로 볼지.
PERIODS = {"week": 7, "month": 30, "quarter": 90}


class ColumnMissing(ValueError):
    """필요한 칸을 시트에서 못 찾았을 때."""


def _find(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    """칸 이름을 찾는다. 공백·대소문자는 무시한다."""
    lookup = {str(column).strip().lower(): column for column in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    # 부분 일치도 본다. '매출액(원)' 같은 이름이 흔하다.
    for key, column in lookup.items():
        if any(name.lower() in key for name in names):
            return column
    return None


def _to_number(series: pd.Series) -> pd.Series:
    """'1,200원' 같은 글자를 숫자로 바꾼다. 못 바꾸면 0."""
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0)
    cleaned = (series.astype(str)
               .str.replace(r"[^\d.\-]", "", regex=True)
               .replace("", "0"))
    return pd.to_numeric(cleaned, errors="coerce").fillna(0)


def load_csv(path: str | Path) -> pd.DataFrame:
    """CSV 를 읽는다. 시트를 붙이기 전이나 시연할 때 쓴다."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"자료 파일이 없습니다: {path}")
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path.name} 의 글자 인코딩을 알아보지 못했습니다")


def load_sheet(sheet_id: str, cell_range: str, credentials_path: str = "") -> pd.DataFrame:
    """구글시트 범위를 읽어 표로 만든다.

    첫 줄을 머리글로 본다. 고객 시트는 위에 제목 줄이 있는 경우가 많은데,
    그럴 때는 범위를 `매출!A3:F` 처럼 잡아 달라고 안내한다.
    """
    import os

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    path = credentials_path or os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if not path:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON 이 없습니다 (서비스 계정 키 파일 경로)")

    credentials = service_account.Credentials.from_service_account_file(
        path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    values = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=cell_range).execute().get("values", [])
    if not values:
        raise ValueError(f"'{cell_range}' 범위가 비어 있습니다")

    header, *rows = values
    width = len(header)
    padded = [row + [""] * (width - len(row)) for row in rows]
    return pd.DataFrame(padded, columns=[str(name).strip() for name in header])


@dataclass
class Aggregate:
    """집계 결과. 보고서에 들어갈 숫자는 여기 있는 것이 전부다."""

    period: str
    days: int
    start: str
    end: str
    prev_start: str
    prev_end: str

    total: int = 0
    count: int = 0
    average: int = 0
    prev_total: int = 0
    delta: int = 0
    delta_ratio: float = 0.0

    group_column: str = ""
    top: list[dict] = field(default_factory=list)
    daily: list[dict] = field(default_factory=list)
    rows_used: int = 0
    rows_dropped: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def grew(self) -> bool:
        return self.delta > 0

    def facts(self) -> list[str]:
        """Claude 에게 넘길 사실 목록. **이 목록 밖의 숫자는 쓰면 안 된다.**"""
        lines = [
            f"기간: {self.start} ~ {self.end} ({self.days}일)",
            f"합계: {self.total:,}원",
            f"건수: {self.count:,}건",
            f"평균 단가: {self.average:,}원",
            f"직전 같은 기간({self.prev_start} ~ {self.prev_end}) 합계: {self.prev_total:,}원",
            f"증감: {self.delta:+,}원 ({self.delta_ratio:+.1f}%)",
        ]
        for rank, item in enumerate(self.top, start=1):
            lines.append(
                f"{rank}위 {item['name']}: {item['amount']:,}원 "
                f"(비중 {item['share']:.1f}%, 직전 대비 {item['delta']:+,}원)")
        return lines

    def numbers(self) -> set[str]:
        """사실에 들어 있는 숫자들. 지어낸 숫자를 걸러 낼 때 쓴다."""
        found: set[str] = set()
        for value in [self.total, self.count, self.average, self.prev_total,
                      self.delta, abs(self.delta), self.days]:
            found.add(str(int(value)))
            found.add(f"{int(value):,}")
        found.add(f"{self.delta_ratio:.1f}")
        found.add(f"{abs(self.delta_ratio):.1f}")
        found.add(str(int(abs(self.delta_ratio))))
        for item in self.top:
            for value in [item["amount"], abs(item["delta"])]:
                found.add(str(int(value)))
                found.add(f"{int(value):,}")
            found.add(f"{item['share']:.1f}")
            found.add(str(int(item["share"])))
        for row in self.daily:
            found.add(str(int(row["amount"])))
            found.add(f"{int(row['amount']):,}")
        # 만 단위로 줄여 쓰는 경우가 많다. "1,234,000원" → "123만"
        for value in [self.total, self.prev_total, abs(self.delta)]:
            found.add(str(int(value) // 10000))
        return found


def summarize(frame: pd.DataFrame, period: str = "week",
              end_date: str = "") -> Aggregate:
    """표 하나를 기간 보고서용 숫자로 바꾼다.

    Args:
        frame: 원본 표.
        period: week | month | quarter.
        end_date: 기준 마지막 날(YYYY-MM-DD). 비우면 자료의 마지막 날.
    """
    if period not in PERIODS:
        raise ValueError(f"기간은 {' / '.join(PERIODS)} 중 하나여야 합니다 (받은 값: {period})")
    days = PERIODS[period]

    date_column = _find(frame, DATE_NAMES)
    amount_column = _find(frame, AMOUNT_NAMES)
    if date_column is None:
        raise ColumnMissing(
            f"날짜 칸을 못 찾았습니다. 이런 이름이 있어야 합니다: {', '.join(DATE_NAMES[:3])}\n"
            f"  지금 칸: {list(frame.columns)}")
    if amount_column is None:
        raise ColumnMissing(
            f"금액 칸을 못 찾았습니다. 이런 이름이 있어야 합니다: {', '.join(AMOUNT_NAMES[:3])}\n"
            f"  지금 칸: {list(frame.columns)}")

    working = frame.copy()
    working["_date"] = pd.to_datetime(working[date_column], errors="coerce")
    working["_amount"] = _to_number(working[amount_column])

    before = len(working)
    working = working.dropna(subset=["_date"])
    dropped = before - len(working)
    if working.empty:
        raise ValueError("날짜를 읽을 수 있는 줄이 하나도 없습니다. 날짜 칸 모양을 확인하세요")

    last = pd.to_datetime(end_date) if end_date else working["_date"].max()
    start = last - timedelta(days=days - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    now = working[(working["_date"] >= start) & (working["_date"] <= last)]
    prev = working[(working["_date"] >= prev_start) & (working["_date"] <= prev_end)]

    total = int(now["_amount"].sum())
    prev_total = int(prev["_amount"].sum())
    count = int(len(now))
    delta = total - prev_total
    ratio = (delta / prev_total * 100) if prev_total else 0.0

    result = Aggregate(
        period=period, days=days,
        start=start.strftime("%Y-%m-%d"), end=last.strftime("%Y-%m-%d"),
        prev_start=prev_start.strftime("%Y-%m-%d"), prev_end=prev_end.strftime("%Y-%m-%d"),
        total=total, count=count,
        average=int(round(total / count)) if count else 0,
        prev_total=prev_total, delta=delta, delta_ratio=round(ratio, 1),
        rows_used=count, rows_dropped=dropped,
    )

    if dropped:
        result.notes.append(f"날짜를 읽지 못한 {dropped}줄은 계산에서 뺐습니다")
    if not prev_total:
        result.notes.append("직전 기간 자료가 없어 증감은 견주지 못했습니다")

    group_column = _find(frame, GROUP_NAMES)
    if group_column is not None:
        result.group_column = str(group_column)
        grouped = now.groupby(group_column)["_amount"].sum().sort_values(ascending=False)
        prev_grouped = prev.groupby(group_column)["_amount"].sum() if not prev.empty else None
        for name, amount in grouped.head(5).items():
            previous = 0
            if prev_grouped is not None and name in prev_grouped.index:
                previous = int(prev_grouped[name])
            result.top.append({
                "name": str(name),
                "amount": int(amount),
                "share": round(int(amount) / total * 100, 1) if total else 0.0,
                "delta": int(amount) - previous,
            })
    else:
        result.notes.append(
            f"채널·상품 칸이 없어 상위 5개는 만들지 못했습니다 "
            f"(이런 이름이면 됩니다: {', '.join(GROUP_NAMES[:3])})")

    by_day = now.groupby(now["_date"].dt.strftime("%Y-%m-%d"))["_amount"].sum()
    result.daily = [{"day": day, "amount": int(amount)} for day, amount in by_day.items()]

    return result
