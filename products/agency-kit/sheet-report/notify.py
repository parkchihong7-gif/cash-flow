"""보내기 — 슬랙과 메일.

둘 다 **선택**이다. 안 보내도 파일은 남는다.

주소가 없으면 오류가 아니라 "안 보냈습니다" 로 끝낸다. 대행 초기에는 파일만
만들어 손으로 전달하는 경우가 대부분이고, 그것도 충분히 일이 된다.

슬랙은 들어오는 웹훅(Incoming Webhook)만 쓴다. 봇 토큰은 권한 범위가 넓어
고객 작업 공간에 들이기 부담스럽다. 웹훅은 그 채널 하나에만 글을 쓸 수 있다.
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path

__all__ = ["send_slack", "send_email", "SendResult", "TIMEOUT_SECONDS"]

TIMEOUT_SECONDS = 15

#: 슬랙 글자 수 한도. 넘으면 잘라 보내고 파일을 보라고 한다.
SLACK_LIMIT = 2800


class SendResult:
    """보낸 결과. 실패해도 예외를 던지지 않는다 — 보고서는 이미 만들어졌다."""

    def __init__(self, channel: str, sent: bool, detail: str = "") -> None:
        self.channel = channel
        self.sent = sent
        self.detail = detail

    def __str__(self) -> str:
        mark = "보냈습니다" if self.sent else "보내지 않았습니다"
        return f"{self.channel}: {mark}" + (f" — {self.detail}" if self.detail else "")


def send_slack(text: str, webhook: str = "", opener=None) -> SendResult:
    """슬랙 채널에 보고서 요약을 보낸다."""
    webhook = webhook or os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        return SendResult("슬랙", False, "SLACK_WEBHOOK_URL 이 없습니다 (선택 기능입니다)")

    body = text if len(text) <= SLACK_LIMIT else (
        text[:SLACK_LIMIT] + "\n\n…(줄여서 보냈습니다. 전체는 파일을 보세요)")
    payload = json.dumps({"text": body}).encode("utf-8")
    request = urllib.request.Request(
        webhook, data=payload, headers={"Content-Type": "application/json"})

    try:
        with (opener or urllib.request.urlopen)(request, timeout=TIMEOUT_SECONDS) as response:
            code = getattr(response, "status", 200)
        return SendResult("슬랙", True, f"HTTP {code}")
    except urllib.error.HTTPError as exc:
        return SendResult("슬랙", False, f"HTTP {exc.code} — 웹훅 주소를 확인하세요")
    except Exception as exc:
        return SendResult("슬랙", False, f"{type(exc).__name__}: {exc}")


def send_email(subject: str, text: str, attachments: list[Path] | None = None,
               to: str = "", sender=None) -> SendResult:
    """메일로 보낸다. 첨부(보고서 파일)도 함께.

    Gmail 을 쓰신다면 **앱 비밀번호**를 만들어 쓰세요. 계정 비밀번호는 안 됩니다.
    """
    to = to or os.getenv("REPORT_EMAIL_TO", "").strip()
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    port = int(os.getenv("SMTP_PORT", "587"))

    if not (to and host and user):
        return SendResult("메일", False,
                          "SMTP_HOST / SMTP_USER / REPORT_EMAIL_TO 가 없습니다 (선택 기능입니다)")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.getenv("SMTP_FROM", user)
    message["To"] = to
    message.set_content(text)

    for path in attachments or []:
        path = Path(path)
        if not path.is_file():
            continue
        data = path.read_bytes()
        subtype = ("vnd.openxmlformats-officedocument.wordprocessingml.document"
                   if path.suffix == ".docx" else "octet-stream")
        message.add_attachment(data, maintype="application", subtype=subtype,
                               filename=path.name)

    try:
        if sender is not None:                       # 테스트에서 갈아 끼운다
            sender(message)
            return SendResult("메일", True, f"{to} 로 보냈습니다")

        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=TIMEOUT_SECONDS) as server:
            server.starttls(context=context)
            server.login(user, password)
            server.send_message(message)
        return SendResult("메일", True, f"{to} 로 보냈습니다")
    except Exception as exc:
        return SendResult("메일", False, f"{type(exc).__name__}: {exc}")
