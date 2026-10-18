// The browser player: walks the approved segments one at a time, like session.py.
// Narration finishes -> the next action runs -> the next narration. LLMs are only used for
// doubt checks and one-line recoveries, and get a read-only snapshot of the class.

import { api } from "./api.js";
import { sleep } from "./ui.js";
import { NOTE_MS, CODE_MS } from "./stage.js";

export class Stopped extends Error {}

// A slide (or slide highlight) followed by another screen action, not by a sentence about it: the class would
// see it flash. Keep it on screen a few seconds first. (A slide followed by its highlight needs no wait.)
const needsDwell = (seg, next) => SLIDE_MARKERS.has(seg.name) && next && next.kind !== "say" && !SLIDE_MARKERS.has(next.name);

// Level 2 sync: a while_speaking action runs during the narration right after it.
const isPair = (seg, next) => seg.kind === "action" && !!seg.args?.while_speaking && next?.kind === "say";

const NO_DOUBT_WORDS = new Set(["", "no", "none", "no doubts", "nope", "n"]);  // as in doubt_agent.py
const BREATH_MS = 500;          // a short breath after each spoken line, before the next step
const SECTION_BREATH_MS = 1100; // a longer one when a new part of the lesson starts
const SLIDE_DWELL_MS = 3000;    // a slide nobody talks about stays this long before the next workspace opens
const SLIDE_MARKERS = new Set(["SLIDE", "SLIDE_HIGHLIGHT"]);
const DOUBT_WAIT_S = 10;    // how long the class has to start asking before the lesson goes on
const ANSWER_WAIT_S = 25;   // when the teacher asked the student something back, they get longer to reply
const BREAK_MAX_QUESTIONS = 4;   // a mid-lecture break takes at most this many questions…
const BREAK_BUDGET_S = 150;      // …or this much time; then the rest waits for the end of the class
const FINAL_MAX_QUESTIONS = 8;
const FIRST_PROMPT = "Any doubts so far? You can type or say your question.";
const FINAL_PROMPT = "Any last questions before we finish?";
const FINAL_DEFERRED_PROMPT = "As promised, let's take your remaining questions now. What would you like to ask?";
const MORE_PROMPT = "Any other doubts?";
const CLOSING_LINE = "Alright, let's move on.";
const DEFER_LINE = "We're running short on time, so let's carry on. Keep your other questions; we'll take them all at the end of the class.";
const LIMIT_LINE = "That's all the time we have for questions today.";
// The answer ended by asking the student something specific (not "Clear so far?"): let them answer it.
const CHECK_IN_RE = /\b(clear|make sense|got it|any (other )?doubts?|questions?|okay|right|ready|follow)\b[^?]*\?\s*$/i;
const asksStudent = (text) => {
  const last = (text || "").trim().split(/(?<=[.!?])\s+/).slice(-2);
  return last.some(sentence => /\?\s*$/.test(sentence) && !CHECK_IN_RE.test(sentence))
    || /\b(please (specify|tell me|share|paste|type)|let me know which|tell me which)\b/i.test(last.join(" "));
};
const FINAL_CLOSING_LINE = "Thank you for your questions. See you in the next class.";

export class Player {
  constructor({ lectureId, segments, teacher, stage, voice, ui }) {
    Object.assign(this, { lectureId, segments, teacher, stage, voice, ui });
    this.doubtThread = null;     // ONE doubt-agent conversation for the whole class: it remembers every answer
    this.deferredDoubts = false; // a break ran out of time: the final break opens with "as promised…"
    this.paused = false;
    this.stopped = false;
    this.cursor = 0;
    this._resume = null;
    this.resetState();
    // ctl is what animations use to wait: it honours pause and stop.
    this.ctl = { tick: (ms) => this.tick(ms) };
  }

  resetState() {
    this.state = { section: "Introduction", covered: [], sectionText: [], doubtsAsked: 0, passed: 0, failed: 0, events: [] };
    this.board = { files: {}, notebook: [], currentSlide: null, lastOutput: "", expectedOutput: "" };
  }

  async gate() {
    if (this.stopped) throw new Stopped();
    while (this.paused) {
      await new Promise(r => { this._resume = r; });
      if (this.stopped) throw new Stopped();
    }
  }

  async tick(ms) { await sleep(ms); await this.gate(); }

  pause() { this.paused = true; this.voice.pause(); }
  resume() { this.paused = false; this.voice.resume(); this._resume?.(); }
  stop() { this.stopped = true; this.paused = false; this.voice.stop(); this._resume?.(); this.ui.cancelAsk?.(); }

  snapshot() {
    const b = this.board, s = this.state;
    return `Current section: ${s.section}\n` +
      `Sections covered so far: ${s.covered.join(", ") || "none"}\n` +
      `Code on the board: ${Object.keys(b.files).join(", ") || "nothing"}\n` +
      `Current slide: ${b.currentSlide || "none"}\n` +
      `Last program output: ${b.lastOutput.trim().slice(0, 300) || "none"}\n` +
      `Notebook (latest lines):\n${b.notebook.slice(-12).join("\n") || "empty"}\n` +
      `Visuals on screen:\n${this.stage.visualStates() || "none"}\n` +
      `Diagrams on the board:\n${this.stage.flowStates() || "none"}\n\n` +
      `What was taught in this section (narration and code):\n` + s.sectionText.join("\n").slice(0, 3000);
  }

  // Rebuild the board silently from already-played segments (jump / resume).
  async restore(upTo) {
    this.resetState();
    this.stage.reset();
    for (const seg of this.segments.slice(0, upTo)) {
      const a = seg.args || {};
      if (seg.kind === "say") { this.state.sectionText.push(seg.text); continue; }
      switch (seg.name) {
        case "SECTION": this.state.section = a.title; this.state.covered.push(a.title); this.state.sectionText = []; break;
        case "WRITE_CODE": this.board.files[a.file] = a.code; await this.stage.writeCode(a.file, a.code); break;
        case "RUN": this.board.lastOutput = this.board.expectedOutput = seg.expected_output || ""; break;
        case "SLIDE": this.board.currentSlide = a.n; this.stage.showSlide(a.n); break;
        case "NOTE": case "WRITE": this.board.notebook.push(...a.text.split("\n")); await this.stage.note(a.text); break;
        case "NOTE_TITLE": this.board.notebook.push("## " + a.text); await this.stage.noteTitle(a.text); break;
        case "NOTE_HIGHLIGHT": this.stage.noteHighlight(a.text); break;
        case "NEW_PAGE": this.board.notebook.push(a.title); await this.stage.newPage(a.title); break;
        case "VISUAL": if (a.key) await this.stage.showVisual(a.id, this.visualUrl(a.key), a.title); break;
        case "VISUAL_SET": await this.stage.setVisual(a.id, a.control, a.value, { instant: true }); break;
        case "FLOW": this.stage.showFlow(a.id, { title: a.title, blocks: a.blocks, edges: a.edges }); break;
        case "FLOW_NEXT": this.stage.flowNext(a.id, false); break;
      }
    }
    this.cursor = upTo;
    this.ui.onSection?.(this.state.section);
  }

  visualUrl(key) { return `/api/lectures/${encodeURIComponent(this.lectureId)}/visuals/${encodeURIComponent(key)}`; }

  async play(from = 0) {
    this.stopped = false;
    await this.restore(from);
    for (let i = from; i < this.segments.length; i++) {
      this.cursor = i;
      this.ui.onProgress?.(i, this.segments.length);
      await this.gate();
      const seg = this.segments[i];
      const next = this.segments[i + 1];
      const pair = isPair(seg, next);
      try {
        await this.playSegment(seg, i, pair ? next : null);
        this.log(i, seg, "done");
      } catch (e) {
        if (e instanceof Stopped) { this.log(i, seg, "stopped"); throw e; }
        this.state.failed += 1;
        this.log(i, seg, "failed", e.message);
        console.warn(`[class] segment ${i + 1} failed:`, e);
      }
      if (pair) { this.log(i + 1, next, "done"); i += 1; }  // its narration played together with it
    }
    this.cursor = this.segments.length;
    this.ui.onProgress?.(this.segments.length, this.segments.length);
  }

  log(index, seg, status, detail = "") {
    this.state.events.push({ time: new Date().toISOString(), index, name: seg.name || "SAY", status, detail: detail.slice(0, 300) });
  }

  nextSay(index) {
    for (let j = index + 1; j < this.segments.length; j++) if (this.segments[j].kind === "say") return this.segments[j].text;
    return null;
  }

  async say(text, index = null) {
    this.ui.onCaption?.(text);
    if (index != null) this.voice.prefetch(this.nextSay(index));
    await this.voice.speak(text);
    await this.tick(BREATH_MS);  // tick also honours pause and stop
  }

  // withSay: the narration to speak while this action runs (a while_speaking pair).
  async playSegment(seg, index, withSay = null) {
    if (seg.kind === "say") {
      this.state.sectionText.push(seg.text);
      return this.say(seg.text, index);
    }
    const a = seg.args || {};
    if (seg.name === "SECTION") {
      this.state.section = a.title; this.state.covered.push(a.title); this.state.sectionText = [];
      this.ui.onSection?.(a.title);
      await this.tick(SECTION_BREATH_MS);
      return;
    }
    if (seg.name === "DOUBT_CHECK") return this.doubtCheck(index === this.segments.length - 1);
    if (seg.name === "WRITE_CODE") this.state.sectionText.push(`Code in ${a.file}:\n${a.code}`);
    if (["NOTE", "NOTE_TITLE", "WRITE"].includes(seg.name)) this.state.sectionText.push(`Notebook:\n${a.text}`);
    if (seg.name === "VISUAL") this.state.sectionText.push(`Visual "${a.title}" (${a.id}): ${a.brief}`);
    if (seg.name === "FLOW") this.state.sectionText.push(`Diagram "${a.title}" (${a.id}): ${a.blocks.map(b => b.label).join(" -> ")}`);
    const error = withSay ? await this.pair(seg, withSay, index) : await this.action(seg);
    if (!error && !withSay && needsDwell(seg, this.segments[index + 1])) await this.tick(SLIDE_DWELL_MS);
    if (error) {  // for a pair, the recovery line comes after the sentence has ended
      this.stage.classLine(error);
      let line = "Let's keep going.";
      try { line = (await api.recovery(this.lectureId, seg, error, this.snapshot())).line || line; } catch {}
      await this.say(line);
      throw new Error(error);
    }
  }

  // Speak the sentence and run the action at the same time; continue when both are done.
  // The writing is paced to fill about 80% of the sentence. Returns the action's error ("" if fine).
  async pair(seg, saySeg, index = null) {
    this.state.sectionText.push(saySeg.text);
    const seconds = await this.voice.duration(saySeg.text);
    const [, error] = await Promise.all([
      this.say(saySeg.text, index == null ? null : index + 1),
      this.action(seg, seconds * 0.8),
    ]);
    return error;
  }

  pacedCtl(seg, paceS) {
    const a = seg.args || {};
    const text = a.code ?? a.text ?? a.title ?? "";
    const code = seg.name === "WRITE_CODE";
    const chars = text.replace(/\s/g, "").length || 1;  // spaces are written without a pause
    const lineMs = code ? 20 : 0;
    const budget = paceS * 1000 - text.split("\n").length * lineMs;
    // Never slower than normal writing, never so fast it looks like a paste.
    const charMs = Math.max(8, Math.min(code ? CODE_MS : NOTE_MS, budget / chars));
    return { tick: this.ctl.tick, charMs, lineMs };
  }

  // Runs one action on the stage. Returns an error string, or "" when it worked.
  // paceS: seconds the writing should take (while_speaking); otherwise the normal speed.
  async action(seg, paceS = null) {
    const a = seg.args || {}, b = this.board, st = this.stage;
    const ctl = paceS ? this.pacedCtl(seg, paceS) : this.ctl;
    switch (seg.name) {
      case "NOTE_TITLE":
        b.notebook.push("## " + a.text); await st.noteTitle(a.text, ctl); return "";
      case "NOTE": case "WRITE":
        b.notebook.push(...a.text.split("\n")); await st.note(a.text, ctl); return "";
      case "NOTE_HIGHLIGHT":
        if (!b.notebook.some(l => l.toLowerCase().includes(a.text.toLowerCase()))) return `'${a.text}' is not in the notebook`;
        st.noteHighlight(a.text); await this.tick(500); return "";
      case "LOOK_BACK":
        if (!b.notebook.some(l => l.toLowerCase().includes(a.text.toLowerCase()))) return `'${a.text}' is not in the notebook`;
        st.lookBack(a.text); await this.tick(900); return "";
      case "NEW_PAGE":
        b.notebook.push(a.title); await st.newPage(a.title, ctl); return "";
      case "OPEN_FILE":
        if (!(a.file in b.files)) return `${a.file} is not on the board`;
        st.openFile(a.file); await this.tick(500); return "";
      case "SLIDE":
        b.currentSlide = a.n; await this.tick(150);
        return st.showSlide(a.n) ? "" : `slide ${a.n} not found`;
      case "SLIDE_HIGHLIGHT":
        st.slideHighlight(a.text); await this.tick(400); return "";
      case "WRITE_CODE":
        b.files[a.file] = a.code; await st.writeCode(a.file, a.code, ctl); return "";
      case "HIGHLIGHT":
        if (!(a.file in b.files)) return `${a.file} is not on the board`;
        st.highlight(a.file, a.lines); await this.tick(500); return "";
      case "RUN": {
        const file = a.cmd.replace(/^python\s+/, "").trim();
        if (!(file in b.files)) return `${file} is not on the board`;
        const out = st.runStart(a.cmd);
        let res;
        try { res = await api.run(this.lectureId, file, b.files[file]); }
        catch (e) { st.runEnd(out, e.message, false); return `${a.cmd} could not run: ${e.message}`; }
        const expected = seg.expected_output || "";
        b.lastOutput = res.output; b.expectedOutput = expected;
        // A non-zero exit is fine if it was approved (e.g. a planned error demo).
        const ok = res.exit_code === 0 || res.output.trim() === expected.trim();
        st.runEnd(out, res.output, ok);
        await this.tick(300);
        return ok ? "" : `${a.cmd} failed (exit ${res.exit_code}): ${res.stderr.trim().slice(-300)}`;
      }
      case "READ_OUTPUT":
        st.flashTerminal(); await this.tick(400);
        if (b.expectedOutput && b.lastOutput.trim() !== b.expectedOutput.trim())
          return `live output differs from the approved output. Expected: ${JSON.stringify(b.expectedOutput.trim().slice(0, 200))}`;
        return "";
      case "PAUSE":
        await this.tick(a.s * 1000); return "";
      case "VISUAL":
        if (!a.key) return `visual ${a.id} was not built`;
        return await st.showVisual(a.id, this.visualUrl(a.key), a.title);
      case "VISUAL_SET": {
        const err = await st.setVisual(a.id, a.control, a.value);
        await this.tick(250);  // let the class see the change before the teacher talks about it
        return err;
      }
      case "FLOW":
        st.showFlow(a.id, { title: a.title, blocks: a.blocks, edges: a.edges }); await this.tick(300); return "";
      case "FLOW_NEXT":
        if (!st.flowNext(a.id)) return `flow ${a.id} has no block left to draw`;
        await this.tick(700); return "";  // the block and its arrows draw themselves
      case "FLOW_HIGHLIGHT":
        if (!st.flowHighlight(a.id, a.block)) return `block ${a.block} is not drawn in ${a.id}`;
        await this.tick(500); return "";
      case "OPEN_FLOW":
        if (!st.openFlow(a.id)) return `diagram ${a.id} is not on the board`;
        await this.tick(400); return "";
      case "OPEN_VISUAL":
        if (!st.openVisual(a.id)) return `visual ${a.id} is not on the board`;
        await this.tick(400); return "";
      default:
        return `no action for [${seg.name}]`;
    }
  }

  // Answers and closing lines from the doubt agent can write notes and code too. They are not approved,
  // so a failing step is shown and skipped without a recovery line.
  async playAnswer(segments) {
    for (let j = 0; j < segments.length; j++) {
      const seg = segments[j];
      await this.gate();
      if (seg.kind === "say") { await this.say(seg.text); continue; }
      const pair = isPair(seg, segments[j + 1]);
      const err = pair ? await this.pair(seg, segments[j + 1]) : await this.action(seg);
      if (!err && !pair && needsDwell(seg, segments[j + 1])) await this.tick(SLIDE_DWELL_MS);
      if (err) this.stage.classLine(err);
      if (pair) j += 1;
    }
  }

  // A question break. The player asks the class itself and waits DOUBT_WAIT_S seconds, so the class always
  // gets its chance, whatever the model does. The doubt agent is only called when a student asks something,
  // always on the class's one conversation. A mid-lecture break ends after BREAK_MAX_QUESTIONS or
  // BREAK_BUDGET_S, but never in the middle of an exchange: if the teacher just asked the student something
  // back ("which code?"), the student may answer first. Questions that didn't fit move to the final break.
  async doubtCheck(final) {
    const ui = this.ui;
    const chk = ui.openCheckpoint(this.state.section, final);
    const view = this.stage.view();  // answers may turn pages or open files; come back afterwards
    const close = () => { chk.close(); this.stage.restoreView(view); };
    const started = performance.now();
    const maxQuestions = final ? FINAL_MAX_QUESTIONS : BREAK_MAX_QUESTIONS;
    let asked = 0, followUp = false;  // followUp: the student is answering the teacher's question back
    let prompt = final ? (this.deferredDoubts ? FINAL_DEFERRED_PROMPT : FINAL_PROMPT) : FIRST_PROMPT;
    let closing = final ? FINAL_CLOSING_LINE : CLOSING_LINE;
    try {
      while (true) {
        const outOfTime = !final && (performance.now() - started) / 1000 > BREAK_BUDGET_S;
        if (!followUp && (asked >= maxQuestions || outOfTime)) {
          if (final) closing = LIMIT_LINE;
          else { closing = DEFER_LINE; this.deferredDoubts = true; }
          break;
        }
        if (prompt) { chk.teacher(prompt, { prompt: true }); await this.say(prompt); }
        const question = (await chk.ask(followUp ? ANSWER_WAIT_S : DOUBT_WAIT_S)).trim();
        await this.gate();
        if (NO_DOUBT_WORDS.has(question.toLowerCase())) break;  // nobody asked in time, or "no questions"
        chk.student(question);
        chk.thinking(true);
        let turn;
        try {
          turn = await api.doubtAsk(this.lectureId, {
            question, context: this.snapshot(), section: this.state.section, final, cursor: this.cursor,
            threadId: this.doubtThread, visuals: [this.stage.visualStates(), this.stage.flowStates()].filter(Boolean).join("\n"),
          });
        } finally { chk.thinking(false); }
        this.doubtThread = turn.thread_id || this.doubtThread;
        if (!followUp) { asked += 1; this.state.doubtsAsked += 1; }  // a reply to the teacher isn't a new doubt
        if (turn.passed) this.state.passed += 1;
        chk.setCount(asked, maxQuestions);
        const segments = turn.reply_segments?.length ? turn.reply_segments : turn.final_segments || [];
        const text = turn.reply_text || turn.reply || turn.final_text;
        if (text) chk.teacher(text, { passed: turn.passed });
        await this.playAnswer(segments);
        followUp = asksStudent(text);
        prompt = followUp ? null : MORE_PROMPT;  // the teacher's own question is the prompt
      }
      chk.teacher(closing);
      await this.say(closing);
      if (final) this.deferredDoubts = false;
    } catch (e) {
      if (e instanceof Stopped) { close(); throw e; }
      chk.note(`Something went wrong (${e.message}). Moving on.`);
    }
    close();
  }


}
