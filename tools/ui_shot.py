"""화면 확인 도구 — 숫자로 먼저 검사하고, 사진은 꼭 필요한 것만 JPEG 로.

회차마다 캡처 스크립트를 새로 쓰지 않으려고 만든 공용 도구다. 확인은 `check`
(자바스크립트 식의 값을 찍음)로 먼저 하고, 눈으로 볼 사진은 1~2장만 연다.

    python tools/ui_shot.py spec.json 출력폴더

spec.json 예
{
  "url": "http://localhost:8793/",
  "init": "localStorage.setItem('maim-dashboard-token','owner-test-token-local')",
  "viewports": [[1180, 900], [390, 844]],
  "steps": [
    {"js": "switchView('categories')"}, {"wait": 1000},
    {"check": "document.documentElement.scrollWidth - innerWidth", "label": "가로 넘침"},
    {"shot": "#category-table", "out": "table", "only": 1180}
  ]
}
- js     : 화면에서 실행 (await 가능한 식)
- wait   : ms 기다리기
- check  : 식의 값을 `라벨[폭]: 값` 으로 찍는다
- shot   : 요소(또는 "page")를 출력폴더/out-폭.jpg 로 저장 (q70). only 로 특정 폭에서만
페이지 오류(pageerror)는 끝에 모아 찍는다.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

브라우저 = os.environ.get("CHROME_BIN", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


async def 돌리기(spec: dict, 출력: Path) -> int:
    from playwright.async_api import async_playwright

    출력.mkdir(parents=True, exist_ok=True)
    오류: list[str] = []
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=브라우저 if Path(브라우저).exists() else None)
        for 폭, 높이 in spec.get("viewports", [[1180, 900]]):
            ctx = await b.new_context(viewport={"width": 폭, "height": 높이})
            if spec.get("init"):
                await ctx.add_init_script(spec["init"])
            pg = await ctx.new_page()
            pg.on("pageerror", lambda e, w=폭: 오류.append(f"[{w}] {e}"))
            await pg.goto(spec["url"])
            await pg.wait_for_timeout(spec.get("settle", 1500))
            for s in spec.get("steps", []):
                if s.get("only") and s["only"] != 폭:
                    continue
                if "js" in s:
                    await pg.evaluate(s["js"])
                elif "wait" in s:
                    await pg.wait_for_timeout(s["wait"])
                elif "check" in s:
                    값 = await pg.evaluate(s["check"])
                    print(f"{s.get('label', s['check'][:40])}[{폭}]: {json.dumps(값, ensure_ascii=False)}")
                elif "shot" in s:
                    파일 = 출력 / f"{s.get('out', 'shot')}-{폭}.jpg"
                    if s["shot"] == "page":
                        await pg.screenshot(path=str(파일), type="jpeg", quality=70, full_page=s.get("full", False))
                    else:
                        el = await pg.query_selector(s["shot"])
                        if not el:
                            print(f"⚠ 없음: {s['shot']}")
                            continue
                        await el.scroll_into_view_if_needed()
                        await el.screenshot(path=str(파일), type="jpeg", quality=70)
                    print(f"사진: {파일} {파일.stat().st_size // 1024}KB")
            await ctx.close()
        await b.close()
    print("페이지 오류:", 오류 or "없음")
    return 1 if 오류 else 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(asyncio.run(돌리기(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), Path(sys.argv[2]))))
