// The landing page a signed-out visitor sees at the root. Few words, things to touch: a class plays in the hero (and
// takes a doubt when Space is pressed), then small interactive pieces show what Eris is, why to trust it, and how a
// teacher's slides decide a lesson's depth and screens. "Sign in" opens #/signin; "Try the demo" opens #/demo (the demo accounts).
// The numbers are real: judge.json across the first 7 lectures, and depth.py's thresholds and minutes.

import { h, icon } from "./ui.js";

const SIGN_IN = "#/signin";
const DEMO = "#/demo";  // the demo accounts
const SCENE_MS = 5200;
const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------- the hero: a class playing ----------

// Each scene is one screen of the class, a caption the tutor says, and the screen's content.
const SCENES = [
  {
    env: "Slides",
    caption: "Brittle metals like cast iron break off in small pieces.",
    build: () => h("div", { class: "sc-slide" },
      h("div", { class: "sc-slide-text" },
        h("b", {}, "Types of chips"),
        h("span", { class: "sc-line" }, "Continuous: ductile metals, high speed"),
        h("span", { class: "sc-line sc-mark" }, "Discontinuous: brittle metals"),
        h("span", { class: "sc-line" }, "Built-up edge: low speed")),
      h("div", { class: "sc-slide-pic", html: `<svg viewBox="0 0 120 90" aria-hidden="true"><rect x="8" y="58" width="104" height="24" rx="3" fill="#cfd8e3"/><path d="M58 58 L80 20 L96 26 L76 58Z" fill="#9aa6b2"/><path d="M50 58 l-6 -10 l8 -2 l-4 -9 l8 -1 l-2 -10" fill="none" stroke="#5b6b7a" stroke-width="3" stroke-linejoin="round"/></svg>` },
        h("span", { class: "sc-pen" }))),
  },
  {
    env: "Notebook",
    caption: "If the running sum goes negative, drop it and start again.",
    build: () => h("div", { class: "sc-notebook" },
      h("div", { class: "sc-hand sc-hand-title" }, "Maximum subarray"),
      h("div", { class: "sc-hand" }, "current = max(x, current + x)"),
      h("div", { class: "sc-hand" }, "best = max(best, current)"),
      h("div", { class: "sc-hand" }, h("mark", {}, "negative run? start again"))),
  },
  {
    env: "Code",
    caption: "Let's run it. The best sum is 6.",
    build: () => h("div", { class: "sc-code" },
      h("pre", { class: "sc-editor" },
        h("span", { class: "sc-type" }, "best = cur = arr[0]\nfor x in arr[1:]:\n    cur = max(x, cur + x)\n    best = max(best, cur)\nprint(best)")),
      h("div", { class: "sc-terminal" }, h("span", {}, "$ python kadane.py"), h("b", { class: "sc-out" }, "6"))),
  },
  {
    env: "Visual",
    caption: "Watch the range as the angle moves: 45° goes farthest.",
    build: () => h("div", { class: "sc-graph" },
      h("div", { class: "sc-graph-plot", html: `<svg viewBox="0 0 300 150" aria-hidden="true"><line x1="10" y1="135" x2="292" y2="135" class="sc-axis"/><path class="sc-traj" d=""/></svg>` }),
      h("div", { class: "sc-slider" }, h("span", {}, "angle"), h("i", {}, h("b")), h("output", {}, "15°"))),
  },
  {
    env: "Visual",
    caption: "For each number: extend the run, or start fresh.",
    build: () => h("div", { class: "sc-diagram" },
      h("span", { class: "sc-block" }, "Take the next number"),
      h("span", { class: "sc-arrow" }),
      h("span", { class: "sc-block on" }, "current = max(x, current + x)"),
      h("span", { class: "sc-arrow" }),
      h("span", { class: "sc-block" }, "Update the best sum")),
  },
];

function trajectory(svg, angle) {  // a projectile's path for the graph scene (range follows sin 2θ)
  const a = (angle * Math.PI) / 180, pts = [];
  const range = 270 * Math.sin(2 * a), peak = 120 * Math.sin(a) ** 2;
  for (let i = 0; i <= 40; i++) {
    const t = i / 40;
    pts.push(`${(12 + range * t).toFixed(1)},${(135 - 4 * peak * t * (1 - t)).toFixed(1)}`);
  }
  svg.querySelector(".sc-traj").setAttribute("d", `M${pts.join(" L")}`);
}

function classDemo() {
  const envs = ["Notebook", "Slides", "Code", "Visual"];
  const pills = envs.map(name => h("button", { class: "sc-pill", type: "button", onclick: () => go(SCENES.findIndex(s => s.env === name)) }, name));
  const screen = h("div", { class: "sc-screen" });
  const caption = h("p", { class: "sc-caption" });
  const tutor = h("video", { class: "sc-tutor", src: "assets/tutor/tutor-talking.mp4", poster: "assets/tutor/tutor-talking-poster.webp",
    loop: true, playsinline: true, autoplay: true, "aria-hidden": "true", disablepictureinpicture: true });
  tutor.muted = true;
  // The voice dock, as in the real class: hold Space and speak; the words show as they are heard.
  const dockText = h("span", { class: "sc-dock-text", "aria-live": "polite" });
  const askBtn = h("button", { class: "sc-ask", type: "button", dataset: { state: "idle" }, onclick: () => ask() },
    h("kbd", {}, "Space"), dockText, h("span", { class: "sc-dots" }, h("i"), h("i"), h("i")),
    h("span", { class: "sc-wave" }, [0, 1, 2, 3, 4].map(() => h("i"))));
  const live = h("span", { class: "sc-live" }, h("i"), h("span", {}, "Playing"));
  const el = h("div", { class: "sc" },
    h("div", { class: "sc-top" }, h("div", { class: "sc-pills" }, pills), live),
    h("div", { class: "sc-body" }, screen),
    h("div", { class: "sc-bar" }, tutor, caption, askBtn));
  const dock = (state, text = "Hold to ask a doubt") => { askBtn.dataset.state = state; dockText.textContent = text; };
  dock("idle");

  let i = 0, timer = 0, anim = 0, asking = false;
  const alive = () => document.body.contains(el);

  function sayCaption(text, extra = null) {
    const words = text.split(" ");
    caption.replaceChildren(...words.map((w, k) => h("span", { style: `animation-delay:${k * 90}ms` }, `${w} `)),
      ...(extra ? [h("small", { class: "sc-checked", style: `animation-delay:${words.length * 90}ms` }, ...extra)] : []));
  }

  function play(node) {
    cancelAnimationFrame(anim);
    if (node.classList.contains("sc-code")) {  // type the program, then print its output
      const target = node.querySelector(".sc-type"), full = target.textContent;
      target.textContent = "";
      let n = 0;
      const step = () => {
        if (!alive() || asking) return;
        n = Math.min(full.length, n + 2);
        target.textContent = full.slice(0, n);
        if (n < full.length) anim = requestAnimationFrame(step); else node.classList.add("ran");
      };
      anim = requestAnimationFrame(step);
    }
    if (node.classList.contains("sc-graph")) {  // the tutor moves the slider: 15° to 75°, settling on 45°
      const svg = node.querySelector("svg"), thumb = node.querySelector(".sc-slider b"), out = node.querySelector("output");
      const set = (deg) => { trajectory(svg, deg); thumb.style.left = `${((deg - 10) / 70) * 100}%`; out.textContent = `${Math.round(deg)}°`; };
      const keys = [[0, 15], [1600, 75], [3200, 45]], start = performance.now();
      const step = (now) => {
        if (!alive() || asking) return;
        const t = now - start, k = keys.findIndex(([at]) => at > t);
        if (k === -1) { set(45); return; }
        const [t0, d0] = keys[k - 1], [t1, d1] = keys[k];
        const f = Math.min(1, (t - t0) / (t1 - t0)), ease = f < 0.5 ? 2 * f * f : 1 - (-2 * f + 2) ** 2 / 2;
        set(d0 + (d1 - d0) * ease);
        anim = requestAnimationFrame(step);
      };
      set(15);
      if (!reduceMotion()) anim = requestAnimationFrame(step); else set(45);
    }
  }

  function go(n) {
    if (!alive()) return;
    if (asking) endAsk();
    i = (n + SCENES.length) % SCENES.length;
    const scene = SCENES[i];
    pills.forEach((p, k) => p.classList.toggle("on", envs[k] === scene.env));
    const node = scene.build();
    screen.replaceChildren(node);
    sayCaption(scene.caption);
    play(node);
    clearTimeout(timer);
    if (!reduceMotion()) timer = setTimeout(() => go(i + 1), SCENE_MS);
  }

  // A doubt, as a student asks it: hold Space and speak. The lesson stops mid-sentence, the words show as they are
  // heard, the teacher thinks, then answers out loud (a checked answer), and the lesson picks up again.
  function ask() {
    if (asking || !alive()) return;
    asking = true;
    clearTimeout(timer); cancelAnimationFrame(anim);
    el.classList.add("paused");
    live.lastChild.textContent = "Listening";
    const q = "Why does the run start again at 4?".split(" ");
    let n = 0;
    dock("listening", "");
    const hear = () => {
      if (!alive() || !asking) return;
      dockText.textContent = q.slice(0, ++n).join(" ");
      if (n < q.length) return setTimeout(hear, 230);
      setTimeout(() => {  // let go: the teacher thinks
        if (!alive() || !asking) return;
        dock("thinking", q.join(" "));
        live.lastChild.textContent = "Thinking";
        setTimeout(() => {
          if (!alive() || !asking) return;
          const answer = "The sum before 4 was negative, so keeping it would only make 4 smaller. Starting fresh at 4 is better.";
          dock("idle");
          live.lastChild.textContent = "Answering your doubt";
          sayCaption(answer, [icon("checkCircle"), "Checked before you hear it"]);
          timer = setTimeout(() => go(i), answer.split(" ").length * 90 + 3200);  // back to where the lesson stopped
        }, 1200);
      }, 450);
    };
    setTimeout(hear, 200);
  }

  function endAsk() {
    asking = false;
    el.classList.remove("paused");
    live.lastChild.textContent = "Playing";
    dock("idle");
  }

  const onKey = (e) => {
    if (!alive()) { document.removeEventListener("keydown", onKey); return; }
    if (e.code !== "Space" || /^(INPUT|TEXTAREA|BUTTON|A)$/.test(document.activeElement?.tagName || "")) return;
    const r = el.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight) return;  // only while the class is on screen
    e.preventDefault();
    if (!e.repeat) ask();
  };
  document.addEventListener("keydown", onKey);
  setTimeout(() => go(0));  // once the page is on screen
  return el;
}

// ---------- small interactive pieces ----------

function isToggle() {
  const lists = {
    is: ["Prerequisite lessons", "Classes when you're away", "Taught only after you approve"],
    not: ["A replacement for teachers", "A grader or decision-maker", "Free to say what you didn't approve"],
  };
  const words = h("ul", { class: "it-words" });
  const btns = { is: h("button", { type: "button" }, "It is"), not: h("button", { type: "button" }, "It isn't") };
  const show = (k) => {
    Object.entries(btns).forEach(([key, b]) => { b.classList.toggle("on", key === k); b.setAttribute("aria-pressed", key === k); });
    words.className = `it-words ${k}`;
    words.replaceChildren(...lists[k].map((t, n) => h("li", { style: `animation-delay:${n * 70}ms` }, icon(k === "is" ? "check" : "close"), t)));
  };
  btns.is.onclick = () => show("is"); btns.not.onclick = () => show("not");
  show("is");
  return h("div", { class: "it" }, h("div", { class: "it-switch", role: "group", "aria-label": "What Eris is and isn't" }, btns.is, btns.not), words);
}

// What Jev, the judge model, asks of every script (eris/generate/script_judge.py): each is a yes/no question, and a
// failed one goes back to the writer with its fix before the teacher ever sees the script.
const JEV_CHECKS = [
  ["The teaching", ["Explains each idea clearly", "Has a worked example", "Stays true to your material",
    "Covers what you asked it to", "Avoids what you ruled out", "Sounds like your teaching style"]],
  ["What's on screen", ["Notes match the code", "Says what the program really printed", "Explains every picture it shows",
    "Graphs and diagrams match your material", "Highlights point at what's being said"]],
  ["How it's said", ["Reads as speech, not a textbook", "Opens by saying why you're away", "Closes with the next class"]],
];

function jevPanel() {
  let k = 0;
  return h("div", { class: "jev" },
    h("div", { class: "jev-groups" }, JEV_CHECKS.map(([group, checks]) => h("div", { class: "jev-group" },
      h("strong", {}, group),
      h("ul", {}, checks.map(c => h("li", { style: `animation-delay:${(k++) * 45}ms` }, icon("check"), c)))))),
    h("p", { class: "jev-how" }, "Jev answers each as a yes or no. A failed check goes back to the writer with its fix, "
      + "and code checks the rest: every program runs, every slide and quote exists."));
}

// ---------- the guide: from creating a lecture to students getting it, one step at a time ----------
// Each step shows the part of the real platform it is about: what you upload and the persona's fields (Studio),
// Jev's checks, the script editor, the teacher preview of the class, and approving a version for a course.

// A window of the platform, drawn small: its title bar, then what is inside.
const mockWindow = (bar, body, cls = "") => h("div", { class: `gm ${cls}` }, h("div", { class: "gm-bar" }, bar), body);

// What a teacher gives Eris, in plain words: a bullet list that streams in, one point after the other, word by word.
const WORD_MS = 45;    // between words of a point
const POINT_MS = 250;  // between one point finishing and the next starting

function createPanel() {
  const items = [
    "Upload your study material: slides, PDFs, Word or text files.",
    "Edit your persona: your name, your class, how you teach, what to cover and what to avoid.",
    "Leave a note for the class: why you're away, and what to prepare for next time.",
    "Pick the topic, the language and the voice.",
  ];
  let at = 300;
  const rows = items.map((text) => {
    const words = text.split(" ");
    const li = h("li", { style: `animation-delay:${at}ms` }, words.map((w, k) => h("span", { style: `animation-delay:${at + k * WORD_MS}ms` }, `${w} `)));
    at += words.length * WORD_MS + POINT_MS;
    return li;
  });
  return h("div", { class: "gd-create" }, h("ul", { class: "gd-stream" }, rows));
}

function editPanel() {
  const tabs = h("div", { class: "gm-tabs" }, ["Preview", "Quality", "Edit", "Progress"].map(t => h("span", { class: t === "Edit" ? "on" : "" }, t)));
  const lines = [
    ["[SECTION title=\"Chip thickness ratio\"]", "mk"],
    ["Now a simple question. Is the chip thicker or thinner than the layer it came from?", ""],
    ["[SLIDE n=7]", "mk"],
    ["[SLIDE_CIRCLE n=7 part=\"to < tc\"]", "mk"],
    ["Notice the chip: tc is bigger than to, so the chip is thicker.", "edit"],
    ["[NOTE_TITLE text=\"Chip thickness ratio\"]", "mk"],
    ["[NOTE]", "mk"], ["- r = t0 / tc", "note"], ["[/NOTE]", "mk"],
  ];
  return h("div", { class: "gd-mock" },
    mockWindow([tabs, h("span", { class: "gm-sp" }), h("span", { class: "gm-btn" }, icon("save"), "Save"),
      h("span", { class: "gm-btn ok" }, icon("check"), "Approve")],
      h("div", { class: "gm-code" }, lines.map(([text, kind], k) => h("div", { class: `gm-ln ${kind}` },
        h("i", {}, 41 + k), h("span", {}, text))))),
    h("ul", { class: "gd-notes" },
      h("li", {}, icon("edit"), "Change any line, said or shown."),
      h("li", {}, icon("checkCircle"), "Saving checks it again.")));
}

function tryPanel() {
  return h("div", { class: "gd-mock" },
    mockWindow([h("span", { class: "gm-tag" }, icon("eye"), "Teacher preview"), h("span", { class: "gm-sp" }),
      h("span", { class: "gm-btn" }, "Script"), h("span", { class: "gm-btn" }, icon("sparkle"), "Regenerate")],
      h("div", { class: "gm-class" },
        h("div", { class: "gm-board" }, h("p", { class: "gm-hand title" }, "Chip thickness ratio"),
          h("p", { class: "gm-hand" }, "r = t0 / tc"), h("p", { class: "gm-hand" }, "r is always less than 1")),
        h("div", { class: "gm-bottom" },
          h("img", { class: "gm-face", src: "assets/tutor/tutor-male-idle-poster.webp", alt: "" }),
          h("p", { class: "gm-caption" }, "So r is always less than 1. Make sense?"),
          h("span", { class: "gm-dock" }, "Hold ", h("kbd", {}, "Space"), " to ask a doubt", h("i", {}, icon("mic")))))),
    h("ul", { class: "gd-notes" },
      h("li", {}, icon("play"), "Exactly what students get."),
      h("li", {}, icon("mic"), "Ask it a doubt yourself.")));
}

function approvePanel() {
  return h("div", { class: "gd-mock" },
    mockWindow([h("strong", { class: "gm-title" }, "Introduction to Chip Making"), h("span", { class: "gm-sp" }),
      h("span", { class: "gm-badge" }, "approved")],
      h("div", { class: "gm-approve" },
        h("div", { class: "gm-row" }, icon("layers"), h("span", {}, h("b", {}, "Version 2"), " · approved today")),
        h("div", { class: "gm-row" }, icon("class"), h("span", {}, h("b", {}, "Manufacturing Processes"), " · Section A"),
          h("span", { class: "gm-switch on" }, h("i"))),
        h("div", { class: "gm-toast" }, icon("check"), "Approved as version 2. The class gets it now."))),
    h("ul", { class: "gd-notes" },
      h("li", {}, icon("check"), "Students only get what you approved."),
      h("li", {}, icon("clock"), "Check attendance: see who heard the whole lesson, and what they asked.")));
}

function approvalTrack() {
  const steps = [
    ["Create", "Upload your material and tell Eris how you teach.", createPanel],
    ["Quality", "Jev checks the script before you read it.", jevPanel],
    ["Edit", "Change anything you'd say differently.", editPanel],
    ["Try it", "Play it exactly as students will.", tryPanel],
    ["Approve", "Only then do students get it.", approvePanel],
  ];
  const line = h("p", { class: "ap-line" });
  const detail = h("div", { class: "ap-detail" });
  const nodes = steps.map(([name], n) => h("button", { type: "button", class: "ap-step", onclick: () => pick(n) }, h("i", {}, n + 1), name));
  const pick = (n) => {
    nodes.forEach((b, k) => { b.classList.toggle("done", k < n); b.classList.toggle("on", k === n); b.setAttribute("aria-pressed", k === n); });
    line.textContent = steps[n][1];
    const next = steps[n + 1] ? h("button", { type: "button", class: "ap-next", onclick: () => pick(n + 1) }, `Next: ${steps[n + 1][0]}`) : null;
    detail.replaceChildren(steps[n][2](), ...(next ? [next] : []));
  };
  pick(0);
  return h("div", { class: "ap" }, h("div", { class: "ap-track" }, nodes), line, detail);
}

// How deep a part is taught, and the lesson's speaking time, by the lesson planner's own rule
// (eris/generate/depth.py): each yes to Jev's six questions adds 1 to a part's score and each slide beyond the first
// adds 1; under brief_below is brief, from in_depth_at in depth. Each depth has a fixed speaking time; a lesson is its
// parts plus the opening, recap and closing, and past max_speaking_min every part is shortened by the same share.
// The settings come from the server (/api/landing), so the page shows what a generated lesson really gets; these are
// its values as a fallback.
const PLAN = { depth_min: { brief: 0.6, normal: 1.2, "in depth": 2.2 }, framing_min: { Opening: 0.6, Recap: 0.5, Closing: 0.3 },
  brief_below: 2, in_depth_at: 3.5, words_per_min: 115, max_speaking_min: 30 };
const MAX_SLIDES = 10, MAX_PARTS = 15, DEPTHS = ["brief", "normal", "in depth"];
const DEPTH_NAMES = { brief: "Brief", normal: "Normal", "in depth": "In depth" };
const loadPlan = fetch("/api/landing").then(r => (r.ok ? r.json() : null)).then(d => { if (d) Object.assign(PLAN, d); }).catch(() => {});

function speakingTime(minutes) {
  const s = Math.round(minutes * 60), m = Math.floor(s / 60);
  return m ? `${m} min${s % 60 ? ` ${s % 60} s` : ""}` : `${s} s`;
}

function stepper(label, min, max, value, onChange) {
  const out = h("output", {}, String(value));
  const less = h("button", { type: "button", "aria-label": `Fewer ${label.toLowerCase()}` }, "−");
  const more = h("button", { type: "button", "aria-label": `More ${label.toLowerCase()}` }, "+");
  const set = (v) => { value = Math.min(max, Math.max(min, v)); out.textContent = value; less.disabled = value <= min; more.disabled = value >= max; onChange(value); };
  less.onclick = () => set(value - 1); more.onclick = () => set(value + 1);
  const el = h("div", { class: "db-step" }, h("span", {}, label), less, out, more);
  el.init = () => set(value);
  return el;
}

function depthBuilder() {
  const traits = ["A worked example", "Steps", "A comparison", "An exception", "A task", "Builds on another part"];
  const on = new Set(["A worked example"]);
  let slides = 1, parts = 6;
  const chips = traits.map(t => h("button", { type: "button", class: `chip-t ${on.has(t) ? "on" : ""}`, "aria-pressed": on.has(t),
    onclick: (e) => { on.has(t) ? on.delete(t) : on.add(t); e.currentTarget.classList.toggle("on"); e.currentTarget.setAttribute("aria-pressed", on.has(t)); update(); } }, t));
  // The score track: three zones of equal width (the zone is what matters); the marker moves on every change.
  const zones = DEPTHS.map(d => h("div", { class: "db-zone" }, h("b", {}, DEPTH_NAMES[d]), h("small", {})));
  const marker = h("i", { class: "db-marker" }, h("span", {}));
  const track = h("div", { class: "db-track" }, h("div", { class: "db-zones" }, zones), marker);
  const partTime = h("output", { class: "db-min" });
  const lessonTime = h("output", { class: "db-lesson-min" });
  const lessonNote = h("small", { class: "db-lesson-note" });
  const slideStep = stepper("Slides on it", 1, MAX_SLIDES, slides, v => { slides = v; update(); });
  const partStep = stepper("Parts like this", 1, MAX_PARTS, parts, v => { parts = v; update(); });

  function update() {
    const score = on.size + (slides - 1);
    const depth = score >= PLAN.in_depth_at ? "in depth" : score >= PLAN.brief_below ? "normal" : "brief";
    // Where the marker sits: across its zone, from the zone's start to (for in depth) a score of 12.
    const edges = [0, PLAN.brief_below, PLAN.in_depth_at, 12], k = DEPTHS.indexOf(depth);
    const within = Math.min(1, (score - edges[k]) / (edges[k + 1] - edges[k]));
    marker.style.left = `${((k + within * 0.9 + 0.05) / 3) * 100}%`;
    marker.firstChild.textContent = score;
    zones.forEach((z, n) => { z.classList.toggle("on", n === k); z.lastChild.textContent = speakingTime(PLAN.depth_min[DEPTHS[n]]); });
    const minutes = PLAN.depth_min[depth];
    // The whole lesson: its parts, plus the opening, recap and closing; past the cap every part is shortened by the
    // same share, so the parts and the framing fill exactly the cap.
    const framing = Object.values(PLAN.framing_min).reduce((a, b) => a + b, 0);
    const wanted = parts * minutes + framing, over = wanted > PLAN.max_speaking_min;
    const part = over ? minutes * (PLAN.max_speaking_min - framing) / (wanted - framing) : minutes;
    partTime.textContent = speakingTime(part);
    lessonTime.textContent = speakingTime(over ? PLAN.max_speaking_min : wanted);
    lessonNote.textContent = over
      ? `Needs ${speakingTime(wanted)}, so each part is cut from ${speakingTime(minutes)} to fit ${PLAN.max_speaking_min} min, and Eris suggests two lessons.`
      : `${parts} part${parts > 1 ? "s" : ""} × ${speakingTime(minutes)}, plus ${speakingTime(framing)} to open, recap and close.`;
  }
  slideStep.init(); partStep.init();
  loadPlan.then(update);
  return h("div", { class: "db" },
    h("p", { class: "db-q" }, "This part of my slides has…"),
    h("div", { class: "db-chips" }, chips),
    slideStep,
    track,
    h("div", { class: "db-out" },
      h("div", {}, h("small", {}, "This part"), partTime),
      h("div", { class: "db-lesson" }, partStep, h("div", {}, h("small", {}, "Whole lesson"), lessonTime))),
    lessonNote);
}

// Which screens a class uses: the notebook always; the rest only when the material has what they show.
function screensBuilder() {
  const screens = [
    ["Notebook", "book", null],
    ["Slides", "slides", "Slides (PPT or PDF)"],
    ["Code", "code", "Code"],
    ["Graphs", "sparkle", "Charts"],
    ["Diagrams", "layers", "Steps or a process"],
  ];
  const have = new Set(["Slides (PPT or PDF)"]);
  const tiles = screens.map(([name, ic, need]) => h("div", { class: "sb-tile" }, icon(ic), h("b", {}, name),
    h("small", {}, need ? `needs ${need.toLowerCase()}` : "always")));
  const update = () => tiles.forEach((t, n) => {
    const lit = !screens[n][2] || have.has(screens[n][2]);
    t.classList.toggle("on", lit);
    t.lastChild.textContent = lit ? "in this class" : `needs ${screens[n][2].toLowerCase().replace(/ \(ppt or pdf\)/, "")}`;
  });
  const chips = screens.filter(s => s[2]).map(([, , need]) => h("button", { type: "button", class: `chip-t ${have.has(need) ? "on" : ""}`, "aria-pressed": have.has(need),
    onclick: (e) => { have.has(need) ? have.delete(need) : have.add(need); e.currentTarget.classList.toggle("on"); e.currentTarget.setAttribute("aria-pressed", have.has(need)); update(); } }, need));
  update();
  return h("div", { class: "sb" },
    h("p", { class: "db-q" }, "My material has…"),
    h("div", { class: "db-chips" }, chips),
    h("div", { class: "sb-tiles" }, tiles));
}

// The class languages: the same greeting in each one's own script, said by the class voice (a woman's, or a man's
// where the language has one). The list and lines come from the server's settings; the clips are pre-made files.
const LANGUAGES = [
  { code: "en-IN", name: "English", sample: "Hello class. Today I'm teaching in place of your teacher.", man: true },
  { code: "hi-IN", name: "Hindi", sample: "नमस्ते दोस्तों, आज की क्लास में आपका स्वागत है।", man: true },
  { code: "ta-IN", name: "Tamil", sample: "வணக்கம், இன்றைய வகுப்புக்கு வரவேற்கிறேன்.", man: false },
  { code: "te-IN", name: "Telugu", sample: "నమస్కారం, ఈ రోజు తరగతికి స్వాగతం.", man: false },
  { code: "kn-IN", name: "Kannada", sample: "ನಮಸ್ಕಾರ, ಇಂದಿನ ತರಗತಿಗೆ ಸ್ವಾಗತ.", man: true },
  { code: "ml-IN", name: "Malayalam", sample: "നമസ്കാരം, ഇന്നത്തെ ക്ലാസ്സിലേക്ക് സ്വാഗതം.", man: true },
  { code: "mr-IN", name: "Marathi", sample: "नमस्कार, आजच्या वर्गात तुमचे स्वागत आहे.", man: true },
  { code: "bn-IN", name: "Bengali", sample: "নমস্কার, আজকের ক্লাসে স্বাগত।", man: true },
  { code: "gu-IN", name: "Gujarati", sample: "નમસ્તે, આજના વર્ગમાં તમારું સ્વાગત છે.", man: true },
  { code: "pa-IN", name: "Punjabi", sample: "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਅੱਜ ਦੀ ਕਲਾਸ ਵਿੱਚ ਤੁਹਾਡਾ ਸਵਾਗਤ ਹੈ।", man: true },
];

function languagePicker() {
  let langs = LANGUAGES, current = langs[1], who = "woman", audio = null;
  const line = h("p", { class: "lg-line" });
  const face = h("img", { class: "lg-face", alt: "" });
  const play = h("button", { type: "button", class: "lg-play", onclick: () => speak() }, icon("play"), h("span", {}, "Hear it"));
  const whoBtns = { woman: h("button", { type: "button" }, "Woman's voice"), man: h("button", { type: "button" }, "Man's voice") };
  const chipRow = h("div", { class: "db-chips lg-chips" });
  function stop() { if (audio) { audio.pause(); audio = null; } play.classList.remove("on"); }
  function speak() {
    stop();
    audio = new Audio(`assets/voices/${current.code}-${who}.m4a`);
    play.classList.add("on");
    audio.onended = audio.onerror = () => play.classList.remove("on");
    audio.play().catch(() => play.classList.remove("on"));
  }
  function render(andSpeak) {
    if (who === "man" && !current.man) who = "woman";
    chipRow.querySelectorAll(".chip-t").forEach(c => { const on = c.dataset.code === current.code; c.classList.toggle("on", on); c.setAttribute("aria-pressed", on); });
    line.textContent = current.sample;
    line.lang = current.code.split("-")[0];
    face.src = `assets/tutor/${who === "man" ? "tutor-male-" : "tutor-"}idle-poster.webp`;
    Object.entries(whoBtns).forEach(([k, b]) => { b.classList.toggle("on", k === who); b.setAttribute("aria-pressed", k === who); });
    whoBtns.man.disabled = !current.man;
    whoBtns.man.title = current.man ? "" : `${current.name} has a woman's voice only`;
    if (andSpeak) speak(); else stop();
  }
  const chips = () => chipRow.replaceChildren(...langs.map(l => h("button", { type: "button", class: "chip-t", dataset: { code: l.code },
    onclick: () => { current = l; render(true); } }, l.name)));
  whoBtns.woman.onclick = () => { who = "woman"; render(true); };
  whoBtns.man.onclick = () => { if (current.man) { who = "man"; render(true); } };
  chips(); render(false);
  fetch("/api/landing").then(r => (r.ok ? r.json() : null)).then(d => {
    if (!d?.languages?.length) return;
    langs = d.languages; current = langs.find(l => l.code === current.code) || langs[0];
    chips(); render(false);
  }).catch(() => {});
  return h("div", { class: "lang" },
    chipRow,
    h("div", { class: "lg-stage" }, face,
      h("div", { class: "lg-body" }, line,
        h("div", { class: "lg-controls" }, play, h("div", { class: "it-switch lg-who", role: "group", "aria-label": "Voice" }, whoBtns.woman, whoBtns.man)))),
    h("p", { class: "lg-note" }, "Lessons, notes and answers are written in the class language, and students can ask their doubts in it. The voice matches the teacher, and so does the grammar."));
}

// ---------- the page ----------

export function renderLanding(root) {
  const cta = (cls, label) => h("a", { class: `btn ${cls}`, href: label === "Sign in" ? SIGN_IN : DEMO }, label);
  root.replaceChildren(h("div", { class: "landing" },
    h("header", { class: "lp-nav" },
      h("a", { class: "lp-brand", href: "#/" },
        h("span", { class: "brand-mark", "aria-hidden": "true", html: `<svg viewBox="0 0 28 28"><rect width="28" height="28" rx="8" fill="var(--accent)"/><path d="M8.5 8.5h11M8.5 14h8M8.5 19.5h11M8.5 8.5v11" stroke="#fff" stroke-width="2.4" stroke-linecap="round" fill="none"/></svg>` }),
        h("strong", {}, "Eris")),
      h("div", { class: "lp-nav-cta" }, cta("ghost", "Sign in"), cta("primary", "Try the demo"))),

    h("section", { class: "lp-hero" },
      h("div", { class: "lp-hero-text" },
        h("h1", {}, "Your class goes on."),
        h("p", {}, "When you can't teach it, Eris does: from your slides, in your style, only after you approve."),
        h("div", { class: "lp-hero-cta" }, cta("primary lg", "Try the demo"))),
      classDemo()),

    h("section", { class: "lp-row" },
      h("h2", {}, "A substitute, not a replacement"),
      isToggle()),

    h("section", { class: "lp-row" },
      h("h2", {}, "From your slides to your class"),
      approvalTrack()),

    h("section", { class: "lp-row" },
      h("h2", {}, "Your slides decide the lesson"),
      h("div", { class: "lp-builders" }, depthBuilder(), screensBuilder())),

    h("section", { class: "lp-row" },
      h("h2", {}, "In your students' language"),
      languagePicker()),

    h("section", { class: "lp-final" },
      h("h2", {}, "See a lesson for yourself."),
      cta("primary lg", "Try the demo"))));
}
