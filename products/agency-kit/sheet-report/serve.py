"""보고서를 HTTP 로 부를 수 있게 하는 얇은 서버.

    uvicorn serve:app --host 0.0.0.0 --port 8090
    curl -X POST localhost:8090/run -H 'Content-Type: application/json' \
         -d '{"period":"week","dry_run":true}'

왜 필요한가
    n8n 이 매주 월요일 아침에 보고서를 만들게 하려면 **부를 수 있는 주소**가
    있어야 한다(`workflow.json` 의 HTTP Request 노드). 터미널 명령은 n8n 이
    직접 부르기 어렵다.

무엇을 돌려주나
    보고서 본문 전체와 파일 경로. n8n 은 이 본문을 그대로 슬랙에 올린다.

열어 둘 때
    이 서버는 **인증이 없다.** 같은 기계나 같은 사설망 안에서만 쓰고,
    바깥에 열어야 하면 앞에 프록시를 두고 토큰을 받으세요.
    설치 가이드 4장에 적어 두었습니다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parents[2]))

from aggregate import PERIODS, load_csv, load_sheet, summarize      # noqa: E402
from narrate import narrate                                        # noqa: E402
from run import _fake_narration                                    # noqa: E402
from writers import report_markdown, write_all                     # noqa: E402

app = FastAPI(title="주간 보고서", docs_url=None, redoc_url=None)


class RunRequest(BaseModel):
    """n8n 이 보내는 것."""

    sheet: str = Field(default="", description="구글시트 ID. 비우면 CSV")
    cell_range: str = Field(default="매출!A:F", alias="range")
    csv: str = Field(default="", description="시트 대신 읽을 CSV")
    period: str = Field(default="week")
    title: str = ""
    dry_run: bool = False

    model_config = {"populate_by_name": True}


@app.get("/health")
def health():
    return {"status": "ok", "periods": sorted(PERIODS)}


@app.post("/run")
def run(request: RunRequest):
    """보고서를 만들고 본문을 돌려준다."""
    if request.period not in PERIODS:
        return {"ok": False, "error": f"기간은 {' / '.join(sorted(PERIODS))} 중 하나입니다"}

    try:
        if request.sheet:
            source = f"구글시트 {request.sheet[:8]}… / {request.cell_range}"
            frame = load_sheet(request.sheet, request.cell_range)
        else:
            path = Path(request.csv or BASE_DIR / "sample_sales.csv")
            source = f"CSV {path.name}"
            frame = load_csv(path)

        aggregate = summarize(frame, period=request.period)
    except Exception as exc:
        # n8n 이 실패를 알아볼 수 있게 200 이 아니라 ok=false 로 준다.
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if request.dry_run or not os.getenv("ANTHROPIC_API_KEY"):
        narration = _fake_narration(aggregate)
        used_claude = False
    else:
        from shared.config import DEFAULT_MODEL
        from shared.llm import ask

        narration = narrate(aggregate, ask, DEFAULT_MODEL)
        used_claude = True

    text = report_markdown(aggregate, narration, title=request.title, source=source)
    md_path, docx_path = write_all(aggregate, narration, BASE_DIR / "outputs",
                                   title=request.title, source=source)

    return {
        "ok": True,
        "period": aggregate.period,
        "start": aggregate.start,
        "end": aggregate.end,
        "total": aggregate.total,
        "delta": aggregate.delta,
        "delta_ratio": aggregate.delta_ratio,
        "verified": narration.verified,
        "used_claude": used_claude,
        "warnings": list(aggregate.notes) + list(narration.warnings),
        "summary": f"[{aggregate.start} ~ {aggregate.end}] 매출 {aggregate.total:,}원"
                   f" ({aggregate.delta:+,}원, {aggregate.delta_ratio:+.1f}%)",
        "report": text,
        "files": {"markdown": str(md_path), "docx": str(docx_path)},
    }
