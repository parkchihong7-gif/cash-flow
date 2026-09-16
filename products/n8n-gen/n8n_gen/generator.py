"""자연어 요구 → 워크플로 계획.

LLM 은 템플릿 목록에서 고르고 파라미터만 채운다. n8n 노드 구조는 만들지 않는다.
계획이 스키마에 맞지 않으면 무엇이 틀렸는지 알려 주고 다시 요청한다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from n8n_gen.nodes import catalog_text, template_ids  # noqa: E402
from n8n_gen.schema import Plan  # noqa: E402
from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import ask as default_ask  # noqa: E402

__all__ = ["PlanGenerator", "BASE_DIR"]

BASE_DIR = Path(__file__).resolve().parents[1]
PROMPTS_DIR = BASE_DIR / "prompts"

MAX_RETRIES = 2


class PlanGenerator:
    """자연어 요구에서 워크플로 계획을 만든다.

    Args:
        model: Claude 모델 ID.
        ask_fn: LLM 호출 함수. 테스트·모의 실행에서 교체한다.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        ask_fn: Callable[..., Any] = default_ask,
    ) -> None:
        self.model = model
        self.ask_fn = ask_fn
        self.rules = (PROMPTS_DIR / "plan.md").read_text(encoding="utf-8")
        self.attempts = 0

    def _system(self) -> str:
        return (
            f"{self.rules}\n\n---\n\n"
            f"# 쓸 수 있는 노드 템플릿\n\n{catalog_text()}\n\n"
            f"이 목록에 있는 `id` 만 `template` 에 씁니다. "
            f"목록: {', '.join(template_ids())}"
        )

    def build(self, request: str) -> Plan:
        """요구 한 줄로 계획을 만든다.

        스키마 검증에 실패하면 오류 내용을 붙여 최대 2회 다시 요청한다.

        Raises:
            ValueError: 재시도 후에도 계획이 스키마에 맞지 않을 때.
        """
        instruction = (
            f"[요구]\n{request}\n\n"
            "이 요구를 n8n 워크플로 계획으로 옮기세요.\n"
            "- 트리거는 정확히 1개\n"
            "- 모든 단계가 연결되어야 합니다 (고아 노드 금지)\n"
            "- 템플릿에 없는 서비스는 http-request 로 대체하고 unsupported 에 적으세요"
        )
        user = instruction
        last_error = ""

        for attempt in range(1, MAX_RETRIES + 2):
            self.attempts = attempt
            data = self.ask_fn(self._system(), user, model=self.model, json_mode=True)
            try:
                return Plan(**data)
            except ValidationError as exc:
                last_error = "\n".join(
                    f"- {'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                    for e in exc.errors()[:8]
                )
                user = (
                    f"{instruction}\n\n[재작성 요청] 계획 형식이 맞지 않습니다.\n"
                    f"{last_error}\n"
                    "이 부분을 고쳐 처음부터 다시 만드세요."
                )

        raise ValueError(
            f"계획을 {MAX_RETRIES + 1}회 만들었지만 형식이 맞지 않습니다.\n{last_error}"
        )
