"""테스트 공통 설정.

상품 폴더 이름에는 하이픈이 들어가 import 할 수 없으므로 각 폴더를 sys.path 에 얹는다.
상품 내부 모듈은 상품마다 고유한 패키지(`funnel_builder`, `hook_script`)에 들어 있어
이름이 충돌하지 않는다. 새 상품도 같은 규칙을 따른다.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ROOT / "products"

for path in [ROOT, *sorted(p for p in PRODUCTS.iterdir() if p.is_dir())]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
