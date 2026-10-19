# Implementation Plan — AI Substitute Teacher v2

**For:** the coding agent continuing after v1
**Builds on:** `IMPLEMENTATION_PLAN_v1.md` (all of its rules still apply unless a step below says otherwise)
**One-line summary:** Keep the script-first player, then add finer narration/action sync (Level 2 and Level 3),
verify the real Gnani voice path, and prepare the pieces that need a team decision (realtime voice, visual board).

---

## 0. Where we are (baseline, already built — do not rebuild)

| Area | Built in v1.5 |
|---|---|
| Pipeline | `index → generate (draft) → approve → render → session` |
| Script | Markers on their own lines, strict parser, `expected_output` filled by running the code |
| Player | `eris/classroom/session.py` walks `script.json` one segment at a time; LLM only for doubts and recovery |
| Sync | **Level 1 only**: each segment finishes before the next starts |
| Voice | Gnani Timbre v2.5 TTS (`eris/classroom/voice.py`, cached clips, `render`), Gnani STT push-to-talk (`--mic`) |
| Board | Terminal + real files in `workspace/lectures/<id>/board/`; live `RUN`, output compared with expected |
| State | `session_state.json` (cursor + event log), Ctrl+C pause, `--resume` |
| Recovery | `eris/classroom/recovery.py`: one spoken line when an action fails, fixed fallback if the LLM is down |

Everything below is **not built yet**.

---

## 1. Rules for the coding agent (additions to v1 §0)

1. All v1 rules hold: plain functions and dicts, files under ~200 lines, tools never raise, print every step.
2. **Non-blocking audio is allowed** (`sounddevice.play()` without `wait()`, then `wait()` later).
   It is not a thread we manage. **No `threading`, no `asyncio`** until Step 6, and Step 6 needs team sign-off first.
3. Text mode (no `--voice`) must keep working after every step, with the same output order as today.
4. Old scripts must still parse. New syntax is opt-in; a script without it behaves exactly as in v1.
5. Every new marker or flag goes in three places together: `eris/generate/script_parser.py` (rules), `eris/prompts.py`
   (marker table plus an example), and `README.md`.
6. Ask before adding a dependency. The steps below name the ones they may need.

---

## 2. Build order

| Step | What | Needs |
|---|---|---|
| 1 | Verify the real Gnani voice path | `GNANI_API_KEY` |
| 2 | **Level 2:** `while_speaking=true` (action runs during the next narration) | — |
| 3 | **Level 3:** inline anchors `{HIGHLIGHT lines="2"}` fired at a word | Step 2 |
| 4 | Lecture timeline (`timeline.json`) from rendered audio | Step 3 |
| 5 | Persistent doubt memory across `--resume` | `langgraph-checkpoint-sqlite` (ask) |
| 6 | Realtime, interruptible voice ("barge-in") | team sign-off: async |
| 7 | Visual board (slides and code in a browser window) | team decision: format |
| 8 | Teacher voice cloning (optional) | the teacher's written consent |
| 9 | Housekeeping | — |

---

### Step 1 — Verify the real Gnani voice path

**Purpose:** everything voice-related has only been tested with stubs. Prove the real path before adding sync on top of it.

- Add `python main.py voicecheck` (in `main.py`, about 20 lines):
  1. `check_voice_env()`.
  2. Synthesize "Hello class, this is a voice check." to `tmp/voicecheck.wav`, print its duration, and play it.
  3. Ask "Press Enter, say something, press Enter", record it, run STT and print the transcript.
- Confirm the output format the API really returns (expected: 48 kHz, 16-bit mono WAV). If it differs,
  adjust `voice.play()` and add a comment with the real values.
- Confirm that long narration (more than `TTS_CHUNK_CHARS`) joins into one clip with no gap or click at the seams.

**Test:** `voicecheck` plays audible speech and prints a transcript that matches what you said.
`render --lecture example` finishes with `0 clip(s) failed`, and `lecture.json` gains `audio_min`.

---

### Step 2 — Level 2: actions that run *while* narration plays

**Purpose:** today the class hears silence while code is "typed". Let an action run during the narration that describes it.

**Syntax (opt-in flag on the action marker):**
```
[WRITE_CODE file="filter.py" while_speaking=true]
scores = [10, 25, 4, 30]
high = [s for s in scores if s > 10]
print(high)
[/WRITE_CODE]
Let me write a small program that keeps only the scores above ten.
```
Meaning: **start the next narration, run this action at the same time, and continue only when both are done.**

**Parser rules (`eris/generate/script_parser.py`):**
- `while_speaking` is allowed only on `WRITE_CODE`, `HIGHLIGHT`, `SLIDE`, `SLIDE_HIGHLIGHT` and `WRITE`.
  On `RUN`, `READ_OUTPUT`, `PAUSE` or `DOUBT_CHECK` it is an error, because those must happen in silence or in order.
- The value must be `true` or `false`. Store it as a bool: `args["while_speaking"] = True`.
- The **next segment must be a `say`**. Otherwise: `line N: [WRITE_CODE] while_speaking needs narration right after it`.
- Add one error case for each rule to `tests/bad_script.md`, and one valid use to `tests/sample_script.md`.

**Voice (`eris/classroom/voice.py`):**
- `start(path) -> float`: `sd.play(data, rate)` **without** `wait()`; returns the clip duration in seconds.
- `wait()`: `sd.wait()`. Ctrl+C calls `sd.stop()` and re-raises, as `play()` does today.
- `play()` becomes `start()` followed by `wait()`.

**Actions (`eris/classroom/actions.py`):**
- `execute(board, segment, duration_s=None)`. When `duration_s` is given, `write_code` spreads its typing
  over about 80% of the clip: `delay = min(0.8 * duration_s / line_count, 0.5)`. Other actions ignore it.

**Player (`eris/classroom/session.py`, `play_segment`):**
```
if args.get("while_speaking") and next segment is say:
    mark both segments running
    duration = voice.start(clip of next say)    # text mode: print the narration, duration = None
    result = actions.execute(board, seg, duration)
    voice.wait()                                 # join: both done
    mark both done (or the action failed → recovery line AFTER the audio ends)
    skip the next index
```
- Save `cursor` past **both** segments only after the join. `--resume` restarts the pair from the beginning.
- Text mode: print the narration first, then run the action. No timing.

**Prompt:** add `while_speaking=true` to the marker table, with one sentence on when to use it
("for writing code or changing slides while you describe them") and a two-line example.

**Test:**
1. The parser accepts the valid example and reports every new error case.
2. Offline, with a fake 3-second clip and a 6-line `WRITE_CODE`: the pair takes about 3 s (not 3 s plus typing time),
   and `session_state.json` shows both segments `done` with the same end time.
3. Real voice: the code appears line by line while the sentence is spoken.

---

### Step 3 — Level 3: inline anchors fired at a specific word

**Purpose:** "now look at **this line**" should highlight line 2 the moment "this line" is said, not before the sentence starts.

**Syntax (inside narration, curly braces):**
```
Now look at {HIGHLIGHT file="filter.py" lines="2"} this line, the filter. Then {SLIDE n=4} the next slide shows the rule.
```
- An anchor is `{` + an UPPERCASE marker name + args + `}`, using the same arg grammar as `[...]` markers.
- Allowed only for instant markers: `HIGHLIGHT`, `SLIDE`, `SLIDE_HIGHLIGHT`, `WRITE`. Anything else is an error.
- A `{` followed by anything other than an uppercase marker name stays normal text.

**Parser (`eris/generate/script_parser.py`):**
- `extract_anchors(text) -> (clean_text, anchors)`: removes each anchor and records
  `{"char": <offset in clean_text>, "name": ..., "args": ...}`.
- The `say` segment becomes `{"kind": "say", "text": clean_text, "anchors": [...]}`. Omit the key when there are none.
- Validate each anchor with `_check_marker`, as if it stood on its own line at that point in the script.
  For example, a `HIGHLIGHT` anchor on a file not written yet is an error.
- `estimate_minutes` counts words of `clean_text` only.

**Timing (new file `timing.py`, about 60 lines):**
Gnani returns **no word timestamps**, so anchor times are **estimated** from the clip duration:
- `anchor_times(clean_text, duration_s, anchors) -> list[float]`
- Weight each character as 1, and add extra weight for pauses: `,` = 4, `.` `!` `?` = 8.
  `t = duration_s × weight_before_anchor / total_weight − ANCHOR_LEAD_S`, clamped to `[0, duration_s]`.
- `ANCHOR_LEAD_S = 0.15` in `eris/config.py`: firing slightly early feels in sync; firing late feels broken.
- Expected accuracy is about ±0.5 s. That is fine for highlights and slides; it is not lip-sync.
- *Later option, not now:* a forced aligner such as `aeneas` or `whisperx` gives exact word times.
  It is heavy, so ask before adding it.

**Player (`eris/classroom/session.py`):**
```
say with anchors, voice on:
    duration = voice.start(clip)
    t0 = time.monotonic()
    for (t, anchor) in sorted(anchor_times(...)):
        time.sleep(max(0, t0 + t - time.monotonic()))
        result = actions.execute(board, anchor)      # instant actions only
        log event "anchor" with planned t and actual t
    voice.wait()
say with anchors, text mode:
    print the clean text, then run the anchors in order (no sleeping)
```
- A failed anchor is logged and does **not** call recovery mid-sentence. The recovery line plays after the clip ends.
- Each event records `planned_s` and `actual_s`, so drift can be measured.

**Prompt:** explain anchors in the marker section with one example. Tell the model to prefer anchors
for "look at this line" moments and plain `[HIGHLIGHT]` lines otherwise. At most one anchor per sentence.

**Test:**
1. `extract_anchors` unit cases: no anchors, two anchors, an anchor at the very start or end,
   `{not a marker}` left untouched, an invalid anchor name reported.
2. `anchor_times` on a known string and duration returns the expected values (within 0.01 s).
3. Offline player with a fake 4-second clip and anchors planned at 1.0 s and 3.0 s: the logged
   `actual_s` is within 0.1 s of plan.
4. Real voice: the highlight lands on or just before the spoken words.

---

### Step 4 — Lecture timeline

**Purpose:** with every clip rendered, the whole lecture can be laid out in time before class.

- `render` also writes `timeline.json`:
  ```json
  [{"index": 3, "kind": "say", "start_s": 41.2, "duration_s": 6.8, "anchors": [{"name": "HIGHLIGHT", "at_s": 44.0}]},
   {"index": 4, "kind": "action", "name": "RUN", "start_s": 48.0, "duration_s": 30.0}]
  ```
  Use the real clip duration for `say`, `RUN_MIN_EACH` for `RUN`, `s` for `PAUSE`, 0 for instant actions,
  and the budgeted share of `DOUBT_TIME_SHARE` for each `DOUBT_CHECK`.
- `render` prints a per-section summary and warns when the total is more than 15% off `duration_min`.
- `session` prints planned against actual time at each `SECTION`, so the class can tell when it is running late.

**Test:** `timeline.json` start times always increase, and its total matches the `estimated_min` printed by `render`.

---

### Step 5 — Persistent doubt memory across `--resume`

**Purpose:** today `--resume` restores the board and position, but the doubt agent forgets earlier questions (`InMemorySaver`).

- Ask before adding `langgraph-checkpoint-sqlite`.
- Replace `InMemorySaver` with `SqliteSaver` at `workspace/lectures/<id>/checkpoints.sqlite` for the doubt agent only.
- Store the current `thread_id` (including the failure suffix) in `session_state.json`, and reuse it on resume.
- Remove the `# v2: replace InMemorySaver` comment in `eris/config.py`.

**Test:** ask a doubt, Ctrl+C, `--resume`, then ask "what did I ask before?". The agent knows.

---

### Step 6 — Realtime, interruptible voice ("barge-in")  ⚠️ needs team sign-off

**Purpose:** a student can interrupt mid-narration ("excuse me, I have a doubt") instead of waiting for `DOUBT_CHECK`.

**Why it needs sign-off:** it breaks rule 2. It needs `asyncio` (Gnani's WebSocket clients are async) and
always-on microphone streaming. Decide this as a team before writing code.

**Design, if approved:**
- `GnaniSTTStreamClient` listens all the time. Server-side VAD emits a transcript for each utterance.
- A small keyword check (no LLM) on each transcript: "doubt", "question", "excuse me", "sir/ma'am", or the teacher's name.
- On a match: `sd.stop()`. The player finishes the **current action** (never cut a `RUN` in half), marks
  the clip `interrupted`, and runs an unscheduled doubt checkpoint with the same snapshot as a `DOUBT_CHECK`.
- Afterwards, replay the interrupted clip from the start (simplest), or from the last sentence boundary (later).
- Use `GnaniTTSRealtimeClient` for doubt answers to cut time to first audio.
- Echo: the mic hears the TTS. Ignore transcripts while the player is speaking unless they contain a keyword,
  or recommend headphones or a separate classroom mic.

**Test:** during narration, say "excuse me, I have a doubt". The audio stops within about 1 s, the doubt is answered,
and the lecture resumes from the interrupted clip. Teacher speech alone never triggers it.

---

### Step 7 — Visual board  ⚠️ needs a format decision

**Purpose:** students see slides and code on a projector, not a terminal.

**Option A (simplest, no server):** after every action, `eris/classroom/actions.py` rewrites `board/index.html` with the current
slide text, the code with highlighted lines, and the last output. A `<meta http-equiv="refresh" content="1">`
reloads it. Open it once with `webbrowser.open()`. No new dependency.

**Option B (later):** a real UI on the platform (WebSocket push), once the platform exists. That is out of scope here.

- Slides as images (not just text) need exporting the PPTX (LibreOffice `soffice --convert-to pdf`, then images).
  That is an external tool, so ask first.
- Build Option A only after the team agrees.

**Test:** run a session with the board page open. Every `SLIDE`, `WRITE_CODE`, `HIGHLIGHT` and `READ_OUTPUT`
shows up within about 1 s, including anchors fired by Step 3.

---

### Step 8 — Teacher voice cloning (optional)  ⚠️ needs consent

**Purpose:** narration in the teacher's own voice. Gnani supports `speaker_embedding` on every TTS client.

- **Only with the teacher's written consent**, recorded in `persona.md` as a new `# Voice` heading:
  `Consent: yes`, `Reference audio: voice_sample.wav`.
- New `python main.py clonevoice --lecture <id>`: call the voice-clone embeddings endpoint once, and save the
  embedding to `data/<id>/speaker_embedding.json` (gitignored).
- `voice.synthesize` passes `SpeakerEmbedding(...)` when that file exists. Add the embedding's hash to the
  clip cache key, so cloned clips never mix with stock-voice clips.
- With no consent line, refuse with a clear message.

**Test:** `render` with an embedding produces clips in the cloned voice. Deleting the file switches back to `TTS_VOICE`.

---

### Step 9 — Housekeeping

- `eris/material/indexer.py` is about 237 lines: move the four loaders into `loaders.py` (agreed exception to rule 2 of v1).
- `eris/generate/script_parser.py` will pass 200 lines after Steps 2 and 3: move anchor handling into `anchors.py`.
- Script quality: if `generate` logs no `[tool]` lines, print a warning recommending a stronger `LLM_MODEL`.
  The structure checks already reject truncated scripts.
- Add `tests/run_offline.py`: the fake-embeddings and fake-LLM end-to-end run used during development,
  so anyone can check the full pipeline without API keys.

---

## 3. Definition of done (v2)

- [ ] `voicecheck` passes with the real Gnani key; `render` produces every clip.
- [ ] Level 2: a `while_speaking` pair takes about the clip length, and both segments are logged as done together.
- [ ] Level 3: logged anchor times are within 0.1 s of plan offline, and land on the right words with real audio.
- [ ] `timeline.json` exists, and its total matches `estimated_min`.
- [ ] `--resume` keeps the doubt memory.
- [ ] Text mode output is unchanged for scripts that use none of the new syntax.
- [ ] Steps 6 to 8 are either built after an explicit team decision, or still listed here as pending.
- [ ] Every file is still about 200 lines or less (after Step 9).
