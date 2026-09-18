"""화면 캡처 — 교육자료에 넣을 실제 화면을 찍는다.

교육자료는 **화면이 바뀌면 같이 바뀌어야** 한다. 손으로 캡처하면 그 일이
안 일어난다. 그래서 스크립트로 만들어 레포에 둔다. 2·3차 수정 뒤에 이걸
한 번 돌리고 PPT 를 다시 만들면 된다.

    python tools/capture_screens.py                    전부
    python tools/capture_screens.py --only exam-drill  한 상품만
    python tools/capture_screens.py --out /tmp/shots

찍은 그림은 커밋하지 않는다(용량). `.gitignore` 에 있다.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_OUT = ROOT / "docs" / "training" / "screens"
ACCESS_CODE = "capture-code"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

#: 통합 대시보드에서 찍을 화면. (파일이름, 주소, 설명)
DASHBOARD_PAGES = (
    ("00_home", "/", "홈 — 오늘 볼 것과 매출 추이"),
    ("01_access", "/access", "권한·환경 — 집 컴퓨터로 되나, 무슨 계정이 필요한가"),
    ("02_schedule", "/schedule", "정기 실행 — 안 돌린 날을 화면이 기억한다"),
    ("03_config", "/config", "설정 한눈에 — 흩어진 설정값을 한 장에"),
    ("04_rules", "/rules", "규정 점검 — 법·정책 장치가 붙어 있는지"),
    ("05_revenue", "/revenue", "수입 현황 — 일회성과 월 유지비를 나눠서"),
    ("06_runs", "/runs", "실행 이력"),
)


def _free_port(start: int = 8811) -> int:
    for port in range(start, start + 50):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("빈 포트를 찾지 못했습니다")


def _wait(port: int, seconds: int = 30) -> bool:
    for _ in range(seconds * 4):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.25)
    return False


async def _shoot(out_dir: Path, port: int, only: str) -> list[tuple[str, str]]:
    from playwright.async_api import async_playwright

    from core.registry import Registry

    base = f"http://127.0.0.1:{port}"
    out_dir.mkdir(parents=True, exist_ok=True)
    made: list[tuple[str, str]] = []
    problems: list[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=CHROME)
        context = await browser.new_context(viewport={"width": 1280, "height": 900},
                                            device_scale_factor=2)
        page = await context.new_page()
        page.on("pageerror", lambda exc: problems.append(str(exc)))

        await page.goto(f"{base}/login")
        await page.fill('input[name="code"]', ACCESS_CODE)
        await page.click('button[type="submit"]')
        await page.wait_for_load_state()

        if not only:
            for name, url, caption in DASHBOARD_PAGES:
                await page.goto(f"{base}{url}")
                await page.wait_for_timeout(500)
                path = out_dir / f"dash_{name}.png"
                await page.screenshot(path=str(path), full_page=True)
                made.append((path.name, caption))
                print(f"  ✓ {path.name}")

        for program in Registry().programs:
            if only and program.id != only:
                continue
            for mode, label in (("admin", "관리자 모드"), ("client", "클라이언트 모드")):
                response = await page.goto(f"{base}/apps/{program.id}/{mode}")
                if response is None or response.status != 200:
                    problems.append(f"{program.id}/{mode} → {response.status if response else '없음'}")
                    continue
                await page.wait_for_timeout(400)
                path = out_dir / f"{program.number:02d}_{program.id}_{mode}.png"
                await page.screenshot(path=str(path), full_page=True)
                made.append((path.name, f"{program.number}. {program.name} — {label}"))
                print(f"  ✓ {path.name}")

            # 상세 페이지(두 모드 버튼이 보이는 화면)도 한 장
            await page.goto(f"{base}/programs/{program.id}")
            await page.wait_for_timeout(300)
            path = out_dir / f"{program.number:02d}_{program.id}_detail.png"
            await page.screenshot(path=str(path), clip={"x": 0, "y": 0,
                                                        "width": 1280, "height": 520})
            made.append((path.name, f"{program.number}. {program.name} — 통합 대시보드 상세"))

        await browser.close()

    if problems:
        print("\n⚠ 문제:")
        for item in problems[:10]:
            print(f"  - {item}")
    return made


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="capture_screens.py",
        description="교육자료에 넣을 화면을 찍습니다 (실제 서버를 띄워서)")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--only", default="", help="상품 id 하나만")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)

    port = args.port or _free_port()
    env = {**os.environ, "DASHBOARD_ACCESS_CODE": ACCESS_CODE,
           "PYTHONUNBUFFERED": "1"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "dashboard.app:app",
         "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not _wait(port):
            print("서버가 뜨지 않았습니다.", file=sys.stderr)
            return 1
        print(f"서버 {port} 포트 · 찍는 곳 {args.out}")
        made = asyncio.run(_shoot(Path(args.out), port, args.only))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    print(f"\n{len(made)}장 찍었습니다 → {args.out}")
    index = Path(args.out) / "INDEX.md"
    index.write_text(
        "# 화면 캡처 목록\n\n"
        "`python tools/capture_screens.py` 로 다시 만듭니다. "
        "**화면이 바뀌면 다시 찍고 교육자료도 다시 만드세요.**\n\n"
        + "\n".join(f"- `{name}` — {caption}" for name, caption in made) + "\n",
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
