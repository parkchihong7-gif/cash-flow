"""리믹스 연결형 — 유튜브 공식 «잘라내기(Cut)» 로 원본 1~5초를 앞에 붙이는 쇼츠.

리믹스는 **유튜브 앱 안에서만** 한다. 이 프로그램은 원본을 내려받지 않고,
그 뒤에 붙을 셀럽오르빗 영상을 만들고, 원본이 리믹스에 맞는지 검사하고, 앱에서 따라 할 순서를 적어 준다.

유튜브 안내 기준(2026-10 확인): 다른 유튜브 영상·쇼츠에서 1~5초 사용, 원본 링크가 자동으로 붙는다.
원작자가 리믹스를 꺼 둔 영상, 음원 파트너의 뮤직비디오는 안 된다. 유튜브 영상만 된다(틱톡 등은 불가).

리믹스로 저작권 허락은 해결되지만, 연예인 얼굴을 상품 판매에 쓰는 문제(퍼블리시티권)는 남을 수 있다.
그래서 원본은 **연예인 본인 채널에서 본인이 그 제품을 이야기하는 장면**으로만 받는다 — 사실을 보여 주는 용도.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from . import catalog
from .db import OrbitDB

__all__ = ["RemixError", "CUT_MIN", "CUT_MAX", "youtube_id", "remix_sources", "check_source", "steps"]

CUT_MIN, CUT_MAX = 1, 5


class RemixError(ValueError):
    """리믹스 원본으로 쓸 수 없을 때. 메시지는 화면에 그대로 보인다."""


def youtube_id(url: str) -> str:
    """유튜브 영상·쇼츠 주소에서 영상 ID. 유튜브가 아니면 빈 문자열."""
    parts = urlparse(url or "")
    host = parts.netloc.lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        return parts.path.strip("/").split("/")[0]
    if host in ("youtube.com", "music.youtube.com"):
        if parts.path == "/watch":
            return parse_qs(parts.query).get("v", [""])[0]
        for prefix in ("/shorts/", "/live/", "/embed/"):
            if parts.path.startswith(prefix):
                return parts.path[len(prefix):].split("/")[0]
    return ""


def check_source(claim: dict) -> list[str]:
    """이 관계(출처)를 리믹스 원본으로 쓸 수 없는 이유 목록. 비면 쓸 수 있다."""
    reasons = []
    if not youtube_id(claim.get("url") or ""):
        reasons.append("유튜브 영상이 아닙니다 (리믹스는 유튜브 영상·쇼츠만 됩니다)")
    if claim.get("kind") != "연예인 본인 영상":
        reasons.append("연예인 본인 채널 영상이 아닙니다 (재업로드·남의 채널은 쓰지 않습니다)")
    if not claim.get("timestamp"):
        reasons.append("제품 이야기가 나오는 시간이 없습니다")
    if claim.get("relation") not in ("추천확인", "사용확인"):
        reasons.append("사람이 출처를 열어 '추천확인' 또는 '사용확인' 으로 확인하지 않았습니다")
    return reasons


def remix_sources(db: OrbitDB, product_id: int) -> tuple[list[dict], list[tuple[dict, list[str]]]]:
    """(쓸 수 있는 원본, [(못 쓰는 원본, 이유)])."""
    ok, bad = [], []
    for claim in catalog.list_claims(db, product_id):
        if not claim.get("url"):
            continue
        reasons = check_source(claim)
        (bad.append((claim, reasons)) if reasons else ok.append(claim))
    return ok, bad


def get_source(db: OrbitDB, product_id: int, claim_id: int) -> dict:
    for claim in catalog.list_claims(db, product_id):
        if claim["id"] == claim_id:
            reasons = check_source(claim)
            if reasons:
                raise RemixError("리믹스 원본으로 쓸 수 없습니다: " + " / ".join(reasons))
            return claim
    raise RemixError("이 상품의 출처가 아닙니다")


def steps(remix: dict) -> list[str]:
    """유튜브 앱에서 따라 할 순서. `remix` 는 영상 기록에 남긴 리믹스 정보."""
    start = remix["timestamp"]
    cut = remix["cut_seconds"]
    return [
        "휴대폰에 이 프로그램이 만든 mp4 를 옮겨 둡니다 (아래 «mp4 받기»).",
        f"유튜브 앱에서 원본 영상을 엽니다: {remix['open_url']}",
        "영상 아래 «리믹스» → «잘라내기» 를 누릅니다. 이 메뉴가 없으면 원작자가 리믹스를 막아 둔 영상입니다 — 이 원본은 쓰지 마세요.",
        f"{start} 부터 {cut}초를 고릅니다 (본인이 제품을 이야기하는 부분만, 1~5초).",
        "다음 화면에서 직접 찍는 대신 갤러리에서 받아 둔 mp4 를 붙입니다 (메뉴 이름은 앱 버전에 따라 조금 다를 수 있습니다).",
        "제목·설명은 이 프로그램의 업로드용 문구를 쓰고, «유료 프로모션 포함» 을 체크합니다. 원본 링크는 유튜브가 자동으로 붙입니다.",
    ]
