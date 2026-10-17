// Narration: Gnani clips from /api/tts (cached per line), else the browser's own speech.
// Also exposes a live loudness level for the teacher visual, and browser dictation.

import { api } from "./api.js";
import { getAudioContext, mediaElementSource } from "./avatar/audio-engine.js";

// The browser voice speaks the text as given, so code is turned into words first (same table as voice.py).
const CODE_WORDS = [["<=", " less than or equal to "], [">=", " greater than or equal to "], ["==", " equals "],
  ["!=", " is not equal to "], ["+=", " plus equals "], ["-=", " minus equals "], ["**", " to the power of "],
  ["//", " divided by "], ["->", " gives "], ["<", " less than "], [">", " greater than "], ["=", " equals "],
  ["%", " mod "], ["_", " "], ["(", " "], [")", " "], ["[", " "], ["]", " "], ["{", " "], ["}", " "],
  ['"', ""], ["'", ""], [":", " "], ["#", " "]];
const BROWSER_RATE = 0.9;        // like TTS_SPEED: 1.0 sounds rushed for teaching
const SENTENCE_PAUSE_MS = 350;   // like SENTENCE_PAUSE_S
const QUESTION_PAUSE_MS = 500;

export function speechText(text) {
  const sayCode = (code) => CODE_WORDS.reduce((c, [sym, words]) => c.split(sym).join(words), code.replace(/\b[fFrRbB](?=["'])/g, ""));
  return text.replace(/`([^`]*)`/g, (_, code) => sayCode(code))
    .replaceAll("<=", " less than or equal to ").replaceAll(">=", " greater than or equal to ")
    .replaceAll("==", " equals ").replaceAll("!=", " is not equal to ")
    .replace(/\s+/g, " ").trim();
}

export class Voice {
  constructor(lectureId) {
    this.lectureId = lectureId;
    this.clips = new Map();      // text -> Promise<objectURL | null>
    this.audio = new Audio();
    this.audio.preload = "auto";
    this.mode = "unknown";       // "gnani" once a clip plays, "browser" when /tts returns 204
    this.speaking = false;
    this.paused = false;
    this._ctx = null; this._analyser = null; this._buf = null;
    this._out = null;            // every Gnani clip leaves through this node: to the speakers, or into the avatar
    this.avatar = null;          // a talking avatar (avatar/avatar.js) that plays and lip-syncs the voice, if any
    this._fake = 0;
    this._cancel = null;
  }

  // Must be called from a click (browsers only start audio after a user gesture).
  unlock() {
    try {
      if (!this._ctx) {
        this._ctx = getAudioContext();  // shared with the avatar: one AudioContext for the page
        this._out = this._ctx.createGain();
        mediaElementSource(this.audio, this._ctx).connect(this._out);
        this._analyser = this._ctx.createAnalyser();  // a tap for the level meter, not an output
        this._analyser.fftSize = 256;
        this._buf = new Uint8Array(this._analyser.frequencyBinCount);
        this._out.connect(this._analyser);
        this._route();
      }
      this._ctx.resume();
    } catch { /* the level meter falls back to a simulated one */ }
  }

  /** Let an avatar play and lip-sync the voice (null: straight to the speakers). Never both: heard once. */
  setAvatar(avatar) {
    if (this.avatar && this._out) this.avatar.detachAudioStream(this._out);
    this.avatar = avatar;
    if (this._out) this._route();
  }

  _route() {
    try { this._out.disconnect(this._ctx.destination); } catch { /* was not connected */ }
    if (this.avatar) this.avatar.attachAudioStream(this._out);
    else this._out.connect(this._ctx.destination);
  }

  // The browser voice can't be routed into Web Audio, so the avatar gets its words as timings instead.
  _wordToAvatar(word) {
    if (!this.avatar || !word) return;
    const ms = Math.max(160, word.length * 80) / BROWSER_RATE;
    this.avatar.setTimestamps({ words: [word], times: [0], durations: [ms] }, { clock: "perf" });
  }

  _sentenceToAvatar(sentence) {  // for voices that fire no word boundaries: spread the words over an estimate
    if (!this.avatar) return;
    const words = sentence.split(/\s+/).filter(Boolean), times = [], durations = [];
    let t = 0;
    for (const w of words) { const d = Math.max(160, w.length * 80) / BROWSER_RATE; times.push(t); durations.push(d); t += d + 50; }
    this.avatar.setTimestamps({ words, times, durations }, { clock: "perf" });
  }

  clip(text) {
    if (!this.clips.has(text)) {
      this.clips.set(text, api.tts(this.lectureId, text).then(async (res) => {
        if (res.status === 204 || !res.ok) return null;
        return URL.createObjectURL(await res.blob());
      }).catch(() => null));
    }
    return this.clips.get(text);
  }

  // Length of the spoken line in seconds: the real clip when there is one, else an estimate.
  async duration(text) {
    const estimate = (text.trim().split(/\s+/).length / 150) * 60;  // browser voices speak ~150 wpm
    const url = this.mode === "browser" ? null : await this.clip(text);
    if (!url) return estimate;
    return new Promise((resolve) => {
      const probe = new Audio();
      probe.preload = "metadata";
      probe.onloadedmetadata = () => resolve(Number.isFinite(probe.duration) ? probe.duration : estimate);
      probe.onerror = () => resolve(estimate);
      probe.src = url;
    });
  }

  prefetch(text) { if (text && this.mode !== "browser") this.clip(text); }

  level() {
    if (!this.speaking || this.paused) return 0;
    if (this.mode === "gnani" && this._analyser && !this.audio.paused) {
      this._analyser.getByteTimeDomainData(this._buf);
      let sum = 0;
      for (const v of this._buf) sum += (v - 128) ** 2;
      return Math.min(1, Math.sqrt(sum / this._buf.length) / 40);
    }
    this._fake += 0.18;
    return 0.35 + 0.3 * Math.abs(Math.sin(this._fake)) * (0.6 + 0.4 * Math.sin(this._fake * 2.7));
  }

  // Resolves when the line has been spoken (or stop() was called).
  async speak(text) {
    if (!text.trim()) return;
    this.speaking = true;
    try {
      const url = await this.clip(text);
      if (url) { this.mode = "gnani"; await this._playUrl(url); }
      else { if (this.mode !== "gnani") this.mode = "browser"; await this._speakBrowser(text); }
    } finally { this.speaking = false; }
  }

  _playUrl(url) {
    return new Promise((resolve) => {
      const done = () => { this.audio.onended = this.audio.onerror = null; this._cancel = null; resolve(); };
      this._cancel = () => { this.audio.pause(); done(); };
      this.audio.onended = done;
      this.audio.onerror = done;
      this.audio.src = url;
      if (!this.paused) this.audio.play().catch(done);
    });
  }

  async _speakBrowser(text) {
    if (!("speechSynthesis" in window)) { await new Promise(r => setTimeout(r, text.split(/\s+/).length * 380)); return; }
    // Chrome cuts long utterances off, so speak one sentence at a time, with a pause between sentences.
    text = speechText(text);
    const parts = text.match(/[^.!?]+[.!?]+["')\]]*|\S[^.!?]*$/g) || [text];
    let cancelled = false;
    this._cancel = () => { cancelled = true; speechSynthesis.cancel(); };
    for (const part of parts) {
      if (cancelled) break;
      await new Promise((resolve) => {
        const u = new SpeechSynthesisUtterance(part.trim());
        u.lang = "en-IN"; u.rate = BROWSER_RATE;
        const voice = speechSynthesis.getVoices().find(v => v.lang === "en-IN") || speechSynthesis.getVoices().find(v => v.lang?.startsWith("en"));
        if (voice) u.voice = voice;
        u.onend = u.onerror = () => { clearTimeout(fallback); resolve(); };
        let boundaries = false;
        u.onboundary = (e) => {
          if (e.name && e.name !== "word") return;
          boundaries = true;
          this._wordToAvatar(u.text.slice(e.charIndex).split(/\s/)[0]);
        };
        const fallback = setTimeout(() => { if (!boundaries && !cancelled) this._sentenceToAvatar(u.text); }, 350);
        speechSynthesis.speak(u);
        if (this.paused) speechSynthesis.pause();
      });
      if (!cancelled && part !== parts[parts.length - 1])
        await new Promise(r => setTimeout(r, /[?!]["')\]]*\s*$/.test(part) ? QUESTION_PAUSE_MS : SENTENCE_PAUSE_MS));
    }
    this._cancel = null;
  }

  pause() {
    this.paused = true;
    this.avatar?.stop();  // mouth to rest; a paused clip is silent anyway
    if (!this.audio.paused) this.audio.pause();
    if ("speechSynthesis" in window) speechSynthesis.pause();
  }

  resume() {
    this.paused = false;
    if (this.audio.src && this.audio.paused && !this.audio.ended && this._cancel) this.audio.play().catch(() => {});
    if ("speechSynthesis" in window) speechSynthesis.resume();
  }

  stop() {
    this.paused = false;
    this.avatar?.stop();  // interruption: the avatar flushes its audio and closes the mouth
    if (this._cancel) this._cancel();
    if ("speechSynthesis" in window) speechSynthesis.cancel();
  }

  dispose() {
    this.stop();
    for (const p of this.clips.values()) p.then(u => u && URL.revokeObjectURL(u));
    this.setAvatar(null);
    try { this._out?.disconnect(); this._analyser?.disconnect(); } catch {}  // the shared AudioContext stays open
  }
}

// Browser dictation (Chrome, Safari). Returns null when unsupported.
export function createDictation(onText, onEnd) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  const rec = new SR();
  rec.lang = "en-IN"; rec.interimResults = true; rec.continuous = false;
  rec.onresult = (e) => onText([...e.results].map(r => r[0].transcript).join(" "));
  rec.onend = onEnd; rec.onerror = onEnd;
  return rec;
}
