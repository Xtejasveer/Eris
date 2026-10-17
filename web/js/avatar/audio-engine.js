// The avatar's audio path. One AudioContext for the whole page, and every sound the avatar speaks goes through:
//
//   [attached element / stream / node] ─┐
//   [chunk queue] → streamGain ─────────┴→ input → analyser → delay → speakers
//
// The analyser sits on the real output path, so the lips follow exactly what is heard, and nothing is played twice.

import { nextStartTime, pcm16ToFloat32, deinterleave } from "./scheduler.js";

let sharedCtx = null;
const elementSources = new WeakMap();  // a media element can only ever get ONE MediaElementSourceNode

export function getAudioContext() {
  if (!sharedCtx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    sharedCtx = new Ctx({ latencyHint: "interactive" });
  }
  return sharedCtx;
}

/** Browsers (iOS Safari most strictly) only start audio after a user gesture: resume on the first one. */
export function unlockOnGesture(ctx = getAudioContext()) {
  if (ctx.state === "running") return Promise.resolve();
  return new Promise((resolve) => {
    const events = ["pointerdown", "touchend", "keydown", "click"];
    const unlock = () => {
      ctx.resume().then(() => {
        // iOS also wants a sound started inside the gesture: a 1-sample silent buffer is enough.
        const b = ctx.createBuffer(1, 1, ctx.sampleRate), s = ctx.createBufferSource();
        s.buffer = b; s.connect(ctx.destination); s.start(); s.onended = () => s.disconnect();
        events.forEach(e => window.removeEventListener(e, unlock, true));
        resolve();
      }).catch(() => {});
    };
    events.forEach(e => window.addEventListener(e, unlock, true));
    unlock();  // works right away if we are already inside a gesture
  });
}

/** The one MediaElementSourceNode of an <audio> element (created on first use, then reused). */
export function mediaElementSource(el, ctx = getAudioContext()) {
  if (!elementSources.has(el)) elementSources.set(el, ctx.createMediaElementSource(el));
  return elementSources.get(el);
}

export class AvatarAudio {
  constructor(ctx = getAudioContext(), { fftSize = 1024, delayMs = 0 } = {}) {
    this.ctx = ctx;
    this.input = ctx.createGain();
    this.streamGain = ctx.createGain();
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = fftSize;
    this.analyser.smoothingTimeConstant = 0;  // smoothing is done per viseme, with attack/release
    this.delay = ctx.createDelay(0.5);
    this.streamGain.connect(this.input);
    this.input.connect(this.analyser);
    this.analyser.connect(this.delay);
    this.delay.connect(ctx.destination);
    this.time = new Float32Array(this.analyser.fftSize);
    this.freq = new Float32Array(this.analyser.frequencyBinCount);
    this.sources = new Set();     // scheduled AudioBufferSourceNodes still alive
    this.attached = new Map();    // source object → its AudioNode
    this.nextStart = 0;
    this.generation = 0;          // bumped by stop(): chunks still decoding are then dropped
    this.pending = Promise.resolve();
    this.stats = { created: 0, released: 0 };  // to check for leaks: created - released = alive
    this.setDelay(delayMs);
  }

  /** ms > 0 delays the audio (mouth leads); ms < 0 is handled by the avatar as a visual lag (mouth trails). */
  setDelay(ms) {
    this.delayMs = Math.max(-150, Math.min(150, ms));
    this.delay.delayTime.setValueAtTime(Math.max(0, this.delayMs) / 1000, this.ctx.currentTime);
  }

  /** Route an existing playback through the avatar: HTMLAudioElement/HTMLVideoElement, MediaStream or AudioNode. */
  attach(source) {
    if (this.attached.has(source)) return this.attached.get(source);
    let node;
    if (typeof HTMLMediaElement !== "undefined" && source instanceof HTMLMediaElement) {
      node = mediaElementSource(source, this.ctx);
      node.disconnect();  // whatever it was connected to before: it must only be heard once, through us
    } else if (typeof MediaStream !== "undefined" && source instanceof MediaStream) {
      node = this.ctx.createMediaStreamSource(source);
    } else if (source && typeof source.connect === "function") {
      node = source;
      if (node.context !== this.ctx) throw new Error("attachAudioStream: the AudioNode belongs to another AudioContext");
    } else {
      throw new Error("attachAudioStream: expected an HTMLMediaElement, a MediaStream or an AudioNode");
    }
    node.connect(this.input);
    this.attached.set(source, node);
    return node;
  }

  detach(source) {
    const node = this.attached.get(source);
    if (!node) return;
    try { node.disconnect(this.input); } catch {}
    this.attached.delete(source);
  }

  /**
   * Queue one chunk for gapless playback. format: { type: "pcm16" | "float32" | "wav" | "mp3" | "ogg" | "encoded",
   * sampleRate, channels }. Encoded chunks must each be decodable on their own. Resolves { start, duration }.
   */
  pushChunk(chunk, format = {}) {
    const generation = this.generation;
    // Decoding is async; chaining keeps chunks in order even if a later one decodes faster.
    const job = this.pending.then(async () => {
      const buffer = await this.toBuffer(chunk, format);
      if (generation !== this.generation || !buffer) return null;  // stop() was called meanwhile
      const source = this.ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(this.streamGain);
      const start = nextStartTime(this.ctx.currentTime, this.nextStart);
      source.start(start);
      this.nextStart = start + buffer.duration;
      this.sources.add(source);
      this.stats.created += 1;
      source.onended = () => this.release(source);
      return { start, duration: buffer.duration };
    });
    this.pending = job.catch(() => null);
    return job;
  }

  async toBuffer(chunk, { type = "pcm16", sampleRate = this.ctx.sampleRate, channels = 1 } = {}) {
    if (type === "pcm16" || type === "float32") {
      const data = type === "pcm16" ? pcm16ToFloat32(chunk, channels) : deinterleave(chunk, channels);
      if (!data[0].length) return null;
      // The buffer keeps its own rate; AudioBufferSourceNode resamples to the context rate when playing.
      const buffer = this.ctx.createBuffer(channels, data[0].length, sampleRate);
      data.forEach((ch, c) => buffer.copyToChannel(ch, c));
      return buffer;
    }
    const bytes = chunk instanceof ArrayBuffer ? chunk.slice(0) : chunk.buffer.slice(chunk.byteOffset, chunk.byteOffset + chunk.byteLength);
    return this.ctx.decodeAudioData(bytes);
  }

  release(source) {
    if (!this.sources.has(source)) return;
    source.onended = null;
    try { source.disconnect(); } catch {}
    this.sources.delete(source);
    this.stats.released += 1;
  }

  /** Is queued chunk audio still playing (or about to)? */
  get queueActive() { return this.sources.size > 0 && this.nextStart > this.ctx.currentTime - 0.02; }

  /** Interrupt: fade the queue out in ~rampMs (no click), drop everything queued or still decoding. */
  stop(rampMs = 30) {
    this.generation += 1;
    const now = this.ctx.currentTime, end = now + rampMs / 1000;
    const g = this.streamGain.gain;
    g.cancelScheduledValues(now);
    g.setValueAtTime(g.value, now);
    g.linearRampToValueAtTime(0, end);
    for (const s of this.sources) { try { s.stop(end); } catch {} }
    g.setValueAtTime(1, end + 0.01);
    this.nextStart = 0;
    this.pending = Promise.resolve();
  }

  /** Fill the time and frequency buffers from the analyser (call once per frame). */
  read() {
    this.analyser.getFloatTimeDomainData(this.time);
    this.analyser.getFloatFrequencyData(this.freq);
    return { time: this.time, freq: this.freq, sampleRate: this.ctx.sampleRate };
  }

  dispose() {
    this.stop(5);
    for (const s of [...this.sources]) this.release(s);
    for (const source of [...this.attached.keys()]) this.detach(source);
    for (const n of [this.streamGain, this.input, this.analyser, this.delay]) { try { n.disconnect(); } catch {} }
  }
}
