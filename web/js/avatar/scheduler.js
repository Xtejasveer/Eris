// Pure audio helpers for the avatar: no DOM, no Web Audio objects, so they can be unit tested in Node.

// Seconds of headroom when the first chunk of a stream (or a chunk after an underrun) is scheduled.
export const LEAD_IN_S = 0.05;

/**
 * When should the next chunk start so that chunks play back-to-back with no gap?
 * nextStart: the end time of the previously scheduled chunk (0 if none yet).
 * now: AudioContext.currentTime. If the queue ran dry (nextStart is in the past) we restart a little ahead of now.
 */
export function nextStartTime(now, nextStart, leadIn = LEAD_IN_S) {
  return nextStart > now + 0.005 ? nextStart : now + leadIn;
}

/** Duration in seconds of `frames` samples at `sampleRate`. */
export function chunkDuration(frames, sampleRate) {
  return frames / sampleRate;
}

/** Little-endian 16-bit PCM bytes (ArrayBuffer or typed view) → Float32Array per channel. */
export function pcm16ToFloat32(bytes, channels = 1) {
  const view = bytes instanceof ArrayBuffer ? new DataView(bytes) : new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const frames = Math.floor(view.byteLength / 2 / channels);
  const out = Array.from({ length: channels }, () => new Float32Array(frames));
  for (let i = 0; i < frames; i++) {
    for (let c = 0; c < channels; c++) {
      const s = view.getInt16((i * channels + c) * 2, true);
      out[c][i] = s < 0 ? s / 32768 : s / 32767;
    }
  }
  return out;
}

/** Interleaved Float32 samples → one Float32Array per channel. */
export function deinterleave(samples, channels = 1) {
  if (channels === 1) return [samples instanceof Float32Array ? samples : Float32Array.from(samples)];
  const frames = Math.floor(samples.length / channels);
  const out = Array.from({ length: channels }, () => new Float32Array(frames));
  for (let i = 0; i < frames; i++) for (let c = 0; c < channels; c++) out[c][i] = samples[i * channels + c];
  return out;
}

/**
 * Parse a PCM WAV file header. Returns { sampleRate, channels, bitsPerSample, dataOffset, dataLength }.
 * Tolerates the placeholder sizes some TTS engines write (0xFFFFFFFF) by reading to the end of the buffer.
 */
export function parseWav(buffer) {
  const view = new DataView(buffer);
  const tag = (o) => String.fromCharCode(view.getUint8(o), view.getUint8(o + 1), view.getUint8(o + 2), view.getUint8(o + 3));
  if (tag(0) !== "RIFF" || tag(8) !== "WAVE") throw new Error("not a WAV file");
  let offset = 12, fmt = null;
  while (offset + 8 <= view.byteLength) {
    const id = tag(offset), size = view.getUint32(offset + 4, true);
    if (id === "fmt ") {
      fmt = { format: view.getUint16(offset + 8, true), channels: view.getUint16(offset + 10, true),
        sampleRate: view.getUint32(offset + 12, true), bitsPerSample: view.getUint16(offset + 22, true) };
    } else if (id === "data") {
      if (!fmt) throw new Error("WAV data before fmt chunk");
      const dataLength = Math.min(size, view.byteLength - offset - 8);
      return { ...fmt, dataOffset: offset + 8, dataLength };
    }
    offset += 8 + size + (size % 2);
  }
  throw new Error("WAV has no data chunk");
}

/**
 * Split the PCM data of a WAV into chunks of `ms` milliseconds (each a fresh ArrayBuffer of PCM16 bytes),
 * which is how a streaming TTS would deliver it.
 */
export function splitPcm(buffer, wav, ms = 100) {
  const frameBytes = wav.channels * (wav.bitsPerSample / 8);
  const chunkBytes = Math.max(frameBytes, Math.round((wav.sampleRate * ms) / 1000) * frameBytes);
  const chunks = [];
  for (let o = 0; o < wav.dataLength; o += chunkBytes) {
    const start = wav.dataOffset + o;
    chunks.push(buffer.slice(start, start + Math.min(chunkBytes, wav.dataLength - o)));
  }
  return chunks;
}
