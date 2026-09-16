"""n8n REST API 로 워크플로 생성.

`N8N_URL` 과 `N8N_API_KEY` 가 있을 때만 쓴다. 없으면 무엇을 설정해야 하는지 알려 준다.
API 키는 n8n 화면의 Settings → n8n API 에서 만든다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests

__all__ = ["push_workflow", "PushResult", "N8nNotConfigured", "n8n_config"]

#: n8n REST API 는 이 헤더로 인증한다.
API_KEY_HEADER = "X-N8N-API-KEY"

#: 생성 요청에 보낼 수 있는 키. n8n 이 모르는 키를 보내면 400 을 낸다.
ALLOWED_KEYS = ("name", "nodes", "connections", "settings")

TIMEOUT_SECONDS = 20


class N8nNotConfigured(RuntimeError):
    """N8N_URL 이나 N8N_API_KEY 가 없을 때."""


@dataclass
class PushResult:
    """생성 결과."""

    workflow_id: str
    name: str
    url: str


def n8n_config() -> tuple[str, str]:
    """환경 변수를 읽는다.

    Raises:
        N8nNotConfigured: 둘 중 하나라도 없을 때.
    """
    base_url = (os.getenv("N8N_URL") or "").strip().rstrip("/")
    api_key = (os.getenv("N8N_API_KEY") or "").strip()

    missing = [
        name for name, value in (("N8N_URL", base_url), ("N8N_API_KEY", api_key))
        if not value
    ]
    if missing:
        raise N8nNotConfigured(
            f"{', '.join(missing)} 가 설정되지 않아 --push 를 쓸 수 없습니다.\n"
            "  N8N_URL      n8n 주소 (예: http://localhost:5678)\n"
            "  N8N_API_KEY  n8n 화면 Settings → n8n API 에서 만든 키\n"
            ".env 에 넣거나 명령 앞에 붙여 실행하세요."
        )
    return base_url, api_key


def push_workflow(workflow: dict[str, Any]) -> PushResult:
    """워크플로를 n8n 에 만든다. 활성화는 하지 않는다.

    Raises:
        N8nNotConfigured: 환경 변수가 없을 때.
        RuntimeError: n8n 이 거절하거나 연결에 실패했을 때.
    """
    base_url, api_key = n8n_config()

    # n8n 이 모르는 키(active, meta, tags 등)를 보내면 400 을 낸다
    payload = {key: workflow[key] for key in ALLOWED_KEYS if key in workflow}
    payload.setdefault("settings", {"executionOrder": "v1"})

    try:
        response = requests.post(
            f"{base_url}/api/v1/workflows",
            headers={API_KEY_HEADER: api_key, "Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=TIMEOUT_SECONDS,
        )
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"n8n({base_url})에 연결하지 못했습니다. 켜져 있는지 확인하세요.\n{exc}"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(f"n8n 응답이 {TIMEOUT_SECONDS}초 안에 오지 않았습니다.") from exc

    if response.status_code == 401:
        raise RuntimeError("n8n API 키가 올바르지 않습니다 (401). 키를 다시 확인하세요.")
    if response.status_code >= 400:
        raise RuntimeError(
            f"n8n 이 워크플로를 거절했습니다 ({response.status_code}).\n"
            f"{response.text[:500]}"
        )

    body = response.json()
    workflow_id = str(body.get("id", ""))
    return PushResult(
        workflow_id=workflow_id,
        name=str(body.get("name", payload.get("name", ""))),
        url=f"{base_url}/workflow/{workflow_id}" if workflow_id else base_url,
    )
