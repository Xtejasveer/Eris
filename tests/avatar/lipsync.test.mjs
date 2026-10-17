// Run: node --test "tests/avatar/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  AdaptiveLevel, DEFAULT_TUNING, EnvelopeSmoother, VISEMES, clampWeights, classify, computeFeatures, dominant,
  openness, scheduleTargets, visemesToArkit, wordsToSchedule,
} from "../../web/js/avatar/lipsync.js";
import { LipsyncEn } from "../../web/vendor/talkinghead/lipsync-en.mjs";

const RATE = 48000, N = 1024, BINS = 512;
const binHz = RATE / 2 / BINS;

/** Analyser-like input: a sine of `amp` and a dB spectrum with energy at the given frequencies. */
function frame({ amp = 0.1, hz = 200, peaks = { 200: -20 }, noise = 0 } = {}) {
  const time = new Float32Array(N);
  for (let i = 0; i < N; i++) time[i] = amp * Math.sin((2 * Math.PI * hz * i) / RATE) + noise * (Math.random() * 2 - 1);
  const freq = new Float32Array(BINS).fill(-120);
  for (const [f, db] of Object.entries(peaks)) freq[Math.round(f / binHz)] = db;
  return computeFeatures(time, freq, RATE);
}

test("the 15 Oculus visemes", () => {
  assert.deepEqual(VISEMES, ["sil", "PP", "FF", "TH", "DD", "kk", "CH", "SS", "nn", "RR", "aa", "E", "I", "O", "U"]);
});

test("features: RMS, dB and zero-crossing rate of a sine", () => {
  const f = frame({ amp: 0.5, hz: 1000 });
  assert.ok(Math.abs(f.rms - 0.5 / Math.SQRT2) < 0.01);
  assert.ok(Math.abs(f.db - 20 * Math.log10(0.5 / Math.SQRT2)) < 0.2);
  assert.ok(Math.abs(f.zcr - (2 * 1000) / RATE) < 0.005);  // two crossings per period
});

test("features: band fractions sum to 1 and the centroid follows the energy", () => {
  const low = frame({ peaks: { 400: -20 } }), high = frame({ peaks: { 6000: -20 } });
  for (const f of [low, high]) assert.ok(Math.abs(f.low + f.mid + f.high + f.air - 1) < 1e-6);
  assert.ok(low.low > 0.99 && high.air > 0.99);
  assert.ok(low.centroid < 500 && high.centroid > 5500);
});

test("noise gate: silence is 'sil' with a closed mouth", () => {
  const c = classify(frame({ amp: 0.0005 }));
  assert.equal(c.viseme, "sil");
  assert.equal(c.open, 0);
  assert.deepEqual(c.targets, {});
});

test("openness: 0 below the gate, rises with loudness, 1 at full", () => {
  const t = DEFAULT_TUNING;
  assert.equal(openness(t.floorDb - 1, t), 0);
  assert.ok(openness(t.fullDb - 10, t) > 0 && openness(t.fullDb - 10, t) < openness(t.fullDb - 3, t));
  assert.equal(openness(t.fullDb + 5, t), 1);
});

test("adaptive level: loud voices raise 'fully open', and it relaxes back slowly", () => {
  const lvl = new AdaptiveLevel(DEFAULT_TUNING);
  const loud = lvl.step(-6, 16);
  assert.equal(loud, -6 - DEFAULT_TUNING.headroomDb);
  let later = loud;
  for (let i = 0; i < 300; i++) later = lvl.step(-40, 16);  // ~5 s of quiet
  assert.ok(later < loud && later >= DEFAULT_TUNING.fullDb);
});

test("viseme groups: hiss → fricative, low energy → rounded, high F2 → spread, else open", () => {
  const base = { db: -15, zcr: 0.02 };
  assert.equal(classify({ ...base, zcr: 0.3, centroid: 6500, low: 0.05, mid: 0.05, high: 0.2, air: 0.7 }).group, "fricative");
  assert.equal(classify({ ...base, zcr: 0.3, centroid: 6500, low: 0.05, mid: 0.05, high: 0.2, air: 0.7 }).viseme, "SS");
  assert.equal(classify({ ...base, centroid: 400, low: 0.9, mid: 0.08, high: 0.01, air: 0.01 }).group, "rounded");
  assert.equal(classify({ ...base, centroid: 2200, low: 0.3, mid: 0.4, high: 0.25, air: 0.05 }).group, "spread");
  assert.equal(classify({ ...base, centroid: 900, low: 0.6, mid: 0.3, high: 0.05, air: 0.05 }).viseme, "aa");
  assert.equal(classify({ ...base, db: -50, level: 0.05, centroid: 300, low: 0.9, mid: 0.1, high: 0, air: 0 }).group, "closed");
});

test("visemes blend with neighbours (coarticulation) and use Oculus names", () => {
  const c = classify({ db: -14, level: 0.8, zcr: 0.02, centroid: 2200, low: 0.3, mid: 0.4, high: 0.25, air: 0.05 });
  const keys = Object.keys(c.targets);
  assert.ok(keys.length >= 2, "more than one shape");
  assert.ok(keys.every(k => k.startsWith("viseme_") && VISEMES.includes(k.slice(7))));
});

test("envelope: fast attack, slower release (asymmetric)", () => {
  const s = new EnvelopeSmoother({ attackMs: 50, releaseMs: 100 });
  const up = s.step({ viseme_aa: 1 }, 50).viseme_aa;      // one attack time constant
  assert.ok(Math.abs(up - (1 - Math.exp(-1))) < 1e-9);
  const s2 = new EnvelopeSmoother({ attackMs: 50, releaseMs: 100 });
  s2.values = { viseme_aa: 1 };
  const down = s2.step({}, 50).viseme_aa;                  // half a release time constant
  assert.ok(Math.abs(down - Math.exp(-0.5)) < 1e-9);
  assert.ok(1 - down < up, "closing is slower than opening");
});

test("envelope: a released key reaches zero and is removed (no frozen mouth)", () => {
  const s = new EnvelopeSmoother({ attackMs: 50, releaseMs: 100 });
  s.step({ viseme_O: 1 }, 200);
  for (let i = 0; i < 100; i++) s.step({}, 16);
  assert.deepEqual(s.values, {});
});

test("envelope: frame-rate independent", () => {
  const a = new EnvelopeSmoother(), b = new EnvelopeSmoother();
  a.step({ viseme_E: 1 }, 40);
  b.step({ viseme_E: 1 }, 20); b.step({ viseme_E: 1 }, 20);
  assert.ok(Math.abs(a.values.viseme_E - b.values.viseme_E) < 1e-9);
});

test("clamp: per-viseme caps and a total cap keep the mouth from opening too wide", () => {
  const out = clampWeights({ viseme_aa: 1, viseme_E: 1, viseme_O: 1 }, { maxWeight: 0.85, maxTotal: 1.1, caps: { viseme_aa: 0.75 } });
  assert.ok(out.viseme_aa <= 0.75 && out.viseme_E <= 0.85);
  assert.ok(Math.abs(Object.values(out).reduce((a, b) => a + b, 0) - 1.1) < 1e-9);
  assert.equal(clampWeights({ viseme_aa: -0.2 }).viseme_aa, 0);
});

test("words → viseme schedule fills each word's time span in order", () => {
  const schedule = wordsToSchedule(["hello", "world"], [1.0, 1.5], [0.4, 0.4], new LipsyncEn());
  assert.ok(schedule.length >= 6);
  assert.ok(schedule.every(s => s.end > s.start));
  for (let i = 1; i < schedule.length; i++) assert.ok(schedule[i].start >= schedule[i - 1].start - 1e-9);
  const first = schedule.filter(s => s.start < 1.45), second = schedule.filter(s => s.start >= 1.45);
  assert.ok(Math.abs(first.at(-1).end - 1.4) < 1e-6 && Math.abs(second.at(-1).end - 1.9) < 1e-6);
  assert.ok(schedule.every(s => VISEMES.includes(s.viseme)));
});

test("words: punctuation is ignored and empty words are skipped", () => {
  const s = wordsToSchedule(["Hi,", "—", "you!"], [0, 0.3, 0.4], [0.3, 0.1, 0.3], new LipsyncEn());
  assert.ok(s.length > 0 && s.every(x => x.start < 0.3 || x.start >= 0.4));
});

test("schedule targets ramp in and out (no snapping) and silence between words is closed", () => {
  const sched = [{ viseme: "aa", start: 1.0, end: 1.2 }, { viseme: "O", start: 1.2, end: 1.4 }];
  const mid = scheduleTargets(sched, 1.1);
  assert.ok(mid.viseme_aa > 0.7);
  const edge = scheduleTargets(sched, 1.2);  // both overlap at the boundary
  assert.ok(edge.viseme_aa > 0 && edge.viseme_O > 0);
  assert.deepEqual(scheduleTargets(sched, 2.0), {});
});

test("ARKit fallback mapping: aa opens the jaw, U puckers, PP closes", () => {
  assert.ok(visemesToArkit({ viseme_aa: 1 }).jawOpen > 0.4);
  assert.ok(visemesToArkit({ viseme_U: 1 }).mouthPucker > 0.5);
  assert.ok(visemesToArkit({ viseme_PP: 1 }).mouthClose > 0.5);
  assert.ok(Object.values(visemesToArkit({ viseme_aa: 1, viseme_O: 1, viseme_E: 1 })).every(v => v <= 1));
});

test("dominant viseme for the debug overlay", () => {
  assert.equal(dominant({ viseme_aa: 0.2, viseme_O: 0.6 }), "O");
  assert.equal(dominant({ viseme_aa: 0.01 }), "sil");
});
