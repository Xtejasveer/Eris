// Checkpoints: the only places a student can jump to in a lesson, following what is taught: each topic (a section of
// the script) and the sub-topics inside it. Worked out from the script's structure alone, so they suit any lesson in
// any subject or language:
//   1. A spoken line is a safe point when nothing on screen is half-done there: it isn't spoken over an action,
//      no program output is waiting to be read, no graph is between its slider moves, no diagram is part-built.
//   2. Every section is a topic; its checkpoint is its first safe line.
//   3. A sub-topic starts where something new and named is introduced: a notebook heading or page, a new code file,
//      a graph or a diagram. Its checkpoint is the first safe line from there, named after it.
//   4. A sub-topic closer than MIN_GAP_S to the checkpoint before it or to the next topic (a summary at a topic's end),
//      or named like its topic, is merged into what is around it.
//   5. A stretch longer than MAX_GAP_S with no sub-topic is split at the safe line nearest its middle ("part 2").
export const MAX_GAP_S = 75;
export const MIN_GAP_S = 20;
const WORDS_PER_S = 2.5;
const CHARS_PER_S = 7;   // scripts written without spaces between words (Chinese, Japanese, Thai)
const NEW_STEP = new Set(["SLIDE", "NEW_PAGE", "NOTE_TITLE", "WRITE_CODE", "OPEN_FILE", "VISUAL", "FLOW"]);

// Seconds a spoken line takes: its clip's real length when known (durations[i]), else an estimate.
export function lineSeconds(seg, i, durations = {}) {
  if (seg.kind !== "say") return 0;
  if (durations[i]) return durations[i];
  const text = seg.text.trim();
  const words = text.split(/\s+/).length;
  const spaced = words > 1 || text.length < 12;
  return Math.max(1, spaced ? words / WORDS_PER_S : text.length / CHARS_PER_S);
}

// Which lines are safe: walks the script once, tracking what is still in progress.
function safeLines(segments) {
  const safe = new Set();
  let outputPending = false, flowLeft = new Map(), sliding = null;
  segments.forEach((seg, i) => {
    const a = seg.args || {};
    if (seg.kind === "action") {
      if (seg.name === "RUN") outputPending = true;
      if (seg.name === "READ_OUTPUT") outputPending = false;
      if (seg.name === "FLOW") flowLeft.set(a.id, (a.blocks || []).length);
      if (seg.name === "FLOW_NEXT" && flowLeft.has(a.id)) {
        const left = flowLeft.get(a.id) - 1;
        if (left <= 0) flowLeft.delete(a.id); else flowLeft.set(a.id, left);
      }
      if (seg.name === "VISUAL_SET") sliding = a.id;
      else if (seg.name !== "VISUAL_SET") sliding = null;
      if (seg.name === "SECTION") { outputPending = false; flowLeft = new Map(); sliding = null; }
      return;
    }
    const prev = segments[i - 1];
    const overAction = prev?.kind === "action" && prev.args?.while_speaking;
    // A line between two slider moves of the same graph is mid-demonstration.
    const nextAction = segments.slice(i + 1).find(s => s.kind === "action");
    const midSlide = sliding && nextAction?.name === "VISUAL_SET" && nextAction.args?.id === sliding;
    if (!overAction && !outputPending && !flowLeft.size && !midSlide) safe.add(i);
  });
  return safe;
}

const NAMED = { NOTE_TITLE: (a) => a.text, NEW_PAGE: (a) => a.title, WRITE_CODE: (a) => a.file, VISUAL: (a) => a.title, FLOW: (a) => a.title };
const norm = (t) => ` ${String(t || "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim()} `;
// "Bottom-up table" is the topic "The bottom-up table" again.
const sameName = (a, b) => { const x = norm(a), y = norm(b); return x.trim() && y.trim() && (x.includes(y) || y.includes(x)); };

// {topics: [{n, title, index, at, end, points}], points: [{index, at, topic, sub, name, label}], at, total}.
// points are in order; sub 0 is the topic's own checkpoint. index is where playing starts.
export function checkpoints(segments, durations = {}) {
  const at = [];
  let t = 0;
  segments.forEach((seg, i) => { at.push(t); t += lineSeconds(seg, i, durations) || (seg.kind === "action" ? 0.6 : 0); });
  const total = t || 1;
  const timeAt = (i) => i < segments.length ? at[i] : total;
  const safe = safeLines(segments);
  const firstSafe = (from, to) => { for (let j = from; j < to; j++) if (safe.has(j)) return j; return null; };

  // Topics: the sections (a lesson without SECTION markers is one topic; anything before the first is "Start").
  const sections = [];
  segments.forEach((seg, i) => { if (seg.name === "SECTION") sections.push({ start: i, title: seg.args?.title || "" }); });
  if (!sections.length || sections[0].start > 0) sections.unshift({ start: 0, title: sections.length ? "Start" : "Lesson" });

  const topics = [];
  sections.forEach((sec, k) => {
    const end = sections[k + 1]?.start ?? segments.length;
    const first = firstSafe(sec.start, end);
    if (first == null) return;
    const topic = { n: topics.length + 1, title: sec.title, index: first, at: at[first], end: timeAt(end), points: [] };
    const subs = [{ index: first, name: sec.title, sub: 0 }];
    // Rule 3: named sub-topics; a code file counts the first time it appears.
    const files = new Set();
    for (let i = sec.start; i < end; i++) {
      const seg = segments[i], name = NAMED[seg.name]?.(seg.args || {});
      if (!name) continue;
      if (seg.name === "WRITE_CODE") { if (files.has(name)) continue; files.add(name); }
      const j = firstSafe(i + 1, end);
      if (j == null) continue;
      const last = subs[subs.length - 1];
      // Rule 4: too close to the one before, or the topic's own name again: merge.
      if (at[j] - at[last.index] < MIN_GAP_S || timeAt(end) - at[j] < MIN_GAP_S || sameName(name, sec.title)) continue;
      subs.push({ index: j, name, sub: subs.length });
    }
    // Rule 5: a long stretch with no sub-topic gets a "part n" at the safe line nearest its middle.
    const filled = [];
    const split = (from, to, name) => {
      const len = timeAt(to) - at[from];
      if (len <= MAX_GAP_S) return;
      const mid = at[from] + len / 2;
      const candidates = [...safe].filter(j => j > from && j < to && at[j] - at[from] >= MIN_GAP_S && timeAt(to) - at[j] >= MIN_GAP_S);
      if (!candidates.length) return;
      const best = candidates.reduce((a, b) => Math.abs(at[b] - mid) < Math.abs(at[a] - mid) ? b : a);
      split(from, best, name);
      filled.push({ index: best, name: `${name} (part 2)`, part: true });
      split(best, to, name);
    };
    subs.forEach((sub, m) => split(sub.index, subs[m + 1]?.index ?? end, sub.name));
    const all = [...subs, ...filled].sort((a, b) => a.index - b.index);
    let partOf = {}, subNo = 0;
    for (const p of all) {
      if (p.part) { const base = p.name.replace(/ \(part 2\)$/, ""); partOf[base] = (partOf[base] || 1) + 1; p.name = `${base} (part ${partOf[base]})`; }
      const sub = p.sub === 0 ? 0 : ++subNo;
      topic.points.push({ index: p.index, at: at[p.index], topic: topic.n, sub, name: p.name,
        label: sub ? `${topic.n}.${sub} · ${p.name}` : `${topic.n} · ${p.name}` });
    }
    topics.push(topic);
  });
  return { topics, points: topics.flatMap(tp => tp.points), at, total };
}
