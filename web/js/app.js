// App shell: sign-in, hash router, sidebar (the person's courses), home and course pages, Studio and the lesson.
//   #/                      home: course grid
//   #/course/<id>[/<tab>]   a course (classwork, people)
//   #/lesson/<postId>       a shared lesson (a student's own session, or the teacher's preview)
//   #/lecture/<id>/studio   build a lesson (teachers);  #/lecture/<id>/class  run its current script (teachers)

import { api, LECTURE_ID_RE, whenSignedOut } from "./api.js";
import { h, $, toast, initials, avatarTint } from "./ui.js";
import { mountStudio } from "./studio.js";
import { mountClassroom } from "./classroom.js";
import { renderAuth } from "./auth.js";
import { renderHome, mountCourse, newCourse, joinCourse } from "./courses.js";

const main = $("#main");
const appEl = $("#app");
let me = null;
let courses = [];
let lectures = [];
let unmount = null;

let coursesLoaded = false;
export async function refreshCourses() {
  try { courses = await api.courses(); coursesLoaded = true; } catch (e) { if (e.status !== 401) toast(`Could not load courses: ${e.message}`, "error"); courses = []; }
  renderSidebar();
  return courses;
}

export async function refreshLectures() {
  if (me?.role !== "teacher") return [];
  try { lectures = await api.lectures(); } catch { lectures = []; }
  return lectures;
}

function currentRoute() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  if (parts[0] === "lecture" && parts[1]) return { page: parts[2] === "class" ? "class" : "studio", id: parts[1], regenerate: parts[3] === "regenerate" };
  if (parts[0] === "course" && /^\d+$/.test(parts[1] || "")) return { page: "course", id: +parts[1], tab: parts[2] };
  if (parts[0] === "lesson" && /^\d+$/.test(parts[1] || "")) return { page: "lesson", id: +parts[1] };
  return { page: "home" };
}

function renderSidebar() {
  const route = currentRoute();
  const list = $("#lecture-list");
  list.replaceChildren(...courses.map(c => h("li", {},
    h("a", { class: `lecture-link ${route.page === "course" && route.id === c.id ? "active" : ""}`, href: `#/course/${c.id}`,
      title: `${c.subject}${c.year ? ` · ${c.year}` : ""}` },
      h("span", { class: "lecture-avatar", style: avatarTint(c.subject) }, initials(c.subject)),
      h("span", { class: "name" }, c.subject, c.year ? h("small", {}, c.year) : null),
      c.to_watch ? h("span", { class: "count-dot", title: `${c.to_watch} to watch` }, c.to_watch) : null))));
  if (!courses.length) list.append(h("li", { class: "muted", style: "padding:6px 11px;font-size:12.5px" }, "No courses yet"));
  document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("active", route.page === "home" && a.dataset.nav === "home"));
  const add = $("#new-lecture-btn");
  add.title = add.ariaLabel = me?.role === "teacher" ? "New course" : "Join a course";
  const userEl = $("#user-chip");
  if (me) userEl.replaceChildren(h("span", { class: "lecture-avatar", style: avatarTint(me.name) }, initials(me.name)),
    h("span", { class: "user-text" }, h("strong", {}, me.name), h("small", {}, me.role === "teacher" ? "Teacher" : "Student")));
}

export function setLectureStatus() {}

// ---------- router ----------

async function route() {
  if (unmount) { try { unmount(); } catch {} unmount = null; }
  if (!me) return;
  const r = currentRoute();
  applySidebar(r);
  renderSidebar();
  main.scrollTop = 0;
  const ctx = { main, refreshLectures, refreshCourses, setLectureStatus };
  if (r.page === "home") {
    await Promise.all([refreshCourses(), refreshLectures()]);
    if (currentRoute().page === "home") renderHome(main, me, courses, lectures);
    return;
  }
  if (!coursesLoaded) await refreshCourses();  // the sidebar lists them on every page
  if (r.page === "course") { unmount = await mountCourse(r.id, r.tab, ctx); return; }
  if (r.page === "lesson") { unmount = await mountClassroom(null, ctx, { postId: r.id }); return; }
  if (me.role !== "teacher" || !LECTURE_ID_RE.test(r.id)) { location.hash = "#/"; return; }
  unmount = r.page === "class" ? await mountClassroom(r.id, ctx) : await mountStudio(r.id, ctx, { regenerate: r.regenerate });
}

function showSignIn() {
  if (unmount) { try { unmount(); } catch {} unmount = null; }
  me = null;
  coursesLoaded = false;
  appEl.classList.add("signed-out");
  renderAuth(main, (user) => {
    me = user;
    appEl.classList.remove("signed-out");
    toast(`Signed in as ${user.name}.`, "success");
    route();  // the page they asked for, or home
  });
}
whenSignedOut(() => { if (me) { toast("Please sign in again.", "info"); showSignIn(); } });

$("#new-lecture-btn").addEventListener("click", () => me?.role === "teacher" ? newCourse() : joinCourse());
$("#signout-btn").addEventListener("click", async () => {
  try { await api.logout(); } catch {}
  courses = []; lectures = [];
  location.hash = "#/";
  showSignIn();
});
// Sidebar: open on the home and course pages; in Studio it folds to an icon rail to give the work room, and slides
// out over the page while the mouse is on it.
function applySidebar(r = currentRoute()) {
  appEl.classList.toggle("collapsed", ["studio", "class", "lesson"].includes(r.page));
  appEl.classList.toggle("immersive", r.page === "class" || r.page === "lesson");  // the lesson takes the whole window
  appEl.classList.remove("peek");
}
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
api.me().then((user) => { me = user; appEl.classList.remove("signed-out"); route(); }, () => showSignIn());
