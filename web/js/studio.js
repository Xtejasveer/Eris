// Studio: upload material, describe the teacher, generate, review/edit and approve the script.

import { api } from "./api.js";
import { h, icon, toast, confirmDialog, sleep } from "./ui.js";
import { lectureHeader } from "./header.js";
import { renderScriptDoc, scriptStats } from "./script-view.js";

const LONG_FIELDS = new Set(["Message to class", "Habits", "Order", "Must cover", "Avoid", "Prep", "Reason"]);
const SECTION_HINTS = {
  "Teacher": "Who the class normally has.",
  "Absence Note": "Read out at the start of class.",
  "Teaching Style": "How the substitute should sound.",
  "Lecture Structure": "What to cover, in what order, and what to skip.",
  "Next Class": "Mentioned at the end.",
};

export async function mountStudio(lectureId, ctx) {
  const { main } = ctx;
  let alive = true;
  let data, template;
  main.replaceChildren(h("div", { class: "page" }, h("div", { class: "empty" }, h("div", { class: "spinner" }), "Loading lecture…")));
  try {
    [data, template] = await Promise.all([api.lecture(lectureId), api.personaTemplate()]);
  } catch (e) {
    main.replaceChildren(h("div", { class: "page" }, h("div", { class: "callout error" }, icon("alert"), e.message)));
    return null;
  }

  const status = () => data.manifest?.status || "new";
  const header = lectureHeader(lectureId, "studio", status());
  const state = { tab: "preview", dirty: false, busy: false, segments: data.segments, errors: data.errors };

  // ---------- left: setup ----------
  const fileList = h("ul", { class: "file-list" });
  const fileInput = h("input", { type: "file", multiple: true, accept: ".pptx,.pdf,.docx,.txt,.md", class: "hidden",
    onchange: (e) => { upload([...e.target.files]); e.target.value = ""; } });
  const drop = h("label", { class: "dropzone" }, fileInput,
    h("div", { class: "dz-icon" }, icon("upload")),
    h("div", {}, h("strong", {}, "Drop files here"), " or ", h("span", { class: "link" }, "browse")),
    h("small", {}, "PPTX, PDF, DOCX, TXT or MD · up to 25 MB each"));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); upload([...e.dataTransfer.files]); });

  function renderFiles() {
    const files = data.files.filter(f => f !== "persona.md");
    fileList.replaceChildren(...files.map(name => h("li", {},
      h("span", { class: `file-type ${name.split(".").pop().toLowerCase()}` }, name.split(".").pop().toUpperCase()),
      h("span", { class: "file-name", title: name }, name),
      h("button", { class: "icon-btn sm", title: `Remove ${name}`, onclick: () => removeFile(name) }, icon("trash")))));
    if (!files.length) fileList.append(h("li", { class: "file-empty" }, "No material uploaded yet."));
    materialStep.classList.toggle("done", files.length > 0);
  }

  async function upload(files) {
    if (!files.length) return;
    drop.classList.add("busy");
    try {
      const res = await api.upload(lectureId, files);
      if (res.saved.length) toast(`Uploaded ${res.saved.length} file(s)`, "success");
      for (const s of res.skipped) toast(`Skipped ${s}`, "error", 5000);
      data.files = (await api.lecture(lectureId)).files;
      renderFiles();
      ctx.refreshLectures();
    } catch (e) { toast(e.message, "error"); }
    drop.classList.remove("busy");
  }

  async function removeFile(name) {
    try {
      await api.deleteFile(lectureId, name);
      data.files = data.files.filter(f => f !== name);
      renderFiles();
    } catch (e) { toast(e.message, "error"); }
  }

  const persona = structuredClone(data.persona || template.values);
  const topicInput = h("input", { class: "input", value: data.manifest?.topic || template.topic || "", placeholder: "e.g. Python while loops" });
  const durationInput = h("input", { class: "input", type: "number", min: 5, max: 120, step: 5, value: data.manifest?.duration_min || template.duration_min || 30 });

  const personaBody = h("div", { class: "persona" });
  function renderPersona() {
    personaBody.replaceChildren(...Object.entries(template.fields).map(([section, keys], i) => {
      persona[section] = persona[section] || {};
      const filled = keys.filter(k => String(persona[section][k] || "").trim()).length;
      const count = h("span", { class: `persona-count ${filled === keys.length ? "ok" : ""}` }, `${filled}/${keys.length}`);
      const fields = keys.map(key => {
        const attrs = { class: LONG_FIELDS.has(key) ? "textarea" : "input", placeholder: key,
          oninput: (e) => {
            persona[section][key] = e.target.value;
            const n = keys.filter(k => String(persona[section][k] || "").trim()).length;
            count.textContent = `${n}/${keys.length}`; count.classList.toggle("ok", n === keys.length);
          } };
        const el = LONG_FIELDS.has(key) ? h("textarea", { ...attrs, rows: 2 }) : h("input", attrs);
        el.value = persona[section][key] || "";
        return h("label", { class: "field" }, h("span", {}, key), el);
      });
      return h("details", { class: "persona-group", open: i === 0 },
        h("summary", {}, h("div", {}, h("strong", {}, section), h("small", {}, SECTION_HINTS[section] || "")), count, icon("chevron", "chev")),
        h("div", { class: "persona-fields" }, fields));
    }));
  }
  renderPersona();

  const generateBtn = h("button", { class: "btn primary lg block", onclick: generate }, icon("sparkle"), "Generate script");
  const resetBtn = h("button", { class: "btn ghost danger sm", onclick: reset }, icon("reset"), "Reset lecture");

  const materialStep = h("span", { class: "step-num" }, "1");
  const left = h("div", { class: "studio-left" },
    h("section", { class: "card" },
      h("div", { class: "card-header" }, materialStep, h("h3", {}, "Study material")),
      h("div", { class: "card-body stack" }, drop, fileList)),
    h("section", { class: "card" },
      h("div", { class: "card-header" }, h("span", { class: "step-num" }, "2"), h("h3", {}, "Lecture")),
      h("div", { class: "card-body grid-2" },
        h("label", { class: "field span-2" }, h("span", {}, "Topic"), topicInput),
        h("label", { class: "field" }, h("span", {}, "Duration (minutes)"), durationInput),
        h("div", { class: "field" }, h("span", {}, "Voice"), h("div", { class: "pill-note" }, icon("volume"), "Set in .env (Gnani or browser)")))),
    h("section", { class: "card" },
      h("div", { class: "card-header" }, h("span", { class: "step-num" }, "3"), h("h3", {}, "Teacher persona"),
        h("div", { class: "spacer" }),
        h("button", { class: "btn ghost sm", title: "Fill with data/example/persona.md", onclick: () => {
          Object.assign(persona, structuredClone(template.values)); renderPersona(); toast("Loaded the example persona");
        } }, "Use example")),
      personaBody),
    h("div", { class: "generate-bar" }, generateBtn,
      h("div", { class: "generate-meta" }, h("small", { class: "muted" }, "Indexes the material, then writes the script. Takes 1–3 minutes."), resetBtn)));

  // ---------- right: script ----------
  const tabBtn = (key, label, ic) => h("button", { class: "tab", dataset: { tab: key }, onclick: () => setTab(key) }, icon(ic), label);
  const tabs = h("div", { class: "tabs" }, tabBtn("preview", "Preview", "eye"), tabBtn("edit", "Edit", "edit"), tabBtn("log", "Log", "log"));
  const saveBtn = h("button", { class: "btn sm", onclick: save, disabled: true }, icon("save"), "Save");
  const approveBtn = h("button", { class: "btn success sm", onclick: approve }, icon("check"), "Approve");
  const classBtn = h("a", { class: "btn primary sm", href: `#/lecture/${encodeURIComponent(lectureId)}/class` }, icon("play"), "Start class");
  const statsEl = h("div", { class: "script-stats" });
  const notices = h("div", { class: "script-notices" });
  const previewPane = h("div", { class: "script-pane preview" });
  const gutter = h("div", { class: "editor-gutter" });
  const textarea = h("textarea", { class: "editor-text", spellcheck: "false", wrap: "off" });
  textarea.value = data.script_md || "";
  textarea.addEventListener("input", () => { state.dirty = true; renderGutter(); renderActions(); });
  textarea.addEventListener("scroll", () => { gutter.scrollTop = textarea.scrollTop; });
  textarea.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); save(); }
    if (e.key === "Tab") { e.preventDefault(); document.execCommand("insertText", false, "    "); }
  });
  const editPane = h("div", { class: "script-pane edit" }, h("div", { class: "editor" }, gutter, textarea));
  const logList = h("div", { class: "log-lines" });
  const logStatus = h("div", { class: "log-status" });
  const logPane = h("div", { class: "script-pane log" }, logStatus, logList);

  const right = h("section", { class: "card studio-right" },
    h("div", { class: "card-header script-head" }, h("h3", {}, "Lecture script"), tabs, h("div", { class: "spacer" }), saveBtn, approveBtn, classBtn),
    statsEl, notices, previewPane, editPane, logPane);

  main.replaceChildren(header, h("div", { class: "page studio" }, left, right));

  function renderGutter() {
    const n = textarea.value.split("\n").length;
    const errLines = new Set(state.errors.map(e => +(/^line (\d+)/.exec(e)?.[1] || 0)));
    gutter.replaceChildren(...Array.from({ length: n }, (_, i) => h("div", { class: errLines.has(i + 1) ? "err" : "" }, i + 1)));
  }

  function jumpToLine(line) {
    setTab("edit");
    const lines = textarea.value.split("\n");
    const start = lines.slice(0, line - 1).reduce((a, l) => a + l.length + 1, 0);
    textarea.focus();
    textarea.setSelectionRange(start, start + (lines[line - 1] || "").length);
    textarea.scrollTop = Math.max(0, (line - 6) * 21);
  }

  function renderNotices() {
    notices.replaceChildren();
    if (data.failed_draft) notices.append(h("div", { class: "callout warn" }, icon("alert"),
      h("div", {}, h("strong", {}, "This is the last failed draft. "), "Generation couldn't produce a valid script. Fix the errors below in Edit and Save, or Generate again.")));
    if (state.errors.length) {
      notices.append(h("div", { class: "callout error errors" }, icon("alert"), h("div", {},
        h("strong", {}, `${state.errors.length} problem(s) to fix before approving`),
        h("ul", {}, state.errors.map(e => {
          const line = +(/^line (\d+)/.exec(e)?.[1] || 0);
          return h("li", {}, line ? h("button", { class: "linkish", onclick: () => jumpToLine(line) }, `Line ${line}`) : null,
            h("span", {}, line ? e.replace(/^line \d+:\s*/, " ") : e));
        })))));
    } else if (status() === "approved") {
      notices.append(h("div", { class: "callout ok" }, icon("checkCircle"), h("div", {}, "Approved. The class is ready to start.")));
    }
  }

  function renderStats() {
    const s = scriptStats(state.segments);
    const est = data.manifest?.estimated_min;
    const item = (ic, v, l) => h("div", { class: "s-item" }, icon(ic), h("strong", {}, v), h("span", {}, l));
    statsEl.replaceChildren(item("layers", s.sections, "sections"), item("clock", est ? `${est}` : `~${Math.round(s.words / 130)}`, "min"),
      item("book", s.notes, "notes"), item("code", s.files, "programs"), item("question", s.breaks, "question breaks"));
    statsEl.classList.toggle("hidden", !state.segments.length);
  }

  function renderPreview() {
    if (!state.segments.length) {
      previewPane.replaceChildren(h("div", { class: "empty" },
        h("div", { class: "empty-icon" }, icon("sparkle")),
        h("h3", {}, data.script_md ? "The script has no valid segments" : "No script yet"),
        h("p", {}, data.script_md ? "Open Edit to fix it." : "Upload the study material, check the persona, then click Generate script. The script appears here as a readable document.")));
      return;
    }
    previewPane.replaceChildren(renderScriptDoc(state.segments, data.persona?.Teacher?.Name));
  }

  function renderActions() {
    const running = data.job?.status === "running";
    saveBtn.disabled = !state.dirty || state.busy;
    approveBtn.disabled = state.busy || running || !textarea.value.trim() || status() === "approved" && !state.dirty;
    approveBtn.classList.toggle("hidden", status() === "approved" && !state.dirty || status() === "completed" && !state.dirty);
    classBtn.classList.toggle("hidden", !(["approved", "completed"].includes(status()) && !state.dirty));
    generateBtn.disabled = running || state.busy;
    generateBtn.replaceChildren(...(running ? [h("span", { class: "spinner" }), "Generating…"] : [icon("sparkle"), data.script_md ? "Regenerate script" : "Generate script"]));
    resetBtn.disabled = running || state.busy;
    header.setStatus(running ? "running" : status());
  }

  function setTab(key) {
    state.tab = key;
    tabs.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === key));
    previewPane.classList.toggle("hidden", key !== "preview");
    editPane.classList.toggle("hidden", key !== "edit");
    logPane.classList.toggle("hidden", key !== "log");
    if (key === "edit") renderGutter();
  }

  function renderLog() {
    const job = data.job || { status: "idle", log: [] };
    logList.replaceChildren(...job.log.map(line => h("div", { class: `log-line ${/^\[tool\]/.test(line) ? "tool" : /error|fail/i.test(line) ? "bad" : ""}` }, line)));
    const label = { running: "Generating…", done: "Finished", failed: "Failed", idle: "No generation in this server run yet" }[job.status];
    logStatus.replaceChildren(job.status === "running" ? h("span", { class: "spinner" }) : icon(job.status === "failed" ? "alert" : job.status === "done" ? "checkCircle" : "info"),
      h("strong", {}, label), job.error ? h("pre", { class: "log-error" }, job.error) : null);
    logStatus.className = `log-status ${job.status}`;
    logList.scrollTop = logList.scrollHeight;
  }

  function renderAll() { renderFiles(); renderStats(); renderNotices(); renderPreview(); renderGutter(); renderLog(); renderActions(); }

  async function reload() {
    data = await api.lecture(lectureId);
    state.segments = data.segments; state.errors = data.errors; state.dirty = false;
    textarea.value = data.script_md || "";
    ctx.setLectureStatus(lectureId, status());
    renderAll();
  }

  async function poll() {
    while (alive) {
      try { data.job = await api.job(lectureId); } catch { /* keep polling */ }
      renderLog(); renderActions();
      if (data.job.status !== "running") break;
      await sleep(1200);
    }
    if (!alive) return;
    await reload();
    if (data.job.status === "done") {
      toast(state.errors.length ? "Script generated with problems to fix" : "Script ready. Review it, then approve.", state.errors.length ? "error" : "success");
      setTab(state.errors.length ? "edit" : "preview");
    } else if (data.job.status === "failed") toast("Generation failed. See the log.", "error");
  }

  function collectPersona() {
    const missing = [];
    for (const [section, keys] of Object.entries(template.fields))
      for (const k of keys) if (!String(persona[section]?.[k] || "").trim()) missing.push(`${section} → ${k}`);
    return missing;
  }

  async function generate() {
    if (!data.files.some(f => f !== "persona.md")) return toast("Upload at least one PPTX, PDF or DOCX first.", "error");
    const missing = collectPersona();
    if (missing.length) {
      personaBody.querySelectorAll("details").forEach(d => d.open = true);
      return toast(`Persona is missing: ${missing.slice(0, 3).join(", ")}${missing.length > 3 ? "…" : ""}`, "error", 6000);
    }
    const duration = +durationInput.value;
    if (!(duration >= 5 && duration <= 120)) return toast("Duration must be 5 to 120 minutes.", "error");
    if (state.segments.length && !await confirmDialog("Regenerate the script?", "This replaces the current script, including any edits.", "Regenerate")) return;
    try {
      await api.generate(lectureId, { persona, topic: topicInput.value.trim(), duration_min: duration });
      data.job = { status: "running", log: [], error: "" };
      setTab("log"); renderLog(); renderActions();
      ctx.refreshLectures();
      poll();
    } catch (e) { toast(e.message, "error", 6000); }
  }

  async function save() {
    if (!state.dirty || state.busy) return true;
    state.busy = true; renderActions();
    try {
      const res = await api.saveScript(lectureId, textarea.value);
      state.segments = res.segments; state.errors = res.errors; state.dirty = false;
      data.manifest = { ...(data.manifest || {}), status: res.status };
      data.failed_draft = false; data.script_md = textarea.value;
      ctx.setLectureStatus(lectureId, res.status);
      toast(res.errors.length ? `Saved with ${res.errors.length} problem(s)` : "Saved", res.errors.length ? "error" : "success");
      return true;
    } catch (e) { toast(e.message, "error"); return false; }
    finally { state.busy = false; renderAll(); }
  }

  async function approve() {
    if (data.failed_draft) state.dirty = true;  // approve reads script.md, so the shown draft must be saved first
    if (state.dirty && !await save()) return;
    state.busy = true;
    approveBtn.replaceChildren(h("span", { class: "spinner" }), "Approving…");
    renderActions();
    try {
      const res = await api.approve(lectureId);
      if (res.ok) toast("Approved. Ready for class.", "success");
      else toast(`Approval failed: ${res.errors.length} problem(s)`, "error");
      await reload();
      if (!res.ok) { state.errors = res.errors; renderNotices(); renderGutter(); }
    } catch (e) { toast(e.message, "error"); }
    state.busy = false;
    approveBtn.replaceChildren(icon("check"), "Approve");
    renderActions();
  }

  async function reset() {
    if (!await confirmDialog("Reset this lecture?",
      "This clears the knowledge base and every generated file (script, audio, logs). The uploaded material and persona are kept.", "Reset lecture", "danger")) return;
    try { await api.reset(lectureId); toast("Lecture reset"); await reload(); setTab("preview"); }
    catch (e) { toast(e.message, "error"); }
  }

  renderAll();
  setTab(data.job?.status === "running" ? "log" : data.failed_draft ? "edit" : "preview");
  if (data.job?.status === "running") poll();
  window.onbeforeunload = () => (state.dirty ? true : undefined);
  return () => { alive = false; window.onbeforeunload = null; };
}
