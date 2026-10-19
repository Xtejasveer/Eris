// A teacher's pen: a hand-drawn circle around something on the board, drawn stroke by stroke.
// Used to circle a picture on a slide ([SLIDE_CIRCLE]) and a diagram block ([FLOW_HIGHLIGHT]).

const NS = "http://www.w3.org/2000/svg";

// A slightly wobbly ellipse that overshoots its start, like a quick pen stroke. seed keeps one circle stable.
export function penPath(cx, cy, rx, ry, seed = 1) {
  let s = seed * 9301 + 49297;
  const rand = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  const start = -0.6 + rand() * 0.4, turn = Math.PI * 2 * 1.07, steps = 96;
  const p1 = rand() * 6.28, p2 = rand() * 6.28;
  const pts = [];
  for (let i = 0; i <= steps; i++) {
    const a = start + (turn * i) / steps;
    // a smooth, slow wobble (not jitter), and the end drifts a little outside the start, like a real pen stroke
    const wobble = 1 + 0.025 * Math.sin(2 * a + p1) + 0.015 * Math.sin(3 * a + p2) + (i / steps) * 0.04;
    pts.push([cx + Math.cos(a) * rx * wobble, cy + Math.sin(a) * ry * wobble]);
  }
  return pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
}

// Append a pen circle to an SVG element (or group) and animate it being drawn. Returns the path.
export function drawPen(parent, cx, cy, rx, ry, { cls = "pen-stroke", seed = 1, ms = 700 } = {}) {
  const path = document.createElementNS(NS, "path");
  path.setAttribute("d", penPath(cx, cy, rx, ry, seed));
  path.setAttribute("class", cls);
  parent.appendChild(path);
  const len = path.getTotalLength?.() || 0;
  if (len) {
    path.style.strokeDasharray = `${len}`;
    path.style.strokeDashoffset = `${len}`;
    path.getBoundingClientRect();  // start from the hidden state
    path.style.transition = `stroke-dashoffset ${ms}ms ease-out`;
    path.style.strokeDashoffset = "0";
  }
  return path;
}

export function svgLayer(cls) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", cls);
  return svg;
}
