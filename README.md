# Eris: the AI substitute that teaches your class, your way

When a teacher is away, Eris teaches their lesson for them. The teacher uploads their slides or notes and fills in a
short persona; Eris writes a lecture script in the teacher's voice, checks it for quality, and the teacher approves
it. Students then join the course with a class code and take the lesson in the browser: a voiced tutor teaches on
the teacher's own slides, a notebook, a code editor and interactive graphs, and answers their doubts live.

```
upload + persona ──► index ──► generate (draft) ──► checks (code + Jev) ──► approve ──► share ──► students learn
```

**How a class runs.** The LLM writes the script once and the teacher approves it. In class, a plain-code *player*
(`web/js/player.js` in the browser; `eris/classroom/session.py` in the terminal) walks the approved `script.json` one
segment at a time: narration plays (Gnani TTS), then the next action runs on the screen, then the next narration.
Each step finishes before the next starts, so speech and actions can't drift apart. During a class, LLMs are used
only for student doubts (`eris/classroom/doubt_agent.py`) and for a one-line recovery when an action fails
(`eris/classroom/recovery.py`). They get a read-only snapshot of the class; only the player moves forward.

## Features

**For teachers**
- **Courses, chapters, topics and lessons.** A course has a class code students join with. Each topic holds its
  lecture, optional **prerequisite** lessons (the groundwork to watch first) and its study material, all in one
  place on the course's **Classwork** page.
- **Create lecture / Edit lecture.** One workspace per lesson: upload the material (PPTX, PDF, DOCX, TXT or MD), fill
  in the teacher persona, pick the teaching language and voice, and click **Generate script**. Then read it in
  **Preview**, see the checks in **Quality**, change it in **Edit**, try it in **Classroom** and approve it.
- **No time to set.** The lesson is as long as the material needs (see "How long a lesson is", below), up to 30
  minutes of speaking.
- **Quality checks before anyone sees it.** Code checks and Jev (a separate judging model) check every script; real
  problems go back to the writer automatically (see "Quality checks").
- **Locked versions and sharing.** Sharing locks the approved script as a version and makes its voice clips ahead.
  A newer approved script reaches students only when the teacher shares the update.
- **Attendance.** A student is present once they have heard every line of a shared lesson. Each lesson row in
  Classwork shows "present" and "watching" counts and opens the full list.
- **Home page.** Counts, every lesson with how far it has come (material, script, approved, shared, watched), and
  the one thing that needs doing next. Clicking a lesson opens its lecture workspace.

**For students**
- Join a course with its class code, then see every topic's prerequisite, lecture and study material together.
- Take a lesson at their own pace: start, continue, pause, skip back. Progress is saved.
- Ask doubts by typing or speaking, at the question breaks or any time, and mark a line as confusing.

**Teaching**
- **The teacher's real slides.** Slides are shown as pictures of the deck itself (PowerPoint, or a PDF of lecture
  notes when there is no PowerPoint), with the line being read highlighted and pictures circled by a pen.
- **Four screens:** notebook, slides, code, and a visual board with interactive graphs and diagrams drawn block by
  block. Only the screens the material supports are used.
- **10 languages:** English, Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi, Bengali, Gujarati and Punjabi, with a
  voice that matches the teacher (a woman's or a man's voice, and the grammar to match).
- **A video tutor** (a woman or a man, matching the voice) that talks while the voice speaks; a 3D lip-synced avatar
  is the fallback.

**Doubts**
- An agent that knows where the class is, searches the teacher's material and teaches its answer on the same
  screens. "No doubts" in any language moves on instantly.
- Every question passes guardrails (prompt injection, harmful requests, abuse, personal data) before the agent
  sees it, and every answer is checked by Jev (does it answer, is it correct, is it safe) before it plays.
- Answers start speaking after their first sentence; the rest is voiced while it plays.

**Safety and deployment**
- Programs run only in a sandbox (Docker on a server, the OS sandbox on a Mac) with no network; if no sandbox is
  available, code runs are switched off instead of running unprotected. Students' doubt answers never run code.
- Teachers are created by the admin; the sign-in page asks "I'm a student / I'm a teacher" and the server checks it
  matches the account.
- One `docker compose` deploy with automatic HTTPS (Caddy). Step-by-step guides: `deploy/azure.md` (Azure for
  Students) and `deploy/README.md` (Google Cloud).

## Project layout

```
main.py                 command line: serve / seed / index / generate / approve / render / session / tutor-video / ...
eris/                   the Python package
  config.py             settings (.env), paths, languages and voices, the lecture manifest
  persona.py            reads persona.md
  prompts.py            every agent's system prompt
  tools.py              the agents' tools (search the material, run code, read the board, ask the class)
  guardrails.py         Jev's checks on doubt questions and answers
  sandbox.py            where programs run (Docker or the OS sandbox; off when neither is there)
  material/             reading the teacher's files: indexer.py (knowledge base), deck.py (which file is the slide
                        deck: a PPTX, else a PDF), slide_images.py (slides as pictures), images.py (pictures, read
                        by a vision model), figures.py (diagrams, step lists, charts and which screens the material
                        unlocks)
  generate/             making the script: depth.py (how long each part is), research + writer (script_agent.py),
                        the lesson (lesson.py) and its staging (staging.py), the generate command
                        (script_writer.py), checks and repairs (script_pipeline.py, script_checks.py,
                        script_fixes.py, format_fixes.py), the parser (script_parser.py) and Jev (script_judge.py)
  visuals/              the Visual board: flow diagrams (flow_diagram.py) and interactive graphs
                        (visual_builder.py, visual_controls.py, visual_smoke.mjs)
  classroom/            running a class: doubt_agent.py, class_board.py, session.py (terminal class), actions.py,
                        recovery.py, voice.py, tutor_video.py
  platform/             accounts and courses: db.py (SQLite), auth.py (sign-in), access.py (who sees what),
                        seed.py (demo data)
  api/                  the website backend: server.py, server_platform.py (courses, lessons, attendance),
                        server_class.py (the class, voice, doubts), jobs.py
web/                    the website (plain HTML/CSS/JS, no build step)
templates/              the example persona, and demo lessons for `seed`
deploy/, Dockerfile, docker-compose.yml   running it on a server
docs/                   design notes
data/, workspace/       lecture material, generated files and the database (local, not in git)
```

A module's own command runs with `python -m`, e.g. `python -m eris.generate.script_parser script.md`.

## 1. Setup (about 5 minutes)

You need [uv](https://docs.astral.sh/uv/) and an [OpenRouter](https://openrouter.ai) API key. For slides shown as
pictures from PowerPoint, install [LibreOffice](https://www.libreoffice.org) (PDF decks need nothing extra).

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install -r requirements-extras.txt  # optional: teacher video (modal) and better lip sync (faster-whisper)
cp .env.example .env
python main.py seed                        # optional: demo accounts and courses
```

Edit `.env` (every setting is explained in `.env.example`):

| Variable | Meaning |
|---|---|
| `OPENROUTER_API_KEY` | required |
| `LLM_MODEL` | required: an OpenRouter model that supports **tool calling**, e.g. `anthropic/claude-haiku-5.5` |
| `EMBED_MODEL` | embedding model (default `baai/bge-m3`) |
| `JUDGE_MODEL` / `JUDGE_ENABLED` | Jev, the model that checks scripts and doubt answers (default `typesafe/jev-1.13`, on) |
| `GUARDRAILS_ENABLED` / `DOUBT_JUDGE` | check doubt questions and answers (both on by default) |
| `VISION_MODEL` / `VISUAL_MODEL` | reads pictures in the material / builds interactive graphs (default `LLM_MODEL`) |
| `SPEAKING_WPM` | the voice's real speed with pauses (default 115): minutes x this = words. Measure it with `python main.py measure-voice` |
| `GNANI_API_KEY` | Gnani voice (TTS) and spoken doubts (STT). Without it the browser's own voice is used |
| `TTS_VOICE` / `TTS_LANGUAGE` / `TTS_SPEED` | default voice and language (`Kaveri`, `en-IN`); each lesson picks its own |
| `ERIS_DEMO_LOGINS` | one-click demo accounts on the sign-in page (turn off for real users) |
| `ERIS_TEACHER_SIGNUP` | let anyone sign up as a teacher (off: only students sign up) |
| `ERIS_STUDENT_CODE_RUNS` | let students' doubt answers run programs (off) |
| `ERIS_SANDBOX` | where programs run: `auto`, `docker`, `os` or `off` |
| `ERIS_DOMAIN` / `ERIS_SECURE_COOKIES` | on a server: the domain for HTTPS, and HTTPS-only sign-in cookies |

`LECTURE_DURATION_MIN` and `SPEAKING_MIN` are only used when the depth plan can't be made.

## 2. The website (easiest way)

```bash
python main.py serve        # then open http://127.0.0.1:8000
```

1. **Sign in.** Choose "I'm a teacher" or "I'm a student". With `python main.py seed`, demo accounts sit under the
   form: three teachers with demo courses, three students, and a blank **Test Teacher** and **Test Student** with
   nothing in them, to try everything from the start.
2. **Make a course** (teacher). On Home, **New course**. In its **Classwork**, add a chapter, a topic, then a
   **Lesson** or a **Prerequisite**.
3. **Create the lecture.** Click **Create lecture** on the lesson: upload the material, fill in the persona (or
   **Use example**), set the topic, language and voice, and **Generate script**. The progress streams while it
   indexes, plans, writes and checks.
4. **Review.** Read the script in **Preview**, see each check in **Quality**, change it in **Edit**, and run it in
   the **Classroom** tab. Approve it, then **Share** it from Classwork.
5. **Take the class** (student). Join with the class code, open the lesson and press play. At each question break,
   type or speak a doubt.
6. **Back as the teacher.** Classwork shows each shared lesson's attendance; the lecture workspace shows its
   versions.

**Voice:** with `GNANI_API_KEY` set, narration uses Gnani Timbre v2.5 (cached per line, made ahead when a lesson is
shared). Without it, the browser's built-in voice is used, so the site works with no voice key.

How it fits together: the browser runs the player (it's where the audio plays, so it keeps narration and actions in
order). The backend generates, checks, approves, makes audio and slide pictures, runs code in the sandbox, keeps
courses, progress and attendance in SQLite (`workspace/eris.db`), and runs doubt-agent turns.

### How long a lesson is

The teacher never sets a time. `eris/generate/depth.py` splits the material into sub-topics and asks Jev six yes/no
questions about how the material explains each one (a specific case? steps? builds on another part? a comparison?
an exception? a task for students?). Jev's confidence in each yes, plus one per extra slide, gives a score: under
2.0 is **Brief** (0.6 min), 3.5 or more is **In depth** (2.2 min), **Normal** (1.2 min) between. A "Must cover" item
is never brief; the lesson's main idea is always in depth. Opening, recap and closing add 1.4 minutes.

Minutes x `SPEAKING_WPM` gives each section its word budget, and a section that comes out far too short goes back to
the writer. If the plan needs more than 30 minutes of speaking (about 35 minutes of lesson), every part is shortened
by the same share and Studio suggests splitting the material into two lessons.

### Quality checks

`generate` writes in three steps (research, the lesson's teaching, then staging for the screen) and checks after
each one:

- **Code checks** (exact): the script's format, every program runs, no programs if the material has none, every
  figure used is in the material, calculation steps are explained one at a time, each section is near its planned
  length, and staging didn't change a single spoken sentence.
- **Jev** (`eris/generate/script_judge.py`) answers yes/no questions with a confidence: covers "Must cover", stays
  away from "Avoid", notes and narration match the programs and their output, graphs match what is said (these are
  blockers), plus the opening and closing, the teacher's style, natural speech, clear and true explanations,
  pictures explained and highlights that fit (minor). A check passes at 0.5.
- **What happens:** code problems and Jev blockers go back to the writer (at most 2 rounds, only the failing
  sections), and the best version is kept. Minor findings show as tips in Studio's **Quality** tab, and repairs made
  by code are listed as auto-fixes.

## 3. Add a lecture from the command line

Pick a lecture id: 3 to 63 letters, digits, `_` or `-`, e.g. `py_listcomp_2026_10_17`.
Put the teacher's files in `data/<id>/`:

```
data/<id>/
├── persona.md      # required (copy templates/persona.md)
├── lecture.pptx    # at least one PPTX, PDF or DOCX; the PPTX is the slide deck
├── notes.pdf       # with no PPTX, the first PDF is the deck: each page is a slide
└── lab.docx        # code in Courier/Consolas font is kept as code
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
python main.py index    --lecture example    # build the knowledge base (set the topic in the lecture workspace)
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
python main.py stage   --lecture example --runs 3           # stage the saved lesson again and report (saves nothing)
python main.py seed                                         # demo accounts and courses (safe to run again)
python main.py measure-voice                                # measure the voice's speed, save SPEAKING_WPM
python main.py tutor-video --idle idle.mp4 --talking talk.mp4 [--name male]   # make the classroom's video tutor
python main.py serve --host 0.0.0.0 --port 8000             # accept outside connections (in a container)
```

During a session, type a student's doubt at each `Student doubt` prompt, or press
Enter for none. Ctrl+C stops the session (it stays `approved`).

Status flow: `indexed → draft → approved → completed`. Re-indexing resets to `indexed`;
re-generating resets to `draft`.

## 5. Where outputs go

```
workspace/lectures/<id>/
├── lecture.json      # status, settings, parsed persona, screens, depth plan
├── outline.json      # slide titles / sections / pages (the deck marked, with its slide count)
├── lesson.md         # the teaching before staging (step 2), kept for review
├── script.md         # the script (edit this)
├── script.json       # parsed segments with expected outputs
├── judge.json        # Jev's findings, rounds and auto-fixes (Studio's Quality tab)
├── images.json, figures.json   # pictures in the material and what the vision model saw; diagrams and charts
├── slides/           # the deck drawn as pictures, with every text line's and picture's position
├── visuals/          # built interactive graphs
├── script_failed.md  # only if generation could not produce a valid script
├── doubts_log.md     # every student question and answer
├── session_state.json# player position + event log (pending/running/done/failed)
├── audio/            # cached narration clips (WAV, plus small AAC copies for browsers)
├── board/            # code files the class saw, run live
└── tmp/              # code files from dry runs
workspace/eris.db     # accounts, courses, lessons, versions, progress, attendance, doubt logs (SQLite)
workspace/versions/   # each approved script version that was shared
chroma_db/            # the vector store
```

## 6. Script markers

Every marker sits on its own line, e.g. `[RUN cmd="python demo.py"]`. Code goes between
`[WRITE_CODE file="demo.py"]` and `[/WRITE_CODE]`. See `eris/prompts.py` for the full table.

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

`generate` requires a `[NOTE]` block in every section that has code.
Check a script by hand with:

```bash
python -m eris.generate.script_parser workspace/lectures/example/script.md
```


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
two kinds of pictures, each in its own tab: flow **diagrams** and interactive **graphs**. The notebook is always
used. The slides, code and the Visual board depend on the teacher's material, so the agent never invents a program
for a history class or a picture the material doesn't have:

| Environment | Used when |
|---|---|
| Notebook | always |
| Slides | the material has a deck: a PPTX, or (with no PPTX) a PDF whose pages are the slides (`eris/material/deck.py`) |
| Code (`WRITE_CODE`, `RUN`, ...) | the material contains code (several code lines in the slides, PDF or DOCX) |
| Visual: diagrams (`FLOW`, ...) | the slides, PDF or DOCX have a diagram, or a written list of steps (1. 2. 3., Step 1/2/3, or A → B → C) |
| Visual: graphs (`VISUAL`, ...) | the slides contain a chart (`VISUALS_ENABLED=true`, the default); otherwise it is explained on its slide |

`index` finds them (`eris/material/figures.py`) and saves them in `lecture.json` (`environments`) and `figures.json` (each diagram,
step list and chart with where it is). The writer is told which environments it has and which processes exist; a
script that uses another environment goes back to the writer, and as a last resort code removes those markers
(listed in the Log). In doubts, the agent may use only the environments the class itself used (notebook and slides
always). Studio shows a note about this and which environments the material unlocks.

### Pictures in the material (vision)

Slides and documents often teach through pictures: a painting, a map, a photo, a diagram or a chart saved as an
image. Text extraction can't see those, so `index` sends every picture (bigger than an icon) once to a vision
model (`VISION_MODEL`, default `LLM_MODEL`; it must accept images) with the slide's text as context
(`eris/material/images.py`). The model returns what kind of picture it is, what it shows and what to notice, every
word written in it (OCR), a diagram's steps and a chart's data. Results are cached by the picture's content.

- The descriptions join the knowledge base, so search and the agents find them ("Picture on slide 3: …").
- A diagram picture with steps can be drawn as a flow, a chart picture recreated as a graph, and any other picture
  is listed for the writer as something to show and explain.
- The doubt agent's board says what the picture on each slide shows.
- In class, the Slides view shows each slide itself as a picture (`eris/material/slide_images.py`: LibreOffice draws a
  PPTX, a PDF is drawn directly). The position of every text line and picture is saved, so `SLIDE_HIGHLIGHT` sweeps
  a highlighter over the exact line on the picture and `SLIDE_CIRCLE` draws a pen circle around a picture. Pictures
  that are icons or one flat colour (a box's shadow in a PDF) are left out.

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

- **Building** (`eris/visuals/visual_builder.py`, prompt `visual_prompt`): during `generate` (and on approve, if a
  description changed), `VISUAL_MODEL` writes one script that draws with the graph helper `Visual.chart`
  (`web/js/visual/chart.js`: axes, `fn`, `line`, `dots`, `bars`, `area`, reference lines, labels, a readout row).
  The builder also sees the programs on the screen and what the teacher says after each `VISUAL_SET`.
  Code checks it (handlers, `Visual.state`, no network or storage, JS syntax), then `eris/visuals/visual_smoke.mjs`
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

## 7. The tutor and the talking avatar

**The video tutor (default).** Beside the caption, the classroom shows a short looping video of the tutor: the
talking loop while the voice speaks, the idle loop otherwise. There are two tutors, a woman and a man; each lesson
shows the one that matches its voice. Make a tutor from an idle clip and a talking clip with
`python main.py tutor-video --idle idle.mp4 --talking talking.mp4` (add `--name male` for the man's); it crops to
the face and writes `web/assets/tutor/`.

**The 3D avatar (fallback).** If the videos can't load, the classroom shows a 3D teacher whose lips move with the voice, who blinks, looks at the class, and moves
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
  calling. Check the model page on OpenRouter for "tools", or try `anthropic/claude-haiku-5.5`.
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
- **Gnani `429 RATE_LIMITED`.** Gnani allows one request at a time per key. `eris/classroom/voice.py` queues
  calls and retries automatically; if a clip still fails, the browser voice is used for that line.
- **The classroom says "This class isn't ready yet".** Its script needs to be generated and approved first
  (Create lecture / Edit lecture). Saving an edit resets it to `draft`.
- **Slides show as text, not pictures.** A PPTX needs LibreOffice (`soffice`) to be drawn; install it and reload. A
  PDF deck is drawn without it.
- **Code lessons can't run programs.** No sandbox was found, so code runs are off: start Docker (and
  `docker pull python:3.12-slim`), or set `ERIS_SANDBOX=os` on a Mac.
- **A sign-in is refused with "This is a teacher account".** Choose "I'm a teacher" (or "I'm a student") to match
  the account, then sign in again.
- **`Lecture not approved`.** Run `approve`, or use `session --force` for a quick look.
