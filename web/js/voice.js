// Narration: Gnani clips from /api/tts (cached per line), else the browser's own speech.
// Also exposes a live loudness level for the teacher visual, and browser dictation.

import { api } from "./api.js";

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
    this._fake = 0;
    this._cancel = null;
  }

  // Must be called from a click (browsers only start audio after a user gesture).
  unlock() {
    try {
      if (!this._ctx) {
        this._ctx = new (window.AudioContext || window.webkitAudioContext)();
        const src = this._ctx.createMediaElementSource(this.audio);
        this._analyser = this._ctx.createAnalyser();
        this._analyser.fftSize = 256;
        this._buf = new Uint8Array(this._analyser.frequencyBinCount);
        src.connect(this._analyser); this._analyser.connect(this._ctx.destination);
      }
      this._ctx.resume();
    } catch { /* the level meter falls back to a simulated one */ }
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
    // Chrome cuts long utterances off, so speak one sentence at a time.
    const parts = text.match(/[^.!?]+[.!?]+["')\]]*|\S[^.!?]*$/g) || [text];
    let cancelled = false;
    this._cancel = () => { cancelled = true; speechSynthesis.cancel(); };
    for (const part of parts) {
      if (cancelled) break;
      await new Promise((resolve) => {
        const u = new SpeechSynthesisUtterance(part.trim());
        u.lang = "en-IN"; u.rate = 1;
        const voice = speechSynthesis.getVoices().find(v => v.lang === "en-IN") || speechSynthesis.getVoices().find(v => v.lang?.startsWith("en"));
        if (voice) u.voice = voice;
        u.onend = u.onerror = resolve;
        speechSynthesis.speak(u);
        if (this.paused) speechSynthesis.pause();
      });
    }
    this._cancel = null;
  }

  pause() {
    this.paused = true;
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
    if (this._cancel) this._cancel();
    if ("speechSynthesis" in window) speechSynthesis.cancel();
  }

  dispose() {
    this.stop();
    for (const p of this.clips.values()) p.then(u => u && URL.revokeObjectURL(u));
    try { this._ctx?.close(); } catch {}
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
