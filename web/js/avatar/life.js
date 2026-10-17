// "Alive" behaviour, independent of rendering: blinks, eye saccades, head sway and breathing, speech nods,
// brow raises on emphasis, and mood. update() returns morph weights and small bone rotations (radians).
// Everything is deliberately subtle: exaggerated motion looks uncanny.

import { fbm } from "./noise.js";

export const MOODS = {
  neutral: {},
  happy: { mouthSmileLeft: 0.28, mouthSmileRight: 0.28, cheekSquintLeft: 0.12, cheekSquintRight: 0.12, eyeSquintLeft: 0.06, eyeSquintRight: 0.06 },
  thinking: { browInnerUp: 0.18, browDownLeft: 0.08, mouthPressLeft: 0.12, mouthPressRight: 0.12, mouthRollLower: 0.06 },
};
const MOOD_GAZE = { neutral: [0, 0], happy: [0, 0], thinking: [0.12, 0.08] };  // [yaw, pitch] bias of the eyes

const rand = (a, b) => a + Math.random() * (b - a);
const approach = (cur, target, dt, tauMs) => cur + (target - cur) * (1 - Math.exp(-dt / tauMs));

export class Life {
  constructor({ intensity = 1 } = {}) {
    this.intensity = intensity;  // 0 = still, 1 = default, >1 = livelier
    this.t = 0;
    this.seed = Math.floor(Math.random() * 1000);
    this.nextBlink = rand(1, 3);
    this.blinkStart = -1;
    this.doubleBlink = false;
    this.nextSaccade = rand(0.5, 2);
    this.gazeTarget = [0, 0];
    this.gaze = [0, 0];
    this.speaking = 0;           // 0..1, eased: smooth idle <-> speaking transitions
    this.avgLevel = 0;
    this.nod = 0; this.nodVel = 0;
    this.brow = 0;
    this.lastEmphasis = -10;
    this.mood = "neutral";
    this.moodWeights = {};
  }

  setMood(mood) { this.mood = MOODS[mood] ? mood : "neutral"; }

  /** A phrase ended (a pause in speech): blink a bit more often there, like people do. */
  phraseBoundary() {
    if (Math.random() < 0.45 && this.nextBlink - this.t > 0.4) this.nextBlink = this.t + rand(0.05, 0.3);
  }

  /**
   * dtMs: frame time. level: speech loudness 0..1 (mouth openness). speaking: is the avatar talking.
   * Returns { morphs, head: [pitch, yaw, roll], neck: [...], spine: [...], emphasis }.
   */
  update(dtMs, { level = 0, speaking = false } = {}) {
    const dt = dtMs / 1000;
    this.t += dt;
    const t = this.t, k = this.intensity;
    this.speaking = approach(this.speaking, speaking ? 1 : 0, dtMs, 300);
    const morphs = {};

    // ---- blinks: every 2-6 s, ~150 ms (close fast, open slower), sometimes twice ----
    if (t >= this.nextBlink && this.blinkStart < 0) { this.blinkStart = t; this.doubleBlink = Math.random() < 0.15; }
    if (this.blinkStart >= 0) {
      const p = (t - this.blinkStart) / 0.15;
      const closed = p < 0.4 ? p / 0.4 : Math.max(0, 1 - (p - 0.4) / 0.6);
      morphs.eyeBlinkLeft = morphs.eyeBlinkRight = Math.min(1, closed);
      if (p >= 1) {
        this.blinkStart = -1;
        this.nextBlink = this.doubleBlink ? t + 0.12 : t + rand(2, 6);
        this.doubleBlink = false;
      }
    }

    // ---- eyes: small saccades, mostly at the camera (the student), now and then a short glance away ----
    if (t >= this.nextSaccade) {
      const away = Math.random() < 0.18;
      const r = away ? 0.22 : 0.06;
      const [by, bp] = MOOD_GAZE[this.mood];
      this.gazeTarget = [by + rand(-r, r), bp + rand(-r, r) * 0.6];
      this.nextSaccade = t + (away ? rand(0.4, 0.9) : rand(0.8, 3));
    }
    this.gaze = this.gaze.map((g, i) => approach(g, this.gazeTarget[i], dtMs, 35));  // saccades are fast
    const [yaw, pitch] = this.gaze;
    // yaw > 0: looking to the avatar's left. ARKit: "In" = toward the nose, "Out" = away from it.
    morphs.eyeLookOutLeft = Math.max(0, yaw); morphs.eyeLookInRight = Math.max(0, yaw);
    morphs.eyeLookInLeft = Math.max(0, -yaw); morphs.eyeLookOutRight = Math.max(0, -yaw);
    morphs.eyeLookUpLeft = morphs.eyeLookUpRight = Math.max(0, pitch);
    morphs.eyeLookDownLeft = morphs.eyeLookDownRight = Math.max(0, -pitch);

    // ---- speech emphasis: a loud syllable well above the running average → small nod + brow raise ----
    this.avgLevel = approach(this.avgLevel, level, dtMs, 800);
    let emphasis = false;
    if (speaking && level > 0.55 && level > this.avgLevel * 1.6 && t - this.lastEmphasis > 0.6) {
      emphasis = true;
      this.lastEmphasis = t;
      this.nodVel += 0.35 * k;        // a nod impulse (spring below brings it back)
      this.brow = Math.min(1, this.brow + 0.6);
    }
    // damped spring for the nod
    const stiffness = 60, damping = 11;
    this.nodVel += (-stiffness * this.nod - damping * this.nodVel) * dt;
    this.nod += this.nodVel * dt;
    this.brow = approach(this.brow, 0, dtMs, 350);
    const browUp = 0.22 * this.brow + 0.06 * level * this.speaking;
    morphs.browInnerUp = browUp;
    morphs.browOuterUpLeft = morphs.browOuterUpRight = browUp * 0.7;

    // ---- mood: blend towards the mood's expression over ~0.4 s ----
    const goal = MOODS[this.mood];
    for (const key of new Set([...Object.keys(this.moodWeights), ...Object.keys(goal)])) {
      this.moodWeights[key] = approach(this.moodWeights[key] || 0, goal[key] || 0, dtMs, 400);
      morphs[key] = (morphs[key] || 0) + this.moodWeights[key];
    }

    // ---- head: slow noise sway + breathing; while speaking, a little more motion tied to loudness ----
    const s = 1 + 0.6 * this.speaking;
    const breath = Math.sin((t / 4.2) * Math.PI * 2);
    const head = [
      k * (0.022 * s * fbm(t * 0.17, this.seed) + 0.006 * breath + 0.05 * this.nod),  // pitch (nod)
      k * 0.035 * s * fbm(t * 0.13, this.seed + 3),                                     // yaw (turn)
      k * (0.02 * s * fbm(t * 0.11, this.seed + 7) + 0.012 * this.speaking * level),    // roll (tilt)
    ];
    const neck = head.map(v => v * 0.4);
    const spine = [k * 0.01 * breath, 0, 0];
    return { morphs, head, neck, spine, emphasis };
  }
}
