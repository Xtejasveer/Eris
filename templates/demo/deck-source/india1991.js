const { buildDeck } = require("./common");
const fa = require("react-icons/fa");

const P = { dark: "0E3B2E", accent: "E07A1F", accent2: "3A7D5C", soft: "E9F2EC", text: "1F2A24", muted: "5E6B63" };

const slides = [
  // 1. Title
  async (c) => {
    const s = c.dark("India's 1991 Reforms");
    c.text(s, "How opening up changed India's trade", { x: 0.6, y: 3.15, w: 8.5, h: 0.5, fontSize: 20, color: "CFE3D8" });
    ["The crisis", "The reforms", "The results"].forEach((t, i) => {
      c.card(s, 0.6 + i * 2.25, 4.1, 2.05, 0.55, i === 1 ? P.accent : "1D5442");
      s.addText(t, { isTextBox: true, x: 0.6 + i * 2.25, y: 4.1, w: 2.05, h: 0.55, align: "center", valign: "middle",
        fontFace: "Calibri", fontSize: 15, bold: true, color: "FFFFFF", margin: 0 });
    });
  },
  // 2. Before 1991
  async (c) => {
    const s = c.light("India before 1991: a closed economy");
    const stats = [["~15%", "of GDP was trade (exports + imports), 1990"], ["300%+", "top import duty on some goods"], ["$97M", "foreign direct investment, 1990-91"]];
    stats.forEach(([big, label], i) => {
      const x = 0.55 + i * 3.02;
      c.card(s, x, 1.3, 2.82, 2.0, c.P.soft);
      c.stat(s, x + 0.3, 1.45, 2.3, big, label, i === 1 ? "B5451B" : P.accent2);
    });
    c.card(s, 0.55, 3.6, 8.9, 1.25, P.dark);
    await c.iconCircle(s, fa.FaFileSignature, 0.8, 3.78, 0.85, P.accent, "FFFFFF");
    s.addText([{ text: "Licence raj: ", options: { bold: true, color: P.accent } },
      { text: "firms needed government permission to start, expand or import, and foreign companies were kept out.", options: { color: "FFFFFF" } }],
      { isTextBox: true, x: 1.9, y: 3.7, w: 7.3, h: 1.05, fontFace: "Calibri", fontSize: 16, margin: 0, valign: "middle" });
    c.source(s, "Sources: World Bank, Trade (% of GDP), rounded; Economic Survey of India; RBI.");
  },
  // 3. Timeline
  async (c) => {
    const s = c.light("How the crisis built up, 1990-91");
    const ev = [["Aug 1990", "Gulf War", "Oil prices jump and money sent home by Gulf workers falls."],
      ["1990-91", "Political uncertainty", "Two governments in a year; investors lose confidence."],
      ["Jan 1991", "Reserves run low", "Foreign exchange falls to about $1.2 billion."],
      ["July 1991", "Gold pledged", "The RBI pledges gold abroad and India borrows from the IMF."]];
    s.addShape(c.pres.shapes.LINE, { x: 0.9, y: 2.12, w: 8.2, h: 0, line: { color: "C7D6CD", width: 2 } });
    ev.forEach(([when, head, body], i) => {
      const x = 0.55 + i * 2.27;
      s.addShape(c.pres.shapes.OVAL, { x: x + 0.12, y: 1.9, w: 0.44, h: 0.44, fill: { color: i === 3 ? P.accent : P.dark }, line: { color: "FFFFFF", width: 2 } });
      s.addText(when, { isTextBox: true, x, y: 1.35, w: 2.1, h: 0.4, fontFace: "Calibri", fontSize: 14, bold: true, color: i === 3 ? P.accent : P.accent2, margin: 0 });
      c.card(s, x, 2.6, 2.1, 2.2, c.P.soft);
      s.addText(head, { isTextBox: true, x: x + 0.18, y: 2.75, w: 1.8, h: 0.6, fontFace: "Cambria", fontSize: 16, bold: true, color: P.text, margin: 0 });
      c.text(s, body, { x: x + 0.18, y: 3.4, w: 1.8, h: 1.3, fontSize: 13, color: P.muted });
    });
  },
  // 4. Crisis in numbers
  async (c) => {
    const s = c.light("The crisis in numbers");
    c.card(s, 0.55, 1.3, 4.3, 3.5, P.dark);
    await c.iconCircle(s, fa.FaHourglassHalf, 0.85, 1.6, 0.85, P.accent, "FFFFFF");
    s.addText("A few weeks", { isTextBox: true, x: 0.85, y: 2.6, w: 3.8, h: 0.8, fontFace: "Cambria", fontSize: 36, bold: true, color: "FFFFFF", margin: 0 });
    c.text(s, "of imports was all India's reserves could pay for by mid-1991 (estimates range from two to three weeks).", { x: 0.85, y: 3.45, w: 3.75, h: 1.2, fontSize: 14, color: "CFE3D8" });
    c.card(s, 5.15, 1.3, 4.3, 1.65, c.P.soft);
    c.stat(s, 5.45, 1.35, 3.8, "3%+", "current account deficit, as a share of GDP, by March 1991", "B5451B");
    c.card(s, 5.15, 3.15, 4.3, 1.65, c.P.soft);
    c.stat(s, 5.45, 3.2, 3.8, "$1.2B", "foreign exchange reserves, January 1991", P.accent2);
    c.source(s, "Sources: RBI; Economic Survey 1991-92; figures rounded.");
  },
  // 5. Three reforms
  async (c) => {
    const s = c.light("The response: three big reforms");
    const items = [[fa.FaBoxOpen, "Cut import duties", "The top duty fell from over 300% to 150% in 1991-92, and kept falling."],
      [fa.FaRupeeSign, "Devalue the rupee", "About 18-19% in two steps in July 1991, making exports cheaper abroad."],
      [fa.FaHandshake, "Welcome foreign investment", "Automatic approval for up to 51% foreign ownership in priority industries."]];
    for (let i = 0; i < 3; i++) {
      const x = 0.55 + i * 3.02;
      c.card(s, x, 1.3, 2.82, 3.5, c.P.soft);
      await c.iconCircle(s, items[i][0], x + 0.3, 1.6, 0.85, P.accent, "FFFFFF");
      s.addText(items[i][1], { isTextBox: true, x: x + 0.3, y: 2.65, w: 2.3, h: 0.7, fontFace: "Cambria", fontSize: 18, bold: true, color: P.text, margin: 0 });
      c.text(s, items[i][2], { x: x + 0.3, y: 3.35, w: 2.3, h: 1.35, fontSize: 14, color: P.muted });
    }
  },
  // 6. Duties chart
  async (c) => {
    const s = c.light("Import duties came down step by step");
    s.addChart(c.pres.charts.BAR, [{ name: "Top import duty (%)", labels: ["1990-91", "1991-92", "1994-95", "1995-96", "1997-98", "2002-03"], values: [300, 150, 65, 50, 40, 30] }],
      c.chartStyle({ x: 0.55, y: 1.25, w: 6.2, h: 3.75, barDir: "col", chartColors: [P.accent], showValue: true, dataLabelPosition: "outEnd",
        dataLabelFormatCode: "0\"%\"", showTitle: true, title: "Top (peak) import duty, %", valAxisMaxVal: 350, barGapWidthPct: 60 }));
    c.card(s, 7.05, 1.25, 2.4, 3.75, c.P.soft);
    c.stat(s, 7.25, 1.45, 2.1, "-90%", "fall in the top duty, 1990-91 to 2002-03", P.accent2);
    c.text(s, "Before 1991 some goods faced duties of 300% or more; 300 is shown here.", { x: 7.25, y: 3.1, w: 2.05, h: 1.7, fontSize: 12, color: P.muted });
    c.source(s, "Sources: Union Budgets; RBI; USTR reports. Pre-reform peak estimates range from about 300% to 400%.");
  },
  // 7. Trade share chart
  async (c) => {
    const s = c.light("Trade grew as a share of the economy");
    s.addChart(c.pres.charts.LINE, [{ name: "Trade (% of GDP)", labels: ["1990", "2000", "2008", "2012", "2016", "2020", "2022"], values: [15, 27, 52, 56, 40, 38, 50] }],
      c.chartStyle({ x: 0.55, y: 1.25, w: 6.2, h: 3.75, chartColors: [P.accent2], lineSize: 3, lineDataSymbolSize: 8, showValue: true,
        dataLabelPosition: "t", dataLabelFormatCode: "0\"%\"", showTitle: true, title: "India: exports + imports as % of GDP", valAxisMinVal: 0, valAxisMaxVal: 70 }));
    c.card(s, 7.05, 1.25, 2.4, 3.75, c.P.soft);
    c.stat(s, 7.25, 1.45, 2.1, "~4x", "from about 15% in 1990 to a peak near 56% in 2012", P.accent2);
    c.text(s, "Dips follow world events: the 2009 slowdown and the 2020 pandemic.", { x: 7.25, y: 3.15, w: 2.05, h: 1.6, fontSize: 12, color: P.muted });
    c.source(s, "Source: World Bank, Trade (% of GDP), India, rounded.");
  },
  // 8. FDI chart
  async (c) => {
    const s = c.light("Foreign investment took off");
    s.addChart(c.pres.charts.BAR, [{ name: "FDI inflow ($ million)", labels: ["1990-91", "1991-92", "1992-93", "1993-94"], values: [97, 129, 315, 586] }],
      c.chartStyle({ x: 0.55, y: 1.25, w: 6.2, h: 3.75, barDir: "col", chartColors: [P.accent2], showValue: true, dataLabelPosition: "outEnd",
        showTitle: true, title: "Foreign direct investment into India, US$ million", valAxisMaxVal: 700, barGapWidthPct: 70 }));
    c.card(s, 7.05, 1.25, 2.4, 3.75, c.P.soft);
    c.stat(s, 7.25, 1.45, 2.1, "6x", "in three years, from $97M to $586M", P.accent);
    c.text(s, "By 1994-95, yearly FDI had passed $1 billion.", { x: 7.25, y: 3.15, w: 2.05, h: 1.6, fontSize: 12, color: P.muted });
    c.source(s, "Source: Economic Survey of India (direct investment, balance of payments tables).");
  },
  // 9. Worked example
  async (c) => {
    const s = c.light("Worked example: percentage change");
    c.card(s, 0.55, 1.3, 8.9, 0.9, P.dark);
    s.addText("% change  =  (new - old) / old  x  100", { isTextBox: true, x: 0.85, y: 1.3, w: 8.3, h: 0.9, fontFace: "Courier New", fontSize: 22, bold: true, color: "FFFFFF", margin: 0, valign: "middle" });
    const steps = [["1", "New minus old", "586 - 97 = 489"], ["2", "Divide by old", "489 / 97 = 5.04"], ["3", "Times 100", "5.04 x 100 = 504%"]];
    steps.forEach(([n, head, calc], i) => {
      const x = 0.55 + i * 3.02;
      c.card(s, x, 2.5, 2.82, 2.3, c.P.soft);
      s.addShape(c.pres.shapes.OVAL, { x: x + 0.25, y: 2.7, w: 0.5, h: 0.5, fill: { color: P.accent }, line: { color: P.accent } });
      s.addText(n, { isTextBox: true, x: x + 0.25, y: 2.7, w: 0.5, h: 0.5, align: "center", valign: "middle", fontFace: "Cambria", fontSize: 18, bold: true, color: "FFFFFF", margin: 0 });
      s.addText(head, { isTextBox: true, x: x + 0.9, y: 2.7, w: 1.8, h: 0.5, fontFace: "Calibri", fontSize: 15, bold: true, color: P.text, margin: 0, valign: "middle" });
      s.addText(calc, { isTextBox: true, x: x + 0.25, y: 3.5, w: 2.45, h: 0.9, fontFace: "Courier New", fontSize: 15, bold: true, color: i === 2 ? P.accent2 : P.text, margin: 0, valign: "middle" });
    });
    c.source(s, "FDI rose by about 504% from 1990-91 to 1993-94.");
  },
  // 10. Flow
  async (c) => {
    const s = c.light("From crisis to more trade");
    const boxes = ["Crisis: reserves run out", "Reforms: duties cut, rupee devalued, FDI allowed", "Imports cheaper, exports more competitive", "More trade and investment", "Faster growth in the 1990s and 2000s"];
    boxes.forEach((t, i) => {
      const x = 0.55 + i * 1.84;
      c.card(s, x, 1.75, 1.5, 2.3, i === 0 ? "F6E3D3" : i === 4 ? P.dark : c.P.soft, { shadow: true });
      s.addText(t, { isTextBox: true, x: x + 0.12, y: 1.85, w: 1.26, h: 2.1, fontFace: "Calibri", fontSize: 14, bold: i === 4, color: i === 4 ? "FFFFFF" : P.text,
        margin: 0, valign: "middle", align: "center" });
      if (i < 4) c.arrow(s, x + 1.53, 2.74, 0.3, P.accent);
    });
    c.text(s, "Each step made the next one possible; none of them alone would have opened the economy.", { x: 0.55, y: 4.4, w: 8.9, h: 0.5, fontSize: 14, color: P.muted, italic: true });
  },
  // 11. Other side
  async (c) => {
    const s = c.light("The other side of the story");
    const col = async (x, Ico, head, items, colr, bg) => {
      c.card(s, x, 1.3, 4.3, 3.55, bg);
      await c.iconCircle(s, Ico, x + 0.3, 1.5, 0.7, colr, "FFFFFF");
      s.addText(head, { isTextBox: true, x: x + 1.15, y: 1.5, w: 3.0, h: 0.7, fontFace: "Cambria", fontSize: 19, bold: true, color: P.text, margin: 0, valign: "middle" });
      c.bullets(s, items, { x: x + 0.35, y: 2.4, w: 3.7, h: 2.3, fontSize: 14 });
    };
    await col(0.55, fa.FaArrowUp, "Who gained", ["Exporters and IT services", "Consumers: more choice, lower prices", "Firms that could import better machines"], P.accent2, c.P.soft);
    await col(5.15, fa.FaBalanceScale, "Who struggled", ["Small firms facing cheap imports", "Many farmers and informal workers", "Gaps between rich and poor widened"], "B5451B", "FBEEE6");
  },
  // 12. Takeaways
  async (c) => {
    const s = c.dark("Takeaways");
    const pts = ["A payments crisis forced India to open up in 1991.", "Lower duties, a cheaper rupee and FDI rules drove trade up.", "Gains were large, but not shared equally."];
    pts.forEach((t, i) => {
      s.addShape(c.pres.shapes.OVAL, { x: 0.6, y: 3.25 + i * 0.68, w: 0.48, h: 0.48, fill: { color: P.accent }, line: { color: P.accent } });
      s.addText(String(i + 1), { isTextBox: true, x: 0.6, y: 3.25 + i * 0.68, w: 0.48, h: 0.48, align: "center", valign: "middle", fontFace: "Cambria", fontSize: 18, bold: true, color: "FFFFFF", margin: 0 });
      s.addText(t, { isTextBox: true, x: 1.3, y: 3.25 + i * 0.68, w: 8.0, h: 0.48, fontFace: "Calibri", fontSize: 18, color: "FFFFFF", margin: 0, valign: "middle" });
    });
  },
];

module.exports = (file, only = null) => buildDeck({ file, title: "India's 1991 Reforms", P, slides, only });
if (require.main === module) module.exports(process.argv[2] || "india1991.pptx").then(f => console.log("wrote", f));
