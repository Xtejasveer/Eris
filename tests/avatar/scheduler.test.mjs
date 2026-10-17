// Run: node --test "tests/avatar/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  LEAD_IN_S, chunkDuration, deinterleave, nextStartTime, parseWav, pcm16ToFloat32, splitPcm,
} from "../../web/js/avatar/scheduler.js";

test("chunks are scheduled back to back while the queue is ahead of the clock", () => {
  let next = 0, now = 1.0;
  const starts = [];
  for (let i = 0; i < 5; i++) {
    const start = nextStartTime(now, next);
    starts.push(start);
    next = start + chunkDuration(4800, 48000);  // 100 ms chunks
    now += 0.02;                                // chunks arrive faster than real time
  }
  assert.equal(starts[0], 1.0 + LEAD_IN_S);     // the first chunk gets a little headroom
  for (let i = 1; i < starts.length; i++) assert.ok(Math.abs(starts[i] - (starts[i - 1] + 0.1)) < 1e-9, "no gap, no overlap");
});

test("after an underrun the next chunk restarts just ahead of the clock (never in the past)", () => {
  assert.equal(nextStartTime(5.0, 4.2), 5.0 + LEAD_IN_S);
  assert.equal(nextStartTime(5.0, 5.3), 5.3);
});

test("chunk duration", () => {
  assert.equal(chunkDuration(48000, 48000), 1);
  assert.equal(chunkDuration(2205, 22050), 0.1);
});

test("PCM16 little-endian → float, full scale and sign", () => {
  const bytes = new Uint8Array([0x00, 0x00, 0xff, 0x7f, 0x00, 0x80, 0x00, 0x40]);  // 0, 32767, -32768, 16384
  const [ch] = pcm16ToFloat32(bytes.buffer);
  assert.deepEqual([...ch].map(v => +v.toFixed(4)), [0, 1, -1, 0.5]);
});

test("PCM16 stereo is split into channels", () => {
  const v = new Int16Array([100, -100, 200, -200]);
  const [l, r] = pcm16ToFloat32(v.buffer, 2);
  assert.equal(l.length, 2);
  assert.ok(l[0] > 0 && r[0] < 0 && l[1] > l[0] && r[1] < r[0]);
});

test("deinterleave float32", () => {
  const [a, b] = deinterleave(new Float32Array([1, -1, 2, -2]), 2);
  assert.deepEqual([...a], [1, 2]);
  assert.deepEqual([...b], [-1, -2]);
});

function makeWav({ frames = 4800, rate = 48000, channels = 1, placeholderSizes = false } = {}) {
  const dataBytes = frames * channels * 2;
  const buf = new ArrayBuffer(44 + dataBytes), v = new DataView(buf);
  const w = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF"); v.setUint32(4, placeholderSizes ? 0xffffffff : 36 + dataBytes, true); w(8, "WAVE");
  w(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, channels, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * channels * 2, true); v.setUint16(32, channels * 2, true); v.setUint16(34, 16, true);
  w(36, "data"); v.setUint32(40, placeholderSizes ? 0xffffffff : dataBytes, true);
  for (let i = 0; i < frames * channels; i++) v.setInt16(44 + i * 2, (i % 100) * 10, true);
  return buf;
}

test("parseWav reads the header", () => {
  const wav = parseWav(makeWav({ frames: 4800, rate: 48000 }));
  assert.equal(wav.sampleRate, 48000);
  assert.equal(wav.channels, 1);
  assert.equal(wav.bitsPerSample, 16);
  assert.equal(wav.dataOffset, 44);
  assert.equal(wav.dataLength, 9600);
});

test("parseWav tolerates placeholder sizes (0xFFFFFFFF), as some TTS engines write", () => {
  const wav = parseWav(makeWav({ frames: 100, placeholderSizes: true }));
  assert.equal(wav.dataLength, 200);
});

test("splitPcm makes 100 ms chunks covering every byte exactly once", () => {
  const buf = makeWav({ frames: 48000 * 1.05, rate: 48000 });  // 1.05 s
  const wav = parseWav(buf);
  const chunks = splitPcm(buf, wav, 100);
  assert.equal(chunks.length, 11);
  assert.equal(chunks[0].byteLength, 9600);
  assert.equal(chunks.at(-1).byteLength, 4800);
  assert.equal(chunks.reduce((n, c) => n + c.byteLength, 0), wav.dataLength);
});
