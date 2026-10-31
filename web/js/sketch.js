// Sketch rows in the notebook ([SKETCH_ROW]): a few simple parts drawn left to right with the pen, like a teacher
// sketching on the board. Boxes, arrows and marks are stroked in; words are written in by hand. The rows of one
// sketch are numbered 1, 2, 3. The parts come from the script (eris/visuals/sketch.py); this code lays them out.

import { h } from "./ui.js";

const NS = "http://www.w3.org/2000/svg";
const STROKE_MS = 420;  // drawing one box, arrow or mark
const WORD_MS = 26;     // per character, as the notebook's handwriting

function svg(tag, attrs = {}, parent = null) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}

// A hand-drawn rectangle: corners a little off, and the last side overshoots its start, like a quick pen stroke.
function roughRect(w, hgt, seed) {
  let s = seed * 9301 + 49297;
  const j = (a) => { s = (s * 9301 + 49297) % 233280; return (s / 233280 - 0.5) * a; };
  const p = [[2 + j(2), 2 + j(2)], [w - 2 + j(2), 2 + j(2)], [w - 2 + j(2), hgt - 2 + j(2)], [2 + j(2), hgt - 2 + j(2)]];
  const end = [p[0][0] + 6, p[0][1] + j(1.5)];
  return `M${p[0]} L${p[1]} L${p[2]} L${p[3]} L${p[0]} L${end}`.replace(/(\d+\.\d)\d+/g, "$1");
}

// Stroke a path in over `ms` (instantly when there is no pen to wait for).
async function stroke(path, ms, ctl) {
  const len = path.getTotalLength?.() || 0;
  if (!ctl || !len) return;
  path.style.strokeDasharray = `${len}`;
  path.style.strokeDashoffset = `${len}`;
  path.getBoundingClientRect();
  path.style.transition = `stroke-dashoffset ${ms}ms ease-out`;
  path.style.strokeDashoffset = "0";
  await ctl.tick(ms);
}

async function write(el, text, ctl) {
  if (!ctl) { el.textContent = text; return; }
  let shown = "";
  for (const ch of text) {
    shown += ch;
    el.textContent = shown;
    if (ch !== " ") await ctl.tick(ctl.charMs ?? WORD_MS);
  }
}

const ICONS = {  // small line drawings on a 56 x 44 box
  stack: ["M8 14h28v22H8z", "M14 9h28v22", "M20 4h28v22"],
  network: ["M12 10L44 34M44 10L12 34M12 10h32M12 34h32", "M12 10m-5 0a5 5 0 1 0 10 0a5 5 0 1 0-10 0",
    "M44 10m-5 0a5 5 0 1 0 10 0a5 5 0 1 0-10 0", "M12 34m-5 0a5 5 0 1 0 10 0a5 5 0 1 0-10 0",
    "M44 34m-5 0a5 5 0 1 0 10 0a5 5 0 1 0-10 0"],
  gear: ["M28 22m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0",
    "M28 6v6M28 32v6M12 22h6M38 22h6M17 11l4 4M35 29l4 4M39 11l-4 4M21 29l-4 4"],
  person: ["M28 13m-7 0a7 7 0 1 0 14 0a7 7 0 1 0-14 0", "M14 41c0-9 6-15 14-15s14 6 14 15"],
  cycle: ["M44 22a16 16 0 1 1-5-11.5", "M40 4l-1 7-7-1"],
  bulb: ["M20 30c-5-4-7-9-5-15a13 13 0 0 1 26 0c2 6 0 11-5 15z", "M22 35h12M24 40h8"],
};

async function drawPart(parent, item, k, ctl) {
  const kind = item.kind;
  if (kind === "box" || kind === "result" || kind === "good") {
    const t = h("span", { class: "sk-t" });
    const el = h("span", { class: `sk-box sk-${kind}` }, t);
    t.textContent = item.text;  // laid out at its full size first, so the frame fits the words
    parent.append(el);
    const w = el.offsetWidth, hgt = el.offsetHeight;
    const frame = svg("svg", { class: "sk-frame", viewBox: `0 0 ${w} ${hgt}`, preserveAspectRatio: "none" });
    const path = svg("path", { d: roughRect(w, hgt, k + item.text.length) }, frame);
    el.prepend(frame);
    if (ctl) t.textContent = "";
    el.classList.add("drawing");
    await stroke(path, STROKE_MS, ctl);
    el.classList.remove("drawing");
    await write(t, item.text, ctl);
  } else if (kind === "text") {
    const t = h("span", { class: "sk-t sk-text" });
    parent.append(t);
    await write(t, item.text, ctl);
  } else if (kind === "arrow") {
    const w = Math.max(64, Math.min(150, item.text.length * 11 + 30));
    const el = h("span", { class: "sk-arrow", style: `width:${w}px` });
    const label = item.text ? h("span", { class: "sk-t sk-arrow-t" }) : null;
    if (label) el.append(label);
    const pic = svg("svg", { viewBox: `0 0 ${w} 22`, style: `width:${w}px;height:22px` }, el);
    const line = svg("path", { d: `M3 11.5 Q${w / 2} ${9 + (k % 2) * 3} ${w - 5} 11` }, pic);
    const head = svg("path", { d: `M${w - 15} 4 L${w - 4} 11 L${w - 15} 18` }, pic);
    parent.append(el);
    if (ctl) head.style.opacity = "0";
    await stroke(line, STROKE_MS * 0.7, ctl);
    head.style.opacity = "";
    await stroke(head, 140, ctl);
    if (label) await write(label, item.text, ctl);
  } else if (kind === "tick" || kind === "cross") {
    const el = h("span", { class: `sk-mark sk-${kind}` });
    const pic = svg("svg", { viewBox: "0 0 30 30", style: "width:30px;height:30px" }, el);
    const paths = kind === "tick" ? ["M5 16 L12 23 L26 6"] : ["M7 7 L23 23", "M23 7 L7 23"];
    parent.append(el);
    for (const d of paths) await stroke(svg("path", { d }, pic), STROKE_MS * 0.6, ctl);
  } else if (kind === "icon") {
    const el = h("span", { class: "sk-icon", title: item.text });
    const pic = svg("svg", { viewBox: "0 0 56 44", style: "width:56px;height:44px" }, el);
    parent.append(el);
    for (const d of ICONS[item.text] || ICONS.bulb) await stroke(svg("path", { d }, pic), STROKE_MS * 0.5, ctl);
  }
}

// Draw one row into `row` (already on the page): its number, then each part in turn.
export async function drawSketchRow(row, items, number, ctl) {
  const num = h("span", { class: "sk-num" }, String(number));
  const parts = h("div", { class: "sk-parts" });
  row.append(num, parts);
  for (const [k, item] of items.entries()) await drawPart(parts, item, k, ctl);
}
