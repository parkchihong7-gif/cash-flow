"""단가표 읽기 — **출처 없는 숫자는 받지 않는다.**

견적 도구에서 가장 위험한 것은 근거 없는 단가다. "한 편에 3천 원" 이라고
적어 놓으면 사람들은 그걸 믿는다. 그런데 요금제는 자주 바뀌고, 바뀐 걸 모르면
견적이 통째로 틀어진다.

그래서 이 모듈은 `source` 가 비어 있는 항목을 **읽는 단계에서 거절한다.**
고칠 때 출처도 같이 고치게 만드는 장치다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

__all__ = ["Rate", "RateTable", "load_rates", "RateError", "MIN_SOURCE_LEN"]

#: 출처가 이보다 짧으면 "확인 필요" 같은 말만 적은 것으로 본다.
MIN_SOURCE_LEN = 8


class RateError(ValueError):
    """단가표가 규격에 안 맞을 때."""


@dataclass
class Rate:
    """단가 한 줄."""

    key: str
    name: str
    won: float
    unit: str
    note: str = ""
    source: str = ""
    quality: str = ""
    senior_fit: int = 0

    @property
    def free(self) -> bool:
        return self.won <= 0

    @property
    def fit_stars(self) -> str:
        return "★" * self.senior_fit + "☆" * (5 - self.senior_fit) if self.senior_fit else ""


@dataclass
class RateTable:
    """단가표 전체."""

    tts: list[Rate]
    image: list[Rate]
    script: list[Rate]
    render_won: float
    storage_won: float
    asof: str
    fx: int
    caution: str

    def pick(self, group: str, key: str) -> Rate:
        table = {"tts": self.tts, "image": self.image, "script": self.script}[group]
        for item in table:
            if item.key == key:
                return item
        raise RateError(
            f"모르는 {group} 항목입니다: {key}\n"
            f"  쓸 수 있는 것: {', '.join(row.key for row in table)}")

    def cheapest(self, group: str) -> Rate:
        table = {"tts": self.tts, "image": self.image, "script": self.script}[group]
        return min(table, key=lambda row: row.won)

    def best_for_senior(self) -> Rate:
        """시니어 적합도가 가장 높은 음성. 값이 같으면 싼 쪽."""
        return max(self.tts, key=lambda row: (row.senior_fit, -row.won))


def _rows(raw: list, group: str, unit: str, won_field: str) -> list[Rate]:
    rows: list[Rate] = []
    for item in raw or []:
        source = str(item.get("source") or "").strip()
        if len(source) < MIN_SOURCE_LEN:
            raise RateError(
                f"{group}/{item.get('key')} 에 출처가 없습니다.\n"
                f"  단가를 고칠 때는 어디서 본 값인지도 같이 적으세요. "
                f"근거 없는 견적은 나중에 분쟁이 됩니다")
        rows.append(Rate(
            key=str(item["key"]),
            name=str(item.get("name") or item["key"]),
            won=float(item.get(won_field) or 0),
            unit=unit,
            note=str(item.get("note") or ""),
            source=source,
            quality=str(item.get("quality") or ""),
            senior_fit=int(item.get("senior_fit") or 0),
        ))
    if not rows:
        raise RateError(f"{group} 항목이 비어 있습니다")
    return rows


def load_rates(path: str | Path) -> RateTable:
    """단가표 YAML 을 읽는다."""
    path = Path(path)
    if not path.is_file():
        raise RateError(f"단가표가 없습니다: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    meta = raw.get("meta") or {}
    etc = raw.get("etc") or {}

    asof = str(meta.get("기준일") or "").strip()
    if not asof:
        raise RateError("단가표에 기준일이 없습니다. 언제 조사한 값인지 적으세요")

    return RateTable(
        tts=_rows(raw.get("tts"), "tts", "1,000자", "won_per_1k_chars"),
        image=_rows(raw.get("image"), "image", "장", "won_per_image"),
        script=_rows(raw.get("script"), "script", "편", "won_per_video"),
        render_won=float(etc.get("render_won_per_video") or 0),
        storage_won=float(etc.get("storage_won_per_gb_month") or 0),
        asof=asof,
        fx=int(meta.get("환율") or 0),
        caution=str(meta.get("주의") or ""),
    )
