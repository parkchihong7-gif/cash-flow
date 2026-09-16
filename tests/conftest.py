"""테스트 공통 설정.

상품 폴더 이름에 하이픈이 들어가 패키지로 import 할 수 없으므로 경로를 직접 얹는다.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for path in (ROOT, ROOT / "products" / "funnel-builder"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
