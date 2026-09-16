"""환경 변수 로드와 경로 상수.

`.env` 는 저장소 루트에서 읽는다. 실제 키는 절대 커밋하지 않는다 (CLAUDE.md §6).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------- 경로 상수
ROOT_DIR = Path(__file__).resolve().parent.parent
SHARED_DIR = ROOT_DIR / "shared"
PRODUCTS_DIR = ROOT_DIR / "products"
TESTS_DIR = ROOT_DIR / "tests"
OUTPUTS_DIR = ROOT_DIR / "outputs"
ENV_PATH = ROOT_DIR / ".env"

load_dotenv(ENV_PATH)

#: 지워지면 안 되는 것(고객 DB, 세션 서명값)을 두는 곳.
#:
#: 기본은 저장소 폴더다. 클라우드에 올리면 배포할 때마다 파일이 초기화되므로,
#: 거기서는 `DASHBOARD_DATA_DIR` 을 디스크가 붙은 경로로 지정해야 고객 정보가 남는다.
DATA_DIR = Path(os.getenv("DASHBOARD_DATA_DIR") or ROOT_DIR)
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


# ---------------------------------------------------------------- 설정 값
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

#: 기본 모델. CLAUDE.md §6 기준값이며 CLAUDE_MODEL 로 덮어쓸 수 있다.
DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
DEFAULT_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "4000"))

#: AI 생성물 표시 기본값. CLAUDE.md §7 에 따라 기본 on.
AI_LABEL_DEFAULT = _env_flag("AI_LABEL", True)

#: add_metadata() 가 상품명을 추론하지 못했을 때 쓰는 이름.
DEFAULT_TOOL_NAME = "cash-flow"


def ensure_outputs_dir(subdir: str | None = None) -> Path:
    """`outputs/` (또는 그 하위 폴더)를 만들고 경로를 돌려준다."""
    path = OUTPUTS_DIR if subdir is None else OUTPUTS_DIR / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def require_api_key() -> str:
    """ANTHROPIC_API_KEY 를 돌려준다. 없으면 무엇을 해야 하는지 알려준다."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY 가 없습니다. .env.example 을 .env 로 복사하고 키를 넣으세요."
        )
    return ANTHROPIC_API_KEY
