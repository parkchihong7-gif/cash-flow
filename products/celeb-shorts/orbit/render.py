"""④ 레트로 렌더 — 승인된 대본 → 1080×1920 mp4.

그림은 Pillow·NumPy 로 직접 그린다(이미지 생성 AI 를 쓰지 않는다). 매끈한 AI 느낌 대신
80년대 인쇄물처럼 **조금씩 어긋나고 흔들리게** 만든다.

    종이 질감(잡음·얼룩·가장자리 어둡게) → 하프톤 망점 → 색면 → 상품 이미지(틀·그림자·테이프)
    → 글자(색 어긋남 그림자) → 별·궤도(4프레임마다 살짝 흔들림 = 손그림 느낌)

화면 배치는 쇼츠 화면의 가림을 피한다: 위 120px·아래 380px·오른쪽 150px 안에는 글자를 두지 않는다.
영상은 15장/초로 그려 FFmpeg 로 30장/초 mp4 를 만든다. 소리는 TTS(선택) + 라이선스 기록이 있는 음악(선택).
"""

from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

__all__ = ["W", "H", "FPS", "load_templates", "RenderJob", "render_still", "render_video",
           "FFmpegMissing", "find_ffmpeg"]

W, H = 1080, 1920
FPS = 15
OUT_FPS = 30
HERE = Path(__file__).resolve().parent
TEMPLATES_PATH = HERE / "video_templates.yaml"
FONT_DIR = HERE / "fonts"

# 쇼츠 화면에서 버튼·글자가 덮는 곳을 피한 안전 영역
SAFE_TOP, SAFE_BOTTOM, SAFE_RIGHT, SAFE_LEFT = 120, 380, 150, 60
BAND = (SAFE_TOP + 20, SAFE_TOP + 330)          # 상단 고정 제목 띠
STAGE = (BAND[1] + 40, H - SAFE_BOTTOM - 330)   # 상품·큰 글자 자리
SUB = (H - SAFE_BOTTOM - 300, H - SAFE_BOTTOM - 20)  # 자막 자리
DISCLOSURE = "광고, 제휴 링크 포함"

#: 동봉 글꼴(검은고딕·도현)에 없는 문장부호 → 있는 글자로. 없으면 네모(□)로 찍힌다.
_GLYPH_FIX = {"·": " ", "•": " ", "…": "...", "–": "-", "—": "-"}


def clean(text: str) -> str:
    for bad, good in _GLYPH_FIX.items():
        text = text.replace(bad, good)
    return text


class FFmpegMissing(RuntimeError):
    """FFmpeg 를 찾지 못했을 때."""


def find_ffmpeg() -> str:
    path = os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")
    if not path:
        raise FFmpegMissing("FFmpeg 가 없습니다. 명령 프롬프트에서 `winget install Gyan.FFmpeg` 로 설치하고 "
                            "실행.bat 을 다시 여세요. (다른 곳에 있으면 .env 에 FFMPEG_PATH=경로)")
    return path


# ------------------------------------------------------------ 설정
def load_templates() -> dict:
    return yaml.safe_load(TEMPLATES_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=32)
def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    name = load_templates()["fonts"][kind]
    return ImageFont.truetype(str(FONT_DIR / name), size)


def readable_on(bg: tuple, palette: dict) -> tuple[int, int, int]:
    """바탕색 위에서 더 잘 읽히는 글자색 — 네이비와 크림 중 밝기 차이가 큰 쪽."""
    def lum(c):
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    return max((palette["navy"], palette["cream"]), key=lambda c: abs(lum(c) - lum(bg)))


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


@dataclass
class Look:
    """템플릿 + 브랜드 색 → 실제 RGB."""

    tpl: dict
    palette: dict

    def c(self, key: str) -> tuple[int, int, int]:
        return self.palette[self.tpl[key]] if key in self.tpl else self.palette[key]


def make_look(template: str, settings: dict) -> Look:
    tpls = load_templates()["templates"]
    if template not in tpls:
        raise ValueError(f"없는 템플릿입니다: {template}")
    palette = {name: hex_rgb(settings[f"color_{name}"]) for name in ("navy", "mustard", "coral", "pink", "cream")}
    return Look(tpls[template], palette)


# ------------------------------------------------------------ 질감
def paper(color: tuple[int, int, int], seed: int) -> Image.Image:
    """빈티지 종이: 고운 잡음 + 큰 얼룩 + 가장자리 어둡게."""
    rng = np.random.default_rng(seed)
    base = np.empty((H, W, 3), dtype=np.float32)
    base[:] = color
    fine = rng.normal(0, 7, (H, W, 1)).astype(np.float32)
    blot = rng.normal(0, 1, (H // 60 + 1, W // 60 + 1)).astype(np.float32)
    blot = np.array(Image.fromarray(((blot - blot.min()) / (np.ptp(blot) + 1e-6) * 255).astype(np.uint8))
                    .resize((W, H), Image.BICUBIC), dtype=np.float32)[..., None]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vignette = (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)[..., None]
    out = base + fine + (blot - 128) * 0.10 - vignette * 22
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def halftone(img: Image.Image, where: str, color: tuple, seed: int) -> None:
    """망점: 한쪽에서 다른 쪽으로 커지는 점. 줄마다 반 칸 어긋나게, 점 크기는 살짝 들쭉날쭉."""
    if where == "none":
        return
    rng = random.Random(seed)
    draw = ImageDraw.Draw(img, "RGBA")
    step = 26
    if where == "top":
        y0, y1, grow = BAND[1], BAND[1] + 520, -1
    elif where == "bottom":
        y0, y1, grow = H - 760, H, 1
    else:
        y0, y1, grow = 0, H, 0
    for row, y in enumerate(range(y0, y1, step)):
        frac = (y - y0) / max(y1 - y0, 1)
        level = frac if grow == 1 else (1 - frac) if grow == -1 else 0.45 + 0.25 * math.sin(y / 180)
        for x in range(-step, W + step, step):
            xx = x + (step // 2 if row % 2 else 0)
            r = max(0.0, level * step * 0.55 + rng.uniform(-1.2, 1.2))
            if r > 1:
                draw.ellipse((xx - r, y - r, xx + r, y + r), fill=color + (150 if where == "full" else 200,))


def wobbly_line(draw, points, fill, width, rng) -> None:
    """손으로 그린 듯 흔들리는 선."""
    pts = []
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        for t in np.linspace(0, 1, 8, endpoint=False):
            pts.append((x1 + (x2 - x1) * t + rng.uniform(-2, 2), y1 + (y2 - y1) * t + rng.uniform(-2, 2)))
    pts.append(points[-1])
    draw.line(pts, fill=fill, width=width, joint="curve")


def star(draw, cx, cy, r, fill, rot=0.0) -> None:
    pts = []
    for i in range(8):
        a = rot + i * math.pi / 4
        rr = r if i % 2 == 0 else r * 0.32
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    draw.polygon(pts, fill=fill)


def draw_cosmos(img: Image.Image, look: Look, n: int, t: float, frame: int, seed: int) -> None:
    """별·궤도. 4프레임마다 흔들림을 다시 뽑아 손그림 애니메이션처럼."""
    draw = ImageDraw.Draw(img, "RGBA")
    jitter = random.Random(seed * 1000 + frame // 4)
    place = random.Random(seed)
    cx, cy = W * 0.5, (STAGE[0] + STAGE[1]) / 2
    for k, (rx, ry, tilt) in enumerate(((470, 150, -0.25), (520, 190, 0.18))):
        pts = []
        for i in range(64):
            a = i / 63 * 2 * math.pi
            x, y = rx * math.cos(a), ry * math.sin(a)
            pts.append((cx + x * math.cos(tilt) - y * math.sin(tilt) + jitter.uniform(-1.5, 1.5),
                        cy + x * math.sin(tilt) + y * math.cos(tilt) + jitter.uniform(-1.5, 1.5)))
        draw.line(pts, fill=look.c("accent") + (170,), width=4 - k)
        a = t * 0.9 + k * 2.3                       # 궤도를 도는 작은 행성
        px = cx + rx * math.cos(a) * math.cos(tilt) - ry * math.sin(a) * math.sin(tilt)
        py = cy + rx * math.cos(a) * math.sin(tilt) + ry * math.sin(a) * math.cos(tilt)
        draw.ellipse((px - 14, py - 14, px + 14, py + 14), fill=look.c("band"), outline=look.c("accent"), width=3)
    for i in range(n):
        x = place.uniform(SAFE_LEFT, W - SAFE_RIGHT)
        y = place.uniform(STAGE[0] - 40, SUB[0] - 20)
        r = place.uniform(14, 34) * (1 + 0.12 * math.sin(t * 3 + i))
        star(draw, x + jitter.uniform(-2, 2), y + jitter.uniform(-2, 2), r,
             (look.c("accent") if i % 2 else look.palette["mustard"] if look.tpl["bg"] != "mustard" else look.palette["cream"]) + (235,),
             rot=jitter.uniform(-0.08, 0.08))


# ------------------------------------------------------------ 글자
def wrap(text: str, fnt: ImageFont.FreeTypeFont, width: int, max_lines: int = 2) -> list[str]:
    words, lines, cur = clean(text).replace("\n", " ").split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if fnt.getlength(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    while lines and any(fnt.getlength(line) > width for line in lines):   # 띄어쓰기 없는 긴 줄
        line = max(lines, key=fnt.getlength)
        i = lines.index(line)
        cut = len(line) // 2
        lines[i:i + 1] = [line[:cut], line[cut:]]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines


def misprint_text(draw, xy, text, fnt, fill, shadow, offset=(5, 4), anchor="la") -> None:
    """인쇄가 살짝 어긋난 느낌 — 다른 색 판이 몇 px 밀려 찍힌 그림자."""
    x, y = xy
    text = clean(text)
    draw.text((x + offset[0], y + offset[1]), text, font=fnt, fill=shadow, anchor=anchor)
    draw.text((x, y), text, font=fnt, fill=fill, anchor=anchor)


def text_block(lines, fnt, fill, shadow, line_gap=1.15) -> Image.Image:
    """가운데 정렬 여러 줄 글자를 투명 바탕에 그린다."""
    height = int(fnt.size * line_gap * len(lines) + 20)
    layer = Image.new("RGBA", (W, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for i, line in enumerate(lines):
        misprint_text(draw, ((W - SAFE_RIGHT + SAFE_LEFT) / 2, 10 + i * fnt.size * line_gap), line, fnt,
                      fill, shadow, anchor="ma")
    return layer


# ------------------------------------------------------------ 상품 틀
def frame_mask(shape: str, size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    if shape == "circle":
        d.ellipse((0, 0, size - 1, size - 1), fill=255)
    elif shape == "arch":
        d.rectangle((0, size // 2, size - 1, size - 1), fill=255)
        d.ellipse((0, 0, size - 1, size - 1), fill=255)
    elif shape == "starburst":
        pts = []
        for i in range(32):
            a = i * math.pi / 16
            r = size / 2 if i % 2 == 0 else size * 0.40
            pts.append((size / 2 + r * math.cos(a), size / 2 + r * math.sin(a)))
        d.polygon(pts, fill=255)
    elif shape == "tv":
        d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 7, fill=255)
    else:  # polaroid
        d.rectangle((0, 0, size - 1, size - 1), fill=255)
    return mask


def product_card(look: Look, product_img: Image.Image | None, name: str, seed: int) -> Image.Image:
    """상품 이미지를 틀에 넣고 테두리·그림자·테이프를 붙인다.

    쓸 수 있는 이미지가 없으면 **자체 그래픽 카드**(상품 이름을 크게 쓴 판)로 대신한다.
    """
    rng = random.Random(seed)
    size = 640
    shape = look.tpl["frame"]
    if product_img is not None:
        inner = ImageOps.fit(product_img.convert("RGB"), (size, size), Image.LANCZOS)
    else:
        inner = Image.new("RGB", (size, size), look.c("block"))
        halftone_small = ImageDraw.Draw(inner, "RGBA")
        for y in range(0, size, 22):
            for x in range(0, size, 22):
                r = 3 + 5 * (y / size)
                halftone_small.ellipse((x - r, y - r, x + r, y + r), fill=look.c("accent") + (120,))
        lines = wrap(name, font("title", 92), size - 90, 3)
        d = ImageDraw.Draw(inner)
        top = size / 2 - len(lines) * 52
        ink = readable_on(look.c("block"), look.palette)
        for i, line in enumerate(lines):
            misprint_text(d, (size / 2, top + i * 104), line, font("title", 92), ink, look.c("accent"), anchor="ma")
    mask = frame_mask(shape, size)
    pad = 40 if shape == "polaroid" else 18
    card = Image.new("RGBA", (size + pad * 2, size + pad * 2 + (70 if shape == "polaroid" else 0)), (0, 0, 0, 0))
    border = Image.new("RGBA", card.size, (0, 0, 0, 0))
    bmask = frame_mask(shape if shape != "polaroid" else "polaroid", size + pad * 2)
    if shape == "polaroid":
        bmask = Image.new("L", card.size, 255)
    border.paste(look.palette["cream"] if look.tpl["bg"] != "cream" else (255, 252, 244), (0, 0), bmask)
    card = Image.alpha_composite(card, border)
    card.paste(inner, (pad, pad), mask)
    # 테이프 두 조각 (오려 붙인 콜라주)
    tape = Image.new("RGBA", (190, 54), look.palette["mustard"] + (170,))
    for corner in (0, 1):
        t = tape.rotate(rng.uniform(-35, -20) if corner == 0 else rng.uniform(20, 35), expand=True)
        card.alpha_composite(t, (10 if corner == 0 else card.width - t.width - 10, 0))
    card = card.rotate(rng.uniform(-4, 4), resample=Image.BICUBIC, expand=True)
    shadow = Image.new("RGBA", card.size, look.c("band") + (0,))
    shadow.putalpha(card.getchannel("A").point(lambda a: int(a * 0.55)))
    out = Image.new("RGBA", (card.width + 24, card.height + 24), (0, 0, 0, 0))
    out.alpha_composite(shadow, (18, 20))
    out.alpha_composite(card, (0, 0))
    return out


# ------------------------------------------------------------ 장면
@dataclass
class RenderJob:
    plan: dict                       # PlanDraft.model_dump()
    template: str
    settings: dict
    product_name: str
    product_image: Path | None = None
    own_comment: str = ""
    name_shown: bool = False          # 연예인 이름을 써도 되는 대본인가 (끝 카드 문구에 씀)
    seed: int = 7
    _cache: dict = field(default_factory=dict, repr=False)


def _base_layer(job: RenderJob, look: Look, index: int) -> Image.Image:
    """장면마다 한 번만 그리는 고정 층: 종이·망점·색면·제목 띠·광고 표시."""
    key = ("base", index)
    if key in job._cache:
        return job._cache[key]
    img = paper(look.c("bg"), job.seed + index).convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    rng = random.Random(job.seed + index)
    # 아래쪽 큰 색면 (살짝 기울어진 오려 붙인 종이)
    y = H - 700 + rng.randint(-20, 20)
    draw.polygon([(0, y + 40), (W, y - 30), (W, H), (0, H)], fill=look.c("block") + (255,))
    halftone(img, look.tpl["halftone"], look.c("halftone_color"), job.seed + index)
    # 상단 고정 제목 띠
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle((0, BAND[0], W, BAND[1]), fill=look.c("band") + (255,))
    wobbly_line(draw, [(SAFE_LEFT, BAND[1] - 14), (W - SAFE_LEFT, BAND[1] - 18)], look.c("accent"), 6, rng)
    label = clean(job.settings.get("channel_name_en", "CELEB ORBIT"))
    draw.text((SAFE_LEFT, BAND[0] + 22), label, font=font("title", 34), fill=look.c("band_text"))
    star(draw, SAFE_LEFT + font("title", 34).getlength(label) + 34, BAND[0] + 40, 18,
         look.c("accent") if look.tpl["band"] == "mustard" else look.palette["mustard"])
    title_font = font("title", 74)
    for i, line in enumerate(wrap(job.plan["title"], title_font, W - SAFE_LEFT * 2, 2)):
        misprint_text(draw, (SAFE_LEFT, BAND[0] + 86 + i * 92), line, title_font,
                      look.c("band_text"), look.c("accent"), offset=(4, 4))
    job._cache[key] = img
    return img


def _tag_layer(job: RenderJob, look: Look) -> Image.Image:
    """광고 표시 — 맨 위층에 그려 상품 틀에도 가리지 않는다. 모든 장면에 늘 보인다."""
    if "tag" not in job._cache:
        layer = Image.new("RGBA", (W, 120), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        tag_font = font("body", 34)
        tw = tag_font.getlength(DISCLOSURE)
        draw.rounded_rectangle((SAFE_LEFT, 16, SAFE_LEFT + tw + 36, 70), radius=26,
                               fill=look.palette["cream"] + (240,), outline=look.palette["navy"], width=3)
        draw.text((SAFE_LEFT + 18, 24), DISCLOSURE, font=tag_font, fill=look.palette["navy"])
        job._cache["tag"] = layer
    return job._cache["tag"]


def _scene_layers(job: RenderJob, look: Look, index: int):
    """장면의 상품 카드와 글자 층(움직이기 전 모양)."""
    key = ("layers", index)
    if key in job._cache:
        return job._cache[key]
    scene = job.plan["scenes"][index]
    last = index == len(job.plan["scenes"]) - 1
    card = None
    if scene.get("visual") in ("product_image", "own_photo"):
        img = Image.open(job.product_image) if job.product_image else None
        card = product_card(look, img, job.product_name, job.seed + index)
    if index == 0:                                    # 훅: 무대 가운데 큰 글자
        big = text_block(wrap(job.plan["hook"], font("title", 128), W - SAFE_LEFT - SAFE_RIGHT - 40, 3),
                         font("title", 128), readable_on(look.c("bg"), look.palette), look.c("accent"))
    elif scene.get("visual") == "text_card" and not last:
        big = text_block(wrap(scene["subtitle"], font("title", 112), W - SAFE_LEFT - SAFE_RIGHT - 40, 3),
                         font("title", 112), readable_on(look.c("bg"), look.palette), look.c("accent"))
    else:
        big = None
    sub = None
    if index != 0 and big is None or last:
        lines = wrap(scene["subtitle"], font("body", 76), W - SAFE_LEFT - SAFE_RIGHT - 80, 2)
        sub = Image.new("RGBA", (W, SUB[1] - SUB[0]), (0, 0, 0, 0))
        d = ImageDraw.Draw(sub)
        box_h = 40 + len(lines) * 92
        d.rectangle((SAFE_LEFT, 0, W - SAFE_RIGHT, box_h), fill=look.c("subtitle_bg") + (240,),
                    outline=look.c("accent"), width=5)
        for i, line in enumerate(lines):
            misprint_text(d, ((W - SAFE_RIGHT + SAFE_LEFT) / 2, 22 + i * 92), line, font("body", 76),
                          look.c("subtitle_text"), look.c("accent"), offset=(3, 3), anchor="ma")
    end = None
    if last:                                          # 끝 카드: 내 말 한 줄 + 고지
        end = Image.new("RGBA", (W, STAGE[1] - STAGE[0]), (0, 0, 0, 0))
        d = ImageDraw.Draw(end)
        panel = look.palette["cream"]
        d.rectangle((SAFE_LEFT, 80, W - SAFE_RIGHT, 640), fill=panel + (235,), outline=look.palette["navy"], width=4)
        ink = look.palette["navy"]
        y = 120
        if job.own_comment:
            for line in wrap(f"“{job.own_comment}”", font("body", 64), W - SAFE_LEFT - SAFE_RIGHT - 60, 3):
                misprint_text(d, ((W - SAFE_RIGHT + SAFE_LEFT) / 2, y), line, font("body", 64),
                              ink, look.c("accent"), offset=(3, 3), anchor="ma")
                y += 80
        y += 40
        notes = ["유료 광고, 제휴 링크 포함", "소개 상품은 비슷한 상품일 수 있어요", "AI 음성, 자동 편집 사용"]
        for note in notes:
            d.text(((W - SAFE_RIGHT + SAFE_LEFT) / 2, y), note, font=font("body", 44), fill=ink, anchor="ma")
            y += 60
    job._cache[key] = (card, big, sub, end)
    return job._cache[key]


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _with_alpha(layer: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return layer
    out = layer.copy()
    out.putalpha(layer.getchannel("A").point(lambda a: int(a * alpha)))
    return out


def draw_frame(job: RenderJob, look: Look, time: float, frame: int) -> Image.Image:
    scenes = job.plan["scenes"]
    index = next((i for i, s in enumerate(scenes) if s["start"] <= time < s["end"]), len(scenes) - 1)
    scene = scenes[index]
    local = time - scene["start"]
    img = _base_layer(job, look, index).copy()
    draw_cosmos(img, look, look.tpl["stars"], time, frame, job.seed)
    card, big, sub, end = _scene_layers(job, look, index)
    enter = _ease(local / 0.35)
    if card is not None:
        scale = 1.0 + 0.04 * min(local / max(scene["end"] - scene["start"], 0.1), 1)
        c = card.resize((int(card.width * scale), int(card.height * scale)), Image.BILINEAR)
        cx = (W - SAFE_RIGHT + SAFE_LEFT) // 2 - c.width // 2
        cy = (STAGE[0] + STAGE[1]) // 2 - c.height // 2 + int((1 - enter) * 80)
        img.alpha_composite(_with_alpha(c, enter), (cx, max(cy, STAGE[0])))
    if big is not None:
        pop = 0.86 + 0.14 * enter
        b = big.resize((int(big.width * pop), int(big.height * pop)), Image.BILINEAR)
        img.alpha_composite(_with_alpha(b, enter), ((W - b.width) // 2, (STAGE[0] + STAGE[1]) // 2 - b.height // 2))
    if end is not None:
        img.alpha_composite(_with_alpha(end, enter), (0, STAGE[0]))
    if sub is not None:
        img.alpha_composite(_with_alpha(sub, enter), (0, SUB[0] + int((1 - enter) * 50)))
    img.alpha_composite(_tag_layer(job, look), (0, BAND[1]))
    return img.convert("RGB")


# ------------------------------------------------------------ 내보내기
def render_still(job: RenderJob, scene_index: int = 0) -> Image.Image:
    look = make_look(job.template, job.settings)
    scene = job.plan["scenes"][scene_index]
    t = min(scene["start"] + 0.6, scene["end"] - 0.01)
    return draw_frame(job, look, t, int(t * FPS))


def _audio_args(duration: float, music: Path | None, voices: list[tuple[Path, float]]) -> tuple[list, list]:
    """(입력 인자, 필터) — 음성은 장면 시작에 맞춰 놓고, 음악은 반복·볼륨·끝 1초 페이드."""
    inputs, chains, labels = [], [], []
    n = 1
    for path, start in voices:
        inputs += ["-i", str(path)]
        ms = int(start * 1000)
        chains.append(f"[{n}:a]adelay={ms}|{ms},apad[v{n}]")
        labels.append(f"[v{n}]")
        n += 1
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        vol = 0.22 if voices else 0.6
        chains.append(f"[{n}:a]volume={vol},afade=t=out:st={max(duration - 1, 0):.2f}:d=1[m]")
        labels.append("[m]")
        n += 1
    if not labels:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        chains.append(f"[{n}:a]anull[a]")
    elif len(labels) == 1:
        chains.append(f"{labels[0]}anull[a]")
    else:
        chains.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0[a]")
    chains[-1] = chains[-1][:-3] + f",atrim=0:{duration:.2f}[a]"
    return inputs, chains


def render_video(job: RenderJob, out: Path, *, music: Path | None = None,
                 voices: list[tuple[Path, float]] | None = None) -> Path:
    """mp4 를 만든다. FFmpeg 가 없으면 FFmpegMissing."""
    ffmpeg = find_ffmpeg()
    look = make_look(job.template, job.settings)
    duration = float(job.plan["scenes"][-1]["end"])
    frames = int(round(duration * FPS))
    out.parent.mkdir(parents=True, exist_ok=True)
    a_inputs, a_chains = _audio_args(duration, music, voices or [])
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           *a_inputs,
           "-filter_complex", ";".join(a_chains), "-map", "0:v", "-map", "[a]",
           "-r", str(OUT_FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-t", f"{duration:.2f}", "-movflags", "+faststart",
           "-metadata", "comment=AI-assisted: script and voice may be AI-generated (CELEB ORBIT)",
           str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in range(frames):
            proc.stdin.write(draw_frame(job, look, f / FPS, f).tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode("utf-8", "replace")
    if proc.wait() != 0:
        raise RuntimeError(f"FFmpeg 오류: {err.strip()[-400:]}")
    return out


def probe(path: Path) -> dict:
    """ffprobe 로 해상도·길이·소리 유무를 확인한다(시험·검사용)."""
    ffprobe = shutil.which("ffprobe") or str(Path(find_ffmpeg()).with_name("ffprobe"))
    import json as _json
    raw = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    data = _json.loads(raw)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    return {"width": video["width"], "height": video["height"], "duration": float(data["format"]["duration"]),
            "audio": any(s["codec_type"] == "audio" for s in data["streams"])}
