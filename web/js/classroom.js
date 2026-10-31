// Classroom: a full-screen lesson canvas. The teacher writes on an open dotted board (slides, code and graphs
// appear on it as cards); a floating bar at the bottom holds the teacher, playback, the live caption, the pen,
// the question box and the mic. Students can ask at any time: a question typed mid-lesson is answered right
// after the current sentence.
//
// A shared lesson (opts.postId) plays the locked version the teacher shared. For a student it is their own session:
// it resumes where they left off, programs show their approved output, and every spoken line they hear (with the
// tab in view) is reported, so the teacher sees attendance: present once every line has been heard.

import { api } from "./api.js";
import { h, icon, toast, modal, initials, formatDuration, modelTag, kindTag, lectureHref, lectureLabel } from "./ui.js";
import { Stage } from "./stage.js";
import { Voice, createDictation } from "./voice.js";
import { Player, Stopped, ClassClock, isNoDoubt } from "./player.js";
import { renderScriptDoc } from "./script-view.js";
import { checkpoints } from "./checkpoints.js";

const cursorKey = (id) => `eris-cursor-${id}`;
const store = {
  get(id) { try { return +(localStorage.getItem(cursorKey(id)) || 0); } catch { return 0; } },
  set(id, v) { try { localStorage.setItem(cursorKey(id), String(v)); } catch {} },
};
const pref = {
  get(k, d) { try { return localStorage.getItem(`eris-${k}`) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(`eris-${k}`, String(v)); } catch {} },
};

export async function mountClassroom(lectureId, ctx, opts = {}) {
  const { main } = ctx;
  const postId = opts.postId || null;
  main.replaceChildren(h("div", { class: "page" }, h("div", { class: "empty" }, h("div", { class: "spinner" }), "Opening the classroom…")));
  let info;
  try {
    info = postId ? await api.postClass(postId) : await api.classData(lectureId);
    if (postId) lectureId = info.lecture_id;
  }
  catch (e) {
    main.replaceChildren(h("div", { class: "page" }, h("div", { class: "callout error" }, icon("alert"), e.message)));
    return null;
  }
  const student = info.role === "student";
  const lessonKind = info.post?.kind || info.kind || null;  // a shared lesson: "lecture" or "prerequisite"
  // Where "back" goes: the course for a shared lesson, the lecture workspace otherwise.
  const studio = postId ? `#/course/${info.course.id}` : lectureHref(lectureId);
  const backLabel = postId ? "Back to course" : "Edit lecture";
  const lessonMeta = postId ? { post_id: postId, version_id: info.version_id } : {};
  if (!info.ready) {
    main.replaceChildren(h("div", { class: "page" },
      h("div", { class: "card empty not-ready" }, h("div", { class: "empty-icon" }, icon("class")),
        h("h3", {}, "This class isn't ready yet"), h("p", {}, info.message),
        h("a", { class: "btn primary", href: postId ? studio : lectureHref(lectureId) }, icon("edit"), postId ? "Back to course" : lectureLabel(info.status)))));
    return null;
  }

  const segments = info.segments;
  const sections = segments.map((s, i) => ({ s, i })).filter(x => x.s.name === "SECTION").map(x => ({ title: x.s.args.title, index: x.i }));
  const voice = new Voice(lectureId, info.language);
  const ENV_OF = { SLIDE: "slides", SLIDE_HIGHLIGHT: "slides", SLIDE_CIRCLE: "slides", WRITE_CODE: "code", RUN: "code", OPEN_FILE: "code",
    FLOW: "visual", VISUAL: "visual" };
  const used = [...new Set(info.segments.map(s => ENV_OF[s.name]).filter(Boolean))];
  if (Object.keys(info.slides || {}).length) used.push("slides");  // doubt answers may always show slides
  const stage = new Stage(info.slides, used, info.slide_pictures, info.slide_images);
  stage.setTopic(info.topic);
  let player = null;
  let running = false;

  // ---------- top: where we are, and the lesson controls ----------
  const sectionText = h("span", { class: "ls-section" }, info.topic);
  const stateText = h("span", { class: "ls-state" }, "Ready");
  const topLeft = h("div", { class: "ls-top-left" },
    h("button", { class: "ls-panel-btn", title: "Outline and transcript", "aria-label": "Outline and transcript",
      onclick: () => toggleDrawer() }, icon("panel")),
    h("div", { class: "ls-where" }, h("strong", {}, lessonKind === "prerequisite" ? h("span", { class: "ls-kind" }, "Prerequisite") : null, info.topic),
      h("small", {}, stateText, " · ", sectionText)));
  // The board tabs (Notebook, Slides, Code, Visual) sit at the top centre of the page.
  const topCenter = h("div", { class: "ls-top-center" }, used.length ? stage.indicator : null);

  const clock = new ClassClock(info.duration_min);
  const mmss = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  const clockText = h("span", {}, `0:00 / ${mmss(clock.totalMs)}`);
  const clockChip = h("span", { class: "ls-clock", title: "Lecture time used / total lecture time" }, icon("clock"), clockText);

  // The teacher and the playback controls, together at the top right.
  const playBtn = h("button", { class: "ls-ctl ls-play", title: "Start (space)", onclick: () => togglePlay() }, icon("play"));
  // The teacher previewing a shared lesson can read the script students get, and regenerate it in Studio.
  const preview = postId && !student;
  const scriptBtn = preview ? h("button", { class: "pv-btn", title: "Read the script students get",
    onclick: () => toggleScript() }, icon("book"), h("span", {}, "Script")) : null;
  const regenBtn = preview ? h("button", { class: "pv-btn primary", title: "Write this lesson's script again, in its lecture workspace",
    onclick: () => regenerate() }, icon("sparkle"), h("span", {}, "Regenerate")) : null;
  const topRight = h("div", { class: "ls-top-right" },
    h("div", { class: "ls-controls" }, playBtn),
    clockChip,
    h("button", { class: "ls-end", title: "End the lesson", onclick: () => endLesson() }, h("span", { class: "ls-end-dot" }), "End"));
  const followBtn = h("button", { class: "ls-follow hidden", onclick: () => stage.followNow() }, icon("focus"), "Follow tutor");
  stage.onFollowChange = (on) => followBtn.classList.toggle("hidden", on || !running);

  // ---------- the board ----------
  const overlay = h("div", { class: "stage-overlay" });
  const board = h("div", { class: "ls-board" }, stage.el, overlay);

  // ---------- bottom: the live caption, and asking a doubt ----------
  const captionText = h("p", { class: "ls-caption-text" });
  // The tutor beside the caption: two looping videos of the same character (web/assets/tutor, made with
  // `main.py tutor-video`): the talking loop while the voice speaks, the idle loop otherwise. If they can't load, the
  // 3D teacher takes their place, and if that can't either, the teacher's initials. info.tutor names the tutor for
  // the lesson's voice ("male": tutor-male-idle.mp4 ...); none is the default tutor.
  const tutorPrefix = info.tutor ? `tutor-${info.tutor}-` : "tutor-";
  const tutorClip = (name) => {
    const v = h("video", { class: `ls-tutor-video ${name === "idle" ? "on" : ""}`, src: `assets/tutor/${tutorPrefix}${name}.mp4`,
      poster: `assets/tutor/${tutorPrefix}${name}-poster.webp`, loop: true, playsinline: true, preload: "auto", "aria-hidden": "true",
      disablepictureinpicture: true, disableremoteplayback: true });
    v.muted = true;  // silent, so the browser lets it play on its own
    return v;
  };
  const tutorIdle = tutorClip("idle"), tutorTalking = tutorClip("talking");
  const tutor3d = h("div", { class: "ls-tutor-3d hidden" });
  const tutor = h("div", { class: "ls-tutor with-video", title: info.teacher },
    h("span", { class: "ls-tutor-orb" }, initials(info.teacher.replace(/^(prof|dr|mr|mrs|ms)\.?\s+/i, ""))),
    tutorIdle, tutorTalking, tutor3d, h("span", { class: "ls-tutor-ring" }));
  const caption = h("div", { class: "ls-caption" }, tutor, captionText);

  // ---------- the voice dock (bottom right): hold Space (or the orb) and speak a doubt; what is heard shows live ----
  const askInput = h("textarea", { class: "vd-input", rows: 1, placeholder: "Type your doubt…" });
  const sendBtn = h("button", { class: "vd-send hidden", title: "Ask (Enter)" }, icon("arrowRight"));
  const dockText = h("div", { class: "vd-text", "aria-live": "polite" });
  const dockOrb = h("button", { class: "vd-orb", title: "Hold to ask a doubt (or hold Space)", "aria-label": "Hold to ask a doubt" },
    h("span", { class: "vd-wave" }, [0, 1, 2, 3, 4].map(() => h("i"))), icon("mic"));
  const askBox = h("div", { class: "vd", dataset: { state: "start" } }, dockText, askInput, sendBtn, dockOrb);

  // ---------- the checkpoint bar: the lesson as a row of checkpoints the student can go back to ----------
  const scrubFill = h("i", { class: "sc-fill" });
  const scrubHeard = h("div", { class: "sc-heard" });
  const scrubMarks = h("div", { class: "sc-marks" });
  const scrubTip = h("div", { class: "sc-tip hidden" });
  const scrubTrack = h("div", { class: "sc-track", "aria-label": "Lesson checkpoints" }, scrubHeard, scrubFill, scrubMarks, scrubTip);
  const restartBtn = h("button", { class: "sc-btn", title: "Restart this part", onclick: () => restartPart() }, icon("reset"));
  const continueBtn = h("button", { class: "sc-gap sc-continue hidden", title: "Go back to where you were", onclick: () => continueWhereLeft() }, "Continue");
  const speedBtn = h("button", { class: "sc-btn sc-speed", title: "Speed (changes from the next sentence)", onclick: () => cycleSpeed() });
  const gapChip = h("button", { class: "sc-gap hidden", title: "Go to the part with lines you haven't heard yet", onclick: () => jumpToGap() });
  const flagBtn = student ? h("button", { class: "sc-btn", title: "Tell your teacher this part was confusing", onclick: () => flagConfusing() },
    icon("question")) : null;
  const topicCount = h("span", { class: "sc-count" });
  const scrubRow = h("div", { class: "ls-scrub" }, restartBtn, scrubTrack, topicCount, continueBtn, gapChip, speedBtn, flagBtn);
  const bar = h("div", { class: "ls-bar" }, scrubRow,
    h("div", { class: "ls-bar-row" }, caption, h("div", { class: "ls-ask-wrap" }, askBox)));

  // ---------- drawer: outline and every question so far ----------
  const outline = h("ol", { class: "outline" });  // topics and their sub-topics (renderOutline, once checkpoints are known)
  const transcriptList = h("ol", { class: "transcript" });
  const drawer = h("aside", { class: "ls-drawer" },
    h("div", { class: "ls-drawer-head" }, h("strong", {}, "Lesson")),  // the panel button at the top left closes it
    h("div", { class: "ls-drawer-label" }, "Outline"), outline,
    h("div", { class: "ls-drawer-label" }, "Transcript"), transcriptList);
  const toggleDrawer = (on) => {
    lesson.classList.toggle("drawer-open", on);
    if (lesson.classList.contains("drawer-open")) renderTranscript();
    topLeft.querySelector(".ls-panel-btn").classList.toggle("active", lesson.classList.contains("drawer-open"));
  };

  // ---------- the script panel (teacher preview) ----------
  const scriptPanel = preview ? h("aside", { class: "ls-script" },
    h("div", { class: "ls-script-head" },
      h("div", {}, h("strong", {}, "Script"), h("small", {}, `Version ${info.version_number || 1} · what students get`)),
      h("button", { class: "ls-mini", onclick: () => toggleScript(false) }, "Close")),
    h("p", { class: "ls-script-note" }, "Regenerating writes a new script in the lecture workspace. Students keep this version until you approve the new one and share the update."),
    h("div", { class: "ls-script-body" }, renderScriptDoc(segments, info.teacher, { lectureId }))) : null;
  function toggleScript(on) {
    lesson.classList.toggle("script-open", on);
    scriptBtn?.classList.toggle("active", lesson.classList.contains("script-open"));
  }
  async function regenerate() {
    if (running && player && !player.paused) { player.pause(); renderPlay(); }
    location.hash = `#/lecture/${encodeURIComponent(lectureId)}/studio/regenerate`;
  }

  // The teacher's preview tools, under the title: what students get, and rewriting it.
  const previewBar = preview ? h("div", { class: "ls-preview-bar" },
    h("span", { class: "pv-tag" }, icon("eye"), "Teacher preview"), scriptBtn, regenBtn) : null;

  const lesson = h("div", { class: `lesson ${preview ? "is-preview" : ""}` }, board, topLeft, previewBar, topCenter, topRight, followBtn, bar, drawer, scriptPanel);
  main.replaceChildren(lesson);

  const clockTimer = setInterval(() => {
    if (!clockChip.isConnected) return clearInterval(clockTimer);
    clockText.textContent = `${mmss(clock.elapsed())} / ${mmss(clock.totalMs)}`;
    clockChip.classList.toggle("warn", clock.left() <= clock.totalMs * 0.10);
  }, 1000);

  // ---------- overlays ----------
  function showOverlay(content) {
    overlay.replaceChildren(content || "");
    overlay.classList.toggle("hidden", !content);
    lesson?.classList.toggle("has-overlay", !!content);  // the start and end screens have their own buttons
  }
  function splash() {
    const saved = postId ? (info.progress?.completed ? 0 : info.progress?.last_index || 0) : store.get(lectureId);
    const savedSec = saved > 0 && saved < segments.length ? [...sections].reverse().find(s => s.index <= saved) : null;
    const item = (ic, label, value) => h("div", { class: "sp-item" }, icon(ic), h("span", {}, label), h("strong", {}, value));
    showOverlay(h("div", { class: "splash" },
      h("div", { class: "splash-badge" }, icon("class")),
      lessonKind ? h("div", { class: "splash-kind" }, kindTag(lessonKind, info.post?.topic_title),
        lessonKind === "prerequisite" ? h("span", {}, `Watch this before the lecture${info.post?.topic_title ? ` on ${info.post.topic_title}` : ""}`) : null) : null,
      h("h2", {}, info.topic), h("p", { class: "muted" }, `Taught by the AI substitute for ${info.teacher}`),
      student ? h("p", { class: `splash-progress ${info.progress?.completed ? "done" : ""}` },
        info.progress?.completed ? "Completed: you're marked present" : `${info.progress?.percent || 0}% heard · present at 100%`) : null,
      h("div", { class: "sp-grid" }, item("clock", "Length", formatDuration(info.estimated_min)), item("layers", "Sections", sections.length),
        item("question", "Doubts", "Hold Space anytime"), item("volume", "Voice", info.voice ? info.voice_name || "Gnani" : "Browser"),
        info.model || info.live_model ? item("sparkle", "Model", info.model || info.live_model) : null),
      h("div", { class: "splash-actions" },
        h("button", { class: "btn primary lg", onclick: () => start(0) }, icon("play"), "Start class"),
        savedSec ? h("button", { class: "btn lg", onclick: () => start(savedSec.index) }, `Resume at “${savedSec.title}”`) : null)));
    // The opening line's clip (and the resume point's) loads while the start screen shows, so the voice starts
    // with the class instead of after a long first download.
    if (info.voice) for (const from of [0, savedSec?.index].filter(i => i != null))
      voice.prefetch(segments.slice(from).find(seg => seg.kind === "say")?.text);
  }
  splash();

  // ---------- attendance: the spoken lines this student heard ----------
  const heard = new Set(info.played || []);
  const unsent = new Set();
  let lineInView = !document.hidden, presentShown = !!info.progress?.completed, lastIndex = info.progress?.last_index || 0;
  const sayTotal = segments.filter(s => s.kind === "say").length;
  async function sendProgress() {
    if (!student || !unsent.size) return;
    const lines = [...unsent];
    unsent.clear();
    try {
      const res = await api.progress(postId, { version_id: info.version_id, lines, last_index: lastIndex });
      if (res.completed && !presentShown) { presentShown = true; toast("Lesson complete: you're marked present.", "success", 6000); }
    } catch { lines.forEach(i => unsent.add(i)); }  // tried again with the next batch
  }
  const progressTimer = student ? setInterval(sendProgress, 5000) : 0;
  const beacon = () => {  // the page is closing: send what is left
    if (!student || !unsent.size) return;
    const body = JSON.stringify({ version_id: info.version_id, lines: [...unsent], last_index: lastIndex });
    navigator.sendBeacon?.(`/api/posts/${postId}/progress`, new Blob([body], { type: "application/json" }));
    unsent.clear();
  };
  // A student's lesson pauses when they leave the tab: a line only counts if it played while they could hear it.
  const onVisibility = () => {
    if (!document.hidden) return;
    lineInView = false;
    if (student && running && player && !player.paused) { player.pause(); renderPlay(); }
    beacon();
  };
  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("pagehide", beacon);

  // ---------- checkpoints: where a student can go back to (checkpoints.js decides them from the script) ----------
  // A jump is one careful step at a time: the old lesson stops completely (voice, writing, anything loading), the board
  // is rebuilt silently up to the checkpoint, then the lesson plays on. Clicks during a jump are ignored.
  const durations = info.durations || {};
  const { topics, points, at: startAt, total: totalLen } = checkpoints(segments, durations);
  const lengthOf = (seg, i) => (startAt[i + 1] ?? totalLen) - startAt[i];
  const sayIndexes = segments.map((seg, i) => seg.kind === "say" ? i : -1).filter(i => i >= 0);
  const breaksDone = new Set();
  const allowSkip = !student || info.post?.allow_skip !== false;
  let furthest = info.progress?.last_index || 0, jumping = false, outlineKey = "";
  const SPEEDS = [0.75, 1, 1.25, 1.5];
  let speed = SPEEDS.includes(+pref.get("speed", 1)) ? +pref.get("speed", 1) : 1;

  const pointAtOrBefore = (i) => [...points].reverse().find(p => p.index <= i) || points[0];
  const reachedUpTo = () => Math.max(furthest, player?.cursor ?? 0);
  // Checkpoints a student may jump to: those reached, plus the next one when the teacher allows skipping ahead.
  function canJump(k) {
    if (!student) return true;
    const reached = points.filter(p => p.index <= reachedUpTo()).length;
    return k < reached || (allowSkip && k === reached);
  }
  function position() {  // seconds into the lesson now
    const c = Math.min(player?.cursor ?? lastIndex, segments.length - 1);
    if (!running || !player) return startAt[c] || 0;
    const seg = segments[c], p = voice.progress();
    const inLine = seg?.kind === "say" && p.seq === voice.seq ? p.frac * lengthOf(seg, c) : 0;
    return Math.min(totalLen, startAt[c] + inLine);
  }
  const pctOf = (t) => `${(100 * t / totalLen).toFixed(3)}%`;
  function moveScrub(t) { scrubFill.style.width = pctOf(t); }
  function renderScrub() {
    scrubMarks.replaceChildren(...points.map((p, k) => {
      const ok = canJump(k), done = p.index <= reachedUpTo();
      return h("button", { class: `sc-point ${done ? "reached" : ""} ${p.sub ? "sub" : "sc-topic"}`, style: `left:${pctOf(p.at)}`, disabled: !ok,
        "aria-label": p.label, onclick: () => jumpToPoint(k),
        onmouseenter: () => { scrubTip.replaceChildren(h("strong", {}, p.label), ...(ok ? [] : [h("span", {}, "Not reached yet")]));
          scrubTip.style.left = pctOf(p.at); scrubTip.classList.remove("hidden"); },
        onmouseleave: () => scrubTip.classList.add("hidden") });  // no number on the bar: the tooltip names the topic
    }));
    const now = currentTopic();
    topicCount.textContent = now ? `Topic ${now.n} of ${topics.length}` : `${topics.length} topics`;
    renderOutline();
    // What this student has heard: their attendance, line by line.
    scrubHeard.replaceChildren(...(student ? [...heard].filter(i => segments[i]?.kind === "say")
      .map(i => h("i", { style: `left:${pctOf(startAt[i])};width:${pctOf(lengthOf(segments[i], i))}` })) : []));
    // Shown once lines were skipped; the count is every line still to hear (as on the end screen).
    const skipped = student && sayIndexes.some(i => i < furthest && !heard.has(i)) ? sayIndexes.filter(i => !heard.has(i)).length : 0;
    gapChip.classList.toggle("hidden", !skipped);
    gapChip.textContent = `${skipped} left`;
    gapChip.title = `${skipped} line${skipped === 1 ? "" : "s"} not heard yet: go to the first one`;
    continueBtn.classList.toggle("hidden", !running || !player || pointAtOrBefore(furthest).index <= pointAtOrBefore(player.cursor).index);
    speedBtn.textContent = `${speed}x`;
    for (const b of [restartBtn, continueBtn, gapChip, ...scrubMarks.children]) b.classList.toggle("busy", jumping);
  }
  renderScrub();
  const scrubTimer = setInterval(renderScrub, 1500);  // heard lines, reached checkpoints and gaps change as it plays

  async function jumpTo(index) {
    if (jumping) return;  // one jump at a time
    jumping = true; renderScrub();
    try { await start(index); } finally { jumping = false; renderScrub(); }
  }
  function currentTopic() { return running && player ? [...topics].reverse().find(tp => tp.index <= player.cursor) || topics[0] : null; }
  // The side panel's outline: topics with their sub-topics, ticked once reached; reachable ones can be clicked.
  function renderOutline() {
    const here = running && player ? pointAtOrBefore(player.cursor) : null;
    const key = `${reachedUpTo()}|${here?.index}|${jumping}`;
    if (key === outlineKey) return;  // nothing changed since the last render
    outlineKey = key;
    const item = (p) => {
      const k = points.indexOf(p), done = p.index <= reachedUpTo() && p !== here;
      return h("li", { class: `${p.sub ? "o-sub" : ""} ${p === here ? "current" : ""} ${done ? "done" : ""}` },
        h("button", { onclick: () => jumpToPoint(k), disabled: !canJump(k), title: canJump(k) ? `Go to ${p.name}` : "Not reached yet" },
          h("span", { class: "o-num" }, p.sub ? `${p.topic}.${p.sub}` : p.topic), h("span", { class: "o-title" }, p.name)));
    };
    outline.replaceChildren(...topics.flatMap(tp => tp.points.map(item)));
  }

  function jumpToPoint(k) { if (canJump(k)) jumpTo(points[k].index); }
  function restartPart() { jumpTo(pointAtOrBefore(player?.cursor ?? lastIndex).index); }
  function continueWhereLeft() { jumpTo(pointAtOrBefore(furthest).index); }
  function jumpToGap() {
    const i = sayIndexes.find(j => j < furthest && !heard.has(j));
    if (i != null) jumpTo(pointAtOrBefore(i).index);
  }
  function cycleSpeed() {
    speed = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length];
    pref.set("speed", speed);
    if (player && running) player.nextRate = speed;  // from the next sentence
    else voice.setRate(speed);
    renderScrub();
  }
  voice.setRate(speed);

  // The transcript in the side panel: every line up to where the lesson got (to read; jumps use checkpoints).
  function renderTranscript() {
    const upTo = reachedUpTo();
    const cur = running ? player?.cursor : -1;
    transcriptList.replaceChildren(...sayIndexes.filter(i => i <= upTo).map(i => h("li", { class: i === cur ? "current" : "" }, segments[i].text)));
    if (!transcriptList.children.length) transcriptList.append(h("li", { class: "muted" }, "Lines appear here as the lesson plays."));
    transcriptList.querySelector(".current")?.scrollIntoView({ block: "center" });
  }

  // "This part was confusing": the student's flag on the line playing now, for the teacher.
  async function flagConfusing() {
    const c = player?.cursor ?? lastIndex;
    const i = segments[c]?.kind === "say" ? c : sayIndexes.filter(j => j <= c).pop() ?? sayIndexes[0];
    const wasPlaying = running && player && !player.paused;
    if (wasPlaying) { player.pause(); renderPlay(); }
    const sec = [...sections].reverse().find(x => x.index <= i);
    const comment = h("textarea", { class: "textarea", rows: 3, placeholder: "What was confusing? (optional)" });
    const sent = await modal({ title: "Was this part confusing?", text: `Your teacher sees this with the part you were on${sec ? ` (“${sec.title}”)` : ""}.`,
      body: [h("blockquote", { class: "flag-line" }, segments[i]?.text || ""), comment],
      actions: [{ label: "Cancel", value: null }, { label: "Send to teacher", kind: "primary", value: true }] });
    if (sent) {
      try {
        await api.feedback(postId, { version_id: info.version_id, line_index: i, section: sec?.title || "", comment: comment.value });
        toast("Sent. Thanks, that helps your teacher improve the lesson.", "success");
      } catch (e) { toast(e.message, "error"); }
    }
    if (wasPlaying && player?.paused) { player.resume(); renderPlay(); }
  }

  // ---------- player UI ----------
  let pendingAsk = null;
  let askingNow = false;  // the lesson was paused by Space (or a click on the box) to ask a doubt
  let holdTalking = false;    // Space is held: the student is speaking a doubt
  const ui = {
    onCaption(text) { lineInView = !document.hidden; setCaption(text); },
    onSpoken(index) {
      if (!student || !lineInView || heard.has(index)) return;
      heard.add(index); unsent.add(index);
    },
    onSection(title) {
      sectionText.textContent = title;
      renderOutline();
    },
    onProgress(i, n) {
      lastIndex = i;
      furthest = Math.max(furthest, i);
      if (!postId) store.set(lectureId, i >= n ? 0 : i);
    },
    isBreakDone(i) { return breaksDone.has(i); },
    onBreakDone(i) { breaksDone.add(i); },
    cancelAsk() { if (pendingAsk) { const r = pendingAsk; pendingAsk = null; r(""); } stopWait(); },
    // A question break (or a raised doubt being answered). There is no chat: the teacher's answer is heard and
    // captioned, and the dock shows what was asked and when the teacher is thinking.
    openCheckpoint(section, final) {
      raisedPending = false;
      setState("Question break");
      return {
        thinking(on) { thinkingNow = on; if (!on) asked = ""; setState(on ? "Thinking…" : "Question break"); },
        setLimit() {},
        setCount() {},
        teacher(text, opts = {}) { if (opts.passed) flash(`Passed to ${info.teacher || "your teacher"}`); },
        student(text) { asked = text; renderAskLock(); },
        note(text) { flash(text); },
        ask(seconds) {
          setState("Listening for questions");
          startWait(seconds);
          return new Promise(resolve => {
            pendingAsk = (v) => { pendingAsk = null; stopWait(); setState("Question break"); resolve(v); };
            renderAskLock();
          });
        },
        close() {
          thinkingNow = false; asked = "";
          setState(running ? "Teaching" : "Ready");
        },
      };
    },
  };

  // ---------- live caption: a word appears only once it has been spoken, like live subtitles ----------
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

  // ---------- asking: the voice dock ----------
  // Hold Space (or the orb) to speak a doubt: the lesson stops at once, what is heard shows live in the dock, and
  // letting go asks it. A tap opens a field to type instead (and starts or resumes the class while paused). At a
  // question break the dock counts down; nothing asked, and the lesson moves on.
  let raisedPending = false;
  let typingOpen = false;   // the field to type a doubt is open
  let thinkingNow = false;  // the teacher is working on an answer
  let asked = "";           // the doubt just asked, shown until the answer starts
  let dockFlash = "";       // a short note ("Passed to ...") shown for a moment
  let heardText = "";       // what the dictation has heard so far, while Space is held
  let waitTimerId = 0, waitLeft = 0, waitTotal = 0;
  function startWait(seconds) {
    stopWait();
    if (!seconds) return;
    waitLeft = waitTotal = seconds;
    waitTimerId = setInterval(() => {
      if (player?.paused) return;
      waitLeft -= 0.1;
      renderWait();
      if (waitLeft <= 0) { stopWait(); submit(""); }
    }, 100);
    renderWait();
  }
  function renderWait() {
    askBox.style.setProperty("--left", waitTotal ? Math.max(0, waitLeft / waitTotal) : 0);
    const n = askBox.querySelector(".vd-count");
    if (n) n.textContent = player?.paused ? "paused" : `${Math.ceil(Math.max(0, waitLeft))}s`;
  }
  function holdWait() { clearInterval(waitTimerId); waitTimerId = 0; askBox.style.setProperty("--left", 1); }
  function stopWait() { clearInterval(waitTimerId); waitTimerId = 0; waitTotal = 0; askBox.style.removeProperty("--left"); }

  const kbd = (k) => h("kbd", { class: "vd-kbd" }, k);
  function dockState() {
    if (holdTalking) return "listening";
    if (typingOpen) return "typing";
    if (thinkingNow) return "thinking";
    if (pendingAsk) return "waiting";
    if (dockFlash) return "note";
    if (asked) return "sent";
    if (player?.inBreak) return "answering";
    return running ? "idle" : "start";
  }
  // The dock shows one state at a time; it is rebuilt only when that state (or what was heard) changes.
  let dockKey = null;
  function renderAskLock() {
    const state = dockState();
    const key = `${state}|${heardText}|${asked}|${dockFlash}`;
    if (key === dockKey) return;
    dockKey = key;
    askBox.dataset.state = state;
    askInput.disabled = state !== "typing";
    const quote = (t) => h("span", { class: "vd-quote" }, `“${t}”`);
    const words = (t) => t.split(/\s+/).filter(Boolean).map((w, i, all) => h("span", { class: `vd-w${i >= all.length - 2 ? " new" : ""}` }, `${w} `));
    dockText.replaceChildren(...{
      start: [h("span", { class: "vd-hint" }, kbd("Space"), " to start the class")],
      idle: [h("span", { class: "vd-hint" }, "Hold ", kbd("Space"), " to ask a doubt")],
      listening: heardText ? words(heardText) : [h("span", { class: "vd-hint" }, "Listening… let go to ask")],
      typing: [h("span", { class: "vd-hint" }, kbd("Enter"), " to ask · ", kbd("Esc"), " to carry on")],
      thinking: [asked ? quote(asked) : null, h("span", { class: "vd-dots" }, h("i"), h("i"), h("i"))],
      sent: [quote(asked), h("span", { class: "vd-hint" }, "after this sentence")],
      waiting: [h("span", { class: "vd-hint" }, "Any doubts? Hold ", kbd("Space")), h("span", { class: "vd-count" })],
      answering: [h("span", { class: "vd-hint" }, "Hold ", kbd("Space"), " to ask a doubt")],
      note: [h("span", { class: "vd-hint" }, dockFlash)],
    }[state]);
    if (state === "waiting") renderWait();
    if (state === "typing") requestAnimationFrame(() => askInput.focus());
  }
  function flash(text) { dockFlash = text; renderAskLock(); setTimeout(() => { dockFlash = ""; renderAskLock(); }, 3500); }

  // A tap: the field opens to type a doubt; the lesson pauses while it is open. Enter asks (the teacher answers
  // right after the current sentence); Esc carries on without asking.
  function askNow() {
    if (!running || !player) return;
    if (!pendingAsk && !player.paused) { player.pause(); renderPlay(); askingNow = true; }
    typingOpen = true;
    renderAskLock();
  }
  function cancelAsk() {
    askInput.blur();
    typingOpen = false;
    if (askingNow && !askInput.value.trim() && player?.paused) { player.resume(); renderPlay(); }
    askingNow = false;
    renderAskLock();
  }

  // spoken: the doubt was spoken with Space held, so it interrupts the teacher instead of waiting for the sentence.
  function submit(text, spoken = false) {
    askingNow = false; typingOpen = false;
    text = text.trim();
    askInput.value = ""; autosize(); renderSend();
    if (pendingAsk) { const r = pendingAsk; pendingAsk = null; r(text); return; }
    if (!text) { renderAskLock(); return; }
    if (!running || !player) { toast("Start the class first, then ask.", "info"); return; }
    if (isNoDoubt(text)) { if (player.paused) { player.resume(); renderPlay(); } renderAskLock(); return; }  // "no": carry on
    asked = text;
    if (spoken) {  // held Space and spoke: the teacher stops and answers now (thinking shows straight away)
      thinkingNow = true;
      if (!player.inBreak) raisedPending = true;
      player.interruptNow(text);
      renderPlay();
      return;
    }
    // Typed mid-lesson: the teacher answers right after the current sentence.
    player.raiseHand(text);
    raisedPending = true;
    if (player.paused) { player.resume(); renderPlay(); }
    renderAskLock();
  }
  const autosize = () => { askInput.style.height = "auto"; askInput.style.height = `${Math.min(askInput.scrollHeight, 96)}px`; };
  const renderSend = () => { sendBtn.classList.toggle("hidden", !askInput.value.trim()); };
  askInput.addEventListener("input", () => { autosize(); renderSend(); if (askInput.value.trim()) holdWait(); });
  askInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (askInput.value.trim()) submit(askInput.value); }
    else if (e.key === "Escape") { e.preventDefault(); cancelAsk(); }
  });
  sendBtn.addEventListener("click", () => askInput.value.trim() && submit(askInput.value));

  // Hold to talk (Space, or pressing the orb): the lesson stops at once (mid-sentence), the student speaks while
  // holding, and letting go asks the doubt; the teacher answers it on screen, then picks the lesson up from the
  // sentence it stopped in. Nothing heard: the lesson simply carries on.
  const HOLD_MS = 280;  // shorter than this is a tap (type a doubt, or play/pause)
  let holdTimer = 0, spaceDown = false, talkPaused = false;
  const talk = createDictation(info.language, (text) => { heardText = text; renderAskLock(); }, () => {
    const text = heardText.trim();
    holdTalking = false; heardText = "";
    if (text) submit(text, true);
    else if (talkPaused && player?.paused) { player.resume(); renderPlay(); }
    talkPaused = false;
    renderAskLock();
  }, true);
  function startTalking() {
    holdTimer = 0;
    if (!talk) { toast("Speaking needs Chrome or Safari: type your doubt instead.", "info"); askNow(); return; }
    holdTalking = true; heardText = ""; typingOpen = false; askInput.blur();
    talkPaused = !pendingAsk && !player.paused;
    if (talkPaused) { player.pause(); renderPlay(); }
    if (pendingAsk) holdWait();
    renderAskLock();
    try { talk.start(); } catch { holdTalking = false; renderAskLock(); }
  }
  function stopTalking() { if (holdTalking) talk.stop(); }
  // The orb: press and hold to talk, a click opens the field to type (or starts the class).
  dockOrb.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    dockOrb.setPointerCapture(e.pointerId);
    if (running && player) holdTimer = setTimeout(startTalking, HOLD_MS);
  });
  const orbUp = () => {
    if (holdTalking) { stopTalking(); return; }
    if (!holdTimer && running && player) return;
    clearTimeout(holdTimer); holdTimer = 0;
    if (!running) togglePlay(); else askNow();
  };
  dockOrb.addEventListener("pointerup", orbUp);
  dockOrb.addEventListener("pointercancel", () => { clearTimeout(holdTimer); holdTimer = 0; stopTalking(); });

  // ---------- controls ----------
  function setState(text) { stateText.textContent = text; renderAskLock(); }
  function renderPlay() {
    renderAskLock();
    const playing = running && !player?.paused;
    playBtn.replaceChildren(icon(playing ? "pause" : "play"));
    playBtn.title = !running ? "Start (space)" : playing ? "Pause" : "Resume (space)";
    lesson.classList.toggle("paused", running && !!player?.paused);
    if (running) setState(player.paused ? "Paused" : stateText.textContent === "Paused" || stateText.textContent === "Ready" ? "Teaching" : stateText.textContent);
  }
  function togglePlay() {
    if (!running) return start(0);
    if (player.paused) player.resume(); else player.pause();
    renderPlay();
  }
  renderPlay();

  let playing = null;  // the current lesson run (settles once it has stopped)
  async function start(from) {
    voice.unlock();
    if (player) {
      player.stop();
      // Wait until the old run has really finished (at most a few seconds), so two runs never share the board.
      await Promise.race([playing?.catch(() => {}), new Promise(r => setTimeout(r, 3000))]);
    }
    // Programs show their approved output during playback (for everyone): code runs for real only in Studio and in
    // doubt answers, never because a lesson was played or jumped around in.
    const p = new Player({ lectureId, segments, teacher: info.teacher, stage, voice, ui, clock, liveCode: false, lesson: lessonMeta });
    p.rate = speed;
    voice.setRate(speed);
    player = p;
    showOverlay(null);
    running = true;
    setState("Teaching");
    renderPlay();
    playing = run(p, from);  // start returns once the new run has begun; the run goes on by itself
  }

  async function run(p, from) {
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

  function jump(index) {  // the outline: a section start is always a checkpoint
    const k = points.findIndex(p => p.index >= index);
    if (k < 0 || !canJump(k)) { toast("You haven't reached this part yet.", "info"); return; }
    toggleDrawer(false);
    jumpTo(points[k].index);
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
    if (complete && !postId) {
      store.set(lectureId, 0);
      try { await api.complete(lectureId); ctx.setLectureStatus?.(lectureId, "completed"); } catch {}
    }
    await sendProgress();
    const missed = student ? sayTotal - [...heard].filter(i => segments[i]?.kind === "say").length : 0;
    const s = p.state;
    const item = (label, value) => h("div", { class: "sum-item" }, h("strong", {}, value), h("span", {}, label));
    showOverlay(h("div", { class: "splash" },
      h("div", { class: `splash-badge ${complete ? "ok" : "muted-badge"}` }, icon(complete ? "checkCircle" : "stop")), h("h2", {}, title),
      h("p", { class: "muted" }, `${info.topic} · taught for ${info.teacher}`),
      student ? h("p", { class: `splash-progress ${missed <= 0 ? "done" : ""}` }, missed <= 0 ? "You're marked present for this lesson."
        : `${missed} line${missed === 1 ? "" : "s"} not heard yet (skipped, or played while away). Play them to be marked present.`) : null,
      h("div", { class: "sum-grid" }, item("sections covered", s.covered.length), item("doubts asked", s.doubtsAsked),
        item(`passed to ${info.teacher}`, s.passed), item("failed actions", s.failed)),
      h("div", { class: "splash-actions" },
        complete ? null : h("button", { class: "btn primary", onclick: () => start(p.cursor) }, icon("play"), "Continue"),
        h("button", { class: `btn ${complete ? "primary" : ""}`, onclick: () => start(0) }, icon("reset"), "Run again"),
        h("a", { class: "btn", href: studio }, backLabel))));
  }

  // ---------- the live caption follows the voice ----------
  let raf = 0, smooth = 0, lastSound = 0, talking = false;
  const TALK_HOLD_MS = 350;  // the talking loop stays through the short gaps between words
  const loop = () => {
    smooth = smooth * 0.7 + voice.level() * 0.3;  // the ring around the tutor moves with the voice
    tutor.style.setProperty("--level", smooth.toFixed(3));
    const now = performance.now();
    if (smooth > 0.05) lastSound = now;
    const nowTalking = now - lastSound < TALK_HOLD_MS && !player?.paused;
    if (nowTalking !== talking) {
      talking = nowTalking;
      tutorTalking.classList.toggle("on", talking);
      tutorIdle.classList.toggle("on", !talking);
    }
    updateCaption();
    moveScrub(position());
    renderAskLock();
    raf = requestAnimationFrame(loop);
  };
  loop();

  const spaceKey = (e) => e.code === "Space" && !/INPUT|TEXTAREA|SELECT|BUTTON/.test(document.activeElement?.tagName);
  const onKey = (e) => {
    if (!spaceKey(e)) return;
    e.preventDefault();
    if (e.repeat || spaceDown) return;
    spaceDown = true;
    // A class under way: holding Space talks. A tap is decided when the key comes up.
    if (running && player) holdTimer = setTimeout(startTalking, HOLD_MS);
  };
  const onKeyUp = (e) => {
    if (e.code !== "Space" || !spaceDown) return;
    spaceDown = false;
    e.preventDefault();
    if (holdTalking) { stopTalking(); return; }
    if (holdTimer) { clearTimeout(holdTimer); holdTimer = 0; }
    else if (running && player) return;  // the hold already started talking (or failed to)
    // A tap: Space starts the class and resumes a pause; while the lesson plays (or at a question break) it opens
    // the box to type a doubt.
    if (!running || (player?.paused && !pendingAsk)) { askingNow = false; togglePlay(); } else askNow();
  };
  document.addEventListener("keydown", onKey);
  document.addEventListener("keyup", onKeyUp);

  // ---------- the 3D tutor (optional): plays and lip-syncs the same voice ----------
  let avatar = null, avatarLoading = false;
  const webgl = () => { try { return !!document.createElement("canvas").getContext("webgl2"); } catch { return false; } };
  async function enableAvatar() {
    if (avatar || avatarLoading || !info.avatar?.enabled || !webgl()) return;
    avatarLoading = true;
    tutor3d.classList.remove("hidden");
    tutor.classList.add("with-3d");
    try {
      const { createAvatar } = await import("./avatar/avatar.js");  // three.js loads only when the tutor is shown
      const created = await createAvatar({ container: tutor3d, modelUrl: info.avatar.model_url || undefined });
      if (!avatarLoading) { created.dispose(); return; }
      avatar = created;
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
    tutor3d.replaceChildren();
    tutor3d.classList.add("hidden");
    tutor.classList.remove("with-3d");
  }
  // Both loops play all the time (only their visibility switches), so a switch is instant.
  let videoFailed = false;
  const onVideoError = () => {
    if (videoFailed) return;
    videoFailed = true;
    console.warn("[tutor] the tutor videos could not load; using the 3D teacher");
    tutor.classList.remove("with-video");
    enableAvatar();
  };
  for (const v of [tutorIdle, tutorTalking]) {
    v.addEventListener("error", onVideoError);
    v.play().catch(() => {});
  }

  return () => {
    clearInterval(progressTimer);
    clearInterval(scrubTimer);
    sendProgress();
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("pagehide", beacon);
    disableAvatar();
    for (const v of [tutorIdle, tutorTalking]) { v.pause(); v.removeAttribute("src"); v.load(); }
    cancelAnimationFrame(raf);
    clearInterval(clockTimer);
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("keyup", onKeyUp);
    try { talk?.abort(); } catch {}
    if (player) player.stop();
    player = null;
    voice.dispose();
  };
}
