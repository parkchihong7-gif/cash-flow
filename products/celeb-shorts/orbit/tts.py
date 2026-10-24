"""AI 음성(선택) — Google Cloud Text-to-Speech 공식 REST API.

키(`GOOGLE_TTS_API_KEY`)가 없으면 음성 없이 자막만으로 만든다. 오류가 아니다.
무료 한도·요금은 Google 공식 요금표로 확인하세요(자료마다 숫자가 달라 여기 적지 않는다).
남의 목소리를 복제하는 기능은 없다 — Google 기본 음성만 쓴다.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import requests

from .db import WaitError

ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"
DEFAULT_VOICE = "ko-KR-Neural2-A"


def api_key() -> str:
    return os.getenv("GOOGLE_TTS_API_KEY", "").strip()


def available() -> bool:
    return bool(api_key())


def synthesize(text: str, out: Path, *, voice: str = "", rate: float = 1.1) -> Path:
    key = api_key()
    if not key:
        raise RuntimeError("GOOGLE_TTS_API_KEY 가 없습니다")
    body = {"input": {"text": text},
            "voice": {"languageCode": "ko-KR", "name": voice or os.getenv("GOOGLE_TTS_VOICE", DEFAULT_VOICE)},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": rate}}
    resp = requests.post(ENDPOINT, params={"key": key}, json=body, timeout=30)
    if resp.status_code == 429:
        raise WaitError("Google TTS 사용량 한도 초과 — 재시도하지 말고 기다리세요")
    if resp.status_code != 200:
        raise RuntimeError(f"Google TTS 오류 {resp.status_code}: {resp.text[:200]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(resp.json()["audioContent"]))
    return out
