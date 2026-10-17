"""③ 대본 3안 — 만들기 · 고치기 · 승인①.

17번 기획기의 규칙(얼굴·출처·가격·효능·추천 표현)을 **그대로** 통과해야 한다.
여기에 셀럽오르빗 규칙 두 가지를 더한다(강의 분석 E-3).

- 0~3초 훅: 첫 장면이 0초에 시작해 3초 안에 끝나야 한다 → 아니면 막음.
- 제품명·브랜드는 4초 이후 공개 → 앞에 나오면 경고(권장 사항이라 막지는 않는다).

승인①에는 **확인한 사람 이름**과 **«내 말 한 줄»** 이 필요하다. 사람의 말이 한 줄도 없는 영상은
양산형으로 판정될 위험이 크다(설계 7장). 모의 생성 대본은 승인할 수 없다.
"""

from __future__ import annotations

import json
from typing import Callable

from celeb_shorts.generator import PROMPT_PATH as BASE_PROMPT, build_request
from celeb_shorts.rules import InputReview, Issue, review_input, review_plan
from celeb_shorts.schema import Item, PlanDraft, ShortsInput

from . import catalog
from .db import OrbitDB, WaitError, now

__all__ = ["ScriptError", "product_review", "generate", "list_scripts", "save_edit", "approve",
           "HOOK_END", "REVEAL_AFTER"]

HOOK_END = 3.0
REVEAL_AFTER = 4.0
ANGLES = ("호기심형", "정보형", "가격·비교형")
ORBIT_PROMPT = BASE_PROMPT.parent / "orbit_variants.md"

#: 셀럽오르빗 분류 → 17번 규칙의 분류 (효능 표현 검사용)
_CATEGORY = {"뷰티": "뷰티", "패션": "패션", "건강식품": "건강식품",
             "라이프스타일": "기타", "디지털": "기타", "기타": "기타"}
_ORDER = {r: i for i, r in enumerate(catalog.RELATIONS)}


class ScriptError(ValueError):
    """대본 단계에서 규칙에 맞지 않을 때. 메시지는 화면에 그대로 보인다."""


# ------------------------------------------------------------ 입력 만들기
def _best_claim(db: OrbitDB, product_id: int) -> dict | None:
    """사람이 확인한 관계 중 가장 강한 것. 추정만 있으면 None."""
    claims = [c for c in catalog.list_claims(db, product_id) if c["relation"] != "추정" and c["url"]]
    return min(claims, key=lambda c: _ORDER[c["relation"]]) if claims else None


def product_review(db: OrbitDB) -> Callable[[int], tuple[InputReview, dict | None]]:
    def build(product_id: int) -> tuple[InputReview, dict | None]:
        product = catalog.get_product(db, product_id)
        claim = _best_claim(db, product_id)
        item = Item(
            name=product["name"], brand=product["brand"] or "",
            confirmed=bool(claim and claim["relation"] in ("추천확인", "사용확인")),
            price=product["price"], price_source=product["price_source"] or "",
            keyword=product["keyword"] or "", category=_CATEGORY.get(product["category"], "기타"),
        )
        data = ShortsInput(
            celebrity=claim["celebrity"] if claim else "",
            occasion=(claim["title"] or claim["kind"]) if claim else "",
            source_url=claim["open_url"] if claim else "",
            source_name=(claim["publisher"] or claim["kind"]) if claim else "",
            duration_sec=int(db.settings().get("video_seconds", "20")),
            items=[item],
        )
        return review_input(data), claim
    return build


# ------------------------------------------------------------ 셀럽오르빗 규칙
def orbit_checks(plan: PlanDraft, review: InputReview) -> list[Issue]:
    issues: list[Issue] = []
    first = plan.scenes[0]
    if first.start > 0 or first.end > HOOK_END:
        issues.append(Issue("block", "장면 1",
                            f"첫 장면(훅)은 0초에 시작해 {HOOK_END:g}초 안에 끝나야 합니다 "
                            f"(지금 {first.start:g}–{first.end:g}초). 강의 분석: 초반 3초 이탈이 가장 큽니다."))
    item = review.data.items[0]
    names = [n for n in (item.name, item.brand) if n and len(n) >= 2]
    early = [s for s in plan.scenes if s.start < REVEAL_AFTER]
    texts = [plan.hook] + [f"{s.subtitle} {s.narration}" for s in early]
    for name in names:
        if any(name in t.replace("\n", " ") for t in texts):
            issues.append(Issue("warn", "제품명 공개",
                                f"'{name}' 이(가) {REVEAL_AFTER:g}초 전에 나옵니다. 궁금증을 위해 뒤에서 공개하길 권합니다."))
            break
    return issues


def _check(draft: PlanDraft, review: InputReview) -> tuple[PlanDraft, list[Issue], list[str]]:
    plan, issues, notes = review_plan(draft, review)
    return plan, issues + orbit_checks(plan, review), notes


# ------------------------------------------------------------ 만들기
def _fake_variants(system: str, user: str, **kwargs) -> dict:
    """모의 생성 — 셀럽오르빗 규칙(3초 훅, 4초 뒤 제품명)을 지키는 예시 3안. 프롬프트는 쓰지 않는다."""
    request = json.loads(user)
    item, duration = request["items"][0], request["duration_sec"]
    who = request.get("celebrity") or ""
    seen = "방송에 나온" if request.get("relation") == "등장" else ("즐겨 쓴다는" if item["mode"] == "확인" else "이런 느낌의")
    name = f"{item['brand']} {item['name']}".strip() if item["mode"] == "확인" else f"비슷한 {item['name']}"
    price = item.get("price")
    detail = f"{price:,}원" if price else "색·질감 체크"
    hooks = ("이 조합, 어디서 봤더라?", "요즘 자주 보이는 그것", "가격 듣고 놀란 템" if price else "이렇게 쓰는 거래요")
    angles = ("호기심형", "정보형", "가격·비교형" if price else "사용법형")
    variants = []
    for angle, hook in zip(angles, hooks):
        cut = [0, 3, 5.5, 9, 13, duration]
        texts = [(hook, "text_card", None), (f"{who} {seen} 템" if who else "정체는 바로", "text_card", None),
                 (name, "product_image", 0), (detail, "product_image", 0), ("설명란에서 확인", "text_card", None)]
        scenes = [{"start": a, "end": b, "subtitle": t, "narration": t, "visual": v, "item_index": i}
                  for (a, b), (t, v, i) in zip(zip(cut, cut[1:]), texts)]
        variants.append({"angle": angle, "title": f"{who or '요즘'} {seen} {item['name']}".strip(),
                         "hook": hook, "scenes": scenes,
                         "description": f"{item['name']} 정보를 모았습니다.", "hashtags": ["#쇼츠", "#셀럽오르빗"]})
    return {"variants": variants}


def generate(db: OrbitDB, product_id: int, *, dry_run: bool, model: str = "",
             ask: Callable | None = None) -> list[int]:
    """대본 3안을 만들어 저장한다. 같은 상품의 승인 안 된 이전 안은 지운다."""
    review, claim = product_review(db)(product_id)
    if review.blocked:
        raise ScriptError(" / ".join(i.message for i in review.issues))
    request = build_request(review)
    request["relation"] = claim["relation"] if claim else "추정"
    system = BASE_PROMPT.read_text(encoding="utf-8") + ORBIT_PROMPT.read_text(encoding="utf-8")

    if dry_run:
        ask = _fake_variants
    elif ask is None:
        from shared.config import DEFAULT_MODEL
        from shared.llm import LLMError, ask as real_ask

        def ask(system, user, **kw):  # noqa: E306
            try:
                return real_ask(system, user, **kw)
            except LLMError as exc:
                if "쿼터" in str(exc):
                    raise WaitError(str(exc)) from exc
                raise
        model = model or DEFAULT_MODEL

    def call():
        return ask(system, json.dumps(request, ensure_ascii=False),
                   model=model or "dry-run", max_tokens=8000, json_mode=True)

    raw = db.run_job("대본 생성", call, {"product_id": product_id, "dry_run": dry_run})
    if raw is None:
        last = db.jobs(1)[0]
        raise ScriptError(f"대본을 만들지 못했습니다: {last['last_error']}")
    variants = raw.get("variants") if isinstance(raw, dict) else None
    if not variants:
        raise ScriptError("대본 3안 형식이 아닙니다. 다시 만들어 주세요.")

    ids = []
    with db.connect() as con:
        con.execute("DELETE FROM script WHERE product_id = ? AND approved_by = ''"
                    " AND id NOT IN (SELECT script_id FROM video)", (product_id,))
        start = (con.execute("SELECT COALESCE(MAX(variant), 0) FROM script WHERE product_id = ?",
                             (product_id,)).fetchone()[0])
        for n, body in enumerate(variants[:3], 1):
            angle = body.pop("angle", ANGLES[n - 1]) if isinstance(body, dict) else ANGLES[n - 1]
            try:
                draft = PlanDraft.model_validate(body)
            except Exception as exc:  # noqa: BLE001 — 한 안이 깨져도 나머지는 살린다
                db.log("대본 생성", f"{n}안 형식 오류: {exc}", status="실패")
                continue
            plan, issues, notes = _check(draft, review)
            payload = {"angle": angle, "dry_run": dry_run, "plan": plan.model_dump(), "notes": notes,
                       "own_comment": "", "relation": request["relation"]}
            ids.append(con.execute(
                "INSERT INTO script(product_id, variant, body_json, issues_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (product_id, start + n, json.dumps(payload, ensure_ascii=False),
                 json.dumps([i.__dict__ for i in issues], ensure_ascii=False), now())).lastrowid)
    if not ids:
        raise ScriptError("세 안 모두 형식이 맞지 않았습니다. 다시 만들어 주세요.")
    db.log("대본 생성", f"상품 #{product_id} · {len(ids)}안 · {'모의' if dry_run else '실제'}")
    return ids


# ------------------------------------------------------------ 보기·고치기·승인
def list_scripts(db: OrbitDB, product_id: int) -> list[dict]:
    with db.connect() as con:
        rows = con.execute("SELECT * FROM script WHERE product_id = ? ORDER BY id", (product_id,)).fetchall()
    out = []
    for row in rows:
        body = json.loads(row["body_json"])
        issues = json.loads(row["issues_json"] or "[]")
        out.append({**dict(row), "body": body, "plan": body["plan"], "issues": issues,
                    "blocked": any(i["level"] == "block" for i in issues)})
    return out


def _get(db: OrbitDB, script_id: int):
    with db.connect() as con:
        row = con.execute("SELECT * FROM script WHERE id = ?", (script_id,)).fetchone()
    if row is None:
        raise ScriptError("없는 대본입니다")
    return row


def save_edit(db: OrbitDB, script_id: int, form: dict[str, str]) -> list[Issue]:
    """사람이 고친 제목·후크·자막·내레이션·내 말 한 줄을 저장하고 다시 검사한다.

    고치면 승인이 풀린다(검사한 그 글이 승인된 글이어야 하므로).
    """
    row = _get(db, script_id)
    body = json.loads(row["body_json"])
    plan = body["plan"]
    plan["title"] = form.get("title", plan["title"]).strip() or plan["title"]
    plan["hook"] = form.get("hook", plan["hook"]).strip() or plan["hook"]
    plan["description"] = form.get("description", plan["description"]).strip()
    for n, scene in enumerate(plan["scenes"]):
        scene["subtitle"] = form.get(f"subtitle_{n}", scene["subtitle"]).strip() or scene["subtitle"]
        scene["narration"] = form.get(f"narration_{n}", scene["narration"]).strip()
    body["own_comment"] = form.get("own_comment", body.get("own_comment", "")).strip()

    review, _ = product_review(db)(row["product_id"])
    fixed, issues, notes = _check(PlanDraft.model_validate(plan), review)
    body["plan"], body["notes"] = fixed.model_dump(), notes
    with db.connect() as con:
        con.execute("UPDATE script SET body_json = ?, issues_json = ?, approved_by = '', approved_at = NULL WHERE id = ?",
                    (json.dumps(body, ensure_ascii=False), json.dumps([i.__dict__ for i in issues], ensure_ascii=False),
                     script_id))
    db.log("대본 수정", f"#{script_id}")
    return issues


def approve(db: OrbitDB, script_id: int, name: str) -> None:
    row = _get(db, script_id)
    body = json.loads(row["body_json"])
    issues = json.loads(row["issues_json"] or "[]")
    if not (name or "").strip():
        raise ScriptError("승인한 사람 이름을 적어 주세요")
    if body.get("dry_run"):
        raise ScriptError("모의 생성 대본은 승인할 수 없습니다. 실제 생성으로 다시 만들어 주세요")
    blocks = [i for i in issues if i["level"] == "block"]
    if blocks:
        raise ScriptError("막음이 남아 있습니다: " + " / ".join(f"[{b['where']}] {b['message']}" for b in blocks))
    if not body.get("own_comment"):
        raise ScriptError("«내 말 한 줄» 을 적어 주세요. 사람의 말이 없는 영상은 양산형으로 보일 위험이 큽니다")
    with db.connect() as con:
        con.execute("UPDATE script SET approved_by = '', approved_at = NULL WHERE product_id = ?", (row["product_id"],))
        con.execute("UPDATE script SET approved_by = ?, approved_at = ? WHERE id = ?", (name.strip(), now(), script_id))
    db.log("대본 승인", f"#{script_id} · {name.strip()}")
