"""프로그램이 늘어도 통합보드가 무거워지지 않는가.

**한 번 데였다.** 3번(maim)이 제 DB 를 살아 있는 채로 올리다가 깨져서
초기화했다. 여기도 같은 코드였다. 그것은 고쳤고, 이 시험은 그다음 —
«시간이 지나면서 조용히 무거워지는 것» 을 막는다.

두 가지를 본다.
    쌓이는 것   실행 로그가 무한히 늘지 않는가
    번지는 것   제 칸(GCS_PREFIX) 밖으로 나가지 않는가
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from core.db import LOG_KEEP, ROW_KEEP, Database


def _돌려보기(db: Database, program_id: str, 몇번: int, 로그="x" * 20_000):
    for _ in range(몇번):
        run_id = db.start_run(program_id, "real")
        db.finish_run(run_id, "success", 0, 로그)


@pytest.fixture()
def db(tmp_path):
    return Database(tmp_path / "t.db")


def test_옛_로그는_지워지고_줄은_남는다(db):
    """«언제 돌렸고 잘 됐나» 는 남고, 자리를 먹는 본문만 없앤다."""
    _돌려보기(db, "exam-drill", LOG_KEEP + 5)

    줄들 = db.list_runs("exam-drill", limit=999)
    assert len(줄들) == LOG_KEEP + 5, "줄까지 지우면 안 됩니다"

    로그있는것 = [r for r in 줄들 if r["log"]]
    assert len(로그있는것) == LOG_KEEP, f"로그가 {len(로그있는것)}개 남았습니다"
    # 남은 것은 **최근 것**이어야 한다. 고칠 때 보는 것은 대개 방금 것이다.
    # (`started_at` 은 초 단위라 차례를 믿을 수 없다. `id` 로 본다.)
    모든번호 = sorted(r["id"] for r in 줄들)
    assert sorted(r["id"] for r in 로그있는것) == 모든번호[-LOG_KEEP:]


def test_아주_옛것은_줄까지_지운다(db):
    _돌려보기(db, "exam-drill", ROW_KEEP + 10, 로그="짧은 로그")
    assert len(db.list_runs("exam-drill", limit=9999)) == ROW_KEEP


def test_프로그램마다_따로_센다(db):
    """자주 돌리는 하나가 다른 것들의 기록을 밀어내면 안 된다."""
    _돌려보기(db, "exam-drill", ROW_KEEP + 50, 로그="짧게")
    _돌려보기(db, "naver-blog", 3, 로그="짧게")

    assert len(db.list_runs("naver-blog", limit=999)) == 3, "남의 기록이 밀렸습니다"
    assert len(db.list_runs("exam-drill", limit=9999)) == ROW_KEEP


def test_천번_돌려도_DB_가_커지지_않는다(db, tmp_path):
    """이것이 이 시험의 본론이다.

    로그 한 번이 2만 자다. 안 줄이면 천 번에 20MB 가 되고, 그것이 60초마다
    통째로 버킷에 올라간다. 올리는 동안 글을 쓰면 깨질 틈이 그만큼 넓어진다.
    """
    _돌려보기(db, "exam-drill", 1000)
    db.execute("VACUUM")          # 지운 자리를 실제로 돌려받는다
    크기 = (tmp_path / "t.db").stat().st_size
    # 안 줄이면 1,000 × 2만 자 = 20MB 다. 1MB 안이면 줄고 있는 것이다.
    assert 크기 < 1_000_000, f"{크기:,}바이트 — 안 줄고 있습니다 (안 줄이면 20MB)"


# ─────────────────────────────────────────────────────────────────────
# 제 칸 밖으로 나가지 않는가
# ─────────────────────────────────────────────────────────────────────

def test_칸_이름이_이상해도_뿌리에_안_쓴다(monkeypatch):
    """비거나 `/` 면 버킷 뿌리에 쓰게 된다. 그러면 남의 파일과 부딪힌다."""
    import core.gcsstate as gcsstate

    for 이상한값 in ("", "/", "   ", "///"):
        monkeypatch.setenv("GCS_PREFIX", 이상한값)
        importlib.reload(gcsstate)
        assert gcsstate.PREFIX == "cash-flow", f"{이상한값!r} → {gcsstate.PREFIX!r}"
    monkeypatch.delenv("GCS_PREFIX", raising=False)
    importlib.reload(gcsstate)


def test_버킷_전체를_훑는_곳이_없다():
    """제 칸만 본다.

    3번(maim)이 «generated/ 빼고 전부» 를 제 것으로 알고 가져가다가
    이 칸까지 덮어썼다. 이쪽은 그 실수를 안 하게 못 박는다.
    """
    글 = Path("core/gcsstate.py").read_text(encoding="utf-8")
    코드 = "\n".join(줄 for 줄 in 글.split("\n")
                     if not 줄.lstrip().startswith("#"))

    for 줄 in 코드.split("\n"):
        if "list_blobs(" in 줄:
            assert "prefix=" in 줄, f"버킷 전체를 훑습니다: {줄.strip()}"

    # 버킷에 닿는 모든 이름은 PREFIX 를 거쳐야 한다.
    for m in re.finditer(r"\.blob\(([^)]*)\)", 코드):
        assert "PREFIX" in m.group(1), f"칸 밖을 가리킵니다: {m.group(0)}"
