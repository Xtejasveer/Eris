// Shared helpers for the three demo decks (16:9, 10" x 5.625").
const pptxgen = require("pptxgenjs");
const React = require("react");
const RDS = require("react-dom/server");
const sharp = require("sharp");

const HEAD = "Cambria", BODY = "Calibri", MONO = "Courier New";
const W = 10, H = 5.625;

async function iconPng(Comp, color, size = 256) {
  const svg = RDS.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

// A deck: P = palette {dark, accent, accent2, soft, text, muted, light}. slides = [async (s, ctx) => {...}, ...]
async function buildDeck({ file, title, P, slides, only = null }) {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.title = title;
  pres.author = "Eris demo";
  pres.theme = { headFontFace: HEAD, bodyFontFace: BODY };
  pres.defineSlideMaster({
    title: "DARK", background: { color: P.dark },
    objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.55, w: 8.8, h: 1.5, fontFace: HEAD, fontSize: 40,
      bold: true, color: "FFFFFF", valign: "bottom", align: "left", margin: 0 }, text: "" } }],
  });
  pres.defineSlideMaster({
    title: "LIGHT", background: { color: "FFFFFF" },
    objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.55, y: 0.32, w: 8.9, h: 0.75, fontFace: HEAD, fontSize: 30,
      bold: true, color: P.text, valign: "middle", align: "left", margin: 0 }, text: "" } }],
    slideNumber: { x: 9.2, y: 5.2, w: 0.5, h: 0.3, fontFace: BODY, fontSize: 10, color: P.muted, align: "right" },
  });
  const ctx = makeCtx(pres, P);
  for (let i = 0; i < slides.length; i++) {
    if (only !== null && i !== only) continue;
    await slides[i](ctx);
  }
  await pres.writeFile({ fileName: file });
  return file;
}

function makeCtx(pres, P) {
  const ctx = {
    pres, P,
    dark(titleText) {
      const s = pres.addSlide({ masterName: "DARK" });
      if (titleText) s.addText(titleText, { placeholder: "title" });
      return s;
    },
    light(titleText) {
      const s = pres.addSlide({ masterName: "LIGHT" });
      s.addText(titleText, { placeholder: "title" });
      return s;
    },
    text(s, text, o) { s.addText(text, { isTextBox: true, fontFace: BODY, fontSize: 15, color: P.text, margin: 0, valign: "top", ...o }); },
    card(s, x, y, w, h, fill = P.soft, opts = {}) {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: fill },
        shadow: opts.shadow ? { type: "outer", color: "000000", opacity: 0.12, blur: 8, offset: 2, angle: 90 } : undefined,
        objectName: opts.name });
    },
    async iconCircle(s, Comp, x, y, d, bg, fg) {
      s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: bg }, line: { color: bg } });
      const pad = d * 0.24;
      s.addImage({ data: await iconPng(Comp, fg), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad });
    },
    stat(s, x, y, w, big, label, color) {
      s.addText(big, { isTextBox: true, x, y, w, h: 0.85, fontFace: HEAD, fontSize: 40, bold: true, color, margin: 0, valign: "bottom" });
      s.addText(label, { isTextBox: true, x, y: y + 0.9, w, h: 0.6, fontFace: BODY, fontSize: 13, color: P.muted, margin: 0, valign: "top" });
    },
    code(s, x, y, w, h, codeText, fontSize = 13) {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: "1D232B" }, line: { color: "1D232B" } });
      s.addText(codeText, { isTextBox: true, x: x + 0.25, y: y + 0.18, w: w - 0.5, h: h - 0.36, fontFace: MONO, fontSize, color: "E8EDF2",
        margin: 0, valign: "top", paraSpaceAfter: 2 });
    },
    bullets(s, items, o) {
      s.addText(items.map((t, i) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: i < items.length - 1 } })),
        { isTextBox: true, fontFace: BODY, fontSize: 15, color: P.text, margin: [0, 0, 0, 4], valign: "top", paraSpaceAfter: 8, ...o });
    },
    arrow(s, x, y, w, color) {
      s.addShape(pres.shapes.RIGHT_ARROW, { x, y, w, h: 0.32, fill: { color }, line: { color } });
    },
    source(s, text) {
      s.addText(text, { isTextBox: true, x: 0.55, y: 5.18, w: 8.4, h: 0.3, fontFace: BODY, fontSize: 10, color: P.muted, margin: 0, italic: true });
    },
    chartStyle(extra = {}) {
      return { catAxisLabelColor: P.muted, valAxisLabelColor: P.muted, catAxisLabelFontFace: BODY, valAxisLabelFontFace: BODY,
        catAxisLabelFontSize: 11, valAxisLabelFontSize: 11, valGridLine: { color: "E3E7EB", size: 0.75 }, catGridLine: { style: "none" },
        dataLabelFontFace: BODY, dataLabelFontSize: 11, dataLabelColor: P.text, titleFontFace: BODY, titleFontSize: 13, titleColor: P.text,
        showLegend: false, ...extra };
    },
  };
  return ctx;
}

module.exports = { buildDeck, iconPng, W, H, HEAD, BODY, MONO };
