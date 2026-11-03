// Studio: upload material, describe the teacher, generate, review/edit and approve the script.

import { api } from "./api.js";
import { h, icon, toast, confirmDialog, sleep, formatDuration, languageSelect, modelTag } from "./ui.js";
import { lectureHeader } from "./header.js";
import { renderScriptDoc, scriptStats } from "./script-view.js";
import { showVersions } from "./versions.js";

const LONG_FIELDS = new Set(["Message to class", "Habits", "Order", "Must cover", "Avoid", "Prep", "Reason"]);
const SECTION_HINTS = {
  "Teacher": "Who the class normally has.",
  "Absence Note": "Read out at the start of class.",
  "Teaching Style": "How the substitute should sound.",
  "Lecture Structure": "What to cover, in what order, and what to skip.",
  "Next Class": "Mentioned at the end.",
};

// opts.regenerate: opened from a lesson preview's Regenerate button: start regenerating right away (it asks first).
export async function mountStudio(lectureId, ctx, opts = {}) {
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
  const header = lectureHeader(lectureId, "studio", status(), data.course,
    data.course ? h("button", { class: "btn sm", title: "Every approved script of this lesson, and which one the class has",
      onclick: () => showVersions(data.course.lesson_id) }, icon("layers"), "Versions") : null);
  const state = { tab: "preview", dirty: false, busy: false, segments: data.segments, errors: data.errors };

  // ---------- left: setup ----------
  const fileList = h("ul", { class: "file-list" });
  const fileInput = h("input", { type: "file", multiple: true, accept: ".pptx,.pdf,.docx,.txt,.md", class: "hidden",
    onchange: (e) => { upload([...e.target.files]); e.target.value = ""; } });
  const drop = h("label", { class: "dropzone" }, fileInput,
    h("div", { class: "dz-icon" }, icon("upload")),
    h("div", {}, h("strong", {}, "Drop files here"), " or ", h("span", { class: "link" }, "browse")),
    h("small", {}, "PPTX, PDF, DOCX, TXT or MD · up to 25 MB each"),
    // Version 1 reads English material only (slides, notes and the textbook); the class may still be taught in another language.
    h("small", { class: "english-note" }, icon("info"), "This version reads English material only: slides, notes and textbooks must be in English."));
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
  const topicInput = h("input", { class: "input", value: data.manifest?.topic || "", placeholder: "e.g. Introduction to recursion" });
  const languageInput = languageSelect(data.manifest?.language || template.language, template.languages);
  const languageName = () => languageInput.selectedOptions[0]?.textContent || "English";
  // The Gnani voice: one of the voices that suit the teaching language (each language lists its own).
  const languageInfo = () => (template.languages || []).find(l => l.code === languageInput.value) || {};
  const voiceInput = h("select", { class: "select" });
  function renderVoices(keep) {
    const info = languageInfo(), voices = info.voices || [];
    const pick = voices.includes(keep) ? keep : info.default_voice || voices[0];
    voiceInput.replaceChildren(...voices.map(v => h("option", { value: v, selected: v === pick }, v)));
  }
  renderVoices(data.manifest?.voice);
  const previewBtn = h("button", { class: "icon-btn voice-play", type: "button", title: "Hear this voice", onclick: () => previewVoice() }, icon("play"));
  const previewAudio = new Audio();
  // ---------- the textbook: the book's PDF, the printed pages the topic spans, and what is taught from it ----------
  let book = data.book;  // {file, size, first, last, found, examples, focus} or null
  const bookInput = h("input", { type: "file", accept: ".pdf", class: "hidden",
    onchange: (e) => { if (e.target.files[0]) uploadBook(e.target.files[0]); e.target.value = ""; } });
  const bookDrop = h("label", { class: "dropzone compact" }, bookInput,
    h("div", { class: "dz-icon" }, icon("book")),
    h("div", {}, h("strong", {}, "Add the textbook"), " or ", h("span", { class: "link" }, "browse")),
    h("small", {}, "The book or chapter as a PDF (e.g. NCERT) · in English · up to 80 MB"));
  const pageInput = (value, label) => h("input", { class: "input", type: "number", min: 1, inputmode: "numeric", value: value ?? "",
    placeholder: label, "aria-label": label, oninput: () => saveSetupSoon() });
  const firstPage = pageInput(book?.first, "e.g. 38"), lastPage = pageInput(book?.last, "e.g. 40");
  const FOCUS = [["slides", "Slides"], ["book", "Book"], ["both", "Both"]];
  const focusPick = (key) => {
    let value = book?.focus?.[key] || "both";
    const el = h("div", { class: "seg", role: "radiogroup" });
    const draw = () => el.replaceChildren(...FOCUS.map(([v, label]) => h("button", { type: "button", role: "radio",
      class: `seg-btn ${v === value ? "on" : ""}`, "aria-checked": String(v === value),
      onclick: () => { value = v; draw(); saveSetupSoon(); } }, label)));
    draw();
    el.pick = () => value;
    return el;
  };
  const focusTheory = focusPick("theory"), focusNumericals = focusPick("numericals");
  const bookInfo = h("div", { class: "book-info stack" });
  const bookFields = h("div", { class: "stack" },
    bookInfo,
    h("div", { class: "grid-2" },
      h("label", { class: "field" }, h("span", {}, "From page (as printed)"), firstPage),
      h("label", { class: "field" }, h("span", {}, "To page"), lastPage)),
    h("div", { class: "field" }, h("span", {}, "Teach the theory from"), focusTheory),
    h("div", { class: "field" }, h("span", {}, "Worked examples & exercises from"), focusNumericals),
    h("small", { class: "muted" }, "Each part's time is set automatically from how much your slides and these pages say ",
      "about it, and from the worked examples. A book example is worked in the notebook beside the page with the book's ",
      "answer covered, then the answer is shown; when it is a number, the script's results must match it."));
  function renderBook() {
    bookDrop.classList.toggle("hidden", !!book);
    bookFields.classList.toggle("hidden", !book);
    if (!book) return bookInfo.replaceChildren();
    const range = book.first && book.last;
    bookInfo.replaceChildren(
      h("ul", { class: "file-list" }, h("li", {},
        h("span", { class: "file-type pdf" }, "PDF"), h("span", { class: "file-name", title: book.file }, book.file),
        h("button", { class: "icon-btn sm", title: "Remove the book", onclick: () => removeBook() }, icon("trash")))),
      // A scan (pictures of pages) has no printed numbers to read, and its text is read by OCR when generating.
      book.scanned ? h("small", { class: "book-warn" }, "This book is scanned: its pages are read by OCR when you generate ",
        "(about half a minute a page), so highlights may sit slightly off. Give the PDF's own page numbers, as your PDF ",
        "viewer counts them.") : null,
      range && (book.found || !book.scanned) ? h("small", { class: book.found ? "muted" : "book-warn" }, book.found
        ? `Pages ${book.first}–${book.last}: ${book.found} page${book.found > 1 ? "s" : ""} found` +
          (book.examples.length ? `. Worked examples: ${book.examples.join(", ")}` : ", no worked examples on them")
        : `Pages ${book.first}–${book.last} are not in this PDF. Use the page numbers printed in the book.`)
        : !range ? h("small", { class: "muted" }, "Enter the pages the topic spans, as numbered in the book.") : null);
  }
  async function uploadBook(file) {
    bookDrop.classList.add("busy");
    try { book = (await api.uploadBook(lectureId, file)).book; renderBook(); toast("Textbook added", "success"); }
    catch (e) { toast(e.message, "error"); }
    bookDrop.classList.remove("busy");
  }
  async function removeBook() {
    try { await api.deleteBook(lectureId); book = null; firstPage.value = lastPage.value = ""; renderBook(); }
    catch (e) { toast(e.message, "error"); }
  }
  renderBook();

  // No lecture or speaking time: the lesson's length comes from how the material treats each part (generate/depth.py).
  const pageNo = (el) => (/^\d+$/.test(el.value.trim()) ? Number(el.value) : null);
  const setupBody = () => ({ persona, topic: topicInput.value.trim(), language: languageInput.value, voice: voiceInput.value,
    ...(book ? { book_first: pageNo(firstPage), book_last: pageNo(lastPage),
      focus_theory: focusTheory.pick(), focus_numericals: focusNumericals.pick() } : {}) });
  async function previewVoice() {
    const sample = languageInfo().sample;
    if (!sample) return;
    previewBtn.replaceChildren(h("span", { class: "spinner" }));
    try {
      clearTimeout(setupTimer);
      await api.saveSetup(lectureId, setupBody());  // the preview speaks with the voice as saved
      const res = await api.tts(lectureId, sample);
      if (!res.ok || res.status === 204) throw new Error("No Gnani voice right now (check GNANI_API_KEY)");
      previewAudio.src = URL.createObjectURL(await res.blob());
      await previewAudio.play();
    } catch (e) { toast(e.message, "error"); }
    previewBtn.replaceChildren(icon("play"));
  }

  // The teacher's fields are saved as they are typed, so they are kept without generating a script.
  let setupTimer = null;
  function saveSetupSoon() {
    clearTimeout(setupTimer);
    setupTimer = setTimeout(() => api.saveSetup(lectureId, setupBody())
      .then(res => { if (book && res.book) { book = res.book; renderBook(); } })
      .catch(e => toast(`Could not save: ${e.message}`, "error")), 700);
  }
  topicInput.addEventListener("input", saveSetupSoon);
  languageInput.addEventListener("change", () => { renderVoices(voiceInput.value); saveSetupSoon(); });
  voiceInput.addEventListener("change", saveSetupSoon);

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
            saveSetupSoon();
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

  // A demo account (its password is public) can look, edit and approve, but not write scripts: the server refuses it.
  const noScripts = ctx.me?.can_generate === false;
  const NO_SCRIPTS = "This is a demo account. Sign in to create your own lectures.";
  const generateBtn = h("button", { class: "btn primary lg block", onclick: generate }, icon("sparkle"), "Generate script");
  const resetBtn = h("button", { class: "btn ghost danger sm", onclick: reset }, icon("reset"), "Reset lecture");

  // Which classroom environments this material unlocks. The notebook and slides are always used; code and
  // diagrams only when the material has them (found when the material is indexed). Graphs show only if turned on.
  const ENV_INFO = [["notebook", "book", "Notebook"], ["slides", "slides", "Slides"], ["code", "code", "Code"],
    ["visual", "sparkle", "Visual"]];
  const envChips = (env) => h("div", { class: "env-chips" }, ENV_INFO.map(([key, ic, base]) => {
    // Visual is on when the material unlocks diagrams, graphs or both; the chip says which.
    const on = key === "visual" ? env.flows || env.graphs : env[key];
    const what = [env.flows && "diagrams", env.graphs && "graphs"].filter(Boolean).join(" + ");
    const label = key === "visual" && what ? `${base}: ${what}` : base;
    return h("span", { class: `env-chip ${on ? "on" : "off"}`, title: on ? `${label}: used in this class`
      : `${label}: not in this class (the material has none)` }, icon(ic), label, on ? icon("check") : null);
  }));
  const env = data.manifest?.environments;
  const envNote = h("div", { class: "env-note" },
    h("div", { class: "env-note-head" }, icon("info"), h("strong", {}, "What the AI teacher can use")),
    h("p", {}, "It always teaches with the notebook and your slides. It writes and runs code only if your material ",
      "contains code. On the Visual board it draws a diagram, block by block, only if your slides or PDF contain a ",
      "diagram or a numbered list of steps (like 1. 2. 3. or A → B → C), and an interactive graph only if your slides ",
      "contain a chart. Add code, step lists or charts to your material so the AI teacher can explain them better."),
    env ? envChips(env) : h("small", { class: "muted" }, "Generate the script to see which environments this material unlocks."));
  // How deep each part is taught comes from the material, so the teacher learns here what earns a part more time.
  const DEPTH_ORDER = ["in depth", "normal", "brief"];
  const depthName = (d) => d === "in depth" ? "In depth" : d[0].toUpperCase() + d.slice(1);
  const depthTag = (d) => h("span", { class: `depth-tag ${d.replace(" ", "-")}` }, depthName(d));
  // The rule the lesson was planned by (depth.py, saved with the plan); these are its values for an older plan.
  const RULE = { brief_below: 2, in_depth_at: 3.5, depth_min: { brief: 0.6, normal: 1.2, "in depth": 2.2 },
    framing_min: { Opening: 0.6, Recap: 0.5, Closing: 0.3 }, max_speaking_min: 30 };
  const mins = (m) => `${(Math.round(m * 10) / 10).toFixed(1)} min`;
  // How the lesson's length was decided: each part's score, its depth and the speaking time that depth gets, then
  // the parts plus the opening, recap and closing.
  const depthList = (depth) => depth?.parts?.length ? h("div", { class: "depth-list" },
    DEPTH_ORDER.map(d => {
      const parts = depth.parts.filter(p => p.depth === d);
      return parts.length ? h("div", { class: "depth-row" }, depthTag(d),
        h("div", { class: "depth-parts" }, parts.map(p => h("span", { class: "depth-part", title: p.why.length ? `Because the material has ${p.why.join(", ")}` : "The material states it without examples or steps" }, p.title)))) : null;
    }),
    h("button", { class: "btn ghost sm", type: "button", onclick: () => setTab("duration") }, icon("clock"), "How the length was decided")) : null;
  const durationBreakdown = (depth) => {
    if (!depth?.parts?.length) return null;
    const rule = { ...RULE, ...(depth.rule || {}) };
    const partMin = (p) => p.minutes ?? rule.depth_min[p.depth];
    const parts = depth.parts.reduce((a, p) => a + partMin(p), 0);
    const framing = Object.values(rule.framing_min).reduce((a, b) => a + b, 0);
    const lesson = data.manifest?.estimated_min;
    const why = (p) => [...p.why, ...(p.must_cover ? ["Must cover"] : [])];
    return h("div", { class: "dur" },
      h("div", { class: "dur-card" },
        h("div", { class: "dur-head" }, h("strong", {}, "How deep each part goes"),
          h("span", {}, "Six yes/no questions about how your material explains each part")),
        h("table", { class: "dur-table" },
          h("thead", {}, h("tr", {}, h("th", {}, "Part and why"), h("th", { class: "num" }, "Score"), h("th", {}, "Depth"),
            h("th", { class: "num" }, "Speaking"))),
          h("tbody", {}, depth.parts.map(p => h("tr", {},
            h("td", {}, h("div", { class: "dur-title" }, p.title),
              h("div", { class: "dur-why" }, (why(p).length ? why(p) : ["stated only"]).map(w =>
                h("span", { class: `dur-chip ${w === "Must cover" ? "must" : ""}` }, w)))),
            h("td", { class: "num" }, p.score != null ? Number(p.score).toFixed(1) : "–"),
            h("td", {}, depthTag(p.depth)),
            h("td", { class: "num" }, mins(partMin(p)))))))),
      h("div", { class: "dur-legend" }, ["brief", "normal", "in depth"].map((d, k) => h("div", { class: `dur-band ${d.replace(" ", "-")}` },
        h("strong", {}, `${depthName(d)} · ${mins(rule.depth_min[d])}`),
        h("small", {}, [`score under ${rule.brief_below.toFixed(1)}`, `${rule.brief_below.toFixed(1)} to ${rule.in_depth_at}`,
          `${rule.in_depth_at} and up`][k])))),
      h("small", { class: "muted" }, "Each yes adds to the score, and so does each slide beyond the first. A Must cover part is ",
        "never Brief, and the lesson's main idea is always In depth."),
      depth.too_long ? h("p", { class: "depth-warn" }, icon("info"), `This material needs more than ${rule.max_speaking_min} min of speaking, so every part was shortened. `,
        "Split it into two lessons to teach it all fully.") : null,
      h("div", { class: "dur-total" },
        h("span", {}, `${depth.parts.length} parts ${mins(parts)} + opening, recap, closing ${mins(framing)}`),
        h("strong", {}, `${mins(depth.speaking_min ?? parts + framing)} speaking${lesson ? ` ≈ ${Math.round(lesson)} min lesson` : ""}`)));
  };
  const depthNote = h("div", { class: "env-note" },
    h("div", { class: "env-note-head" }, icon("layers"), h("strong", {}, "How your slides set the depth")),
    h("p", {}, "Each part of your material is taught ", h("strong", {}, "Brief"), ", ", h("strong", {}, "Normal"), " or ",
      h("strong", {}, "In depth"), ". A part gets more depth when your material gives it more than one slide, an example, ",
      "steps, a comparison, an exception or a task for students."),
    h("p", {}, "For example, a definition in one line is Brief; a process over two slides with a worked case (a reaction, a historical event, an algorithm) is In depth."),
    // The ranges follow DEPTH_MIN and MAX_SPEAKING_MIN in eris/generate/depth.py, with notes and code on top.
    h("p", {}, h("strong", {}, "How this sets the length: "), "an In depth part takes about four times as long as a Brief one. ",
      "Material that is mostly short definitions makes a lesson of about 5–8 min; a mix makes about 10–14 min; ",
      "many worked examples, processes or comparisons make about 18–30 min. Past about 30 min every part is shortened, ",
      "so split such material into two lessons. There is no time to set."),
    depthList(data.manifest?.depth) || h("small", { class: "muted" }, "Generate the script to see how deep each part is taught."));

  const materialStep = h("span", { class: "step-num" }, "1");
  // Once a script exists, the setup folds into this summary so the script gets the room.
  const summaryBody = h("div", { class: "setup-summary-body" });
  const regenBtn = h("button", { class: "btn primary block", onclick: () => generate() }, icon("sparkle"), "Regenerate script");
  const setupSummary = h("section", { class: "card setup-summary" },
    h("div", { class: "card-header" }, icon("layers"), h("h3", {}, "Lecture setup"), h("div", { class: "spacer" }),
      h("button", { class: "btn ghost sm", onclick: () => setFolded(false) }, icon("edit"), "Edit setup")),
    summaryBody, h("div", { class: "setup-summary-foot" }, regenBtn,
      modelTag(data.model, "center")));
  const doneBtn = h("button", { class: "btn ghost sm", onclick: () => setFolded(true) }, icon("chevron"), "Done");
  const setupFull = h("div", { class: "setup-full" },
    h("div", { class: "setup-full-head" }, h("strong", {}, "Lecture setup"), h("div", { class: "spacer" }), doneBtn),
    h("section", { class: "card" },
      h("div", { class: "card-header" }, materialStep, h("h3", {}, "Study material")),
      h("div", { class: "card-body stack" }, drop, fileList, envNote, depthNote)),
    h("section", { class: "card" },
      h("div", { class: "card-header" }, icon("book"), h("h3", {}, "Textbook"), h("div", { class: "spacer" }),
        h("small", { class: "muted" }, "optional")),
      h("div", { class: "card-body stack" }, bookDrop, bookFields)),
    h("section", { class: "card" },
      h("div", { class: "card-header" }, h("span", { class: "step-num" }, "2"), h("h3", {}, "Lecture")),
      h("div", { class: "card-body grid-2" },
        h("label", { class: "field span-2" }, h("span", {}, "Topic"), topicInput),
        h("label", { class: "field" }, h("span", {}, "Teaching language"), languageInput,
          h("small", { class: "muted" }, "The language the class is taught in. Your material stays in English.")),
        h("div", { class: "field" }, h("span", {}, "Voice"), template.gnani
          ? h("div", { class: "voice-row" }, voiceInput, previewBtn)
          : h("div", { class: "pill-note" }, icon("volume"), "Browser voice")))),
    h("section", { class: "card" },
      h("div", { class: "card-header" }, h("span", { class: "step-num" }, "3"), h("h3", {}, "Teacher persona"),
        h("div", { class: "spacer" }),
        h("button", { class: "btn ghost sm", title: "Fill with templates/persona.md", onclick: () => {
          Object.assign(persona, structuredClone(template.values)); renderPersona(); toast("Loaded the example persona");
        } }, "Use example")),
      personaBody),
    h("div", { class: "generate-bar" }, generateBtn,
      h("div", { class: "generate-meta" }, modelTag(data.model), resetBtn)));
  const left = h("div", { class: "studio-left" }, setupSummary, setupFull);

  function renderSummary() {
    const files = data.files.filter(f => f !== "persona.md");
    const row = (ic, text) => h("div", { class: "sum-row" }, icon(ic), h("span", {}, text));
    summaryBody.replaceChildren(...[
      row("file", files.length ? `${files.length} file${files.length > 1 ? "s" : ""}: ${files.join(", ")}` : "No material yet"),
      book ? row("book", `${book.file}${book.first ? `, pages ${book.first}–${book.last}` : ""} · theory from ${book.focus.theory}, worked examples from ${book.focus.numericals}`) : null,
      row("user", persona.Teacher?.Name || "No teacher yet"),
      row("clock", `${topicInput.value || "No topic"}${data.manifest?.estimated_min ? ` · about ${formatDuration(data.manifest.estimated_min)}` : ""} · ${languageName()}${template.gnani ? ` · ${voiceInput.value} voice` : ""}`),
      data.manifest?.environments ? envChips(data.manifest.environments) : null,
      depthList(data.manifest?.depth)].filter(Boolean));
  }

  // Folded: the setup is a summary card (default once a script exists); unfolded: everything to edit.
  let folded = !!data.script_md;
  function setFolded(on) {
    folded = on && !!data.script_md;
    page.classList.toggle("folded", folded);
    doneBtn.classList.toggle("hidden", !data.script_md);
    if (folded) renderSummary();
  }

  // ---------- right: script ----------
  const tabBtn = (key, label, ic) => h("button", { class: "tab", dataset: { tab: key }, onclick: () => setTab(key) }, icon(ic), label);
  const qualityBadge = h("span", { class: "tab-badge" });
  const tabs = h("div", { class: "tabs" }, tabBtn("preview", "Preview", "eye"), tabBtn("quality", "Quality", "checkCircle"),
    tabBtn("duration", "Duration", "clock"), tabBtn("edit", "Edit", "edit"), tabBtn("log", "Progress", "log"));
  tabs.querySelector('[data-tab="quality"]').append(qualityBadge);
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
  const logActions = h("div", { class: "progress-actions" });
  const logPane = h("div", { class: "script-pane log" }, h("div", { class: "progress-card" }, logStatus, logList, logActions));
  const qualityPane = h("div", { class: "script-pane quality" });
  const durationPane = h("div", { class: "script-pane duration" });
  function renderDuration() {
    const table = durationBreakdown(data.manifest?.depth);
    durationPane.replaceChildren(table ? h("div", { class: "duration-wrap" },
      data.manifest?.environments ? h("div", { class: "dur-unlocks" }, h("strong", {}, "Your material unlocks"), envChips(data.manifest.environments)) : null,
      table) : h("div", { class: "empty" }, icon("clock"), "Generate the script to see how its length was decided."));
  }

  const right = h("section", { class: "card studio-right" },
    h("div", { class: "card-header script-head" }, h("h3", {}, "Lecture script"), tabs, h("div", { class: "spacer" }), saveBtn, approveBtn, classBtn),
    statsEl, notices, previewPane, qualityPane, durationPane, editPane, logPane);

  const page = h("div", { class: "page studio" }, left, right);
  main.replaceChildren(header, page);

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
    }
    const q = qualitySummary();
    if (q && state.tab !== "quality") notices.append(h("button", { class: `quality-line ${q.ok ? "ok" : "warn"}`, onclick: () => setTab("quality") },
      icon(q.ok ? "checkCircle" : "alert"), h("span", {}, q.text), icon("chevron")));
  }

  // "All 10 checks passed" / "2 things to look at", for the tab badge and the line above the script.
  function qualitySummary() {
    const j = data.judge;
    if (!j || state.dirty || j.error || !j.findings?.length) return null;
    // A failed blocker must be fixed; a failed minor check is only a suggestion.
    const byCheck = new Map();
    for (const f of j.findings) {
      if (!PLAIN_CHECKS[f.check]) continue;
      const was = byCheck.get(f.check) || "pass";
      const now = f.passed ? "pass" : f.severity === "blocker" ? "fail" : "tip";
      byCheck.set(f.check, was === "fail" || now === "fail" ? "fail" : was === "tip" || now === "tip" ? "tip" : "pass");
    }
    const total = byCheck.size, failed = [...byCheck.values()].filter(v => v === "fail").length;
    const tips = [...byCheck.values()].filter(v => v === "tip").length;
    const tipText = tips ? ` (${tips} suggestion${tips > 1 ? "s" : ""})` : "";
    return { ok: !failed, failed, total,
      text: failed ? `Quality check: ${failed} thing${failed > 1 ? "s" : ""} to fix${tipText}` : `Quality check: passed${tipText}`,
      badge: failed ? `${failed} to fix` : tips ? `${tips} tip${tips > 1 ? "s" : ""}` : `${total}/${total}` };
  }

  function renderQuality() {
    const q = qualitySummary();
    qualityBadge.textContent = q ? q.badge : "";
    qualityBadge.className = `tab-badge ${q ? (q.ok ? "ok" : "warn") : "hidden"}`;
    const card = judgeCard();
    qualityPane.replaceChildren(card ? h("div", { class: "quality-wrap" }, card) : h("div", { class: "empty" },
      h("div", { class: "empty-icon" }, icon("checkCircle")), h("h3", {}, "No quality check yet"),
      h("p", {}, "It runs when the script is generated.")));
  }

  // The quality check from generation (judge.json), in the teacher's words: what was checked, what passed, and
  // where to look when something didn't. Technical details (writer rounds, code repairs) stay in the server terminal.
  const PLAIN_CHECKS = {
    covers_must_cover: ["Teaches everything in your “Must cover” list", "Something from “Must cover” is missing."],
    respects_avoid: ["Stays away from the topics you listed under “Avoid”", "It touches a topic you asked to avoid."],
    opening_absence: ["The opening says why you're away and passes on your message", "The opening misses your reason or your message."],
    closing_next_class: ["The closing mentions the next class and what to prepare", "The closing misses the next class or the preparation."],
    sounds_like_teacher: ["Sounds like you: your tone, pace and habits", "It doesn't sound much like your teaching style yet."],
    notes_match_code: ["Notebook examples match the programs", "A notebook example doesn't match its program."],
    narration_matches_output: ["Program results are explained correctly", "What is said about a program's result is not what it prints."],
    narration_is_speech: ["Everything spoken sounds like natural speech", "Some spoken lines sound like notes or symbols, not speech."],
    graph_matches_text: ["Graphs agree with what is said about them", "What is said about a graph doesn't match the graph."],
    graph_matches_material: ["Graphs match the ones in your slides", "A graph shows something different from your slide's graph."],
    flow_matches_material: ["Diagrams follow the steps in your material", "A diagram's steps differ from your material."],
    has_worked_example: ["Each topic has a worked example with real numbers", "A topic has no worked example yet."],
    pictures_explained: ["Every picture shown is explained correctly", "A picture is shown but not explained, or explained wrongly."],
    explains_clearly: ["Each idea is explained so the class can understand it", "An idea may be hard for the class to follow."],
    highlights_fit: ["Highlights light up what the teacher is talking about", "A highlight lights up something the teacher isn't talking about."],
    stays_true: ["Dates, numbers and names match your material", "A date, number, name or event doesn't match your material."],
  };
  const CHECK_ORDER = Object.keys(PLAIN_CHECKS);
  // While-speaking pairs are checked too (is the sentence about what appears?) but they adjust timing, not quality.

  function judgeCard() {
    const j = data.judge;
    if (!j || state.dirty) return null;
    if (j.error) return h("div", { class: "judge-card" }, h("div", { class: "judge-head" }, icon("info"),
      h("span", {}, "The quality check couldn't run this time. The script was still checked for mistakes; you can review it below.")));
    // One line per check, however many sections it was asked for; a check passes only if it passed everywhere.
    // A failed blocker is something to fix; a failed minor check (style, polish) is shown as a suggestion.
    const byCheck = new Map();
    for (const f of j.findings || []) {
      if (!PLAIN_CHECKS[f.check]) continue;
      const c = byCheck.get(f.check) || { passed: true, tip: false, sections: [] };
      if (!f.passed) {
        if (f.severity === "blocker") c.passed = false; else c.tip = true;
        if (f.section) c.sections.push(f.section);
      }
      byCheck.set(f.check, c);
    }
    const checks = CHECK_ORDER.filter(k => byCheck.has(k)).map(k => ({ key: k, ...byCheck.get(k) }));
    const failed = checks.filter(c => !c.passed);
    const tips = checks.filter(c => c.passed && c.tip).length;
    const summary = (failed.length ? `${checks.length - failed.length} of ${checks.length} checks passed` : `All ${checks.length} checks passed`)
      + (tips ? `, ${tips} suggestion${tips > 1 ? "s" : ""}` : "");
    return h("details", { class: `judge-card ${failed.length ? "bad" : "ok"}`, open: true },
      h("summary", {}, icon(failed.length ? "alert" : "checkCircle"), h("strong", {}, "Quality check"),
        h("span", { class: "judge-meta" }, summary)),
      h("ul", { class: "judge-checks" }, checks.map(c => {
        const tip = c.passed && c.tip;
        return h("li", { class: !c.passed ? "bad" : tip ? "tip" : "ok" },
          icon(!c.passed ? "alert" : tip ? "info" : "check"),
          h("div", {}, h("span", {}, PLAIN_CHECKS[c.key][0]),
            c.passed && !tip ? null : h("small", {}, (tip ? "Suggestion: " : "") + PLAIN_CHECKS[c.key][1]
              + (c.sections.length ? ` Look at: ${[...new Set(c.sections)].join(", ")}.` : ""))));
      })),
      failed.length ? h("p", { class: "judge-hint" }, "Fix these in Edit, or click Generate script again.") : null);
  }

  function renderStats() {
    const s = scriptStats(state.segments);
    const est = data.manifest?.estimated_min;
    const item = (ic, v, l) => h("div", { class: "s-item" }, icon(ic), h("strong", {}, v), h("span", {}, l));
    statsEl.replaceChildren(...[item("layers", s.sections, "sections"), item("clock", est ? formatDuration(est) : `~${formatDuration(s.words / 115)}`, ""),
      item("book", s.notes, "notes"), item("code", s.files, "programs"),
      s.breaks ? item("question", s.breaks, "question breaks") : null,  // only older scripts have them
      modelTag(data.script_model, "s-model")].filter(Boolean));  // replaceChildren would write a null as "null"
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
    previewPane.replaceChildren(renderScriptDoc(state.segments, data.persona?.Teacher?.Name, { lectureId }));
  }

  function renderActions() {
    const running = data.job?.status === "running";
    saveBtn.disabled = !state.dirty || state.busy;
    approveBtn.disabled = state.busy || running || !textarea.value.trim() || status() === "approved" && !state.dirty;
    approveBtn.classList.toggle("hidden", status() === "approved" && !state.dirty || status() === "completed" && !state.dirty);
    classBtn.classList.toggle("hidden", !(["approved", "completed"].includes(status()) && !state.dirty));
    generateBtn.disabled = running || state.busy;
    generateBtn.replaceChildren(...(running ? [h("span", { class: "spinner" }), "Generating…"] : [icon("sparkle"), data.script_md ? "Regenerate script" : "Generate script"]));
    // Both buttons rest while a script is being written: a second click would start a second generation.
    regenBtn.disabled = running || state.busy;
    // greyed out but still clickable for a demo account, so the click can say why (generate() shows the note)
    for (const b of [generateBtn, regenBtn]) { b.classList.toggle("locked", noScripts); b.title = noScripts ? NO_SCRIPTS : ""; }
    regenBtn.replaceChildren(...(running ? [h("span", { class: "spinner" }), "Generating…"] : [icon("sparkle"), "Regenerate script"]));
    resetBtn.disabled = running || state.busy;
    header.setStatus(running ? "running" : status());
  }

  function setTab(key) {
    const job = data.job?.status;
    const generating = job === "running";
    if (generating) key = "log";  // the old script is being replaced: only the progress is shown
    state.tab = key;
    const visible = { preview: !generating, quality: !generating && !!data.judge, duration: !generating && !!data.manifest?.depth?.parts?.length, edit: !generating,
      log: generating || job === "failed" };
    tabs.querySelectorAll(".tab").forEach(b => {
      b.classList.toggle("active", b.dataset.tab === key);
      b.classList.toggle("hidden", !visible[b.dataset.tab]);
    });
    previewPane.classList.toggle("hidden", key !== "preview");
    qualityPane.classList.toggle("hidden", key !== "quality");
    durationPane.classList.toggle("hidden", key !== "duration");
    editPane.classList.toggle("hidden", key !== "edit");
    logPane.classList.toggle("hidden", key !== "log");
    statsEl.classList.toggle("hidden", generating || !state.segments.length);
    notices.classList.toggle("hidden", generating || key === "log");
    right.classList.toggle("generating", key === "log");
    [saveBtn, approveBtn, classBtn].forEach(b => b.classList.toggle("gone", generating));
    if (key === "edit") renderGutter();
    renderNotices();
  }

  // Generation progress in plain steps (the technical log stays in the server's terminal).
  function renderLog() {
    const job = data.job || { status: "idle", steps: [] };
    const label = { running: "Making your script…", done: "Your script is ready", failed: "The script couldn't be finished",
      idle: "Click Generate script to make the lecture script." }[job.status];
    logStatus.replaceChildren(...[job.status === "running" ? h("span", { class: "spinner" }) : icon(job.status === "failed" ? "alert" : job.status === "done" ? "checkCircle" : "info"),
      h("strong", {}, label), job.error ? h("p", { class: "log-error" }, job.error) : null].filter(Boolean));
    logStatus.className = `log-status ${job.status}`;
    // A new mark element per row (one element can only sit in one place).
    const mark = { done: () => icon("check"), now: () => h("span", { class: "spinner" }), failed: () => icon("alert"),
      later: () => h("span", { class: "step-dot" }) };
    logList.replaceChildren(...(job.steps || []).map(st => h("div", { class: `progress-step ${st.state}` }, mark[st.state](), h("span", {}, st.label))));
    if (job.status === "running") logList.append(h("p", { class: "progress-note" }, "You can leave this page and come back."));
    logActions.replaceChildren(...(job.status === "failed" ? [
      h("button", { class: "btn primary sm", onclick: () => generate() }, icon("reset"), "Try again"),
      data.script_md ? h("button", { class: "btn ghost sm", onclick: () => { data.job = { status: "idle" }; setTab("preview"); } }, "Back to the script") : null,
    ] : []).filter(Boolean));
  }

  function renderAll() {
    renderFiles(); renderStats(); renderNotices(); renderPreview(); renderQuality(); renderDuration(); renderGutter(); renderLog(); renderActions();
    setFolded(folded);
  }

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
    const finished = data.job;  // reload() fetches the lecture again; keep how the job ended
    await reload();
    data.job = finished;
    renderLog(); renderActions();
    if (finished.status === "done") {
      toast(state.errors.length ? "Script generated with problems to fix" : "Script ready. Review it, then approve.", state.errors.length ? "error" : "success");
      setFolded(true);
      setTab(state.errors.length ? "edit" : "preview");
    } else if (finished.status === "failed") {
      toast(data.job.error || "The script couldn't be finished. Please try again.", "error");
      setTab("log");
    }
  }

  function collectPersona() {
    const missing = [];
    for (const [section, keys] of Object.entries(template.fields))
      for (const k of keys) if (!String(persona[section]?.[k] || "").trim()) missing.push(`${section} → ${k}`);
    return missing;
  }

  async function generate() {
    if (noScripts) return toast(NO_SCRIPTS, "info");
    if (data.job?.status === "running" || state.busy) return toast("A script is already being generated. Wait for it to finish.", "info");
    if (!data.files.some(f => f !== "persona.md") && !book) return toast("Upload at least one PPTX, PDF or DOCX, or a textbook, first.", "error");
    if (book && !(pageNo(firstPage) && pageNo(lastPage))) return toast("Enter the textbook pages this topic spans.", "error");
    const missing = collectPersona();
    if (missing.length) {
      personaBody.querySelectorAll("details").forEach(d => d.open = true);
      return toast(`Persona is missing: ${missing.slice(0, 3).join(", ")}${missing.length > 3 ? "…" : ""}`, "error", 6000);
    }
    if (!topicInput.value.trim()) return toast("Enter this lecture's topic.", "error");
    if (state.segments.length && !await confirmDialog("Regenerate the script?", "This replaces the current script, including any edits.", "Regenerate")) return;
    try {
      clearTimeout(setupTimer);
      await api.saveSetup(lectureId, setupBody());  // the book's pages and focus are read from the saved setup
      await api.generate(lectureId, { persona, topic: topicInput.value.trim(), language: languageInput.value });
      data.job = { status: "running", steps: [], error: "" };
      data.judge = null;  // the old quality result belongs to the old script
      renderQuality(); renderLog(); renderActions(); setTab("log");
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
      const v = res.lesson_version;
      if (res.ok) toast(v ? (v.shared ? `Approved as version ${v.version}. The class gets it now.` : `Approved as version ${v.version}. Share it from the course.`)
        : "Approved. Ready for class.", "success", 6000);
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
  if (opts.regenerate && !noScripts) {
    history.replaceState(null, "", `#/lecture/${encodeURIComponent(lectureId)}/studio`);  // a reload doesn't ask again
    generate();
  }
  return () => { alive = false; window.onbeforeunload = null; };
}
