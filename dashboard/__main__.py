"""대시보드 실행 진입점.

    python -m dashboard                 # http://127.0.0.1:8000
    python -m dashboard --port 9000
    python -m dashboard --host 0.0.0.0  # 같은 네트워크의 다른 기기에서도 접속
"""

from __future__ import annotations

import argparse
import webbrowser

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m dashboard", description="통합 관리자 대시보드를 띄웁니다"
    )
    parser.add_argument("--host", default="127.0.0.1", help="기본: 127.0.0.1 (내 PC 에서만 접속)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="코드를 고치면 자동 재시작 (개발용)")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    args = parser.parse_args()

    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    print(f"통합 관리자 대시보드를 시작합니다 → {url}")
    print("종료하려면 Ctrl+C 를 누르세요.")

    if not args.no_browser and not args.reload:
        try:
            webbrowser.open(url)
        except Exception:
            pass  # 브라우저가 없는 환경(서버 등)에서는 조용히 넘어간다

    uvicorn.run(
        "dashboard.app:app" if args.reload else "dashboard.app:app",
        host=args.host, port=args.port, reload=args.reload, log_level="info",
    )


if __name__ == "__main__":
    main()
