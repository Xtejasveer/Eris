// Flow diagrams on the board: drawn by this code from the script's [FLOW] structure, one block at a time.
// Blocks go top to bottom. An arrow to the next block is straight; a loop back to an earlier block runs up the
// right side; a skip forward (or to the end) runs down the left side. Questions are diamonds with labelled
// branches. An arrow is drawn once both of its blocks are on the board.

const NS = "http://www.w3.org/2000/svg";
const W = 800;              // picture width; the height grows with the number of blocks
const TOP = 34, GAP = 46;   // space above the first block, and between blocks
const BOX_W = 360, PAD = 14, FONT = 20, LINE_H = 25;
const DIAMOND_W = 400;
const SIDE_STEP = 30;       // each extra loop-back or skip arrow runs a little further out

function el(tag, attrs = {}, parent = null, text = null) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}

// Split a label into lines that fit `width` (rough width per character: plenty for the board's hand font).
function wrap(label, width, font = FONT) {
  const max = Math.max(8, Math.floor(width / (font * 0.52)));
  const lines = [];
  let cur = "";
  for (const word of label.split(/\s+/)) {
    if (cur && (cur + " " + word).length > max) { lines.push(cur); cur = word; }
    else cur = cur ? `${cur} ${word}` : word;
  }
  if (cur) lines.push(cur);
  return lines;
}

// Positions for every block (and the "End" pill if anything points to it).
export function layoutFlow(blocks, edges) {
  const cx = W / 2;
  let y = TOP;
  const pos = {};
  for (const b of blocks) {
    const question = b.kind === "question";
    const lines = wrap(b.label, question ? DIAMOND_W * 0.55 : BOX_W - 2 * PAD);
    const h = question ? Math.max(96, lines.length * LINE_H + 60) : lines.length * LINE_H + 2 * PAD;
    const w = question ? DIAMOND_W : BOX_W;
    pos[b.id] = { x: cx - w / 2, y, w, h, cx, cy: y + h / 2, lines, kind: b.kind };
    y += h + GAP;
  }
  if (edges.some(e => e.to === "end")) {
    pos.end = { x: cx - 60, y, w: 120, h: 44, cx, cy: y + 22, lines: ["End"], kind: "end" };
    y += 44 + GAP;
  }
  return { pos, height: y - GAP + TOP };
}

// The path of one arrow, plus where its label goes.
function route(edge, pos, order, sideIndex) {
  const a = pos[edge.from], b = pos[edge.to];
  const ia = order.indexOf(edge.from), ib = edge.to === "end" ? order.length : order.indexOf(edge.to);
  if (ib === ia + 1) {  // straight down to the next block
    return { d: `M ${a.cx} ${a.y + a.h} L ${b.cx} ${b.y - 4}`, lx: a.cx + 10, ly: a.y + a.h + 20, anchor: "start" };
  }
  if (ib <= ia) {  // loop back up the right side
    const out = Math.max(a.x + a.w, b.x + b.w) + 34 + sideIndex * SIDE_STEP;
    return { d: `M ${a.x + a.w} ${a.cy} H ${out} V ${b.cy} H ${b.x + b.w + 4}`, lx: a.x + a.w + 8, ly: a.cy - 8, anchor: "start" };
  }
  const out = Math.min(a.x, b.x) - 34 - sideIndex * SIDE_STEP;  // skip forward down the left side
  return { d: `M ${a.x} ${a.cy} H ${out} V ${b.cy} H ${b.x - 4}`, lx: a.x - 8, ly: a.cy - 8, anchor: "end" };
}

export class FlowBoard {
  constructor(flow) {
    this.flow = flow;
    this.order = flow.blocks.map(b => b.id);
    const { pos, height } = layoutFlow(flow.blocks, flow.edges);
    this.pos = pos;
    this.svg = el("svg", { viewBox: `0 0 ${W} ${height}`, class: "flow-svg", preserveAspectRatio: "xMidYMin meet" });
    const defs = el("defs", {}, this.svg);
    const marker = el("marker", { id: `arrow-${flow.id}`, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" }, defs);
    el("path", { d: "M 0 0 L 10 5 L 0 10 z", class: "flow-arrowhead" }, marker);
    this.edgeLayer = el("g", {}, this.svg);
    this.blockLayer = el("g", {}, this.svg);
    this.drawn = new Set();
    this.edgeEls = new Map();
    this.blockEls = new Map();
    // Side arrows that share a side get their own lane.
    let right = 0, left = 0;
    this.routes = flow.edges.map(e => {
      const ia = this.order.indexOf(e.from), ib = e.to === "end" ? this.order.length : this.order.indexOf(e.to);
      const lane = ib === ia + 1 ? 0 : ib <= ia ? right++ : left++;
      return { edge: e, ...route(e, pos, this.order, lane) };
    });
  }

  get revealed() { return this.drawn.size - (this.drawn.has("end") ? 1 : 0); }

  _drawBlock(id, animate) {
    const p = this.pos[id];
    const g = el("g", { class: `flow-block ${p.kind}${animate ? " enter" : ""}`, "data-block": id }, this.blockLayer);
    let shape;
    if (p.kind === "question") {
      shape = el("polygon", { points: `${p.cx},${p.y} ${p.x + p.w},${p.cy} ${p.cx},${p.y + p.h} ${p.x},${p.cy}` }, g);
    } else {
      shape = el("rect", { x: p.x, y: p.y, width: p.w, height: p.h, rx: p.kind === "end" ? p.h / 2 : 14 }, g);
    }
    shape.setAttribute("class", "flow-shape");
    const first = p.cy - ((p.lines.length - 1) * LINE_H) / 2 + 7;
    p.lines.forEach((line, i) => el("text", { x: p.cx, y: first + i * LINE_H, "text-anchor": "middle", class: "flow-text" }, g, line));
    this.blockEls.set(id, g);
    this.drawn.add(id);
  }

  _drawReadyEdges(animate) {
    for (const r of this.routes) {
      const key = `${r.edge.from}>${r.edge.to}`;
      if (this.edgeEls.has(key) || !this.drawn.has(r.edge.from) || !this.drawn.has(r.edge.to)) continue;
      const g = el("g", { class: `flow-edge${animate ? " enter" : ""}` }, this.edgeLayer);
      el("path", { d: r.d, class: "flow-line", "marker-end": `url(#arrow-${this.flow.id})` }, g);
      if (r.edge.label) el("text", { x: r.lx, y: r.ly, "text-anchor": r.anchor, class: "flow-branch" }, g, r.edge.label);
      this.edgeEls.set(key, g);
    }
  }

  // Draw the next block (and "End" once something leads there and the last block is on the board).
  next(animate = true) {
    const id = this.order[this.revealed];
    if (!id) return null;
    this._drawBlock(id, animate);
    if (this.revealed === this.order.length && this.pos.end && !this.drawn.has("end")) this._drawBlock("end", animate);
    this._drawReadyEdges(animate);
    this.blockEls.get(id)?.scrollIntoView?.({ block: "nearest", behavior: animate ? "smooth" : "auto" });
    return id;
  }

  highlight(id) {
    const g = this.blockEls.get(id);
    if (!g) return false;
    for (const other of this.blockEls.values()) other.classList.remove("hl");
    g.classList.remove("hl"); void g.getBBox?.(); g.classList.add("hl");
    return true;
  }

  // What is on the board now, for the doubt agent.
  describe() {
    const shown = this.order.filter(id => this.drawn.has(id));
    return `${this.flow.title}: ${shown.map(id => this.flow.blocks.find(b => b.id === id).label).join(" -> ")}` +
      (shown.length < this.order.length ? ` (${this.order.length - shown.length} more block(s) not drawn yet)` : "");
  }
}
