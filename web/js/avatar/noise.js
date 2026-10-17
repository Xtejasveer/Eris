// Smooth 1-D gradient (Perlin-style) noise for subtle, never-repeating motion. Pure; unit tested.

function hash(i, seed) {
  // Integer hash → a gradient in [-1, 1].
  let h = (i * 374761393 + seed * 668265263) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return ((h >>> 0) / 4294967295) * 2 - 1;
}

const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);

/** Gradient noise at x, roughly in [-0.5, 0.5], exactly 0 at integer x, smooth everywhere. */
export function noise1(x, seed = 0) {
  const i = Math.floor(x), f = x - i;
  const a = hash(i, seed) * f, b = hash(i + 1, seed) * (f - 1);
  return a + (b - a) * fade(f);
}

/** A few octaves of noise for natural-looking drift, roughly in [-1, 1]. */
export function fbm(x, seed = 0, octaves = 3) {
  let sum = 0, amp = 1, freq = 1, norm = 0;
  for (let o = 0; o < octaves; o++) {
    sum += amp * noise1(x * freq, seed + o * 17);
    norm += amp * 0.5;
    amp *= 0.5; freq *= 2;
  }
  return sum / norm;
}
