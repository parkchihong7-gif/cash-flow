"""카카오 i 오픈빌더 스킬 서버.

    POST /skill    오픈빌더가 부르는 곳
    GET  /health   살아 있는지, 시트를 언제 읽었는지
    POST /reload   시트를 지금 다시 읽는다 (5분 안 기다리고)

지켜야 하는 것 — **5초**
    오픈빌더는 5초 안에 답을 못 받으면 끊는다. 끊기면 고객에게는
    "오류가 발생했습니다" 만 보인다. 그래서 이 서버는 **어떤 일이 있어도
    시간 안에 무언가를 돌려준다.**

        글자 맞추기   0초 (Claude 안 부름)
        Claude 매칭   남은 시간까지만 기다린다
        시간 초과     "잠시 후 다시 문의" 로 넘긴다

    기다리다 못 받으면 **버린다.** 늦게 온 답은 쓸 데가 없다.

답을 만드는 순서
    ① 시트 FAQ 와 맞춰 본다 (글자 → 뜻)
    ② 맞으면 **시트 답을 그대로** 낸다. 고객이 검수한 문장이라 고치지 않는다
    ③ 안 맞으면 시트 전체를 근거로 Claude 가 답하되 "담당자 확인 필요" 를 붙인다
    ④ 끝에 AI 응답 표시를 붙인다 (AI_LABEL=true, 인공지능기본법 §31)
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parents[2]))

from faq_source import CACHE_SECONDS, FaqBook, load_from_csv, load_from_sheet  # noqa: E402
from logs import LogStore                                                      # noqa: E402
from matcher import literal_match, match                                       # noqa: E402

__all__ = ["create_app", "skill_response", "BUDGET_SECONDS", "FALLBACK_TEXT"]

#: Claude 호출에 줄 수 있는 최대 시간(초). 카카오 5초 중 1초는 네트워크 몫으로 둔다.
BUDGET_SECONDS = float(os.getenv("CLAUDE_TIMEOUT_SECONDS", "4.0"))

#: 시간 안에 못 만들었을 때 내보내는 말.
FALLBACK_TEXT = (
    "지금은 답변을 준비하지 못했습니다. 잠시 후 다시 문의해 주세요.\n"
    "급하시면 영업시간에 상담원 연결을 눌러 주세요."
)

#: 시트에 없는 것을 Claude 가 답할 때 반드시 붙이는 꼬리.
UNSURE_TAIL = "\n\n※ 정확한 내용은 담당자 확인이 필요합니다."

#: AI 응답 표시. 인공지능기본법 제31조에 따라 기본 켬이다.
AI_LABEL_TEXT = os.getenv("AI_LABEL_TEXT", "🤖 AI 자동 응답입니다.")

ANSWER_SYSTEM = """당신은 이 가게(회사)의 고객센터 상담원이다.

아래 FAQ 가 **네가 아는 전부**다. 여기 없는 것은 모르는 것이다.

규칙
  - FAQ 에 있는 내용만으로 답한다. 없는 사실을 지어내지 않는다
  - 가격·기간·환불 조건을 **추측하지 않는다.** 모르면 모른다고 한다
  - 3문장 안으로 짧게, 존댓말로 답한다
  - 인사말과 사과를 길게 늘어놓지 않는다

FAQ 로 답할 수 없으면 이렇게만 답한다.
  "문의하신 내용은 제가 확인하기 어렵습니다. 담당자에게 연결해 드리겠습니다."
"""


def skill_response(text: str) -> dict[str, Any]:
    """오픈빌더 스킬 응답 규격(2.0)으로 감싼다."""
    return {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]},
    }


def _utterance(payload: dict) -> str:
    request = payload.get("userRequest") or {}
    return str(request.get("utterance") or "").strip()


def _user_id(payload: dict) -> str:
    request = payload.get("userRequest") or {}
    user = request.get("user") or {}
    return str(user.get("id") or "")


def _default_book() -> FaqBook:
    """환경에 맞는 FAQ 원본을 고른다.

    시트 아이디가 있으면 시트를, 없으면 CSV 를 읽는다. CSV 는 시연·개발용이고
    고객 납품에서는 시트를 쓴다.
    """
    sheet_id = (os.getenv("SHEET_ID") or "").strip()
    csv_path = (os.getenv("FAQ_CSV") or "").strip() or str(BASE_DIR / "sample_faq.csv")

    if sheet_id:
        def loader():
            return load_from_sheet(sheet_id)
    else:
        def loader():
            return load_from_csv(csv_path)

    return FaqBook(loader=loader, cache_seconds=CACHE_SECONDS)


def create_app(book: FaqBook | None = None, ask_fn=None, store: LogStore | None = None,
               model: str = "", budget: float = BUDGET_SECONDS,
               ai_label: bool | None = None) -> FastAPI:
    """스킬 서버를 만든다.

    Args:
        book: FAQ 원본. 비우면 환경변수를 보고 정한다.
        ask_fn: Claude 호출 함수. 테스트에서는 가짜를 끼운다.
        store: 대화 기록 저장소.
        model: 쓸 모델. 비우면 공통 기본값.
        budget: 답을 만드는 데 쓸 수 있는 최대 시간(초).
        ai_label: AI 응답 표시. 비우면 환경변수 `AI_LABEL`(기본 켬).
    """
    app = FastAPI(title="카카오 FAQ 챗봇", docs_url=None, redoc_url=None)

    app.state.book = book or _default_book()
    app.state.store = store or LogStore()
    app.state.budget = float(budget)
    app.state.pool = ThreadPoolExecutor(max_workers=4)
    app.state.started_at = time.time()

    if ai_label is None:
        ai_label = (os.getenv("AI_LABEL", "true").strip().lower()
                    not in {"0", "false", "no", "off"})
    app.state.ai_label = bool(ai_label)

    if ask_fn is None:
        from shared.llm import ask as _ask

        app.state.ask = _ask
    else:
        app.state.ask = ask_fn

    if not model:
        from shared.config import DEFAULT_MODEL

        model = DEFAULT_MODEL
    app.state.model = model

    def _label(text: str) -> str:
        if not app.state.ai_label or AI_LABEL_TEXT in text:
            return text
        return f"{text}\n\n{AI_LABEL_TEXT}"

    def _answer(question: str, deadline: float) -> tuple[str, int | None, str]:
        """답 · 맞은 FAQ 번호(1부터) · 출처를 돌려준다."""
        faqs = app.state.book.get()

        # ① 글자로 먼저. 공짜이고 즉시 끝난다.
        index = literal_match(question, faqs)
        if index is not None:
            return faqs[index].answer, index + 1, "sheet"

        left = deadline - time.monotonic()
        if left <= 0.2:
            raise TimeoutError("글자 맞추기까지 하고 시간이 다 됐습니다")

        # ② 뜻으로. 남은 시간만큼만 기다린다.
        future = app.state.pool.submit(match, question, faqs, app.state.ask, app.state.model)
        try:
            index = future.result(timeout=left)
        except FutureTimeout:
            future.cancel()
            raise TimeoutError("FAQ 매칭이 제 시간에 끝나지 않았습니다")

        if index is not None:
            return faqs[index].answer, index + 1, "sheet"

        # ③ 시트에 없다. 시트를 근거로 짧게 답하되 담당자 확인을 붙인다.
        left = deadline - time.monotonic()
        if left <= 0.2:
            raise TimeoutError("답을 지을 시간이 남지 않았습니다")

        listing = "\n".join(f"- {faq.question} → {faq.answer}" for faq in faqs[:60])
        user = f"[FAQ]\n{listing}\n\n[고객 질문]\n{question}"
        future = app.state.pool.submit(
            app.state.ask, ANSWER_SYSTEM, user, model=app.state.model)
        try:
            text = future.result(timeout=left)
        except FutureTimeout:
            future.cancel()
            raise TimeoutError("답변 생성이 제 시간에 끝나지 않았습니다")

        text = str(text).strip() or FALLBACK_TEXT
        return text + UNSURE_TAIL, None, "claude"

    @app.post("/skill")
    async def skill(request: Request):
        started = time.monotonic()
        deadline = started + app.state.budget

        try:
            payload = await request.json()
        except Exception:
            payload = {}

        question = _utterance(payload)
        user_id = _user_id(payload)

        if not question:
            # 빈 발화도 규격에 맞는 응답으로 돌려준다. 500 을 내면 고객 화면에
            # '오류가 발생했습니다' 가 뜬다.
            return JSONResponse(skill_response(
                "무엇이 궁금하신지 한 줄로 적어 주시겠어요?"))

        try:
            text, matched, source = _answer(question, deadline)
            text = _label(text)
        except TimeoutError:
            text, matched, source = FALLBACK_TEXT, None, "fallback"
        except Exception as exc:                       # 어떤 일이 있어도 규격대로 답한다
            text, matched, source = FALLBACK_TEXT, None, "fallback"
            print(f"[skill] 예상 못 한 오류: {type(exc).__name__}: {exc}", flush=True)

        elapsed_ms = int((time.monotonic() - started) * 1000)
        try:
            app.state.store.add(user_id=user_id, question=question, answer=text,
                                matched=matched, elapsed_ms=elapsed_ms, source=source)
        except Exception as exc:                       # 기록 실패로 답을 막지 않는다
            print(f"[skill] 기록 실패: {type(exc).__name__}: {exc}", flush=True)

        return JSONResponse(skill_response(text))

    @app.get("/health")
    def health():
        book: FaqBook = app.state.book
        try:
            count = len(book.get())
            ok = True
        except Exception as exc:
            count, ok = 0, False
            book.last_error = f"{type(exc).__name__}: {exc}"
        return {
            "status": "ok" if ok else "degraded",
            "faq_count": count,
            "faq_age_seconds": round(book.age_seconds, 1),
            "cache_seconds": book.cache_seconds,
            "last_error": book.last_error,
            "ai_label": app.state.ai_label,
            "budget_seconds": app.state.budget,
            "uptime_seconds": round(time.time() - app.state.started_at, 1),
        }

    @app.post("/reload")
    def reload_faq():
        """시트를 지금 다시 읽는다. 고객이 '방금 고쳤는데요' 할 때 쓴다."""
        app.state.book.invalidate()
        return {"status": "ok", "faq_count": len(app.state.book.get())}

    return app


app_instance: FastAPI | None = None


def get_app() -> FastAPI:
    """uvicorn 이 부르는 곳. `uvicorn app:get_app --factory`"""
    global app_instance
    if app_instance is None:
        app_instance = create_app()
    return app_instance


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(get_app(), host=os.getenv("HOST", "0.0.0.0"),
                port=int(os.getenv("PORT", "8080")))
