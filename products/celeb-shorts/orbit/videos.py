"""④ 영상 만들기 — 승인된 대본만 받는다. 결과는 video 표와 data/videos/ 에 남는다.

음악은 라이선스 기록이 있는 파일만, 상품 이미지도 라이선스 기록이 있는 것만 쓴다.
권리가 맞는 이미지가 없으면 렌더러가 «자체 그래픽 카드» 로 대신한다(설계 8장).
"""

from __future__ import annotations

import json
from pathlib import Path

from . import catalog, remix, render, tts
from .db import OrbitDB, now

__all__ = ["VideoError", "MUSIC_TYPES", "add_music", "list_music", "make_job", "make_video", "list_videos",
           "videos_dir"]

MUSIC_TYPES = {".mp3", ".m4a", ".wav", ".ogg"}
MAX_MUSIC_BYTES = 20 * 1024 * 1024
#: 영상에 써도 되는 이미지 권리 — 증빙이 필요한 '브랜드허락' 은 등록 때 이미 증빙을 받았다.
IMAGE_OK = {"직접촬영", "브랜드허락", "제휴제공", "무료라이선스", "자체제작"}


class VideoError(ValueError):
    """화면에 그대로 보일 오류."""


def videos_dir(db: OrbitDB) -> Path:
    return db.path.parent / "videos"


# ------------------------------------------------------------ 음악
def add_music(db: OrbitDB, *, filename: str, data: bytes, license: str, license_proof: str) -> int:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in MUSIC_TYPES:
        raise VideoError("mp3 · m4a · wav · ogg 만 올릴 수 있습니다")
    if not data or len(data) > MAX_MUSIC_BYTES:
        raise VideoError("음악 파일은 1바이트~20MB 입니다")
    if license not in ("무료라이선스", "자체제작"):
        raise VideoError("음악 권리를 골라 주세요 (무료 라이선스 / 직접 만든 음악)")
    if license == "무료라이선스" and not (license_proof or "").strip():
        raise VideoError("무료 라이선스 음악은 곡 주소나 라이선스 조건(출처 표기 필요 여부 등)을 적어 주세요")
    folder = catalog.assets_dir(db) / "music"
    folder.mkdir(parents=True, exist_ok=True)
    with db.connect() as con:
        asset_id = con.execute("INSERT INTO asset(product_id, path, kind, license, license_proof, added_at)"
                               " VALUES (NULL, '', 'music', ?, ?, ?)", (license, license_proof.strip(), now())).lastrowid
        relative = f"music/{asset_id}{suffix}"
        (catalog.assets_dir(db) / relative).write_bytes(data)
        con.execute("UPDATE asset SET path = ? WHERE id = ?", (relative, asset_id))
    db.log("음악 등록", f"#{asset_id} · {license} · {Path(filename).name}")
    return asset_id


def list_music(db: OrbitDB):
    with db.connect() as con:
        return con.execute("SELECT * FROM asset WHERE kind = 'music' ORDER BY id").fetchall()


# ------------------------------------------------------------ 영상
def _approved_script(db: OrbitDB, script_id: int) -> dict:
    with db.connect() as con:
        row = con.execute("SELECT * FROM script WHERE id = ?", (script_id,)).fetchone()
    if row is None:
        raise VideoError("없는 대본입니다")
    if not row["approved_by"]:
        raise VideoError("승인한 대본만 영상으로 만들 수 있습니다")
    return dict(row)


def _licensed_image(db: OrbitDB, product_id: int) -> Path | None:
    for asset in catalog.list_assets(db, product_id):
        if asset["kind"] == "image" and asset["license"] in IMAGE_OK:
            path = catalog.assets_dir(db) / asset["path"]
            if path.is_file():
                return path
    return None


def make_job(db: OrbitDB, script_id: int, template: str) -> render.RenderJob:
    script = _approved_script(db, script_id)
    body = json.loads(script["body_json"])
    product = catalog.get_product(db, script["product_id"])
    if template not in render.load_templates()["templates"]:
        raise VideoError("없는 템플릿입니다")
    return render.RenderJob(plan=body["plan"], template=template, settings=db.settings(),
                            product_name=product["name"], product_image=_licensed_image(db, product["id"]),
                            own_comment=body.get("own_comment", ""), seed=script_id * 31 + 7)


def make_video(db: OrbitDB, script_id: int, template: str, *, music_id: int | None = None,
               use_tts: bool = False, remix_claim_id: int | None = None, cut_seconds: int = remix.CUT_MAX) -> int:
    """영상을 만든다. `remix_claim_id` 를 주면 «리믹스 연결형» — 유튜브 앱에서 원본 1~5초를 앞에 붙일 영상."""
    job = make_job(db, script_id, template)
    remix_info = None
    if remix_claim_id:
        if not remix.CUT_MIN <= int(cut_seconds) <= remix.CUT_MAX:
            raise VideoError(f"잘라내기는 {remix.CUT_MIN}~{remix.CUT_MAX}초입니다")
        with db.connect() as con:
            product_id = con.execute("SELECT product_id FROM script WHERE id = ?", (script_id,)).fetchone()[0]
        try:
            src = remix.get_source(db, product_id, int(remix_claim_id))
        except remix.RemixError as exc:
            raise VideoError(str(exc)) from exc
        remix_info = {"claim_id": src["id"], "url": src["url"], "open_url": src["open_url"],
                      "timestamp": src["timestamp"], "cut_seconds": int(cut_seconds),
                      "celebrity": src["celebrity"], "video_id": remix.youtube_id(src["url"])}
    render.find_ffmpeg()          # 없으면 기록 전에 바로 알린다(다시 시도해도 소용없으므로)
    if use_tts and not tts.available():
        raise VideoError("GOOGLE_TTS_API_KEY 가 없어 음성을 만들 수 없습니다. 음성 없이 만들거나 .env 에 키를 넣으세요")
    music = None
    if music_id:
        with db.connect() as con:
            row = con.execute("SELECT * FROM asset WHERE id = ? AND kind = 'music'", (music_id,)).fetchone()
        if row is None:
            raise VideoError("없는 음악입니다")
        music = catalog.assets_dir(db) / row["path"]
    with db.connect() as con:
        video_id = con.execute("INSERT INTO video(script_id, template, status, created_at) VALUES (?, ?, '렌더됨', ?)",
                               (script_id, template, now())).lastrowid
    out = videos_dir(db) / f"{video_id}.mp4"
    checks = {"image": "상품 이미지(권리 기록 있음)" if job.product_image else "자체 그래픽 카드(쓸 수 있는 이미지 없음)",
              "music": f"#{music_id}" if music else "없음", "tts": "Google TTS" if use_tts else "없음(자막만)",
              "remix": remix_info}

    def work():
        voices = []
        if use_tts:
            for n, scene in enumerate(job.plan["scenes"]):
                text = (scene.get("narration") or "").strip()
                if text:
                    voices.append((tts.synthesize(text, videos_dir(db) / f"{video_id}-voice-{n}.mp3"), scene["start"]))
        render.render_video(job, out, music=music, voices=voices)
        return render.probe(out)

    info = db.run_job("영상 렌더", work, {"script_id": script_id, "template": template})
    if info is None:
        with db.connect() as con:
            con.execute("DELETE FROM video WHERE id = ?", (video_id,))
        raise VideoError(f"영상을 만들지 못했습니다: {db.jobs(1)[0]['last_error']}")
    checks["probe"] = info
    with db.connect() as con:
        con.execute("UPDATE video SET path = ?, duration = ?, checks_json = ? WHERE id = ?",
                    (f"{video_id}.mp4", info["duration"], json.dumps(checks, ensure_ascii=False), video_id))
    db.log("영상 렌더", f"#{video_id} · {template} · {info['duration']:.1f}초")
    return video_id


def list_videos(db: OrbitDB, product_id: int) -> list[dict]:
    with db.connect() as con:
        rows = con.execute("SELECT v.* FROM video v JOIN script s ON s.id = v.script_id WHERE s.product_id = ?"
                           " ORDER BY v.id DESC", (product_id,)).fetchall()
    out = []
    for r in rows:
        checks = json.loads(r["checks_json"] or "{}")
        item = {**dict(r), "checks": checks}
        if checks.get("remix"):
            item["remix_steps"] = remix.steps(checks["remix"])
            item["total_seconds"] = (r["duration"] or 0) + checks["remix"]["cut_seconds"]
        out.append(item)
    return out
