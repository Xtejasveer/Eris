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
const BROWSER_RATE = 0.8;        // like TTS_SPEED: 1.0 sounds rushed for teaching
const SENTENCE_PAUSE_MS = 600;   // like SENTENCE_PAUSE_S
const QUESTION_PAUSE_MS = 850;   // like QUESTION_PAUSE_S
const PHRASE_PAUSE_MS = 250;     // like PHRASE_PAUSE_S: a short break at a comma
const PHRASE_MIN_WORDS = 4;

// A sentence split at commas into phrases of at least PHRASE_MIN_WORDS words (same rule as voice.py).
function phrases(sentence) {
  const parts = []; let cur = "";
  for (const bit of sentence.split(/(?<=,)\s+/)) {
    cur = `${cur} ${bit}`.trim();
    if (cur.endsWith(",") && cur.split(/\s+/).length >= PHRASE_MIN_WORDS) { parts.push(cur); cur = ""; }
  }
  if (cur) {
    if (parts.length && cur.split(/\s+/).length < PHRASE_MIN_WORDS) parts[parts.length - 1] += ` ${cur}`;
    else parts.push(cur);
  }
  return parts;
}

export function speechText(text) {
  const sayCode = (code) => CODE_WORDS.reduce((c, [sym, words]) => c.split(sym).join(words), code.replace(/\b[fFrRbB](?=["'])/g, ""));
  return text.replace(/`([^`]*)`/g, (_, code) => sayCode(code))
    .replaceAll("<=", " less than or equal to ").replaceAll(">=", " greater than or equal to ")
    .replaceAll("==", " equals ").replaceAll("!=", " is not equal to ")
    .replace(/\s+/g, " ").trim();
}

export class Voice {
  constructor(lectureId, language = "en-IN") {
    this.lectureId = lectureId;
    this.language = language;    // the lecture's teaching language: used by the browser voice when Gnani is off
    this.clips = new Map();      // text -> Promise<objectURL | null>
    this.timings = new Map();    // text -> Promise<{ words, times, durations } | null>: word timings for lip sync
    this._timing = null;         // timings of the clip playing now (re-sent after a pause or an avatar switch)
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
    this.rate = 1;               // playback speed (1 unless changed); the clip keeps its pitch
    this.muted = false;
    this.seq = 0;                // counts lines spoken, so a caption knows which line progress() is about
    this._done = 0;              // progress of the last line once it ended (1) or before it starts (0)
    this._browserFrac = 0;       // browser voice: how far through the line its word boundaries have got
  }

  // How far the line being spoken has got: {seq, frac 0-1}. Gnani clips follow their word timings (else the
  // clip's position); the browser voice follows its word boundaries. Live captions use this.
  progress() {
    if (!this.speaking) return { seq: this.seq, frac: this._done };
    if (this.mode === "gnani" && this.audio.src && this.audio.duration > 0) {
      const t = this.audio.currentTime;
      const times = this._timing?.times;
      if (times?.length) {
        const ms = t * 1000;
        let k = 0;
        while (k < times.length && times[k] <= ms) k++;
        return { seq: this.seq, frac: k / times.length };
      }
      return { seq: this.seq, frac: Math.min(1, t / this.audio.duration) };
    }
    return { seq: this.seq, frac: this._browserFrac };
  }

  setRate(rate) {
    this.rate = rate;
    this.audio.defaultPlaybackRate = rate;
    this.audio.playbackRate = rate;
  }

  setMuted(muted) {
    this.muted = muted;
    this.audio.muted = muted;
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
    this._timingToAvatar();
  }

  // The avatar follows the clip's own playback position, so pausing, resuming or late timings stay in sync.
  _timingToAvatar() {
    if (this.avatar && this._timing && this.mode === "gnani") this.avatar.setTimestamps(this._timing, { clock: "media", media: this.audio });
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
        const url = URL.createObjectURL(await res.blob());
        this.timing(text);  // the clip exists now, so its word timings can be made
        return url;
      }).catch(() => null));
    }
    return this.clips.get(text);
  }

  timing(text) {
    if (!this.timings.has(text)) {
      this.timings.set(text, api.ttsTiming(this.lectureId, text)
        .then(res => (res.ok && res.status !== 204 ? res.json() : null)).catch(() => null));
    }
    return this.timings.get(text);
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
    this.seq += 1;
    this._done = 0;
    this._browserFrac = 0;
    this.speaking = true;
    try {
      const url = await this.clip(text);
      if (url) {
        this.mode = "gnani";
        this._timing = null;
        this.avatar?.clearTimestamps();  // the last clip's timings must not drive this one
        const token = (this._token = {});
        this.timing(text).then((t) => { if (t && this._token === token) { this._timing = t; this._timingToAvatar(); } });
        await this._playUrl(url);
      }
      else { if (this.mode !== "gnani") this.mode = "browser"; await this._speakBrowser(text); }
    } finally { this.speaking = false; this._done = 1; this._token = null; this._timing = null; }
  }

  _playUrl(url) {
    return new Promise((resolve) => {
      const done = () => { this.audio.onended = this.audio.onerror = null; this._cancel = null; resolve(); };
      this._cancel = () => { this.audio.pause(); done(); };
      this.audio.onended = done;
      this.audio.onerror = done;
      this.audio.src = url;
      this.audio.playbackRate = this.rate;
      if (!this.paused) this.audio.play().catch(done);
    });
  }

  async _speakBrowser(text) {
    if (!("speechSynthesis" in window)) { await new Promise(r => setTimeout(r, text.split(/\s+/).length * 380)); return; }
    // Chrome cuts long utterances off, so speak one sentence at a time, with a pause between sentences.
    text = speechText(text);
    const sentences = text.match(/[^.!?।]+[.!?।]+["')\]]*|\S[^.!?।]*$/g) || [text];
    const parts = sentences.flatMap(sn => phrases(sn.trim()));
    let cancelled = false;
    this._cancel = () => { cancelled = true; speechSynthesis.cancel(); };
    const total = parts.reduce((n, p) => n + p.length, 0) || 1;
    let before = 0;  // characters of the line already spoken (for live captions)
    for (const part of parts) {
      if (cancelled) break;
      await new Promise((resolve) => {
        const u = new SpeechSynthesisUtterance(part.trim());
        u.lang = this.language; u.rate = BROWSER_RATE * this.rate; u.volume = this.muted ? 0 : 1;
        const base = this.language.split("-")[0];
        const voice = speechSynthesis.getVoices().find(v => v.lang === this.language) || speechSynthesis.getVoices().find(v => v.lang?.startsWith(base));
        if (voice) u.voice = voice;
        u.onend = u.onerror = () => { clearTimeout(fallback); resolve(); };
        let boundaries = false;
        u.onboundary = (e) => {
          if (e.name && e.name !== "word") return;
          this._browserFrac = Math.min(1, (before + e.charIndex) / total);
          boundaries = true;
          this._wordToAvatar(u.text.slice(e.charIndex).split(/\s/)[0]);
        };
        const fallback = setTimeout(() => { if (!boundaries && !cancelled) this._sentenceToAvatar(u.text); }, 350);
        speechSynthesis.speak(u);
        if (this.paused) speechSynthesis.pause();
      });
      before += part.length;
      this._browserFrac = Math.min(1, before / total);
      if (!cancelled && part !== parts[parts.length - 1])
        await new Promise(r => setTimeout(r, /[?!]["')\]]*\s*$/.test(part) ? QUESTION_PAUSE_MS
          : /,\s*$/.test(part) ? PHRASE_PAUSE_MS : SENTENCE_PAUSE_MS));
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
    this._timingToAvatar();  // pause() cleared the avatar's schedule
    if ("speechSynthesis" in window) speechSynthesis.resume();
  }

  stop() {
    this.paused = false;
    this._token = null; this._timing = null;
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
export function createDictation(language, onText, onEnd) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  const rec = new SR();
  rec.lang = language || "en-IN"; rec.interimResults = true; rec.continuous = false;
  rec.onresult = (e) => onText([...e.results].map(r => r[0].transcript).join(" "));
  rec.onend = onEnd; rec.onerror = onEnd;
  return rec;
}
