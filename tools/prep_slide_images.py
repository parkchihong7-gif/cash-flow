"""캡처를 슬라이드에 넣을 수 있는 크기로 자른다.

전체 페이지 캡처는 세로 9,000px 이 넘는 것도 있다. 그대로 슬라이드에 넣으면
글씨가 개미만 해져서 아무것도 안 보인다. **위쪽 한 화면 분량**과 필요하면
특정 구간을 잘라 쓴다.

    python tools/prep_slide_images.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "training" / "screens"
OUT = SRC / "slide"

#: 슬라이드에 넣을 가로 크기. 이보다 크면 파일만 커지고 안 선명해진다.
WIDTH = 1600

#: (파일, 시작 비율, 높이 비율) — 특정 구간을 따로 뽑을 때.
CROPS: dict[str, tuple[float, float]] = {}


def _save(image: Image.Image, path: Path) -> None:
    ratio = WIDTH / image.width
    resized = image.resize((WIDTH, max(1, int(image.height * ratio))),
                           Image.LANCZOS)
    resized.save(path, optimize=True)


def top_crop(path: Path, out: Path, ratio: float = 0.62) -> None:
    """위쪽 한 화면 분량. 가로:세로 = 16:10 쯤으로 맞춘다."""
    with Image.open(path) as image:
        height = min(image.height, int(image.width * ratio))
        _save(image.crop((0, 0, image.width, height)), out)


def band(path: Path, out: Path, start: float, span: float) -> None:
    """세로 비율로 잘라낸 한 구간. 특정 패널을 보여 줄 때 쓴다."""
    with Image.open(path) as image:
        top = int(image.height * start)
        bottom = min(image.height, top + int(image.height * span))
        _save(image.crop((0, top, image.width, bottom)), out)


def main() -> int:
    if not SRC.is_dir():
        print("먼저 `python tools/capture_screens.py` 를 돌리세요.", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    made = 0
    for path in sorted(SRC.glob("*.png")):
        target = OUT / path.name
        if path.name.endswith("_detail.png"):
            # 상세 화면은 이미 위쪽만 잘라 찍어 두었다.
            with Image.open(path) as image:
                _save(image, target)
        else:
            top_crop(path, target)
        made += 1

    # 깊은 구간 몇 장 — 슬라이드에서 특정 기능을 짚을 때 쓴다.
    deep = {
        "13_exam-drill_admin.png": ("13_exam_weak.png", 0.30, 0.34),
        "14_senior-video_admin.png": ("14_senior_savings.png", 0.22, 0.30),
        "15_naver-blog_admin.png": ("15_naver_review.png", 0.26, 0.32),
        "16_speaker-desk_admin.png": ("16_speaker_tax.png", 0.18, 0.26),
    }
    for source, (name, start, span) in deep.items():
        path = SRC / source
        if path.is_file():
            band(path, OUT / name, start, span)
            made += 1

    total = sum(item.stat().st_size for item in OUT.glob("*.png"))
    print(f"{made}장 → {OUT} ({total / 1_000_000:.1f}MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
