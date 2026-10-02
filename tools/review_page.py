"""검토 문서(아티팩트) 빌드 도구 — 적은 사용량으로.

사진을 본문에 base64 로 박지 않고 `img/*.jpg` 파일로 따로 둔다. 아티팩트에 한 번
올린 파일은 다음 publish 에서 빼도 남으므로, 회차마다 **새 사진과 페이지(수십 KB)만**
올리면 된다. 예전에는 사진 23장이 박힌 2MB 를 매번 통째로 다시 올렸다.

폴더 구조 (작업 폴더는 scratchpad 에 둔다 — 캡처 이미지는 이 공개 저장소에 커밋하지 않는다)

    <폴더>/page.html         틀: <head>·스타일·머리말 + <!--ROUNDS--> 자리 + 꼬리
    <폴더>/rounds/NN-*.html  회차 조각. 파일 이름 순서. 맨 뒤 것만 펼치고 나머지는 접는다
    <폴더>/img/*.jpg         사진 (조각에서 src="img/이름.jpg")

쓰는 법

    python tools/review_page.py img  <폴더> 캡처.png [이름]   # PNG → img/이름.jpg (820px, q72)
    python tools/review_page.py build <폴더>                   # → <폴더>/index.html + files 목록

build 가 찍어 주는 `files` 를 Artifact publish 에 넘긴다. 이미 올린 사진은 빼고 새 것만.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

자리 = "<!--ROUNDS-->"
접기스타일 = """<style>
details.past{border:1px solid var(--line,#e3e6ec);border-radius:10px;margin:14px 0;padding:0 14px}
details.past>summary{cursor:pointer;padding:12px 0;font-weight:700;list-style-position:inside}
details.past[open]>summary{border-bottom:1px solid var(--line,#e3e6ec);margin-bottom:8px}
</style>"""


def 제목(조각: str, 파일: Path) -> str:
    m = re.search(r"<!--\s*title:\s*(.+?)\s*-->", 조각) or re.search(r"<h2[^>]*>(.*?)</h2>", 조각, re.S)
    return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else 파일.stem


def build(폴더: Path, 펼칠수: int = 1) -> Path:
    틀 = (폴더 / "page.html").read_text(encoding="utf-8")
    if 자리 not in 틀:
        sys.exit(f"page.html 에 {자리} 자리가 없습니다.")
    조각들 = sorted((폴더 / "rounds").glob("*.html"))
    본문 = []
    for i, f in enumerate(조각들):
        글 = f.read_text(encoding="utf-8")
        if i >= len(조각들) - 펼칠수:
            본문.append(글)
        else:
            본문.append(f'<details class="past"><summary>{제목(글, f)}</summary>\n{글}\n</details>')
    html = 틀.replace(자리, "\n".join(본문)).replace("</head>", 접기스타일 + "</head>", 1)
    if "</head>" not in 틀:
        html = 접기스타일 + html
    쓴사진 = sorted(set(re.findall(r'src="(img/[^"]+)"', html)))
    없는것 = [p for p in 쓴사진 if not (폴더 / p).exists()]
    if 없는것:
        sys.exit(f"사진 파일이 없습니다: {없는것}")
    if "base64," in html:
        print("⚠ 본문에 base64 사진이 남아 있습니다 — img/ 파일로 빼세요.")
    out = 폴더 / "index.html"
    out.write_text(html, encoding="utf-8")
    사진합 = sum((폴더 / p).stat().st_size for p in 쓴사진)
    print(f"페이지 {out.stat().st_size // 1024}KB · 사진 {len(쓴사진)}장 {사진합 // 1024}KB (따로 올림)")
    print("files =", json.dumps({p: str(폴더 / p) for p in 쓴사진}, ensure_ascii=False))
    return out


def img(폴더: Path, 원본: Path, 이름: str | None = None, 폭: int = 820, 품질: int = 72) -> Path:
    from PIL import Image

    im = Image.open(원본).convert("RGB")
    if im.width > 폭 * 2:          # 고해상도 캡처(2배)는 2배 폭까지만
        im = im.resize((폭 * 2, round(im.height * 폭 * 2 / im.width)))
    (폴더 / "img").mkdir(parents=True, exist_ok=True)
    out = 폴더 / "img" / f"{이름 or 원본.stem}.jpg"
    im.save(out, "JPEG", quality=품질, optimize=True)
    print(f"{out} {out.stat().st_size // 1024}KB")
    return out


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "build":
        build(Path(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    elif len(sys.argv) >= 4 and sys.argv[1] == "img":
        img(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else None)
    else:
        print(__doc__)
