"""고객 DB 를 통째로 한 벌 떠내는 곳.

클라우드에 대시보드를 올리면 고객 이름·이메일·발급한 키가 전부 그쪽에
쌓인다. 호스팅 계정이 잠기거나, 요금을 못 내거나, 디스크를 잘못 지우면
**판 키의 목록이 통째로 사라진다.** 그래서 집 컴퓨터로 한 벌 내려받는
길을 둔다.

`cp` 로 복사하면 안 된다. 그 순간 누가 키를 발급하고 있으면 반쯤 쓰다 만
파일을 복사해 열리지 않는 DB 가 나온다. SQLite 가 주는 온라인 백업을
쓰면 쓰는 중에도 앞뒤가 맞는 한 벌이 나온다.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

__all__ = ["backup_name", "copy_db"]


def backup_name(now: datetime | None = None) -> str:
    """내려받을 때 붙일 파일 이름. 날짜가 들어가 덮어쓰지 않는다."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M")
    return f"dashboard-{stamp}.db"


def copy_db(src: str | Path, dest: str | Path) -> int:
    """`src` 를 `dest` 로 한 벌 뜬다. 쓰는 중이어도 깨지지 않는다.

    Args:
        src: 원본 DB 경로.
        dest: 받을 자리. 있으면 덮어쓴다.

    Returns:
        만들어진 파일 크기(바이트).

    Raises:
        FileNotFoundError: 원본이 없을 때.
    """
    src, dest = Path(src), Path(dest)
    if not src.exists():
        raise FileNotFoundError(f"DB 가 없습니다: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 읽기 전용으로 연다. 백업 뜨다가 원본을 건드리는 일이 없게.
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    target = sqlite3.connect(dest)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return dest.stat().st_size
