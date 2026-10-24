"""`python -m orbit` — 관리자 화면을 띄우고 브라우저를 연다."""

from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import uvicorn  # noqa: E402

from orbit import PORT  # noqa: E402
from orbit.app import create_app  # noqa: E402


def main() -> None:
    url = f"http://127.0.0.1:{PORT}"
    print(f"셀럽오르빗 관리자 — {url}\n끄려면 이 창에서 Ctrl+C")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(), host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
