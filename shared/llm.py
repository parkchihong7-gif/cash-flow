"""Claude API 호출 래퍼.

모든 상품 모듈은 anthropic SDK 를 직접 쓰지 말고 이 모듈의 :func:`ask` 를 쓴다.
모델·재시도·JSON 파싱 정책을 한 곳에서 바꾸기 위해서다.
"""

from __future__ import annotations

import json
import re
from typing import Any

import anthropic

from shared.config import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, require_api_key

__all__ = ["ask", "LLMError", "LLMJSONError", "get_client"]


class LLMError(RuntimeError):
    """Claude 호출이 실패했을 때."""


class LLMJSONError(LLMError):
    """json_mode 응답을 재시도 후에도 JSON 으로 파싱하지 못했을 때."""

    def __init__(self, message: str, raw: str) -> None:
        super().__init__(message)
        self.raw = raw


_client: anthropic.Anthropic | None = None

_JSON_SYSTEM_SUFFIX = (
    "\n\n출력 규칙: 유효한 JSON 하나만 출력한다. "
    "설명 문장, 인사말, 코드 펜스(```) 를 붙이지 않는다."
)

_JSON_RETRY_TEMPLATE = (
    "직전 응답을 JSON 으로 파싱하지 못했습니다.\n"
    "파싱 오류: {error}\n\n"
    "아래 내용을 같은 의미의 유효한 JSON 하나로만 다시 출력하세요. "
    "다른 문장이나 코드 펜스는 붙이지 마세요.\n\n"
    "--- 직전 응답 ---\n{raw}"
)

# ```json ... ``` 또는 ``` ... ``` 펜스를 벗겨낸다.
_FENCE_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*\n(?P<body>.*?)\n?\s*```\s*$",
    re.DOTALL,
)


def get_client() -> anthropic.Anthropic:
    """프로세스당 하나의 Anthropic 클라이언트를 재사용한다."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=require_api_key())
    return _client


def strip_json_fence(text: str) -> str:
    """응답에서 ```json 코드 펜스를 제거한다. 펜스가 없으면 그대로 돌려준다."""
    match = _FENCE_RE.match(text)
    return match.group("body").strip() if match else text.strip()


def _extract_text(message: anthropic.types.Message) -> str:
    """응답 블록 중 text 블록만 이어 붙인다 (thinking 등은 건너뛴다)."""
    return "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()


def _call(system: str, user: str, model: str, max_tokens: int) -> str:
    """단발 호출. SDK 예외를 LLMError 로 감싸 상위에서 한 종류만 잡게 한다."""
    try:
        message = get_client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.NotFoundError as exc:  # 404 — 대개 잘못된 모델 ID
        raise LLMError(f"모델을 찾을 수 없습니다: {model}") from exc
    except anthropic.RateLimitError as exc:  # 429 — SDK 가 이미 재시도한 뒤
        raise LLMError("Claude API 쿼터 초과. 재시도하지 말고 대기하세요.") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError(f"Claude API 오류 {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError("Claude API 에 연결하지 못했습니다.") from exc

    if message.stop_reason == "refusal":
        detail = getattr(message.stop_details, "explanation", None) or ""
        raise LLMError(f"Claude 가 요청을 거절했습니다. {detail}".strip())

    text = _extract_text(message)
    if message.stop_reason == "max_tokens":
        raise LLMError(
            f"응답이 max_tokens({max_tokens})에서 잘렸습니다. max_tokens 를 늘리세요."
        )
    if not text:
        raise LLMError("Claude 응답에 텍스트 블록이 없습니다.")
    return text


def ask(
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    json_mode: bool = False,
) -> Any:
    """Claude 에 한 번 묻고 답을 돌려준다.

    Args:
        system: 시스템 프롬프트 (역할·규칙).
        user: 사용자 메시지 (실제 요청).
        model: 모델 ID. 기본값은 `.env` 의 CLAUDE_MODEL 또는 CLAUDE.md §6 기준값.
        max_tokens: 응답 최대 토큰.
        json_mode: True 면 ```json 펜스를 제거하고 json.loads 로 파싱해 돌려준다.
            파싱에 실패하면 오류 내용을 붙여 1회만 다시 묻는다.

    Returns:
        json_mode=False 면 문자열, True 면 파싱된 dict/list 등.

    Raises:
        LLMError: API 호출 실패, 거절, 응답 잘림.
        LLMJSONError: 재시도 후에도 JSON 파싱에 실패 (``.raw`` 에 원문 보관).
    """
    system_prompt = system + _JSON_SYSTEM_SUFFIX if json_mode else system
    raw = _call(system_prompt, user, model, max_tokens)

    if not json_mode:
        return raw

    try:
        return json.loads(strip_json_fence(raw))
    except json.JSONDecodeError as first_error:
        retry_user = _JSON_RETRY_TEMPLATE.format(error=first_error, raw=raw)
        retried = _call(system_prompt, retry_user, model, max_tokens)
        try:
            return json.loads(strip_json_fence(retried))
        except json.JSONDecodeError as second_error:
            raise LLMJSONError(
                f"JSON 파싱에 2회 실패했습니다: {second_error}", raw=retried
            ) from second_error
