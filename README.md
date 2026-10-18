# AI Substitute Teacher (v1)

Index a teacher's files, generate a lecture script with inline markers, let the teacher
approve it, then run a class session that previews the script and answers student doubts.

```
index ──► generate (draft) ──► approve ──► render (audio) ──► session
```

**How a class runs.** The LLM writes the script once and the teacher approves it. In class,
a plain-code *player* (`session.py`) walks the approved `script.json` one segment at a time:
narration plays (Gnani TTS), then the next action runs on the board, then the next narration.
Each step finishes before the next starts, so speech and actions can't drift apart.
LLMs are used only for student doubts (`doubt_agent.py`) and for a one-line recovery when an
action fails (`recovery.py`). They get a read-only snapshot of the class; only the player
moves forward.

Each command is a separate run. They share state only through files in
`workspace/lectures/<id>/` and the Chroma collection named `<id>`.

## 1. Setup (about 5 minutes)

You need [uv](https://docs.astral.sh/uv/) and an [OpenRouter](https://openrouter.ai) API key.

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

| Variable | Meaning |
|---|---|
| `OPENROUTER_API_KEY` | required |
| `LLM_MODEL` | required: an OpenRouter model that supports **tool calling**, e.g. `openai/gpt-4o-mini` |
| `EMBED_MODEL` | embedding model (default `baai/bge-m3`) |
| `TOPIC_NAME` | the lecture topic |
| `LECTURE_DURATION_MIN` | lecture length in minutes (default 30) |
| `SPEAKING_WPM` | speaking speed used for time estimates (default 130) |
| `GNANI_API_KEY` | needed only for voice (`render`, `session --voice/--mic`). Get one at app.gnani.ai/voice |
| `TTS_VOICE` / `TTS_LANGUAGE` | Gnani Timbre v2.5 voice and language (default `Kaveri`, `en-IN`) |
| `TTS_SPEED` | 0.85 to 1.15 (default 1.0) |
| `STT_LANGUAGE` | language for spoken doubts (default `en-IN`) |

## 2. The website (easiest way)

```bash
python main.py serve        # then open http://127.0.0.1:8000
```

- **Home:** pick a Lecture in the sidebar, drop the study material on the upload area, check
  the persona fields (prefilled from `templates/persona.md`), set the Topic, and click
  **Generate script**. The log streams while it indexes and writes. The script appears on the
  right as a readable document (speech, notebook cards, code, actions). **Edit** it if needed,
  then **Approve**. **Reset lecture** clears that lecture's knowledge base (its Chroma
  collection) and everything generated, but keeps the uploaded material and persona.
- **Classroom:** click **Start class** (the sidebar folds into an icon rail to give the stage more room). The left panel shows the teacher, a voice visual and the
  caption. The right panel is the stage with three environments: **Notebook** (a ruled page where
  notes are hand-written), **Slides**, and **Code** (editor plus terminal). Only the AI teacher's
  script switches between them; the indicator can't be clicked. At each question break, type a
  student's question (or use Dictate in Chrome/Safari). The doubt agent can answer on the screen
  too: it may write notes and small programs (`answer1.py`, ...) that are checked and run by the
  backend without teacher approval.
- **Voice:** with `GNANI_API_KEY` set, narration uses Gnani Timbre v2.5 (cached per line).
  Without it, the browser's built-in voice is used, so the site works with no voice key.

How it fits together: the browser runs the player (it's where the audio plays, so it keeps
narration and actions in order). The backend (`server.py`, `server_class.py`, `jobs.py`)
only generates, approves, makes audio, runs code, writes recovery lines and runs doubt-agent turns.

## 3. Add a lecture from the command line

Pick a lecture id: 3 to 63 letters, digits, `_` or `-`, e.g. `py_listcomp_2026_10_17`.
Put the teacher's files in `data/<id>/`:

```
data/<id>/
├── persona.md      # required (copy templates/persona.md)
├── lecture.pptx    # at least one PPTX, PDF or DOCX
├── notes.pdf
└── lab.docx        # code in Courier/Consolas font is kept as code
```

To try it without real material, create sample files:

```bash
python tests/make_example_data.py example
```

### Filling in `persona.md`

Each `# Heading` holds `Key: value` lines. Every key below is required; `index` lists
everything that is missing at once. A value can continue on the next lines.

| Heading | Keys |
|---|---|
| `# Teacher` | Name, Subject, Class |
| `# Absence Note` | Reason, Message to class |
| `# Teaching Style` | Tone, Pace, Language, Habits |
| `# Lecture Structure` | Order, Must cover, Avoid |
| `# Next Class` | Topic, Prep |

## 4. Run it from the command line

```bash
python main.py index    --lecture example    # build the knowledge base
python main.py generate --lecture example    # write the script -> status: draft
python main.py approve  --lecture example    # validate script.md -> status: approved
python main.py render   --lecture example    # optional: pre-render narration audio, real duration
python main.py session  --lecture example --voice --mic   # run the class
```

Session modes:

| Flags | Narration | Student doubts |
|---|---|---|
| (none) | printed | typed |
| `--voice` | printed and spoken (Gnani TTS) | typed, answers spoken |
| `--voice --mic` | printed and spoken | typed, or type `r` + Enter to speak (Gnani STT), Enter to stop |

The session writes and runs the code for real in `workspace/lectures/<id>/board/`. It checks
each live output against the approved one; if an action fails, it says one recovery line and
carries on. Ctrl+C pauses: the position is saved in `session_state.json`, and `--resume`
continues from there.

Before approving, read `workspace/lectures/example/script.md` and edit it by hand
if you like. `approve` re-reads it, re-validates it and re-runs the code.

Voice notes: narration clips are cached in `workspace/lectures/<id>/audio/` by text and voice,
so `render` (or the first `--voice` session) is the only slow step. Re-running costs nothing
unless the script or voice changes. Doubt answers are synthesized live.

Other commands:

```bash
python main.py index   --lecture example --query "syntax"   # test a search
python main.py index   --lecture example --no-reset         # add without wiping
python main.py doubts  --lecture example                    # test one doubt checkpoint
python main.py status  --lecture example                    # print lecture.json
python main.py session --lecture example --force            # run a draft (warns)
```

During a session, type a student's doubt at each `Student doubt` prompt, or press
Enter for none. Ctrl+C stops the session (it stays `approved`).

Status flow: `indexed → draft → approved → completed`. Re-indexing resets to `indexed`;
re-generating resets to `draft`.

## 5. Where outputs go

```
workspace/lectures/<id>/
├── lecture.json      # status, settings, parsed persona
├── outline.json      # slide titles / sections / pages
├── script.md         # the script (edit this)
├── script.json       # parsed segments with expected outputs
├── script_failed.md  # only if generation could not produce a valid script
├── doubts_log.md     # every student question and answer
├── session_state.json# player position + event log (pending/running/done/failed)
├── audio/            # cached narration clips (WAV)
├── board/            # code files the class saw, run live
└── tmp/              # code files from dry runs
chroma_db/            # the vector store
```

## 6. Script markers

Every marker sits on its own line, e.g. `[RUN cmd="python demo.py"]`. Code goes between
`[WRITE_CODE file="demo.py"]` and `[/WRITE_CODE]`. See `prompts.py` for the full table.

The **notebook** is the teacher's blackboard, a ruled page on the Class screen:

```
[NOTE_TITLE text="while loop"]          an underlined heading
[NOTE]                                  lines written by hand, one per line
Repeats AS LONG AS the condition is True
count = 1 -> 2 -> 3 -> stop
[/NOTE]
[NOTE_HIGHLIGHT text="AS LONG AS"]      highlighter over words already in the notebook (quoted, not counted)
```

**Writing while speaking.** Add `while_speaking=true` to a notebook, code, highlight or slide marker
to run it during the narration right after it, instead of in silence before it:

```
[WRITE_CODE file="count.py" while_speaking=true]
count = 1
...
[/WRITE_CODE]
Let me write a loop that counts to three.     <- spoken while the code is typed
```

The narration must come right after the marker (or after `[/NOTE]` / `[/WRITE_CODE]`). Only its **first
sentence** is spoken while the writing appears (it should say what is being written: "Let me write the shape…");
the rest is spoken after, as the explanation. If a generated script doesn't announce its writing, code adds a
short lead ("Let me write this down: …") as a last resort. The writing is paced to fill most of the sentence,
and the class moves on when both are done. It is not allowed on
`RUN`, `READ_OUTPUT`, `PAUSE`, `SECTION` or `DOUBT_CHECK`. The website overlaps the two; the terminal
`session` speaks the sentence first, then runs the action.

Three markers point back at what is already on the screen. Doubt answers use them most
(see "Doubt answers" below), but they work in a lecture script too:

```
[LOOK_BACK text="checked BEFORE every round"]   scroll the notebook back to that line and highlight it
[OPEN_FILE file="count.py"]                     bring an earlier program back into the editor
[NEW_PAGE title="Why it stops at 3"]            turn to a fresh notebook page (shown as a page tab)
```

Code highlights quote the code instead of counting lines, so they can't point at the wrong line:

```
[HIGHLIGHT file="count.py" text="while count <= 3:"]                      one line
[HIGHLIGHT file="count.py" text="while count <= 3:" to="count = count + 1"]  a range
```

The quote must match exactly one line (spacing is ignored). `lines="3-5"` still works for
hand-written scripts, but `generate` rejects it.

`generate` requires a `[NOTE]` block in every section that has code. `tests/notebook_script.md`
is a short hand-written example.
Check a script by hand with:

```bash
python script_parser.py workspace/lectures/example/script.md
```

Parser tests: `tests/sample_script.md` must pass, and `tests/bad_script.md` must list every error.

### Doubt answers

At a question break the doubt agent answers the students itself. It passes a question to the real
teacher only when it needs them personally (marks, deadlines, exams, course decisions).
It has a `read_board` tool that shows everything on the class screen: the notebook by page and
section, the code files and the slides shown so far. The server rebuilds this from `script.json`
up to the question break, plus whatever earlier answers in the same class run added.
The answer is a short script, checked against that board before it plays. A `LOOK_BACK`,
`OPEN_FILE`, `HIGHLIGHT` or `NOTE_HIGHLIGHT` that quotes something not on the screen is dropped,
and new code is run first to record its real output. After the break, the stage returns to the
page and view the class was on.

### What the AI teacher may use: environments

The classroom has four environments: **notebook**, **slides**, **code** and **visual**. The Visual board holds
two kinds of pictures, each in its own tab: flow **diagrams** and interactive **graphs**. The notebook and slides
are always used. Code and the Visual board depend on the teacher's material, so the agent never invents a program
for a history class or a picture the material doesn't have:

| Environment | Used when |
|---|---|
| Notebook | always |
| Slides | the material has a PPTX deck |
| Code (`WRITE_CODE`, `RUN`, ...) | the material contains code (several code lines in the slides, PDF or DOCX) |
| Visual: diagrams (`FLOW`, ...) | the slides, PDF or DOCX have a diagram, or a written list of steps (1. 2. 3., Step 1/2/3, or A → B → C) |
| Visual: graphs (`VISUAL`, ...) | the slides contain a chart (`VISUALS_ENABLED=true`, the default); otherwise it is explained on its slide |

`index` finds them (`figures.py`) and saves them in `lecture.json` (`environments`) and `figures.json` (each diagram,
step list and chart with where it is). The writer is told which environments it has and which processes exist; a
script that uses another environment goes back to the writer, and as a last resort code removes those markers
(listed in the Log). In doubts, the agent may use only the environments the class itself used (notebook and slides
always). Studio shows a note about this and which environments the material unlocks.

### Flow diagrams, drawn block by block

For a process in the material, the teacher draws a diagram on the **Visual** board the way a teacher does at a
whiteboard: one block, an explanation, then the next block with its arrow. The script gives only the structure;
our own code (`web/js/flow.js`) draws it, top to bottom, the same way every time (no model writes any code):

```
[FLOW id="for-loop" title="How a for loop runs" from="slide 2"]
take: Take the next item
body: Run the loop body
more: Any items left? | yes -> take | no -> end
[/FLOW]
[FLOW_NEXT id="for-loop"]                      draws the next block and its arrows (in the order listed)
Let me draw the first step: take the next item.
[FLOW_HIGHLIGHT id="for-loop" block="more"]    points back at a drawn block
[OPEN_FLOW id="for-loop"]                      shows the diagram again
```

One block per line (`id: label`); a label ending in `?` is a question (a diamond) with branches `| answer -> id`
(or `end`). A loop back runs up the right side, a skip or exit down the left. Up to 8 blocks. `from` must name a
diagram or step list in the material. The parser checks the order (no block drawn twice, highlights only on drawn
blocks); the judge checks that each sentence said while a block appears is about that block, and that the diagram
follows the material's steps. Doubt answers can point at blocks, or draw a new diagram if the class used diagrams.

### Interactive graphs (on the Visual board; `VISUALS_ENABLED=false` turns them off)

A `[VISUAL]` is an **interactive graph** the class explores with sliders, like the ones Claude draws in chat:
a normal curve with mean and sd sliders, a fitted line with a slope slider and its error, how a value grows
with `n`. Diagrams are left to the slides. The graph appears in the **Visual** workspace next to the notebook,
slides and code, and redraws instantly as a slider moves.

```
[VISUAL id="normal" title="The normal distribution"]
A normal curve of value against probability density, with the area within one sd shaded.
controls: mean (slider -3-3 step 0.5), sd (slider 0.5-3 step 0.25)
[/VISUAL]
Let me show you this on a graph you can play with.
[VISUAL_SET id="normal" control="mean" value=1.5]   the teacher drags the slider there (about a second)
[VISUAL_SET id="normal" control="sd" value=2]
[OPEN_VISUAL id="normal"]                             show it again later
```

Controls: `name (slider 1-10)` (optional `step 0.5`); `name (choice a/b/c)` and `name (toggle)` when needed.
The parser checks every `VISUAL_SET` against them. A visual without a slider is sent back to the writer.

- **Building** (`visual_builder.py`, prompt `visual_prompt`): during `generate` (and on approve, if a
  description changed), `VISUAL_MODEL` writes one script that draws with the graph helper `Visual.chart`
  (`web/js/visual/chart.js`: axes, `fn`, `line`, `dots`, `bars`, `area`, reference lines, labels, a readout row).
  The builder also sees the programs on the screen and what the teacher says after each `VISUAL_SET`.
  Code checks it (handlers, `Visual.state`, no network or storage, JS syntax), then `visual_smoke.mjs`
  test-runs it in node: every slider is dragged across its range and must change the result, and text or
  shapes on top of each other are reported. Problems go back to the builder (up to 3 tries). A visual that
  still fails is removed and listed under auto-fixes in Studio. Built graphs are saved in
  `workspace/lectures/<id>/visuals/`.
- **In class**: each graph runs in a sandboxed frame (scripts only, no network) with a standard slider panel
  from `web/js/visual/runtime.js`. `VISUAL_SET` lights the slider up and drags it; students can drag it too.
- **In doubts**: `read_board` lists every graph with its sliders and values, and each question carries what
  every graph shows right now. An answer can drag any graph's sliders, or build one new graph.
- Settings (`.env`): `VISUALS_ENABLED=true`, `VISUAL_MODEL` (defaults to `LLM_MODEL`; a stronger coding model
  draws better graphs). Needs `node` for the test run (skipped without it).

## 7. Talking avatar

The classroom shows a 3D teacher whose lips move with the voice, who blinks, looks at the class, and moves
naturally. It is free and open source, runs entirely in the browser (no GPU server, no API keys), and does not
change how the TTS makes audio. The investigation and design are in `docs/avatar-plan.md`.

**Try it:** `python main.py serve`, then open **http://127.0.0.1:8000/avatar-demo.html** (debug overlay: FPS, current
viseme, RMS, lip-sync mode, audio delay slider; buttons for Play, chunked streaming, word timings, Stop, Mood and a
leak check). In a class, the avatar sits above the teacher card; the person button on the card turns it on or off.

**Turn it off** for everyone with `AVATAR_ENABLED=false` in `.env` (three.js is then never downloaded and the class
runs exactly as before, audio only). Each viewer can also hide it with the button; that choice is remembered.

### How it works

```
Gnani clip (WAV, 48 kHz PCM16) → <audio> → Voice output node ─┐
pushAudioChunk() → gapless AudioBufferSource queue ───────────┴→ avatar input → AnalyserNode → delay → speakers
                                                                                    │
                     every frame: RMS + spectrum → viseme → attack/release smoothing → blend shapes
```

- **One AudioContext** for the page (`web/js/avatar/audio-engine.js`), resumed on the first tap/click (iOS unlock).
- **The avatar plays the audio** (or taps the existing playback node), and the analyser is on the real output path, so
  the lips follow exactly what is heard and nothing is played twice.
- **Lip sync, chosen automatically:**
  - *Audio mode* (Gnani clips, streamed chunks): RMS with a noise gate opens the jaw; pre-emphasized spectral
    centroid, band energies and zero-crossing rate pick closed / open / spread / rounded / fricative, mapped onto
    the 15 Oculus visemes (or ARKit shapes for ARKit-only models).
  - *Timestamp mode* (browser fallback voice, or `setTimestamps`): words → visemes with TalkingHead's `lipsync-en`
    rules, scheduled on the clock. Used for the browser voice because its audio can't be routed into Web Audio;
    its word-boundary events give the timings.
  - Both: fast open (~50 ms), slower close (~100 ms), blended visemes, clamped weights, delay compensation ±150 ms.
- **Alive:** blinks every 2–6 s (~150 ms, sometimes double, more at phrase ends), small eye saccades mostly at the
  camera, slow noise-driven head sway and breathing, small nods and brow raises on loud syllables, moods
  (neutral / happy while waiting for questions / thinking while the agent answers).
- **Stop/pause** in the class calls `avatar.stop()`: queued audio fades out in 30 ms and the mouth is at rest in ~150 ms.

### Module API (`web/js/avatar/avatar.js`)

```js
const avatar = await createAvatar({ container, modelUrl, options });  // options: background, delayMs, mood, tuning, …
avatar.attachAudioStream(source);          // HTMLAudioElement, MediaStream or AudioNode (same AudioContext)
avatar.pushAudioChunk(chunk, { type: "pcm16", sampleRate: 48000, channels: 1 });  // or "float32", "wav", "mp3", …
avatar.setTimestamps({ words, times, durations });          // optional, ms; or { visemes, vtimes, vdurations }
avatar.stop(); avatar.setMood("happy"); avatar.setDelay(40); avatar.dispose();
avatar.addEventListener("speechstart" | "speechend" | "ready" | "error", …);
```

### Swap the avatar model

Put a GLB in `web/assets/avatars/` and set `AVATAR_MODEL_URL=/assets/avatars/your-model.glb` in `.env` (or pass
`modelUrl` to `createAvatar`). The camera frames head and shoulders from the model's own measurements.

**Required blend shapes** (morph targets, exact names):
- *Either* the Oculus visemes `viseme_PP, viseme_FF, viseme_TH, viseme_DD, viseme_kk, viseme_CH, viseme_SS,
  viseme_nn, viseme_RR, viseme_aa, viseme_E, viseme_I, viseme_O, viseme_U` (at least 10 of them; `viseme_sil` is
  optional, rest = all zero),
- *or* ARKit mouth shapes (`jawOpen`, `mouthClose`, `mouthFunnel`, `mouthPucker`, `mouthStretchLeft/Right`,
  `mouthSmileLeft/Right`, `mouthRollLower`, `mouthPressLeft/Right` …) — the module converts visemes to these.
- *Recommended (ARKit):* `eyeBlinkLeft/Right`, `eyeLookIn/Out/Up/DownLeft/Right`, `browInnerUp`,
  `browOuterUpLeft/Right`, `browDownLeft`, `cheekSquintLeft/Right`, `eyeSquintLeft/Right`.
- *Bones (optional):* `Head`, `Neck`, `Spine2` for sway and nods; `LeftArm`/`RightArm` are lowered out of the shot.

**Making a free avatar:**
- **Blender + MPFB** (MakeHuman Plugin For Blender, free; its assets are CC0): create a character, add the ARKit
  face rig and visemes, export as GLB. This is how the bundled avatar was made.
- **MetaPerson Creator / Avaturn** (free tiers): export GLB with ARKit blend shapes. Check each service's terms for
  your use; their free tiers are not always licensed for commercial use.
- **VRoid Studio** makes VRM models whose mouth shapes are VRM expressions (`aa`, `ih`, `ou`, `ee`, `oh`), not
  Oculus/ARKit names; it is not supported directly — rename the shape keys in Blender (VRM add-on) before export.
- Make the file small: `npx @gltf-transform/cli resize in.glb a.glb --width 1024 --height 1024`, then `webp`, then
  `meshopt` (the bundled avatar went from 36.8 MB to 3.15 MB).

### Tuning (`options.tuning` / `DEFAULT_TUNING` in `web/js/avatar/lipsync.js`)

| Setting | Default | Effect |
|---|---|---|
| `floorDb` | −52 | noise gate: below this the mouth is closed |
| `fullDb`, `headroomDb`, `rangeDb`, `curve` | −26, 3, 20, 1.6 | how loudness opens the mouth (adapts to the voice's peak) |
| `attackMs` / `releaseMs` | 50 / 100 | open fast, close slower |
| `maxWeight`, `caps`, `maxTotal` | 0.85, `{viseme_aa: 0.75}`, 1.1 | keep the mouth from opening too wide |
| `jawFromOpen` | 0.25 | extra ARKit `jawOpen` with loudness |
| `options.delayMs` | 0 | −150…150: + delays the sound, − delays the lips |
| `options.meshVisemeScale` | `{tongue: 0.3}` | damp visemes on matching meshes (tongue poking out) |
| `options.lifeIntensity` | 1 | 0 = still, >1 = livelier idle motion |
| `options.maxPixelRatio` | 2 | lower it on weak phones |

**Tests:** `node --test "tests/avatar/*.test.mjs"` (viseme mapping, smoothing, chunk scheduling, WAV/PCM, noise, life).

### Licenses (everything the avatar ships)

| Item | Where | License |
|---|---|---|
| three.js 0.170.0 (core, GLTFLoader, BufferGeometryUtils) | `web/vendor/three/` | MIT (`web/vendor/three/LICENSE`) |
| meshoptimizer decoder (part of three.js) | `web/vendor/three/addons/libs/` | MIT |
| TalkingHead `lipsync-en.mjs` (Mika Suominen) | `web/vendor/talkinghead/` | MIT (`web/vendor/talkinghead/LICENSE`) |
| Avatar `mpfb.glb` (TalkingHead repo, made with MPFB) | `web/assets/avatars/` | CC0 (`web/assets/avatars/LICENSE.md`) |
| Demo voice `sample.wav` | `web/assets/avatar-demo/` | generated by this project's own TTS |
| gltf-transform, sharp (only used once to shrink the GLB, not shipped) | — | MIT, Apache-2.0 |

Not used, on purpose: TalkingHead's other sample avatars (non-commercial licenses) and HeadAudio's trained model
(no stated license). No paid service or API key is involved in the avatar.

### Known limits

- Audio-only lip sync is a heuristic (no phoneme recognition): vowels and fricatives are distinguished, but
  `DD`/`kk`/`RR` only appear in timestamp mode. The browser fallback voice gets exact word timings.
- Measured in Chrome: lips trail the heard sound by ~20 ms, Stop reaches rest in ~130 ms, ~1 ms CPU per frame.
  Firefox and Safari (including iOS) use the same standard APIs but were not tested here.

## 8. Troubleshooting

- **The model does not use tools / errors about tools.** `LLM_MODEL` must support tool
  calling. Check the model page on OpenRouter for "tools", or try `openai/gpt-4o-mini`.
- **`Missing required settings in .env`.** Copy `.env.example` to `.env` and set
  `OPENROUTER_API_KEY` and `LLM_MODEL`.
- **Chroma metadata errors.** Chroma accepts only str, int, float and bool metadata.
  The indexer drops anything else; if you changed a loader, never put `None` or lists
  in metadata. To start clean, delete `chroma_db/` and run `index` again.
- **The script fails validation.** `generate` asks the model to fix it once; if errors
  remain it saves `script_failed.md`. Fix the listed lines, save it as `script.md`
  and run `approve`, or run `generate` again.
- **`GNANI_API_KEY is missing`.** Voice flags need it; run without `--voice/--mic` for text mode.
- **No sound / microphone errors.** Check the system output and input devices. On macOS, allow
  microphone access for your terminal under System Settings → Privacy & Security → Microphone.
  If speaking fails, the prompt falls back to typing.
- **Gnani `400 ... supported models are "timbre-v2.5"`.** The code always sends `timbre-v2.5`;
  update `gnani-vachana` if you still see this.
- **Gnani `429 RATE_LIMITED`.** Gnani allows one request at a time per key. `voice.py` queues
  calls and retries automatically; if a clip still fails, the browser voice is used for that line.
- **The website shows "Approve the script on the Home page first".** Class needs status `approved`
  (or `completed` to re-run). Saving an edit resets it to `draft`.
- **`Lecture not approved`.** Run `approve`, or use `session --force` for a quick look.
