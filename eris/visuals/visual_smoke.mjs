// Test-runs a built visual in node, with a small fake page, before the class sees it.
// Usage: node visual_smoke.mjs <visual.json>   -> prints {"problems": [...], "states": [...]}
//
// It presses every control like a teacher would and checks two things a static check can't:
//   - the code doesn't crash with a real bug (an undefined name, a syntax error);
//   - every control changes what the visual reports it shows (Visual.state), i.e. it really does something;
//   - the drawing is readable: no text or shapes half on top of each other, nothing outside the picture
//     ("layout": sent back to the builder as advice, never fails a visual on its own).
// The fake page is permissive: DOM details it doesn't model never count as problems.
import { readFileSync } from "node:fs";
import vm from "node:vm";

const visual = JSON.parse(readFileSync(process.argv[2], "utf8"));
const problems = [];
const layout = new Set();
const states = [];
let lastState = "";

const noop = () => {};
function makeEl(tag = "div") {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], attrs: {}, style: {}, dataset: {}, textContent: "", innerHTML: "",
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    appendChild(c) { this.children.push(c); return c; },
    append(...c) { this.children.push(...c); },
    prepend(...c) { this.children.unshift(...c); },
    insertBefore(c) { this.children.push(c); return c; },
    replaceChildren(...c) { this.children = c; },
    removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; },
    remove: noop,
    setAttribute(k, v) { this.attrs[k] = String(v); if (k === "id") ids[v] = proxy; },
    getAttribute(k) { return this.attrs[k] ?? null; },
    removeAttribute(k) { delete this.attrs[k]; },
    addEventListener: noop, removeEventListener: noop,
    getBBox: () => ({ x: 0, y: 0, width: 40, height: 16 }),
    getBoundingClientRect: () => ({ x: 0, y: 0, left: 0, top: 0, width: 800, height: 450, right: 800, bottom: 450 }),
    getComputedTextLength: () => 40,
    getContext: () => new Proxy({}, { get: (t, p) => (p in t ? t[p] : noop), set: (t, p, v) => { t[p] = v; return true; } }),
    querySelector(sel) { return find(this, sel)[0] || makeEl("g"); },
    querySelectorAll(sel) { return find(this, sel); },
    get firstChild() { return this.children[0] || null; },
    get lastChild() { return this.children.at(-1) || null; },
    get clientWidth() { return 800; }, get clientHeight() { return 450; },
  };
  const proxy = new Proxy(node, { get: (t, p) => (p in t ? t[p] : typeof p === "string" ? noop : undefined) });
  return proxy;
}
function find(root, sel) {
  const want = String(sel).trim().split(/\s+/).at(-1).replace(/:.*$/, "");
  const out = [];
  const walk = (n) => {
    for (const c of n.children || []) {
      if (!c || typeof c !== "object") continue;
      const tag = c.tagName?.toLowerCase();
      if ((want.startsWith("#") && c.attrs?.id === want.slice(1)) ||
          (want.startsWith(".") && String(c.attrs?.class || "").split(/\s+/).includes(want.slice(1))) ||
          (!/^[#.]/.test(want) && tag === want.toLowerCase())) out.push(c);
      walk(c);
    }
  };
  walk(root);
  return out;
}

const ids = {};
const body = makeEl("body");
const stage = makeEl("div");
ids.stage = stage;
// Elements the fragment's markup declares (<svg id="v">, <div id="out">, ...).
for (const m of visual.html.matchAll(/<(\w+)[^>]*\bid\s*=\s*["']([^"']+)["']/g)) {
  const el = makeEl(m[1]);
  el.attrs.id = m[2];
  ids[m[2]] = el;
  stage.children.push(el);
}

const handlers = {};
const Visual = {
  get stage() { return stage; },
  on(name, fn) { (handlers[name] = handlers[name] || []).push(fn); },
  value: () => undefined,
  state(text) { lastState = String(text); },
  svg(tag, attrs = {}, parent = null) {
    const el = makeEl(tag);
    for (const [k, v] of Object.entries(attrs)) { if (k === "text") el.textContent = String(v); else el.setAttribute(k, v); }
    if (parent) parent.appendChild(el);
    return el;
  },
  tween: (ms, fn) => { fn(1); return Promise.resolve(); },
  sleep: () => Promise.resolve(),
};
const document = {
  getElementById: (id) => ids[id] || null,
  querySelector: (sel) => (sel.startsWith("#") ? ids[sel.slice(1)] || null : find(stage, sel)[0] || null),
  querySelectorAll: (sel) => find(stage, sel),
  createElement: (t) => makeEl(t), createElementNS: (ns, t) => makeEl(t), createTextNode: (t) => ({ textContent: t }),
  body, documentElement: body, addEventListener: noop,
};
const context = vm.createContext({
  Visual, document, console: { log: noop, warn: noop, error: noop },
  setTimeout: (fn) => { Promise.resolve().then(fn); return 0; }, clearTimeout: noop,
  setInterval: () => 0, clearInterval: noop,  // intervals never fire: a test must finish
  requestAnimationFrame: (fn) => { Promise.resolve().then(() => fn(0)); return 0; }, cancelAnimationFrame: noop,
  performance: { now: () => 0 }, getComputedStyle: () => ({ getPropertyValue: () => "" }),
  addEventListener: noop, removeEventListener: noop, innerWidth: 800, innerHeight: 450,
});
context.window = context;
context.self = context;

// Errors from the visual's own code. The fake page is permissive (unknown DOM calls do nothing), so a
// SyntaxError, ReferenceError or TypeError here is a real bug that would also break the graph in class.
const realBug = (e) => /^(SyntaxError|ReferenceError|TypeError|RangeError)$/.test(String(e?.name)) ||
  /\bis not defined\b|is not a function|Cannot read properties/.test(String(e?.message));
function report(where, e) {
  if (realBug(e)) problems.push(`${where}: ${e.name}: ${String(e.message).slice(0, 160)}`);
}
const withTimeout = (p) => Promise.race([p, new Promise((r) => setTimeout(() => r("timeout"), 1500))]);

async function call(name, value) {
  for (const fn of handlers[name] || []) {
    try {
      if ((await withTimeout(Promise.resolve(fn(value)))) === "timeout")
        problems.push(`control "${name}": its handler never finished (an endless wait or loop?)`);
    } catch (e) { report(`control "${name}"`, e); }
  }
  return lastState;
}

// The graph helper the real page has (Visual.chart), drawing into this fake page.
context.Visual = Visual;
vm.runInContext(readFileSync(new URL("../../web/js/visual/chart.js", import.meta.url), "utf8"), context);
const scripts = [...visual.html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1]);
for (const code of scripts) {
  try { vm.runInContext(code, context, { timeout: 2000 }); } catch (e) {
    if (/timed out/i.test(e.message)) problems.push("the script runs forever when it loads (an endless loop)");
    else report("while loading", e);
  }
}

// ---------- layout: boxes of what is drawn in the main <svg>, checked for clashes ----------
const num = (v, d = 0) => (Number.isFinite(parseFloat(v)) ? parseFloat(v) : d);
function boxes(node, dx = 0, dy = 0, out = []) {
  for (const c of node.children || []) {
    if (!c || typeof c !== "object" || !c.attrs) continue;
    const a = c.attrs, tag = c.tagName.toLowerCase();
    if (tag === "defs" || tag === "clippath" || tag === "mask") continue;  // never drawn
    let x = dx, y = dy;
    if (a.transform) {
      const t = /^\s*translate\(\s*(-?[\d.]+)[\s,]+(-?[\d.]+)?\s*\)\s*$/.exec(a.transform);
      if (!t) continue;  // rotated or scaled: not modelled
      x += num(t[1]); y += num(t[2]);
    }
    if (tag === "rect") out.push({ kind: "shape", label: `a box at (${num(a.x)}, ${num(a.y)})`, x: x + num(a.x), y: y + num(a.y), w: num(a.width), h: num(a.height) });
    else if (tag === "circle") out.push({ kind: "shape", label: `a circle at (${num(a.cx)}, ${num(a.cy)})`, x: x + num(a.cx) - num(a.r), y: y + num(a.cy) - num(a.r), w: 2 * num(a.r), h: 2 * num(a.r) });
    else if (tag === "ellipse") out.push({ kind: "shape", label: `an ellipse at (${num(a.cx)}, ${num(a.cy)})`, x: x + num(a.cx) - num(a.rx), y: y + num(a.cy) - num(a.ry), w: 2 * num(a.rx), h: 2 * num(a.ry) });
    else if (tag === "polygon" && a.points) {
      const p = a.points.trim().split(/[\s,]+/).map(Number);
      const xs = p.filter((_, i) => i % 2 === 0), ys = p.filter((_, i) => i % 2 === 1);
      if (xs.length > 2) out.push({ kind: "shape", label: `a polygon at (${Math.round(Math.min(...xs))}, ${Math.round(Math.min(...ys))})`, x: x + Math.min(...xs), y: y + Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) });
    } else if (tag === "text" && String(c.textContent).trim()) {
      const fs = num(a["font-size"], num(String(a.style || "").match(/font-size:\s*([\d.]+)/)?.[1], 16));
      const w = String(c.textContent).length * fs * 0.55, anchor = a["text-anchor"];
      const tx = x + num(a.x) - (anchor === "middle" ? w / 2 : anchor === "end" ? w : 0);
      const base = a["dominant-baseline"] === "middle" || a["dominant-baseline"] === "central" ? y + num(a.y) - fs * 0.5 : y + num(a.y) - fs * 0.8;
      if (/var\(--(line|marker)\)/.test(String(a.fill || ""))) layout.add(`the text "${String(c.textContent).slice(0, 30)}" uses a very light colour; use var(--ink) or var(--muted)`);
      out.push({ kind: "text", label: `the text "${String(c.textContent).slice(0, 30)}"`, x: tx, y: base, w, h: fs });
    }
    if (tag !== "text") boxes(c, x, y, out);
  }
  return out;
}
const area = (b) => Math.max(0, b.w) * Math.max(0, b.h);
const inter = (a, b) => Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
const inside = (a, b, tol = 3) => a.x >= b.x - tol && a.y >= b.y - tol && a.x + a.w <= b.x + b.w + tol && a.y + a.h <= b.y + b.h + tol;
function checkLayout(when) {
  const svg = [...Object.values(ids), ...stage.children].find((e) => e?.tagName === "SVG" && e.children.length);
  if (!svg) return;
  const vb = String(svg.attrs.viewBox || "").split(/[\s,]+/).map(Number);
  const items = boxes(svg).filter((b) => area(b) > 0 && (b.kind === "text" || area(b) >= 600));
  for (let i = 0; i < items.length; i++) {
    const a = items[i];
    if (vb.length === 4 && (a.x < vb[0] - 5 || a.y < vb[1] - 5 || a.x + a.w > vb[0] + vb[2] + 5 || a.y + a.h > vb[1] + vb[3] + 5))
      layout.add(`${when}: ${a.label} goes outside the picture`);
    for (let j = i + 1; j < items.length; j++) {
      const b = items[j], o = inter(a, b);
      if (o < 0.15 * Math.min(area(a), area(b))) continue;
      if (a.kind === "text" && b.kind === "text") layout.add(`${when}: ${a.label} overlaps ${b.label}`);
      else if (!inside(a, b) && !inside(b, a)) layout.add(`${when}: ${a.label} and ${b.label} overlap (one sits half on top of the other)`);
    }
  }
}

const controls = visual.controls || [];
const first = (c) => (c.type === "slider" ? c.min : c.type === "toggle" ? false : c.type === "choice" ? c.options[0] : undefined);
for (const c of controls) if (c.type !== "button") await call(c.name, first(c));
if (!lastState) problems.push("Visual.state(...) is never called after the first draw");
checkLayout("at the start");
states.push(lastState);

for (const c of controls) {
  const before = lastState;
  const seen = new Set([before]);
  if (c.type === "button") {
    const firstPress = await call(c.name);
    if (firstPress === before && (handlers[c.name] || []).length)
      problems.push(`the first press of "${c.name}" changes nothing; every press must visibly change the picture`);
    seen.add(firstPress);
    for (let i = 0; i < 2; i++) seen.add(await call(c.name));
  } else if (c.type === "slider") {
    seen.add(await call(c.name, c.max));
    checkLayout(`with "${c.name}" at ${c.max}`);  // the longest labels usually come at the top of the range
    await call(c.name, c.min);
  } else if (c.type === "toggle") {
    seen.add(await call(c.name, true));
    await call(c.name, false);
  } else {
    seen.add(await call(c.name, c.options[1]));
    await call(c.name, c.options[0]);
  }
  states.push(...seen);
  checkLayout(`after using "${c.name}"`);
  if (seen.size < 2 && (handlers[c.name] || []).length)
    problems.push(`using control "${c.name}" never changes what Visual.state reports, so it probably changes ` +
                  `nothing on screen: change the state, redraw, and call Visual.state with the new values`);
}

if (Visual._clip && Visual._clip.max > Visual._clip.top * 1.02)
  layout.add(`the highest point reaches y = ${+Visual._clip.max.toPrecision(3)} but the y axis stops at ${Visual._clip.top}, ` +
             `so the curve would be cut off: set the y range to at least [.., ${+(Visual._clip.max * 1.1).toPrecision(2)}]`);
// The teacher's slider moves from the script, in order, from a fresh start: what the graph reports after each.
const moves = [];
if (Array.isArray(visual.moves) && visual.moves.length) {
  for (const c of controls) if (c.type !== "button") await call(c.name, first(c));
  for (const [name, value] of visual.moves) moves.push({ control: name, value, graph_reports: await call(name, value) });
}
console.log(JSON.stringify({ problems: [...new Set(problems)], layout: [...layout].slice(0, 4),
  states: [...new Set(states)].slice(0, 12), moves }));
