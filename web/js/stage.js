// The class stage: the environments the script switches between.
// Notebook (hand-written ruled page), Slides, Code (editor tabs + terminal) and Visual: one board with a tab per
// picture, holding flow diagrams drawn block by block from [FLOW] and interactive graphs from [VISUAL] (each graph
// in its own sandboxed frame).
// Only the environments this class uses get a pill.

import { h, icon, esc } from "./ui.js";
import { highlightLine } from "./highlight.js";
import { FlowBoard } from "./flow.js";

const ENVS = [["notebook", "Notebook", "book"], ["slides", "Slides", "slides"], ["code", "Code", "code"],
  ["visual", "Visual", "sparkle"]];
const PILL_W = 96;
const VISUAL_READY_MS = 10000;  // a visual that hasn't drawn itself by then is reported as failed
const VISUAL_SET_MS = 8000;     // the longest a control change (with its animation) may take
export const NOTE_MS = 26;   // per character, "handwriting"
export const CODE_MS = 14;   // per character, "typing"
// A ctl may carry charMs / lineMs to pace writing to a sentence (while_speaking); otherwise these are used.

export class Stage {
  // used: environment keys this class uses (from its script); null = show all.
  constructor(slides, used = null) {
    this.slides = slides || {};
    this.envs = ENVS.filter(([key]) => !used || key === "notebook" || used.includes(key));
    this.files = {};          // name -> { lines, tab, body }
    this.current = null;
    this.env = null;

    this.indicator = h("div", { class: "env-indicator", role: "status", "aria-label": "Current environment",
      style: `grid-template-columns: repeat(${this.envs.length}, var(--pill-w, ${PILL_W}px))` },
      h("span", { class: "env-glider" }),
      this.envs.map(([key, label, ic]) => h("span", { class: "env-pill", dataset: { env: key } }, icon(ic), label)));

    // Notebook pages: "Lecture" plus one per [NEW_PAGE]. Like the environment pills, the page tabs
    // only show where the teacher is; the script turns the pages.
    this.pageBar = h("div", { class: "nb-pages", "aria-label": "Notebook pages" });
    this.paper = h("div", { class: "nb-paper" });
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

    this.visuals = {};        // id -> { frame, tab, title, state, ready, waiting: Map(req -> resolve) }
    this.currentVisual = null;
    this._req = 0;
    this.visualTitle = h("span", { class: "vz-title" });
    this.visualTabs = h("div", { class: "vz-tabs" });
    this.visualBody = h("div", { class: "vz-body" }, this._visualEmpty());
    this.visualEl = h("div", { class: "env env-visual" },
      h("div", { class: "vz-win" }, h("div", { class: "vz-head" }, icon("sparkle"), this.visualTitle, this.visualTabs), this.visualBody));
    window.addEventListener("message", (e) => this._onVisualMessage(e));

    this.flows = {};          // id -> { board, tab, title }
    this.currentFlow = null;  // diagrams share the Visual board (title, tabs, body) with the graphs

    this.el = h("div", { class: "stage-envs" }, this.notebook, this.slidesEl, this.codeEl, this.visualEl);
    this.setEnv("notebook");
  }

  setEnv(env) {
    if (this.env === env) return;
    this.env = env;
    const i = Math.max(0, this.envs.findIndex(e => e[0] === env));
    this.indicator.style.setProperty("--i", i);
    this.indicator.querySelectorAll(".env-pill").forEach(p => p.classList.toggle("active", p.dataset.env === env));
    for (const [key, el] of [["notebook", this.notebook], ["slides", this.slidesEl], ["code", this.codeEl],
      ["visual", this.visualEl]])
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
      if (ch !== " ") await ctl.tick(ctl.charMs ?? ms);
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
        for (const ch of line) { shown += ch; src.innerHTML = highlightLine(shown); if (ch !== " ") await ctl.tick(ctl.charMs ?? CODE_MS); }
        row.classList.remove("typing");
        await ctl.tick(ctl.lineMs ?? 60);
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

  // ---------- the Visual board: flow diagrams and graphs, one tab each ----------
  _visualEmpty() { return h("div", { class: "vz-empty" }, icon("sparkle"), "Nothing drawn yet"); }

  _boardTabs() {
    this.visualTabs.classList.toggle("hidden", Object.keys(this.flows).length + Object.keys(this.visuals).length < 2);
  }

  _addToBoard(el, tab) {
    this.visualBody.querySelector(".vz-empty")?.remove();
    this.visualBody.append(el);
    this.visualTabs.append(tab);
  }

  // Show one picture on the board (a diagram or a graph) and hide the others.
  _showOnBoard(kind, id) {
    this.currentFlow = kind === "flow" ? id : null;
    this.currentVisual = kind === "graph" ? id : null;
    Object.entries(this.flows).forEach(([k, x]) => {
      x.wrap.classList.toggle("hidden", !(kind === "flow" && k === id));
      x.tab.classList.toggle("active", kind === "flow" && k === id);
    });
    Object.entries(this.visuals).forEach(([k, x]) => {
      x.frame.classList.toggle("off", !(kind === "graph" && k === id));  // still rendered: its animations keep running
      x.tab.classList.toggle("active", kind === "graph" && k === id);
    });
    this.visualTitle.textContent = (kind === "flow" ? this.flows[id] : this.visuals[id]).title;
    this._boardTabs();
  }

  _activateFlow(id) { this._showOnBoard("flow", id); }
  _activateVisual(id) { this._showOnBoard("graph", id); }

  // A new, empty diagram; [FLOW_NEXT] draws its blocks one by one.
  showFlow(id, flow) {
    this.setEnv("visual");
    if (!this.flows[id]) {
      const board = new FlowBoard({ id, ...flow });
      const wrap = h("div", { class: "flow-wrap" }, board.svg);
      const tab = h("span", { class: "vz-tab" }, flow.title);
      this.flows[id] = { board, wrap, tab, title: flow.title };
      this._addToBoard(wrap, tab);
    }
    this._activateFlow(id);
    return true;
  }

  flowNext(id, animate = true) {
    const f = this.flows[id];
    if (!f) return null;
    if (animate) { this.setEnv("visual"); this._activateFlow(id); }
    return f.board.next(animate);
  }

  flowHighlight(id, block) {
    const f = this.flows[id];
    if (!f) return false;
    this.setEnv("visual");
    this._activateFlow(id);
    return f.board.highlight(block);
  }

  openFlow(id) {
    if (!this.flows[id]) return false;
    this.setEnv("visual");
    this._activateFlow(id);
    return true;
  }

  // What each diagram shows now, for the doubt agent.
  flowStates() {
    return Object.entries(this.flows).map(([id, f]) => `${id}: ${f.board.describe()}`).join("\n");
  }

  // Load a built visual into its own sandboxed frame and wait until it has drawn itself.
  // Returns an error string, or "" when it is ready.
  async showVisual(id, url, title) {
    this.setEnv("visual");
    let v = this.visuals[id];
    if (!v) {
      const frame = h("iframe", { class: "vz-frame", title, sandbox: "allow-scripts", referrerpolicy: "no-referrer" });
      const tab = h("span", { class: "vz-tab" }, title);
      v = this.visuals[id] = { frame, tab, title, state: "", errors: [], waiting: new Map() };
      v.ready = new Promise(resolve => { v._ready = resolve; });
      this._addToBoard(frame, tab);
      // Loaded as srcdoc (fetched like any API call): some browsers and embedders block framed page loads.
      // The sandbox (scripts only, opaque origin) and the page's own CSP still apply.
      fetch(url).then(r => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then(html => { frame.srcdoc = html; })
        .catch(e => v.errors.push(`could not load: ${e.message}`));
    }
    this._activateVisual(id);
    v.frame.classList.remove("enter"); void v.frame.offsetWidth; v.frame.classList.add("enter");
    const ok = await Promise.race([v.ready.then(() => true), new Promise(r => setTimeout(() => r(false), VISUAL_READY_MS))]);
    if (!ok) return `visual ${id} did not load${v.errors.length ? `: ${v.errors[0]}` : ""}`;
    return v.errors.length ? `visual ${id} reported an error: ${v.errors[0]}` : "";
  }

  // Move one control of a visual (the frame animates it and points at it). Returns an error string or "".
  async setVisual(id, control, value, { instant = false } = {}) {
    const v = this.visuals[id];
    if (!v) return `visual ${id} is not on the board`;
    if (!instant) { this.setEnv("visual"); this._activateVisual(id); }
    await v.ready;
    const req = ++this._req;
    const done = new Promise(resolve => v.waiting.set(req, resolve));
    v.frame.contentWindow?.postMessage({ __visual: true, type: "set", control, value, req, instant }, "*");
    const reply = await Promise.race([done, new Promise(r => setTimeout(() => r({ error: "it did not respond" }), VISUAL_SET_MS))]);
    v.waiting.delete(req);
    return reply.error ? `visual ${id}, control ${control}: ${reply.error}` : "";
  }

  openVisual(id) {
    if (!this.visuals[id]) return false;
    this.setEnv("visual");
    this._activateVisual(id);
    return true;
  }

  // What each visual shows now, in its own words (Visual.state), for the doubt agent.
  visualStates() {
    return Object.entries(this.visuals).filter(([, v]) => v.state)
      .map(([id, v]) => `${id} (${v.title}): ${v.state}`).join("\n");
  }

  _onVisualMessage(e) {
    const m = e.data;
    if (!m || !m.__visual) return;
    const entry = Object.entries(this.visuals).find(([, v]) => v.frame.contentWindow === e.source);
    if (!entry) return;
    const [id, v] = entry;
    if (typeof m.state === "string" && m.state) v.state = m.state;
    if (m.type === "ready") v._ready();
    else if (m.type === "done") v.waiting.get(m.req)?.(m);
    else if (m.type === "error") { v.errors.push(String(m.message)); console.warn(`[visual ${id}]`, m.message); }
  }

  // Where the class is looking (environment, notebook page, open file, visual), to come back after a doubt.
  view() { return { env: this.env, page: this.page, file: this.current, visual: this.currentVisual, flow: this.currentFlow }; }

  restoreView(v) {
    if (!v) return;
    if (v.visual && this.visuals[v.visual]) this._activateVisual(v.visual);
    if (v.flow && this.flows[v.flow]) this._activateFlow(v.flow);
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
    Object.values(this.flows).forEach(f => { f.wrap.remove(); f.tab.remove(); });
    this.flows = {}; this.currentFlow = null;
    Object.values(this.visuals).forEach(v => { v.frame.remove(); v.tab.remove(); });
    this.visuals = {}; this.currentVisual = null;
    this.visualTitle.textContent = "";
    this.visualBody.replaceChildren(this._visualEmpty());
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
