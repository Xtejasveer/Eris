// The header shared by a lecture's Studio and Classroom pages.

import { h, icon, badge } from "./ui.js";

export function lectureHeader(lectureId, active, status, ...extra) {
  const tab = (key, label, ic) =>
    h("a", { class: `tab ${active === key ? "active" : ""}`, href: `#/lecture/${encodeURIComponent(lectureId)}/${key}` },
      icon(ic), label);
  const statusEl = h("span", { class: "header-status" }, badge(status));
  const el = h("header", { class: "page-header" },
    h("div", { class: "page-title" },
      h("span", { class: "crumb" }, "Lectures"),
      h("h1", {}, lectureId)),
    statusEl,
    h("div", { class: "spacer" }),
    ...extra,
    h("nav", { class: "tabs" }, tab("studio", "Studio", "edit"), tab("class", "Classroom", "class")));
  el.setStatus = (s) => statusEl.replaceChildren(badge(s));
  return el;
}
