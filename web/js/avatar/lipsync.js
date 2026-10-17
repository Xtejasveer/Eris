// Pure lip-sync logic: audio features → visemes, smoothing, clamping, and word timings → visemes.
// No DOM and no Web Audio objects here, so it is unit tested in Node (tests/avatar/).

/** The Oculus viseme set, in the usual order. `sil` is "mouth at rest" (no blend shape needed). */
export const VISEMES = ["sil", "PP", "FF", "TH", "DD", "kk", "CH", "SS", "nn", "RR", "aa", "E", "I", "O", "U"];

export const DEFAULT_TUNING = {
  floorDb: -52,      // below this RMS level it is silence: mouth closed (noise gate)
  fullDb: -26,       // the mouth is fully open at least at this level (AdaptiveLevel raises it for loud voices)
  headroomDb: 3,     // fully open this many dB below the recent peak
  rangeDb: 20,       // the mouth opens over this many dB below "fully open"
  curve: 1.6,        // >1: ordinary syllables stay moderately open
  attackMs: 50,      // fast open
  releaseMs: 100,    // slower close
  maxWeight: 0.85,   // no single viseme above this
  caps: { viseme_aa: 0.75 },  // tighter limits for the widest shapes
  maxTotal: 1.1,     // sum of all viseme weights above this is scaled down
  jawFromOpen: 0.25, // extra jawOpen (ARKit) added in proportion to loudness
};

const BANDS = { low: [100, 700], mid: [700, 2000], high: [2000, 4000], air: [4000, 9000] };

/**
 * Per-frame features from an AnalyserNode: time-domain samples and frequency data in dB.
 * Returns { rms, db, zcr, centroid, low, mid, high, air } — band values are fractions of the 100-9000 Hz energy.
 */
export function computeFeatures(time, freqDb, sampleRate) {
  let sum = 0, crossings = 0;
  for (let i = 0; i < time.length; i++) {
    sum += time[i] * time[i];
    if (i && (time[i] >= 0) !== (time[i - 1] >= 0)) crossings++;
  }
  const rms = Math.sqrt(sum / time.length);
  const binHz = sampleRate / 2 / freqDb.length;
  const energy = { low: 0, mid: 0, high: 0, air: 0 };
  let total = 0, weighted = 0;
  for (let b = 0; b < freqDb.length; b++) {
    const hz = (b + 0.5) * binHz;
    if (hz < 100 || hz > 9000) continue;
    // dB → power, then pre-emphasis (+6 dB/octave, i.e. power × f²): without it the voice's fundamental
    // (~100-250 Hz) dominates and every vowel looks the same. With it, the formants decide.
    const p = Math.pow(10, freqDb[b] / 10) * (hz / 1000) * (hz / 1000);
    if (!Number.isFinite(p)) continue;
    total += p; weighted += p * hz;
    for (const [band, [lo, hi]] of Object.entries(BANDS)) if (hz >= lo && hz < hi) energy[band] += p;
  }
  const frac = (x) => (total > 0 ? x / total : 0);
  return {
    rms, db: 20 * Math.log10(rms + 1e-9), zcr: crossings / time.length,
    centroid: total > 0 ? weighted / total : 0,
    low: frac(energy.low), mid: frac(energy.mid), high: frac(energy.high), air: frac(energy.air),
  };
}

/**
 * How open the mouth should be (0-1) from loudness. Below floorDb: 0 (noise gate). The mouth opens over the top
 * rangeDb below fullDb (which AdaptiveLevel keeps near the voice's recent peak), on a gentle curve, so ordinary
 * syllables are half open and only the loudest are fully open.
 */
export function openness(db, tuning = DEFAULT_TUNING, fullDb = tuning.fullDb) {
  if (db <= tuning.floorDb) return 0;
  const lo = Math.max(tuning.floorDb, fullDb - tuning.rangeDb);
  const x = Math.max(0, Math.min(1, (db - lo) / Math.max(3, fullDb - lo)));
  return Math.max(0.02, Math.pow(x, tuning.curve));  // a voiced but very quiet sound stays just above 0
}

/**
 * Voices and volumes differ a lot, so "fully open" follows the recent loudness peak: it jumps up on a loud
 * syllable and drifts down slowly (~2 s) in quieter speech. Never below fullDb (a fixed minimum).
 */
export class AdaptiveLevel {
  constructor(tuning = DEFAULT_TUNING) { this.tuning = tuning; this.peakDb = tuning.fullDb; }

  /** Feed one frame's dB; returns the dB that counts as "fully open" right now. */
  step(db, dtMs) {
    if (db > this.peakDb) this.peakDb = db;
    else this.peakDb += (this.tuning.fullDb - this.peakDb) * (1 - Math.exp(-dtMs / 2000));
    return Math.max(this.tuning.fullDb, this.peakDb - this.tuning.headroomDb);
  }
}

/**
 * Classify one frame into a viseme group and spread it onto Oculus viseme targets.
 * Groups: sil (silence), closed (PP / nn), fricative (SS / CH / FF / TH), rounded (O / U), spread (E / I), open (aa).
 * Returns { viseme, group, open, targets: { viseme_xx: weight } }.
 */
export function classify(f, tuning = DEFAULT_TUNING) {
  const open = f.level ?? openness(f.db, tuning);  // f.level: adaptive loudness from the caller, if any
  if (open === 0) return { viseme: "sil", group: "sil", open: 0, targets: {} };
  // Thresholds are for pre-emphasized band fractions (see computeFeatures), measured on TTS speech.
  const hiss = f.high + f.air;
  let viseme, group;
  if (hiss > 0.6 && f.zcr > 0.08) {
    group = "fricative";
    viseme = f.centroid > 5500 ? "SS" : f.centroid > 3500 ? "CH" : open < 0.35 ? "TH" : "FF";
  } else if (open < 0.15) {
    group = "closed";                       // quiet voiced sound: lips (nearly) together
    viseme = f.centroid < 500 ? "nn" : "PP";
  } else if (f.low > 0.8) {
    group = "rounded";                      // energy only below 700 Hz: low F1 and F2, rounded lips
    viseme = open < 0.5 ? "U" : "O";
  } else if (f.mid + f.high > 0.35 && f.centroid > 1200) {
    group = "spread";                       // high second formant: front vowels, lips spread
    viseme = f.high > f.mid ? "I" : "E";
  } else {
    group = "open";
    viseme = "aa";
  }
  return { viseme, group, open, targets: spread(viseme, group, open) };
}

// A group never shows only one shape: blending neighbours approximates coarticulation.
function spread(viseme, group, open) {
  const t = {};
  const add = (v, w) => { if (w > 0) t[`viseme_${v}`] = (t[`viseme_${v}`] || 0) + w; };
  switch (group) {
    case "open": add(viseme, 0.55 + 0.45 * open); add("aa", viseme === "aa" ? 0 : 0.3 * open); break;
    case "spread": add(viseme, 0.5 + 0.4 * open); add("aa", 0.25 * open); break;
    case "rounded": add(viseme, 0.55 + 0.35 * open); add("aa", 0.2 * open); break;
    case "fricative": add(viseme, 0.65); add("E", 0.15 * open); break;
    case "closed": add(viseme, 0.6); break;
  }
  return t;
}

/**
 * Asymmetric attack/release smoothing per key: rises with time constant attackMs, falls with releaseMs.
 * Keys that disappear from the targets fall back to 0 (released), so the mouth never freezes open.
 */
export class EnvelopeSmoother {
  constructor({ attackMs = DEFAULT_TUNING.attackMs, releaseMs = DEFAULT_TUNING.releaseMs } = {}) {
    this.attackMs = attackMs; this.releaseMs = releaseMs;
    this.values = {};
  }

  step(targets, dtMs) {
    const keys = new Set([...Object.keys(this.values), ...Object.keys(targets)]);
    for (const k of keys) {
      const cur = this.values[k] || 0, target = targets[k] || 0;
      const tau = target > cur ? this.attackMs : this.releaseMs;
      const next = cur + (target - cur) * (1 - Math.exp(-dtMs / tau));
      if (next < 1e-4 && target === 0) delete this.values[k]; else this.values[k] = next;
    }
    return this.values;
  }

  /** Ease everything to rest quickly (interruption): a short release time for a while. */
  reset() { this.values = {}; }
}

/** Clamp weights so the mouth never looks unnaturally wide: per-key max and a cap on the total. */
export function clampWeights(values, { maxWeight = DEFAULT_TUNING.maxWeight, maxTotal = DEFAULT_TUNING.maxTotal, caps = DEFAULT_TUNING.caps } = {}) {
  const out = {};
  let total = 0;
  for (const [k, v] of Object.entries(values)) { out[k] = Math.max(0, Math.min(caps?.[k] ?? maxWeight, v)); total += out[k]; }
  if (total > maxTotal) for (const k of Object.keys(out)) out[k] *= maxTotal / total;
  return out;
}

/**
 * Words with timings → a viseme schedule [{ viseme, start, end }] in seconds.
 * lipsync: an object with wordsToVisemes(word) → { visemes, times, durations } (TalkingHead's LipsyncEn).
 * times/durations are in seconds, relative to the same clock as the returned schedule.
 */
export function wordsToSchedule(words, times, durations, lipsync) {
  const out = [];
  words.forEach((word, i) => {
    const clean = String(word).replace(/[^\p{L}\p{N}']/gu, "");
    if (!clean) return;
    const v = lipsync.wordsToVisemes(lipsync.preProcessText ? lipsync.preProcessText(clean) : clean);
    if (!v || !v.visemes.length) return;
    const last = v.visemes.length - 1;
    const units = v.times[last] + v.durations[last];
    const scale = durations[i] / (units || 1);
    v.visemes.forEach((vis, j) => out.push({ viseme: vis, start: times[i] + v.times[j] * scale, end: times[i] + (v.times[j] + v.durations[j]) * scale }));
  });
  return out;
}

/**
 * Viseme targets at clock time t from a schedule: each viseme ramps in and out over `blendS` seconds,
 * so neighbouring visemes overlap instead of snapping.
 */
export function scheduleTargets(schedule, t, blendS = 0.06, weight = 0.75) {
  const targets = {};
  for (const item of schedule) {
    if (t < item.start - blendS || t > item.end + blendS) continue;
    const rampIn = Math.min(1, (t - (item.start - blendS)) / (2 * blendS));
    const rampOut = Math.min(1, (item.end + blendS - t) / (2 * blendS));
    const w = weight * Math.max(0, Math.min(rampIn, rampOut));
    if (item.viseme === "sil" || w <= 0) continue;
    const key = `viseme_${item.viseme}`;
    targets[key] = Math.max(targets[key] || 0, w);
  }
  return targets;
}

/** ARKit fallback for models without Oculus visemes: rough mouth shapes from ARKit blend shapes. */
export const ARKIT_FROM_VISEME = {
  viseme_PP: { mouthClose: 0.6, mouthPressLeft: 0.3, mouthPressRight: 0.3 },
  viseme_FF: { mouthRollLower: 0.5, mouthUpperUpLeft: 0.2, mouthUpperUpRight: 0.2, jawOpen: 0.08 },
  viseme_TH: { jawOpen: 0.12, mouthStretchLeft: 0.1, mouthStretchRight: 0.1 },
  viseme_DD: { jawOpen: 0.2, mouthStretchLeft: 0.15, mouthStretchRight: 0.15 },
  viseme_kk: { jawOpen: 0.25, mouthStretchLeft: 0.1, mouthStretchRight: 0.1 },
  viseme_CH: { jawOpen: 0.15, mouthFunnel: 0.4, mouthShrugUpper: 0.2 },
  viseme_SS: { jawOpen: 0.08, mouthStretchLeft: 0.3, mouthStretchRight: 0.3 },
  viseme_nn: { jawOpen: 0.12, mouthClose: 0.15 },
  viseme_RR: { jawOpen: 0.15, mouthFunnel: 0.3 },
  viseme_aa: { jawOpen: 0.55 },
  viseme_E: { jawOpen: 0.3, mouthStretchLeft: 0.3, mouthStretchRight: 0.3 },
  viseme_I: { jawOpen: 0.18, mouthSmileLeft: 0.25, mouthSmileRight: 0.25, mouthStretchLeft: 0.2, mouthStretchRight: 0.2 },
  viseme_O: { jawOpen: 0.35, mouthFunnel: 0.5 },
  viseme_U: { jawOpen: 0.15, mouthPucker: 0.7 },
};

/** Convert Oculus viseme weights to ARKit weights (sum of contributions, clamped to 1). */
export function visemesToArkit(weights) {
  const out = {};
  for (const [vis, w] of Object.entries(weights)) {
    for (const [shape, s] of Object.entries(ARKIT_FROM_VISEME[vis] || {})) out[shape] = Math.min(1, (out[shape] || 0) + w * s);
  }
  return out;
}

/** The strongest viseme in a set of weights (for the debug overlay). */
export function dominant(weights) {
  let best = "sil", max = 0.05;
  for (const [k, v] of Object.entries(weights)) if (v > max) { max = v; best = k.replace("viseme_", ""); }
  return best;
}
