"""연결 확인 — **고객이 지금 들어갈 수 있는가.**

이 프로그램의 본체는 여기에 없다. GitHub Pages 에서 돌고, 접속키는 구글
앱스 스크립트가 내준다. 그래서 «내 컴퓨터에서 돌려 보기» 라는 시험이 성립하지
않는다. 대신 파는 사람이 정말 알고 싶은 것 하나를 확인한다 —

    고객이 지금 그 주소를 열면 열리는가. 키를 보낼 수 있는가.

셋 중 하나라도 죽으면 파는 일이 멈춘다. 그런데 죽은 줄을 모르고 있다가
고객 전화로 아는 것이 제일 나쁘다.

    python check.py            # 실제로 두드려 본다
    python check.py --dry-run  # 두드리지 않고 무엇을 볼지만 보여 준다

`--dry-run` 은 인터넷이 없거나 자동 검사에서 돌 때 쓴다. 바깥을 건드리지
않으므로 언제 돌려도 안전하다.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.registry import Registry                                   # noqa: E402

TIMEOUT = 15
#: 앱스 스크립트는 로그인 화면으로 넘기거나 302 를 준다. 200 만 성공으로 보면
#: 멀쩡한 서버를 죽었다고 말한다. «응답이 왔다» 까지만 본다.
OK_CODES = range(200, 400)


def 볼곳() -> list[tuple[str, str, str]]:
    """확인할 주소들. (이름, 주소, 없을 때 할 말)"""
    program = Registry().require("exam-drill")
    return [
        ("고객이 들어가는 곳", program.live.client,
         "program.yaml 의 live.client 가 비었습니다"),
        ("관리자 화면", program.live.admin,
         "program.yaml 의 live.admin 이 비었습니다"),
        ("접속키 서버", (os.getenv("KEYSERVER_URL") or "").strip(),
         ".env 의 KEYSERVER_URL 이 비었습니다 — 키를 보낼 수 없습니다"),
    ]


def 두드리기(url: str) -> tuple[bool, str]:
    """한 번 열어 본다. (됐나, 할 말)"""
    request = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "exam-drill-check/1"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            code = response.status
        return (code in OK_CODES), f"HTTP {code}"
    except urllib.error.HTTPError as error:
        return (error.code in OK_CODES), f"HTTP {error.code}"
    except urllib.error.URLError as error:
        return False, f"닿지 못했습니다 — {error.reason}"
    except OSError as error:                      # 타임아웃·DNS 등
        return False, f"닿지 못했습니다 — {error}"


def main() -> int:
    parser = argparse.ArgumentParser(description="고객이 지금 들어갈 수 있는지 확인합니다")
    parser.add_argument("--dry-run", action="store_true",
                        help="바깥을 두드리지 않고 무엇을 볼지만 보여 줍니다")
    args = parser.parse_args()

    print("연결 확인 — 고객이 지금 들어갈 수 있는가")
    print("=" * 52)

    나쁨 = 0
    for 이름, 주소, 없을때 in 볼곳():
        if not 주소:
            print(f"  ✗  {이름}\n       {없을때}")
            나쁨 += 1
            continue
        if args.dry_run:
            print(f"  ·  {이름}\n       {주소}")
            continue
        됐나, 말 = 두드리기(주소)
        print(f"  {'✓' if 됐나 else '✗'}  {이름}  ({말})\n       {주소}")
        if not 됐나:
            나쁨 += 1

    print("=" * 52)
    if args.dry_run:
        # 두드리지는 않았지만 **주소가 비어 있는 것**은 지금도 안다.
        # 그것까지 초록으로 넘기면 확인의 뜻이 없다.
        if 나쁨:
            print(f"{나쁨}군데는 주소부터 비어 있습니다. 두드려 볼 것도 없습니다.")
            return 1
        print("주소는 셋 다 적혀 있습니다. 실제로 열리는지는 [지금 확인하기] 로 보세요.")
        return 0
    if 나쁨:
        print(f"{나쁨}군데가 응답하지 않습니다. **고객에게 키를 보내기 전에** 고치세요.")
        return 1
    print("셋 다 살아 있습니다. 키를 보내셔도 됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
