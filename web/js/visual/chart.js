// The graph helper every visual uses (inlined after runtime.js, so it extends window.Visual).
// It draws clean axes with "nice" ticks and maps data to the 800x450 picture, so the generated code only
// computes values and calls these. Plot marks are clipped to the plot area; labels and readouts never are.
//
//   const c = Visual.chart({ x: [0, 10], y: [0, 100], xLabel: "x", yLabel: "y" });
//   Named categories: Visual.chart({ xLabels: ["Asia", "Europe", ...], y: [...] }) and bars at x = 0, 1, 2...
//   c.clear();  c.fn(x => x * x);  c.line(points);  c.dots(points);  c.bars(points);  c.area(points);
//   c.vline(x, "label");  c.hline(y, "label");  c.label(x, y, "text");  c.readout(["mean = 2.0", ...]);
//   c.setRange({ x: [lo, hi], y: [lo, hi] });  c.x(v) / c.y(v): data -> picture coordinates.
(function () {
  "use strict";
  const V = window.Visual;
  if (!V) return;
  const W = 800, H = 450;
  let clipCount = 0;

  function niceTicks(lo, hi, count = 6) {
    const span = hi - lo;
    if (!(span > 0)) return [lo];
    let step = Math.pow(10, Math.floor(Math.log10(span / count)));
    const err = span / count / step;
    step *= err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }
  // Builders sometimes pass { label, value } or [label, value] instead of a string: show those properly too.
  const asText = (v) => {
    if (v == null) return "";
    if (Array.isArray(v)) return v.join(" = ");
    if (typeof v === "object") {
      if (v.text != null) return String(v.text);
      const label = v.label ?? v.name ?? v.title;
      if (label != null) return v.value != null ? `${label} = ${typeof v.value === "number" ? fmt(v.value) : v.value}` : String(label);
      return Object.values(v).join(" ");
    }
    return String(v);
  };
  const fmt = (v) => {
    const a = Math.abs(v);
    if (a !== 0 && (a >= 1e5 || a < 1e-3)) return v.toExponential(1);
    return String(+v.toFixed(a < 1 ? 3 : a < 10 ? 2 : 1));
  };

  V.chart = function (opts = {}) {
    const m = Object.assign({ left: 72, right: 28, top: 56, bottom: 62 }, opts.margin || {});
    // xLabels: named categories; the x range then fits them (bar k is at x = k)
    let xr = (opts.x || (opts.xLabels ? [-0.6, opts.xLabels.length - 0.4] : [0, 10])).slice(), yr = (opts.y || [0, 10]).slice();
    let svg = opts.svg || (V.stage && V.stage.querySelector("svg"));
    if (!svg || String(svg.tagName).toLowerCase() !== "svg") svg = V.svg("svg", { viewBox: `0 0 ${W} ${H}` }, V.stage);
    const id = `plot-clip-${++clipCount}`;
    const defs = V.svg("defs", {}, svg);
    const clip = V.svg("clipPath", { id }, defs);
    V.svg("rect", { x: m.left, y: m.top, width: W - m.left - m.right, height: H - m.top - m.bottom }, clip);
    const axes = V.svg("g", {}, svg);
    const plot = V.svg("g", { "clip-path": `url(#${id})` }, svg);
    const notes = V.svg("g", {}, svg);

    const sx = (v) => m.left + ((v - xr[0]) / (xr[1] - xr[0])) * (W - m.left - m.right);
    const sy = (v) => H - m.bottom - ((v - yr[0]) / (yr[1] - yr[0])) * (H - m.top - m.bottom);
    const clampX = (px) => Math.max(m.left + 4, Math.min(W - m.right - 4, px));
    const clampY = (py) => Math.max(m.top + 14, Math.min(H - m.bottom - 4, py));

    function drawAxes() {
      axes.replaceChildren();
      // Named categories (countries, regions...): one tick per bar at x = 0, 1, 2... with its name
      const xTicks = opts.xLabels ? opts.xLabels.map((_, k) => k) : niceTicks(xr[0], xr[1]);
      const xText = (t) => opts.xLabels ? String(opts.xLabels[t]) : fmt(t);
      for (const t of xTicks) {
        V.svg("line", { x1: sx(t), x2: sx(t), y1: m.top, y2: H - m.bottom, stroke: "var(--line)", "stroke-width": 1 }, axes);
        V.svg("text", { x: sx(t), y: H - m.bottom + 22, "text-anchor": "middle", "font-size": 14, fill: "var(--muted)", text: xText(t) }, axes);
      }
      for (const t of niceTicks(yr[0], yr[1], 5)) {
        V.svg("line", { x1: m.left, x2: W - m.right, y1: sy(t), y2: sy(t), stroke: "var(--line)", "stroke-width": 1 }, axes);
        V.svg("text", { x: m.left - 10, y: sy(t) + 5, "text-anchor": "end", "font-size": 14, fill: "var(--muted)", text: fmt(t) }, axes);
      }
      V.svg("line", { x1: m.left, x2: W - m.right, y1: H - m.bottom, y2: H - m.bottom, stroke: "var(--muted)", "stroke-width": 1.5 }, axes);
      V.svg("line", { x1: m.left, x2: m.left, y1: m.top, y2: H - m.bottom, stroke: "var(--muted)", "stroke-width": 1.5 }, axes);
      if (opts.xLabel) V.svg("text", { x: (m.left + W - m.right) / 2, y: H - 14, "text-anchor": "middle", "font-size": 16, fill: "var(--ink)", text: opts.xLabel }, axes);
      if (opts.yLabel) V.svg("text", { x: 18, y: (m.top + H - m.bottom) / 2, "text-anchor": "middle", "font-size": 16, fill: "var(--ink)",
        transform: `rotate(-90 18 ${(m.top + H - m.bottom) / 2})`, text: opts.yLabel }, axes);
    }
    drawAxes();

    let barW = null;  // the width of the last full set of bars

    // Labels placed since the last clear(): a new one that would overlap them moves down a row.
    const placed = [];
    const overlaps = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

    // A mark above the y axis would be cut off. The axis grows to fit (never shrinks, so movement stays
    // visible) and the runtime redraws once; the highest point is kept for the test run's feedback.
    const topAtStart = yr[1];
    const offscale = (pts) => {
      let hi = -Infinity;
      for (const p of pts) if (Number.isFinite(p[1])) hi = Math.max(hi, p[1]);
      if (!Number.isFinite(hi)) return;
      V._clip = { top: topAtStart, max: Math.max(hi, V._clip ? V._clip.max : -Infinity) };
      if (hi > yr[1] + (yr[1] - yr[0]) * 0.02) {
        const ticks = niceTicks(yr[0], hi * 1.08, 5);
        yr = [yr[0], Math.max(hi * 1.08, ticks[ticks.length - 1])];
        drawAxes();
        V._needsRedraw = true;
      }
    };
    const path = (pts) => pts.filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]))
      .map((p, i) => `${i ? "L" : "M"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(" ");

    const c = {
      x: sx, y: sy, plot, notes,
      get range() { return { x: xr.slice(), y: yr.slice() }; },
      // setRange({ x, y }), or setRange(xRange, yRange) with null for "keep".
      setRange(r = {}, y = null) {
        if (Array.isArray(r) || r === null) r = { x: r, y };
        if (r.x) xr = r.x.slice();
        if (r.y) yr = r.y.slice();
        drawAxes();
      },
      clear() { plot.replaceChildren(); notes.replaceChildren(); placed.length = 0; },
      line(points, a = {}) {
        offscale(points);
        return V.svg("path", { d: path(points), fill: "none", stroke: a.color || "var(--accent)", "stroke-width": a.width || 3,
          "stroke-dasharray": a.dashed ? "7 6" : "none", "stroke-linejoin": "round", opacity: a.opacity ?? 1 }, plot);
      },
      fn(f, a = {}) {
        const pts = [], n = a.samples || 240;
        for (let i = 0; i <= n; i++) { const xv = xr[0] + ((xr[1] - xr[0]) * i) / n; pts.push([xv, f(xv)]); }
        return c.line(pts, a);
      },
      area(points, a = {}) {
        const pts = points.filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));
        if (pts.length < 2) return null;
        const base = Math.max(yr[0], Math.min(yr[1], a.base ?? 0));
        const d = path(pts) + ` L${sx(pts.at(-1)[0]).toFixed(1)},${sy(base).toFixed(1)} L${sx(pts[0][0]).toFixed(1)},${sy(base).toFixed(1)} Z`;
        return V.svg("path", { d, fill: a.color || "var(--accent)", opacity: a.opacity ?? 0.18, stroke: "none" }, plot);
      },
      dots(points, a = {}) {
        offscale(points);
        for (const p of points) {
          if (!Number.isFinite(p[0]) || !Number.isFinite(p[1])) continue;
          V.svg("circle", { cx: sx(p[0]), cy: sy(p[1]), r: a.r || 5, fill: a.color || "var(--accent)", stroke: "#fff", "stroke-width": 1.5 }, plot);
        }
      },
      bars(points, a = {}) {
        offscale(points);
        // Each bar is as wide as the CLOSEST pair of bars allows, so bars never overlap, even for uneven years
        // (1990, 2000, 2007, 2010...): the first gap alone would make every bar 8 years wide.
        const xs = [...new Set(points.map(p => p[0]).filter(Number.isFinite))].sort((p, q) => p - q);
        let gap = Infinity;
        for (let k = 1; k < xs.length; k++) gap = Math.min(gap, xs[k] - xs[k - 1]);
        // a single bar drawn again to point at it (a highlight) keeps the width of the full set
        const w = a.width ?? (Number.isFinite(gap) ? (barW = gap * 0.7) : barW ?? (xr[1] - xr[0]) / 10);
        const base = Math.max(yr[0], Math.min(yr[1], 0));
        for (const [xv, yv] of points) {
          if (!Number.isFinite(xv) || !Number.isFinite(yv)) continue;
          const top = Math.min(sy(yv), sy(base)), h = Math.abs(sy(yv) - sy(base));
          V.svg("rect", { x: sx(xv - w / 2), y: top, width: Math.max(1, sx(xv + w / 2) - sx(xv - w / 2)), height: h,
            rx: 2, fill: a.color || "var(--accent)", opacity: a.opacity ?? 0.85 }, plot);
        }
      },
      vline(xv, text = "", a = {}) {
        V.svg("line", { x1: sx(xv), x2: sx(xv), y1: m.top, y2: H - m.bottom, stroke: a.color || "var(--warn)", "stroke-width": 2, "stroke-dasharray": "6 5" }, plot);
        if (text) c.label(xv, yr[1], asText(text), { color: a.color || "var(--warn)", anchor: "middle", dy: -6 });
      },
      hline(yv, text = "", a = {}) {
        V.svg("line", { x1: m.left, x2: W - m.right, y1: sy(yv), y2: sy(yv), stroke: a.color || "var(--warn)", "stroke-width": 2, "stroke-dasharray": "6 5" }, plot);
        if (text) c.label(xr[1], yv, asText(text), { color: a.color || "var(--warn)", anchor: "end", dy: -8 });
      },
      label(xv, yv, text, a = {}) {
        text = asText(text);
        const size = a.size || 15, anchor = a.anchor || "middle";
        const w = text.length * size * 0.58 + 6, px = clampX(sx(xv) + (a.dx || 0));
        let py = clampY(sy(yv) + (a.dy ?? -10));
        const box = () => ({ x: px - (anchor === "middle" ? w / 2 : anchor === "end" ? w : 0), y: py - size, w, h: size + 4 });
        for (let tries = 0; tries < 8 && placed.some((b) => overlaps(box(), b)); tries++) py += size + 6;
        placed.push(box());
        return V.svg("text", { x: px, y: py, "text-anchor": anchor, "font-size": size, "font-weight": 600,
          fill: a.color || "var(--ink)", text }, notes);
      },
      // Key numbers above the plot (never on top of the data): one row, a second row if they don't fit.
      // Long items are shortened; put lists in Visual.state, not here.
      readout(items) {
        let xpos = m.left, row = 0;
        for (let item of [].concat(items || []).slice(0, 4)) {
          item = asText(item);
          if (item.length > 34) item = item.slice(0, 33) + "…";
          const w = item.length * 9.5 + 28;
          if (xpos > m.left && xpos + w > W - m.right) { row += 1; xpos = m.left; }
          if (row > 1) break;
          V.svg("text", { x: xpos, y: row ? 46 : 24, "font-size": row ? 15 : 17, "font-weight": 600, fill: "var(--ink)", text: item }, notes);
          xpos += Math.max(110, w);
        }
      },
    };
    return c;
  };
})();
