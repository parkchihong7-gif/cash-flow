"""프로젝트 공통 기반 모듈.

- config       : .env 로드, 경로 상수
- llm          : Claude API 호출 래퍼
- ai_label     : AI 생성물 표시 (인공지능기본법 제31조 대응)
- banned_phrases : 판매용 텍스트 금지 문구 검사
"""

from shared import ai_label, banned_phrases, config, llm

__all__ = ["ai_label", "banned_phrases", "config", "llm"]
