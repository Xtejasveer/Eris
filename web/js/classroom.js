// Classroom: a full-screen lesson canvas. The teacher writes on an open dotted board (slides, code and graphs
// appear on it as cards); a floating bar at the bottom holds the teacher, playback, the live caption, the pen,
// the question box and the mic. Students can ask at any time: a question typed mid-lesson is answered right
// after the current sentence.

import { api } from "./api.js";
import { h, icon, toast, initials, formatDuration } from "./ui.js";
import { Stage } from "./stage.js";
import { Voice, createDictation } from "./voice.js";
import { Player, Stopped, ClassClock } from "./player.js";

const cursorKey = (id) => `eris-cursor-${id}`;
const store = {
  get(id) { try { return +(localStorage.getItem(cursorKey(id)) || 0); } catch { return 0; } },
  set(id, v) { try { localStorage.setItem(cursorKey(id), String(v)); } catch {} },
};
const pref = {
  get(k, d) { try { return localStorage.getItem(`eris-${k}`) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(`eris-${k}`, String(v)); } catch {} },
};

export async function mountClassroom(lectureId, ctx) {
  const { main } = ctx;
  const studio = `#/lecture/${encodeURIComponent(lectureId)}/studio`;
  main.replaceChildren(h("div", { class: "page" }, h("div", { class: "empty" }, h("div", { class: "spinner" }), "Opening the classroom…")));
  let info;
  try { info = await api.classData(lectureId); }
  catch (e) {
    main.replaceChildren(h("div", { class: "page" }, h("div", { class: "callout error" }, icon("alert"), e.message)));
    return null;
  }
  if (!info.ready) {
    main.replaceChildren(h("div", { class: "page" },
      h("div", { class: "card empty not-ready" }, h("div", { class: "empty-icon" }, icon("class")),
        h("h3", {}, "This class isn't ready yet"), h("p", {}, info.message),
        h("a", { class: "btn primary", href: studio }, icon("edit"), "Open Studio"))));
    return null;
  }

  const segments = info.segments;
  const sections = segments.map((s, i) => ({ s, i })).filter(x => x.s.name === "SECTION").map(x => ({ title: x.s.args.title, index: x.i }));
  const voice = new Voice(lectureId, info.language);
  const ENV_OF = { SLIDE: "slides", SLIDE_HIGHLIGHT: "slides", SLIDE_CIRCLE: "slides", WRITE_CODE: "code", RUN: "code", OPEN_FILE: "code",
    FLOW: "visual", VISUAL: "visual" };
  const used = [...new Set(info.segments.map(s => ENV_OF[s.name]).filter(Boolean))];
  if (Object.keys(info.slides || {}).length) used.push("slides");  // doubt answers may always show slides
  const stage = new Stage(info.slides, used, info.slide_pictures);
  stage.setTopic(info.topic);
  let player = null;
  let running = false;

  // ---------- top: where we are, and the lesson controls ----------
  const sectionText = h("span", { class: "ls-section" }, info.topic);
  const stateText = h("span", { class: "ls-state" }, "Ready");
  const topLeft = h("div", { class: "ls-top-left" },
    h("a", { class: "ls-back", href: studio, title: "Back to Studio" }, icon("back")),
    h("div", { class: "ls-where" }, h("strong", {}, info.topic), h("small", {}, stateText, " · ", sectionText)),
    used.length ? stage.indicator : null);

  const clock = new ClassClock(info.duration_min);
  const mmss = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  const clockText = h("span", {}, `0:00 / ${mmss(clock.totalMs)}`);
  const clockChip = h("span", { class: "ls-clock", title: "Lecture time used / total lecture time" }, icon("clock"), clockText);

  // The teacher and the playback controls, together at the top right.
  const avatarView = h("div", { class: "ls-avatar-3d hidden" });
  const orb = h("span", { class: "ls-orb" }, initials(info.teacher.replace(/^(prof|dr|mr|mrs|ms)\.?\s+/i, "")));
  const avatarBtn = h("button", { class: "ls-avatar", title: info.avatar?.enabled ? `${info.teacher} · click to show or hide the 3D teacher` : info.teacher,
    onclick: () => info.avatar?.enabled && toggleAvatar() }, orb, avatarView, h("span", { class: "ls-ring" }));
  let captionsOn = pref.get("captions", "1") !== "0";
  const captionBtn = h("button", { class: "ls-ctl", title: "Show or hide captions", onclick: () => {
    captionsOn = !captionsOn; pref.set("captions", captionsOn ? 1 : 0); renderCaptions();
  } }, icon("captions"));
  const playBtn = h("button", { class: "ls-ctl ls-play", title: "Start (space)", onclick: () => togglePlay() }, icon("play"));
  const muteBtn = h("button", { class: "ls-ctl", title: "Mute", onclick: () => { voice.setMuted(!voice.muted); renderMute(); } }, icon("volume"));
  const penBtn = h("button", { class: "ls-ctl ls-pen", title: "Draw on the board", onclick: () => togglePen() }, icon("pen"));
  const clearInkBtn = h("button", { class: "ls-mini hidden", title: "Clear your drawing", onclick: () => stage.clearInk() }, "Clear");
  const topRight = h("div", { class: "ls-top-right" },
    h("div", { class: "ls-controls" }, avatarBtn, h("span", { class: "ls-sep" }), playBtn, muteBtn, captionBtn, penBtn, clearInkBtn),
    clockChip,
    h("button", { class: "ls-end", title: "End the lesson", onclick: () => endLesson() }, h("span", { class: "ls-end-dot" }), "End"));
  const followBtn = h("button", { class: "ls-follow hidden", onclick: () => stage.followNow() }, icon("focus"), "Follow tutor");
  stage.onFollowChange = (on) => followBtn.classList.toggle("hidden", on || !running);

  // ---------- the board ----------
  const overlay = h("div", { class: "stage-overlay" });
  const board = h("div", { class: "ls-board" }, stage.el, overlay);

  // ---------- bottom: the live caption, and asking a doubt ----------
  const captionText = h("p", { class: "ls-caption-text" });
  const caption = h("div", { class: "ls-caption" }, captionText);

  const askInput = h("textarea", { class: "ls-input", rows: 1, placeholder: "Ask a doubt…" });
  const sendBtn = h("button", { class: "ls-send hidden", title: "Send (Enter)" }, icon("arrowRight"));
  const plusMenu = h("div", { class: "ls-menu hidden" });
  const plusBtn = h("button", { class: "ls-plus", title: "More", onclick: (e) => { e.stopPropagation(); openMenu(); } }, icon("plus"));
  const micBtn = h("button", { class: "ls-mic", title: "Speak your doubt" }, icon("mic"));
  const askBox = h("div", { class: "ls-ask" }, plusBtn, askInput, sendBtn, micBtn, plusMenu);

  const waitBar = h("i");
  const waitText = h("span");
  const waitTimer = h("div", { class: "wait-timer hidden", role: "timer", "aria-live": "polite" }, h("div", { class: "wait-bar" }, waitBar), waitText);
  const liveThread = h("div", { class: "ls-live-thread" });
  const liveCard = h("div", { class: "ls-live hidden" },
    h("div", { class: "ls-live-head" }, icon("question"), h("strong", { class: "ls-live-title" }, "Questions"),
      h("button", { class: "ls-mini", title: "Hide", onclick: () => liveCard.classList.add("hidden") }, "Hide")),
    liveThread, waitTimer);

  const bar = h("div", { class: "ls-bar" }, caption, h("div", { class: "ls-ask-wrap" }, liveCard, askBox));

  // ---------- drawer: outline and every question so far ----------
  const outline = h("ol", { class: "outline" }, sections.map((sec, n) => h("li", { dataset: { index: sec.index } },
    h("button", { onclick: () => jump(sec.index), title: `Jump to ${sec.title}` }, h("span", { class: "o-num" }, n + 1), h("span", { class: "o-title" }, sec.title)))));
  const history = h("div", { class: "chat" }, h("div", { class: "chat-empty" }, icon("chat"), h("p", {}, "Questions and answers show up here.")));
  const drawer = h("aside", { class: "ls-drawer" },
    h("div", { class: "ls-drawer-head" }, h("strong", {}, "Lesson"), h("button", { class: "icon-btn sm", title: "Close", onclick: () => toggleDrawer(false) }, icon("plus", "x"))),
    h("div", { class: "ls-drawer-label" }, "Outline"), outline,
    h("div", { class: "ls-drawer-label" }, "Questions"), history);
  const handle = h("button", { class: "ls-handle", title: "Outline and questions", onclick: () => toggleDrawer() });
  const toggleDrawer = (on) => lesson.classList.toggle("drawer-open", on);

  const lesson = h("div", { class: "lesson" }, board, topLeft, topRight, followBtn, bar, handle, drawer);
  main.replaceChildren(lesson);

  const clockTimer = setInterval(() => {
    if (!clockChip.isConnected) return clearInterval(clockTimer);
    clockText.textContent = `${mmss(clock.elapsed())} / ${mmss(clock.totalMs)}`;
    clockChip.classList.toggle("warn", clock.left() <= clock.totalMs * 0.10);
  }, 1000);

  // ---------- overlays ----------
  function showOverlay(content) { overlay.replaceChildren(content || ""); overlay.classList.toggle("hidden", !content); }
  function splash() {
    const saved = store.get(lectureId);
    const savedSec = saved > 0 && saved < segments.length ? [...sections].reverse().find(s => s.index <= saved) : null;
    const item = (ic, label, value) => h("div", { class: "sp-item" }, icon(ic), h("span", {}, label), h("strong", {}, value));
    showOverlay(h("div", { class: "splash" },
      h("div", { class: "splash-badge" }, icon("class")),
      h("h2", {}, info.topic), h("p", { class: "muted" }, `Taught by the AI substitute for ${info.teacher}`),
      h("div", { class: "sp-grid" }, item("clock", "Length", formatDuration(info.estimated_min)), item("layers", "Sections", sections.length),
        item("question", "Question breaks", segments.filter(s => s.name === "DOUBT_CHECK").length), item("volume", "Voice", info.voice ? "Gnani" : "Browser")),
      h("div", { class: "splash-actions" },
        h("button", { class: "btn primary lg", onclick: () => start(0) }, icon("play"), "Start class"),
        savedSec ? h("button", { class: "btn lg", onclick: () => start(savedSec.index) }, `Resume at “${savedSec.title}”`) : null)));
  }
  splash();

  // ---------- player UI ----------
  let pendingAsk = null;
  let live = null;  // the question break (or raised question) on screen now
  const ui = {
    onCaption(text) { setCaption(text); },
    onSection(title) {
      sectionText.textContent = title;
      const cur = [...sections].reverse().find(s => s.title === title && s.index <= (player?.cursor ?? 0)) || sections.find(s => s.title === title);
      outline.querySelectorAll("li").forEach(li => {
        const idx = +li.dataset.index;
        li.classList.toggle("current", cur && idx === cur.index);
        li.classList.toggle("done", cur && idx < cur.index);
      });
    },
    onProgress(i, n) { store.set(lectureId, i >= n ? 0 : i); },
    cancelAsk() { if (pendingAsk) { const r = pendingAsk; pendingAsk = null; r(""); } stopWait(); },
    openCheckpoint(section, final) {
      history.querySelector(".chat-empty")?.remove();
      const raised = raisedPending;  // this break was opened for a question asked mid-lesson
      raisedPending = false;
      const thread = h("div", { class: "ck-thread" });
      const typing = h("div", { class: "msg teacher typing hidden" }, h("span"), h("span"), h("span"));
      const block = h("div", { class: "checkpoint" },
        h("div", { class: "ck-head" }, icon("question"), h("strong", {}, final ? "Final questions" : raised ? "Your question" : "Question break"), h("small", {}, section)),
        thread, typing);
      liveThread.replaceChildren(block);
      liveCard.querySelector(".ls-live-title").textContent = final ? "Final questions" : raised ? "Your question" : "Question break";
      liveCard.classList.remove("hidden");
      live = block;
      const scroll = () => { liveThread.scrollTop = liveThread.scrollHeight; };
      setState("Question break");
      const add = (cls, text, extra) => { thread.append(h("div", { class: `msg ${cls}` }, h("div", { class: "bubble" }, text), extra)); scroll(); };
      return {
        thinking(on) { typing.classList.toggle("hidden", !on); setState(on ? "Thinking…" : "Question break"); avatar?.setMood(on ? "thinking" : "happy"); scroll(); },
        setLimit() {},
        setCount() {},
        teacher(text, opts = {}) { add(`teacher ${opts.prompt ? "prompt" : ""}`, text, opts.passed ? h("span", { class: "msg-tag" }, `Passed to ${info.teacher}`) : null); },
        student(text) { add("student", text); },
        note(text) { add("system", text); },
        ask(seconds) {
          avatar?.setMood("happy");
          setState("Listening for questions");
          askInput.placeholder = "Ask your doubt, or say “no”…";
          askBox.classList.add("active");
          askInput.focus();
          startWait(seconds);
          return new Promise(resolve => {
            pendingAsk = (v) => { stopWait(); askBox.classList.remove("active"); askInput.placeholder = "Ask a doubt…"; setState("Question break"); resolve(v); };
          });
        },
        close() {
          avatar?.setMood("neutral");
          typing.classList.add("hidden");
          askBox.classList.remove("active");
          history.append(block);  // into the drawer's history; the live card fades out
          if (live === block) { live = null; setTimeout(() => { if (!live) liveCard.classList.add("hidden"); }, 400); }
          setState(running ? "Teaching" : "Ready");
        },
      };
    },
  };

  // ---------- live caption: each word lights up as it is spoken ----------
  let capWords = [], capSeq = 0, capShown = -1, capLive = false;
  function setCaption(text, live = true) {
    capWords = text.replace(/`/g, "").split(/\s+/).filter(Boolean).map(w => h("span", { class: "w" }, `${w} `));
    captionText.replaceChildren(...capWords);
    capSeq = voice.seq + 1;  // the line the voice starts next
    capShown = -1;
    capLive = live;
    if (!live) capWords.forEach(w => w.classList.add("said"));
    captionText.scrollTop = 0;
  }
  function updateCaption() {
    if (!capLive || !capWords.length) return;
    const p = voice.progress();
    const n = Math.round((p.seq >= capSeq ? p.frac : 0) * capWords.length);
    if (n === capShown) return;
    capShown = n;
    capWords.forEach((w, i) => w.classList.toggle("said", i < n));
    const cur = capWords[Math.max(0, n - 1)];  // keep the word being said on the last visible line
    captionText.scrollTop = Math.max(0, cur.offsetTop + cur.offsetHeight - captionText.clientHeight);
  }
  setCaption("Press play when the class is ready.", false);

  // ---------- asking ----------
  let raisedPending = false;
  let waitTimerId = 0, waitLeft = 0, waitTotal = 0;
  function startWait(seconds) {
    stopWait();
    if (!seconds) return;
    waitLeft = waitTotal = seconds;
    waitTimer.classList.remove("hidden", "holding");
    renderWait();
    waitTimerId = setInterval(() => {
      if (player?.paused) return;
      waitLeft -= 0.1;
      renderWait();
      if (waitLeft <= 0) { stopWait(); submit(""); }
    }, 100);
  }
  function renderWait() {
    waitBar.style.width = `${Math.max(0, (100 * waitLeft) / waitTotal)}%`;
    waitText.textContent = player?.paused ? "Paused" : `Moving on in ${Math.ceil(Math.max(0, waitLeft))}s · start typing to ask`;
  }
  function holdWait() {
    if (!waitTimerId) return;
    clearInterval(waitTimerId); waitTimerId = 0;
    waitTimer.classList.add("holding");
    waitBar.style.width = "100%";
    waitText.textContent = "Take your time. Press Enter to ask.";
  }
  function stopWait() { clearInterval(waitTimerId); waitTimerId = 0; waitTimer.classList.add("hidden"); }

  function submit(text) {
    text = text.trim();
    askInput.value = ""; autosize(); renderSend();
    if (pendingAsk) { const r = pendingAsk; pendingAsk = null; r(text); return; }
    if (!text) return;
    if (!running || !player) { toast("Start the class first, then ask.", "info"); return; }
    // Mid-lesson: the teacher answers right after the current sentence.
    player.raiseHand(text);
    raisedPending = true;
    liveThread.replaceChildren(h("div", { class: "msg student raised" }, h("div", { class: "bubble" }, text)),
      h("div", { class: "msg system" }, h("div", { class: "bubble" }, `${info.teacher.split(" ")[0] || "The teacher"} will answer right after this sentence.`)));
    liveCard.querySelector(".ls-live-title").textContent = "Your question";
    liveCard.classList.remove("hidden");
    if (player.paused) { player.resume(); renderPlay(); }
  }
  const autosize = () => { askInput.style.height = "auto"; askInput.style.height = `${Math.min(askInput.scrollHeight, 120)}px`; };
  const renderSend = () => { sendBtn.classList.toggle("hidden", !askInput.value.trim()); };
  askInput.addEventListener("input", () => { autosize(); renderSend(); if (askInput.value.trim()) holdWait(); });
  askInput.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (askInput.value.trim()) submit(askInput.value); } });
  sendBtn.addEventListener("click", () => askInput.value.trim() && submit(askInput.value));

  function openMenu() {
    const item = (label, ic, fn, disabled) => h("button", { class: "ls-menu-item", disabled, onclick: () => { closeMenu(); fn(); } }, icon(ic), label);
    plusMenu.replaceChildren(
      item("No questions, continue", "skip", () => submit(""), !pendingAsk),
      item("Outline and questions", "layers", () => toggleDrawer(true)),
      item(captionsOn ? "Hide captions" : "Show captions", "captions", () => captionBtn.click()));
    plusMenu.classList.remove("hidden");
    setTimeout(() => document.addEventListener("click", closeMenu, { once: true }));
  }
  function closeMenu() { plusMenu.classList.add("hidden"); }

  // The mic: dictation fills the box and sends it when the student stops talking.
  let listening = false;
  const dictation = createDictation(info.language, (text) => { askInput.value = text; autosize(); renderSend(); }, () => {
    listening = false; renderMic();
    if (askInput.value.trim()) submit(askInput.value);
  });
  if (!dictation) micBtn.title = "Speaking needs Chrome or Safari: type your question instead";
  micBtn.addEventListener("click", () => {
    if (!dictation) return toast("Speaking needs Chrome or Safari. Type your question instead.", "info");
    if (listening) { dictation.stop(); return; }
    listening = true; renderMic(); holdWait(); askInput.value = ""; dictation.start();
  });
  function renderMic() {
    micBtn.classList.toggle("on", listening);
    micBtn.title = listening ? "Listening… click to stop" : "Speak your doubt";
  }

  // ---------- controls ----------
  function setState(text) { stateText.textContent = text; }
  function renderCaptions() { caption.classList.toggle("off", !captionsOn); captionBtn.classList.toggle("active", captionsOn); }
  function renderMute() { muteBtn.replaceChildren(icon(voice.muted ? "volumeOff" : "volume")); muteBtn.title = voice.muted ? "Unmute" : "Mute"; }
  function renderPlay() {
    const playing = running && !player?.paused;
    playBtn.replaceChildren(icon(playing ? "pause" : "play"));
    playBtn.title = !running ? "Start (space)" : playing ? "Pause (space)" : "Resume (space)";
    lesson.classList.toggle("paused", running && !!player?.paused);
    if (running) setState(player.paused ? "Paused" : stateText.textContent === "Paused" || stateText.textContent === "Ready" ? "Teaching" : stateText.textContent);
  }
  function togglePen() {
    const on = !stage.penActive;
    if (on && stage.env !== "notebook") stage.setEnv("notebook");
    stage.setPen(on);
    penBtn.classList.toggle("on", on);
    clearInkBtn.classList.toggle("hidden", !on);
    penBtn.title = on ? "Stop drawing" : "Draw on the board";
  }
  function togglePlay() {
    if (!running) return start(0);
    if (player.paused) player.resume(); else player.pause();
    renderPlay();
  }
  renderCaptions(); renderMute(); renderPlay();

  async function start(from) {
    voice.unlock();
    if (player) player.stop();
    const p = new Player({ lectureId, segments, teacher: info.teacher, stage, voice, ui, clock });
    player = p;
    showOverlay(null);
    running = true;
    setState("Teaching");
    renderPlay();
    try {
      await p.play(from);
      if (player !== p) return;
      running = false; renderPlay();
      await finish(p, "Class complete.");
    } catch (e) {
      if (player !== p) return;  // replaced by a jump
      running = false; renderPlay();
      if (e instanceof Stopped) { if (!p.ended) stoppedOverlay(p); }
      else { console.error(e); toast(`The class stopped: ${e.message}`, "error"); stoppedOverlay(p); }
    } finally { followBtn.classList.add("hidden"); }
  }

  function jump(index) {
    if (running && player && !confirm("Jump to this section? The current step stops.")) return;
    toggleDrawer(false);
    start(index);
  }

  async function endLesson() {
    if (!running) { location.hash = studio; return; }
    if (!confirm("End the lesson now?")) return;
    const p = player;
    p.ended = true;  // its Stopped error must not show the "Class stopped" card
    p.stop();
    await finish(p, "Lesson ended.");
  }

  function stoppedOverlay(p) {
    setState("Stopped");
    const sec = [...sections].reverse().find(s => s.index <= p.cursor);
    showOverlay(h("div", { class: "splash compact" },
      h("div", { class: "splash-badge muted-badge" }, icon("pause")), h("h2", {}, "Class stopped"),
      h("p", { class: "muted" }, sec ? `Stopped in “${sec.title}”.` : "Stopped."),
      h("div", { class: "splash-actions" },
        h("button", { class: "btn primary", onclick: () => start(p.cursor) }, icon("play"), "Continue from here"),
        h("button", { class: "btn", onclick: () => start(0) }, icon("reset"), "Restart"))));
  }

  async function finish(p, title) {
    running = false; renderPlay();
    setState(title.replace(/\.$/, ""));
    setCaption(title, false);
    const complete = p.cursor >= segments.length;
    if (complete) {
      store.set(lectureId, 0);
      try { await api.complete(lectureId); ctx.setLectureStatus(lectureId, "completed"); } catch {}
    }
    const s = p.state;
    const item = (label, value) => h("div", { class: "sum-item" }, h("strong", {}, value), h("span", {}, label));
    showOverlay(h("div", { class: "splash" },
      h("div", { class: `splash-badge ${complete ? "ok" : "muted-badge"}` }, icon(complete ? "checkCircle" : "stop")), h("h2", {}, title),
      h("p", { class: "muted" }, `${info.topic} · taught for ${info.teacher}`),
      h("div", { class: "sum-grid" }, item("sections covered", s.covered.length), item("doubts asked", s.doubtsAsked),
        item(`passed to ${info.teacher}`, s.passed), item("failed actions", s.failed)),
      h("div", { class: "splash-actions" },
        complete ? null : h("button", { class: "btn primary", onclick: () => start(p.cursor) }, icon("play"), "Continue"),
        h("button", { class: `btn ${complete ? "primary" : ""}`, onclick: () => start(0) }, icon("reset"), "Run again"),
        h("a", { class: "btn", href: studio }, "Back to Studio"))));
  }

  // ---------- live visual: the teacher's ring moves with the voice ----------
  let raf = 0, smooth = 0;
  const loop = () => {
    smooth = smooth * 0.7 + voice.level() * 0.3;
    avatarBtn.style.setProperty("--level", smooth.toFixed(3));
    avatarBtn.classList.toggle("speaking", smooth > 0.04);
    updateCaption();
    raf = requestAnimationFrame(loop);
  };
  loop();

  const onKey = (e) => {
    if (e.code !== "Space" || !running || /INPUT|TEXTAREA|BUTTON|SELECT/.test(document.activeElement?.tagName)) return;
    e.preventDefault(); togglePlay();
  };
  document.addEventListener("keydown", onKey);

  // ---------- talking avatar (optional): the 3D teacher in the round portrait ----------
  let avatar = null, avatarLoading = false;
  const AVATAR_PREF = "eris-avatar";
  const avatarWanted = () => { try { return localStorage.getItem(AVATAR_PREF) !== "0"; } catch { return true; } };
  const webgl = () => { try { return !!document.createElement("canvas").getContext("webgl2"); } catch { return false; } };

  async function enableAvatar() {
    if (avatar || avatarLoading || !info.avatar?.enabled || !webgl()) return;
    avatarLoading = true;
    avatarView.classList.remove("hidden");
    avatarBtn.classList.add("with-3d");
    try {
      const { createAvatar } = await import("./avatar/avatar.js");  // three.js loads only when the avatar is used
      const created = await createAvatar({ container: avatarView, modelUrl: info.avatar.model_url || undefined });
      if (!avatarLoading) { created.dispose(); return; }
      avatar = created;
      window.erisAvatar = avatar;
      voice.setAvatar(avatar);
    } catch (e) {
      console.warn("[avatar] could not load, audio only:", e);
      disableAvatar();
    } finally { avatarLoading = false; }
  }
  function disableAvatar() {
    avatarLoading = false;
    voice.setAvatar(null);
    avatar?.dispose();
    avatar = null;
    window.erisAvatar = undefined;
    avatarView.replaceChildren();
    avatarView.classList.add("hidden");
    avatarBtn.classList.remove("with-3d");
  }
  function toggleAvatar() {
    const on = !(avatar || avatarLoading);
    try { localStorage.setItem(AVATAR_PREF, on ? "1" : "0"); } catch {}
    on ? enableAvatar() : disableAvatar();
  }
  if (avatarWanted()) enableAvatar();

  return () => {
    disableAvatar();
    cancelAnimationFrame(raf);
    clearInterval(clockTimer);
    document.removeEventListener("keydown", onKey);
    if (player) player.stop();
    player = null;
    voice.dispose();
  };
}
