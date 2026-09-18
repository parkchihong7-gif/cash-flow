"""11번 전용 웹 화면 — **세 모듈이 각각 어디까지 준비됐나.**

이 상품은 납품용이라 화면이 봐야 하는 것이 다르다. 내가 돌려 보는 것보다
**고객 계정 쪽 준비가 어디까지 됐는지**가 중요하다. 카카오 오픈빌더와 인스타
권한 검수는 심사가 있어서, 코드가 다 돼도 못 판다.

그래서 화면 맨 위가 '심사 대기' 다.
"""

from __future__ import annotations

import os
from pathlib import Path

from core.webui import Field, Note, Panel, Table, WebUI

BASE_DIR = Path(__file__).resolve().parent

MODULES = (
    ("kakao-faq-bot", "A. 카카오톡 FAQ 챗봇",
     "문의 응대. 오픈빌더 스킬 서버로 붙습니다",
     ("ANTHROPIC_API_KEY", "GOOGLE_CREDENTIALS_JSON"),
     "카카오 i 오픈빌더 심사"),
    ("sheet-report", "B. 주간 보고서",
     "구글시트를 읽어 월요일 아침에 보냅니다",
     ("GOOGLE_CREDENTIALS_JSON",),
     ""),
    ("insta-scheduler", "C. 인스타 예약 게시",
     "사람이 승인한 캡션만 큐에 들어갑니다",
     ("IG_ACCESS_TOKEN", "IG_USER_ID"),
     "인스타 권한 검수"),
)

DELIVERABLES = (
    ("INSTALL_GUIDE.md", "설치 가이드"),
    ("RETAINER_CONTRACT_TEMPLATE.md", "리테이너 계약서 템플릿"),
    ("HANDOVER_CHECKLIST.md", "인수인계 체크리스트 (20항목)"),
    ("KMONG_LISTING.md", "크몽 상세페이지"),
    ("AI_NOTICE.md", "AI 생성물 고지"),
)


def _module_table() -> Table:
    rows, tones = [], []
    for folder, title, what, keys, review in MODULES:
        missing = [key for key in keys if not (os.getenv(key) or "").strip()]
        if review:
            state, tone = f"⚠ {review} 먼저", "warn"
        elif missing:
            state, tone = f"키 {len(missing)}개 필요", ""
        else:
            state, tone = "준비됨", "ok"
        rows.append([title, what, ", ".join(keys), state])
        tones.append(tone)
    return Table(headers=["모듈", "하는 일", "필요한 키", "지금"],
                 rows=rows, tones=tones)


def _deliverable_table() -> Table:
    rows, tones = [], []
    for name, label in DELIVERABLES:
        path = BASE_DIR / "deliverables" / name
        exists = path.is_file()
        rows.append([label, f"`deliverables/{name}`",
                     f"{path.stat().st_size:,}B" if exists else "없음"])
        tones.append("" if exists else "bad")
    return Table(headers=["문서", "어디에", "크기"], rows=rows, numeric=[2])


def build(program, ctx) -> WebUI:
    review_notes = [
        Note("카카오 i 오픈빌더 — 심사 필요",
             "채널 개설 후 신청합니다. **코드가 다 돼도 이게 안 나면 못 팝니다.**",
             tone="warn"),
        Note("인스타그램 권한 검수 — 심사 필요",
             "비즈니스 계정 + 페이스북 앱 검수. 개인 계정으로는 안 됩니다.",
             tone="warn"),
        Note("계약 전에 고객과 이 화면을 같이 보세요",
             "기다려야 한다는 걸 미리 알면 불만이 안 생깁니다.", tone=""),
    ]

    admin = [
        Panel(key="review", title="먼저 신청해야 하는 것", notes=review_notes),
        Panel(key="modules", title="모듈 세 개", table=_module_table(),
              lines=["카카오 스킬은 **5초 안에** 답해야 합니다. Claude 를 4초에서 끊습니다",
                     "인스타 게시는 계정당 24시간에 25건까지입니다",
                     "인스타 토큰은 **60일마다** 갱신해야 합니다. 안 하면 조용히 멈춥니다"]),
        Panel(key="deliverables", title="납품 문서", table=_deliverable_table(),
              note="고객에게 넘기는 문서입니다. 인수인계 체크리스트를 꼭 같이 주세요."),
        Panel(key="run", title="세 모듈 한 번에 돌려 보기",
              intro="**모의 실행이라 외부 API 를 부르지 않습니다.** "
                    "대행 상담에서 그대로 보여 주는 화면입니다.",
              action="run", action_label="모의 실행", run_mode="dry"),
        Panel(key="package", title="납품 꾸러미 만들기",
              intro="플랜을 고르면 그 구성으로 문서를 채웁니다.",
              fields=[Field("plan", "플랜", "select", default="basic",
                            options=["basic", "standard", "premium"]),
                      Field("client", "고객 상호", "text", placeholder="OO상사")],
              action="do:package", action_label="꾸러미 만들기"),
        Panel(key="never", title="넣지 않은 기능",
              lines=["팔로우·좋아요·콜드 DM — Meta 정책 위반, 계정 정지",
                     "사람 승인 없는 게시 — 캡션은 승인해야 큐에 들어갑니다",
                     "문의 원문 저장 — 로그에 개인정보를 남기지 않습니다"],
              notes=[Note("이 키트는 반복 업무 자동화 도구이며 매출을 보장하지 않습니다",
                          "", tone="warn")]),
    ]

    client = [
        Panel(key="modules", title="받으신 것", table=_module_table()),
        Panel(key="run", title="한 번 돌려 보기",
              action="run", action_label="돌려 보기", run_mode="dry"),
        Panel(key="never", title="일부러 넣지 않은 것",
              lines=["팔로우·좋아요·콜드 DM은 하지 않습니다. 계정이 정지됩니다",
                     "게시물은 **사람이 승인한 것만** 올라갑니다"]),
    ]

    return WebUI(
        program_id=program.id, title=program.name,
        admin=admin, client=client,
        admin_intro="세 모듈과 납품 문서의 준비 상태입니다. "
                    "**심사가 걸린 것부터** 보세요.",
        client_intro="문의 응대·주간 보고·예약 게시에 드는 시간을 줄입니다. "
                     "매출을 보장하지 않습니다.")


def handle(program, ctx, action: str, form: dict) -> str:
    if action != "package":
        return "error=모르는 동작입니다"
    plan = (form.get("plan") or "basic").strip()
    client = (form.get("client") or "").strip()
    if not client:
        return "error=고객 상호를 적어 주세요. 계약서에 들어갑니다"
    if plan not in ("basic", "standard", "premium"):
        return "error=플랜은 basic / standard / premium 중 하나입니다"
    return (f"saved={client} · {plan} 플랜으로 꾸러미를 만들려면 "
            f"'모의 실행' 대신 터미널에서 `python cli.py package --plan {plan} "
            f"--client \"{client}\"` 를 쓰세요")
