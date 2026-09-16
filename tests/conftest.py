"""테스트 공통 설정.

상품 폴더 이름에는 하이픈이 들어가 import 할 수 없으므로 각 폴더를 sys.path 에 얹는다.
상품 내부 모듈은 상품마다 고유한 패키지(`funnel_builder`, `hook_script`)에 들어 있어
이름이 충돌하지 않는다. 새 상품도 같은 규칙을 따른다.

다만 `cli.py` 만은 모든 상품이 같은 이름으로 폴더 최상단에 둔다(사용자가
`python cli.py` 로 치는 이름이라 바꿀 수 없다). 그래서 `import cli` 하면
sys.path 에서 먼저 잡히는 상품의 것이 들어온다 — 한 테스트 파일이 먼저 실어 두면
다른 테스트 파일이 엉뚱한 모듈을 받는다. `load_product_cli()` 로 경로를 지정해
고유한 이름으로 싣는다.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ROOT / "products"

for path in [ROOT, *sorted(p for p in PRODUCTS.iterdir() if p.is_dir())]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def load_product_cli(product_id: str) -> ModuleType:
    """`products/<product_id>/cli.py` 를 상품별 고유 이름으로 싣는다.

    `import cli` 는 상품끼리 이름이 겹쳐 쓸 수 없다. 이 함수는 경로를 직접 지정하고
    `cli_<product_id>` 라는 이름으로 등록하므로 어느 테스트가 먼저 돌든 결과가 같다.
    """
    module_name = "cli_" + product_id.replace("-", "_")
    if module_name in sys.modules:
        return sys.modules[module_name]

    path = PRODUCTS / product_id / "cli.py"
    if not path.is_file():
        raise FileNotFoundError(f"cli.py 가 없습니다: {path}")

    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
