"""산출물 5종 쓰기.

    detail_page.md       크몽 상세페이지 본문 (섹션 순서 고정)
    packages.json        BASIC/STANDARD/PREMIUM. 크몽 입력 폼 필드명 기준
    title_variants.json  제목 10안 + 검색 태그 20개
    inquiry_scripts.md   문의 응답 템플릿 8종
    compliance_report.md 금지 문구·크몽 정책·전자상거래법 표기 검사 결과
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from kmong_copy.generator import CopyResult  # noqa: E402
from kmong_copy.policy import check_contact_lure  # noqa: E402
from kmong_copy.schema import (  # noqa: E402
    NO_PROOF_TEXT, PACKAGE_TIERS, TAG_COUNT, TITLE_COUNT, TITLE_LIMIT,
)
from shared import banned_phrases  # noqa: E402
from shared.ai_label import add_text_label  # noqa: E402

__all__ = [
    "write_detail_page", "write_packages", "write_titles",
    "write_inquiry_scripts", "write_compliance_report", "write_outputs",
    "KMONG_FIELDS",
]

#: 크몽 패키지 입력 폼 필드명. 크몽이 폼을 바꾸면 여기를 고친다.
KMONG_FIELDS = {
    "tier": "패키지 종류",
    "title": "패키지명",
    "description": "패키지 설명",
    "includes": "제공 항목",
    "days": "작업일",
    "revisions": "수정 횟수",
    "price": "가격",
}

#: 전자상거래법상 상세페이지에 반드시 있어야 하는 항목.
REQUIRED_POLICY_FIELDS = {
    "revisions": "수정 가능 횟수와 범위",
    "extra_cost": "추가 수정 시 비용",
    "refund_ok": "환불 가능한 경우",
    "refund_no": "환불이 어려운 경우",
    "cancel": "작업 시작 후 취소 시 처리",
}


def _collect_strings(value) -> str:
    """중첩된 JSON 에서 문자열만 모아 한 덩어리로."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(_collect_strings(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_collect_strings(item) for item in value)
    return ""


def write_detail_page(result: CopyResult, out_dir: Path, ai_label: bool = True) -> Path:
    """detail_page.md — 크몽 상세페이지 구조 그대로."""
    data = result.data
    detail = result.detail

    lines = [
        f"# {detail.get('headline', '')}",
        "",
        f"> {data.service_name} · {data.category}",
        "",
    ]
    for line in detail.get("summary", []):
        lines.append(line)
    lines.append("")

    lines += ["## 이런 분께 추천합니다", ""]
    lines += [f"- {item}" for item in detail.get("recommended_for", [])]
    not_for = detail.get("not_for", [])
    if not_for:
        lines += ["", "**이런 경우에는 맞지 않습니다**", ""]
        lines += [f"- {item}" for item in not_for]
    lines.append("")

    lines += ["## 제공 내용", "", "| 항목 | 내용 |", "|---|---|"]
    for item in detail.get("deliverables", []):
        lines.append(f"| {item.get('item', '')} | {item.get('detail', '')} |")
    lines.append("")

    lines += ["## 작업 프로세스", ""]
    for index, step in enumerate(detail.get("process", []), start=1):
        lines.append(f"**{index}. {step.get('step', '')}** — {step.get('what', '')}")
        if step.get("when"):
            lines.append(f"  소요: {step['when']}")
        lines.append("")

    lines += ["## 이 서비스의 차별점", ""]
    for item in detail.get("differentiators", []):
        lines += [f"### {item.get('title', '')}", "", item.get("body", ""), ""]

    lines += ["## 포트폴리오", ""]
    if data.has_proof:
        lines += [f"- {item}" for item in data.proof]
        lines += ["", "> 위 내용은 판매자가 제공한 자료입니다. "
                      "같은 결과를 보장하지 않으며 작업 조건에 따라 다를 수 있습니다."]
    else:
        lines += [
            f"{NO_PROOF_TEXT}입니다.",
            "",
            "> **[판매자가 채울 곳]** 작업물 이미지 3~5장을 이 자리에 올리세요. "
            "크몽 상세페이지는 이미지 영역이 따로 있습니다. "
            "실적이 없어도 샘플 작업물을 만들어 올리는 편이 낫습니다.",
        ]
    lines.append("")

    lines += ["## 자주 묻는 질문", ""]
    for item in detail.get("faq", []):
        lines += [f"**Q. {item.get('q', '')}**", "", item.get("a", ""), ""]

    lines += ["## 작업 전 준비해 주실 것", ""]
    lines += [f"- {item}" for item in detail.get("prepare", [])]
    lines.append("")

    policy = detail.get("policy", {})
    lines += [
        "## 수정·환불 정책",
        "",
        "| 항목 | 내용 |",
        "|---|---|",
        f"| 수정 횟수·범위 | {policy.get('revisions', '')} |",
        f"| 추가 수정 비용 | {policy.get('extra_cost', '')} |",
        f"| 환불 가능 | {policy.get('refund_ok', '')} |",
        f"| 환불 불가 | {policy.get('refund_no', '')} |",
        f"| 작업 시작 후 취소 | {policy.get('cancel', '')} |",
        "",
        "> **[판매자가 채울 곳]** 위 내용을 본인 운영 방식에 맞게 고치세요. "
        "전자상거래법상 청약철회 조건을 표시할 의무가 있고, "
        "실제 운영과 다르면 분쟁에서 불리해집니다.",
        "",
        "## AI 활용 고지",
        "",
        "이 상세페이지 초안은 생성형 AI로 작성한 뒤 판매자가 검토·수정했습니다. "
        "인공지능기본법 제31조에 따라 이 사실을 밝힙니다.",
        "",
    ]

    text = "\n".join(lines)
    if ai_label:
        text = add_text_label(text) + "\n"

    path = out_dir / "detail_page.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_packages(result: CopyResult, out_dir: Path) -> Path:
    """packages.json — 크몽 입력 폼 필드명 기준."""
    packages = result.packages.get("packages", [])
    by_tier = {str(p.get("tier", "")).upper(): p for p in packages}

    rows = []
    for tier in PACKAGE_TIERS:
        package = by_tier.get(tier, {})
        rows.append({
            KMONG_FIELDS["tier"]: tier,
            KMONG_FIELDS["title"]: package.get("title", ""),
            KMONG_FIELDS["description"]: package.get("description", ""),
            KMONG_FIELDS["includes"]: package.get("includes", []),
            KMONG_FIELDS["days"]: package.get("days", result.data.turnaround_days),
            KMONG_FIELDS["revisions"]: package.get("revisions", 1),
            KMONG_FIELDS["price"]: result.data.prices[tier],
        })

    payload = {
        "서비스명": result.data.service_name,
        "카테고리": result.data.category,
        "생성_시각": result.generated_at.isoformat(),
        "안내": "크몽 패키지 등록 화면의 각 칸에 그대로 옮겨 적으세요. "
                "폼이 바뀌었으면 kmong_copy/writers.py 의 KMONG_FIELDS 를 고치세요.",
        "패키지": rows,
    }
    path = out_dir / "packages.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def write_titles(result: CopyResult, out_dir: Path) -> Path:
    """title_variants.json — 제목 10안과 검색 태그."""
    packages = result.packages
    payload = {
        "서비스명": result.data.service_name,
        "생성_시각": result.generated_at.isoformat(),
        "제목_글자수_제한": TITLE_LIMIT,
        "안내": "크몽 검색은 제목 앞부분을 더 크게 봅니다. "
                "검색 키워드가 앞에 오는 안을 고르세요.",
        "제목_후보": [
            {
                "번호": index,
                "제목": title.get("text", ""),
                "글자수": len(str(title.get("text", ""))),
                "앞세운_키워드": title.get("keyword", ""),
            }
            for index, title in enumerate(packages.get("titles", [])[:TITLE_COUNT], start=1)
        ],
        "검색_태그": packages.get("tags", [])[:TAG_COUNT],
    }
    path = out_dir / "title_variants.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def write_inquiry_scripts(result: CopyResult, out_dir: Path,
                          ai_label: bool = True) -> Path:
    """inquiry_scripts.md — 문의 응답 템플릿 8종."""
    lines = [
        f"# 문의 응답 템플릿 — {result.data.service_name}",
        "",
        "복사해서 쓰되 `[ ]` 안은 상황에 맞게 채우세요.",
        "",
        "> ⚠️ **크몽 정책** 전화번호·이메일·카카오톡·외부 링크를 절대 넣지 마세요. "
        "플랫폼 밖 거래 유도로 보여 서비스가 내려가거나 계정이 정지될 수 있습니다. "
        "문의는 크몽 메시지로만 받으세요.",
        "",
    ]
    for index, script in enumerate(result.scripts.get("scripts", []), start=1):
        lines += [
            f"## {index}. {script.get('situation', '')}",
            "",
            f"*{script.get('when', '')}*",
            "",
            "```",
            str(script.get("body", "")).strip(),
            "```",
            "",
        ]
        if script.get("tip"):
            lines += [f"> {script['tip']}", ""]

    text = "\n".join(lines)
    if ai_label:
        text = add_text_label(text) + "\n"

    path = out_dir / "inquiry_scripts.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_compliance_report(result: CopyResult, out_dir: Path) -> tuple[Path, bool]:
    """compliance_report.md — 검사 결과. (경로, 전부 통과 여부) 를 돌려준다."""
    data = result.data
    detail = result.detail

    # 검사 대상은 두 가지다.
    #   1. LLM 이 만든 카피 — 여기서 사고가 난다
    #   2. 판매자가 입력한 값 — 차별점 칸에 전화번호를 적는 경우가 실제로 있다
    # 프로그램이 넣는 고정 안내문("전화번호를 쓰지 마세요" 같은 경고)은 검사하지 않는다.
    # 그 문구 자체가 금지어를 포함하고 있어 검사하면 스스로 걸린다.
    produced = "\n".join(
        _collect_strings(section.data) for section in result.sections.values()
    )
    from_input = "\n".join([
        data.service_name, data.category, data.who_for,
        *data.what_you_deliver, *data.differentiators, *data.proof, *data.faq_seed,
    ])
    checked = f"{produced}\n{from_input}"

    banned_found = banned_phrases.check(checked)
    contact_found = check_contact_lure(checked)

    policy = detail.get("policy", {})
    missing_policy = [
        label for key, label in REQUIRED_POLICY_FIELDS.items()
        if not str(policy.get(key, "")).strip()
    ]

    numbers_without_proof = []
    if not data.has_proof:
        import re

        for match in re.finditer(r"\d[\d,]*\s*(?:건|명|%|퍼센트|배)", checked):
            snippet = checked[max(0, match.start() - 20):match.end() + 10]
            numbers_without_proof.append(" ".join(snippet.split()))

    passed = not (banned_found or contact_found or missing_policy)

    lines = [
        f"# 등록 전 점검 — {data.service_name}",
        "",
        f"- 생성 시각: {result.generated_at.strftime('%Y-%m-%d %H:%M:%S %z')}",
        f"- 모델: {result.model}",
        f"- 결과: {'✅ 통과' if passed else '⚠️ 확인 필요'}",
        "",
        "## 1. 금지 문구 검사",
        "",
        f"성과를 단정하는 표현 {len(banned_phrases.BANNED)}개를 검사했습니다 "
        "(`shared/banned_phrases.py`).",
        "",
        "검사 범위는 AI가 만든 카피와 입력하신 값입니다. "
        "프로그램이 넣는 고정 안내문은 제외했습니다.",
        "",
    ]
    if banned_found:
        lines += [
            f"⚠️ **{len(banned_found)}건 발견 — 등록 전 반드시 고치세요.**", "",
        ]
        lines += [f"- `{phrase}`" for phrase in banned_found]
    else:
        lines.append("✅ 발견되지 않았습니다.")
    lines.append("")

    lines += [
        "## 2. 크몽 정책 — 외부 연락처 유도",
        "",
        "전화번호·이메일·카카오톡·외부 링크·직거래 유도를 검사했습니다.",
        "적발되면 서비스가 내려가고 반복되면 계정이 정지됩니다.",
        "",
    ]
    if contact_found:
        lines += [f"⚠️ **{len(contact_found)}건 발견 — 등록 전 반드시 지우세요.**", "",
                  "| 종류 | 발견된 문구 | 앞뒤 문맥 |", "|---|---|---|"]
        for finding in contact_found:
            lines.append(f"| {finding.label} | `{finding.matched}` | {finding.context} |")
    else:
        lines.append("✅ 발견되지 않았습니다.")
    lines.append("")

    lines += [
        "## 3. 전자상거래법 필수 표기",
        "",
        "온라인으로 용역을 파는 경우 아래를 표시할 의무가 있습니다.",
        "",
        "| 항목 | 상태 |",
        "|---|---|",
    ]
    for key, label in REQUIRED_POLICY_FIELDS.items():
        filled = bool(str(policy.get(key, "")).strip())
        lines.append(f"| {label} | {'✅ 작성됨' if filled else '⚠️ 비어 있음'} |")
    lines += [
        "",
        "> 자동으로 만든 문구는 **초안**입니다. 실제 운영 방식과 다르면 분쟁에서 불리합니다. "
        "본인 기준으로 고쳐서 쓰세요.",
        "",
        "### 크몽 판매자 정보에도 필요한 것",
        "",
        "- [ ] 상호·대표자명·사업자등록번호 (크몽 판매자 정보에 등록)",
        "- [ ] 통신판매업 신고번호 (해당하는 경우)",
        "- [ ] 사업자가 아니라면 크몽의 개인 판매자 조건을 확인",
        "",
        "## 4. 근거 없는 수치",
        "",
    ]
    if not data.has_proof:
        if numbers_without_proof:
            lines += [
                f"⚠️ 실적 자료를 넣지 않으셨는데 수치 표현이 {len(numbers_without_proof)}건 "
                "보입니다. 사실인지 확인하세요.", "",
            ]
            lines += [f"- {item}" for item in numbers_without_proof[:10]]
        else:
            lines.append("✅ 실적 자료가 없고 지어낸 수치도 없습니다.")
    else:
        lines.append(
            f"입력하신 실적 {len(data.proof)}건을 그대로 썼습니다. "
            "실제 자료와 일치하는지 대조하세요."
        )
    lines.append("")

    lines += [
        "## 5. 섹션별 생성 이력",
        "",
        "| 섹션 | 생성 시도 | 금지 문구 | 외부 연락처 | 길이 제한 |",
        "|---|---|---|---|---|",
    ]
    for name, section in result.sections.items():
        banned = ", ".join(section.banned) if section.banned else "통과"
        contact = (
            ", ".join(sorted({f.label for f in section.contact}))
            if section.contact else "통과"
        )
        length = (
            f"⚠ {len(section.length_fixes)}건 자동 보정"
            if section.length_fixes else "통과"
        )
        lines.append(f"| {name} | {section.attempts}회 | {banned} | {contact} | {length} |")

    lines += [
        "",
        "## 6. 등록 전 최종 확인",
        "",
        "- [ ] 위 1~3번에 ⚠️ 가 없다",
        "- [ ] 포트폴리오 이미지를 올렸다",
        "- [ ] 환불·수정 정책을 본인 기준으로 고쳤다",
        "- [ ] 패키지 가격과 작업일이 실제로 지킬 수 있는 값이다",
        "- [ ] 제목 10안 중 하나를 골랐다",
        "",
    ]

    path = out_dir / "compliance_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path, passed


def write_outputs(result: CopyResult, out_root: Path,
                  ai_label: bool = True) -> tuple[Path, bool]:
    """산출물 5종을 쓰고 (폴더 경로, 점검 통과 여부) 를 돌려준다."""
    out_dir = out_root / result.data.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    write_detail_page(result, out_dir, ai_label)
    write_packages(result, out_dir)
    write_titles(result, out_dir)
    write_inquiry_scripts(result, out_dir, ai_label)
    _, passed = write_compliance_report(result, out_dir)
    return out_dir, passed
