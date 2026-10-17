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
  the persona fields (prefilled from `data/example/persona.md`), set the Topic, and click
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
├── persona.md      # required (copy data/example/persona.md)
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

## 7. Troubleshooting

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
