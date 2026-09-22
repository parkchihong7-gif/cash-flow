"""연결 확인 — **고객이 지금 들어갈 수 있는가.**

본체(maim)가 여기에 없다. Google Cloud Run 에서 돌고, 안 쓸 때는 잠들어
있다가 요청이 오면 깨어난다. 그래서 «내 컴퓨터에서 돌려 보기» 라는 시험이
성립하지 않는다. 대신 파는 사람이 정말 알고 싶은 것 하나를 확인한다 —

    고객이 지금 그 주소를 열면 열리는가.

잠들어 있으면 첫 응답이 늦다. 그래서 넉넉히 기다린다.

    python check.py            # 실제로 두드려 본다
    python check.py --dry-run  # 두드리지 않고 무엇을 볼지만 보여 준다
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.registry import Registry                                   # noqa: E402

#: 잠든 컨테이너가 깨어나는 데 2~10초 걸린다. 짧게 잡으면 멀쩡한 서버를
#: 죽었다고 말한다.
TIMEOUT = 45
#: 로그인 화면으로 넘기거나 302 를 주는 것이 정상이다. 200 만 성공으로 보면
#: 안 된다. «응답이 왔다» 까지만 본다.
OK_CODES = range(200, 400)


def 두드리기(url: str) -> tuple[bool, str]:
    request = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "naver-blog-check/1"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            code = response.status
        return (code in OK_CODES), f"HTTP {code}"
    except urllib.error.HTTPError as error:
        return (error.code in OK_CODES), f"HTTP {error.code}"
    except urllib.error.URLError as error:
        return False, f"닿지 못했습니다 — {error.reason}"
    except OSError as error:
        return False, f"닿지 못했습니다 — {error}"


def main() -> int:
    parser = argparse.ArgumentParser(description="고객이 지금 들어갈 수 있는지 확인합니다")
    parser.add_argument("--dry-run", action="store_true",
                        help="바깥을 두드리지 않고 무엇을 볼지만 보여 줍니다")
    args = parser.parse_args()

    program = Registry().require("naver-blog")
    주소 = program.live.admin or program.live.client

    print("연결 확인 — 고객이 지금 들어갈 수 있는가")
    print("=" * 52)

    if not 주소:
        print("  ✗ 프로그램 주소\n       program.yaml 의 live 가 비었습니다")
        print("=" * 52)
        return 1

    if args.dry_run:
        print(f"  ·  프로그램 (관리자·고객 같은 주소)\n       {주소}")
        print("=" * 52)
        print("주소는 적혀 있습니다. 실제로 열리는지는 [지금 확인하기] 로 보세요.")
        return 0

    print("  잠들어 있으면 깨어나는 데 몇 초 걸립니다...")
    됐나, 말 = 두드리기(주소)
    print(f"  {'✓' if 됐나 else '✗'}  프로그램 (관리자·고객 같은 주소)  ({말})")
    print(f"       {주소}")
    print("=" * 52)
    if not 됐나:
        print("응답하지 않습니다. **고객에게 코드를 보내기 전에** 고치세요.")
        print("  gcloud run services list  로 서비스가 살아 있는지 보십시오.")
        return 1
    print("살아 있습니다. 코드를 보내셔도 됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
