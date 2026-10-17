// Classroom: teacher panel, stage and question breaks around the browser player.

import { api } from "./api.js";
import { h, icon, toast, initials } from "./ui.js";
import { lectureHeader } from "./header.js";
import { inlineCode } from "./script-view.js";
import { Stage } from "./stage.js";
import { Voice, createDictation } from "./voice.js";
import { Player, Stopped } from "./player.js";

const cursorKey = (id) => `eris-cursor-${id}`;
const store = {
  get(id) { try { return +(localStorage.getItem(cursorKey(id)) || 0); } catch { return 0; } },
  set(id, v) { try { localStorage.setItem(cursorKey(id), String(v)); } catch {} },
};

export async function mountClassroom(lectureId, ctx) {
  const { main } = ctx;
  main.replaceChildren(h("div", { class: "page" }, h("div", { class: "empty" }, h("div", { class: "spinner" }), "Opening the classroom…")));
  let info;
  try { info = await api.classData(lectureId); }
  catch (e) {
    main.replaceChildren(lectureHeader(lectureId, "class", "new"), h("div", { class: "page" }, h("div", { class: "callout error" }, icon("alert"), e.message)));
    return null;
  }
  if (!info.ready) {
    main.replaceChildren(lectureHeader(lectureId, "class", info.status), h("div", { class: "page" },
      h("div", { class: "card empty not-ready" }, h("div", { class: "empty-icon" }, icon("class")),
        h("h3", {}, "This class isn't ready yet"), h("p", {}, info.message),
        h("a", { class: "btn primary", href: `#/lecture/${encodeURIComponent(lectureId)}/studio` }, icon("edit"), "Open Studio"))));
    return null;
  }

  // The ready answer has no status; the lecture list does (approved or completed).
  info.status = (await api.lectures().catch(() => [])).find(l => l.id === lectureId)?.status || "approved";
  const segments = info.segments;
  const sections = segments.map((s, i) => ({ s, i })).filter(x => x.s.name === "SECTION").map(x => ({ title: x.s.args.title, index: x.i }));
  const voice = new Voice(lectureId);
  const stage = new Stage(info.slides);
  let player = null;
  let running = false;

  // ---------- left panel ----------
  const stateLabel = h("span", { class: "t-state" }, "Ready");
  const bars = h("div", { class: "vbars" }, Array.from({ length: 5 }, () => h("i")));
  const teacherCard = h("div", { class: "teacher-card" },
    h("div", { class: "orb" }, h("span", { class: "orb-ring r1" }), h("span", { class: "orb-ring r2" }), h("span", { class: "orb-core" }, initials(info.teacher.replace(/^(prof|dr|mr|mrs|ms)\.?\s+/i, "")))),
    h("div", { class: "t-meta" }, h("strong", {}, info.teacher), h("small", {}, "AI substitute teacher"), h("div", { class: "t-live" }, bars, stateLabel)));
  const caption = h("p", { class: "caption-text" }, "Press Start class when the students are ready.");
  const sectionLabel = h("span", { class: "caption-section" }, info.topic);
  const progressFill = h("i");
  const progressText = h("span", {}, `0 / ${segments.length}`);
  const playBtn = h("button", { class: "btn primary", onclick: () => togglePlay() }, icon("play"), "Start class");
  const stopBtn = h("button", { class: "btn", onclick: () => stop(), disabled: true, title: "Stop the class" }, icon("stop"), "Stop");

  const outline = h("ol", { class: "outline" }, sections.map((sec, n) => h("li", { dataset: { index: sec.index } },
    h("button", { onclick: () => jump(sec.index), title: `Jump to ${sec.title}` }, h("span", { class: "o-num" }, n + 1), h("span", { class: "o-title" }, sec.title)))));
  const chat = h("div", { class: "chat" }, h("div", { class: "chat-empty" }, icon("chat"), h("p", {}, "Students can ask doubts at each question break. The conversation shows up here.")));
  const qCount = h("span", { class: "seg-count hidden" });
  const segBtn = (key, label, extra) => h("button", { class: "seg", dataset: { key }, onclick: () => setPanel(key) }, label, extra);
  const segs = h("div", { class: "segmented" }, segBtn("outline", "Outline"), segBtn("questions", "Questions", qCount));

  const composerInput = h("textarea", { class: "composer-input", rows: 1, placeholder: "Type a student's question…", disabled: true });
  const sendBtn = h("button", { class: "icon-btn send", title: "Ask", disabled: true }, icon("send"));
  const micBtn = h("button", { class: "icon-btn", title: "Dictate", disabled: true }, icon("mic"));
  const noDoubtBtn = h("button", { class: "btn sm", disabled: true }, "No questions, continue");
  const limitLabel = h("small", { class: "muted" });
  const composer = h("div", { class: "composer" }, h("div", { class: "composer-box" }, composerInput, micBtn, sendBtn),
    h("div", { class: "composer-foot" }, limitLabel, noDoubtBtn));

  const side = h("aside", { class: "class-side" },
    teacherCard,
    h("div", { class: "caption-card" }, sectionLabel, caption),
    h("div", { class: "controls" }, playBtn, stopBtn,
      h("div", { class: "progress-wrap" }, h("div", { class: "progress-bar" }, progressFill), progressText)),
    h("div", { class: "side-panel" }, segs, h("div", { class: "panel-body" }, outline, chat), composer));

  // ---------- stage ----------
  const stageSection = h("span", { class: "stage-section" }, info.topic);
  const overlay = h("div", { class: "stage-overlay" });
  const stageCard = h("section", { class: "stage-card" },
    h("div", { class: "stage-head" }, stage.indicator, h("div", { class: "spacer" }), stageSection),
    h("div", { class: "stage-body" }, stage.el, overlay));

  const voiceChip = h("span", { class: "chip" }, icon("volume"), info.voice ? "Gnani voice" : "Browser voice");
  const header = lectureHeader(lectureId, "class", info.status,
    h("span", { class: "chip" }, icon("clock"), `${info.estimated_min ?? "?"} min`), voiceChip);
  main.replaceChildren(header, h("div", { class: "classroom" }, side, stageCard));

  // ---------- panel + overlay ----------
  function setPanel(key) {
    segs.querySelectorAll(".seg").forEach(b => b.classList.toggle("active", b.dataset.key === key));
    outline.classList.toggle("hidden", key !== "outline");
    chat.classList.toggle("hidden", key !== "questions");
    composer.classList.toggle("hidden", key !== "questions");
  }
  setPanel("outline");

  function showOverlay(content) { overlay.replaceChildren(content); overlay.classList.toggle("hidden", !content); }
  function splash() {
    const saved = store.get(lectureId);
    const savedSec = saved > 0 && saved < segments.length ? [...sections].reverse().find(s => s.index <= saved) : null;
    const item = (ic, label, value) => h("div", { class: "sp-item" }, icon(ic), h("span", {}, label), h("strong", {}, value));
    showOverlay(h("div", { class: "splash" },
      h("div", { class: "splash-badge" }, icon("class")),
      h("h2", {}, info.topic), h("p", { class: "muted" }, `Taught by the AI substitute for ${info.teacher}`),
      h("div", { class: "sp-grid" }, item("clock", "Length", `${info.estimated_min ?? "?"} min`), item("layers", "Sections", sections.length),
        item("question", "Question breaks", segments.filter(s => s.name === "DOUBT_CHECK").length), item("volume", "Voice", info.voice ? "Gnani" : "Browser")),
      h("div", { class: "splash-actions" },
        h("button", { class: "btn primary lg", onclick: () => start(0) }, icon("play"), "Start class"),
        savedSec ? h("button", { class: "btn lg", onclick: () => start(savedSec.index) }, `Resume at “${savedSec.title}”`) : null)));
  }
  splash();

  // ---------- player UI callbacks ----------
  let pendingAsk = null;
  let questionCount = 0;
  const ui = {
    onCaption(text) { caption.replaceChildren(...inlineCode(text)); caption.classList.remove("in"); void caption.offsetWidth; caption.classList.add("in"); },
    onSection(title) {
      sectionLabel.textContent = title; stageSection.textContent = title;
      const cur = [...sections].reverse().find(s => s.title === title && s.index <= (player?.cursor ?? 0)) || sections.find(s => s.title === title);
      outline.querySelectorAll("li").forEach(li => {
        const idx = +li.dataset.index;
        li.classList.toggle("current", cur && idx === cur.index);
        li.classList.toggle("done", cur && idx < cur.index);
      });
    },
    onProgress(i, n) {
      progressFill.style.width = `${(100 * i) / n}%`;
      progressText.textContent = `${Math.min(i + 1, n)} / ${n}`;
      store.set(lectureId, i >= n ? 0 : i);
    },
    cancelAsk() { if (pendingAsk) { const r = pendingAsk; pendingAsk = null; r(""); } },
    openCheckpoint(section, final) {
      setPanel("questions");
      chat.querySelector(".chat-empty")?.remove();
      const status = h("span", { class: "ck-status live" }, "Live");
      const thread = h("div", { class: "ck-thread" });
      const typing = h("div", { class: "msg teacher typing hidden" }, h("span"), h("span"), h("span"));
      const block = h("div", { class: "checkpoint" },
        h("div", { class: "ck-head" }, icon("question"), h("strong", {}, final ? "Final questions" : "Question break"), h("small", {}, section), status),
        thread, typing);
      chat.append(block);
      const scroll = () => { chat.scrollTop = chat.scrollHeight; };
      scroll();
      stateLabel.textContent = "Question break";
      const add = (cls, text, extra) => { thread.append(h("div", { class: `msg ${cls}` }, h("div", { class: "bubble" }, text), extra)); scroll(); };
      return {
        thinking(on) { typing.classList.toggle("hidden", !on); stateLabel.textContent = on ? "Thinking…" : "Question break"; scroll(); },
        setLimit(max) { limitLabel.textContent = `Up to ${max} question(s) in this break`; },
        setCount(asked, max) { limitLabel.textContent = `${asked} of ${max} question(s) asked`; },
        teacher(text, opts = {}) {
          add(`teacher ${opts.prompt ? "prompt" : ""}`, text, opts.passed ? h("span", { class: "msg-tag" }, `Passed to ${info.teacher}`) : null);
        },
        student(text) { add("student", text); questionCount += 1; qCount.textContent = questionCount; qCount.classList.remove("hidden"); },
        note(text) { add("system", text); },
        ask() {
          setComposer(true);
          stateLabel.textContent = "Listening for questions";
          return new Promise(resolve => { pendingAsk = (v) => { setComposer(false); stateLabel.textContent = "Question break"; resolve(v); }; });
        },
        close() { status.textContent = "Done"; status.className = "ck-status done"; setComposer(false); limitLabel.textContent = ""; typing.classList.add("hidden"); },
      };
    },
  };

  function setComposer(on) {
    for (const el of [composerInput, sendBtn, micBtn, noDoubtBtn]) el.disabled = !on;
    if (!dictation) micBtn.disabled = true;
    composer.classList.toggle("active", on);
    if (on) composerInput.focus();
  }
  function submit(text) {
    if (!pendingAsk) return;
    const r = pendingAsk; pendingAsk = null;
    composerInput.value = ""; autosize();
    r(text.trim());
  }
  const autosize = () => { composerInput.style.height = "auto"; composerInput.style.height = `${Math.min(composerInput.scrollHeight, 120)}px`; };
  composerInput.addEventListener("input", autosize);
  composerInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (composerInput.value.trim()) submit(composerInput.value); }
  });
  sendBtn.addEventListener("click", () => composerInput.value.trim() && submit(composerInput.value));
  noDoubtBtn.addEventListener("click", () => submit(""));
  let listening = false;
  const dictation = createDictation((text) => { composerInput.value = text; autosize(); },
    () => { listening = false; micBtn.classList.remove("rec"); });
  if (!dictation) micBtn.title = "Dictation needs Chrome or Safari";
  micBtn.addEventListener("click", () => {
    if (!dictation) return;
    if (listening) { dictation.stop(); return; }
    listening = true; micBtn.classList.add("rec"); dictation.start();
  });

  // ---------- controls ----------
  function setRunning(on) {
    running = on;
    stopBtn.disabled = !on;
    renderPlayBtn();
  }
  function renderPlayBtn() {
    if (!running) playBtn.replaceChildren(icon("play"), "Start class");
    else if (player.paused) playBtn.replaceChildren(icon("play"), "Resume");
    else playBtn.replaceChildren(icon("pause"), "Pause");
    stateLabel.textContent = !running ? stateLabel.textContent : player.paused ? "Paused" : stateLabel.textContent === "Paused" ? "Teaching" : stateLabel.textContent;
    teacherCard.classList.toggle("paused", !!player?.paused);
  }
  function togglePlay() {
    if (!running) return start(0);
    if (player.paused) player.resume(); else player.pause();
    renderPlayBtn();
  }

  async function start(from) {
    voice.unlock();
    if (player) player.stop();
    const p = new Player({ lectureId, segments, teacher: info.teacher, stage, voice, ui });
    player = p;
    showOverlay(null);
    setRunning(true);
    stateLabel.textContent = "Teaching";
    try {
      await p.play(from);
      if (player !== p) return;
      setRunning(false);
      await finish(p);
    } catch (e) {
      if (player !== p) return;  // replaced by a jump
      setRunning(false);
      if (e instanceof Stopped) stoppedOverlay(p);
      else { console.error(e); toast(`The class stopped: ${e.message}`, "error"); stoppedOverlay(p); }
    }
  }

  function stop() { if (player && running) player.stop(); }

  function jump(index) {
    if (running && player && !confirm("Jump to this section? The current step stops.")) return;
    start(index);
  }

  function stoppedOverlay(p) {
    stateLabel.textContent = "Stopped";
    const sec = [...sections].reverse().find(s => s.index <= p.cursor);
    showOverlay(h("div", { class: "splash compact" },
      h("div", { class: "splash-badge muted-badge" }, icon("pause")), h("h2", {}, "Class stopped"),
      h("p", { class: "muted" }, sec ? `Stopped in “${sec.title}”.` : "Stopped."),
      h("div", { class: "splash-actions" },
        h("button", { class: "btn primary", onclick: () => start(p.cursor) }, icon("play"), "Continue from here"),
        h("button", { class: "btn", onclick: () => start(0) }, icon("reset"), "Restart"))));
  }

  async function finish(p) {
    stateLabel.textContent = "Class complete";
    caption.textContent = "Class complete.";
    store.set(lectureId, 0);
    try { await api.complete(lectureId); header.setStatus("completed"); ctx.setLectureStatus(lectureId, "completed"); } catch {}
    const s = p.state;
    const item = (label, value) => h("div", { class: "sum-item" }, h("strong", {}, value), h("span", {}, label));
    showOverlay(h("div", { class: "splash" },
      h("div", { class: "splash-badge ok" }, icon("checkCircle")), h("h2", {}, "Class complete."),
      h("p", { class: "muted" }, `${info.topic} · taught for ${info.teacher}`),
      h("div", { class: "sum-grid" }, item("sections covered", s.covered.length), item("doubts asked", s.doubtsAsked),
        item(`passed to ${info.teacher}`, s.passed), item("failed actions", s.failed)),
      h("div", { class: "splash-actions" },
        h("button", { class: "btn primary", onclick: () => start(0) }, icon("reset"), "Run again"),
        h("a", { class: "btn", href: `#/lecture/${encodeURIComponent(lectureId)}/studio` }, "Back to Studio"))));
  }

  // ---------- live visual ----------
  let raf = 0;
  const barEls = [...bars.children];
  let smooth = 0;
  const loop = () => {
    const lvl = voice.level();
    smooth = smooth * 0.7 + lvl * 0.3;
    teacherCard.style.setProperty("--level", smooth.toFixed(3));
    teacherCard.classList.toggle("speaking", smooth > 0.04);
    barEls.forEach((b, i) => { b.style.transform = `scaleY(${0.15 + smooth * (0.5 + 0.5 * Math.abs(Math.sin(performance.now() / (140 + i * 37) + i)))})`; });
    if (voice.mode !== "unknown") voiceChip.lastChild.textContent = voice.mode === "gnani" ? "Gnani voice" : "Browser voice";
    raf = requestAnimationFrame(loop);
  };
  loop();

  const onKey = (e) => {
    if (e.code !== "Space" || !running || /INPUT|TEXTAREA|BUTTON/.test(document.activeElement?.tagName)) return;
    e.preventDefault(); togglePlay();
  };
  document.addEventListener("keydown", onKey);

  return () => {
    cancelAnimationFrame(raf);
    document.removeEventListener("keydown", onKey);
    if (player) player.stop();
    player = null;
    voice.dispose();
  };
}
