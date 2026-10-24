// A lesson's script versions: every approved script is kept, numbered. The class plays the shared one; the teacher
// can read any version and give the class a different one (e.g. roll back a new script).

import { api } from "./api.js";
import { h, icon, toast, modal, formatDate } from "./ui.js";
import { renderScriptDoc } from "./script-view.js";

export async function showVersions(lessonId, { onChange } = {}) {
  let data;
  try { data = await api.versions(lessonId); } catch (e) { return toast(e.message, "error"); }
  const list = h("ul", { class: "version-list" });
  const reader = h("div", { class: "version-reader" });

  async function read(v) {
    reader.replaceChildren(h("div", { class: "spinner" }));
    try {
      const s = await api.versionScript(v.id);
      reader.replaceChildren(h("div", { class: "version-reader-head" }, h("strong", {}, `Version ${v.number}`),
        h("button", { class: "btn sm ghost", onclick: () => reader.replaceChildren() }, "Close")),
        renderScriptDoc(s.segments, s.teacher, { lectureId: s.lecture_id }));
      reader.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) { reader.replaceChildren(h("p", { class: "muted" }, e.message)); }
  }

  async function share(v) {
    try {
      await api.shareVersion(lessonId, v.id);
      data.shared_version_id = v.id;
      toast(`The class now gets version ${v.number}.`, "success");
      render(); onChange?.();
    } catch (e) { toast(e.message, "error", 6000); }
  }

  function render() {
    list.replaceChildren(...data.versions.map(v => {
      const shared = v.id === data.shared_version_id;
      return h("li", { class: `version-row ${shared ? "shared" : ""}` },
        h("span", { class: "version-num" }, `v${v.number}`),
        h("div", { class: "version-meta" },
          h("strong", {}, `Approved ${formatDate(v.created_at)}`),
          h("small", { class: "muted" }, `${v.say_count} spoken lines · ${v.students} student${v.students === 1 ? "" : "s"} played it`)),
        shared ? h("span", { class: "att-tag present" }, icon("check"), "Class has this") : null,
        h("button", { class: "btn sm ghost", onclick: () => read(v) }, icon("eye"), "Read"),
        !shared && data.post_id ? h("button", { class: "btn sm", onclick: () => share(v) }, icon("send"), "Give the class this") : null);
    }));
    if (!data.versions.length) list.append(h("li", { class: "muted" }, "No versions yet. Approve the script in Studio to make version 1."));
  }
  render();
  await modal({
    wide: true, title: `Script versions · ${data.lesson.title}`,
    text: data.post_id ? "Every approved script is kept. Approving a new script gives it to the class straight away; attendance already taken stays."
      : "Every approved script is kept. Share the lesson from Classwork to give the class the newest one.",
    body: [list, reader],
    actions: [{ label: "Close", kind: "primary", value: true }],
  });
}
