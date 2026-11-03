// The textbook in the Slides view: the pages the teacher chose (material/book.py), drawn as pictures, with where each
// printed line and word sits (fractions of the page). The teacher highlights, underlines and circles printed words,
// zooms to a worked example and covers its printed answer while the class solves it ([BOOK_EXAMPLE]), then uncovers
// it and circles the results that match the notebook ([BOOK_ANSWER]).

import { h, icon } from "./ui.js";
import { drawPen, svgLayer } from "./pen.js";

const NS = "http://www.w3.org/2000/svg";
const W = 1000;          // the pen layer's width in its own units (its height follows the page's ratio)
const MAX_ZOOM = 2.6;
const ZOOM_PAD = 0.025;  // room around a zoomed example, as a share of the page

// Letters and digits of any script (as book.py _norm), so a word in another alphabet is matched, not dropped.
const norm = (s) => String(s).toLowerCase().replace(/[–−]/g, "-").replace(/[^\p{L}\p{N}.]+/gu, " ").trim().split(/\s+/).filter(Boolean);
const union = (boxes) => [Math.min(...boxes.map(b => b[0])), Math.min(...boxes.map(b => b[1])),
  Math.max(...boxes.map(b => b[2])), Math.max(...boxes.map(b => b[3]))];
const inside = (b, r) => b[0] >= r[0] - 0.01 && b[2] <= r[2] + 0.01 && b[1] >= r[1] - 0.01 && b[3] <= r[3] + 0.01;

export class BookView {
  constructor(book) {
    this.book = book || null;
    this.n = null;
    this.zoom = null;
    this.nameEl = h("span", { class: "bk-name" }, this.book?.file || "");
    this.pageEl = h("span", { class: "bk-num" });
    this.img = h("img", { class: "bk-img", alt: "" });
    this.layer = svgLayer("bk-pen");
    this.page = h("div", { class: "bk-page" }, this.img, this.layer);
    this.view = h("div", { class: "bk-view" }, this.page);
    this.el = h("div", { class: "bk-card hidden" },
      h("div", { class: "bk-head" }, icon("file"), this.nameEl, this.pageEl), this.view);
    this.img.addEventListener("load", () => this.layout());
    new ResizeObserver(() => this.layout()).observe(this.view);
  }

  get has() { return !!this.book && Object.keys(this.book.pages || {}).length > 0; }
  _page(n = this.n) { return this.book?.pages?.[String(n)]; }

  /** Show page n (the number printed in the book), whole, with nothing on it. */
  show(n) {
    const p = this._page(n);
    if (!p) return false;
    if (String(this.n) !== String(n)) {
      this.n = n;
      this.img.src = p.url;
      this.img.alt = `${this.book.file}, page ${n}`;
      this.layer.setAttribute("viewBox", `0 0 ${W} ${W / p.ratio}`);
      this.page.classList.remove("enter"); void this.page.offsetWidth; this.page.classList.add("enter");
    }
    this.clear();
    this.zoom = null;
    this.pageEl.textContent = `page ${n} · ${this.book.first}–${this.book.last}`;
    this.layout();
    return true;
  }

  clear() {
    this.page.querySelectorAll(".bk-mark, .bk-cover").forEach(e => e.remove());
    this.layer.replaceChildren();
  }

  /** Fit the page in the view, then apply the zoom (a box of the page, centred and as large as fits). */
  layout() {
    const p = this._page();
    if (!p) return;
    const vw = this.view.clientWidth, vh = this.view.clientHeight;
    if (!vw || !vh) return;
    const pw = Math.min(vw, vh * p.ratio), ph = pw / p.ratio;
    this.page.style.width = `${pw}px`; this.page.style.height = `${ph}px`;
    let s = 1, x = (vw - pw) / 2, y = (vh - ph) / 2;
    if (this.zoom) {
      const [x0, y0, x1, y1] = this.zoom;
      s = Math.max(1, Math.min(MAX_ZOOM, 0.94 * Math.min(vw / ((x1 - x0) * pw), vh / ((y1 - y0) * ph))));
      x = vw / 2 - s * pw * (x0 + x1) / 2;
      y = vh / 2 - s * ph * (y0 + y1) / 2;
      // never show past the page's edges when it is larger than the view
      x = s * pw > vw ? Math.min(0, Math.max(vw - s * pw, x)) : (vw - s * pw) / 2;
      y = s * ph > vh ? Math.min(0, Math.max(vh - s * ph, y)) : (vh - s * ph) / 2;
    }
    this.page.style.transform = `translate(${x}px, ${y}px) scale(${s})`;
  }

  zoomTo(box) {
    this.zoom = box ? [Math.max(0, box[0] - ZOOM_PAD), Math.max(0, box[1] - ZOOM_PAD),
      Math.min(1, box[2] + ZOOM_PAD), Math.min(1, box[3] + ZOOM_PAD)] : null;
    this.layout();
  }

  /** Boxes of the printed words that read `text` (one per printed line), optionally only inside `region`. */
  findWords(text, region = null, n = this.n) {
    const p = this._page(n), want = norm(text);
    if (!p || !want.length) return [];
    const words = region ? p.words.filter(w => inside(w.box, region)) : p.words;
    const flat = words.flatMap((w, i) => norm(w.text).map(t => [t, i]));
    for (let s = 0; s + want.length <= flat.length; s++) {
      if (want.every((t, k) => flat[s + k][0] === t)) {
        const rows = {};
        for (const i of new Set(flat.slice(s, s + want.length).map(f => f[1]))) {
          const b = words[i].box;
          (rows[b[1].toFixed(2)] ||= []).push(b);
        }
        return Object.values(rows).map(union);
      }
    }
    return [];
  }

  _pct(box, pad = 0.003) {
    const [x0, y0, x1, y1] = box;
    return `left:${(x0 - pad) * 100}%; top:${(y0 - pad) * 100}%; width:${(x1 - x0 + 2 * pad) * 100}%; height:${(y1 - y0 + 2 * pad) * 100}%`;
  }

  _units(box) {
    const r = this._page().ratio;
    return { x0: box[0] * W, y0: box[1] * W / r, x1: box[2] * W, y1: box[3] * W / r };
  }

  highlight(text, region = null) {
    const boxes = this.findWords(text, region);
    boxes.forEach(b => this.page.append(h("div", { class: "bk-mark", style: this._pct(b) })));
    return boxes.length > 0;
  }

  /** A quick pen line under the words, like a teacher marking the given values of a problem. */
  underline(text) {
    const boxes = this.findWords(text);
    boxes.forEach((b, k) => {
      const { x0, x1, y1 } = this._units(b), y = y1 + 2.5, wob = (x1 - x0) / 3;
      const path = document.createElementNS(NS, "path");
      path.setAttribute("d", `M${x0 - 2},${y + 0.6} C${x0 + wob},${y - 1.6} ${x1 - wob},${y + 2.2} ${x1 + 3},${y - 0.4}`);
      path.setAttribute("class", "pen-stroke bk-line");
      this.layer.appendChild(path);
      const len = path.getTotalLength?.() || 0;
      if (len) {
        path.style.strokeDasharray = `${len}`; path.style.strokeDashoffset = `${len}`;
        path.getBoundingClientRect();
        path.style.transition = `stroke-dashoffset 420ms ease-out ${k * 120}ms`;
        path.style.strokeDashoffset = "0";
      }
    });
    return boxes.length > 0;
  }

  circle(text, region = null) {
    let boxes = this.findWords(text, region);
    if (!boxes.length && region) boxes = this.findWords(text);
    if (!boxes.length) return false;
    const { x0, y0, x1, y1 } = this._units(union(boxes));
    drawPen(this.layer, (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 + 9, (y1 - y0) / 2 + 6, { seed: Math.round(x0 + y0), ms: 650 });
    return true;
  }

  // The book may print a result rounded ("69 m" for the notebook's 69.3 m): circle the printed number that matches it,
  // by the same rule the answer check uses (eris/material/book.py close), the last one in the answer.
  _circleNumber(result, region) {
    const value = (t) => { const [a, b] = t.split("/").map(parseFloat); return b ? a / b : a; };  // "3/4" -> 0.75
    const x = value(String(result).match(/-?\d+(?:\.\d+)?(?:\/\d+(?:\.\d+)?)?/)?.[0] ?? "");
    if (Number.isNaN(x)) return false;
    const close = (b) => b === x || Math.abs(x - b) <= Math.max(0.05 * Math.abs(b), Number.isInteger(b) ? 0.5 : 0.051);
    const words = (this._page()?.words || []).filter(w => (!region || inside(w.box, region))
      && /^-?\d+(\.\d+)?(\/\d+(\.\d+)?)?$/.test(w.text) && close(value(w.text)));
    const w = words[words.length - 1];
    if (!w) return false;
    const { x0, y0, x1, y1 } = this._units(w.box);
    drawPen(this.layer, (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 + 9, (y1 - y0) / 2 + 6, { seed: Math.round(x0), ms: 650 });
    return true;
  }

  _example(name) {
    const want = String(name).trim().toLowerCase().replace(/\s+/g, " ");
    return (this._page()?.examples || []).find(e => e.name.toLowerCase() === want) || null;
  }

  /** Zoom to a worked example, mark its name, and cover its printed answer while the class solves it. */
  example(name) {
    const ex = this._example(name);
    if (!ex) return false;
    this.clear();
    this.highlight(ex.name, union(ex.question));
    ex.answer.forEach(b => this.page.append(h("div", { class: "bk-cover", style: this._pct(b, 0.004) },
      h("span", {}, "Book's answer · hidden while we solve"))));
    this.zoomTo(union([...ex.question, ...ex.answer]));
    return true;
  }

  /** Uncover the answer and circle each of the notebook's results the book prints too. */
  answer(name, matches = []) {
    const ex = this._example(name);
    if (!ex) return false;
    this.page.querySelectorAll(".bk-cover").forEach(c => { c.classList.add("off"); setTimeout(() => c.remove(), 450); });
    this.zoomTo(union([...ex.question, ...ex.answer]));
    const region = ex.answer.length ? union(ex.answer) : null;
    setTimeout(() => {
      for (const m of matches) if (!this.circle(m, region)) this._circleNumber(m, region);
    }, 420);
    return true;
  }
}
