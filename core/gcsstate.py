"""Cloud Run 에서 **지워지면 안 되는 것**을 구글 클라우드 스토리지에 맞춘다.

왜 필요한가
-----------
Cloud Run 은 컨테이너가 꺼지면 디스크가 초기화된다. 안 쓸 때 잠들었다가
요청이 오면 깨어나는 구조라 **하루에도 여러 번 꺼진다.** 그대로 두면
고객 DB 와 발급한 접속키가 날아간다.

그래서 켜질 때 버킷에서 받아 오고, 바뀌면 올려 둔다.

maim 이 먼저 겪은 것 — 같은 데서 안 넘어지려고 적어 둔다
--------------------------------------------------------
1. **시작할 때 버킷 전체를 받으면 안 된다.** 산출물이 쌓일수록 느려져서,
   컨테이너 시작 제한 시간을 넘기면 **배포 자체가 실패한다.** 그래서 여기서는
   `NEEDED` 에 적은 것만 받는다. 산출물은 다시 만들면 되는 것이라 안 받는다.
2. **GCS 를 FUSE 로 마운트해 그 위에서 SQLite 를 돌리면 불안정하다.**
   로컬 디스크에서 돌리고 파일만 주기적으로 올리는 방식을 쓴다.
3. 버킷 이름이 `YOUR_...` 자리표시자로 남은 채 배포되는 일이 잦다.
   그래서 이름이 비었거나 자리표시자면 **조용히 꺼진다** — 집에서 쓸 때와
   같은 동작이 되어 고장나지 않는다.

집에서 쓸 때
-----------
`GCS_BUCKET` 이 없으면 아무 일도 하지 않는다. 지금까지처럼 로컬 파일만 쓴다.
구글 라이브러리가 깔려 있지 않아도 마찬가지다.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from shared.config import DATA_DIR

__all__ = ["bucket_name", "enabled", "restore", "save", "start_autosave", "NEEDED"]

#: 켜질 때 받아 오고 주기적으로 올려 둘 것. **이것만** 다룬다.
#:
#: 산출물(리포트·엑셀)은 넣지 않는다. 다시 만들면 되는 것이고, 쌓이면
#: 시작이 느려져 배포가 실패한다 — maim 이 그렇게 한 번 멈췄다.
NEEDED = ("dashboard.db", ".dashboard_secret")

#: 버킷 안에서 쓸 앞머리. 한 버킷을 maim 과 같이 써도 섞이지 않게.
PREFIX = os.getenv("GCS_PREFIX", "cash-flow")

#: 몇 초마다 올릴지. maim 과 같은 60초.
INTERVAL = int(os.getenv("GCS_SYNC_SECONDS", "60"))

#: 자리표시자를 그대로 둔 채 배포하는 일이 잦다. 그건 안 켠 것으로 본다.
_PLACEHOLDERS = {"", "your_bucket", "your-bucket", "your_bucket_name", "YOUR_BUCKET"}


def bucket_name() -> str:
    """쓸 버킷 이름. 안 켰으면 빈 글자."""
    name = (os.getenv("GCS_BUCKET") or "").strip()
    if name.lower() in _PLACEHOLDERS or name.upper().startswith("YOUR_"):
        return ""
    return name


def _client():
    """구글 스토리지 손잡이. 라이브러리가 없으면 None."""
    try:
        from google.cloud import storage          # type: ignore
    except ImportError:
        return None
    try:
        return storage.Client()
    except Exception:                              # 자격 증명이 없을 때
        return None


def enabled() -> bool:
    """지금 이 판에서 GCS 를 쓰는가."""
    return bool(bucket_name()) and _client() is not None


def _blob(client, name: str):
    return client.bucket(bucket_name()).blob(f"{PREFIX}/{name}")


def restore(into: Path | None = None) -> list[str]:
    """버킷에서 **필요한 것만** 받아 온다. 받아 온 이름을 돌려준다.

    없으면 그냥 넘어간다 — 처음 켤 때는 버킷이 비어 있는 것이 정상이다.
    """
    client = _client()
    if not bucket_name() or client is None:
        return []
    target = into or DATA_DIR
    target.mkdir(parents=True, exist_ok=True)
    got = []
    for name in NEEDED:
        blob = _blob(client, name)
        try:
            if not blob.exists():
                continue
            blob.download_to_filename(str(target / name))
            got.append(name)
        except Exception:
            # 한 파일이 안 받아졌다고 서버가 안 뜨면 안 된다. 빈 상태로 시작한다.
            continue
    return got


def save(sources: Path | None = None) -> list[str]:
    """지금 상태를 버킷에 올린다. 올린 이름을 돌려준다."""
    client = _client()
    if not bucket_name() or client is None:
        return []
    source = sources or DATA_DIR
    sent = []
    for name in NEEDED:
        path = source / name
        if not path.is_file():
            continue
        try:
            _blob(client, name).upload_from_filename(str(path))
            sent.append(name)
        except Exception:
            continue
    return sent


def start_autosave() -> threading.Thread | None:
    """주기적으로 올려 두는 뒷일꾼을 띄운다. 안 켰으면 None.

    daemon 이라 서버가 멎으면 같이 멎는다. Cloud Run 이 컨테이너를 접을 때는
    마지막 한 번을 못 올릴 수 있는데, 그래서 주기를 짧게(60초) 둔다.
    """
    if not enabled():
        return None

    def 돌기() -> None:
        while True:
            time.sleep(INTERVAL)
            save()

    thread = threading.Thread(target=돌기, name="gcs-autosave", daemon=True)
    thread.start()
    return thread
