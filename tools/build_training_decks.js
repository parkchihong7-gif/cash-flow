/**
 * 교육자료 덱 — 실제 화면 캡처를 넣은 PPT 5종.
 *
 *   node tools/build_training_decks.js
 *
 * 화면이 바뀌면 tools/capture_screens.py → tools/prep_slide_images.py 를 돌리고
 * 이걸 다시 돌린다. 캡처를 손으로 넣지 않는 이유가 그것이다.
 */
const pptxgen = require("pptxgenjs");
const path = require("path");
const fs = require("fs");

const ROOT = path.resolve(__dirname, "..");
const IMG = path.join(ROOT, "docs/training/screens/slide");
const OUT = path.join(ROOT, "docs/training");

// 제품 화면에서 그대로 가져온 색. 덱과 앱이 한 벌로 보이게.
const C = {
  ink: "12151C",        // 관리자 껍데기
  client: "1B3A5C",     // 클라이언트 껍데기
  accent: "1F5EFF",
  ok: "0F8A4F",
  warn: "9A6400",
  warnSoft: "FDF3E0",
  bad: "C1341F",
  badSoft: "FDECEB",
  line: "E4E7EC",
  soft: "F7F8FA",
  sunk: "EEF0F4",
  gray: "697086",
  white: "FFFFFF",
};
const FH = "맑은 고딕";   // 제목
const FB = "맑은 고딕";   // 본문

const img = (name) => path.join(IMG, name);
const has = (name) => fs.existsSync(img(name));

function deck() {
  const p = new pptxgen();
  p.layout = "LAYOUT_WIDE";      // 13.3 × 7.5
  p.theme = { headFontFace: FH, bodyFontFace: FB };
  return p;
}

/** 표지 — 어두운 바탕. */
function cover(p, { number, title, subtitle, tag }) {
  const s = p.addSlide();
  s.background = { color: C.ink };
  if (number) {
    s.addShape(p.ShapeType.ellipse, {
      x: 0.9, y: 1.5, w: 0.86, h: 0.86, fill: { color: C.accent },
    });
    s.addText(String(number), {
      x: 0.9, y: 1.5, w: 0.86, h: 0.86, align: "center", valign: "middle",
      fontSize: 30, bold: true, color: C.white, fontFace: FH, isTextBox: true,
    });
  }
  s.addText(title, {
    x: 0.9, y: 2.6, w: 11.5, h: 1.1, fontSize: 42, bold: true,
    color: C.white, fontFace: FH, isTextBox: true, margin: 0,
  });
  s.addText(subtitle, {
    x: 0.9, y: 3.8, w: 10.5, h: 0.9, fontSize: 17, color: "B9C0CE",
    fontFace: FB, isTextBox: true, margin: 0,
  });
  if (tag) {
    s.addText(tag, {
      x: 0.9, y: 6.3, w: 11.5, h: 0.4, fontSize: 12, color: "6E7688",
      fontFace: FB, isTextBox: true, margin: 0,
    });
  }
  return s;
}

/** 본문 슬라이드 머리. */
function head(p, title, kicker) {
  const s = p.addSlide();
  s.background = { color: C.white };
  if (kicker) {
    s.addText(kicker, {
      x: 0.6, y: 0.5, w: 12.1, h: 0.3, fontSize: 12, bold: true,
      color: C.accent, fontFace: FB, isTextBox: true, margin: 0,
    });
  }
  s.addText(title, {
    x: 0.6, y: kicker ? 0.82 : 0.62, w: 12.1, h: 0.72, fontSize: 32, bold: true,
    color: C.ink, fontFace: FH, isTextBox: true, margin: 0,
  });
  return s;
}

/** 화면 캡처 한 장 + 옆에 설명. */
function shot(p, { kicker, title, image, notes, caption, tone }) {
  const s = head(p, title, kicker);
  const y = 1.62;
  if (has(image)) {
    s.addImage({
      path: img(image), x: 0.6, y, w: 7.7, h: 4.85, sizing: { type: "contain", w: 7.7, h: 4.85 },
    });
    if (caption) {
      s.addText(caption, {
        x: 0.6, y: y + 4.9, w: 7.7, h: 0.35, fontSize: 10.5, color: C.gray,
        fontFace: FB, isTextBox: true, margin: 0,
      });
    }
  }
  let ny = y;
  (notes || []).forEach((note) => {
    const t = note.tone || tone || "";
    const bg = t === "bad" ? C.badSoft : t === "warn" ? C.warnSoft : C.sunk;
    const fg = t === "bad" ? C.bad : t === "warn" ? C.warn : C.ink;
    const h = note.body ? 1.28 : 0.62;
    s.addShape(p.ShapeType.roundRect, {
      x: 8.6, y: ny, w: 4.15, h, fill: { color: bg }, line: { color: bg },
      rectRadius: 0.06,
    });
    s.addText(note.title, {
      x: 8.82, y: ny + 0.12, w: 3.75, h: 0.34, fontSize: 13, bold: true,
      color: fg, fontFace: FH, isTextBox: true, margin: 0,
    });
    if (note.body) {
      s.addText(note.body, {
        x: 8.82, y: ny + 0.5, w: 3.75, h: 0.7, fontSize: 11, color: C.ink,
        fontFace: FB, isTextBox: true, margin: 0, lineSpacingMultiple: 1.15,
      });
    }
    ny += h + 0.18;
  });
  return s;
}

/** 아이콘 없는 카드 격자. */
function cards(p, { kicker, title, intro, items, cols }) {
  const s = head(p, title, kicker);
  let y = 1.62;
  if (intro) {
    s.addText(intro, {
      x: 0.6, y: 1.6, w: 12.1, h: 0.45, fontSize: 14, color: C.gray,
      fontFace: FB, isTextBox: true, margin: 0,
    });
    y = 2.18;
  }
  const n = cols || 2;
  const w = (12.1 - 0.35 * (n - 1)) / n;
  const rows = Math.ceil(items.length / n);
  const h = Math.min(1.7, (6.6 - y) / rows - 0.3);
  items.forEach((item, i) => {
    const cx = 0.6 + (i % n) * (w + 0.35);
    const cy = y + Math.floor(i / n) * (h + 0.3);
    const tone = item.tone || "";
    const bg = tone === "bad" ? C.badSoft : tone === "warn" ? C.warnSoft
      : tone === "ok" ? "E7F6EE" : C.soft;
    s.addShape(p.ShapeType.roundRect, {
      x: cx, y: cy, w, h, fill: { color: bg }, line: { color: C.line },
      rectRadius: 0.06,
    });
    s.addText(item.title, {
      x: cx + 0.28, y: cy + 0.16, w: w - 0.56, h: 0.36, fontSize: 15, bold: true,
      color: tone === "bad" ? C.bad : tone === "warn" ? C.warn : C.ink,
      fontFace: FH, isTextBox: true, margin: 0,
    });
    s.addText(item.body, {
      x: cx + 0.28, y: cy + 0.56, w: w - 0.56, h: h - 0.72, fontSize: 11.5,
      color: C.ink, fontFace: FB, isTextBox: true, margin: 0,
      lineSpacingMultiple: 1.2,
    });
  });
  return s;
}

/** 표 한 장. */
function table(p, { kicker, title, intro, headers, rows, widths, note }) {
  const s = head(p, title, kicker);
  let y = 1.62;
  if (intro) {
    s.addText(intro, {
      x: 0.6, y: 1.6, w: 12.1, h: 0.4, fontSize: 14, color: C.gray,
      fontFace: FB, isTextBox: true, margin: 0,
    });
    y = 2.12;
  }
  const body = [
    headers.map((h) => ({
      text: h,
      options: { bold: true, color: C.white, fill: { color: C.ink }, fontSize: 12 },
    })),
    ...rows.map((r) =>
      r.map((cell) => {
        const text = typeof cell === "object" ? cell.text : cell;
        const tone = typeof cell === "object" ? cell.tone : "";
        return {
          text,
          options: {
            fontSize: 11.5, color: tone === "bad" ? C.bad : tone === "warn" ? C.warn : "1A1D23",
            fill: { color: tone === "bad" ? C.badSoft : tone === "warn" ? C.warnSoft : C.white },
          },
        };
      })),
  ];
  s.addTable(body, {
    x: 0.6, y, w: 12.1, colW: widths, border: { type: "solid", color: C.line, pt: 0.5 },
    fontFace: FB, valign: "middle", rowH: 0.34, autoPage: false,
  });
  if (note) {
    s.addText(note, {
      x: 0.6, y: 6.62, w: 12.1, h: 0.45, fontSize: 10.5, color: C.gray,
      fontFace: FB, isTextBox: true, margin: 0,
    });
  }
  return s;
}

/** 큰 숫자 한 줄. */
function stats(p, { kicker, title, intro, items }) {
  const s = head(p, title, kicker);
  let y = 2.2;
  if (intro) {
    s.addText(intro, {
      x: 0.6, y: 1.62, w: 12.1, h: 0.5, fontSize: 14, color: C.gray,
      fontFace: FB, isTextBox: true, margin: 0,
    });
  }
  const w = (12.1 - 0.35 * (items.length - 1)) / items.length;
  items.forEach((item, i) => {
    const cx = 0.6 + i * (w + 0.35);
    s.addShape(p.ShapeType.roundRect, {
      x: cx, y, w, h: 2.0, fill: { color: item.tone === "bad" ? C.badSoft : C.soft },
      line: { color: C.line }, rectRadius: 0.06,
    });
    s.addText(item.value, {
      x: cx + 0.2, y: y + 0.28, w: w - 0.4, h: 0.9, fontSize: 40, bold: true,
      color: item.tone === "bad" ? C.bad : C.accent, fontFace: FH,
      isTextBox: true, margin: 0, align: "center",
    });
    s.addText(item.label, {
      x: cx + 0.2, y: y + 1.22, w: w - 0.4, h: 0.6, fontSize: 12, color: C.ink,
      fontFace: FB, isTextBox: true, margin: 0, align: "center",
      lineSpacingMultiple: 1.15,
    });
  });
  return s;
}

/** 마무리 — 어두운 바탕. */
function closing(p, { title, lines }) {
  const s = p.addSlide();
  s.background = { color: C.ink };
  s.addText(title, {
    x: 0.9, y: 1.5, w: 11.5, h: 0.9, fontSize: 34, bold: true, color: C.white,
    fontFace: FH, isTextBox: true, margin: 0,
  });
  s.addText(lines.map((t, i) => ({
    text: t, options: { bullet: true, breakLine: i !== lines.length - 1 },
  })), {
    x: 0.9, y: 2.7, w: 11.5, h: 3.4, fontSize: 15, color: "CFD6E4",
    fontFace: FB, isTextBox: true, margin: 0, paraSpaceAfter: 10,
  });
  return s;
}

module.exports = { deck, cover, head, shot, cards, table, stats, closing, C, FH, FB, img, has, OUT };
