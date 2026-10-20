"""⑤ 업로드 준비 — 권리·고지 검사, 사람 확인, 최종 승인②, 업로드용 제목·설명·태그.

검사는 **지금 상태**로 다시 한다. 영상을 만든 뒤에 대본을 고쳤거나, 관계를 «추정» 으로 내렸거나,
이미지·음악을 지웠다면 그 영상은 더 이상 통과하지 못한다.

막음(⛔)이 하나라도 있거나, 사람이 할 확인을 다 체크하지 않았거나, 이름이 없으면 승인되지 않는다.
승인 없이 공개되는 길은 없다. 업로드 자체는 3단계(유튜브 연결)에서 붙는다 — 지금은 파일과 문구를 받아
스튜디오에서 올린다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from celeb_shorts.disclosure import COUPANG, YOUTUBE
from celeb_shorts.output import CHANNEL_SETUP
from shared.ai_label import label_text_for
from shared.banned_phrases import check as banned_check

from . import catalog, remix, videos
from .db import OrbitDB, now

__all__ = ["Check", "PublishError", "UPLOAD_MANUAL", "run_checks", "metadata", "save_manual", "approve",
           "channel_checklist", "save_channel_checklist", "upload_text"]

#: 업로드할 때마다 사람이 스튜디오에서 직접 하는 것 — 다 체크해야 승인된다.
UPLOAD_MANUAL = (
    ("paid", "업로드 화면에서 «유료 프로모션 포함» 을 체크한다"),
    ("synthetic", "«변경되거나 합성된 콘텐츠» 를 사실대로 고른다 (AI 음성·자동 편집을 썼으면 «예»)"),
    ("kids", "시청자층: «아동용 아님»"),
    ("watch", "완성 영상을 처음부터 끝까지 소리 켜고 봤다"),
    ("link", "채널 프로필 링크(인포크 등)에 이번 상품 링크를 넣었다 — 쇼츠 설명란 링크는 눌리지 않는다"),
)

CHANNEL_KEY = "channel_checklist"
TITLE_MAX = 100          # 유튜브 제목 한도
TITLE_GOOD = 40          # 쇼츠 화면에서 잘리지 않는 길이(권장)
HASHTAG_MAX = 10


class PublishError(ValueError):
    """화면에 그대로 보일 오류."""


@dataclass
class Check:
    label: str
    level: str          # "ok" | "info" | "warn" | "block"
    detail: str = ""

    @property
    def mark(self) -> str:
        return {"ok": "✅", "info": "ℹ️", "warn": "⚠", "block": "⛔"}[self.level]


# ------------------------------------------------------------ 읽기
def _video(db: OrbitDB, video_id: int) -> dict:
    with db.connect() as con:
        row = con.execute("SELECT v.*, s.product_id, s.body_json, s.issues_json, s.approved_by AS script_ok"
                          " FROM video v JOIN script s ON s.id = v.script_id WHERE v.id = ?", (video_id,)).fetchone()
    if row is None:
        raise PublishError("없는 영상입니다")
    item = dict(row)
    item["checks"] = json.loads(item["checks_json"] or "{}")
    item["body"] = json.loads(item["body_json"])
    item["issues"] = json.loads(item["issues_json"] or "[]")
    return item


def _verified_claims(db: OrbitDB, product_id: int) -> list[dict]:
    return [c for c in catalog.list_claims(db, product_id) if c["relation"] != "추정" and c["url"]]


# ------------------------------------------------------------ 검사
def run_checks(db: OrbitDB, video_id: int) -> list[Check]:
    v = _video(db, video_id)
    plan, checks = v["body"]["plan"], v["checks"]
    out: list[Check] = []

    # 1. 대본
    if not v["script_ok"]:
        out.append(Check("대본 승인", "block", "영상을 만든 뒤 대본이 고쳐져 승인이 풀렸습니다. 대본을 다시 승인하고 영상을 다시 만드세요."))
    elif any(i["level"] == "block" for i in v["issues"]):
        out.append(Check("대본 규칙", "block", "대본에 막음이 남아 있습니다."))
    else:
        out.append(Check("대본 승인·규칙", "ok", f"{v['body'].get('angle', '')} 안"))

    # 2. 영상 파일
    path = videos.videos_dir(db) / (v["path"] or "-")
    probe = checks.get("probe") or {}
    if not path.is_file():
        out.append(Check("영상 파일", "block", "파일이 없습니다. 다시 만드세요."))
    elif (probe.get("width"), probe.get("height")) != (1080, 1920):
        out.append(Check("영상 규격", "block", f"1080×1920 이 아닙니다: {probe}"))
    else:
        total = probe["duration"] + ((checks.get("remix") or {}).get("cut_seconds") or 0)
        level = "ok" if total <= 60 else "warn"
        out.append(Check("영상 규격", level, f"1080×1920 · {probe['duration']:.1f}초"
                         + (f" (리믹스 포함 약 {total:.0f}초)" if checks.get("remix") else "")
                         + ("" if level == "ok" else " — 60초를 넘습니다. 쇼츠 길이 한도를 확인하세요")))

    # 3. 이미지 권리 — 지금도 권리 기록이 있는가
    used = videos._licensed_image(db, v["product_id"])
    if checks.get("image", "").startswith("상품 이미지"):
        if used is None:
            out.append(Check("이미지 권리", "block", "영상에 쓴 상품 이미지의 권리 기록이 지워졌습니다. 다시 만드세요."))
        else:
            asset = next(a for a in catalog.list_assets(db, v["product_id"]) if str(a["path"]) in str(used))
            own = asset["license"] in ("직접촬영", "자체제작")
            level = "ok" if asset["license_proof"] or own else "warn"
            out.append(Check("이미지 권리", level, asset["license"]
                             + (" · 증빙 없음 — 증빙을 적어 두길 권합니다" if level == "warn" else "")))
    else:
        out.append(Check("이미지 권리", "ok", "자체 그래픽 카드 (외부 이미지 없음)"))

    # 4. 음악
    music = checks.get("music", "없음")
    if music != "없음":
        mid = int(str(music).lstrip("#"))
        exists = any(m["id"] == mid for m in videos.list_music(db))
        out.append(Check("음악 라이선스", "ok" if exists else "block",
                         "라이선스 기록 있음" if exists else "음악 기록이 지워졌습니다"))
    else:
        out.append(Check("음악 라이선스", "ok", "음악 없음"))

    # 5. 음성
    out.append(Check("음성", "ok", "Google 기본 음성 (목소리 복제 없음)" if checks.get("tts", "").startswith("Google")
                     else "음성 없음 (자막만)"))

    # 6. 연예인-상품 관계 — 대본이 이름을 쓰면 지금도 확인된 관계가 있어야 한다
    text = json.dumps(plan, ensure_ascii=False)
    claims = _verified_claims(db, v["product_id"])
    named = [c for c in catalog.list_claims(db, v["product_id"]) if c["celebrity"] in text]
    if named and not any(c["celebrity"] in text for c in claims):
        out.append(Check("연예인 관계", "block", f"대본에 '{named[0]['celebrity']}' 이(가) 나오지만 지금은 확인된 관계가 없습니다."))
    elif named:
        best = next(c for c in claims if c["celebrity"] in text)
        out.append(Check("연예인 관계", "ok", f"{best['celebrity']} · {best['relation']} · {best['verified_by']} 확인"))
    else:
        out.append(Check("연예인 관계", "ok", "이름을 쓰지 않음"))

    # 7. 리믹스 원본 — 지금도 조건에 맞는가
    rmx = checks.get("remix")
    if rmx:
        claim = next((c for c in catalog.list_claims(db, v["product_id"]) if c["id"] == rmx["claim_id"]), None)
        reasons = remix.check_source(claim) if claim else ["원본 출처가 지워졌습니다"]
        out.append(Check("리믹스 원본", "block" if reasons else "ok",
                         " / ".join(reasons) if reasons else f"{rmx['timestamp']}부터 {rmx['cut_seconds']}초 · 앱에서 «잘라내기» 메뉴가 있는지 확인"))

    # 8. 고지 — 영상 안(렌더러가 늘 넣음) + 설명란(아래 metadata 가 넣음)
    out.append(Check("광고 고지", "ok", "영상 안 «광고, 제휴 링크 포함» 표시 + 설명란 첫 줄"))
    out.append(Check("AI 사용 표시", "ok", "끝 카드 «AI 음성, 자동 편집 사용» + 설명란 끝 줄"))

    # 9. 제휴 링크
    links = catalog.list_links(db, v["product_id"])
    out.append(Check("제휴 링크", "ok" if links else "warn",
                     f"{len(links)}개 — 채널 프로필 링크에 넣으세요" if links else "등록된 링크가 없습니다. 올려도 수익으로 이어지지 않습니다"))

    # 10. 업로드 문구 금지 표현
    meta = metadata(db, video_id)
    found = banned_check(meta["title"] + meta["description"])
    out.append(Check("문구 금지 표현", "block" if found else "ok", ", ".join(found) if found else "없음"))
    if len(meta["title"]) > TITLE_GOOD:
        out.append(Check("제목 길이", "warn", f"{len(meta['title'])}자 — {TITLE_GOOD}자를 넘으면 쇼츠 화면에서 잘립니다"))

    # 11. 채널 점검표 (처음 한 번)
    done = channel_checklist(db)
    left = [line for i, line in enumerate(CHANNEL_SETUP) if not done.get(str(i))]
    out.append(Check("채널 설정 점검표", "warn" if left else "ok",
                     f"{len(left)}개 남음 — 설정 화면에서 확인" if left else "모두 확인"))
    return out


# ------------------------------------------------------------ 업로드 문구
def metadata(db: OrbitDB, video_id: int) -> dict:
    """유튜브 업로드용 제목·설명·해시태그·태그. 사실(출처)·고지·AI 표시를 늘 넣는다."""
    v = _video(db, video_id)
    plan, body = v["body"]["plan"], v["body"]
    product = catalog.get_product(db, v["product_id"])
    text = json.dumps(plan, ensure_ascii=False)
    claim = next((c for c in _verified_claims(db, v["product_id"]) if c["celebrity"] in text), None)
    rmx = v["checks"].get("remix")
    settings = db.settings()

    title = plan["title"].replace("\n", " ").strip()[:TITLE_MAX]
    tags_seen, hashtags = set(), []
    for tag in list(plan.get("hashtags", [])) + [f"#{settings['channel_name']}", "#Shorts"]:
        tag = "#" + tag.lstrip("#").replace(" ", "")
        if tag.lower() not in tags_seen and len(tag) > 1:
            tags_seen.add(tag.lower())
            hashtags.append(tag)
    hashtags = hashtags[:HASHTAG_MAX]

    lines = [YOUTUBE, COUPANG, "", plan.get("description", "").strip()]
    if body.get("own_comment"):
        lines += ["", f"{settings['channel_name']} 한마디: {body['own_comment']}"]
    if claim:
        lines += ["", f"출처: {claim['celebrity']} — {claim['title'] or claim['kind']} {claim['open_url']}"]
    if rmx:
        lines += ["앞부분은 유튜브 리믹스(잘라내기)로 원본을 인용했습니다. 원본 링크는 영상 위에 자동으로 표시됩니다."]
    lines += ["", "※ 소개한 상품은 영상 속 제품과 같은 제품이 아닐 수 있습니다. 구매 전 상품 정보를 확인하세요.",
              "상품 링크는 채널 프로필 링크에서 확인하세요.", "", " ".join(hashtags), "", label_text_for("ko")]
    description = "\n".join(line for line in lines if line is not None).strip()

    tags = [t for t in (product["name"], product["brand"], product["category"], product["keyword"],
                        claim["celebrity"] if claim else "", settings["channel_name"], "쇼핑쇼츠") if t]
    tags = list(dict.fromkeys(tags))
    links = [dict(l) for l in catalog.list_links(db, v["product_id"])]
    return {"title": title, "description": description, "hashtags": hashtags, "tags": tags, "links": links}


def upload_text(db: OrbitDB, video_id: int) -> str:
    meta = metadata(db, video_id)
    link_lines = [f"- {l['platform']}: {l['url']}" for l in meta["links"]] or ["- (등록된 링크 없음)"]
    return "\n".join([
        "[제목]", meta["title"], "", "[설명]", meta["description"], "",
        "[태그]", ", ".join(meta["tags"]), "", "[채널 프로필 링크에 넣을 상품 링크]", *link_lines, "",
        "[업로드 화면에서 직접]", *[f"- {label}" for _, label in UPLOAD_MANUAL],
    ])


# ------------------------------------------------------------ 사람 확인·승인
def save_manual(db: OrbitDB, video_id: int, checked: set[str]) -> None:
    v = _video(db, video_id)
    checks = v["checks"]
    checks["manual"] = sorted(k for k, _ in UPLOAD_MANUAL if k in checked)
    with db.connect() as con:
        con.execute("UPDATE video SET checks_json = ? WHERE id = ?", (json.dumps(checks, ensure_ascii=False), video_id))


def approve(db: OrbitDB, video_id: int, name: str) -> list[Check]:
    if not (name or "").strip():
        raise PublishError("승인한 사람 이름을 적어 주세요")
    results = run_checks(db, video_id)
    blocks = [c for c in results if c.level == "block"]
    if blocks:
        with db.connect() as con:
            con.execute("UPDATE video SET status = '검사실패' WHERE id = ?", (video_id,))
        raise PublishError("막음이 있어 승인할 수 없습니다: " + " / ".join(f"{c.label} — {c.detail}" for c in blocks))
    done = set(_video(db, video_id)["checks"].get("manual", []))
    left = [label for key, label in UPLOAD_MANUAL if key not in done]
    if left:
        raise PublishError("업로드 화면에서 직접 할 일을 모두 체크해 주세요: " + " / ".join(left))
    with db.connect() as con:
        con.execute("UPDATE video SET status = '승인됨', approved_by = ?, approved_at = ? WHERE id = ?",
                    (name.strip(), now(), video_id))
    db.log("영상 승인", f"#{video_id} · {name.strip()}")
    return results


# ------------------------------------------------------------ 채널 점검표
def channel_checklist(db: OrbitDB) -> dict:
    with db.connect() as con:
        row = con.execute("SELECT value FROM setting WHERE key = ?", (CHANNEL_KEY,)).fetchone()
    return json.loads(row["value"]) if row else {}


def save_channel_checklist(db: OrbitDB, checked: set[str]) -> None:
    value = {str(i): str(i) in checked for i in range(len(CHANNEL_SETUP))}
    with db.connect() as con:
        con.execute("INSERT INTO setting(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (CHANNEL_KEY, json.dumps(value)))
    db.log("채널 점검표", f"{sum(value.values())}/{len(value)} 확인")
