"""설계대로 노션에 실제로 만든다.

토큰이 없으면 **오류가 아니라 안내**하고 끝난다. 이 기능은 있으면 좋은 것이지
없으면 못 쓰는 것이 아니다. 손으로 만드는 길(`build_guide.md`)이 늘 있다.

[관계를 2단계로 나누는 이유]
관계 속성은 **이을 상대 데이터베이스가 이미 있어야** 만들 수 있다. 그런데
데이터베이스를 만들면서 동시에 관계를 넣으려면 아직 없는 id 가 필요하다.
그래서 이렇게 나눈다.

    1단계  관계·롤업을 뺀 나머지 속성으로 데이터베이스를 전부 만든다
    2단계  id 를 다 알게 됐으니 PATCH 로 관계를 붙인다
    3단계  관계가 생겼으니 롤업을 붙인다 (롤업은 관계를 타고 간다)
    4단계  예시 데이터를 넣는다

[어디까지 만들었는지 남기는 이유]
중간에 끊기면 노션에는 **절반쯤 만들어진 것**이 남는다. 무엇이 남았는지 모르면
지우지도 이어 만들지도 못한다. 그래서 한 단계가 끝날 때마다 기록하고,
실패해도 그때까지의 기록을 파일로 남긴다.

⚠️ 이 저장소를 만든 컨테이너는 api.notion.com 에 닿지 못해 **실제 호출로
   확인하지 못했습니다.** 요청 모양은 공개 문서를 근거로 적었습니다.
   처음 쓰실 때는 빈 페이지에 먼저 해 보세요.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

from notion_kit.notion_types import MANUAL_ONLY, SUBSTITUTE, why_manual
from notion_kit.schema import DatabaseSpec, PropertySpec, TemplateSpec

__all__ = ["NotionNotConfigured", "NotionError", "DeployReport", "Step",
           "notion_config", "deploy", "API_VERSION", "build_property_schema",
           "build_row_properties", "write_deploy_log"]

API_BASE = "https://api.notion.com/v1"

#: 노션 API 판 번호. 이 값을 안 보내면 요청이 거절된다.
API_VERSION = "2022-06-28"

#: 노션은 초당 3회쯤으로 제한한다. 넘으면 429 가 온다.
PAUSE_SECONDS = 0.34

#: 429 를 만났을 때 다시 해 보는 횟수.
MAX_RETRY = 3

#: number 속성의 표시 형식. 모르는 값이 오면 기본 number 로 둔다.
NUMBER_FORMATS = frozenset({
    "number", "number_with_commas", "percent", "won", "dollar", "euro", "yen",
    "yuan", "pound", "rupee", "real", "ruble", "franc",
})


class NotionNotConfigured(RuntimeError):
    """토큰이나 부모 페이지가 없을 때. 오류가 아니라 안내로 다룬다."""


class NotionError(RuntimeError):
    """노션이 요청을 거절했을 때."""


@dataclass
class Step:
    """한 단계의 결과. 실패해도 여기까지는 남는다."""

    kind: str
    name: str
    status: str            # ok | skipped | failed
    detail: str = ""
    notion_id: str = ""


@dataclass
class DeployReport:
    spec_name: str = ""
    parent_page_id: str = ""
    steps: list[Step] = field(default_factory=list)
    manual_todo: list[str] = field(default_factory=list)
    started_at: str = ""
    failed_at: str = ""

    def add(self, kind: str, name: str, status: str, detail: str = "",
            notion_id: str = "") -> Step:
        step = Step(kind, name, status, detail, notion_id)
        self.steps.append(step)
        return step

    @property
    def made(self) -> int:
        return sum(1 for step in self.steps if step.status == "ok")

    @property
    def failures(self) -> list[Step]:
        return [step for step in self.steps if step.status == "failed"]

    @property
    def ok(self) -> bool:
        return not self.failures


# ------------------------------------------------------------------ 설정 읽기
def notion_config() -> tuple[str, str]:
    """토큰과 부모 페이지 id. 없으면 무엇을 해야 하는지 알려 준다."""
    token = os.getenv("NOTION_TOKEN", "").strip()
    parent = os.getenv("NOTION_PARENT_PAGE_ID", "").strip()
    missing = [name for name, value in
               (("NOTION_TOKEN", token), ("NOTION_PARENT_PAGE_ID", parent))
               if not value]
    if missing:
        raise NotionNotConfigured(
            f"{', '.join(missing)} 가 없어 노션에 만들지 않았습니다.\n"
            "\n"
            "  이 기능은 없어도 됩니다. build_guide.md 를 보며 손으로 만드셔도\n"
            "  똑같은 결과가 나옵니다. 오히려 처음 한 번은 손으로 만들어 보시는 편이\n"
            "  구조를 이해하는 데 낫습니다.\n"
            "\n"
            "  자동으로 만들고 싶으시면 .env 에 두 줄을 넣으세요.\n"
            "\n"
            "    1) notion.so/my-integrations 에서 통합을 만들고 토큰을 받습니다\n"
            "       NOTION_TOKEN=ntn_...\n"
            "\n"
            "    2) 만들 자리가 될 노션 페이지를 하나 만들고,\n"
            "       그 페이지 오른쪽 위 ··· → 연결 → 방금 만든 통합을 고릅니다\n"
            "       (이걸 안 하면 토큰이 있어도 권한이 없다고 나옵니다)\n"
            "       페이지 주소 끝의 32자리가 페이지 id 입니다\n"
            "       NOTION_PARENT_PAGE_ID=1a2b3c...\n"
        )
    return token, _clean_id(parent)


def _clean_id(value: str) -> str:
    """주소를 통째로 붙여넣어도 id 만 뽑아낸다."""
    text = value.strip().rstrip("/").split("?")[0]
    tail = text.split("/")[-1]
    if "-" in tail and len(tail) > 32:
        tail = tail.split("-")[-1]
    return tail


# ------------------------------------------------------------------ 속성 모양
def build_property_schema(prop: PropertySpec, database_ids: dict[str, str]
                          ) -> tuple[str, dict | None, str]:
    """속성 하나를 노션이 아는 모양으로 바꾼다.

    돌려주는 것은 (쓸 타입, 요청 본문, 알림) 이다.
    본문이 None 이면 지금 단계에서는 만들지 않는다는 뜻이다.
    """
    kind = prop.type
    note = ""

    if kind in MANUAL_ONLY:
        kind = SUBSTITUTE[kind]
        note = why_manual(prop.type)

    if kind == "title":
        return kind, {"title": {}}, note
    if kind in ("rich_text", "date", "people", "files", "checkbox", "url",
                "email", "phone_number", "created_time", "created_by",
                "last_edited_time", "last_edited_by"):
        return kind, {kind: {}}, note
    if kind == "number":
        fmt = prop.number_format if prop.number_format in NUMBER_FORMATS else "number"
        if prop.number_format and fmt != prop.number_format:
            note = (note + " ").strip() + \
                f"모르는 숫자 형식({prop.number_format})이라 기본으로 두었습니다."
        return kind, {"number": {"format": fmt}}, note
    if kind in ("select", "multi_select"):
        options = [{"name": name} for name in prop.options]
        return kind, {kind: {"options": options}}, note
    if kind == "formula":
        return kind, {"formula": {"expression": prop.formula}}, note
    if kind == "relation":
        target = database_ids.get(prop.relation_to)
        if not target:
            return kind, None, "이을 데이터베이스가 아직 없습니다"
        return kind, {"relation": {"database_id": target,
                                   "type": "dual_property",
                                   "dual_property": {}}}, note
    if kind == "rollup":
        return kind, {"rollup": {
            "relation_property_name": prop.rollup_relation,
            "rollup_property_name": prop.rollup_property,
            "function": prop.rollup_function,
        }}, note

    return kind, None, f"만들 줄 모르는 타입입니다: {prop.type}"


def build_row_properties(db: DatabaseSpec, row: dict[str, Any]) -> dict:
    """예시 한 행을 노션 페이지 속성으로 바꾼다.

    관계 칸은 비운다. 상대 행의 id 를 알아야 채울 수 있는데, 예시 데이터끼리
    무엇을 이어야 하는지는 설계서에 없다. `build_guide.md` 가 손으로 잇게 안내한다.
    """
    built: dict[str, Any] = {}
    for name, value in row.items():
        prop = db.property_map.get(name)
        if prop is None or value in (None, ""):
            continue
        kind = prop.type
        if kind in MANUAL_ONLY:
            kind = SUBSTITUTE[kind]

        if kind == "title":
            built[name] = {"title": [{"text": {"content": str(value)}}]}
        elif kind == "rich_text":
            built[name] = {"rich_text": [{"text": {"content": str(value)}}]}
        elif kind == "number":
            try:
                built[name] = {"number": float(value)}
            except (TypeError, ValueError):
                continue
        elif kind == "select":
            built[name] = {"select": {"name": str(value)}}
        elif kind == "multi_select":
            names = value if isinstance(value, list) else [value]
            built[name] = {"multi_select": [{"name": str(v)} for v in names]}
        elif kind == "date":
            text = value.isoformat() if isinstance(value, (date, datetime)) else str(value)
            built[name] = {"date": {"start": text}}
        elif kind == "checkbox":
            built[name] = {"checkbox": bool(value)}
        elif kind in ("url", "email", "phone_number"):
            built[name] = {kind: str(value)}
    return built


# ------------------------------------------------------------------ API 호출
class _Notion:
    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Notion-Version": API_VERSION,
            "Content-Type": "application/json",
        })

    def call(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{API_BASE}{path}"
        for attempt in range(1, MAX_RETRY + 1):
            try:
                response = self.session.request(method, url, json=payload, timeout=30)
            except requests.RequestException as exc:
                if attempt == MAX_RETRY:
                    raise NotionError(f"노션에 닿지 못했습니다: {exc}") from exc
                time.sleep(attempt)
                continue

            if response.status_code == 429:
                # 쿼터를 넘었으면 재시도가 아니라 기다린다 (CLAUDE.md §7)
                wait = float(response.headers.get("Retry-After", attempt * 2))
                time.sleep(wait)
                continue

            if response.status_code >= 400:
                raise NotionError(_explain(response))

            time.sleep(PAUSE_SECONDS)
            return response.json()

        raise NotionError("노션이 계속 요청을 받지 못했습니다 (429). 잠시 뒤 다시 하세요")


def _explain(response) -> str:
    """노션의 오류를 무엇을 해야 하는지로 바꾼다."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    code = body.get("code", "")
    message = body.get("message", response.text[:200])

    hints = {
        "unauthorized": "토큰이 틀렸습니다. .env 의 NOTION_TOKEN 을 확인하세요.",
        "restricted_resource":
            "통합에 권한이 없습니다. 부모 페이지에서 ··· → 연결 → 통합을 고르세요.",
        "object_not_found":
            "페이지를 찾지 못했습니다. NOTION_PARENT_PAGE_ID 가 맞는지, "
            "그 페이지에 통합을 연결했는지 보세요.",
        "validation_error": "요청 모양이 맞지 않습니다. spec.yaml 을 확인하세요.",
        "rate_limited": "요청이 너무 잦습니다. 잠시 뒤 다시 하세요.",
    }
    hint = hints.get(code, "")
    return f"[{response.status_code} {code}] {message}" + (f"\n  → {hint}" if hint else "")


# ------------------------------------------------------------------- 만들기
def deploy(spec: TemplateSpec, token: str, parent_page_id: str) -> DeployReport:
    """설계대로 노션에 만든다. 중간에 실패해도 어디까지 했는지 남긴다."""
    report = DeployReport(spec_name=spec.name, parent_page_id=parent_page_id,
                          started_at=datetime.now().astimezone().isoformat(timespec="seconds"))
    api = _Notion(token)

    try:
        api.call("GET", "/users/me")
        report.add("연결", "토큰 확인", "ok")
    except NotionError as exc:
        report.add("연결", "토큰 확인", "failed", str(exc))
        report.failed_at = "토큰 확인"
        return report

    page_ids: dict[str, str] = {}
    database_ids: dict[str, str] = {}

    try:
        # 1단계 — 페이지 트리
        def make_page(node, parent_id: str) -> None:
            payload = {
                "parent": {"type": "page_id", "page_id": parent_id},
                "properties": {"title": [{"text": {"content": node.title}}]},
            }
            if node.icon:
                payload["icon"] = {"type": "emoji", "emoji": node.icon}
            created = api.call("POST", "/pages", payload)
            page_ids[node.title] = created["id"]
            report.add("페이지", node.title, "ok", node.purpose, created["id"])
            for child in node.children:
                make_page(child, created["id"])

        for page in spec.pages:
            make_page(page, parent_page_id)

        # 2단계 — 데이터베이스 (관계·롤업은 빼고)
        for db in spec.databases:
            parent_id = page_ids.get(db.parent_page) or next(iter(page_ids.values()))
            properties: dict[str, Any] = {}
            deferred: list[str] = []

            for prop in db.properties:
                if prop.type in ("relation", "rollup"):
                    deferred.append(prop.name)
                    continue
                _, schema, note = build_property_schema(prop, database_ids)
                if schema is None:
                    report.add("속성", f"{db.name}.{prop.name}", "skipped", note)
                    continue
                properties[prop.name] = schema
                if note:
                    report.manual_todo.append(f"{db.name} / {prop.name} — {note}")

            payload = {
                "parent": {"type": "page_id", "page_id": parent_id},
                "title": [{"text": {"content": db.name}}],
                "properties": properties,
            }
            if db.icon:
                payload["icon"] = {"type": "emoji", "emoji": db.icon}
            if db.description:
                payload["description"] = [{"text": {"content": db.description}}]

            created = api.call("POST", "/databases", payload)
            database_ids[db.key] = created["id"]
            report.add("데이터베이스", db.name, "ok",
                       f"속성 {len(properties)}개" +
                       (f" · 뒤로 미룬 것 {len(deferred)}개" if deferred else ""),
                       created["id"])

        # 3단계 — 관계 (id 를 다 알게 된 뒤)
        for db, prop in spec.relation_properties():
            if prop.type != "relation":
                continue
            _, schema, note = build_property_schema(prop, database_ids)
            if schema is None:
                report.add("관계", f"{db.name}.{prop.name}", "failed", note)
                continue
            api.call("PATCH", f"/databases/{database_ids[db.key]}",
                     {"properties": {prop.name: schema}})
            report.add("관계", f"{db.name}.{prop.name}", "ok",
                       f"→ {spec.database_map[prop.relation_to].name}")

        # 4단계 — 롤업 (관계가 생긴 뒤에야 걸 수 있다)
        for db, prop in spec.relation_properties():
            if prop.type != "rollup":
                continue
            _, schema, _ = build_property_schema(prop, database_ids)
            api.call("PATCH", f"/databases/{database_ids[db.key]}",
                     {"properties": {prop.name: schema}})
            report.add("롤업", f"{db.name}.{prop.name}", "ok",
                       f"{prop.rollup_relation} → {prop.rollup_property} "
                       f"({prop.rollup_function})")

        # 5단계 — 예시 데이터
        for db in spec.databases:
            made = 0
            for row in db.sample_rows:
                properties = build_row_properties(db, row)
                if not properties:
                    continue
                api.call("POST", "/pages",
                         {"parent": {"type": "database_id",
                                     "database_id": database_ids[db.key]},
                          "properties": properties})
                made += 1
            if made:
                report.add("예시 데이터", db.name, "ok", f"{made}행")

    except NotionError as exc:
        last = report.steps[-1].name if report.steps else "시작"
        report.add("중단", last, "failed", str(exc))
        report.failed_at = last

    # 손으로 해야 하는 것
    total_views = sum(len(db.views) for db in spec.databases)
    if total_views:
        report.manual_todo.append(
            f"뷰 {total_views}개 — 공개 API 로는 뷰를 만들지 못합니다. "
            "build_guide.md 4단계를 보고 손으로 만드세요.")
    if spec.buttons:
        report.manual_todo.append(
            f"템플릿 버튼 {len(spec.buttons)}개 — 공개 API 로는 만들지 못합니다. "
            "build_guide.md 6단계를 보세요.")
    if any(db.sample_rows for db in spec.databases):
        report.manual_todo.append(
            "예시 데이터의 관계 칸 — 어느 행끼리 이을지는 설계서에 없어 비워 두었습니다. "
            "노션에서 직접 골라 주세요.")
    report.manual_todo.append(
        "공유 → 웹에서 공유 → 템플릿 복제 허용을 켜야 구매자가 복제할 수 있습니다.")

    return report


def write_deploy_log(report: DeployReport, path: Path) -> Path:
    """어디까지 만들었는지 파일로 남긴다."""
    out = [f"# 노션 만들기 기록 — {report.spec_name}\n"]
    out.append(f"- 시작: {report.started_at}\n"
               f"- 부모 페이지: `{report.parent_page_id}`\n"
               f"- 만든 것: {report.made}개\n")

    if report.failures:
        out.append(f"\n> ⚠️ **`{report.failed_at}` 에서 멈췄습니다.**\n>\n"
                   "> 노션에 절반쯤 만들어진 것이 남아 있습니다. "
                   "아래 표에서 `ok` 까지가 만들어진 것입니다.\n"
                   "> 다시 실행하기 전에 **만들어진 페이지를 지우세요.** "
                   "그러지 않으면 같은 것이 두 벌 생깁니다.\n")
    else:
        out.append("\n> ✅ 끝까지 만들었습니다. 아래 '손으로 해야 하는 것' 을 마저 하세요.\n")

    out.append("\n## 단계별 기록\n")
    out.append("| 종류 | 이름 | 결과 | 비고 | 노션 id |\n|---|---|---|---|---|")
    for step in report.steps:
        mark = {"ok": "✅", "skipped": "⏭", "failed": "❌"}.get(step.status, step.status)
        out.append(f"| {step.kind} | {step.name} | {mark} | "
                   f"{step.detail.replace(chr(10), ' ')[:120]} | `{step.notion_id[:8]}` |")

    if report.manual_todo:
        out.append("\n## 손으로 해야 하는 것\n")
        out.append("공개 API 로 만들지 못하는 것들입니다. 이 목록을 다 처리해야 "
                   "팔 수 있는 상태가 됩니다.\n")
        for item in report.manual_todo:
            out.append(f"- [ ] {item}")

    out.append("\n## 다시 만들려면\n")
    out.append("1. 노션에서 이번에 만들어진 페이지를 통째로 지웁니다 (휴지통까지 비우세요).\n"
               "2. `python cli.py deploy <spec.yaml>` 을 다시 실행합니다.\n")
    out.append("\n같은 이름으로 또 만들어도 노션은 막지 않습니다. "
               "**지우지 않고 다시 돌리면 두 벌이 생깁니다.**\n")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")
    return path
