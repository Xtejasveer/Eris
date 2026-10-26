// The three prerequisite decks: what a student should know before each lecture. Same palettes as the lectures.
const { buildDeck } = require("./common");
const fa = require("react-icons/fa");

const PAL = {
  kadane: { dark: "17202A", accent: "F2B134", accent2: "1E9E8C", soft: "EEF4F3", text: "1F2A33", muted: "5F6B76" },
  india: { dark: "0E3B2E", accent: "E07A1F", accent2: "3A7D5C", soft: "E9F2EC", text: "1F2A24", muted: "5E6B63" },
  physics: { dark: "13203B", accent: "F28C28", accent2: "3A8FD9", soft: "EAF2FB", text: "1C2533", muted: "5B6577" },
};

// shared pieces
function preTitle(c, title, sub, forWhat) {
  const s = c.dark(title);
  s.addShape(c.pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 0.9, w: 1.85, h: 0.42, rectRadius: 0.1, fill: { color: "8A4F78" }, line: { color: "8A4F78" } });
  s.addText("PREREQUISITE", { isTextBox: true, x: 0.6, y: 0.9, w: 1.85, h: 0.42, align: "center", valign: "middle", fontFace: "Calibri", fontSize: 12, bold: true, color: "FFFFFF", charSpacing: 2, margin: 0 });
  c.text(s, sub, { x: 0.6, y: 3.15, w: 8.6, h: 0.5, fontSize: 19, color: "D5DEE8" });
  c.text(s, `Watch before: ${forWhat}`, { x: 0.6, y: 4.3, w: 8.6, h: 0.4, fontSize: 14, color: c.P.accent, bold: true });
  return s;
}
function ready(c, items, next) {
  const s = c.dark("You're ready");
  items.forEach((t, i) => {
    s.addShape(c.pres.shapes.OVAL, { x: 0.6, y: 3.3 + i * 0.52, w: 0.4, h: 0.4, fill: { color: c.P.accent }, line: { color: c.P.accent } });
    s.addImage({ data: c._check, x: 0.67, y: 3.37 + i * 0.52, w: 0.26, h: 0.26 });
    s.addText(t, { isTextBox: true, x: 1.25, y: 3.3 + i * 0.52, w: 8.0, h: 0.4, fontFace: "Calibri", fontSize: 17, color: "FFFFFF", margin: 0, valign: "middle" });
  });
  c.text(s, `Next: ${next}`, { x: 0.6, y: 4.98, w: 8.6, h: 0.4, fontSize: 14, color: c.P.accent, bold: true });
}
function boxes(c, s, values, x, y, size, opts = {}) {
  values.forEach((v, i) => {
    const hi = opts.hi && opts.hi.includes(i);
    s.addShape(c.pres.shapes.ROUNDED_RECTANGLE, { x: x + i * (size + 0.08), y, w: size, h: size, rectRadius: 0.08,
      fill: { color: hi ? (opts.hiColor || c.P.accent) : "FFFFFF" }, line: { color: hi ? (opts.hiColor || c.P.accent) : "C9D3DC", width: 1.25 } });
    s.addText(String(v), { isTextBox: true, x: x + i * (size + 0.08), y, w: size, h: size, align: "center", valign: "middle",
      fontFace: "Calibri", fontSize: opts.fontSize || 18, bold: true, color: hi ? c.P.dark : c.P.text, margin: 0 });
    if (opts.index) s.addText(String(i), { isTextBox: true, x: x + i * (size + 0.08), y: y + size + 0.04, w: size, h: 0.25, align: "center",
      fontFace: "Calibri", fontSize: 10, color: c.P.muted, margin: 0 });
  });
}
async function withCheck(c) { if (!c._check) c._check = await require("./common").iconPng(fa.FaCheck, "FFFFFF"); }

// ---------- Before Kadane: arrays, subarrays, running sums ----------
const kadane = [
  async (c) => { preTitle(c, "Arrays, Subarrays and Running Sums", "The three ideas you need before Kadane's algorithm", "Kadane's algorithm (maximum subarray)"); },
  async (c) => {
    const s = c.light("An array and its indexes");
    boxes(c, s, [5, -2, 7, 3, -4, 6], 0.95, 1.45, 0.95, { index: true, fontSize: 22 });
    c.card(s, 0.55, 3.0, 8.9, 1.8, c.P.soft);
    c.bullets(s, ["An array is a list of values in a fixed order.", "Each value has an index, starting from 0: here arr[2] is 7.",
      "len(arr) is the number of values: 6."], { x: 0.85, y: 3.2, w: 8.3, h: 1.5, fontSize: 15 });
  },
  async (c) => {
    const s = c.light("What is a subarray?");
    const row = async (y, label, vals, hi, ok) => {
      boxes(c, s, vals, 0.75, y, 0.66, { hi, hiColor: ok ? c.P.accent2 : "E1A3A3", fontSize: 18 });
      await c.iconCircle(s, ok ? fa.FaCheck : fa.FaTimes, 5.4, y + 0.04, 0.58, ok ? c.P.accent2 : "C0392B", "FFFFFF");
      c.text(s, label, { x: 6.15, y: y + 0.04, w: 3.3, h: 0.6, fontSize: 15, color: c.P.text, valign: "middle" });
    };
    await row(1.35, "[-2, 7, 3]: next to each other", [5, -2, 7, 3, -4, 6], [1, 2, 3], true);
    await row(2.4, "[6]: one value counts too", [5, -2, 7, 3, -4, 6], [5], true);
    await row(3.45, "[5, 7]: skips -2, so not a subarray", [5, -2, 7, 3, -4, 6], [0, 2], false);
    c.text(s, "A subarray is a run of values that sit next to each other, with nothing skipped.", { x: 0.55, y: 4.55, w: 8.9, h: 0.45, fontSize: 14, color: c.P.muted, italic: true });
  },
  async (c) => {
    const s = c.light("How many subarrays are there?");
    const head = ["n (length)", "Subarrays"].map(t => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: c.P.dark }, align: "center" } }));
    const rows = [1, 2, 3, 4, 5, 9].map(n => [n, n * (n + 1) / 2].map(v => ({ text: String(v), options: { align: "center", bold: n === 9, color: n === 9 ? c.P.accent2 : c.P.text } })));
    s.addTable([head, ...rows], { x: 0.55, y: 1.3, w: 3.9, colW: [1.95, 1.95], rowH: 0.45, fontFace: "Calibri", fontSize: 15, border: { type: "solid", pt: 0.5, color: "DCE3E9" } });
    c.card(s, 4.85, 1.3, 4.6, 3.5, c.P.soft);
    s.addText("n (n + 1) / 2", { isTextBox: true, x: 5.15, y: 1.5, w: 4.0, h: 0.8, fontFace: "Courier New", fontSize: 28, bold: true, color: c.P.accent2, margin: 0 });
    c.text(s, "Pick where a subarray starts and where it ends. For 9 numbers that is 45 subarrays, and the count grows like n²: checking them all gets slow fast.",
      { x: 5.15, y: 2.45, w: 4.0, h: 2.2, fontSize: 15 });
  },
  async (c) => {
    const s = c.light("A running sum");
    boxes(c, s, [3, -1, 2, -5, 4], 0.95, 1.4, 0.85, { fontSize: 20 });
    c.text(s, "values", { x: 5.85, y: 1.65, w: 1.5, h: 0.4, fontSize: 13, color: c.P.muted });
    boxes(c, s, [3, 2, 4, -1, 3], 0.95, 2.55, 0.85, { hi: [0, 1, 2, 3, 4], hiColor: "D7EFEA", fontSize: 20 });
    c.text(s, "running sum", { x: 5.85, y: 2.8, w: 1.8, h: 0.4, fontSize: 13, color: c.P.muted });
    c.card(s, 0.55, 3.75, 8.9, 1.1, c.P.soft);
    c.text(s, "Each running sum is the previous one plus the next value: 3, then 3 - 1 = 2, then 2 + 2 = 4, then 4 - 5 = -1, then -1 + 4 = 3.",
      { x: 0.85, y: 3.85, w: 8.3, h: 0.9, fontSize: 15, valign: "middle" });
  },
  async (c) => {
    const s = c.light("max() picks the larger value");
    const ex = [["max(4, 9)", "9"], ["max(-3, 2)", "2"], ["max(-1, -6)", "-1"]];
    ex.forEach(([q, a], i) => {
      const x = 0.55 + i * 3.02;
      c.card(s, x, 1.3, 2.82, 2.0, c.P.soft);
      s.addText(q, { isTextBox: true, x: x + 0.3, y: 1.45, w: 2.3, h: 0.6, fontFace: "Courier New", fontSize: 20, bold: true, color: c.P.text, margin: 0 });
      s.addText(`= ${a}`, { isTextBox: true, x: x + 0.3, y: 2.2, w: 2.3, h: 0.8, fontFace: "Cambria", fontSize: 34, bold: true, color: c.P.accent2, margin: 0 });
    });
    c.card(s, 0.55, 3.6, 8.9, 1.2, c.P.dark);
    s.addText("Kadane's algorithm uses max() twice at every step: to choose whether to keep a running sum, and to remember the best one.",
      { isTextBox: true, x: 0.85, y: 3.6, w: 8.3, h: 1.2, fontFace: "Calibri", fontSize: 16, color: "FFFFFF", margin: 0, valign: "middle" });
  },
  async (c) => {
    const s = c.light("Reading Big-O: how work grows");
    const n = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    s.addChart(c.pres.charts.LINE, [{ name: "O(n)", labels: n.map(String), values: n }, { name: "O(n²)", labels: n.map(String), values: n.map(v => v * v) }],
      c.chartStyle({ x: 0.55, y: 1.25, w: 6.1, h: 3.75, chartColors: [c.P.accent2, "C0392B"], lineSize: 3, lineDataSymbolSize: 6, showLegend: true, legendPos: "b",
        legendFontFace: "Calibri", legendFontSize: 11, legendColor: c.P.muted, showTitle: true, title: "Steps needed as the input grows (n)" }));
    c.card(s, 6.95, 1.25, 2.5, 3.75, c.P.soft);
    c.stat(s, 7.15, 1.45, 2.2, "100", "steps for O(n²) at n = 10, against 10 for O(n)", "C0392B");
    c.text(s, "O(n) grows in step with the input. O(n²) grows with its square.", { x: 7.15, y: 3.05, w: 2.15, h: 1.7, fontSize: 13, color: c.P.muted });
  },
  async (c) => { await withCheck(c); ready(c, ["A subarray is a run of neighbours, nothing skipped", "A running sum adds one value at a time", "O(n) beats O(n²) as the input grows"], "Kadane's algorithm finds the best subarray in one pass"); },
];

// ---------- Before 1991: GDP, trade, exchange rates ----------
const india = [
  async (c) => { preTitle(c, "GDP, Trade and Exchange Rates", "The economics you need before India's 1991 reforms", "India's 1991 reforms: how opening up changed trade"); },
  async (c) => {
    const s = c.light("What is GDP?");
    c.card(s, 0.55, 1.3, 8.9, 1.2, c.P.dark);
    await c.iconCircle(s, fa.FaIndustry, 0.8, 1.48, 0.85, c.P.accent, "FFFFFF");
    s.addText([{ text: "GDP (Gross Domestic Product) ", options: { bold: true, color: c.P.accent } }, { text: "is the value of everything a country produces in a year.", options: { color: "FFFFFF" } }],
      { isTextBox: true, x: 1.9, y: 1.3, w: 7.3, h: 1.2, fontFace: "Calibri", fontSize: 17, margin: 0, valign: "middle" });
    const ex = [[fa.FaSeedling, "Farms", "Rice, wheat, milk"], [fa.FaCogs, "Factories", "Cars, cloth, medicines"], [fa.FaLaptopCode, "Services", "Banks, IT, teaching"]];
    for (let i = 0; i < 3; i++) {
      const x = 0.55 + i * 3.02;
      c.card(s, x, 2.8, 2.82, 2.0, c.P.soft);
      await c.iconCircle(s, ex[i][0], x + 0.3, 3.05, 0.7, c.P.accent2, "FFFFFF");
      s.addText(ex[i][1], { isTextBox: true, x: x + 1.15, y: 3.05, w: 1.6, h: 0.7, fontFace: "Cambria", fontSize: 17, bold: true, color: c.P.text, margin: 0, valign: "middle" });
      c.text(s, ex[i][2], { x: x + 0.3, y: 3.95, w: 2.3, h: 0.7, fontSize: 14, color: c.P.muted });
    }
  },
  async (c) => {
    const s = c.light("Exports and imports");
    const col = async (x, Ico, head, body, ex, colr) => {
      c.card(s, x, 1.3, 4.3, 3.5, c.P.soft);
      await c.iconCircle(s, Ico, x + 0.3, 1.55, 0.8, colr, "FFFFFF");
      s.addText(head, { isTextBox: true, x: x + 1.3, y: 1.55, w: 2.8, h: 0.8, fontFace: "Cambria", fontSize: 21, bold: true, color: c.P.text, margin: 0, valign: "middle" });
      c.text(s, body, { x: x + 0.3, y: 2.6, w: 3.7, h: 0.9, fontSize: 15 });
      c.text(s, ex, { x: x + 0.3, y: 3.6, w: 3.7, h: 1.0, fontSize: 14, color: c.P.muted, italic: true });
    };
    await col(0.55, fa.FaPlaneDeparture, "Exports", "Goods and services India sells to other countries.", "For example: IT services, medicines, rice.", c.P.accent2);
    await col(5.15, fa.FaPlaneArrival, "Imports", "Goods and services India buys from other countries.", "For example: crude oil, gold, electronics.", c.P.accent);
  },
  async (c) => {
    const s = c.light("Trade as a share of GDP");
    c.card(s, 0.55, 1.3, 8.9, 0.95, c.P.dark);
    s.addText("trade share  =  (exports + imports) / GDP  x  100", { isTextBox: true, x: 0.85, y: 1.3, w: 8.3, h: 0.95, fontFace: "Courier New", fontSize: 19, bold: true, color: "FFFFFF", margin: 0, valign: "middle" });
    const st = [["Exports", "₹23"], ["Imports", "₹27"], ["GDP", "₹100"]];
    st.forEach(([k, v], i) => {
      const x = 0.55 + i * 2.05;
      c.card(s, x, 2.6, 1.85, 1.3, c.P.soft);
      s.addText(k, { isTextBox: true, x: x + 0.2, y: 2.7, w: 1.5, h: 0.35, fontFace: "Calibri", fontSize: 13, color: c.P.muted, margin: 0 });
      s.addText(v, { isTextBox: true, x: x + 0.2, y: 3.05, w: 1.5, h: 0.7, fontFace: "Cambria", fontSize: 28, bold: true, color: c.P.text, margin: 0 });
    });
    c.card(s, 6.75, 2.6, 2.7, 1.3, c.P.dark);
    s.addText("= 50%", { isTextBox: true, x: 6.95, y: 2.6, w: 2.3, h: 1.3, fontFace: "Cambria", fontSize: 34, bold: true, color: c.P.accent, margin: 0, valign: "middle" });
    c.text(s, "A bigger share means the economy is more open: more of what it makes and uses crosses its borders.", { x: 0.55, y: 4.25, w: 8.9, h: 0.6, fontSize: 14, color: c.P.muted, italic: true });
  },
  async (c) => {
    const s = c.light("Exchange rates and devaluation");
    const col = (x, head, rate, price, colr) => {
      c.card(s, x, 1.3, 4.3, 2.4, c.P.soft);
      s.addText(head, { isTextBox: true, x: x + 0.3, y: 1.45, w: 3.7, h: 0.45, fontFace: "Cambria", fontSize: 18, bold: true, color: c.P.text, margin: 0 });
      s.addText(rate, { isTextBox: true, x: x + 0.3, y: 1.95, w: 3.7, h: 0.6, fontFace: "Courier New", fontSize: 20, bold: true, color: colr, margin: 0 });
      c.text(s, price, { x: x + 0.3, y: 2.65, w: 3.7, h: 0.95, fontSize: 15 });
    };
    col(0.55, "Before", "₹20 = $1", "An Indian shirt costing ₹500 sells abroad for $25.", c.P.text);
    col(5.15, "After devaluation", "₹25 = $1", "The same ₹500 shirt now sells for only $20.", c.P.accent2);
    c.card(s, 0.55, 3.95, 8.9, 0.9, c.P.dark);
    s.addText("A devalued rupee makes India's exports cheaper abroad, and imports dearer at home. (Illustrative numbers.)",
      { isTextBox: true, x: 0.85, y: 3.95, w: 8.3, h: 0.9, fontFace: "Calibri", fontSize: 15, color: "FFFFFF", margin: 0, valign: "middle" });
  },
  async (c) => {
    const s = c.light("Tariffs: a tax on imports");
    s.addChart(c.pres.charts.BAR, [{ name: "Price in India (₹)", labels: ["No duty", "50% duty", "150% duty"], values: [1000, 1500, 2500] }],
      c.chartStyle({ x: 0.55, y: 1.25, w: 5.9, h: 3.75, barDir: "col", chartColors: [c.P.accent], showValue: true, dataLabelPosition: "outEnd",
        showTitle: true, title: "A ₹1,000 imported machine, after duty (₹)", valAxisMaxVal: 3000, barGapWidthPct: 70 }));
    c.card(s, 6.75, 1.25, 2.7, 3.75, c.P.soft);
    c.stat(s, 6.95, 1.45, 2.4, "2.5x", "the price with a 150% duty", c.P.accent2);
    c.text(s, "High duties protect local firms, but make imported machines and inputs expensive.", { x: 6.95, y: 3.0, w: 2.35, h: 1.8, fontSize: 13, color: c.P.muted });
  },
  async (c) => {
    const s = c.light("Percentage change");
    c.card(s, 0.55, 1.3, 8.9, 0.9, c.P.dark);
    s.addText("% change  =  (new - old) / old  x  100", { isTextBox: true, x: 0.85, y: 1.3, w: 8.3, h: 0.9, fontFace: "Courier New", fontSize: 21, bold: true, color: "FFFFFF", margin: 0, valign: "middle" });
    const steps = [["Old 40, new 50", "50 - 40 = 10"], ["Divide by old", "10 / 40 = 0.25"], ["Times 100", "0.25 x 100 = 25%"]];
    steps.forEach(([h1, calc], i) => {
      const x = 0.55 + i * 3.02;
      c.card(s, x, 2.5, 2.82, 2.3, c.P.soft);
      s.addText(h1, { isTextBox: true, x: x + 0.25, y: 2.65, w: 2.4, h: 0.5, fontFace: "Calibri", fontSize: 15, bold: true, color: c.P.text, margin: 0 });
      s.addText(calc, { isTextBox: true, x: x + 0.25, y: 3.4, w: 2.45, h: 0.9, fontFace: "Courier New", fontSize: 15, bold: true, color: i === 2 ? c.P.accent2 : c.P.text, margin: 0, valign: "middle" });
    });
  },
  async (c) => { await withCheck(c); ready(c, ["GDP is everything a country produces in a year", "Trade share = (exports + imports) / GDP", "Devaluation makes exports cheaper; tariffs make imports dearer"], "India's 1991 crisis and the reforms that opened it up"); },
];

// ---------- Before projectile motion: vectors, sin and cos, motion under gravity ----------
const physics = [
  async (c) => { preTitle(c, "Vectors, Sine and Cosine", "The maths and motion you need before projectile motion", "Projectile motion: why 45° goes farthest"); },
  async (c) => {
    const s = c.light("Scalars and vectors");
    const col = async (x, Ico, head, body, ex, colr) => {
      c.card(s, x, 1.3, 4.3, 3.5, c.P.soft);
      await c.iconCircle(s, Ico, x + 0.3, 1.55, 0.8, colr, "FFFFFF");
      s.addText(head, { isTextBox: true, x: x + 1.3, y: 1.55, w: 2.8, h: 0.8, fontFace: "Cambria", fontSize: 21, bold: true, color: c.P.text, margin: 0, valign: "middle" });
      c.text(s, body, { x: x + 0.3, y: 2.6, w: 3.7, h: 0.9, fontSize: 15 });
      c.text(s, ex, { x: x + 0.3, y: 3.6, w: 3.7, h: 1.0, fontSize: 14, color: c.P.muted, italic: true });
    };
    await col(0.55, fa.FaTachometerAlt, "Scalar", "Has only a size.", "Speed: 20 m/s. Mass: 2 kg. Time: 3 s.", c.P.accent2);
    await col(5.15, fa.FaLocationArrow, "Vector", "Has a size and a direction.", "Velocity: 20 m/s at 30° above the ground.", c.P.accent);
  },
  async (c) => {
    const s = c.light("A right triangle: sine and cosine");
    const ox = 1.0, oy = 4.5, bx = 3.6, by = 1.9;
    s.addShape(c.pres.shapes.LINE, { x: ox, y: by, w: bx, h: oy - by, flipV: true, line: { color: c.P.accent, width: 3.5 } });
    s.addShape(c.pres.shapes.LINE, { x: ox, y: oy, w: bx, h: 0, line: { color: c.P.accent2, width: 3 } });
    s.addShape(c.pres.shapes.LINE, { x: ox + bx, y: by, w: 0, h: oy - by, line: { color: "C0392B", width: 3 } });
    s.addText("hypotenuse", { isTextBox: true, x: 1.55, y: 2.65, w: 1.8, h: 0.4, fontFace: "Calibri", fontSize: 15, bold: true, color: c.P.accent, margin: 0, rotate: -36 });
    s.addText("adjacent", { isTextBox: true, x: 2.2, y: 4.6, w: 1.6, h: 0.35, fontFace: "Calibri", fontSize: 15, bold: true, color: c.P.accent2, margin: 0 });
    s.addText("opposite", { isTextBox: true, x: 4.75, y: 3.0, w: 1.3, h: 0.35, fontFace: "Calibri", fontSize: 15, bold: true, color: "C0392B", margin: 0 });
    s.addText("θ", { isTextBox: true, x: 1.55, y: 4.1, w: 0.4, h: 0.35, fontFace: "Cambria", fontSize: 18, bold: true, italic: true, color: c.P.text, margin: 0 });
    c.card(s, 6.3, 1.3, 3.15, 3.5, c.P.soft);
    s.addText("sin θ =\nopposite / hypotenuse", { isTextBox: true, x: 6.55, y: 1.55, w: 2.75, h: 0.8, fontFace: "Courier New", fontSize: 14, bold: true, color: "C0392B", margin: 0 });
    s.addText("cos θ =\nadjacent / hypotenuse", { isTextBox: true, x: 6.55, y: 2.55, w: 2.75, h: 0.8, fontFace: "Courier New", fontSize: 14, bold: true, color: c.P.accent2, margin: 0 });
    c.text(s, "θ is the angle at the bottom left corner.", { x: 6.55, y: 3.6, w: 2.75, h: 0.9, fontSize: 13, color: c.P.muted });
  },
  async (c) => {
    const s = c.light("Values you will use");
    const head = ["θ", "0°", "30°", "45°", "60°", "90°"].map(t => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: c.P.dark }, align: "center" } }));
    const row = (name, vals, colr) => [{ text: name, options: { bold: true, color: colr, align: "center" } }, ...vals.map(v => ({ text: v, options: { align: "center", color: c.P.text } }))];
    s.addTable([head, row("sin θ", ["0", "0.5", "0.707", "0.866", "1"], "C0392B"), row("cos θ", ["1", "0.866", "0.707", "0.5", "0"], c.P.accent2)],
      { x: 0.55, y: 1.35, w: 8.65, colW: [1.4, 1.45, 1.45, 1.45, 1.45, 1.45], rowH: 0.6, fontFace: "Calibri", fontSize: 18, border: { type: "solid", pt: 0.5, color: "D7DFEA" } });
    c.card(s, 0.55, 3.45, 8.9, 1.35, c.P.soft);
    c.bullets(s, ["sin rises from 0 to 1 as the angle grows; cos falls from 1 to 0.", "sin 30° = cos 60° and sin 60° = cos 30°: angles that add up to 90° swap values."],
      { x: 0.85, y: 3.6, w: 8.3, h: 1.1, fontSize: 15 });
  },
  async (c) => {
    const s = c.light("Splitting a vector into two parts");
    const ox = 1.0, oy = 4.5, bx = 3.5, by = 2.5;
    s.addShape(c.pres.shapes.LINE, { x: ox, y: by, w: bx, h: oy - by, flipV: true, line: { color: c.P.accent, width: 3.5, endArrowType: "triangle" } });
    s.addShape(c.pres.shapes.LINE, { x: ox, y: oy, w: bx, h: 0, line: { color: c.P.accent2, width: 2.5, endArrowType: "triangle", dashType: "dash" } });
    s.addShape(c.pres.shapes.LINE, { x: ox + bx, y: by, w: 0, h: oy - by, flipV: true, line: { color: "C0392B", width: 2.5, endArrowType: "triangle", dashType: "dash" } });
    s.addText("10 m/s at 30°", { isTextBox: true, x: 1.3, y: 2.95, w: 2.2, h: 0.4, fontFace: "Calibri", fontSize: 15, bold: true, color: c.P.accent, margin: 0 });
    s.addText("10 cos 30° = 8.66 m/s", { isTextBox: true, x: 1.4, y: 4.6, w: 3.2, h: 0.35, fontFace: "Courier New", fontSize: 13, bold: true, color: c.P.accent2, margin: 0 });
    s.addText("10 sin 30° = 5 m/s", { isTextBox: true, x: 4.65, y: 3.3, w: 2.2, h: 0.35, fontFace: "Courier New", fontSize: 13, bold: true, color: "C0392B", margin: 0 });
    c.card(s, 6.95, 1.3, 2.5, 3.5, c.P.soft);
    c.text(s, "Any slanted velocity can be split into a sideways part and an upward part. Each part can then be worked out on its own.",
      { x: 7.15, y: 1.5, w: 2.15, h: 3.1, fontSize: 14 });
  },
  async (c) => {
    const s = c.light("Thrown straight up: gravity at work");
    const t = [0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];
    s.addChart(c.pres.charts.LINE, [{ name: "Height (m)", labels: t.map(v => `${v}s`), values: t.map(v => +(10 * v - 4.9 * v * v).toFixed(2)) }],
      c.chartStyle({ x: 0.55, y: 1.25, w: 6.1, h: 3.75, chartColors: [c.P.accent], lineSize: 3, lineDataSymbolSize: 7, lineSmooth: true,
        showTitle: true, title: "A ball thrown up at 10 m/s: height against time", valAxisMinVal: 0, valAxisMaxVal: 6 }));
    c.card(s, 6.95, 1.25, 2.5, 3.75, c.P.soft);
    c.stat(s, 7.15, 1.45, 2.2, "1.02 s", "to reach the top (10 / 9.8)", c.P.accent2);
    c.text(s, "Gravity takes 9.8 m/s off the upward speed every second, then speeds it back up on the way down.", { x: 7.15, y: 3.0, w: 2.15, h: 1.85, fontSize: 13, color: c.P.muted });
  },
  async (c) => {
    const s = c.light("The equations of motion");
    const f = [["Speed after time t", "v = u + a t"], ["Distance in time t", "s = u t + ½ a t²"], ["Speed after distance s", "v² = u² + 2 a s"]];
    f.forEach(([head, eq], i) => {
      const x = 0.55 + i * 3.02;
      c.card(s, x, 1.3, 2.82, 2.6, i === 1 ? c.P.dark : c.P.soft);
      s.addText(head, { isTextBox: true, x: x + 0.3, y: 1.5, w: 2.3, h: 0.6, fontFace: "Cambria", fontSize: 16, bold: true, color: i === 1 ? "FFFFFF" : c.P.text, margin: 0 });
      s.addText(eq, { isTextBox: true, x: x + 0.25, y: 2.4, w: 2.45, h: 1.0, fontFace: "Courier New", fontSize: 17, bold: true, color: i === 1 ? c.P.accent : c.P.accent2, margin: 0, valign: "middle" });
    });
    c.text(s, "u = starting speed, v = final speed, a = acceleration (for gravity, a = -9.8 m/s² going up), t = time, s = distance.", { x: 0.55, y: 4.2, w: 8.9, h: 0.6, fontSize: 13, color: c.P.muted, italic: true });
  },
  async (c) => { await withCheck(c); ready(c, ["A vector has a size and a direction", "sin and cos split a vector into two parts", "Gravity changes the up-down speed by 9.8 m/s each second"], "Projectile motion: both motions at once"); },
];

const decks = { kadane: [kadane, "Arrays, Subarrays and Running Sums"], india: [india, "GDP, Trade and Exchange Rates"], physics: [physics, "Vectors, Sine and Cosine"] };
module.exports = (name) => (file, only = null) => buildDeck({ file, title: decks[name][1], P: PAL[name], slides: decks[name][0], only });
if (require.main === module) {
  (async () => { for (const n of Object.keys(decks)) await module.exports(n)(`pre_${n}.pptx`).then(f => console.log("wrote", f)); })();
}
