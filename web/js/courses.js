// Courses: the home page (a grid of the person's courses) and a course's page.
// A course has a Stream (everything shared, newest first), Classwork (chapters > topics > lessons and material)
// and People. Teachers build lessons in topics, open them in Studio, and share approved ones; students play them.

import { api } from "./api.js";
import { h, icon, toast, modal, confirmDialog, badge, kindTag, avatarTint, initials, formatDate, languageSelect } from "./ui.js";
import { showVersions } from "./versions.js";

const greeting = () => { const hr = new Date().getHours(); return hr < 12 ? "Good morning" : hr < 17 ? "Good afternoon" : "Good evening"; };
// "Prof. Ananya Rao" -> "Ananya" (a title is not a name to greet).
const firstName = (n) => String(n || "").replace(/^(prof|dr|mr|mrs|ms|miss|sir)\.?\s+/i, "").split(" ")[0];
// What the guardrails flagged on a doubt: red when it was blocked, amber when only flagged.
const safetyTags = (flags) => flags?.length ? h("div", { class: "safety-tags" }, flags.map(f =>
  h("span", { class: `safety-tag ${f.blocked ? "blocked" : ""}`, title: `Safety check, probability ${f.p}` },
    icon("alert"), f.blocked ? `Blocked: ${f.label}` : `Flagged: ${f.label}`))) : null;
const courseName = (c) => `${c.subject}${c.year ? ` · ${c.year}` : ""}`;

// ---------- home ----------

export function renderHome(main, me, courses, lectures = []) {
  const teacher = me.role === "teacher";
  const card = (c) => h("a", { class: "card course-card", href: `#/course/${c.id}` },
    h("div", { class: "course-band", style: avatarTint(c.subject) }, h("span", { class: "course-initials" }, initials(c.subject))),
    h("div", { class: "course-body" },
      h("h3", {}, c.subject), h("p", { class: "muted" }, c.year || " "),
      h("div", { class: "course-foot" }, teacher
        ? [h("span", {}, icon("user"), `${c.students} student${c.students === 1 ? "" : "s"}`),
           h("span", {}, icon("class"), `${c.lessons} lesson${c.lessons === 1 ? "" : "s"}`),
           h("span", { class: "code-chip", title: "Class code" }, c.code)]
        : [h("span", {}, icon("user"), c.teacher),
           c.to_watch ? h("span", { class: "todo-chip" }, `${c.to_watch} to watch`) : h("span", { class: "done-chip" }, icon("check"), "All caught up")])));
  const addCard = h("button", { class: "card course-card new-card", onclick: teacher ? () => newCourse() : () => joinCourse() },
    icon("plus"), teacher ? "Create a course" : "Join a course");
  const loose = lectures.filter(l => !l.in_course);
  main.replaceChildren(h("div", { class: "page home" },
    h("div", { class: "home-head" },
      h("div", {}, h("div", { class: "hero-kicker" }, `${greeting()}, ${firstName(me.name)}`),
        h("h1", { class: "home-title" }, "Your courses")),
      h("button", { class: "btn primary", onclick: teacher ? () => newCourse() : () => joinCourse() }, icon("plus"), teacher ? "New course" : "Join a course")),
    courses.length ? null : h("div", { class: "card empty" }, h("div", { class: "empty-icon" }, icon(teacher ? "class" : "book")),
      h("h3", {}, teacher ? "Create your first course" : "Join your first course"),
      h("p", {}, teacher ? "A course is a subject you teach to a year, like DSA for 4th year. Students join it with its class code."
        : "Ask your teacher for the class code, then join the course to see its lessons.")),
    h("div", { class: "course-grid" }, courses.map(card), addCard),
    teacher && loose.length ? [
      h("div", { class: "loose-head" }, h("h2", {}, "Lectures not in a course"),
        h("p", { class: "muted" }, "Only you can see these. Students can't until a lecture is part of a course.")),
      h("div", { class: "loose-list" }, loose.map(l => h("a", { class: "loose-item", href: `#/lecture/${encodeURIComponent(l.id)}/studio` },
        h("span", { class: "lecture-avatar", style: avatarTint(l.id) }, initials(l.id)), h("span", { class: "name" }, l.id), badge(l.status))))] : null));
}

export async function newCourse() {
  const subject = h("input", { class: "input", placeholder: "e.g. Data Structures and Algorithms" });
  const year = h("input", { class: "input", placeholder: "e.g. 4th year, Section B" });
  const made = await modal({
    title: "New course", text: "One course per subject you teach to a class. Students join it with its code.",
    body: [h("label", { class: "field" }, h("span", {}, "Subject"), subject), h("label", { class: "field" }, h("span", {}, "Year or class"), year)],
    actions: [{ label: "Cancel", value: null }, { label: "Create course", kind: "primary",
      value: () => subject.value.trim() ? { subject: subject.value.trim(), year: year.value.trim() } : (subject.classList.add("invalid"), undefined) }],
  });
  if (!made) return;
  try {
    const c = await api.createCourse(made.subject, made.year);
    location.hash = `#/course/${c.id}/classwork`;
  } catch (e) { toast(e.message, "error"); }
}

export async function joinCourse() {
  const code = h("input", { class: "input code-input", placeholder: "ABC123", maxlength: 8, autocomplete: "off", spellcheck: "false" });
  const value = await modal({
    title: "Join a course", text: "Enter the class code your teacher shared.",
    body: h("label", { class: "field" }, h("span", {}, "Class code"), code),
    actions: [{ label: "Cancel", value: null }, { label: "Join", kind: "primary", value: () => code.value.trim() || (code.classList.add("invalid"), undefined) }],
  });
  if (!value) return;
  try {
    const c = await api.join(value);
    toast(`Joined ${courseName(c)}.`, "success");
    location.hash = `#/course/${c.id}`;
  } catch (e) { toast(e.message, "error", 6000); }
}

// ---------- a course ----------

export async function mountCourse(courseId, tab, ctx) {
  const { main } = ctx;
  main.replaceChildren(h("div", { class: "page" }, h("div", { class: "empty" }, h("div", { class: "spinner" }), "Loading course…")));
  let course;
  try { course = await api.course(courseId); }
  catch (e) {
    main.replaceChildren(h("div", { class: "page" }, h("div", { class: "callout error" }, icon("alert"), e.message)));
    return null;
  }
  const teacher = course.role === "teacher";
  tab = ["stream", "classwork", "people"].includes(tab) ? tab : teacher && !course.posts.length ? "classwork" : "stream";
  const reload = async () => { course = await api.course(courseId); render(); ctx.refreshCourses?.(); };
  const act = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, "error", 6000); } };

  const tabLink = (key, label, ic) => h("a", { class: `tab ${tab === key ? "active" : ""}`, href: `#/course/${courseId}/${key}` }, icon(ic), label);

  function header() {
    const codeEl = teacher ? h("div", { class: "class-code" },
      h("small", {}, "Class code"), h("strong", { class: "mono" }, course.code),
      h("button", { class: "icon-btn sm", title: "Copy the code", onclick: () => {
        navigator.clipboard?.writeText(course.code).then(() => toast("Code copied.", "success"), () => {});
      } }, icon("file")),
      h("button", { class: "icon-btn sm", title: "Make a new code (the old one stops working)", onclick: act(async () => {
        if (!await confirmDialog("New class code?", "Students who already joined stay in the course. The old code stops working.", "Make new code")) return;
        course.code = (await api.newCode(courseId)).code; render();
      }) }, icon("reset")),
      h("button", { class: "icon-btn sm danger-icon", title: "Delete this course", onclick: () => deleteCourse() }, icon("trash"))) : null;
    return h("header", { class: "course-header", style: avatarTint(course.subject) },
      h("div", { class: "course-header-text" },
        h("a", { class: "crumb", href: "#/" }, "Courses"),
        h("h1", {}, course.subject),
        h("p", {}, [course.year, teacher ? null : `Taught by ${course.teacher.name}`].filter(Boolean).join(" · "))),
      codeEl);
  }

  // ---------- stream ----------
  function lessonActions(post) {
    if (!teacher) {
      const p = post.my_progress || {};
      const label = p.completed ? "Watch again" : p.started ? "Continue" : "Start lesson";
      return h("div", { class: "post-lesson" },
        h("div", { class: "progress-line", title: `${p.percent || 0}% heard` }, h("i", { style: `width:${p.percent || 0}%` })),
        h("span", { class: `att-tag ${p.completed ? "present" : p.started ? "started" : ""}` },
          p.completed ? "Present" : p.started ? `${p.percent}% heard` : "Not started"),
        h("a", { class: `btn sm ${p.completed ? "" : "primary"}`, href: `#/lesson/${post.id}` }, icon("play"), label));
    }
    const a = post.attendance || { present: 0, total: 0 };
    return h("div", { class: "post-lesson" },
      h("div", { class: "progress-line", title: `${a.present} of ${a.total} present` }, h("i", { style: `width:${a.total ? (100 * a.present) / a.total : 0}%` })),
      h("span", { class: "att-tag" }, `${a.present}/${a.total} present${a.started > a.present ? ` · ${a.started - a.present} watching` : ""}`),
      h("button", { class: "btn sm", onclick: () => showAttendance(post) }, icon("user"), "Attendance"),
      h("button", { class: "btn sm", title: "Where students got stuck, and what they flagged as confusing",
        onclick: () => showInsights(post) }, icon("search"), "Insights"),
      h("button", { class: `btn sm ghost skip-toggle ${post.allow_skip ? "" : "on"}`,
        title: post.allow_skip ? "Students may skip ahead (click to require every part in order)" : "Students must hear every part in order (click to allow skipping ahead)",
        onclick: act(async () => { await api.editPost(post.id, { allow_skip: !post.allow_skip }); await reload(); }) },
        icon(post.allow_skip ? "skip" : "stop"), post.allow_skip ? "Skipping allowed" : "No skipping"),
      h("a", { class: "btn sm ghost", href: `#/lesson/${post.id}` }, icon("eye"), "Preview"));
  }

  function postCard(post) {
    const lesson = post.kind === "lesson";
    const files = post.files.length ? h("div", { class: "post-files" }, post.files.map(f =>
      h("a", { class: "file-chip", href: api.fileUrl(post.id, f.id), target: "_blank", rel: "noopener" }, icon("file"), f.name))) : null;
    const pre = lesson && post.lesson?.kind === "prerequisite";
    return h("article", { class: `card post ${lesson ? "is-lesson" : "is-material"} ${pre ? "is-pre" : ""}` },
      h("div", { class: "post-icon" }, icon(!lesson ? "book" : pre ? "layers" : "class")),
      h("div", { class: "post-main" },
        h("div", { class: "post-top" },
          h("div", { class: "post-title" },
            lesson ? h("div", { class: "post-kind" }, kindTag(post.lesson?.kind, post.topic_title),
              pre ? h("small", { class: "muted" }, `Watch before the lecture${post.topic_title ? ` on ${post.topic_title}` : ""}`) : null) : null,
            h("h3", {}, post.title),
            h("small", { class: "muted" }, [lesson ? `v${post.version?.number || 1}` : "Material", post.topic_title, `Posted ${formatDate(post.created_at)}`].filter(Boolean).join(" · "))),
          post.due_at ? h("span", { class: "due-chip" }, icon("clock"), `Due ${formatDate(post.due_at)}`) : null,
          teacher ? h("button", { class: "icon-btn sm", title: lesson ? "Stop sharing" : "Delete", onclick: act(async () => {
            if (!await confirmDialog(lesson ? "Stop sharing this lesson?" : "Delete this post?",
              lesson ? "Students won't see it any more, and its attendance is removed." : "Students won't see it any more.", lesson ? "Stop sharing" : "Delete", "danger")) return;
            await api.deletePost(post.id); await reload();
          }) }, icon("trash")) : null),
        post.body ? h("p", { class: "post-body" }, post.body) : null,
        files,
        lesson ? lessonActions(post) : null));
  }

  function stream() {
    return h("div", { class: "stream" },
      teacher ? h("div", { class: "card composer" },
        h("span", { class: "lecture-avatar", style: avatarTint(course.subject) }, initials(course.subject)),
        h("button", { class: "composer-btn", onclick: () => addMaterial() }, "Share notes or material with the class…"),
        h("a", { class: "btn sm", href: `#/course/${courseId}/classwork` }, icon("class"), "Share a lesson")) : null,
      course.posts.length ? course.posts.map(postCard)
        : h("div", { class: "card empty" }, h("div", { class: "empty-icon" }, icon("chat")),
          h("h3", {}, "Nothing shared yet"),
          h("p", {}, teacher ? "Build a lesson in Classwork and share it once it's approved, or share notes here." : "Lessons and notes your teacher shares show up here.")));
  }

  // ---------- classwork ----------
  function lessonRow(l) {
    const shared = !!l.post_id;
    const post = course.posts.find(p => p.id === l.post_id);
    const kind = kindTag(l.kind);
    if (!teacher) {
      const p = post?.my_progress || {};
      return h("li", { class: "lesson-row" },
        h("span", { class: "lesson-icon" }, icon("class")),
        h("div", { class: "lesson-name" }, h("strong", {}, l.title), kind),
        h("span", { class: `att-tag ${p.completed ? "present" : p.started ? "started" : ""}` }, p.completed ? "Present" : p.started ? `${p.percent}%` : "Not started"),
        h("a", { class: "btn sm", href: `#/lesson/${l.post_id}` }, icon("play"), p.completed ? "Again" : p.started ? "Continue" : "Start"));
    }
    const approved = ["approved", "completed"].includes(l.status);
    return h("li", { class: "lesson-row" },
      h("span", { class: "lesson-icon" }, icon("class")),
      h("div", { class: "lesson-name" }, h("strong", {}, l.title), kind, badge(l.status)),
      shared ? h("span", { class: "att-tag present" }, icon("check"), `Shared v${post?.version?.number || 1}`) : null,
      l.versions ? h("button", { class: "btn sm ghost", title: "Every approved script of this lesson",
        onclick: () => showVersions(l.id, { onChange: reload }) }, icon("layers"), `${l.versions} version${l.versions === 1 ? "" : "s"}`) : null,
      h("a", { class: "btn sm ghost", href: `#/lecture/${encodeURIComponent(l.lecture_id)}/studio` }, icon("edit"), "Studio"),
      shared && l.update_available ? h("button", { class: "btn sm primary", title: "Students get the newly approved script; attendance so far stays",
        onclick: act(async () => { const r = await api.share(l.id); toast(`Shared version ${r.version}.`, "success"); await reload(); }) }, icon("upload"), "Share update") : null,
      !shared ? h("button", { class: `btn sm ${approved ? "primary" : ""}`, disabled: !approved, title: approved ? "Share with the class" : "Approve the script in Studio first",
        onclick: () => shareLesson(l) }, icon("send"), "Share") : null,
      h("button", { class: "icon-btn sm", title: "Delete lesson", onclick: act(async () => {
        if (!await confirmDialog("Delete this lesson?", "Its attendance, and its lecture (material, script and audio), are deleted too. This can't be undone.", "Delete", "danger")) return;
        await api.deleteLesson(l.id); await reload();
      }) }, icon("trash")));
  }

  function topicBlock(t) {
    const materials = course.posts.filter(p => p.kind === "material" && p.topic_id === t.id);
    const visible = teacher || t.lessons.length || materials.length;
    if (!visible) return null;
    return h("div", { class: "topic" },
      h("div", { class: "topic-head" },
        h("h4", {}, t.title),
        teacher ? h("div", { class: "row-actions" },
          h("button", { class: "btn sm ghost", onclick: () => newLesson(t, "lecture") }, icon("plus"), "Lesson"),
          h("button", { class: "btn sm ghost", title: "A short lesson on what students need to know before this topic",
            onclick: () => newLesson(t, "prerequisite") }, icon("plus"), "Prerequisite"),
          h("button", { class: "btn sm ghost", onclick: () => addMaterial(t.id) }, icon("book"), "Material"),
          h("button", { class: "icon-btn sm", title: "Rename topic", onclick: act(async () => {
            const title = await askTitle("Rename topic", t.title); if (title) { await api.renameTopic(t.id, title); await reload(); }
          }) }, icon("edit")),
          h("button", { class: "icon-btn sm", title: "Delete topic", onclick: act(async () => {
            if (!await confirmDialog(`Delete “${t.title}”?`, "Its lessons are deleted too, with their material, scripts, audio and attendance. This can't be undone.", "Delete", "danger")) return;
            await api.deleteTopic(t.id); await reload();
          }) }, icon("trash"))) : null),
      t.lessons.length || materials.length ? h("ul", { class: "lesson-list" }, t.lessons.map(lessonRow),
        materials.map(m => h("li", { class: "lesson-row" }, h("span", { class: "lesson-icon material" }, icon("book")),
          h("div", { class: "lesson-name" }, h("strong", {}, m.title), h("small", { class: "muted" }, `${m.files.length} file${m.files.length === 1 ? "" : "s"}`)),
          m.files.map(f => h("a", { class: "file-chip", href: api.fileUrl(m.id, f.id), target: "_blank", rel: "noopener" }, icon("file"), f.name)))))
        : h("p", { class: "topic-empty" }, "No lessons yet. Add one, then build it in Studio."));
  }

  function classwork() {
    const chapters = course.chapters.map(ch => {
      const topics = ch.topics.map(topicBlock).filter(Boolean);
      if (!teacher && !topics.length) return null;
      return h("section", { class: "card chapter" },
        h("div", { class: "chapter-head" },
          h("h3", {}, ch.title),
          teacher ? h("div", { class: "row-actions" },
            h("button", { class: "btn sm", onclick: act(async () => {
              const title = await askTitle("New topic", "", "e.g. Coin change"); if (title) { await api.addTopic(ch.id, title); await reload(); }
            }) }, icon("plus"), "Topic"),
            h("button", { class: "icon-btn sm", title: "Rename chapter", onclick: act(async () => {
              const title = await askTitle("Rename chapter", ch.title); if (title) { await api.renameChapter(ch.id, title); await reload(); }
            }) }, icon("edit")),
            h("button", { class: "icon-btn sm", title: "Delete chapter", onclick: act(async () => {
              if (!await confirmDialog(`Delete “${ch.title}”?`, "Its topics and lessons are deleted too, with their material, scripts, audio and attendance. This can't be undone.", "Delete", "danger")) return;
              await api.deleteChapter(ch.id); await reload();
            }) }, icon("trash"))) : null),
        topics.length ? topics : h("p", { class: "topic-empty" }, teacher ? "Add a topic to this chapter." : "Nothing here yet."));
    }).filter(Boolean);
    return h("div", { class: "classwork" },
      teacher ? h("div", { class: "classwork-bar" },
        h("p", { class: "muted" }, "Chapters hold topics; each topic holds its lessons. Build a lesson in Studio, then share it."),
        h("button", { class: "btn primary", onclick: act(async () => {
          const title = await askTitle("New chapter", "", "e.g. Dynamic programming"); if (title) { await api.addChapter(courseId, title); await reload(); }
        }) }, icon("plus"), "Chapter")) : null,
      chapters.length ? chapters : h("div", { class: "card empty" }, h("div", { class: "empty-icon" }, icon("layers")),
        h("h3", {}, teacher ? "Plan the course" : "No lessons yet"),
        h("p", {}, teacher ? "Start with a chapter, add its topics, and create a lesson in each topic." : "Lessons appear here once your teacher shares them.")));
  }

  // ---------- people ----------
  function people() {
    return h("div", { class: "people" },
      h("section", { class: "card" }, h("div", { class: "card-header" }, h("h3", {}, "Teacher")),
        h("ul", { class: "people-list" }, h("li", {}, h("span", { class: "lecture-avatar", style: avatarTint(course.teacher.name) }, initials(course.teacher.name)),
          h("strong", {}, course.teacher.name)))),
      h("section", { class: "card" }, h("div", { class: "card-header" }, h("h3", {}, "Students"), h("span", { class: "sub" }, course.students.length)),
        course.students.length ? h("ul", { class: "people-list" }, course.students.map(s => h("li", {},
          h("span", { class: "lecture-avatar", style: avatarTint(s.name) }, initials(s.name)),
          h("strong", {}, s.name), teacher ? h("small", { class: "muted" }, s.email) : null,
          teacher ? h("small", { class: "muted right" }, `Joined ${formatDate(s.joined_at)}`) : null)))
          : h("p", { class: "topic-empty" }, teacher ? `No students yet. Share the class code ${course.code}.` : "No classmates yet.")));
  }

  // ---------- dialogs ----------
  // Deleting can't be undone, so the teacher types the course's name to confirm.
  async function deleteCourse() {
    const typed = h("input", { class: "input", placeholder: course.subject, autocomplete: "off" });
    const ok = await modal({
      title: "Delete this course?",
      text: `This removes ${course.subject}${course.year ? ` (${course.year})` : ""} for you and its ${course.students.length} student${course.students.length === 1 ? "" : "s"}: `
        + "chapters, topics, lessons with their material, scripts and audio, shared material, attendance, doubts and "
        + "feedback. It can't be undone.",
      body: h("label", { class: "field" }, h("span", {}, `Type “${course.subject}” to confirm`), typed),
      actions: [{ label: "Cancel", value: null }, { label: "Delete course", kind: "danger", value: () =>
        typed.value.trim().toLowerCase() === course.subject.trim().toLowerCase() ? true : (typed.classList.add("invalid"), undefined) }],
    });
    if (!ok) return;
    try {
      await api.deleteCourse(courseId);
      toast(`${course.subject} was deleted.`, "success");
      await ctx.refreshCourses?.();
      location.hash = "#/";
    } catch (e) { toast(e.message, "error", 6000); }
  }

  async function askTitle(title, value = "", placeholder = "") {
    const input = h("input", { class: "input", value, placeholder });
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") e.target.closest(".modal").querySelector(".btn.primary").click(); });
    return modal({ title, body: input, actions: [{ label: "Cancel", value: null },
      { label: "Save", kind: "primary", value: () => input.value.trim() || (input.classList.add("invalid"), undefined) }] });
  }

  async function newLesson(topic, kind) {
    const defaults = await api.personaTemplate().catch(() => ({}));
    const prereq = kind === "prerequisite";
    const title = h("input", { class: "input", value: prereq ? `Before ${topic.title}` : topic.title });
    const duration = h("input", { class: "input", type: "number", min: 5, max: 120, step: 5, value: prereq ? 10 : defaults.duration_min || 15 });
    const speaking = h("input", { class: "input", type: "number", min: 1, max: 120, value: prereq ? 4 : defaults.speaking_min || 5 });
    const language = languageSelect(defaults.language, defaults.languages);
    const made = await modal({
      title: prereq ? "New prerequisite lesson" : "New lesson",
      text: prereq ? `A short lesson on what students should know before “${topic.title}”. Upload material for it in Studio.`
        : `A lesson in “${topic.title}”. Next, upload its material and describe the teacher in Studio.`,
      body: [h("label", { class: "field" }, h("span", {}, "Lesson title"), title),
        h("div", { class: "field-row" },
          h("label", { class: "field" }, h("span", {}, "Total time (min)"), duration),
          h("label", { class: "field" }, h("span", {}, "Speaking time (min)"), speaking)),
        h("label", { class: "field" }, h("span", {}, "Teaching language"), language)],
      actions: [{ label: "Cancel", value: null }, { label: "Create and open Studio", kind: "primary", value: () => {
        if (!title.value.trim()) return (title.classList.add("invalid"), undefined);
        const d = +duration.value, sp = +speaking.value;
        if (!(d >= 5 && d <= 120)) return (duration.classList.add("invalid"), undefined);
        if (!(sp >= 1 && sp <= d)) return (speaking.classList.add("invalid"), undefined);
        return { kind, title: title.value.trim(), duration_min: d, speaking_min: sp, language: language.value };
      } }],
    });
    if (!made) return;
    try {
      const r = await api.addLesson(topic.id, made);
      location.hash = `#/lecture/${encodeURIComponent(r.lecture_id)}/studio`;
    } catch (e) { toast(e.message, "error", 6000); }
  }

  async function shareLesson(l) {
    const note = h("textarea", { class: "textarea", rows: 3, placeholder: "A note for the class (optional)" });
    const due = h("input", { class: "input", type: "datetime-local" });
    const skip = h("input", { type: "checkbox", checked: true });
    const ok = await modal({
      title: `Share “${l.title}”`, text: "Students get a locked copy of the approved script. If you change it later, share the update.",
      body: [h("label", { class: "field" }, h("span", {}, "Note"), note), h("label", { class: "field" }, h("span", {}, "Watch by (optional)"), due),
        h("label", { class: "check-field" }, skip, h("span", {}, "Students may skip ahead (they still need every line heard to be present)"))],
      actions: [{ label: "Cancel", value: null }, { label: "Share", kind: "primary", value: true }],
    });
    if (!ok) return;
    try { await api.share(l.id, note.value, due.value || null, skip.checked); toast("Shared with the class.", "success"); await reload(); }
    catch (e) { toast(e.message, "error", 6000); }
  }

  async function addMaterial(topicId = null) {
    const title = h("input", { class: "input", placeholder: "e.g. Notes for chapter 3" });
    const body = h("textarea", { class: "textarea", rows: 3, placeholder: "Anything the class should know (optional)" });
    const topics = course.chapters.flatMap(ch => ch.topics.map(t => [t.id, `${ch.title} › ${t.title}`]));
    const topicSel = h("select", { class: "select" }, h("option", { value: "" }, "No topic"),
      topics.map(([id, label]) => h("option", { value: id, selected: id === topicId }, label)));
    const files = h("input", { type: "file", multiple: true, class: "input file-input" });
    const due = h("input", { class: "input", type: "datetime-local" });
    const ok = await modal({
      title: "Share material", text: "Notes, slides or a reading for the class.",
      body: [h("label", { class: "field" }, h("span", {}, "Title"), title), h("label", { class: "field" }, h("span", {}, "Message"), body),
        h("div", { class: "field-row" }, h("label", { class: "field" }, h("span", {}, "Topic"), topicSel), h("label", { class: "field" }, h("span", {}, "Due (optional)"), due)),
        h("label", { class: "field" }, h("span", {}, "Files"), files, h("small", {}, "Up to 25 MB each"))],
      actions: [{ label: "Cancel", value: null }, { label: "Post", kind: "primary", value: () => title.value.trim() ? true : (title.classList.add("invalid"), undefined) }],
    });
    if (!ok) return;
    try {
      await api.addMaterial(courseId, { title: title.value.trim(), body: body.value, topicId: topicSel.value, dueAt: due.value, files: [...files.files] });
      toast("Posted.", "success");
      await reload();
    } catch (e) { toast(e.message, "error", 6000); }
  }

  // Where the lesson is weak, section by section; a section can be rewritten from what students said about it.
  async function showInsights(post) {
    let data;
    try { data = await api.insights(post.id); } catch (e) { return toast(e.message, "error"); }
    const detail = h("div", { class: "insight-detail" });
    const most = Math.max(1, ...data.sections.map(s => s.doubt_count + 2 * s.open_flags + s.stopped));
    async function regenerate(sec) {
      const lines = [...sec.flags.filter(f => !f.resolved_at).map(f => `- Marked confusing at: "${f.line_text}"${f.comment ? ` (${f.comment})` : ""}`),
        ...sec.doubts.map(d => `- Doubt: ${d.question}`)];
      if (!await confirmDialog(`Rewrite “${sec.title}”?`, "Eris rewrites just this section from what students said. The lesson becomes a draft: "
        + "review it in Studio and approve it to give the class a new version.", "Rewrite section")) return;
      detail.replaceChildren(h("div", { class: "insight-wait" }, h("div", { class: "spinner" }), "Rewriting the section… this takes about a minute."));
      try {
        await api.regenerateSection(data.post.lecture_id, { section: sec.title, feedback: lines.join("\n") });
        for (const f of sec.flags.filter(f => !f.resolved_at)) await api.resolveFeedback(f.id).catch(() => {});
        document.querySelector("#modal-root").innerHTML = "";
        toast("Section rewritten. Review it and approve to give the class the new version.", "success", 7000);
        location.hash = `#/lecture/${encodeURIComponent(data.post.lecture_id)}/studio`;
      } catch (e) { detail.replaceChildren(h("div", { class: "callout error" }, icon("alert"), e.message)); }
    }
    const open = (sec) => detail.replaceChildren(...[
      h("div", { class: "insight-head" }, h("h4", {}, sec.title),
        h("button", { class: "btn sm primary", onclick: () => regenerate(sec) }, icon("sparkle"), "Rewrite this section")),
      sec.flags.length ? [h("div", { class: "insight-label" }, "Marked confusing"), ...sec.flags.map(f => h("div", { class: `doubt ${f.resolved_at ? "resolved" : ""}` },
        h("p", { class: "q" }, `“${f.line_text || "(this part)"}”`), f.comment ? h("p", { class: "a" }, f.comment) : null,
        h("small", { class: "muted" }, [f.student, formatDate(f.created_at), f.resolved_at ? "resolved" : ""].filter(Boolean).join(" · "))))] : null,
      sec.doubts.length ? [h("div", { class: "insight-label" }, "Doubts asked here"), ...sec.doubts.map(d => h("div", { class: "doubt" },
        h("p", { class: "q" }, d.question), safetyTags(d.flags), h("small", { class: "muted" }, [d.student, formatDate(d.created_at), d.passed ? "passed to you" : ""].filter(Boolean).join(" · "))))] : null,
      !sec.flags.length && !sec.doubts.length ? h("p", { class: "muted" }, "No doubts or flags in this section yet.") : null].flat().filter(Boolean));
    await modal({
      wide: true, title: `Insights · ${post.title}`,
      text: `Version ${data.post.version}. Each section: doubts asked, parts marked confusing, and students who stopped there without finishing.`,
      body: [h("table", { class: "att-table insight-table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Section"), h("th", {}, "Doubts"), h("th", {}, "Confusing"), h("th", {}, "Stopped here"), h("th", {}, ""))),
        h("tbody", {}, data.sections.map(sec => h("tr", { class: "insight-row", onclick: () => open(sec) },
          h("td", {}, h("strong", {}, sec.title), h("div", { class: "heat" }, h("i", { style: `width:${100 * (sec.doubt_count + 2 * sec.open_flags + sec.stopped) / most}%` }))),
          h("td", {}, sec.doubt_count ? `${sec.doubt_count} (${sec.students_asking} student${sec.students_asking === 1 ? "" : "s"})` : "–"),
          h("td", {}, sec.open_flags ? h("span", { class: "att-tag started" }, sec.open_flags) : "–"),
          h("td", {}, sec.stopped || "–"),
          h("td", {}, h("button", { class: "btn sm ghost" }, "Open")))))), detail],
      actions: [{ label: "Close", kind: "primary", value: true }],
    });
  }

  async function showAttendance(post) {
    let data;
    try { data = await api.attendance(post.id); } catch (e) { return toast(e.message, "error"); }
    const LABEL = { present: "Present", started: "Watching", not_started: "Not started" };
    const detail = h("div", { class: "doubt-detail" });
    const openDoubts = async (s) => {
      detail.replaceChildren(h("div", { class: "spinner" }));
      const list = await api.postDoubts(post.id, s.id).catch(() => []);
      detail.replaceChildren(h("h4", {}, `${s.name}'s doubts`),
        ...(list.length ? list.map(d => h("div", { class: "doubt" }, h("p", { class: "q" }, d.question), safetyTags(d.flags),
          h("p", { class: "a" }, d.answer || "(no answer)"),
          h("small", { class: "muted" }, [d.section, formatDate(d.created_at), d.passed ? "passed to you" : ""].filter(Boolean).join(" · "))))
          : [h("p", { class: "muted" }, "No doubts asked.")]));
    };
    const present = data.students.filter(s => s.status === "present").length;
    await modal({
      wide: true, title: `Attendance · ${post.title}`,
      text: `${present} of ${data.students.length} present. A student is present once they've heard every line of the lesson.${data.post.due_at ? ` Due ${formatDate(data.post.due_at)}.` : ""}`,
      body: [data.students.length ? h("table", { class: "att-table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Student"), h("th", {}, "Status"), h("th", {}, "Heard"), h("th", {}, "Last active"), h("th", {}, "Doubts"))),
        h("tbody", {}, data.students.map(s => h("tr", {},
          h("td", {}, h("strong", {}, s.name), h("small", { class: "muted" }, s.email)),
          h("td", {}, h("span", { class: `att-tag ${s.status === "present" ? "present" : s.status === "started" ? "started" : ""}` }, LABEL[s.status])),
          h("td", {}, h("div", { class: "progress-line sm" }, h("i", { style: `width:${s.percent}%` })), h("small", {}, `${s.percent}%`)),
          h("td", {}, h("small", {}, s.completed_at ? `Done ${formatDate(s.completed_at)}` : formatDate(s.last_activity) || "–")),
          h("td", {}, s.doubts ? h("button", { class: "btn sm ghost", onclick: () => openDoubts(s) }, icon("chat"), String(s.doubts),
            s.passed ? h("span", { class: "passed-dot", title: `${s.passed} passed to you` }) : null,
            s.flagged ? h("span", { class: "safety-count", title: `${s.flagged} flagged by the safety check` }, icon("alert"), s.flagged) : null)
            : h("small", { class: "muted" }, "0"))))))
        : h("p", { class: "muted" }, `No students yet. Share the class code ${course.code}.`), detail],
      actions: [{ label: "Close", kind: "primary", value: true }],
    });
  }

  function render() {
    const body = tab === "stream" ? stream() : tab === "classwork" ? classwork() : people();
    main.replaceChildren(h("div", { class: "page course-page" }, header(),
      h("nav", { class: "tabs course-tabs" }, tabLink("stream", "Stream", "chat"), tabLink("classwork", "Classwork", "layers"), tabLink("people", "People", "user")),
      body));
  }
  render();
  return null;
}
