"""대시보드 실행 진입점.

    python -m dashboard                 # 내 PC 에서만 (http://127.0.0.1:8000)
    python -m dashboard --public        # 어디서나 되는 https 주소를 만들어 준다
    python -m dashboard --host 0.0.0.0  # 같은 공유기에 있는 기기에서 접속
    python -m dashboard --port 9000

어느 쪽으로 띄우든 **접속 코드를 넣어야 화면이 열립니다**(`core/auth.py`).
코드는 `.env` 의 `DASHBOARD_ACCESS_CODE` 로 바꿉니다.

`--public` 은 Cloudflare 임시 터널을 씁니다. 가입 없이 바로 https 주소가
나오지만, **이 창을 닫으면 주소가 사라지고 다음에 켜면 주소가 바뀝니다.**
늘 같은 주소가 필요하면 README 의 '항상 켜 두기' 를 보세요.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import webbrowser

import uvicorn

from core import auth

#: cloudflared 가 주소를 뱉을 때 쓰는 모양.
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

#: 주소가 안 나오는 이유를 알려 주는 줄을 골라내는 모양.
FAILURE = re.compile(r"(?i)\b(failed|error|ERR)\b")

#: 이만큼 지나도 주소가 안 나오면 한마디 한다.
WAIT_SECONDS = 25

TUNNEL_FAILED = """
주소를 만들지 못할 때 흔한 이유입니다.

  - 회사·학교 네트워크가 막고 있다 → 집 인터넷이나 휴대폰 핫스팟으로 해 보세요
  - 인터넷이 끊겼다
  - cloudflared 쪽이 잠깐 안 된다 → 몇 분 뒤 다시 해 보세요

그동안 쓸 수 있는 방법입니다.
  같은 공유기 안에서만   python -m dashboard --host 0.0.0.0
  늘 같은 주소로        README 의 '항상 켜 두기' 를 보세요
""".rstrip()

INSTALL_HINT = """
`--public` 을 쓰려면 cloudflared 가 필요합니다. 한 번만 깔면 됩니다.

  macOS      brew install cloudflared
  Windows    winget install --id Cloudflare.cloudflared
  Linux      https://github.com/cloudflare/cloudflared/releases 에서 받으세요

깔기 어려우시면 대신 이렇게 하세요.
  1) 같은 공유기 안에서만 쓰기   python -m dashboard --host 0.0.0.0
  2) 늘 같은 주소로 쓰기        README 의 '항상 켜 두기' 를 보세요
""".strip()


def _announce(port: int) -> None:
    """접속 코드 상태를 알려 준다."""
    print()
    print(f"  접속 코드: {auth.access_code()}")
    if auth.is_default_code():
        print("  ⚠ 기본 코드를 그대로 쓰고 있습니다.")
        print("    인터넷에 열어 두실 거라면 .env 에 DASHBOARD_ACCESS_CODE 를 넣어 바꾸세요.")
    print(f"  한 번 들어가면 {auth.session_hours()}시간 동안 유지됩니다.")
    print()


def _start_tunnel(port: int) -> subprocess.Popen | None:
    """Cloudflare 임시 터널을 띄우고 주소를 출력한다.

    주소가 안 나오는 경우가 종종 있다. 회사 방화벽이 막거나, 인터넷이
    끊겼거나, cloudflared 쪽이 잠깐 안 될 때다. 그때 아무것도 알려 주지 않으면
    터미널만 보며 기다리게 되므로, 실패한 이유를 그대로 보여 준다.
    """
    binary = shutil.which("cloudflared")
    if binary is None:
        print(INSTALL_HINT, file=sys.stderr)
        return None

    process = subprocess.Popen(
        [binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    found_url = threading.Event()

    def watch() -> None:
        tail: list[str] = []
        for line in process.stdout or []:
            tail.append(line.rstrip())
            del tail[:-12]

            found = TUNNEL_URL.search(line)
            if found and not found_url.is_set():
                found_url.set()
                print()
                print("  " + "=" * 58)
                print(f"  어디서나 접속:  {found.group(0)}")
                print(f"  접속 코드:      {auth.access_code()}")
                print("  " + "=" * 58)
                print("  이 창을 닫으면 주소가 사라집니다.")
                print()
            elif not found_url.is_set() and FAILURE.search(line):
                print(f"  cloudflared: {line.strip()}", file=sys.stderr)

        # 여기까지 왔으면 cloudflared 가 끝난 것이다
        if not found_url.is_set():
            print(file=sys.stderr)
            print("  주소를 만들지 못했습니다. cloudflared 가 남긴 마지막 줄입니다.", file=sys.stderr)
            for line in tail:
                print(f"    {line}", file=sys.stderr)
            print(TUNNEL_FAILED, file=sys.stderr)

    threading.Thread(target=watch, daemon=True).start()

    def nag() -> None:
        if not found_url.wait(WAIT_SECONDS) and process.poll() is None:
            print(f"  ({WAIT_SECONDS}초가 지나도 주소가 안 나옵니다. "
                  "조금 더 기다려 보시고, 계속 안 나오면 Ctrl+C 로 끄세요.)",
                  file=sys.stderr)

    threading.Thread(target=nag, daemon=True).start()
    return process


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m dashboard", description="통합 관리자 대시보드를 띄웁니다"
    )
    parser.add_argument("--host", default="", help="기본: 127.0.0.1 (내 PC 에서만 접속)")
    parser.add_argument("--port", type=int, default=0,
                        help="기본: 8000. 환경변수 PORT 가 있으면 그 값을 씁니다")
    parser.add_argument("--public", action="store_true",
                        help="어디서나 접속되는 https 주소를 만듭니다 (cloudflared 필요)")
    parser.add_argument("--reload", action="store_true", help="코드를 고치면 자동 재시작 (개발용)")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    args = parser.parse_args()

    # 클라우드 호스팅(Render·Railway 등)은 쓸 포트를 `PORT` 로 알려 주고,
    # 바깥에서 닿게 하려면 0.0.0.0 에 붙으라고 요구한다. 그 관례를 따른다.
    on_hosting = bool(os.getenv("PORT")) and not args.host
    port = args.port or int(os.getenv("PORT", "8000"))
    host = args.host or ("0.0.0.0" if on_hosting else "127.0.0.1")

    local = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
    print(f"통합 관리자 대시보드를 시작합니다 → {local}")
    _announce(port)

    tunnel = _start_tunnel(port) if args.public else None
    if args.public and tunnel is None:
        raise SystemExit(1)

    if not args.no_browser and not args.reload and not args.public:
        try:
            webbrowser.open(local)
        except Exception:
            pass  # 브라우저가 없는 환경(서버 등)에서는 조용히 넘어간다

    print("종료하려면 Ctrl+C 를 누르세요.")
    try:
        uvicorn.run("dashboard.app:app", host=host, port=port,
                    reload=args.reload, log_level="info",
                    # 터널·클라우드 뒤에 있으면 접속자 주소가 헤더로 온다.
                    # 그 헤더를 믿어야 코드 잠금이 사람별로 걸린다.
                    forwarded_allow_ips="*" if (args.public or on_hosting) else None)
    finally:
        if tunnel is not None:
            tunnel.terminate()


if __name__ == "__main__":
    main()
