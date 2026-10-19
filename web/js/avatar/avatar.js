// The talking avatar: a Three.js head-and-shoulders view of a GLB with ARKit and/or Oculus viseme blend shapes,
// lip-synced to the audio it plays (or taps), with blinks, eye saccades, head sway and moods.
//
//   const avatar = await createAvatar({ container, modelUrl, options });
//   avatar.attachAudioStream(audioElementOrStreamOrNode);
//   avatar.pushAudioChunk(chunk, { type: "pcm16", sampleRate: 48000, channels: 1 });
//   avatar.setTimestamps({ words, times, durations });   // optional, times in ms
//   avatar.stop(); avatar.setMood("happy"); avatar.dispose();
//   events: "ready", "speechstart", "speechend", "error"

import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import { LipsyncEn } from "../../vendor/talkinghead/lipsync-en.mjs";
import { AvatarAudio, getAudioContext, unlockOnGesture } from "./audio-engine.js";
import {
  AdaptiveLevel, DEFAULT_TUNING, VISEMES, classify, clampWeights, computeFeatures, dominant, EnvelopeSmoother,
  jawFrom, openness, scheduleTargets, visemesToArkit, wordsToSchedule,
} from "./lipsync.js";

// Lips move a little before the sound they make, so timed visemes are shown this much ahead of the audio.
const LIP_LEAD_S = 0.04;
import { Life } from "./life.js";

export const DEFAULT_MODEL_URL = new URL("../../assets/avatars/mpfb.glb", import.meta.url).href;

const DEFAULTS = {
  background: null,        // null = transparent canvas, or any CSS colour
  maxPixelRatio: 2,        // caps rendering resolution on high-DPI phones
  delayMs: 0,              // audio delay compensation, -150..150
  mood: "neutral",
  lifeIntensity: 1,
  tuning: {},              // overrides of DEFAULT_TUNING (lip sync)
  fov: 22,
  armsDown: true,          // lower T/A-pose arms out of the shot
  // Viseme shapes on meshes whose name matches a key are scaled by its value. Many avatars move a separate
  // tongue mesh so far forward in "aa"/"O" that it shows past the teeth; damping it looks natural.
  meshVisemeScale: { tongue: 0.3 },
};

export async function createAvatar({ container, modelUrl = DEFAULT_MODEL_URL, options = {} } = {}) {
  const avatar = new Avatar(container, modelUrl, options);
  await avatar.load();
  return avatar;
}

class Avatar extends EventTarget {
  constructor(container, modelUrl, options) {
    super();
    this.container = container;
    this.modelUrl = modelUrl;
    this.opts = { ...DEFAULTS, ...options };
    this.tuning = { ...DEFAULT_TUNING, ...this.opts.tuning };
    this.ctx = options.audioContext || getAudioContext();
    unlockOnGesture(this.ctx);
    this.audio = new AvatarAudio(this.ctx, { delayMs: this.opts.delayMs });
    this.smoother = new EnvelopeSmoother(this.tuning);
    this.levelTracker = new AdaptiveLevel(this.tuning);
    this.life = new Life({ intensity: this.opts.lifeIntensity });
    this.life.setMood(this.opts.mood);
    this.lipsync = new LipsyncEn();
    this.schedule = [];          // viseme schedule from timestamps: { viseme, start, end } (seconds, scheduleClock)
    this.scheduleClock = "audio";
    this.lagFrames = [];         // for negative delay: lip targets waiting to be shown
    this.morphs = new Map();     // blend shape name → [{ mesh, index }]
    this.driven = new Set();     // blend shapes set at least once (reset to 0 when not driven)
    this.bones = {};
    this.speaking = false;
    this.lastVoice = -1;
    this.fastRelease = 0;        // ms left of quick mouth release after stop()
    this.debug = { fps: 0, viseme: "sil", rms: 0, db: -100, mode: "idle", level: 0 };
    this._frames = 0; this._fpsT = performance.now();
    this.running = false;
    this.disposed = false;

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.opts.maxPixelRatio));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.domElement.className = "avatar-canvas";
    this.renderer.domElement.style.cssText = "display:block;width:100%;height:100%";
    container.append(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.setBackground(this.opts.background);
    this.camera = new THREE.PerspectiveCamera(this.opts.fov, 1, 0.05, 20);
    this.addLights();

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.onVisibility = () => (document.hidden ? this.pause() : this.resume());
    document.addEventListener("visibilitychange", this.onVisibility);
  }

  // ---------- setup ----------

  addLights() {
    // Soft three-point lighting: warm key, cool fill, rim from behind, plus a little sky light.
    this.scene.add(new THREE.HemisphereLight(0xf2f0ff, 0x3a3530, 0.7));
    const key = new THREE.DirectionalLight(0xfff1e0, 1.7); key.position.set(1.2, 1.6, 2.2);
    const fill = new THREE.DirectionalLight(0xdfe8ff, 0.6); fill.position.set(-1.6, 0.6, 1.6);
    const rim = new THREE.DirectionalLight(0xffffff, 1.1); rim.position.set(0, 1.8, -2);
    this.scene.add(key, fill, rim);
  }

  setBackground(bg) {
    this.scene.background = bg ? new THREE.Color(bg) : null;
    this.renderer.setClearColor(0x000000, bg ? 1 : 0);
  }

  async load() {
    try {
      const loader = new GLTFLoader();
      loader.setMeshoptDecoder(MeshoptDecoder);
      const gltf = await loader.loadAsync(this.modelUrl);
      if (this.disposed) return;
      this.model = gltf.scene;
      this.scene.add(this.model);
      this.model.traverse((o) => {
        if (o.isMesh || o.isSkinnedMesh) o.frustumCulled = false;  // skinned/morphed bounds are unreliable
        if (o.morphTargetDictionary) {
          for (const [name, index] of Object.entries(o.morphTargetDictionary)) {
            if (!this.morphs.has(name)) this.morphs.set(name, []);
            let scale = 1;
            if (name.startsWith("viseme_")) {
              for (const [pattern, s] of Object.entries(this.opts.meshVisemeScale || {})) if (new RegExp(pattern, "i").test(o.name)) scale = s;
            }
            this.morphs.get(name).push({ mesh: o, index, scale });
          }
        }
        if (o.isBone) this.bones[o.name] = o;
      });
      this.hasVisemes = VISEMES.slice(1).filter(v => this.morphs.has(`viseme_${v}`)).length >= 10;
      this.hasArkit = this.morphs.has("jawOpen");
      if (!this.hasVisemes && !this.hasArkit) throw new Error("the model has neither Oculus viseme nor ARKit blend shapes");
      this.rest = {};
      for (const name of ["Head", "Neck", "Spine2", "Spine1"]) if (this.bones[name]) this.rest[name] = this.bones[name].quaternion.clone();
      if (this.opts.armsDown) this.lowerArms();
      this.frame();
      this.resize();
      this.resume();
      this.dispatchEvent(new CustomEvent("ready", { detail: { visemes: this.hasVisemes, arkit: this.hasArkit } }));
    } catch (error) {
      this.dispatchEvent(new CustomEvent("error", { detail: error }));
      throw error;
    }
  }

  /** Rotate the upper arms down from a T/A-pose so they don't stick out of a head-and-shoulders shot. */
  lowerArms() {
    for (const [name, sign] of [["LeftArm", 1], ["RightArm", -1]]) {
      const bone = this.bones[name];
      if (!bone) continue;
      // Rotate in world space around the forward (Z) axis, so it works whatever the bone's local axes are.
      const parentQ = bone.parent.getWorldQuaternion(new THREE.Quaternion());
      const worldTurn = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), -sign * 1.1);
      const local = parentQ.clone().invert().multiply(worldTurn).multiply(parentQ);
      bone.quaternion.premultiply(local);
    }
    this.model.updateMatrixWorld(true);
  }

  /** Head-and-shoulders framing measured from the model: from just above the hair down to the upper chest. */
  frame() {
    this.model.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(this.model);
    const top = box.max.y;
    const neckY = (this.bones.Neck || this.bones.Head)?.getWorldPosition(new THREE.Vector3()).y ?? top - 0.25;
    const x = this.bones.Head ? this.bones.Head.getWorldPosition(new THREE.Vector3()).x : (box.min.x + box.max.x) / 2;
    const z = this.bones.Head ? this.bones.Head.getWorldPosition(new THREE.Vector3()).z : (box.min.z + box.max.z) / 2;
    const headH = top - neckY;                          // neck to top of head (hair included)
    const frameTop = top + 0.12 * headH, frameBottom = neckY - 1.0 * headH;
    const center = (frameTop + frameBottom) / 2, half = (frameTop - frameBottom) / 2;
    this.frameHalf = half;
    this.lookTarget = new THREE.Vector3(x, center, z);
    this.camera.position.set(x, center + 0.02, z + half / Math.tan(THREE.MathUtils.degToRad(this.opts.fov / 2)));
    this.camera.lookAt(this.lookTarget);
  }

  resize() {
    const w = this.container.clientWidth || 1, h = this.container.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    // On tall/narrow containers widen the view so the shoulders still fit.
    this.camera.fov = this.opts.fov * (this.camera.aspect < 0.8 ? 0.8 / this.camera.aspect : 1);
    this.camera.updateProjectionMatrix();
  }

  // ---------- public API ----------

  attachAudioStream(source) { return this.audio.attach(source); }
  detachAudioStream(source) { this.audio.detach(source); }
  pushAudioChunk(chunk, format) { return this.audio.pushChunk(chunk, format); }

  /**
   * Timings for the speech that is (about to be) heard. Accepts
   *   { words, times, durations }            times/durations in ms
   *   { visemes, vtimes, vdurations }        Oculus viseme names without the "viseme_" prefix
   * Optional `levels` (0-1 per word) make louder words open wider.
   * opts.start: when time 0 is — an AudioContext time (seconds, default: now on the audio clock);
   * opts.clock: "audio" (AudioContext.currentTime), "perf" (performance.now(), for speech we can't route) or
   *   "media": times are positions in `opts.media` (an <audio> element), which keeps pause/resume in sync.
   */
  setTimestamps(data, { start, clock = "audio", media = null } = {}) {
    if (clock === "media") { this.media = media; this.mediaClock = null; }
    const now = this.clockTime(clock, performance.now());
    const t0 = start ?? (clock === "media" ? 0 : now);
    let schedule;
    if (data.visemes) {
      schedule = data.visemes.map((v, i) => ({ viseme: v, start: t0 + data.vtimes[i] / 1000, end: t0 + (data.vtimes[i] + data.vdurations[i]) / 1000 }));
    } else {
      schedule = wordsToSchedule(data.words, data.times.map(t => t0 + t / 1000), data.durations.map(d => d / 1000), this.lipsync, data.levels);
    }
    if (clock !== this.scheduleClock || clock === "media") this.schedule = [];  // a media schedule is one whole clip
    this.scheduleClock = clock;
    const cutoff = now - 1;
    this.schedule = this.schedule.filter(s => s.end > cutoff).concat(schedule);
    return schedule.length;
  }

  /**
   * Now, on a schedule clock, in seconds. "media": what is being HEARD of the clip: the element's position
   * (smoothed between its coarse updates) minus our audio delay and the device's output latency (large on
   * Bluetooth), plus the lip lead.
   */
  clockTime(clock, nowMs) {
    if (clock === "audio") return this.ctx.currentTime;
    if (clock === "perf") return nowMs / 1000;
    const m = this.media;
    if (!m) return -1;
    const pos = m.currentTime;
    let c = this.mediaClock;
    if (!c || pos !== c.pos || m.paused) c = this.mediaClock = { pos, at: nowMs };
    const est = m.paused ? pos : Math.min(pos + 0.25, c.pos + ((nowMs - c.at) / 1000) * (m.playbackRate || 1));
    // Output latency is ~10-40 ms on speakers, up to ~300 ms on Bluetooth; browsers can report nonsense for a
    // moment while audio starts, so it is capped.
    const device = Math.min(0.4, Math.max(0, (this.ctx.outputLatency || 0) + (this.ctx.baseLatency || 0)));
    const latency = device + Math.max(0, this.audio.delayMs) / 1000;
    return est - latency + LIP_LEAD_S;
  }

  /** Forget timed visemes (a new clip starts): lips follow the audio itself until new timings arrive. */
  clearTimestamps() { this.schedule = []; this.media = null; }

  /** Interrupt: stop queued audio (fade ~30 ms), drop timings, mouth back to rest in ~150 ms. */
  stop() {
    this.audio.stop(30);
    this.schedule = [];
    this.media = null;
    this.lagFrames = [];
    this.fastRelease = 200;
    this.setSpeaking(false);
  }

  setMood(mood) { this.life.setMood(mood); }
  setDelay(ms) { this.audio.setDelay(ms); }
  get delayMs() { return this.audio.delayMs; }

  pause() { this.running = false; cancelAnimationFrame(this.raf); }

  resume() {
    if (this.running || this.disposed || !this.model || document.hidden) return;
    this.running = true;
    this.last = performance.now();
    const tick = (now) => {
      if (!this.running) return;
      this.raf = requestAnimationFrame(tick);
      const dt = Math.min(100, now - this.last);  // a long gap (tab switch) must not make a jump
      this.last = now;
      this.update(dt, now);
      this.renderer.render(this.scene, this.camera);
    };
    this.raf = requestAnimationFrame(tick);
  }

  dispose() {
    this.disposed = true;
    this.pause();
    this.resizeObserver.disconnect();
    document.removeEventListener("visibilitychange", this.onVisibility);
    this.audio.dispose();
    this.scene.traverse((o) => {
      o.geometry?.dispose();
      for (const m of [].concat(o.material || [])) {
        for (const v of Object.values(m)) if (v && v.isTexture) v.dispose();
        m.dispose();
      }
    });
    this.renderer.dispose();
    this.renderer.forceContextLoss();  // free the WebGL context now (browsers allow only ~16 at once)
    this.renderer.domElement.remove();
  }

  // ---------- per frame ----------

  update(dtMs, nowMs) {
    // Lips: timestamps when we have them for "now", otherwise the audio itself.
    const { time, freq, sampleRate } = this.audio.read();
    const f = computeFeatures(time, freq, sampleRate);
    const fullDb = this.levelTracker.step(f.db, dtMs);
    const level = openness(f.db, this.tuning, fullDb);
    f.level = level;
    const clockNow = this.clockTime(this.scheduleClock, nowMs);
    const timed = this.schedule.length && this.schedule.some(s => clockNow >= s.start - 0.1 && clockNow <= s.end + 0.1);
    let targets = {}, mode = "idle";
    if (timed) {
      mode = "timestamps";
      targets = scheduleTargets(this.schedule, clockNow);
      // Rough timings (live word events) are gated by the audio's own silences. Clip timings are measured on
      // the audio itself, and the analyser runs ahead of what is heard by the output latency, so they aren't.
      if (this.scheduleClock !== "media" && (this.audio.attached.size || this.audio.queueActive)) {
        const gate = level > 0 ? 1 : 0.15;
        for (const k of Object.keys(targets)) targets[k] *= gate;
      }
    } else if (level > 0 && !(this.scheduleClock === "media" && this.media && this.schedule.length)) {
      // (A clip with measured timings stays closed between its words: what the analyser hears there is breath.)
      mode = "audio";
      targets = classify(f, this.tuning).targets;
    }
    if (this.scheduleClock !== "media" && this.schedule.length && this.schedule[this.schedule.length - 1].end < clockNow - 1) this.schedule = [];

    // Negative delay compensation: show lip targets |delay| ms later than we compute them.
    const lag = Math.max(0, -this.audio.delayMs);
    if (lag > 0) {
      this.lagFrames.push({ t: nowMs, targets, level });
      while (this.lagFrames.length > 1 && this.lagFrames[1].t <= nowMs - lag) this.lagFrames.shift();
      const shown = this.lagFrames[0].t <= nowMs - lag ? this.lagFrames[0] : { targets: {}, level: 0 };
      targets = shown.targets;
    } else if (this.lagFrames.length) this.lagFrames = [];

    if (this.fastRelease > 0) {  // after stop(): close the mouth within ~150 ms
      this.fastRelease -= dtMs;
      this.smoother.releaseMs = 40;
      targets = {};
    } else this.smoother.releaseMs = this.tuning.releaseMs;
    const lips = clampWeights(this.smoother.step(targets, dtMs), this.tuning);
    const lipLevel = Math.min(1, Object.values(lips).reduce((a, b) => a + b, 0));

    // Speaking state with a short hangover, so a breath between words isn't "speech end".
    const voiced = mode !== "idle" && lipLevel > 0.05;
    if (voiced) this.lastVoice = nowMs;
    if (voiced && !this.speaking) this.setSpeaking(true);
    if (!voiced && this.speaking && nowMs - this.lastVoice > 400) { this.setSpeaking(false); this.life.phraseBoundary(); }
    if (!voiced && this.wasVoiced && nowMs - this.lastVoice > 150) this.life.phraseBoundary();
    this.wasVoiced = voiced;

    const life = this.life.update(dtMs, { level: lipLevel, speaking: this.speaking });
    const weights = { ...life.morphs };
    const mouth = this.hasVisemes ? lips : visemesToArkit(lips);
    for (const [k, v] of Object.entries(mouth)) weights[k] = (weights[k] || 0) + v;
    if (this.hasVisemes && this.morphs.has("jawOpen")) weights.jawOpen = (weights.jawOpen || 0) + jawFrom(lips) * this.tuning.jawFromOpen;
    this.applyMorphs(weights);
    this.applyBones(life);

    this.debug = { ...this.debug, viseme: dominant(lips), rms: f.rms, db: f.db, mode, level: lipLevel, features: f };
    this._frames++;
    if (nowMs - this._fpsT >= 500) { this.debug.fps = Math.round((this._frames * 1000) / (nowMs - this._fpsT)); this._frames = 0; this._fpsT = nowMs; }
  }

  setSpeaking(on) {
    if (on === this.speaking) return;
    this.speaking = on;
    this.dispatchEvent(new CustomEvent(on ? "speechstart" : "speechend"));
  }

  applyMorphs(weights) {
    for (const name of this.driven) if (!(name in weights)) weights[name] = 0;
    for (const [name, value] of Object.entries(weights)) {
      const targets = this.morphs.get(name);
      if (!targets) continue;
      this.driven.add(name);
      const v = Math.max(0, Math.min(1, value));
      for (const { mesh, index, scale } of targets) mesh.morphTargetInfluences[index] = v * scale;
    }
  }

  applyBones({ head, neck, spine }) {
    const set = (name, [pitch, yaw, roll]) => {
      const bone = this.bones[name], rest = this.rest[name];
      if (!bone || !rest) return;
      bone.quaternion.copy(rest).multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(pitch, yaw, roll, "YXZ")));
    };
    set("Head", head); set("Neck", neck); set("Spine2", spine);
  }
}
