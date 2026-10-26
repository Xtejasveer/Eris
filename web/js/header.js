// The header shared by a lecture's Studio and Classroom pages.

import { h, icon, badge, kindTag } from "./ui.js";

// course: where the lecture sits (a lesson in a course's topic), or null for a lecture outside every course.
export function lectureHeader(lectureId, active, status, course = null, ...extra) {
  const tab = (key, label, ic) =>
    h("a", { class: `tab ${active === key ? "active" : ""}`, href: `#/lecture/${encodeURIComponent(lectureId)}/${key}` },
      icon(ic), label);
  const statusEl = h("span", { class: "header-status" }, badge(status));
  const el = h("header", { class: "page-header" },
    h("div", { class: "page-title" },
      course ? h("a", { class: "crumb", href: `#/course/${course.course_id}` },
        `${course.subject}${course.year ? ` · ${course.year}` : ""} › ${course.topic_title}`) : h("span", { class: "crumb" }, "Lectures"),
      h("h1", {}, course ? course.lesson_title : lectureId)),
    course ? kindTag(course.kind, course.topic_title) : null,
    statusEl,
    h("div", { class: "spacer" }),
    ...extra,
    h("nav", { class: "tabs" }, tab("studio", "Studio", "edit"), tab("class", "Classroom", "class")));
  el.setStatus = (s) => statusEl.replaceChildren(badge(s));
  return el;
}
