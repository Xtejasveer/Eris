// The browser player: walks the approved segments one at a time, like session.py.
// Narration finishes -> the next action runs -> the next narration. LLMs are only used for
// doubt checks and one-line recoveries, and get a read-only snapshot of the class.

import { api } from "./api.js";
import { sleep } from "./ui.js";

export class Stopped extends Error {}

const NO_DOUBT_WORDS = new Set(["", "no", "none", "no doubts", "nope", "n"]);  // as in doubt_agent.py

export class Player {
  constructor({ lectureId, segments, teacher, stage, voice, ui }) {
    Object.assign(this, { lectureId, segments, teacher, stage, voice, ui });
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
      `Notebook (latest lines):\n${b.notebook.slice(-12).join("\n") || "empty"}\n\n` +
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
      }
    }
    this.cursor = upTo;
    this.ui.onSection?.(this.state.section);
  }

  async play(from = 0) {
    this.stopped = false;
    await this.restore(from);
    for (let i = from; i < this.segments.length; i++) {
      this.cursor = i;
      this.ui.onProgress?.(i, this.segments.length);
      await this.gate();
      const seg = this.segments[i];
      try {
        await this.playSegment(seg, i);
        this.log(i, seg, "done");
      } catch (e) {
        if (e instanceof Stopped) { this.log(i, seg, "stopped"); throw e; }
        this.state.failed += 1;
        this.log(i, seg, "failed", e.message);
        console.warn(`[class] segment ${i + 1} failed:`, e);
      }
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
    await this.gate();
  }

  async playSegment(seg, index) {
    if (seg.kind === "say") {
      this.state.sectionText.push(seg.text);
      return this.say(seg.text, index);
    }
    const a = seg.args || {};
    if (seg.name === "SECTION") {
      this.state.section = a.title; this.state.covered.push(a.title); this.state.sectionText = [];
      this.ui.onSection?.(a.title);
      return;
    }
    if (seg.name === "DOUBT_CHECK") return this.doubtCheck(index === this.segments.length - 1);
    if (seg.name === "WRITE_CODE") this.state.sectionText.push(`Code in ${a.file}:\n${a.code}`);
    if (["NOTE", "NOTE_TITLE", "WRITE"].includes(seg.name)) this.state.sectionText.push(`Notebook:\n${a.text}`);
    const error = await this.action(seg);
    if (error) {
      this.stage.classLine(error);
      let line = "Let's keep going.";
      try { line = (await api.recovery(this.lectureId, seg, error, this.snapshot())).line || line; } catch {}
      await this.say(line);
      throw new Error(error);
    }
  }

  // Runs one action on the stage. Returns an error string, or "" when it worked.
  async action(seg) {
    const a = seg.args || {}, b = this.board, st = this.stage;
    switch (seg.name) {
      case "NOTE_TITLE":
        b.notebook.push("## " + a.text); await st.noteTitle(a.text, this.ctl); return "";
      case "NOTE": case "WRITE":
        b.notebook.push(...a.text.split("\n")); await st.note(a.text, this.ctl); return "";
      case "NOTE_HIGHLIGHT":
        if (!b.notebook.some(l => l.toLowerCase().includes(a.text.toLowerCase()))) return `'${a.text}' is not in the notebook`;
        st.noteHighlight(a.text); await this.tick(500); return "";
      case "LOOK_BACK":
        if (!b.notebook.some(l => l.toLowerCase().includes(a.text.toLowerCase()))) return `'${a.text}' is not in the notebook`;
        st.lookBack(a.text); await this.tick(900); return "";
      case "NEW_PAGE":
        b.notebook.push(a.title); await st.newPage(a.title, this.ctl); return "";
      case "OPEN_FILE":
        if (!(a.file in b.files)) return `${a.file} is not on the board`;
        st.openFile(a.file); await this.tick(500); return "";
      case "SLIDE":
        b.currentSlide = a.n; await this.tick(150);
        return st.showSlide(a.n) ? "" : `slide ${a.n} not found`;
      case "SLIDE_HIGHLIGHT":
        st.slideHighlight(a.text); await this.tick(400); return "";
      case "WRITE_CODE":
        b.files[a.file] = a.code; await st.writeCode(a.file, a.code, this.ctl); return "";
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
      default:
        return `no action for [${seg.name}]`;
    }
  }

  // Answers and closing lines from the doubt agent can write notes and code too. They are not approved,
  // so a failing step is shown and skipped without a recovery line.
  async playAnswer(segments) {
    for (const seg of segments) {
      await this.gate();
      if (seg.kind === "say") { await this.say(seg.text); continue; }
      const err = await this.action(seg);
      if (err) this.stage.classLine(err);
    }
  }

  async doubtCheck(final) {
    const ui = this.ui;
    const chk = ui.openCheckpoint(this.state.section, final);
    const view = this.stage.view();  // answers may turn pages or open files; come back afterwards
    const close = () => { chk.close(); this.stage.restoreView(view); };
    let turn;
    try {
      chk.thinking(true);
      turn = await api.doubtStart(this.lectureId, this.snapshot(), this.state.section, final, this.cursor);
      chk.setLimit(turn.max);
    } catch (e) {
      chk.note(`The doubt agent is unavailable (${e.message}). Moving on.`);
      close();
      return;
    } finally { chk.thinking(false); }
    const threadId = turn.thread_id;
    let rounds = 0, askedHere = 0, declined = 0;  // declined: replies of "no doubts" in a row
    try {
      while (true) {
        if (turn.reply_text || turn.reply_segments?.length) {
          chk.teacher(turn.reply_text || turn.reply, { passed: turn.passed });
          await this.playAnswer(turn.reply_segments || []);
        }
        if (turn.done || rounds > (turn.max || 3) + 3) {
          if (turn.final_text) { chk.teacher(turn.final_text); await this.playAnswer(turn.final_segments || []); }
          break;
        }
        if (declined === 1) {
          // The class said no doubts but the model asked again: tell it once more, without asking the class.
          declined = 2;
          chk.thinking(true);
          try { turn = await api.doubtReply(this.lectureId, threadId, "no doubts"); }
          finally { chk.thinking(false); }
          continue;
        }
        if (declined > 1) {
          const line = "Alright, let's move on.";
          chk.teacher(line); await this.say(line);
          break;
        }
        rounds += 1;
        if (turn.prompt && turn.prompt !== turn.reply) { chk.teacher(turn.prompt, { prompt: true }); await this.say(turn.prompt); }
        const answer = await chk.ask();
        await this.gate();
        if (answer) chk.student(answer);
        declined = NO_DOUBT_WORDS.has(answer.toLowerCase()) ? 1 : 0;
        chk.thinking(true);
        try { turn = await api.doubtReply(this.lectureId, threadId, answer); }
        finally { chk.thinking(false); }
        this.state.doubtsAsked += (turn.asked || 0) - askedHere;
        askedHere = turn.asked || 0;
        if (turn.passed) this.state.passed += 1;
        chk.setCount(turn.asked, turn.max);
      }
    } catch (e) {
      if (e instanceof Stopped) { close(); throw e; }
      chk.note(`Something went wrong (${e.message}). Moving on.`);
    }
    close();
  }
}
