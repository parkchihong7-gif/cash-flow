"""덱 점검 — 슬라이드 밖으로 나간 것, 겹친 것, 넘칠 것 같은 글.

이 환경에서는 LibreOffice 가 파일을 못 열어(텍스트 파일조차 실패) 그림으로
뽑아 눈으로 보는 점검을 못 한다. 그래서 **좌표와 글자 수로** 본다.
눈으로 보는 것만은 못하지만, 실제로 자주 나는 결함(밖으로 나감·겹침·넘침)은
이 셋으로 대부분 걸린다.

    python tools/qa_deck.py docs/training/*.pptx
"""

from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu

EMU_PER_INCH = 914400
SLIDE_W = 13.333
SLIDE_H = 7.5
MARGIN = 0.4          # 이보다 가장자리에 붙으면 짚는다
#: 한글은 대체로 한 글자가 한 칸(em)을 먹는다. 영문은 절반쯤.
def _em_width(text: str) -> float:
    wide = sum(1 for ch in text if ord(ch) > 0x1100)
    return wide + (len(text) - wide) * 0.55


def _inch(value) -> float:
    return (value or 0) / EMU_PER_INCH


def _boxes(slide):
    for shape in slide.shapes:
        if shape.left is None or shape.top is None:
            continue
        yield shape, (_inch(shape.left), _inch(shape.top),
                      _inch(shape.width), _inch(shape.height))


def _text_of(shape) -> tuple[str, float]:
    """글과 가장 큰 글자 크기(pt)."""
    if not shape.has_text_frame:
        return "", 0.0
    text, size = [], 0.0
    for para in shape.text_frame.paragraphs:
        line = "".join(run.text for run in para.runs)
        if line:
            text.append(line)
        for run in para.runs:
            if run.font.size:
                size = max(size, run.font.size.pt)
    return "\n".join(text), size or 12.0


def check(path: Path) -> list[str]:
    problems: list[str] = []
    deck = Presentation(str(path))

    for index, slide in enumerate(deck.slides, start=1):
        placed = []
        for shape, (x, y, w, h) in _boxes(slide):
            name = shape.shape_type
            label = (shape.name or str(name))[:28]

            # 1) 슬라이드 밖으로 나갔나
            if x < -0.01 or y < -0.01 or x + w > SLIDE_W + 0.01 or y + h > SLIDE_H + 0.01:
                problems.append(
                    f"{path.name} 슬라이드 {index}: '{label}' 가 슬라이드 밖으로 나갑니다 "
                    f"({x:.2f},{y:.2f} {w:.2f}×{h:.2f})")

            # 2) 가장자리에 너무 붙었나 (배경으로 깔린 큰 그림은 뺀다)
            if w < SLIDE_W - 1 and h < SLIDE_H - 1:
                if 0 <= x < MARGIN or 0 <= y < MARGIN:
                    problems.append(
                        f"{path.name} 슬라이드 {index}: '{label}' 가 가장자리에 "
                        f"너무 붙었습니다 ({x:.2f},{y:.2f})")

            # 3) 글이 상자를 넘칠 것 같은가
            text, size = _text_of(shape)
            if text and size:
                per_line = max(1.0, (w - 0.2) * 72 / size)
                lines = 0
                for chunk in text.split("\n"):
                    lines += max(1, int(_em_width(chunk) / per_line) + 1)
                needed = lines * size * 1.25 / 72
                if needed > h + 0.08:
                    problems.append(
                        f"{path.name} 슬라이드 {index}: '{label}' 글이 넘칠 수 있습니다 "
                        f"(필요 {needed:.2f}\" / 상자 {h:.2f}\") — {text[:34]}…")
            placed.append((label, x, y, w, h, bool(text)))

        # 4) 글끼리 겹쳤나 (도형 위에 얹은 글은 정상이므로 글–글만 본다)
        texts = [item for item in placed if item[5]]
        for i, a in enumerate(texts):
            for b in texts[i + 1:]:
                ox = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
                oy = min(a[2] + a[4], b[2] + b[4]) - max(a[2], b[2])
                if ox > 0.12 and oy > 0.12:
                    problems.append(
                        f"{path.name} 슬라이드 {index}: '{a[0]}' 와 '{b[0]}' 가 "
                        f"겹칩니다 ({ox:.2f}×{oy:.2f}\")")
    return problems


def main(argv: list[str]) -> int:
    paths = [Path(item) for item in argv[1:]]
    if not paths:
        print("점검할 pptx 를 넘기세요.", file=sys.stderr)
        return 1
    total = 0
    for path in paths:
        found = check(path)
        total += len(found)
        deck = Presentation(str(path))
        count = len(deck.slides._sldIdLst)
        if found:
            print(f"\n■ {path.name} — 슬라이드 {count}장, 짚을 것 {len(found)}건")
            for item in found:
                print(f"  - {item}")
        else:
            print(f"■ {path.name} — 슬라이드 {count}장, 짚을 것 없음")
    print(f"\n합계 {total}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
