"""② 상품 · 출처 · 검증 · 제휴 링크 · 이미지 라이선스.

규칙은 화면이 아니라 여기서 지킨다(화면을 거치지 않는 호출도 같은 규칙을 받게).

- 관계(claim)는 처음엔 늘 «추정». 확인 단계로 올리려면 **확인한 사람 이름과 출처**가 있어야 한다.
- 출처가 «연예인 본인 영상» 이면 **그 시간(분:초)** 을 적어야 한다. 영상은 받지 않고 링크만 둔다.
- 제휴 링크는 사람이 붙여 넣은 것만 받는다(`created_by_api=0`). 쿠팡파트너스는 쿠팡 주소만.
- 이미지는 라이선스 종류를 고르지 않으면 저장하지 않는다. 증빙이 없으면 «증빙 없음» 으로 표시.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .db import OrbitDB, now

__all__ = [
    "CatalogError", "CATEGORIES", "SOURCE_KINDS", "RELATIONS", "LICENSES", "PLATFORMS", "IMAGE_TYPES",
    "add_product", "update_product", "list_products", "get_product",
    "add_claim", "verify_claim", "list_claims",
    "add_link", "delete_link", "list_links", "add_image", "delete_asset", "list_assets", "assets_dir",
    "parse_timestamp", "timed_url",
]

CATEGORIES = ("뷰티", "패션", "라이프스타일", "디지털", "건강식품", "기타")
SOURCE_KINDS = ("연예인 본인 영상", "기사", "공식SNS", "브랜드", "방송정보", "기타")
#: 신뢰도 높은 순. '추정' 은 사람이 확인하기 전 기본값.
RELATIONS = ("추천확인", "사용확인", "등장", "추정")
RELATION_HELP = {
    "추천확인": "연예인이 직접 좋다고·쓴다고 말한 것이 출처에 있다",
    "사용확인": "쓰는 모습이 출처에서 확인된다 (말은 없음)",
    "등장": "방송·SNS 화면에 나온다 (쓴다는 근거는 없음)",
    "추정": "아직 확인하지 않음 — 영상에서 이름을 쓸 수 없다",
}
LICENSES = ("직접촬영", "브랜드허락", "제휴제공", "무료라이선스", "자체제작")
PLATFORMS = ("쿠팡파트너스", "기타")
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024

_URL = re.compile(r"^https?://[^\s]+$")
_TS = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")
_COUPANG_HOSTS = ("coupang.com", "coupa.ng")


class CatalogError(ValueError):
    """입력이 규칙에 맞지 않을 때. 메시지는 화면에 그대로 보인다."""


# ------------------------------------------------------------ 도우미
def _url(value: str, what: str = "주소") -> str:
    value = (value or "").strip()
    if not _URL.match(value):
        raise CatalogError(f"{what}는 http:// 나 https:// 로 시작해야 합니다")
    return value


def parse_timestamp(value: str) -> int:
    """`1:47` / `01:02:03` → 초. 틀리면 CatalogError."""
    match = _TS.match((value or "").strip())
    if not match:
        raise CatalogError("시간은 분:초 (예: 1:47) 또는 시:분:초 로 적어 주세요")
    hours, minutes, seconds = int(match.group(1) or 0), int(match.group(2)), int(match.group(3))
    if seconds >= 60 or (match.group(1) and minutes >= 60):
        raise CatalogError("시간 형식이 맞지 않습니다")
    return hours * 3600 + minutes * 60 + seconds


def timed_url(url: str, timestamp: str) -> str:
    """유튜브 주소면 그 시간에서 열리게 `t=` 를 붙인다. 다른 주소는 그대로."""
    if not timestamp:
        return url
    parts = urlparse(url)
    if not any(host in parts.netloc for host in ("youtube.com", "youtu.be")):
        return url
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "t"] + [("t", f"{parse_timestamp(timestamp)}s")]
    return urlunparse(parts._replace(query=urlencode(query)))


def _price(price: str, source: str) -> tuple[int | None, str]:
    digits = re.sub(r"[^\d]", "", price or "")
    source = (source or "").strip()
    if not digits:
        return None, ""
    if not source:
        raise CatalogError("가격을 적으면 가격을 본 곳(가격 출처)도 적어 주세요")
    return int(digits), source


# ------------------------------------------------------------ 상품
def add_product(db: OrbitDB, *, name: str, brand: str = "", model: str = "", category: str = "기타",
                price: str = "", price_source: str = "", keyword: str = "") -> int:
    name = (name or "").strip()
    if not name:
        raise CatalogError("상품 이름을 적어 주세요")
    if category not in CATEGORIES:
        raise CatalogError(f"분류는 {', '.join(CATEGORIES)} 중 하나입니다")
    value, source = _price(price, price_source)
    with db.connect() as con:
        product_id = con.execute(
            "INSERT INTO product(name, brand, model, category, price, price_source, price_checked_at, keyword, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, brand.strip(), model.strip(), category, value, source, now() if value else None,
             keyword.strip(), now())).lastrowid
    db.log("상품 등록", f"#{product_id} {name}")
    return product_id


def update_product(db: OrbitDB, product_id: int, *, name: str, brand: str = "", model: str = "",
                   category: str = "기타", price: str = "", price_source: str = "", keyword: str = "",
                   available: str = "") -> None:
    if not (name or "").strip():
        raise CatalogError("상품 이름을 적어 주세요")
    if category not in CATEGORIES:
        raise CatalogError(f"분류는 {', '.join(CATEGORIES)} 중 하나입니다")
    value, source = _price(price, price_source)
    avail = {"판매중": 1, "품절": 0}.get(available)
    with db.connect() as con:
        con.execute("UPDATE product SET name=?, brand=?, model=?, category=?, price=?, price_source=?,"
                    " price_checked_at=COALESCE(?, price_checked_at), keyword=?, available=? WHERE id=?",
                    (name.strip(), brand.strip(), model.strip(), category, value, source,
                     now() if value else None, keyword.strip(), avail, product_id))
    db.log("상품 수정", f"#{product_id}")


def get_product(db: OrbitDB, product_id: int) -> sqlite3.Row:
    with db.connect() as con:
        row = con.execute("SELECT * FROM product WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        raise CatalogError("없는 상품입니다")
    return row


def list_products(db: OrbitDB) -> list[dict]:
    """목록용 — 상품마다 가장 강한 관계, 링크 수, 이미지 수."""
    order = {r: i for i, r in enumerate(RELATIONS)}
    with db.connect() as con:
        products = con.execute("SELECT * FROM product ORDER BY id DESC").fetchall()
        rows = []
        for p in products:
            relations = [r[0] for r in con.execute("SELECT relation FROM claim WHERE product_id = ?", (p["id"],))]
            celebs = [r[0] for r in con.execute(
                "SELECT DISTINCT c.name FROM claim k JOIN celebrity c ON c.id = k.celebrity_id WHERE k.product_id = ?",
                (p["id"],))]
            rows.append({
                **dict(p),
                "best": min(relations, key=order.get) if relations else "",
                "celebs": celebs,
                "links": con.execute("SELECT COUNT(*) FROM affiliate_link WHERE product_id = ?", (p["id"],)).fetchone()[0],
                "images": con.execute("SELECT COUNT(*) FROM asset WHERE product_id = ? AND kind = 'image'",
                                      (p["id"],)).fetchone()[0],
            })
    return rows


# ------------------------------------------------------------ 출처·관계
def add_claim(db: OrbitDB, product_id: int, *, celebrity: str, url: str = "", title: str = "",
              publisher: str = "", published_at: str = "", kind: str = "기사", timestamp: str = "",
              note: str = "") -> int:
    """연예인-상품 관계를 «추정» 으로 등록한다. 출처를 함께 적으면 출처도 만든다."""
    get_product(db, product_id)
    celebrity = (celebrity or "").strip()
    if not celebrity:
        raise CatalogError("연예인 이름을 적어 주세요")
    source_id = None
    if (url or "").strip():
        url = _url(url, "출처 주소")
        if kind not in SOURCE_KINDS:
            raise CatalogError(f"출처 종류는 {', '.join(SOURCE_KINDS)} 중 하나입니다")
        timestamp = (timestamp or "").strip()
        if kind == "연예인 본인 영상" and not timestamp:
            raise CatalogError("연예인 본인 영상은 상품 이야기가 나오는 시간(예: 1:47)을 적어 주세요")
        if timestamp:
            parse_timestamp(timestamp)
    with db.connect() as con:
        con.execute("INSERT OR IGNORE INTO celebrity(name) VALUES (?)", (celebrity,))
        celeb_id = con.execute("SELECT id FROM celebrity WHERE name = ?", (celebrity,)).fetchone()[0]
        if url:
            source_id = con.execute(
                "INSERT INTO source(url, title, publisher, published_at, kind, timestamp, added_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (url, title.strip(), publisher.strip(), published_at.strip() or None, kind, timestamp, now())).lastrowid
        claim_id = con.execute("INSERT INTO claim(celebrity_id, product_id, source_id, note) VALUES (?, ?, ?, ?)",
                               (celeb_id, product_id, source_id, note.strip())).lastrowid
    db.log("관계 등록", f"상품 #{product_id} · {celebrity} · 추정")
    return claim_id


def verify_claim(db: OrbitDB, claim_id: int, *, relation: str, verified_by: str) -> None:
    """사람이 출처를 열어 본 뒤 관계를 정한다. '추정' 으로 되돌리는 것은 이름 없이도 된다."""
    if relation not in RELATIONS:
        raise CatalogError(f"관계는 {', '.join(RELATIONS)} 중 하나입니다")
    with db.connect() as con:
        claim = con.execute("SELECT * FROM claim WHERE id = ?", (claim_id,)).fetchone()
        if claim is None:
            raise CatalogError("없는 관계입니다")
        if relation == "추정":
            con.execute("UPDATE claim SET relation='추정', verified_by='', verified_at=NULL WHERE id=?", (claim_id,))
        else:
            if not (verified_by or "").strip():
                raise CatalogError("확인한 사람 이름을 적어 주세요. 누가 출처를 열어 봤는지 남겨야 합니다")
            if claim["source_id"] is None:
                raise CatalogError("출처가 없는 관계는 확인할 수 없습니다. 출처를 넣어 새로 등록하세요")
            con.execute("UPDATE claim SET relation=?, verified_by=?, verified_at=? WHERE id=?",
                        (relation, verified_by.strip(), now(), claim_id))
    db.log("관계 확인", f"#{claim_id} → {relation}")


def list_claims(db: OrbitDB, product_id: int) -> list[dict]:
    with db.connect() as con:
        rows = con.execute(
            "SELECT k.*, c.name AS celebrity, s.url, s.title, s.publisher, s.published_at, s.kind, s.timestamp"
            " FROM claim k JOIN celebrity c ON c.id = k.celebrity_id LEFT JOIN source s ON s.id = k.source_id"
            " WHERE k.product_id = ? ORDER BY k.id", (product_id,)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["open_url"] = timed_url(row["url"], row["timestamp"] or "") if row["url"] else ""
        out.append(item)
    return out


# ------------------------------------------------------------ 제휴 링크
def add_link(db: OrbitDB, product_id: int, *, platform: str, url: str, added_by: str) -> int:
    get_product(db, product_id)
    if platform not in PLATFORMS:
        raise CatalogError(f"플랫폼은 {', '.join(PLATFORMS)} 중 하나입니다")
    url = _url(url, "제휴 링크")
    if platform == "쿠팡파트너스" and not any(h in urlparse(url).netloc for h in _COUPANG_HOSTS):
        raise CatalogError("쿠팡파트너스 링크는 쿠팡 주소(link.coupang.com, coupa.ng 등)여야 합니다. "
                           "파트너스 사이트에서 만든 링크를 그대로 붙여 넣으세요")
    if not (added_by or "").strip():
        raise CatalogError("링크를 붙여 넣은 사람 이름을 적어 주세요")
    with db.connect() as con:
        link_id = con.execute("INSERT INTO affiliate_link(product_id, platform, url, added_by, created_by_api, added_at)"
                              " VALUES (?, ?, ?, ?, 0, ?)", (product_id, platform, url, added_by.strip(), now())).lastrowid
    db.log("제휴 링크", f"상품 #{product_id} · {platform}")
    return link_id


def delete_link(db: OrbitDB, link_id: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM affiliate_link WHERE id = ?", (link_id,))
    db.log("제휴 링크 삭제", f"#{link_id}")


def list_links(db: OrbitDB, product_id: int) -> list[sqlite3.Row]:
    with db.connect() as con:
        return con.execute("SELECT * FROM affiliate_link WHERE product_id = ? ORDER BY id", (product_id,)).fetchall()


# ------------------------------------------------------------ 이미지·라이선스
def assets_dir(db: OrbitDB) -> Path:
    return db.path.parent / "assets"


def add_image(db: OrbitDB, product_id: int, *, filename: str, data: bytes, license: str,
              license_proof: str = "") -> int:
    get_product(db, product_id)
    if license not in LICENSES:
        raise CatalogError("이미지 권리를 골라 주세요. 권리를 모르는 이미지는 쓸 수 없습니다")
    suffix = Path(filename or "").suffix.lower()
    if suffix not in IMAGE_TYPES:
        raise CatalogError("jpg · png · webp 이미지만 올릴 수 있습니다")
    if not data:
        raise CatalogError("빈 파일입니다")
    if len(data) > MAX_IMAGE_BYTES:
        raise CatalogError("이미지는 10MB 까지입니다")
    if license == "브랜드허락" and not (license_proof or "").strip():
        raise CatalogError("브랜드 허락이면 허락받은 근거(메일 날짜·담당자 등)를 적어 주세요")
    folder = assets_dir(db) / str(product_id)
    folder.mkdir(parents=True, exist_ok=True)
    with db.connect() as con:
        asset_id = con.execute("INSERT INTO asset(product_id, path, kind, license, license_proof, added_at)"
                               " VALUES (?, '', 'image', ?, ?, ?)",
                               (product_id, license, license_proof.strip(), now())).lastrowid
        relative = f"{product_id}/{asset_id}{suffix}"
        (assets_dir(db) / relative).write_bytes(data)
        con.execute("UPDATE asset SET path = ? WHERE id = ?", (relative, asset_id))
    db.log("이미지 등록", f"상품 #{product_id} · {license}")
    return asset_id


def list_assets(db: OrbitDB, product_id: int) -> list[sqlite3.Row]:
    with db.connect() as con:
        return con.execute("SELECT * FROM asset WHERE product_id = ? ORDER BY id", (product_id,)).fetchall()


def delete_asset(db: OrbitDB, asset_id: int) -> None:
    with db.connect() as con:
        row = con.execute("SELECT path FROM asset WHERE id = ?", (asset_id,)).fetchone()
        con.execute("DELETE FROM asset WHERE id = ?", (asset_id,))
    if row and row["path"]:
        (assets_dir(db) / row["path"]).unlink(missing_ok=True)
    db.log("이미지 삭제", f"#{asset_id}")
