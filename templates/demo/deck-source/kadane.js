const { buildDeck } = require("./common");
const fa = require("react-icons/fa");

const P = { dark: "17202A", accent: "F2B134", accent2: "1E9E8C", soft: "EEF4F3", text: "1F2A33", muted: "5F6B76" };
const ARR = [-2, 1, -3, 4, -1, 2, 1, -5, 4];
const CUR = [-2, 1, -2, 4, 3, 5, 6, 1, 5];
const BEST = [-2, 1, 1, 4, 4, 5, 6, 6, 6];

function arrayRow(c, s, values, x, y, size, hiFrom = -1, hiTo = -1, opts = {}) {
  values.forEach((v, i) => {
    const hi = i >= hiFrom && i <= hiTo;
    const fill = hi ? P.accent : (opts.dark ? "2A3644" : "FFFFFF");
    s.addShape(c.pres.shapes.ROUNDED_RECTANGLE, { x: x + i * (size + 0.08), y, w: size, h: size, rectRadius: 0.08,
      fill: { color: fill }, line: { color: hi ? P.accent : (opts.dark ? "3A4756" : "C9D3DC"), width: 1.25 } });
    s.addText(String(v), { isTextBox: true, x: x + i * (size + 0.08), y, w: size, h: size, align: "center", valign: "middle",
      fontFace: "Calibri", fontSize: opts.fontSize || 18, bold: true, color: hi ? P.dark : (opts.dark ? "FFFFFF" : P.text), margin: 0 });
    if (opts.index) s.addText(String(i), { isTextBox: true, x: x + i * (size + 0.08), y: y + size + 0.04, w: size, h: 0.25, align: "center",
      fontFace: "Calibri", fontSize: 10, color: P.muted, margin: 0 });
  });
}

const slides = [
  // 1. Title
  async (c) => {
    const s = c.dark("Kadane's Algorithm");
    c.text(s, "The maximum subarray sum, in a single pass", { x: 0.6, y: 3.15, w: 8.5, h: 0.5, fontSize: 20, color: "C9D6E2" });
    arrayRow(c, s, ARR, 0.6, 4.05, 0.62, 3, 6, { dark: true, fontSize: 16 });
    s.addText("= 6", { isTextBox: true, x: 7.05, y: 4.05, w: 1.2, h: 0.62, fontFace: "Cambria", fontSize: 26, bold: true, color: P.accent, margin: 0, valign: "middle" });
    s.addNotes("Title slide. One problem, explained in depth: the largest sum of a run of consecutive numbers.");
  },
  // 2. The problem
  async (c) => {
    const s = c.light("The problem");
    c.text(s, "Given an array of numbers, find the contiguous stretch whose sum is largest.", { x: 0.55, y: 1.25, w: 8.9, h: 0.5, fontSize: 17 });
    arrayRow(c, s, ARR, 0.95, 2.05, 0.82, 3, 6, { index: true, fontSize: 20 });
    c.card(s, 0.95, 3.55, 8.1, 1.25, c.P.soft);
    s.addText([
      { text: "Best subarray: ", options: { bold: true } }, { text: "[4, -1, 2, 1]", options: { fontFace: "Courier New", bold: true, color: P.accent2 } },
      { text: "   (indices 3 to 6)", options: { color: P.muted } },
    ], { isTextBox: true, x: 1.2, y: 3.68, w: 7.6, h: 0.45, fontFace: "Calibri", fontSize: 17, color: P.text, margin: 0 });
    s.addText([{ text: "Its sum: ", options: { bold: true } }, { text: "4 - 1 + 2 + 1 = 6", options: { fontFace: "Courier New" } },
      { text: ". No other run adds up to more.", options: { color: P.muted } }],
      { isTextBox: true, x: 1.2, y: 4.18, w: 7.6, h: 0.45, fontFace: "Calibri", fontSize: 17, color: P.text, margin: 0 });
  },
  // 3. Where it shows up
  async (c) => {
    const s = c.light("Where this problem shows up");
    const items = [
      [fa.FaChartLine, "Stock prices", "The best stretch of days to hold a share, from daily price changes."],
      [fa.FaWaveSquare, "Signals", "The strongest burst in a noisy sensor reading."],
      [fa.FaGamepad, "Game streaks", "A player's best run of points, where some rounds lose points."],
    ];
    for (let i = 0; i < 3; i++) {
      const x = 0.55 + i * 3.02;
      c.card(s, x, 1.4, 2.82, 3.3, c.P.soft);
      await c.iconCircle(s, items[i][0], x + 0.3, 1.7, 0.85, P.dark, P.accent);
      s.addText(items[i][1], { isTextBox: true, x: x + 0.3, y: 2.75, w: 2.3, h: 0.45, fontFace: "Cambria", fontSize: 19, bold: true, color: P.text, margin: 0 });
      c.text(s, items[i][2], { x: x + 0.3, y: 3.25, w: 2.3, h: 1.3, fontSize: 14, color: P.muted });
    }
  },
  // 4. Brute force
  async (c) => {
    const s = c.light("First idea: try every subarray");
    c.code(s, 0.55, 1.35, 5.3, 3.4,
      "def max_sub_brute(arr):\n    best = arr[0]\n    for i in range(len(arr)):\n        total = 0\n        for j in range(i, len(arr)):\n            total += arr[j]\n            best = max(best, total)\n    return best", 14);
    c.card(s, 6.2, 1.35, 3.25, 1.55, c.P.soft);
    c.stat(s, 6.45, 1.35, 2.9, "45", "subarrays to check for just 9 numbers", P.accent2);
    c.card(s, 6.2, 3.2, 3.25, 1.55, c.P.soft);
    c.stat(s, 6.45, 3.2, 2.9, "O(n²)", "time: doubling the input makes it 4x slower", "C0392B");
  },
  // 5. Key insight
  async (c) => {
    const s = c.light("The key insight");
    c.card(s, 0.55, 1.35, 8.9, 1.55, P.dark);
    s.addText("A running sum that has gone negative can only drag the next numbers down. Drop it and start fresh.",
      { isTextBox: true, x: 0.9, y: 1.5, w: 8.2, h: 1.25, fontFace: "Cambria", fontSize: 22, italic: true, color: "FFFFFF", margin: 0, valign: "middle" });
    const box = (x, label, val, good) => {
      c.card(s, x, 3.25, 4.3, 1.45, good ? "E3F4EF" : "FBEAEA");
      s.addText(label, { isTextBox: true, x: x + 0.3, y: 3.38, w: 3.7, h: 0.4, fontFace: "Calibri", fontSize: 14, color: P.muted, margin: 0 });
      s.addText(val, { isTextBox: true, x: x + 0.3, y: 3.78, w: 3.7, h: 0.75, fontFace: "Courier New", fontSize: 22, bold: true, color: good ? P.accent2 : "C0392B", margin: 0 });
    };
    box(0.55, "Keep the old sum", "(-2) + 1 = -1", false);
    box(5.15, "Start fresh at 1", "1", true);
  },
  // 6. Two numbers
  async (c) => {
    const s = c.light("Two numbers do all the work");
    const col = async (x, Ico, name, meaning, formula, colr) => {
      c.card(s, x, 1.35, 4.3, 3.45, c.P.soft);
      await c.iconCircle(s, Ico, x + 0.3, 1.6, 0.75, colr, "FFFFFF");
      s.addText(name, { isTextBox: true, x: x + 1.2, y: 1.6, w: 2.9, h: 0.75, fontFace: "Courier New", fontSize: 24, bold: true, color: P.text, margin: 0, valign: "middle" });
      c.text(s, meaning, { x: x + 0.3, y: 2.55, w: 3.7, h: 0.9, fontSize: 15, color: P.muted });
      c.card(s, x + 0.3, 3.55, 3.7, 0.95, "FFFFFF");
      s.addText(formula, { isTextBox: true, x: x + 0.45, y: 3.55, w: 3.45, h: 0.95, fontFace: "Courier New", fontSize: 15, bold: true, color: colr, margin: 0, valign: "middle" });
    };
    await col(0.55, fa.FaArrowRight, "current", "The best sum of a run that ends exactly here.", "max(x, current + x)", P.accent2);
    await col(5.15, fa.FaTrophy, "best", "The best sum seen anywhere so far.", "max(best, current)", "B7791F");
  },
  // 7. Trace table
  async (c) => {
    const s = c.light("Tracing it by hand");
    const head = ["i", "x", "current", "best"].map(t => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: P.dark }, align: "center" } }));
    const rows = ARR.map((x, i) => [i, x, CUR[i], BEST[i]].map((v, k) => ({ text: String(v), options: {
      align: "center", fill: { color: i >= 3 && i <= 6 && k === 2 ? "FCEFD3" : (i % 2 ? "F5F8FA" : "FFFFFF") },
      bold: (k === 3 && v === 6), color: (k === 3 && v === 6) ? P.accent2 : P.text } })));
    s.addTable([head, ...rows], { x: 0.55, y: 1.3, w: 4.9, colW: [0.7, 1.1, 1.6, 1.5], rowH: 0.36, fontFace: "Calibri", fontSize: 13,
      border: { type: "solid", pt: 0.5, color: "DCE3E9" } });
    c.card(s, 5.8, 1.3, 3.65, 3.6, c.P.soft);
    c.bullets(s, ["At i = 3, current jumps to 4: starting fresh beats carrying -2.",
      "From i = 3 to 6, current grows: 4, 3, 5, 6.", "best stops at 6. The -5 at i = 7 can't beat it."],
      { x: 6.05, y: 1.55, w: 3.2, h: 3.2, fontSize: 14 });
  },
  // 8. Chart
  async (c) => {
    const s = c.light("Watching the running sum");
    const labels = ARR.map((x, i) => `${i}: ${x}`);
    s.addChart(c.pres.charts.LINE, [{ name: "current", labels, values: CUR }, { name: "best", labels, values: BEST }],
      c.chartStyle({ x: 0.55, y: 1.25, w: 6.1, h: 3.75, chartColors: [P.accent2, P.accent], lineSize: 2.5, lineDataSymbolSize: 7,
        showLegend: true, legendPos: "b", legendFontFace: "Calibri", legendFontSize: 11, legendColor: P.muted,
        showTitle: true, title: "current and best at each index (i: x)", valAxisMinVal: -3, valAxisMaxVal: 7 }));
    c.card(s, 6.95, 1.25, 2.5, 3.75, c.P.soft);
    c.stat(s, 7.15, 1.45, 2.2, "6", "best sum, reached at i = 6", P.accent2);
    c.text(s, "current dips below zero only at the start, so the run restarts at i = 3.", { x: 7.15, y: 3.05, w: 2.15, h: 1.8, fontSize: 13, color: P.muted });
  },
  // 9. Code
  async (c) => {
    const s = c.light("The code");
    c.code(s, 0.55, 1.3, 5.6, 3.55, "def max_subarray(arr):\n    current = best = arr[0]\n    for x in arr[1:]:\n        current = max(x, current + x)\n        best = max(best, current)\n    return best\n\nnums = [-2, 1, -3, 4, -1, 2, 1, -5, 4]\nprint(max_subarray(nums))", 14);
    c.card(s, 6.45, 1.3, 3.0, 1.45, c.P.soft);
    s.addText("Output", { isTextBox: true, x: 6.7, y: 1.42, w: 2.5, h: 0.35, fontFace: "Calibri", fontSize: 13, color: P.muted, margin: 0 });
    s.addText("6", { isTextBox: true, x: 6.7, y: 1.78, w: 2.5, h: 0.8, fontFace: "Courier New", fontSize: 36, bold: true, color: P.accent2, margin: 0 });
    c.bullets(s, ["Starts from arr[0], not 0", "One loop over the array", "Two variables, no extra list"], { x: 6.5, y: 3.05, w: 2.95, h: 1.8, fontSize: 14 });
  },
  // 10. Why fast
  async (c) => {
    const s = c.light("Why it's fast");
    const col = (x, name, time, space, steps, colr) => {
      c.card(s, x, 1.3, 4.3, 3.55, c.P.soft);
      s.addText(name, { isTextBox: true, x: x + 0.3, y: 1.45, w: 3.7, h: 0.5, fontFace: "Cambria", fontSize: 20, bold: true, color: P.text, margin: 0 });
      c.stat(s, x + 0.3, 2.0, 3.7, time, "time", colr);
      s.addText(`${space} extra space`, { isTextBox: true, x: x + 0.3, y: 3.5, w: 3.7, h: 0.4, fontFace: "Calibri", fontSize: 15, color: P.text, margin: 0 });
      s.addText(steps, { isTextBox: true, x: x + 0.3, y: 3.95, w: 3.7, h: 0.7, fontFace: "Calibri", fontSize: 13, color: P.muted, margin: 0 });
    };
    col(0.55, "Try every subarray", "O(n²)", "O(1)", "1 million numbers: about 500 billion sums", "C0392B");
    col(5.15, "Kadane's algorithm", "O(n)", "O(1)", "1 million numbers: 1 million steps", P.accent2);
  },
  // 11. Edge case
  async (c) => {
    const s = c.light("Watch out: every number negative");
    arrayRow(c, s, [-3, -1, -4], 0.95, 1.55, 1.0, 1, 1, { fontSize: 24 });
    s.addText("= -1", { isTextBox: true, x: 4.35, y: 1.55, w: 1.5, h: 1.0, fontFace: "Cambria", fontSize: 30, bold: true, color: P.accent2, margin: 0, valign: "middle" });
    c.card(s, 0.55, 3.0, 8.9, 1.85, c.P.soft);
    c.bullets(s, ["The answer is the largest single number, here -1.",
      "If current and best started at 0, the code would wrongly print 0: an empty run.",
      "Starting both at arr[0] keeps the answer a real subarray."], { x: 0.85, y: 3.2, w: 8.3, h: 1.6, fontSize: 15 });
  },
  // 12. Takeaways
  async (c) => {
    const s = c.dark("Takeaways");
    const pts = ["Drop a negative running sum: it can only hurt.", "Keep two numbers: current (ends here) and best (so far).", "One pass: O(n) time, O(1) space."];
    pts.forEach((t, i) => {
      s.addShape(c.pres.shapes.OVAL, { x: 0.6, y: 3.25 + i * 0.68, w: 0.48, h: 0.48, fill: { color: P.accent }, line: { color: P.accent } });
      s.addText(String(i + 1), { isTextBox: true, x: 0.6, y: 3.25 + i * 0.68, w: 0.48, h: 0.48, align: "center", valign: "middle", fontFace: "Cambria", fontSize: 18, bold: true, color: P.dark, margin: 0 });
      s.addText(t, { isTextBox: true, x: 1.3, y: 3.25 + i * 0.68, w: 8.0, h: 0.48, fontFace: "Calibri", fontSize: 18, color: "FFFFFF", margin: 0, valign: "middle" });
    });
  },
];

module.exports = (file, only = null) => buildDeck({ file, title: "Kadane's Algorithm", P, slides, only });
if (require.main === module) module.exports(process.argv[2] || "kadane.pptx").then(f => console.log("wrote", f));
