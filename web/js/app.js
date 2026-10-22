// App shell: hash router, sidebar lecture list, overview page and "new lecture".

import { api, LECTURE_ID_RE } from "./api.js";
import { h, $, icon, toast, modal, badge, initials, STATUS_ORDER, languageSelect } from "./ui.js";
import { mountStudio } from "./studio.js";
import { mountClassroom } from "./classroom.js";

const main = $("#main");
const appEl = $("#app");
let lectures = [];
let unmount = null;

// Lectures created here but with no files uploaded yet (the backend only lists folders in data/).
const PENDING_KEY = "eris-pending-lectures";
function pending() {
  try { return JSON.parse(localStorage.getItem(PENDING_KEY) || "[]"); } catch { return []; }
}
function setPending(ids) {
  try { localStorage.setItem(PENDING_KEY, JSON.stringify(ids)); } catch {}
}

export async function refreshLectures() {
  try {
    lectures = await api.lectures();
  } catch (e) {
    toast(`Could not load lectures: ${e.message}`, "error");
    lectures = [];
  }
  const known = new Set(lectures.map(l => l.id));
  const still = pending().filter(id => !known.has(id));
  setPending(still);
  lectures = [...lectures, ...still.map(id => ({ id, status: "new", local: true }))]
    .sort((a, b) => a.id.localeCompare(b.id));
  renderSidebar();
  return lectures;
}

function currentRoute() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  if (parts[0] === "lecture" && parts[1]) return { page: parts[2] === "class" ? "class" : "studio", id: parts[1] };
  return { page: "home" };
}

function renderSidebar() {
  const route = currentRoute();
  const list = $("#lecture-list");
  list.replaceChildren(...lectures.map(l => h("li", {},
    h("a", { class: `lecture-link ${route.id === l.id ? "active" : ""}`, href: `#/lecture/${encodeURIComponent(l.id)}/studio`, title: `${l.id} · ${l.status}` },
      h("span", { class: "lecture-avatar" }, initials(l.id)),
      h("span", { class: "name" }, l.id),
      h("span", { class: `dot ${l.status}` })))));
  if (!lectures.length) list.append(h("li", { class: "muted", style: "padding:6px 11px;font-size:12.5px" }, "No lectures yet"));
  document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("active", route.page === "home" && a.dataset.nav === "home"));
}

export function setLectureStatus(id, status) {
  const l = lectures.find(x => x.id === id);
  if (l && l.status !== status) { l.status = status; renderSidebar(); }
}

export async function newLecture() {
  // The teacher names the topic and length once, here at the start; the id is suggested from the topic.
  const topic = h("input", { class: "input", placeholder: "e.g. Introduction to recursion", autocomplete: "off" });
  const defaults = await api.personaTemplate().catch(() => ({}));  // the configured total and speaking time
  const duration = h("input", { class: "input", type: "number", min: 5, max: 120, step: 5, value: defaults.duration_min || 15 });
  const speaking = h("input", { class: "input", type: "number", min: 1, max: 120, step: 1, value: defaults.speaking_min || 5 });
  const language = languageSelect(defaults.language, defaults.languages);
  const input = h("input", { class: "input mono", placeholder: "intro_topic_week1", autocomplete: "off", spellcheck: "false" });
  const hint = h("small", {}, "3–63 characters: letters, digits, _ or -. It names the folder in data/.");
  let idEdited = false;
  const slug = (t) => t.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
  topic.addEventListener("input", () => { if (!idEdited) input.value = slug(topic.value); });
  input.addEventListener("input", () => { idEdited = true; });
  for (const el of [topic, duration, speaking, input]) {
    el.addEventListener("keydown", (e) => { if (e.key === "Enter") e.target.closest(".modal").querySelector(".btn.primary").click(); });
  }
  const bad = (el) => { el.classList.add("invalid"); el.focus(); return undefined; };
  const made = await modal({
    title: "New lecture",
    text: "What will this lecture teach? Next, you'll upload the study material and describe the teacher.",
    body: h("div", { class: "new-lecture-fields" },
      h("label", { class: "field" }, h("span", {}, "Topic"), topic),
      h("div", { class: "field-row" },
        h("label", { class: "field" }, h("span", {}, "Total lecture time (min)"), duration),
        h("label", { class: "field" }, h("span", {}, "Speaking time (min)"), speaking)),
      h("label", { class: "field" }, h("span", {}, "Teaching language"), language),
      h("small", { class: "muted" }, "The script is written for the speaking time; doubts, notes and code fill the rest. "
        + "The class warns when 10% and 5% of the total time are left."),
      h("label", { class: "field" }, h("span", {}, "Lecture id"), input, hint)),
    actions: [
      { label: "Cancel", value: null },
      { label: "Create lecture", kind: "primary", value: () => {
        const t = topic.value.trim(), d = +duration.value, sp = +speaking.value, v = input.value.trim();
        if (!t) return bad(topic);
        if (!(d >= 5 && d <= 120)) return bad(duration);
        if (!(sp >= 1 && sp <= d)) return bad(speaking);
        if (!LECTURE_ID_RE.test(v)) { hint.style.color = "var(--danger)"; return bad(input); }
        return { id: v, topic: t, duration_min: d, speaking_min: sp, language: language.value };
      } },
    ],
  });
  if (!made) return;
  try {
    await api.createLecture(made.id, { topic: made.topic, duration_min: made.duration_min, speaking_min: made.speaking_min,
      language: made.language });
  } catch (e) { return toast(e.message, "error", 6000); }
  await refreshLectures();
  location.hash = `#/lecture/${encodeURIComponent(made.id)}/studio`;
}

// ---------- overview ----------

const PIPE = [
  ["upload", "Upload material", "Slides, notes and lab sheets (PPTX, PDF, DOCX)."],
  ["user", "Describe the teacher", "Tone, pace, habits and what to cover or avoid."],
  ["sparkle", "Generate a script", "The AI writes narration, notes, code and question breaks."],
  ["checkCircle", "Review & approve", "Read it as a document, edit, and approve. Code is re-run."],
  ["class", "Run the class", "The AI teacher speaks, writes and answers student doubts."],
];

function renderOverview() {
  const counts = Object.fromEntries(STATUS_ORDER.map(s => [s, lectures.filter(l => l.status === s).length]));
  const ready = counts.approved + counts.completed;
  const card = (l) => {
    const step = STATUS_ORDER.indexOf(l.status);
    return h("a", { class: "card lecture-card", href: `#/lecture/${encodeURIComponent(l.id)}/${l.status === "approved" ? "class" : "studio"}` },
      h("div", { class: "top" }, h("span", { class: "lecture-avatar" }, initials(l.id)),
        h("div", { style: "min-width:0;flex:1" }, h("h3", {}, l.id)), badge(l.status)),
      h("div", { class: "progress" }, STATUS_ORDER.slice(1).map((_, i) => h("i", { class: i < step ? "on" : "" }))),
      h("div", { class: "foot" }, h("span", {}, nextStep(l.status)), icon("arrowRight")));
  };
  const page = h("div", { class: "page" },
    h("section", { class: "hero" },
      h("div", { class: "hero-art", html: '<svg viewBox="0 0 24 24"><path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2.5 9 2.5 12 0v-5"/></svg>' }),
      h("h1", {}, "Your class, taught while you're away."),
      h("p", {}, "Eris turns a teacher's material into an approved lecture script, then runs the class: it speaks in your style, writes on the notebook, runs real code and answers student doubts."),
      h("div", { style: "display:flex;gap:10px;flex-wrap:wrap" },
        h("button", { class: "btn lg", onclick: newLecture }, icon("plus"), "New lecture"),
        lectures.length ? h("a", { class: "btn lg outline", href: `#/lecture/${encodeURIComponent((lectures.find(l => l.status === "approved") || lectures[0]).id)}/studio` }, "Open a lecture") : null)),
    h("div", { class: "stat-row" },
      stat("Lectures", lectures.length), stat("Drafts to review", counts.draft),
      stat("Ready for class", ready), stat("Classes taught", counts.completed)),
    h("div", { class: "section-title" }, h("h2", {}, "How it works")),
    h("div", { class: "pipeline" }, PIPE.map(([ic, t, d], i) => h("div", { class: "card pipe-step" },
      h("div", { class: "pipe-icon" }, icon(ic)), h("h4", {}, `${i + 1}. ${t}`), h("p", {}, d)))),
    h("div", { class: "section-title" }, h("h2", {}, "Lectures"),
      h("button", { class: "btn sm", onclick: newLecture }, icon("plus"), "New")),
    h("div", { class: "lecture-grid" }, lectures.map(card),
      h("button", { class: "card lecture-card new-card", onclick: newLecture }, icon("plus"), "Create a lecture")));
  main.replaceChildren(page);
}

function stat(label, value) {
  return h("div", { class: "card stat" }, h("div", { class: "label" }, label), h("div", { class: "value" }, value));
}

function nextStep(status) {
  return { new: "Upload material & generate", indexed: "Generate a script", draft: "Review & approve",
    approved: "Ready to teach", completed: "Taught · run again" }[status] || "";
}

// ---------- router ----------

async function route() {
  if (unmount) { try { unmount(); } catch {} unmount = null; }
  const r = currentRoute();
  applySidebar(r);
  renderSidebar();
  main.scrollTop = 0;
  if (r.page === "home") { await refreshLectures(); renderOverview(); return; }
  if (!LECTURE_ID_RE.test(r.id)) { location.hash = "#/"; return; }
  const ctx = { main, refreshLectures, setLectureStatus };
  unmount = r.page === "class" ? await mountClassroom(r.id, ctx) : await mountStudio(r.id, ctx);
}

$("#new-lecture-btn").addEventListener("click", newLecture);
$("#theme-btn").addEventListener("click", () => {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("eris-theme", root.dataset.theme); } catch {}
});
// Sidebar: open on the Overview; on a lecture's Studio and Classroom it folds to an icon rail to give the work
// room, and slides out over the page while the mouse is on it. "Keep open" pins it open everywhere (remembered).
const PIN_KEY = "eris-sidebar-pinned";
const pinned = () => { try { return localStorage.getItem(PIN_KEY) === "1"; } catch { return false; } };
function applySidebar(r = currentRoute()) {
  appEl.classList.toggle("collapsed", r.page !== "home" && !pinned());
  appEl.classList.toggle("immersive", r.page === "class");  // the lesson takes the whole window
  appEl.classList.remove("peek");
  const btn = $("#collapse-btn");
  btn.querySelector("span").textContent = pinned() ? "Auto-hide" : "Keep open";
  btn.title = pinned() ? "Fold the sidebar away on lecture pages" : "Keep the sidebar open on lecture pages";
  btn.classList.toggle("pinned", pinned());
}
$("#collapse-btn").addEventListener("click", () => {
  try { localStorage.setItem(PIN_KEY, pinned() ? "0" : "1"); } catch {}
  applySidebar();
});
let peekTimer = null;
const sidebarEl = $("#sidebar");
sidebarEl.addEventListener("mouseenter", () => {
  if (!appEl.classList.contains("collapsed")) return;
  clearTimeout(peekTimer);
  peekTimer = setTimeout(() => appEl.classList.add("peek"), 120);  // a short delay, so passing the mouse by doesn't open it
});
sidebarEl.addEventListener("mouseleave", () => {
  clearTimeout(peekTimer);
  peekTimer = setTimeout(() => appEl.classList.remove("peek"), 200);
});
sidebarEl.addEventListener("click", (e) => { if (e.target.closest("a")) appEl.classList.remove("peek"); });
window.addEventListener("hashchange", route);
refreshLectures().then(route);
