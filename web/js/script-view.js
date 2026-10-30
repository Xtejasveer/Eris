// Renders parsed script segments as a readable document (Studio preview).

import { h, icon } from "./ui.js";
import { highlightCode } from "./highlight.js";

export function scriptStats(segments) {
  const count = (n) => segments.filter(s => s.name === n).length;
  const words = segments.filter(s => s.kind === "say").reduce((n, s) => n + s.text.split(/\s+/).length, 0);
  return {
    sections: count("SECTION"), words, files: new Set(segments.filter(s => s.name === "WRITE_CODE").map(s => s.args.file)).size,
    runs: count("RUN"), breaks: count("DOUBT_CHECK"), notes: count("NOTE") + count("NOTE_TITLE"),
  };
}

// `code` in narration becomes inline code.
export function inlineCode(text) {
  return text.split(/(`[^`]+`)/).map(p => p.startsWith("`") && p.endsWith("`") && p.length > 2 ? h("code", { class: "ic" }, p.slice(1, -1)) : p);
}

function chip(ic, text, kind = "") {
  return h("div", { class: `doc-chip ${kind}` }, icon(ic), h("span", {}, text));
}

function codeBlock(file, code) {
  const lines = highlightCode(code);
  return h("figure", { class: "doc-code" },
    h("figcaption", {}, icon("code"), file),
    h("pre", {}, lines.map((l, i) => h("div", { class: "ln" }, h("span", { class: "no" }, i + 1), h("span", { html: l || " " })))));
}

export function renderScriptDoc(segments, teacher = "Teacher", { lectureId = null } = {}) {
  const doc = h("article", { class: "script-doc" });
  let section = null;
  const target = () => section || doc;
  let n = 0;
  for (const seg of segments) {
    if (seg.kind === "say") {
      target().append(h("div", { class: "doc-say" },
        h("span", { class: "doc-speaker" }, icon("volume")), h("p", {}, inlineCode(seg.text))));
      continue;
    }
    const a = seg.args || {};
    switch (seg.name) {
      case "SECTION":
        n += 1;
        section = h("section", { class: "doc-section", id: `doc-sec-${n}` },
          h("h2", {}, h("span", { class: "doc-sec-num" }, String(n)), a.title));
        doc.append(section);
        break;
      case "NOTE_TITLE":
        target().append(h("div", { class: "doc-note title" }, h("span", { class: "doc-note-tag" }, icon("book"), "Notebook"), h("h4", {}, a.text)));
        break;
      case "NOTE":
      case "WRITE":
        target().append(h("div", { class: "doc-note" },
          h("span", { class: "doc-note-tag" }, icon("book"), "Notebook"),
          h("div", { class: "doc-note-lines" }, (a.text || "").split("\n").map(l => h("div", {}, l || " ")))));
        break;
      case "SKETCH_ROW":
        target().append(h("div", { class: "doc-note" },
          h("span", { class: "doc-note-tag" }, icon("pen"), "Notebook sketch"),
          h("div", { class: "doc-note-lines" }, h("div", {}, (a.parts || []).map(p =>
            p.kind === "arrow" ? (p.text ? `→ ${p.text} →` : "→") : p.kind === "tick" ? "✓" : p.kind === "cross" ? "✗"
              : p.kind === "icon" ? `(${p.text})` : p.kind === "text" ? p.text : `[${p.text}]`).join("  ")))));
        break;
      case "NOTE_HIGHLIGHT":
        target().append(chip("edit", `Highlight in notebook: “${a.text}”`, "marker"));
        break;
      case "WRITE_CODE":
        target().append(codeBlock(a.file, a.code || ""));
        break;
      case "HIGHLIGHT":
        target().append(chip("eye", `Highlight ${a.file} line ${a.lines}${a.text ? ` · ${a.text}` : ""}`, "marker"));
        break;
      case "RUN":
        target().append(h("div", { class: "doc-run" },
          h("div", { class: "doc-run-cmd" }, icon("terminal"), h("code", {}, `$ ${a.cmd}`)),
          seg.expected_output != null ? h("pre", {}, seg.expected_output.trimEnd() || "(no output)") : null));
        break;
      case "READ_OUTPUT":
        target().append(chip("terminal", "Read the output aloud"));
        break;
      case "SLIDE":
        target().append(chip("slides", `Show slide ${a.n}`));
        break;
      case "SLIDE_CIRCLE":
        target().append(chip("pen", a.part ? `Circle “${a.part}” on slide ${a.n}` : `Circle the picture on slide ${a.n}`, "marker"));
        break;
      case "SLIDE_HIGHLIGHT":
        target().append(chip("slides", `Highlight on slide ${a.n}: “${a.text}”`, "marker"));
        break;
      case "LOOK_BACK":
        target().append(chip("book", `Look back in notebook: “${a.text}”`, "marker"));
        break;
      case "OPEN_FILE":
        target().append(chip("file", `Open ${a.file} again`));
        break;
      case "NEW_PAGE":
        target().append(h("div", { class: "doc-note title" }, h("span", { class: "doc-note-tag" }, icon("book"), "New page"), h("h4", {}, a.title)));
        break;
      case "FLOW":
        target().append(h("div", { class: "doc-run" },
          h("div", { class: "doc-run-cmd" }, icon("layers"), h("strong", {}, `Diagram: ${a.title}`),
            a.from ? h("span", { class: "muted" }, `from ${a.from}`) : null),
          h("pre", {}, (a.blocks || []).map(b => {
            const outs = (a.edges || []).filter(e => e.from === b.id && e.label).map(e => `${e.label} → ${e.to}`);
            return `${b.kind === "question" ? "◇" : "▭"} ${b.label}${outs.length ? `   (${outs.join(", ")})` : ""}`;
          }).join("\n  ↓\n"))));
        break;
      case "FLOW_NEXT":
        target().append(chip("layers", `Draw the next block: “${a.label || a.block}”`));
        break;
      case "FLOW_HIGHLIGHT":
        target().append(chip("layers", `Point at block “${a.block}” in ${a.id}`, "marker"));
        break;
      case "OPEN_FLOW":
        target().append(chip("layers", `Show diagram ${a.id} again`));
        break;
      case "VISUAL": {
        const url = lectureId && a.key ? `/api/lectures/${encodeURIComponent(lectureId)}/visuals/${encodeURIComponent(a.key)}` : null;
        target().append(h("div", { class: "doc-run" },
          h("div", { class: "doc-run-cmd" }, icon("sparkle"), h("strong", {}, `Visual: ${a.title}`),
            url ? h("a", { href: url, target: "_blank", rel: "noopener" }, "Preview") : h("span", { class: "muted" }, "(built on approve)")),
          h("pre", {}, `${a.brief || ""}\ncontrols: ${(a.controls || []).map(c => c.name + " (" + c.type + ")").join(", ")}`)));
        break;
      }
      case "VISUAL_SET":
        target().append(chip("sparkle", `Visual ${a.id}: ${a.value === undefined ? `press ${a.control}` : `set ${a.control} to ${a.value}`}`, "marker"));
        break;
      case "OPEN_VISUAL":
        target().append(chip("sparkle", `Show visual ${a.id} again`));
        break;
      case "PAUSE":
        target().append(chip("clock", `Pause ${a.s}s`));
        break;
      case "DOUBT_CHECK":
        target().append(h("div", { class: "doc-break" }, icon("question"), h("span", {}, "Question break: students can ask doubts")));
        break;
      default:
        target().append(chip("info", seg.name));
    }
    if (a.while_speaking && seg.name !== "SECTION") {
      const el = target().lastChild;
      el.classList.add("ws");
      el.append(h("span", { class: "ws-tag", title: "Runs while the next sentence is spoken" }, icon("volume"), "while speaking"));
    }
  }
  if (!segments.length) doc.append(h("p", { class: "muted" }, "Nothing to show."));
  doc.dataset.teacher = teacher;
  return doc;
}
