const { buildDeck } = require("./common");
const fa = require("react-icons/fa");

const P = { dark: "13203B", accent: "F28C28", accent2: "3A8FD9", soft: "EAF2FB", text: "1C2533", muted: "5B6577" };
const G = 9.8, U = 20;
const range = (deg) => U * U * Math.sin((2 * deg * Math.PI) / 180) / G;

// A throw's path: a parabola from (x, base) to (x + w, base) peaking h above base, drawn as many short lines.
function arc(c, s, x, base, w, h, color, width = 3, dash = "solid") {
  const N = 32, pts = [];
  for (let k = 0; k <= N; k++) {
    const t = k / N;
    pts.push({ x: t * w, y: h - 4 * h * t * (1 - t) });
  }
  s.addShape(c.pres.shapes.CUSTOM_GEOMETRY, { x, y: base - h, w, h, points: pts, line: { color, width, dashType: dash }, fill: { type: "none" } });
}
function ground(c, s, x, y, w, color = "B8C4D6") {
  s.addShape(c.pres.shapes.LINE, { x, y, w, h: 0, line: { color, width: 2 } });
}

const slides = [
  // 1. Title
  async (c) => {
    const s = c.dark("Projectile Motion");
    c.text(s, "Why a 45° throw goes the farthest", { x: 0.6, y: 3.15, w: 6, h: 0.5, fontSize: 20, color: "C7D3EA" });
    ground(c, s, 5.6, 4.9, 3.9, "3A4A6B");
    arc(c, s, 5.7, 4.9, 3.6, 1.5, P.accent, 3.5);
    arc(c, s, 5.7, 4.9, 3.1, 0.85, "5E7299", 2, "dash");
    arc(c, s, 5.7, 4.9, 3.1, 2.4, "5E7299", 2, "dash");
    s.addText("45°", { isTextBox: true, x: 7.2, y: 2.95, w: 0.9, h: 0.4, fontFace: "Cambria", fontSize: 18, bold: true, color: P.accent, margin: 0 });
  },
  // 2. What is a projectile
  async (c) => {
    const s = c.light("What is a projectile?");
    c.card(s, 0.55, 1.25, 8.9, 0.85, c.P.soft);
    s.addText([{ text: "A projectile ", options: { bold: true } }, { text: "is anything thrown or launched that then moves under gravity alone." }],
      { isTextBox: true, x: 0.85, y: 1.25, w: 8.3, h: 0.85, fontFace: "Calibri", fontSize: 17, color: P.text, margin: 0, valign: "middle" });
    const items = [[fa.FaBaseballBall, "A cricket throw", "The fielder's throw to the keeper."], [fa.FaFutbol, "A football kick", "A long kick down the field."], [fa.FaTint, "Water from a hose", "Every drop follows a curved path."]];
    for (let i = 0; i < 3; i++) {
      const x = 0.55 + i * 3.02;
      c.card(s, x, 2.4, 2.82, 2.4, "FFFFFF", { shadow: true });
      await c.iconCircle(s, items[i][0], x + 0.3, 2.65, 0.8, P.dark, P.accent);
      s.addText(items[i][1], { isTextBox: true, x: x + 1.25, y: 2.65, w: 1.45, h: 0.8, fontFace: "Cambria", fontSize: 16, bold: true, color: P.text, margin: 0, valign: "middle" });
      c.text(s, items[i][2], { x: x + 0.3, y: 3.65, w: 2.3, h: 1.0, fontSize: 14, color: P.muted });
    }
  },
  // 3. Two motions
  async (c) => {
    const s = c.light("Two motions at the same time");
    ground(c, s, 0.55, 4.75, 5.2);
    arc(c, s, 0.75, 4.75, 4.8, 2.6, P.accent, 3);
    // velocity components at three points: horizontal stays the same, vertical shrinks then reverses
    const pts = [[1.05, 3.85, -0.55], [3.15, 2.15, 0], [5.25, 3.85, 0.55]];
    pts.forEach(([x, y, vy]) => {
      s.addShape(c.pres.shapes.LINE, { x, y, w: 0.6, h: 0, line: { color: P.accent2, width: 2.5, endArrowType: "triangle" } });
      if (vy) s.addShape(c.pres.shapes.LINE, { x, y: vy < 0 ? y + vy : y, w: 0, h: Math.abs(vy), line: { color: "C0392B", width: 2.5,
        endArrowType: vy < 0 ? undefined : "triangle", beginArrowType: vy < 0 ? "triangle" : undefined } });
    });
    c.card(s, 6.1, 1.3, 3.35, 1.65, c.P.soft);
    s.addText("Sideways", { isTextBox: true, x: 6.35, y: 1.42, w: 2.9, h: 0.4, fontFace: "Cambria", fontSize: 17, bold: true, color: P.accent2, margin: 0 });
    c.text(s, "Same speed all the way: nothing pushes or pulls sideways.", { x: 6.35, y: 1.85, w: 2.9, h: 1.0, fontSize: 14, color: P.text });
    c.card(s, 6.1, 3.15, 3.35, 1.65, "FBEAEA");
    s.addText("Up and down", { isTextBox: true, x: 6.35, y: 3.27, w: 2.9, h: 0.4, fontFace: "Cambria", fontSize: 17, bold: true, color: "C0392B", margin: 0 });
    c.text(s, "Gravity slows it going up and speeds it coming down: g = 9.8 m/s².", { x: 6.35, y: 3.7, w: 2.9, h: 1.0, fontSize: 14, color: P.text });
  },
  // 4. Components
  async (c) => {
    const s = c.light("Splitting the launch speed");
    // right triangle: u along the slope, ux along the ground, uy upwards
    const ox = 1.0, oy = 4.6, bx = 3.6, by = 2.1;
    s.addShape(c.pres.shapes.LINE, { x: ox, y: by, w: bx, h: oy - by, flipV: true, line: { color: P.accent, width: 3.5, endArrowType: "triangle" } });
    s.addShape(c.pres.shapes.LINE, { x: ox, y: oy, w: bx, h: 0, line: { color: P.accent2, width: 2.5, endArrowType: "triangle" } });
    s.addShape(c.pres.shapes.LINE, { x: ox + bx, y: by, w: 0, h: oy - by, flipV: true, line: { color: "C0392B", width: 2.5, endArrowType: "triangle" } });
    s.addText("u", { isTextBox: true, x: 2.3, y: 2.75, w: 0.5, h: 0.4, fontFace: "Cambria", fontSize: 22, bold: true, italic: true, color: P.accent, margin: 0 });
    s.addText("ux = u cos θ", { isTextBox: true, x: 1.7, y: 4.7, w: 2.4, h: 0.4, fontFace: "Courier New", fontSize: 16, bold: true, color: P.accent2, margin: 0 });
    s.addText("uy = u sin θ", { isTextBox: true, x: 4.75, y: 3.15, w: 2.0, h: 0.4, fontFace: "Courier New", fontSize: 16, bold: true, color: "C0392B", margin: 0 });
    s.addText("θ", { isTextBox: true, x: 1.55, y: 4.2, w: 0.4, h: 0.35, fontFace: "Cambria", fontSize: 18, bold: true, italic: true, color: P.text, margin: 0 });
    c.card(s, 6.6, 1.3, 2.85, 3.5, c.P.soft);
    s.addText("For u = 20 m/s at 30°", { isTextBox: true, x: 6.85, y: 1.45, w: 2.45, h: 0.6, fontFace: "Cambria", fontSize: 16, bold: true, color: P.text, margin: 0 });
    c.stat(s, 6.85, 2.05, 2.45, "17.3", "m/s sideways (20 x cos 30°)", P.accent2);
    c.stat(s, 6.85, 3.25, 2.45, "10", "m/s upwards (20 x sin 30°)", "C0392B");
  },
  // 5. Three formulas
  async (c) => {
    const s = c.light("Three formulas for a throw");
    const f = [["Time in the air", "T = 2u sin θ / g", fa.FaStopwatch, P.dark], ["Highest point", "H = u² sin² θ / 2g", fa.FaArrowUp, P.dark], ["Range (how far)", "R = u² sin 2θ / g", fa.FaRulerHorizontal, P.accent]];
    for (let i = 0; i < 3; i++) {
      const x = 0.55 + i * 3.02, hi = i === 2;
      c.card(s, x, 1.3, 2.82, 3.5, hi ? P.dark : c.P.soft);
      await c.iconCircle(s, f[i][2], x + 0.3, 1.55, 0.8, hi ? P.accent : P.dark, "FFFFFF");
      s.addText(f[i][0], { isTextBox: true, x: x + 0.3, y: 2.55, w: 2.3, h: 0.5, fontFace: "Cambria", fontSize: 17, bold: true, color: hi ? "FFFFFF" : P.text, margin: 0 });
      s.addText(f[i][1], { isTextBox: true, x: x + 0.22, y: 3.2, w: 2.5, h: 0.9, fontFace: "Courier New", fontSize: 14, bold: true, color: hi ? P.accent : P.accent2, margin: 0, valign: "middle" });
    }
    c.source(s, "u = launch speed, θ = launch angle, g = 9.8 m/s². Launch and landing at the same height; no air resistance.");
  },
  // 6. Derivation
  async (c) => {
    const s = c.light("Where the range formula comes from");
    const st = [["Time in the air", "T = 2u sin θ / g"], ["Distance = sideways speed x time", "R = u cos θ x 2u sin θ / g"], ["Use 2 sin θ cos θ = sin 2θ", "R = u² sin 2θ / g"]];
    st.forEach(([head, eq], i) => {
      const y = 1.3 + i * 1.2;
      c.card(s, 0.55, y, 8.9, 1.0, i === 2 ? P.dark : c.P.soft);
      s.addShape(c.pres.shapes.OVAL, { x: 0.8, y: y + 0.25, w: 0.5, h: 0.5, fill: { color: P.accent }, line: { color: P.accent } });
      s.addText(String(i + 1), { isTextBox: true, x: 0.8, y: y + 0.25, w: 0.5, h: 0.5, align: "center", valign: "middle", fontFace: "Cambria", fontSize: 18, bold: true, color: "FFFFFF", margin: 0 });
      s.addText(head, { isTextBox: true, x: 1.55, y, w: 3.6, h: 1.0, fontFace: "Calibri", fontSize: 16, bold: true, color: i === 2 ? "FFFFFF" : P.text, margin: 0, valign: "middle" });
      s.addText(eq, { isTextBox: true, x: 5.2, y, w: 4.1, h: 1.0, fontFace: "Courier New", fontSize: 17, bold: true, color: i === 2 ? P.accent : P.accent2, margin: 0, valign: "middle" });
    });
  },
  // 7. Worked example
  async (c) => {
    const s = c.light("Worked example: u = 20 m/s at 30°");
    const cards = [["Range", "R = 400 x sin 60° / 9.8", "35.3 m", P.accent], ["Time in the air", "T = 2 x 20 x sin 30° / 9.8", "2.04 s", P.accent2], ["Highest point", "H = 400 x sin² 30° / 19.6", "5.1 m", P.accent2]];
    cards.forEach(([head, calc, ans, colr], i) => {
      const x = 0.55 + i * 3.02;
      c.card(s, x, 1.3, 2.82, 3.5, i === 0 ? P.dark : c.P.soft);
      s.addText(head, { isTextBox: true, x: x + 0.3, y: 1.5, w: 2.3, h: 0.45, fontFace: "Cambria", fontSize: 17, bold: true, color: i === 0 ? "FFFFFF" : P.text, margin: 0 });
      s.addText(calc, { isTextBox: true, x: x + 0.22, y: 2.1, w: 2.5, h: 0.9, fontFace: "Courier New", fontSize: 11.5, color: i === 0 ? "C7D3EA" : P.muted, margin: 0, valign: "top" });
      s.addText(ans, { isTextBox: true, x: x + 0.3, y: 3.3, w: 2.3, h: 0.9, fontFace: "Cambria", fontSize: 36, bold: true, color: colr, margin: 0, valign: "middle" });
    });
    c.source(s, "sin 30° = 0.5, sin 60° = 0.866, u² = 400.");
  },
  // 8. Table
  async (c) => {
    const s = c.light("Same speed, different angles");
    const angles = [15, 30, 45, 60, 75];
    const head = ["Angle θ", "2θ", "sin 2θ", "Range R"].map(t => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: P.dark }, align: "center" } }));
    const rows = angles.map((a, i) => {
      const best = a === 45;
      const cell = (t) => ({ text: t, options: { align: "center", bold: best, color: best ? P.accent : P.text, fill: { color: best ? "FDF0E3" : (i % 2 ? "F5F8FC" : "FFFFFF") } } });
      return [cell(`${a}°`), cell(`${2 * a}°`), cell(Math.sin((2 * a * Math.PI) / 180).toFixed(3)), cell(`${range(a).toFixed(1)} m`)];
    });
    s.addTable([head, ...rows], { x: 0.55, y: 1.3, w: 5.4, colW: [1.25, 1.1, 1.35, 1.7], rowH: 0.5, fontFace: "Calibri", fontSize: 15, border: { type: "solid", pt: 0.5, color: "D7DFEA" } });
    c.card(s, 6.3, 1.3, 3.15, 3.0, c.P.soft);
    c.stat(s, 6.55, 1.45, 2.8, "40.8 m", "the farthest, at 45°", P.accent);
    c.text(s, "15° and 75° land at the same spot, and so do 30° and 60°.", { x: 6.55, y: 3.0, w: 2.75, h: 1.2, fontSize: 14, color: P.muted });
  },
  // 9. Chart
  async (c) => {
    const s = c.light("Range against launch angle");
    const ang = [0, 15, 30, 45, 60, 75, 90];
    s.addChart(c.pres.charts.LINE, [{ name: "Range (m)", labels: ang.map(a => `${a}°`), values: ang.map(a => +range(a).toFixed(1)) }],
      c.chartStyle({ x: 0.55, y: 1.25, w: 6.2, h: 3.75, chartColors: [P.accent], lineSize: 3, lineDataSymbolSize: 8, showValue: true, dataLabelPosition: "t",
        showTitle: true, title: "Range for u = 20 m/s (no air resistance)", valAxisMinVal: 0, valAxisMaxVal: 50, lineSmooth: true }));
    c.card(s, 7.05, 1.25, 2.4, 3.75, c.P.soft);
    c.stat(s, 7.25, 1.45, 2.1, "45°", "the peak of the curve", P.accent);
    c.text(s, "The curve is symmetric: angles that add up to 90° give the same range.", { x: 7.25, y: 3.0, w: 2.05, h: 1.8, fontSize: 13, color: P.muted });
  },
  // 10. Why 45
  async (c) => {
    const s = c.light("Why 45° wins");
    ground(c, s, 0.55, 4.7, 5.6);
    const scale = 5.2 / range(45);
    // heights in the real ratio 1 : 2 : 3 (5.1 m, 10.2 m, 15.3 m)
    arc(c, s, 0.65, 4.7, range(30) * scale, 0.9, P.accent2, 2.5);
    arc(c, s, 0.65, 4.7, range(60) * scale, 2.7, "8E5BD8", 2.5);
    arc(c, s, 0.65, 4.7, range(45) * scale, 1.8, P.accent, 3.5);
    [["30°", P.accent2, 2.6, 3.95], ["60°", "8E5BD8", 2.3, 1.65], ["45°", P.accent, 4.9, 3.0]].forEach(([t, col, x, y]) =>
      s.addText(t, { isTextBox: true, x, y, w: 0.7, h: 0.35, fontFace: "Cambria", fontSize: 16, bold: true, color: col, margin: 0 }));
    c.card(s, 6.45, 1.3, 3.0, 3.5, c.P.soft);
    c.bullets(s, ["R depends on sin 2θ.", "sin 2θ is largest (= 1) when 2θ = 90°, so θ = 45°.", "30° and 60° both give 35.3 m: same sin 2θ."], { x: 6.7, y: 1.5, w: 2.6, h: 3.2, fontSize: 14 });
  },
  // 11. Real sport
  async (c) => {
    const s = c.light("In real sport, a bit less than 45°");
    const items = [[fa.FaWind, "Air resistance", "Drag slows the ball, so a lower, faster path loses less distance."],
      [fa.FaChild, "Release height", "Throwers release above the ground, which also favours a lower angle."],
      [fa.FaBullseye, "So in practice", "The best angle is usually somewhat below 45°."]];
    for (let i = 0; i < 3; i++) {
      const y = 1.3 + i * 1.18;
      c.card(s, 0.55, y, 8.9, 1.0, i === 2 ? P.dark : c.P.soft);
      await c.iconCircle(s, items[i][0], 0.8, y + 0.15, 0.7, i === 2 ? P.accent : P.dark, "FFFFFF");
      s.addText(items[i][1], { isTextBox: true, x: 1.75, y, w: 2.3, h: 1.0, fontFace: "Cambria", fontSize: 17, bold: true, color: i === 2 ? "FFFFFF" : P.text, margin: 0, valign: "middle" });
      s.addText(items[i][2], { isTextBox: true, x: 4.1, y, w: 5.15, h: 1.0, fontFace: "Calibri", fontSize: 15, color: i === 2 ? "C7D3EA" : P.muted, margin: 0, valign: "middle" });
    }
  },
  // 12. Takeaways
  async (c) => {
    const s = c.dark("Takeaways");
    const pts = ["Sideways speed stays the same; gravity changes the up-down speed.", "Range R = u² sin 2θ / g.", "45° gives the farthest range; 30° and 60° tie."];
    pts.forEach((t, i) => {
      s.addShape(c.pres.shapes.OVAL, { x: 0.6, y: 3.25 + i * 0.68, w: 0.48, h: 0.48, fill: { color: P.accent }, line: { color: P.accent } });
      s.addText(String(i + 1), { isTextBox: true, x: 0.6, y: 3.25 + i * 0.68, w: 0.48, h: 0.48, align: "center", valign: "middle", fontFace: "Cambria", fontSize: 18, bold: true, color: "FFFFFF", margin: 0 });
      s.addText(t, { isTextBox: true, x: 1.3, y: 3.25 + i * 0.68, w: 8.0, h: 0.48, fontFace: "Calibri", fontSize: 18, color: "FFFFFF", margin: 0, valign: "middle" });
    });
  },
];

module.exports = (file, only = null) => buildDeck({ file, title: "Projectile Motion", P, slides, only });
if (require.main === module) module.exports(process.argv[2] || "projectile.pptx").then(f => console.log("wrote", f));
