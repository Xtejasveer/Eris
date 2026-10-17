// Run: node --test "tests/avatar/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";
import { fbm, noise1 } from "../../web/js/avatar/noise.js";
import { Life } from "../../web/js/avatar/life.js";

test("noise is smooth, bounded and zero at integers", () => {
  for (let i = 0; i < 5; i++) assert.ok(Math.abs(noise1(i, 3)) < 1e-12);  // may be -0
  let maxStep = 0;
  for (let x = 0; x < 20; x += 0.01) {
    const v = noise1(x, 7);
    assert.ok(Math.abs(v) <= 0.75);
    maxStep = Math.max(maxStep, Math.abs(noise1(x + 0.01, 7) - v));
  }
  assert.ok(maxStep < 0.05, "no jumps");
  for (let x = 0; x < 50; x += 0.37) assert.ok(Math.abs(fbm(x, 1)) <= 1.5);
});

test("noise is deterministic per seed and differs between seeds", () => {
  assert.equal(noise1(3.3, 5), noise1(3.3, 5));
  assert.notEqual(noise1(3.3, 5), noise1(3.3, 6));
});

function run(life, seconds, opts = {}) {
  const frames = [];
  for (let t = 0; t < seconds * 1000; t += 16) frames.push(life.update(16, opts));
  return frames;
}

test("blinks every 2-6 s on average, each about 150 ms", () => {
  const frames = run(new Life(), 120);
  let blinks = 0, closedFrames = 0, inBlink = false;
  for (const f of frames) {
    const closed = (f.morphs.eyeBlinkLeft || 0) > 0.5;
    if (closed && !inBlink) blinks++;
    if (closed) closedFrames++;
    inBlink = closed;
  }
  assert.ok(blinks >= 15 && blinks <= 70, `blinks in 2 min: ${blinks}`);
  const msClosedPerBlink = (closedFrames * 16) / blinks;
  assert.ok(msClosedPerBlink > 30 && msClosedPerBlink < 150);
});

test("the head and eyes never freeze, idle or speaking, and motion stays subtle", () => {
  for (const opts of [{}, { speaking: true, level: 0.6 }]) {
    const frames = run(new Life(), 10, opts);
    let frozen = 0;
    for (let i = 1; i < frames.length; i++) if (frames[i].head.every((v, k) => v === frames[i - 1].head[k])) frozen++;
    assert.equal(frozen, 0);
    const maxDeg = Math.max(...frames.flatMap(f => f.head.map(Math.abs))) * 57.3;
    assert.ok(maxDeg < 6, `head moves at most a few degrees (${maxDeg.toFixed(1)}°)`);
  }
});

test("a loud syllable above the running average triggers emphasis (nod + brows)", () => {
  const life = new Life();
  run(life, 2, { speaking: true, level: 0.3 });
  const f = life.update(16, { speaking: true, level: 0.95 });
  assert.equal(f.emphasis, true);
  const later = run(life, 0.2, { speaking: true, level: 0.3 });
  assert.ok(Math.max(...later.map(x => x.morphs.browInnerUp)) > 0.1);
});

test("moods blend in smoothly", () => {
  const life = new Life();
  life.setMood("happy");
  const first = life.update(16).morphs.mouthSmileLeft;
  const later = run(life, 2).at(-1).morphs.mouthSmileLeft;
  assert.ok(first < 0.05 && later > 0.2);
  life.setMood("unknown-mood");
  assert.equal(life.mood, "neutral");
});
