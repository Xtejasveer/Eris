// Runs INSIDE a visual's sandboxed iframe (served inline by /lectures/<id>/visuals/<key>; not a module).
// It gives the generated code a small API, draws the control panel, and lets the class page drive
// the controls by message, so the teacher can move a slider or press a button while explaining.
//
// The generated code uses:
//   Visual.on(name, fn)       fn(value) runs when a control changes (button: no value). May be async.
//   Visual.state(text)        one sentence saying what is shown now; the teacher reads it in doubts.
//   Visual.svg(tag, attrs, parent)   make an SVG element.   Visual.tween(ms, t => ...)   animate t 0..1.
//   Visual.value(name)        a control's current value.   Visual.stage   the #stage element.
//
// Messages: page -> frame {__visual, type:"set", control, value, req};
//           frame -> page {__visual, type: "ready"|"state"|"done"|"user"|"error", ...}.
(function () {
  "use strict";
  const CONTROLS = window.__VISUAL_CONTROLS__ || [];
  const SVG_NS = "http://www.w3.org/2000/svg";
  const handlers = {}, values = {}, widgets = {};
  let stateText = "", queue = Promise.resolve(), instant = false;
  // requestAnimationFrame pauses in frames the browser doesn't paint; a timer keeps animations finishing.
  const next = (fn) => {
    let done = false;
    const run = () => { if (!done) { done = true; fn(); } };
    requestAnimationFrame(run);
    setTimeout(run, 50);
  };

  const post = (msg) => { try { parent.postMessage({ __visual: true, ...msg }, "*"); } catch { /* no parent */ } };
  const report = (e) => post({ type: "error", message: String(e && (e.message || e)).slice(0, 300) });
  window.addEventListener("error", (e) => report(e.error || e.message));
  window.addEventListener("unhandledrejection", (e) => report(e.reason));

  const Visual = {
    get stage() { return document.getElementById("stage"); },
    on(name, fn) { (handlers[name] = handlers[name] || []).push(fn); },
    value(name) { return values[name]; },
    state(text) { stateText = String(text == null ? "" : text).slice(0, 400); post({ type: "state", state: stateText }); },
    svg(tag, attrs = {}, parent = null) {
      const el = document.createElementNS(SVG_NS, tag);
      for (const [k, v] of Object.entries(attrs)) {
        if (k === "text") el.textContent = v; else el.setAttribute(k, v);
      }
      if (parent) parent.appendChild(el);
      return el;
    },
    tween(ms, fn) {
      if (instant) { try { fn(1); } catch (e) { report(e); } return Promise.resolve(); }
      return new Promise((resolve) => {
        const start = performance.now();
        const frame = () => {
          const t = Math.min(1, (performance.now() - start) / Math.max(1, ms));
          try { fn(t < 1 ? 0.5 - Math.cos(Math.PI * t) / 2 : 1); } catch (e) { report(e); resolve(); return; }
          if (t < 1) next(frame); else resolve();
        };
        next(frame);
      });
    },
    sleep(ms) { return new Promise((r) => setTimeout(r, instant ? 0 : ms)); },
  };
  window.Visual = Visual;

  async function fire(name, value) {
    if (value !== undefined) values[name] = value;
    for (const fn of handlers[name] || []) {
      try { await fn(value); } catch (e) { report(e); }
    }
    if (Visual._needsRedraw) {  // the graph helper grew an axis mid-draw: draw once more at the new scale
      Visual._needsRedraw = false;
      for (const fn of handlers[name] || []) {
        try { await fn(value); } catch (e) { report(e); }
      }
    }
  }

  // Run changes one at a time, so a quick second click never interleaves with an animation.
  const serial = (job) => (queue = queue.then(job, job));

  const fmt = (c, v) => (c.type === "slider" ? String(+(+v).toFixed(4)) : String(v));

  function syncWidget(c) {
    const w = widgets[c.name], v = values[c.name];
    if (c.type === "slider") { w.input.value = v; w.out.textContent = fmt(c, v); }
    if (c.type === "toggle") { w.btn.setAttribute("aria-pressed", String(!!v)); w.btn.textContent = v ? "On" : "Off"; }
    if (c.type === "choice") w.opts.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === v)));
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function buildPanel() {
    const panel = document.getElementById("visual-controls");
    if (!CONTROLS.length) { panel.remove(); return; }
    for (const c of CONTROLS) {
      const box = el("div", "vc vc-" + c.type);
      box.dataset.control = c.name;
      const w = widgets[c.name] = { box };
      if (c.type === "button") {
        w.btn = el("button", "vc-btn", c.label);
        w.btn.onclick = () => user(c, undefined);
        box.append(w.btn);
      } else {
        box.append(el("span", "vc-label", c.label));
        if (c.type === "slider") {
          w.input = el("input");
          Object.assign(w.input, { type: "range", min: c.min, max: c.max, step: c.step });
          w.out = el("output", "vc-out");
          w.input.oninput = () => user(c, +w.input.value);
          box.append(w.input, w.out);
        } else if (c.type === "toggle") {
          w.btn = el("button", "vc-toggle");
          w.btn.onclick = () => user(c, !values[c.name]);
          box.append(w.btn);
        } else {
          const group = el("div", "vc-seg");
          w.opts = c.options.map((o) => {
            const b = el("button", "vc-opt", o);
            b.dataset.v = o;
            b.onclick = () => user(c, o);
            return b;
          });
          group.append(...w.opts);
          box.append(group);
        }
      }
      panel.append(box);
    }
  }

  function user(c, value) {
    if (c.type !== "button" && values[c.name] === value) return;
    if (c.type !== "button") { values[c.name] = value; syncWidget(c); }
    serial(async () => {
      await fire(c.name, value);
      post({ type: "user", control: c.name, value: values[c.name], state: stateText });
    });
  }

  // The teacher drives a control: point at it, move it visibly, then report what is shown.
  async function drive(c, value, now) {
    const w = widgets[c.name];
    if (now) {  // rebuilding the screen after a jump: no pointing, no animation
      if (c.type !== "button") { values[c.name] = value; syncWidget(c); }
      instant = true;
      try { await fire(c.name, c.type === "button" ? undefined : value); } finally { instant = false; }
      return;
    }
    w.box.classList.remove("vc-driven"); void w.box.offsetWidth; w.box.classList.add("vc-driven");
    clearTimeout(w.glow);  // animations pause in a frame nobody sees; never leave the highlight stuck on
    w.glow = setTimeout(() => w.box.classList.remove("vc-driven"), 1500);
    if (c.type === "button") {
      w.btn.classList.add("vc-press");
      await Visual.sleep(180);
      w.btn.classList.remove("vc-press");
      await fire(c.name);
      return;
    }
    if (c.type === "slider") {
      const from = +values[c.name], to = +value;
      const steps = Math.min(24, Math.max(1, Math.round(Math.abs(to - from) / c.step)));
      for (let i = 1; i <= steps; i++) {
        let v = i === steps ? to : from + ((to - from) * i) / steps;
        v = Math.round(v / c.step) * c.step;
        values[c.name] = +v.toFixed(6);
        syncWidget(c);
        await fire(c.name, values[c.name]);
        await Visual.sleep(steps > 1 ? Math.round(900 / steps) : 0);  // about a second for the whole drag
      }
      return;
    }
    values[c.name] = value;
    syncWidget(c);
    await fire(c.name, value);
  }

  window.addEventListener("message", (e) => {
    const m = e.data;
    if (!m || !m.__visual || m.type !== "set") return;
    const c = CONTROLS.find((x) => x.name === m.control);
    if (!c) { post({ type: "done", req: m.req, error: `no control '${m.control}'`, state: stateText }); return; }
    serial(async () => {
      await drive(c, m.value, !!m.instant);
      post({ type: "done", req: m.req, state: stateText });
    });
  });

  Visual._start = async function () {
    buildPanel();
    for (const c of CONTROLS) {
      if (c.type === "slider") values[c.name] = c.min;
      if (c.type === "toggle") values[c.name] = false;
      if (c.type === "choice") values[c.name] = c.options[0];
      if (c.type !== "button") syncWidget(c);
    }
    // Draw from the first values, then tell the page the visual is ready.
    for (const c of CONTROLS) if (c.type !== "button") await fire(c.name, values[c.name]);
    const missing = CONTROLS.filter((c) => !handlers[c.name]).map((c) => c.name);
    if (missing.length) report(`no Visual.on handler for: ${missing.join(", ")}`);
    post({ type: "ready", state: stateText, values });
  };
})();
