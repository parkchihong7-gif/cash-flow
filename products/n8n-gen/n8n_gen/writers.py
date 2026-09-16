"""산출물 4종 쓰기.

    workflow.json      n8n import 가능
    plan.md            노드 순서·역할·credential·파라미터 표
    setup_guide.md     고객 납품용 설치 가이드
    test_payload.json  웹훅 트리거일 때 테스트용 샘플
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from n8n_gen.assembler import AssembledWorkflow  # noqa: E402
from n8n_gen.schema import Plan  # noqa: E402
from n8n_gen.validator import ValidationResult  # noqa: E402
from shared.ai_label import add_text_label  # noqa: E402

__all__ = ["write_outputs", "CREDENTIAL_GUIDE"]

#: credential 종류별 발급 안내. 설치 가이드에 그대로 들어간다.
CREDENTIAL_GUIDE = {
    "googleSheetsOAuth2Api": (
        "Google Sheets", "구글 클라우드 콘솔에서 OAuth 클라이언트를 만들고 "
        "n8n 의 Credentials → Google Sheets OAuth2 API 에서 연결합니다. "
        "시트에 해당 계정의 편집 권한이 있어야 합니다."),
    "gmailOAuth2": (
        "Gmail", "구글 클라우드 콘솔에서 Gmail API 를 켜고 OAuth 클라이언트를 만든 뒤 "
        "n8n 의 Credentials → Gmail OAuth2 에서 연결합니다."),
    "slackApi": (
        "Slack", "api.slack.com 에서 앱을 만들고 Bot Token(xoxb-)을 발급받습니다. "
        "chat:write 권한이 필요하고, 봇을 해당 채널에 초대해야 합니다."),
    "telegramApi": (
        "Telegram", "@BotFather 에게 /newbot 으로 봇을 만들고 받은 토큰을 넣습니다. "
        "봇과 한 번 대화를 시작해야 메시지를 보낼 수 있습니다."),
    "notionApi": (
        "Notion", "notion.so/my-integrations 에서 통합을 만들고 Internal Token 을 받습니다. "
        "대상 데이터베이스 페이지에서 해당 통합을 '연결'해야 접근됩니다."),
    "httpHeaderAuth": (
        "Anthropic API (헤더 인증)",
        "n8n 의 Credentials → Header Auth 를 만들고 "
        "Name 에 `x-api-key`, Value 에 Anthropic 콘솔에서 발급한 키를 넣습니다."),
}


def _credential_rows(workflow: AssembledWorkflow) -> list[tuple[str, str, str]]:
    rows = []
    for credential in workflow.credentials:
        label, guide = CREDENTIAL_GUIDE.get(credential, (credential, "발급 방법을 확인하세요."))
        rows.append((credential, label, guide))
    return rows


def write_workflow(workflow: AssembledWorkflow, out_dir: Path) -> Path:
    path = out_dir / "workflow.json"
    path.write_text(
        json.dumps(workflow.workflow, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def write_plan(plan: Plan, workflow: AssembledWorkflow, result: ValidationResult,
               out_dir: Path, request: str, model: str,
               generated_at: datetime, ai_label: bool = True) -> Path:
    """plan.md — 노드 순서·역할·credential·파라미터 표."""
    lines = [
        f"# {plan.workflow_name}",
        "",
        f"> {plan.summary}" if plan.summary else "",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 원래 요구 | {request} |",
        f"| 노드 수 | {len(workflow.placements)}개 |",
        f"| 생성 시각 | {generated_at.strftime('%Y-%m-%d %H:%M:%S %z')} |",
        f"| 모델 | {model} |",
        f"| 검증 | {'통과' if result.ok else '실패'} |",
        "",
        "## 노드 순서와 역할",
        "",
        "| # | 노드 이름 | 템플릿 | 역할 |",
        "|---|---|---|---|",
    ]
    for index, placement in enumerate(workflow.placements, start=1):
        step = plan.step(placement.step_id)
        note = (step.note if step else "") or placement.template.description
        lines.append(
            f"| {index} | {placement.name} | `{placement.template.id}` | {note} |"
        )

    lines += ["", "## 연결", ""]
    if plan.connections:
        lines += ["| 출발 | 도착 | 비고 |", "|---|---|---|"]
        for connection in plan.connections:
            source = workflow.placement(connection.from_)
            target = workflow.placement(connection.to)
            note = ""
            if connection.from_output == 1:
                note = "조건이 거짓일 때"
            elif connection.to_input == 1:
                note = "두 번째 입력으로"
            lines.append(
                f"| {source.name if source else connection.from_} | "
                f"{target.name if target else connection.to} | {note} |"
            )
    else:
        lines.append("연결이 없습니다. 노드가 하나뿐인 워크플로입니다.")

    lines += ["", "## 필요한 credential", ""]
    rows = _credential_rows(workflow)
    if rows:
        lines += ["| 종류 | 서비스 | 발급 방법 |", "|---|---|---|"]
        for credential, label, guide in rows:
            lines.append(f"| `{credential}` | {label} | {guide} |")
        lines += [
            "",
            "> workflow.json 에는 **키를 넣지 않았습니다.** 연결할 자리만 만들어 두었으니 "
            "n8n 화면에서 직접 연결하세요. 키가 든 파일을 주고받으면 안 됩니다.",
        ]
    else:
        lines.append("필요한 credential 이 없습니다.")

    lines += ["", "## 노드별 파라미터", ""]
    for placement in workflow.placements:
        lines += [f"### {placement.name} (`{placement.template.id}`)", ""]
        if not placement.params:
            lines += ["파라미터가 없습니다.", ""]
            continue
        lines += ["| 항목 | 값 |", "|---|---|"]
        for key, value in placement.params.items():
            label = placement.template.param_label(key)
            shown = str(value).replace("|", "\\|").replace("\n", " ")
            if len(shown) > 120:
                shown = shown[:120] + "…"
            lines.append(f"| {label} (`{key}`) | `{shown}` |")
        lines.append("")

    if workflow.unsupported:
        lines += [
            "## ⚠️ 지원하지 않아 대체한 항목",
            "",
            "아래는 전용 노드가 없어 **HTTP Request 로 대체**했습니다. "
            "사람이 직접 설정해야 동작합니다.",
            "",
        ]
        for item in workflow.unsupported:
            lines += [
                f"### {item.want}",
                "",
                f"- 대체: `{item.fallback}`",
                f"- 직접 해야 할 일: {item.manual}",
                "",
            ]

    if workflow.notes:
        lines += ["## 조립 중 알림", ""]
        lines += [f"- {note}" for note in workflow.notes]
        lines.append("")

    lines += ["## 검증 결과", ""]
    if result.ok and not result.warnings:
        lines.append("✅ 구조 검증을 통과했습니다.")
    else:
        for issue in result.errors:
            lines.append(f"- ✗ **{issue.code}** {issue.message}")
        for issue in result.warnings:
            lines.append(f"- ! {issue.code}: {issue.message}")
    lines.append("")

    text = "\n".join(line for line in lines if line is not None)
    if ai_label:
        text = add_text_label(text) + "\n"

    path = out_dir / "plan.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_setup_guide(plan: Plan, workflow: AssembledWorkflow, out_dir: Path,
                      ai_label: bool = True) -> Path:
    """setup_guide.md — 고객에게 그대로 주는 설치 가이드."""
    has_webhook = any(
        p.template.id == "webhook-trigger" for p in workflow.placements
    )

    lines = [
        f"# 설치 가이드 — {plan.workflow_name}",
        "",
        f"{plan.summary}" if plan.summary else "",
        "",
        "이 문서대로 따라 하시면 자동화가 동작합니다. 순서대로 진행해 주세요.",
        "",
        "## 준비물",
        "",
        "- n8n 계정 (클라우드) 또는 직접 설치한 n8n",
        "- 아래 4단계에 나오는 서비스 계정",
        "- `workflow.json` 파일 (함께 드린 파일)",
        "",
        "---",
        "",
        "## 1단계. n8n 접속",
        "",
        "n8n 클라우드를 쓰신다면 로그인하세요.",
        "직접 설치하실 거면 컴퓨터에서 아래 한 줄을 실행하시면 됩니다.",
        "",
        "```bash",
        "docker run -it --rm -p 5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n",
        "```",
        "",
        "브라우저에서 `http://localhost:5678` 로 접속합니다.",
        "",
        "> 📷 **[스크린샷 자리]** n8n 첫 화면",
        "",
        "## 2단계. 워크플로 가져오기 (import)",
        "",
        "1. 왼쪽 위 **Workflows** 를 누릅니다",
        "2. 오른쪽 위 **Add workflow** 옆 `⋯` → **Import from File** 을 고릅니다",
        "3. 받으신 `workflow.json` 을 선택합니다",
        "",
        f"노드 {len(workflow.placements)}개가 화면에 나타나면 성공입니다.",
        "",
        "> 📷 **[스크린샷 자리]** Import from File 메뉴 위치",
        "",
        "> 📷 **[스크린샷 자리]** 가져오기 직후 노드가 배치된 화면",
        "",
        "## 3단계. 노드 확인",
        "",
        "가져온 노드는 이렇게 이어져 있습니다.",
        "",
    ]
    for index, placement in enumerate(workflow.placements, start=1):
        lines.append(f"{index}. **{placement.name}** — {placement.template.description}")
    lines += [
        "",
        "빨간 삼각형(⚠)이 뜬 노드가 있으면 4단계에서 연결하면 사라집니다.",
        "",
        "## 4단계. 계정 연결 (credential)",
        "",
    ]

    rows = _credential_rows(workflow)
    if rows:
        lines += [
            "각 노드를 더블클릭하면 위쪽에 **Credential to connect with** 칸이 있습니다.",
            "**Create new credential** 을 눌러 아래대로 연결하세요.",
            "",
        ]
        for credential, label, guide in rows:
            lines += [
                f"### {label}",
                "",
                guide,
                "",
                "> 📷 **[스크린샷 자리]** " + f"{label} 연결 화면",
                "",
            ]
    else:
        lines += ["이 워크플로는 별도 계정 연결이 필요 없습니다.", ""]

    lines += [
        "## 5단계. 값 채우기",
        "",
        "노드를 열어 **대괄호로 표시된 자리**를 실제 값으로 바꿔 주세요.",
        "",
        "| 노드 | 채울 항목 | 어떻게 찾나 |",
        "|---|---|---|",
    ]
    placeholder_found = False
    for placement in workflow.placements:
        for key, value in placement.params.items():
            if isinstance(value, str) and value.strip().startswith("["):
                placeholder_found = True
                hint = {
                    "document_id": "구글시트 주소의 /d/ 와 /edit 사이 긴 문자열",
                    "sheet_name": "시트 아래쪽 탭 이름",
                    "channel": "슬랙 채널 이름 (# 없이)",
                    "chat_id": "텔레그램 봇에게 메시지를 보낸 뒤 getUpdates 로 확인",
                    "database_id": "노션 데이터베이스 주소의 마지막 32자리",
                    "to": "받는 사람 메일 주소",
                    "url": "호출할 API 주소",
                }.get(key, "담당자에게 확인")
                lines.append(
                    f"| {placement.name} | {placement.template.param_label(key)} | {hint} |"
                )
    if not placeholder_found:
        lines.append("| — | 채울 항목이 없습니다 | — |")

    lines += [
        "",
        "> 📷 **[스크린샷 자리]** 값을 채운 노드 화면",
        "",
        "## 6단계. 테스트 실행",
        "",
    ]
    if has_webhook:
        lines += [
            "이 워크플로는 **웹훅**으로 시작합니다.",
            "",
            "1. 웹훅 노드를 열고 **Test URL** 을 복사합니다",
            "2. 오른쪽 위 **Test workflow** 를 누릅니다 (대기 상태가 됩니다)",
            "3. 함께 드린 `test_payload.json` 의 내용을 그 주소로 보냅니다",
            "",
            "터미널에서 보내는 방법:",
            "",
            "```bash",
            "curl -X POST '복사한_Test_URL' \\",
            "  -H 'Content-Type: application/json' \\",
            "  -d @test_payload.json",
            "```",
            "",
        ]
    else:
        lines += [
            "1. 오른쪽 위 **Test workflow** 를 누릅니다",
            "2. 트리거 노드부터 순서대로 실행됩니다",
            "",
            "정해진 시각을 기다리지 않고 바로 실행해 볼 수 있습니다.",
            "",
        ]
    lines += [
        "각 노드에 초록색 체크가 뜨면 성공입니다.",
        "빨간색이 뜨면 그 노드를 눌러 오류 메시지를 확인하세요.",
        "",
        "> 📷 **[스크린샷 자리]** 실행 성공 화면 (초록 체크)",
        "",
        "## 7단계. 활성화",
        "",
        "테스트가 성공하면 오른쪽 위 **Inactive** 스위치를 눌러 **Active** 로 바꿉니다.",
        "이때부터 자동으로 돌아갑니다.",
        "",
        "> 📷 **[스크린샷 자리]** Active 로 바뀐 상태",
        "",
        "---",
        "",
        "## 자주 생기는 문제",
        "",
        "| 증상 | 원인 | 해결 |",
        "|---|---|---|",
        "| 노드에 빨간 삼각형 | 계정 연결 안 됨 | 4단계를 다시 |",
        "| `401` 또는 `403` 오류 | 권한 부족 | 해당 서비스에서 접근 권한을 확인 |",
        "| 시트를 못 찾음 | ID 나 탭 이름이 다름 | 5단계의 값을 다시 확인 |",
        "| 슬랙 메시지가 안 감 | 봇이 채널에 없음 | 채널에서 봇을 초대 |",
        "| 실행은 되는데 내용이 비어 있음 | 앞 노드 출력 구조가 다름 | 실행 결과의 JSON 을 보고 표현식을 맞추세요 |",
        "",
        "## 운영 중 확인할 곳",
        "",
        "- 왼쪽 **Executions** 에서 실행 이력과 실패를 볼 수 있습니다",
        "- 실패한 실행을 눌러 어느 노드에서 멈췄는지 확인하세요",
        "",
    ]

    text = "\n".join(line for line in lines if line is not None)
    if ai_label:
        text = add_text_label(text) + "\n"

    path = out_dir / "setup_guide.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_test_payload(plan: Plan, workflow: AssembledWorkflow,
                       out_dir: Path) -> Path | None:
    """test_payload.json — 웹훅 트리거일 때만 만든다."""
    webhook = next(
        (p for p in workflow.placements if p.template.id == "webhook-trigger"), None
    )
    if webhook is None:
        return None

    payload = {
        "_설명": "웹훅 테스트용 샘플입니다. 실제 데이터 모양에 맞춰 고쳐 쓰세요.",
        "_보내는_법": "curl -X POST '<n8n Test URL>' -H 'Content-Type: application/json' "
                      "-d @test_payload.json",
        "_웹훅_경로": webhook.params.get("path", "incoming"),
        "_메서드": webhook.params.get("method", "POST"),
        "body": {
            "name": "홍길동",
            "email": "sample@example.com",
            "message": "테스트 문의입니다. 자동화가 동작하는지 확인합니다.",
            "priority": "normal",
            "created_at": "2026-01-01T09:00:00+09:00",
        },
    }
    path = out_dir / "test_payload.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def write_outputs(plan: Plan, workflow: AssembledWorkflow, result: ValidationResult,
                  out_root: Path, request: str, model: str,
                  generated_at: datetime, ai_label: bool = True) -> Path:
    """산출물을 `out_root/<slug>/` 에 쓰고 폴더 경로를 돌려준다."""
    out_dir = out_root / plan.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    write_workflow(workflow, out_dir)
    write_plan(plan, workflow, result, out_dir, request, model, generated_at, ai_label)
    write_setup_guide(plan, workflow, out_dir, ai_label)
    write_test_payload(plan, workflow, out_dir)
    return out_dir
