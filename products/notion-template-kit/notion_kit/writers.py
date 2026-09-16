"""산출물 6종을 쓴다.

    1. spec.yaml          구조 설계 — 사람도 읽고 deploy 도 읽는다
    2. build_guide.md     노션에서 손으로 만드는 단계별 가이드
    3. sales_page.md      판매 문구 + 금지 표현 점검 결과
    4. user_manual.md     구매자용 사용 설명서
    5. preview_brief.md   썸네일·미리보기 촬영 지시서
    6. variants.md        타깃만 바꿔 만드는 파생 템플릿 5개

`build_guide.md` 는 **설계에서 기계적으로 만든다.** 사람이 쓴 설명서는 설계가
바뀌면 조용히 낡고, 그 낡은 설명서를 따라 만든 사람이 중간에서 막힌다.
소요 시간도 개수를 세어 계산하므로 구조가 커지면 자동으로 늘어난다.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from notion_kit.notion_types import MANUAL_ONLY, why_manual   # noqa: E402
from notion_kit.schema import DatabaseSpec, TemplateSpec       # noqa: E402
from shared import banned_phrases                              # noqa: E402
from shared.ai_label import add_text_label                     # noqa: E402

__all__ = ["write_outputs", "MINUTES", "estimate_minutes", "OUTPUT_FILES"]

#: 산출물 이름. 대시보드와 테스트가 이 목록을 본다.
OUTPUT_FILES = ("spec.yaml", "build_guide.md", "sales_page.md",
                "user_manual.md", "preview_brief.md", "variants.md")

#: 손으로 만들 때 걸리는 시간(분). 노션을 처음 다루는 사람 기준으로 넉넉히 잡았다.
MINUTES = {
    "page": 1.5,
    "database": 3.0,
    "property": 0.7,
    "linked_property": 2.0,     # 관계·롤업은 대상을 고르고 확인하는 시간이 더 든다
    "manual_property": 1.5,     # API 로 못 만들어 손으로만 되는 것
    "view": 2.5,
    "sample_row": 0.5,
    "button": 3.5,
}


def estimate_minutes(spec: TemplateSpec) -> dict[str, float]:
    """항목 수를 세어 소요 시간을 잡는다."""
    pages = sum(1 for page in spec.pages for _ in page.walk())
    plain = linked = manual = views = rows = 0
    for db in spec.databases:
        for prop in db.properties:
            if prop.type in MANUAL_ONLY:
                manual += 1
            elif prop.type in ("relation", "rollup"):
                linked += 1
            else:
                plain += 1
        views += len(db.views)
        rows += len(db.sample_rows)

    parts = {
        "페이지 만들기": pages * MINUTES["page"],
        "데이터베이스 만들기": len(spec.databases) * MINUTES["database"],
        "속성 넣기": plain * MINUTES["property"],
        "관계·롤업 잇기": linked * MINUTES["linked_property"],
        "손으로만 되는 속성": manual * MINUTES["manual_property"],
        "뷰 만들기": views * MINUTES["view"],
        "예시 데이터 넣기": rows * MINUTES["sample_row"],
        "버튼 만들기": len(spec.buttons) * MINUTES["button"],
    }
    parts["합계"] = sum(parts.values())
    return parts


def _type_label(prop) -> str:
    label = prop.type
    if prop.type in MANUAL_ONLY:
        label += " ⚠️"
    return label


def _property_table(db: DatabaseSpec) -> list[str]:
    lines = ["| 속성 | 타입 | 설정 | 설명 |", "|---|---|---|---|"]
    for prop in db.properties:
        detail = ""
        if prop.options:
            detail = "선택지: " + ", ".join(prop.options)
        elif prop.type == "relation":
            detail = f"→ {prop.relation_to}"
        elif prop.type == "rollup":
            detail = (f"{prop.rollup_relation} 을 타고 "
                      f"{prop.rollup_property} 를 {prop.rollup_function}")
        elif prop.type == "formula":
            detail = f"`{prop.formula}`"
        elif prop.number_format:
            detail = f"형식: {prop.number_format}"
        lines.append(f"| {prop.name} | {_type_label(prop)} | {detail} | {prop.description} |")
    return lines


# --------------------------------------------------------------- 1. spec.yaml
def write_spec(spec: TemplateSpec, path: Path) -> Path:
    data = spec.model_dump(mode="json", exclude_defaults=False)
    header = (
        "# 노션 템플릿 구조 설계\n"
        f"# {spec.name} — {spec.audience} 대상\n"
        "#\n"
        "# 이 파일은 두 곳에서 읽습니다.\n"
        "#   사람     build_guide.md 를 보며 노션에서 손으로 만들 때\n"
        "#   프로그램 python cli.py deploy 로 노션 API 가 만들 때\n"
        "#\n"
        "# ⚠️ 표시된 속성은 공개 API 로 만들지 못해 노션에서 직접 바꿔야 합니다.\n"
        "# 뷰(views)도 공개 API 로는 만들지 못합니다. 설계만 적혀 있습니다.\n"
        "\n"
    )
    path.write_text(header + yaml.safe_dump(data, allow_unicode=True,
                                            sort_keys=False, width=100),
                    encoding="utf-8")
    return path


# ---------------------------------------------------------- 2. build_guide.md
def write_build_guide(spec: TemplateSpec, path: Path, ai_label: bool = True) -> Path:
    times = estimate_minutes(spec)
    out: list[str] = []

    out.append(f"# {spec.name} — 만드는 순서\n")
    out.append(f"노션에서 **손으로** 만드는 가이드입니다. "
               f"예상 소요 **약 {times['합계'] / 60:.1f}시간** "
               f"({times['합계']:.0f}분).\n")
    out.append("> 자동으로 만들고 싶으시면 `python cli.py deploy spec.yaml` 을 쓰세요.\n"
               "> 다만 **뷰와 일부 속성은 자동으로 못 만듭니다.** 그 부분은 "
               "여기 적힌 대로 손으로 하셔야 합니다.\n")

    out.append("\n## 시간이 어디에 드는가\n")
    out.append("| 단계 | 분 |\n|---|--:|")
    for label, minutes in times.items():
        if label == "합계" or minutes <= 0:
            continue
        out.append(f"| {label} | {minutes:.0f} |")
    out.append(f"| **합계** | **{times['합계']:.0f}** |\n")

    out.append("\n## 0단계. 시작하기 전에\n")
    out.append("- 노션 계정이 있어야 합니다. 무료 요금제로 충분합니다.\n"
               "- 빈 페이지를 하나 만들고 시작하세요. 기존 페이지 안에 만들면 "
               "나중에 복제 링크를 만들 때 딸려 나갈 것이 생깁니다.\n"
               "- 데이터베이스를 먼저 다 만들고 **그다음에** 관계를 잇습니다. "
               "순서를 바꾸면 이을 대상이 없어 두 번 일하게 됩니다.\n")
    out.append("\n> 📷 **스크린샷 자리** — 빈 페이지에서 시작하는 화면\n")

    # 1단계 페이지
    out.append("\n## 1단계. 페이지 만들기\n")
    for page in spec.pages:
        for node in page.walk():
            depth = 0
            out.append(f"- {'  ' * depth}{node.icon} **{node.title}** — {node.purpose}")
    out.append("\n페이지 안에 하위 페이지를 만들려면 본문에서 `/페이지` 를 치면 됩니다.\n")
    out.append("> 📷 **스크린샷 자리** — 페이지 트리가 완성된 좌측 사이드바\n")

    # 2단계 데이터베이스
    out.append(f"\n## 2단계. 데이터베이스 {len(spec.databases)}개 만들기\n")
    out.append("본문에서 `/표 데이터베이스` 를 치고 **전체 페이지** 를 고르세요.\n")
    for index, db in enumerate(spec.databases, start=1):
        out.append(f"\n### 2-{index}. {db.icon} {db.name}")
        out.append(f"\n{db.description}")
        if db.parent_page:
            out.append(f"\n둘 곳: **{db.parent_page}** 페이지 안")
        out.append("")
        out.extend(_property_table(db))
        manual = [p for p in db.properties if p.type in MANUAL_ONLY]
        if manual:
            out.append("\n⚠️ 아래 속성은 노션에서 직접 만들어야 합니다.\n")
            for prop in manual:
                out.append(f"- **{prop.name}** — {why_manual(prop.type)}")
        out.append("\n> 📷 **스크린샷 자리** — "
                   f"{db.name} 속성 설정이 끝난 화면\n")

    # 3단계 관계
    linked = spec.relation_properties()
    if linked:
        out.append("\n## 3단계. 관계와 롤업 잇기\n")
        out.append("**데이터베이스를 전부 만든 뒤에 하세요.** 관계는 이을 상대가 "
                   "이미 있어야 고를 수 있습니다.\n")
        for db, prop in linked:
            if prop.type == "relation":
                target = spec.database_map[prop.relation_to]
                out.append(f"1. **{db.name}** 의 `{prop.name}` → 관계 → "
                           f"**{target.name}** 을 고릅니다.")
            else:
                out.append(f"1. **{db.name}** 의 `{prop.name}` → 롤업 → "
                           f"관계 `{prop.rollup_relation}`, "
                           f"속성 `{prop.rollup_property}`, "
                           f"계산 `{prop.rollup_function}` 를 고릅니다.")
        out.append("\n롤업은 **관계를 먼저 이어야** 고를 수 있습니다. "
                   "관계가 비어 있으면 롤업 목록에 아무것도 안 뜹니다.\n")
        out.append("> 📷 **스크린샷 자리** — 관계 속성 설정 창\n")

    # 4단계 뷰
    total_views = sum(len(db.views) for db in spec.databases)
    if total_views:
        out.append(f"\n## 4단계. 뷰 {total_views}개 만들기\n")
        out.append("데이터베이스 위쪽 `+` 를 눌러 뷰를 추가합니다.\n")
        for db in spec.databases:
            if not db.views:
                continue
            out.append(f"\n**{db.name}**\n")
            out.append("| 뷰 | 종류 | 설정 | 왜 필요한가 |\n|---|---|---|---|")
            for view in db.views:
                setting = []
                if view.group_by:
                    setting.append(f"그룹: {view.group_by}")
                if view.date_property:
                    setting.append(f"날짜: {view.date_property}")
                if view.filter_note:
                    setting.append(f"필터: {view.filter_note}")
                if view.sort_note:
                    setting.append(f"정렬: {view.sort_note}")
                out.append(f"| {view.name} | {view.type} | "
                           f"{' · '.join(setting) or '기본'} | {view.purpose} |")
        out.append("\n> 📷 **스크린샷 자리** — 뷰 탭이 여러 개 달린 데이터베이스\n")

    # 5단계 예시 데이터
    rows = sum(len(db.sample_rows) for db in spec.databases)
    if rows:
        out.append(f"\n## 5단계. 예시 데이터 {rows}행 넣기\n")
        out.append("구매자가 **지우고 쓰는** 데이터입니다. 실제 고객 이름이나 "
                   "실제 금액을 넣지 마세요.\n")
        for db in spec.databases:
            if not db.sample_rows:
                continue
            title_prop = db.title_property
            names = [str(row.get(title_prop.name, "")) for row in db.sample_rows] \
                if title_prop else []
            out.append(f"- **{db.name}** {len(db.sample_rows)}행: "
                       + ", ".join(filter(None, names)))
        out.append("\n관계 칸은 **양쪽 데이터를 다 넣은 뒤** 채우세요.\n")

    # 6단계 버튼
    if spec.buttons:
        out.append(f"\n## 6단계. 템플릿 버튼 {len(spec.buttons)}개\n")
        out.append("본문에서 `/버튼` 을 치고 만듭니다. "
                   "동작은 **페이지 추가 위치**를 고른 뒤 대상 데이터베이스를 고릅니다.\n")
        for button in spec.buttons:
            target = spec.database_map.get(button.creates)
            out.append(f"\n**{button.name}** — {button.where} 페이지에 둡니다")
            out.append(f"- 만드는 곳: {target.name if target else button.creates}")
            if button.prefill:
                filled = ", ".join(f"{k} = {v}" for k, v in button.prefill.items())
                out.append(f"- 미리 채울 값: {filled}")
            if button.note:
                out.append(f"- {button.note}")
        out.append("\n> 📷 **스크린샷 자리** — 버튼 동작 설정 화면\n")

    out.append("\n## 7단계. 복제 링크 만들기\n")
    out.append("1. 맨 위 페이지 오른쪽 위 **공유** → **웹에서 공유** 를 켭니다.\n"
               "2. **템플릿 복제 허용** 을 켭니다. 이걸 켜야 구매자가 복제할 수 있습니다.\n"
               "3. 주소 끝에 `?duplicate=true` 를 붙이면 열자마자 복제 창이 뜹니다.\n"
               "4. **로그아웃 상태의 다른 브라우저에서 직접 열어 보세요.** "
               "공유를 안 켜고 링크를 파는 사고가 가장 흔합니다.\n")
    out.append("\n> 📷 **스크린샷 자리** — 공유 설정에서 템플릿 복제 허용을 켠 화면\n")

    out.append("\n## 마지막 점검\n")
    out.append("- [ ] 로그아웃 상태에서 복제가 되는가\n"
               "- [ ] 복제한 쪽에서 관계 속성이 연결되어 있는가\n"
               "- [ ] 롤업이 0 이 아닌 값을 보여 주는가\n"
               "- [ ] 예시 데이터에 실제 정보가 섞이지 않았는가\n"
               "- [ ] 휴대폰에서 열었을 때 첫 화면이 쓸 만한가\n")

    text = "\n".join(out)
    if ai_label:
        text = add_text_label(text)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------- 3. sales_page.md
def write_sales_page(spec: TemplateSpec, sales: dict, path: Path,
                     ai_label: bool = True) -> tuple[Path, list[str]]:
    out = [f"# {spec.name} — 판매 문구\n"]
    out.append(f"대상: **{spec.audience}** · 주제: {spec.topic}\n")

    out.append("\n## 제목 5안\n")
    for index, title in enumerate(sales.get("titles", []), start=1):
        out.append(f"{index}. {title}  <span>({len(title)}자)</span>")
    out.append("\n제목에 **타깃이 들어간 안**을 고르세요. "
               "'프로젝트 관리 템플릿' 보다 '1인 디자이너용' 이 붙은 쪽이 눈에 띕니다.\n")

    out.append("\n## 소개\n")
    intro = sales.get("intro", "")
    out.append(intro)
    out.append(f"\n<span>({len(intro)}자)</span>\n")

    out.append("\n## 포함 내용\n")
    for item in sales.get("included", []):
        out.append(f"- {item}")

    out.append("\n## 사용법 3단계\n")
    for index, step in enumerate(sales.get("howto", []), start=1):
        out.append(f"{index}. {step}")

    out.append("\n## 이런 분께 맞습니다\n")
    for item in sales.get("audience", []):
        out.append(f"- {item}")

    if sales.get("not_for"):
        out.append("\n## 이런 분께는 맞지 않습니다\n")
        for item in sales["not_for"]:
            out.append(f"- {item}")
        out.append("\n안 맞는 분을 미리 걸러 내면 환불과 낮은 별점이 줄어듭니다. "
                   "이 칸을 지우지 마세요.\n")

    out.append("\n## 가격 3안\n")
    out.append("| 안 | 가격 | 포함 | 메모 |\n|---|--:|---|---|")
    for plan in sales.get("pricing", []):
        out.append(f"| {plan.get('name','')} | {int(plan.get('price', 0)):,}원 | "
                   f"{plan.get('includes','')} | {plan.get('note','')} |")
    out.append("\n가운데 안이 가장 많이 팔립니다. 낮은 안은 문턱을 낮추고, "
               "높은 안은 객단가를 올립니다.\n")

    # 금지 표현 점검
    body = "\n".join(out)
    found = banned_phrases.check(body)
    out.append("\n## 등록 전 점검\n")
    if found:
        out.append("⚠️ **쓰면 안 되는 표현이 남아 있습니다. 고치고 올리세요.**\n")
        for phrase in found:
            out.append(f"- `{phrase}`")
        out.append("\n고액 부업·템플릿 판매는 소비자원 주의보가 나온 분야입니다. "
                   "성과를 단정하는 문구는 분쟁의 근거가 됩니다.\n")
    else:
        out.append("✅ 성과를 단정하는 표현은 없습니다.\n")
    out.append("- [ ] 실적 수치를 지어내지 않았는가 (썼다면 실제 기록이 있는가)\n"
               "- [ ] 미리보기 이미지가 실제 화면과 같은가\n"
               "- [ ] 환불 조건을 적었는가 (디지털 상품은 다툼이 잦습니다)\n"
               "- [ ] 노션 로고나 공식 이미지를 쓰지 않았는가\n")

    text = "\n".join(out)
    if ai_label:
        text = add_text_label(text)
    path.write_text(text, encoding="utf-8")
    return path, found


# ---------------------------------------------------------- 4. user_manual.md
def write_user_manual(spec: TemplateSpec, extras: dict, path: Path,
                      ai_label: bool = True) -> Path:
    out = [f"# {spec.name} — 사용 설명서\n"]
    out.append("구매해 주셔서 감사합니다. 10분이면 다 읽습니다.\n")

    out.append("\n## 1. 복제하기\n")
    out.append("1. 받으신 링크를 엽니다.\n"
               "2. 오른쪽 위 **복제(Duplicate)** 를 누릅니다.\n"
               "3. 내 노션 계정 안으로 들어옵니다. 이제 마음대로 고치셔도 됩니다.\n")
    out.append("\n복제 버튼이 안 보이면 로그인이 안 된 상태입니다. "
               "노션에 로그인한 뒤 다시 열어 주세요.\n")

    out.append("\n## 2. 무엇이 들어 있나\n")
    out.append(f"{spec.summary}\n")
    out.append("\n| 데이터베이스 | 한 행이 무엇인가 | 언제 여나 |\n|---|---|---|")
    for db in spec.databases:
        views = db.views[0].name if db.views else "기본"
        out.append(f"| {db.icon} {db.name} | {db.description} | {views} 뷰부터 보세요 |")

    out.append("\n### 서로 어떻게 연결되어 있나\n")
    linked = [(db, prop) for db, prop in spec.relation_properties()
              if prop.type == "relation"]
    if linked:
        for db, prop in linked:
            target = spec.database_map[prop.relation_to]
            out.append(f"- **{db.name}** 의 `{prop.name}` → **{target.name}**")
        out.append("\n이 연결이 이 템플릿의 핵심입니다. 표를 여러 개 만드는 것과 "
                   "다른 점이 여기 있습니다. 한쪽을 채우면 다른 쪽에서 같이 보입니다.\n")

    out.append("\n## 3. 각 데이터베이스 설명\n")
    for db in spec.databases:
        out.append(f"\n### {db.icon} {db.name}\n")
        out.append(f"{db.description}\n")
        out.extend(_property_table(db))
        if db.views:
            out.append("\n**뷰**\n")
            for view in db.views:
                out.append(f"- **{view.name}** ({view.type}) — {view.purpose}")
        out.append("")

    if spec.buttons:
        out.append("\n## 4. 버튼\n")
        for button in spec.buttons:
            target = spec.database_map.get(button.creates)
            out.append(f"- **{button.name}** — 누르면 "
                       f"{target.name if target else button.creates} 에 새 항목이 생깁니다. "
                       f"{button.note}")

    if extras.get("first_week"):
        out.append("\n## 5. 첫 주에 할 일\n")
        for item in extras["first_week"]:
            out.append(f"- {item}")

    out.append("\n## 6. 자주 하는 실수\n")
    for item in extras.get("mistakes", []):
        out.append(f"\n### {item.get('what','')}\n")
        out.append(f"**왜 그런가** {item.get('why','')}\n")
        out.append(f"**어떻게 고치나** {item.get('fix','')}\n")

    out.append("\n## 7. 그 밖에\n")
    out.append("- **속성을 마음대로 지우셔도 됩니다.** 안 쓰는 칸은 없느니만 못합니다. "
               "다만 관계·롤업 속성을 지우면 연결이 끊기니 그것만 조심하세요.\n"
               "- **무료 요금제로 충분합니다.** 이 템플릿은 유료 기능을 쓰지 않습니다.\n"
               "- **휴대폰에서도 열립니다.** 다만 보드 뷰는 좁아서 답답하니, "
               "자주 보시는 표 뷰를 맨 앞으로 옮겨 두세요.\n")

    text = "\n".join(out)
    if ai_label:
        text = add_text_label(text)
    path.write_text(text, encoding="utf-8")
    return path


# -------------------------------------------------------- 5. preview_brief.md
def write_preview_brief(spec: TemplateSpec, extras: dict, path: Path,
                        ai_label: bool = True) -> Path:
    preview = extras.get("preview", {})
    out = [f"# {spec.name} — 미리보기 이미지 지시서\n"]
    out.append("**그리는 것이 아니라 찍는 것입니다.** 실제로 만든 노션 화면을 "
               "캡처해서 쓰세요. 실제와 다른 이미지는 환불 사유가 됩니다.\n")

    out.append("\n## 썸네일 (1장)\n")
    out.append(preview.get("thumbnail", "") or "_받지 못했습니다._")
    out.append("\n썸네일은 목록에서 **작게** 보입니다. 글씨를 크게, 요소를 적게 두세요.\n")

    out.append("\n## 미리보기 이미지\n")
    shots = preview.get("shots", [])
    for index, shot in enumerate(shots, start=1):
        out.append(f"\n### {index}. {shot.get('title','')}\n")
        out.append(f"**무엇을 찍나** {shot.get('what','')}\n")
        out.append(f"**왜 이 장면인가** {shot.get('why','')}\n")
        out.append("> 📷 **촬영 자리**\n")

    if preview.get("avoid"):
        out.append("\n## 하지 말아야 할 것\n")
        for item in preview["avoid"]:
            out.append(f"- {item}")

    out.append("\n## 찍기 전 준비\n")
    out.append("- 예시 데이터를 **보기 좋게** 채워 두세요. 빈 화면은 팔리지 않습니다.\n"
               "- 브라우저 확대를 110~125% 로 올리면 글씨가 또렷하게 찍힙니다.\n"
               "- 사이드바는 접으세요. 내 다른 페이지 이름이 그대로 찍힙니다.\n"
               "- 다크 모드와 라이트 모드 중 **하나로 통일**하세요. 섞이면 지저분해 보입니다.\n")

    out.append("\n## 크기\n")
    out.append("| 쓰는 곳 | 권장 비율 |\n|---|---|\n"
               "| 크몽 썸네일 | 가로형 4:3 |\n"
               "| 노션 마켓 | 가로형 16:9 |\n"
               "| 인스타 피드 | 정사각 1:1 또는 세로 4:5 |\n")
    out.append("\n정확한 크기는 올리는 곳의 안내를 보고 맞추세요. 플랫폼마다 다르고 자주 바뀝니다.\n")

    text = "\n".join(out)
    if ai_label:
        text = add_text_label(text)
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------- 6. variants.md
def write_variants(spec: TemplateSpec, extras: dict, path: Path,
                   ai_label: bool = True) -> Path:
    out = [f"# {spec.name} 에서 파생할 수 있는 템플릿\n"]
    out.append("구조는 그대로 두고 **타깃과 낱말만 바꿔** 만드는 것들입니다. "
               "처음 하나를 만드는 시간의 10~20% 로 한 개가 더 나옵니다.\n")
    out.append("\n> ⚠️ 다만 **아무거나 늘리지 마세요.** 팔리는 이유는 타깃이 "
               "'내 얘기' 라고 느끼기 때문입니다. 내가 모르는 직군으로 넓히면 "
               "그 느낌이 사라지고, 질문이 들어와도 답할 수 없습니다.\n")

    out.append("\n| 파생 템플릿 | 타깃 | 무엇만 바꾸나 | 예상 시간 |\n|---|---|---|---|")
    for item in extras.get("variants", []):
        out.append(f"| {item.get('name','')} | {item.get('audience','')} | "
                   f"{item.get('changes','')} | {item.get('effort','')} |")

    out.append("\n## 파생을 만들 때 순서\n")
    out.append("1. 원본을 복제합니다. 처음부터 만들지 마세요.\n"
               "2. **낱말부터 바꿉니다.** 데이터베이스 이름, 속성 이름, 선택지.\n"
               "3. 예시 데이터를 새 타깃에 맞게 다시 씁니다. "
               "여기를 안 바꾸면 티가 바로 납니다.\n"
               "4. 뷰 이름과 필터를 손봅니다.\n"
               "5. 판매 문구는 **다시 씁니다.** 원본 문구에서 낱말만 바꾸면 "
               "그 타깃의 말이 아니게 됩니다.\n")

    out.append("\n## 얼마나 늘릴 것인가\n")
    out.append("3~4개가 적당합니다. 그 이상은 관리가 안 됩니다. "
               "템플릿마다 문의가 들어오고, 노션이 바뀌면 전부 손봐야 합니다.\n")
    out.append("\n같은 구조를 여러 타깃에 파는 것은 정상적인 방식이지만, "
               "**내용 없이 개수만 늘리는 것**은 다릅니다. 플랫폼도 구매자도 금방 알아봅니다.\n")

    text = "\n".join(out)
    if ai_label:
        text = add_text_label(text)
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------- 진입점
def write_outputs(spec: TemplateSpec, sales: dict, extras: dict, out_root: Path,
                  ai_label: bool = True) -> tuple[Path, list[str]]:
    """산출물 6종을 `<out_root>/<slug>/` 에 쓴다."""
    out_dir = Path(out_root) / spec.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    write_spec(spec, out_dir / "spec.yaml")
    write_build_guide(spec, out_dir / "build_guide.md", ai_label)
    _, dirty = write_sales_page(spec, sales, out_dir / "sales_page.md", ai_label)
    write_user_manual(spec, extras, out_dir / "user_manual.md", ai_label)
    write_preview_brief(spec, extras, out_dir / "preview_brief.md", ai_label)
    write_variants(spec, extras, out_dir / "variants.md", ai_label)

    return out_dir, dirty
