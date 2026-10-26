// Small DOM helpers, icons, toasts and modals shared by every page.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const PATHS = {
  home: '<path d="M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
  file: '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/>',
  play: '<path d="M7 4.5v15l12-7.5z" fill="currentColor"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
  reset: '<path d="M4 4v6h6"/><path d="M20 12a8 8 0 0 0-14.3-4.9L4 10"/><path d="M4 12a8 8 0 0 0 14.3 4.9"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.5v.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.5v.01"/>',
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M8 7h7"/>',
  slides: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M12 17v4M8 21h8"/>',
  code: '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/>',
  class: '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2.5 9 2.5 12 0v-5"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  send: '<path d="M4 12l16-8-6 16-2.5-6.5z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  chat: '<path d="M4 5h16v11H9l-5 4z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  volume: '<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/>',
  arrowRight: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  save: '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7M8 20v-6h8v6"/>',
  log: '<path d="M8 6h12M8 12h12M8 18h12M4 6v.01M4 12v.01M4 18v.01"/>',
  skip: '<path d="M6 5l9 7-9 7z" fill="currentColor"/><path d="M18 5v14"/>',
  question: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17v.01"/>',
  volumeOff: '<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M17 9l5 6M22 9l-5 6"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  pen: '<path d="M4 20l1-5L16 4l4 4L9 19z"/><path d="M14 6l4 4"/>',
  micOff: '<path d="M9 5a3 3 0 0 1 6 0v5M15 13.5A3 3 0 0 1 9 11V9"/><path d="M5 11a7 7 0 0 0 11.5 5.4M19 11a7 7 0 0 1-.4 2.3M12 18v3M3 3l18 18"/>',
  focus: '<path d="M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4"/>',
  captions: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 13h3M13 13h4M7 16h6"/>',
  back: '<path d="M15 6l-6 6 6 6"/>',
  menu: '<path d="M5 9h14M5 15h14"/>',
  panel: '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M9 4v16"/>',
};

export function icon(name, cls = "") {
  const span = document.createElement("span");
  span.innerHTML = `<svg viewBox="0 0 24 24" class="${cls}">${PATHS[name] || ""}</svg>`;
  return span.firstChild;
}

export function toast(message, kind = "info", ms = 3800) {
  const root = $("#toasts");
  const el = h("div", { class: `toast ${kind}` },
    icon(kind === "error" ? "alert" : kind === "success" ? "checkCircle" : "info"), h("div", {}, message));
  root.append(el);
  setTimeout(() => { el.style.transition = "opacity .2s"; el.style.opacity = "0"; setTimeout(() => el.remove(), 220); }, ms);
}

// A modal that resolves with the clicked action's value (or null when dismissed).
export function modal({ title, text, body, actions, wide = false }) {
  return new Promise((resolve) => {
    const root = $("#modal-root");
    const close = (value) => { root.innerHTML = ""; document.removeEventListener("keydown", onKey); resolve(value); };
    const onKey = (e) => { if (e.key === "Escape") close(null); };
    const foot = h("div", { class: "modal-foot" });
    for (const a of actions) {
      foot.append(h("button", { class: `btn ${a.kind || ""}`, onclick: () => {
        const v = a.value instanceof Function ? a.value() : a.value;
        if (v !== undefined) close(v);
      } }, a.label));
    }
    const box = h("div", { class: `modal ${wide ? "wide" : ""}`, role: "dialog", "aria-modal": "true" },
      h("div", { class: "modal-head" }, h("h2", {}, title), text ? h("p", {}, text) : null),
      body ? h("div", { class: "modal-body" }, body) : null, foot);
    const backdrop = h("div", { class: "modal-backdrop", onmousedown: (e) => { if (e.target === backdrop) close(null); } }, box);
    root.append(backdrop);
    document.addEventListener("keydown", onKey);
    (box.querySelector("input, textarea") || foot.lastChild)?.focus();
  });
}

export const confirmDialog = (title, text, label = "Confirm", kind = "primary") =>
  modal({ title, text, actions: [{ label: "Cancel", value: false }, { label, kind, value: true }] });

// The LLM model's name, as a small tag (where a script is written, and where the AI teaches and answers).
export function modelTag(name, cls = "") {
  return name ? h("span", { class: `model-tag ${cls}`, title: "LLM model" }, icon("sparkle"), name) : null;
}

// What kind of lesson: the lecture the AI teaches in the teacher's absence, or a prerequisite to watch before it.
export function kindTag(kind, topic = "") {
  const pre = kind === "prerequisite";
  return h("span", { class: `kind-tag ${pre ? "pre" : "lecture"}`,
    title: pre ? `Watch before the lecture${topic ? ` on ${topic}` : ""}` : "The class lecture, taught by the AI substitute" },
    icon(pre ? "layers" : "class"), pre ? "Prerequisite" : "Lecture");
}

export function badge(status) {
  return h("span", { class: `badge ${status}` }, status);
}

// Decimal minutes as a person says them: 4.7 -> "4 min 42 s", 5 -> "5 min", 0.5 -> "30 s".
export function formatDuration(minutes) {
  if (minutes == null || !isFinite(minutes)) return "?";
  const total = Math.round(minutes * 60);
  const m = Math.floor(total / 60), s = total % 60;
  if (!m) return `${s} s`;
  return s ? `${m} min ${s} s` : `${m} min`;
}

// A warm tint per name, the same every time (sage, terracotta, honey, plum, teal).
const TINTS = ["primary", "accent", "warning", "violet", "sky"];
export function avatarTint(name) {
  let n = 0;
  for (const ch of String(name)) n = (n * 31 + ch.charCodeAt(0)) >>> 0;
  const t = TINTS[n % TINTS.length];
  return `background: var(--${t}-soft); color: var(--${t})`;
}

// "Oct 30, 5:00 PM" from an ISO date or a datetime-local value.
export function formatDate(value) {
  if (!value) return "";
  const d = new Date(value);
  if (isNaN(d)) return String(value);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function initials(name) {
  const parts = String(name).split(/[_\-\s]+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || parts[0]?.[1] || "")).toUpperCase();
}

export const STATUS_ORDER = ["new", "indexed", "draft", "approved", "completed"];

// The lecture's teaching language: the script is written in it, the voice says it and hears students in it.
export const LANGUAGES = [["en-IN", "English"], ["hi-IN", "Hindi"], ["ta-IN", "Tamil"], ["te-IN", "Telugu"],
  ["kn-IN", "Kannada"], ["ml-IN", "Malayalam"], ["mr-IN", "Marathi"], ["bn-IN", "Bengali"], ["gu-IN", "Gujarati"],
  ["pa-IN", "Punjabi"]];

export function languageSelect(value, languages) {
  const list = languages?.length ? languages.map(l => [l.code, l.name]) : LANGUAGES;
  return h("select", { class: "select" },
    list.map(([code, name]) => h("option", { value: code, selected: code === (value || "en-IN") }, name)));
}
