// The class stage: three environments the script switches between.
// Notebook (hand-written ruled page), Slides, and Code (editor tabs + terminal).

import { h, icon, esc } from "./ui.js";
import { highlightLine } from "./highlight.js";

const ENVS = [["notebook", "Notebook", "book"], ["slides", "Slides", "slides"], ["code", "Code", "code"]];
const NOTE_MS = 26;   // per character, "handwriting"
const CODE_MS = 14;   // per character, "typing"

export class Stage {
  constructor(slides) {
    this.slides = slides || {};
    this.files = {};          // name -> { lines, tab, body }
    this.current = null;
    this.env = null;

    this.indicator = h("div", { class: "env-indicator", role: "status", "aria-label": "Current environment" },
      h("span", { class: "env-glider" }),
      ENVS.map(([key, label, ic]) => h("span", { class: "env-pill", dataset: { env: key } }, icon(ic), label)));

    // Notebook pages: "Lecture" plus one per [NEW_PAGE]. Like the environment pills, the page tabs
    // only show where the teacher is; the script turns the pages.
    this.pageBar = h("div", { class: "nb-pages", "aria-label": "Notebook pages" });
    this.paper = h("div", { class: "nb-paper" }, h("div", { class: "nb-margin" }));
    this.notebook = h("div", { class: "env env-notebook" }, this.pageBar, this.paper);
    this.pages = [];
    this._addPage("Lecture");

    this.slideBox = h("div", { class: "slide" }, h("div", { class: "slide-empty" }, icon("slides"), "No slide shown yet"));
    this.slideNum = h("span", { class: "slide-num" });
    this.slidesEl = h("div", { class: "env env-slides" }, h("div", { class: "slide-frame" }, this.slideBox, this.slideNum));

    this.tabBar = h("div", { class: "ed-tabs" });
    this.codeBody = h("div", { class: "ed-body" }, h("div", { class: "ed-empty" }, icon("code"), "No code yet"));
    this.termBody = h("div", { class: "term-body" });
    this.term = h("div", { class: "terminal" },
      h("div", { class: "term-head" }, icon("terminal"), "Terminal", h("span", { class: "term-cwd" }, "board/")), this.termBody);
    this.codeEl = h("div", { class: "env env-code" },
      h("div", { class: "editor-win" }, h("div", { class: "ed-chrome" }, h("i"), h("i"), h("i")), this.tabBar, this.codeBody), this.term);

    this.el = h("div", { class: "stage-envs" }, this.notebook, this.slidesEl, this.codeEl);
    this.setEnv("notebook");
  }

  setEnv(env) {
    if (this.env === env) return;
    this.env = env;
    const i = ENVS.findIndex(e => e[0] === env);
    this.indicator.style.setProperty("--i", i);
    this.indicator.querySelectorAll(".env-pill").forEach(p => p.classList.toggle("active", p.dataset.env === env));
    for (const [key, el] of [["notebook", this.notebook], ["slides", this.slidesEl], ["code", this.codeEl]])
      el.classList.toggle("active", key === env);
  }

  // ---------- notebook ----------
  get notePage() { return this.pages[this.page].el; }

  _addPage(title) {
    const el = h("div", { class: "nb-lines" });
    const tab = h("span", { class: "nb-page-tab" }, title);
    this.pages.push({ title, el, tab });
    this.paper.append(el);
    this.pageBar.append(tab);
    this.pageBar.classList.toggle("hidden", this.pages.length < 2);
    this.showPage(this.pages.length - 1);
  }

  showPage(i) {
    this.page = i;
    this.pages.forEach((p, j) => { p.el.classList.toggle("hidden", j !== i); p.tab.classList.toggle("active", j === i); });
  }

  async newPage(title, ctl) {
    this.setEnv("notebook");
    this._addPage(title);
    this.paper.scrollTop = 0;
    await this.noteTitle(title, ctl);
  }

  // Pages to search for a quote: the current one first, then the others from newest to oldest.
  _pageOrder() {
    return [this.page, ...this.pages.map((_, i) => i).reverse().filter(i => i !== this.page)];
  }

  lookBack(text) {
    this.setEnv("notebook");
    for (const i of this._pageOrder()) {
      const el = [...this.pages[i].el.querySelectorAll(".nb-line")].reverse()
        .find(line => line.textContent.toLowerCase().includes(text.trim().toLowerCase()));
      if (!el) continue;
      this.showPage(i);
      markText(el, text, "center");
      el.classList.remove("nb-focus"); void el.offsetWidth; el.classList.add("nb-focus");
      return true;
    }
    return false;
  }

  async _write(el, text, ctl, ms) {
    el.classList.add("writing");
    const fast = !ctl;
    if (fast) { el.textContent = text; el.classList.remove("writing"); return; }
    let shown = "";
    for (const ch of text) {
      shown += ch;
      el.textContent = shown;
      if (ch !== " ") await ctl.tick(ms);
    }
    el.classList.remove("writing");
  }

  async noteTitle(text, ctl) {
    this.setEnv("notebook");
    const el = h("div", { class: "nb-line nb-title" });
    this.notePage.append(el);
    el.scrollIntoView({ block: "nearest", behavior: ctl ? "smooth" : "auto" });
    await this._write(el, text, ctl, NOTE_MS);
  }

  async note(text, ctl) {
    this.setEnv("notebook");
    for (const line of text.split("\n")) {
      const indent = line.match(/^\s*/)[0].length;
      const el = h("div", { class: "nb-line", style: indent ? `padding-left:${indent * 0.55}em` : null });
      this.notePage.append(el);
      el.scrollIntoView({ block: "nearest", behavior: ctl ? "smooth" : "auto" });
      await this._write(el, line.trim() || " ", ctl, NOTE_MS);
    }
  }

  noteHighlight(text) {
    this.setEnv("notebook");
    for (const i of this._pageOrder()) {
      const lines = [...this.pages[i].el.querySelectorAll(".nb-line")].reverse();
      if (lines.some(el => markText(el, text))) { this.showPage(i); return true; }
    }
    return false;
  }

  // ---------- slides ----------
  showSlide(n) {
    this.setEnv("slides");
    const text = this.slides[n] ?? this.slides[String(n)];
    if (text == null) return false;
    const [title, ...rest] = text.split("\n").map(s => s.trim()).filter(Boolean);
    this.slideBox.replaceChildren(h("h2", { class: "slide-title" }, title || `Slide ${n}`),
      h("ul", { class: "slide-points" }, rest.map(r => h("li", {}, r.replace(/^[•\-*]\s*/, "")))));
    this.slideBox.classList.remove("enter"); void this.slideBox.offsetWidth; this.slideBox.classList.add("enter");
    this.slideNum.textContent = `${n} / ${Object.keys(this.slides).length}`;
    return true;
  }

  slideHighlight(text) {
    this.setEnv("slides");
    return [...this.slideBox.querySelectorAll("h2, li")].some(el => markText(el, text));
  }

  // ---------- code ----------
  _openFile(name) {
    if (!this.files[name]) {
      const tab = h("div", { class: "ed-tab" }, icon("file"), name);
      const body = h("div", { class: "ed-code" });
      this.tabBar.append(tab);
      this.files[name] = { lines: [], tab, body };
    }
    const f = this.files[name];
    if (this.current !== name) {
      this.current = name;
      Object.values(this.files).forEach(x => x.tab.classList.toggle("active", x === f));
      this.codeBody.replaceChildren(f.body);
    }
    return f;
  }

  _lineEl(n, html) {
    return h("div", { class: "ed-line" }, h("span", { class: "ed-no" }, n), h("span", { class: "ed-src", html: html || " " }));
  }

  async writeCode(name, code, ctl) {
    this.setEnv("code");
    const f = this._openFile(name);
    f.body.replaceChildren();
    f.lines = code.split("\n");
    for (let i = 0; i < f.lines.length; i++) {
      const line = f.lines[i];
      const row = this._lineEl(i + 1, "");
      const src = row.lastChild;
      f.body.append(row);
      if (ctl) {
        row.classList.add("typing");
        row.scrollIntoView({ block: "nearest" });
        let shown = "";
        for (const ch of line) { shown += ch; src.innerHTML = highlightLine(shown); if (ch !== " ") await ctl.tick(CODE_MS); }
        row.classList.remove("typing");
        await ctl.tick(60);
      }
      src.innerHTML = highlightLine(line) || " ";
    }
  }

  openFile(name) {
    if (!this.files[name]) return false;
    this.setEnv("code");
    this._openFile(name);
    Object.values(this.files).forEach(f => [...f.body.children].forEach(r => r.classList.remove("hl")));
    this.codeBody.scrollTop = 0;
    return true;
  }

  // Where the class is looking (environment, notebook page, open file), to come back after a doubt.
  view() { return { env: this.env, page: this.page, file: this.current }; }

  restoreView(v) {
    if (!v) return;
    if (v.file && this.files[v.file]) this._openFile(v.file);
    if (v.page != null && this.pages[v.page]) this.showPage(v.page);
    this.setEnv(v.env || "notebook");
  }

  highlight(name, lines) {
    if (!this.files[name]) return false;
    this.setEnv("code");
    const f = this._openFile(name);
    const [a, b] = String(lines).split("-").map(Number);
    const rows = [...f.body.children];
    rows.forEach((r, i) => r.classList.toggle("hl", i + 1 >= a && i + 1 <= (b || a)));
    rows[a - 1]?.scrollIntoView({ block: "center", behavior: "smooth" });
    return true;
  }

  runStart(cmd) {
    this.setEnv("code");
    const file = cmd.replace(/^python\s+/, "");
    if (this.files[file]) this._openFile(file);
    Object.values(this.files).forEach(f => [...f.body.children].forEach(r => r.classList.remove("hl")));
    this.termBody.append(h("div", { class: "term-cmd", html: `<span class="term-prompt">$</span> ${esc(cmd)}` }));
    const out = h("div", { class: "term-out running" }, h("span", { class: "spinner" }));
    this.termBody.append(out);
    this.termBody.scrollTop = this.termBody.scrollHeight;
    return out;
  }

  runEnd(outEl, text, ok) {
    outEl.classList.remove("running");
    outEl.classList.toggle("bad", !ok);
    outEl.textContent = text.replace(/\n$/, "") || "(no output)";
    this.termBody.scrollTop = this.termBody.scrollHeight;
  }

  flashTerminal() {
    this.setEnv("code");
    this.term.classList.remove("flash"); void this.term.offsetWidth; this.term.classList.add("flash");
  }

  classLine(text) {
    this.termBody.append(h("div", { class: "term-class" }, `[class] ${text}`));
    this.termBody.scrollTop = this.termBody.scrollHeight;
  }

  reset() {
    this.pages.forEach(p => { p.el.remove(); p.tab.remove(); });
    this.pages = [];
    this._addPage("Lecture");
    this.files = {}; this.current = null;
    this.tabBar.replaceChildren();
    this.codeBody.replaceChildren(h("div", { class: "ed-empty" }, icon("code"), "No code yet"));
    this.termBody.replaceChildren();
    this.slideBox.replaceChildren(h("div", { class: "slide-empty" }, icon("slides"), "No slide shown yet"));
    this.slideNum.textContent = "";
    this.env = null; this.setEnv("notebook");
  }
}

// Wrap the first match of `text` (case-insensitive, spacing ignored) inside `el` with a highlighter mark.
function markText(el, text, block = "nearest") {
  const want = text.trim().toLowerCase();
  if (!want) return false;
  const src = el.textContent;
  const idx = src.toLowerCase().indexOf(want);
  if (idx < 0) return false;
  const mark = h("mark", { class: "hl-mark" }, src.slice(idx, idx + want.length));
  el.replaceChildren(src.slice(0, idx), mark, src.slice(idx + want.length));
  el.scrollIntoView({ block, behavior: "smooth" });
  return true;
}
