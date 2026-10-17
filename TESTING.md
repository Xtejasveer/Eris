# Testing checklist: "Python while loops" lecture

A fresh end-to-end test of the website with new material. It takes about 15 minutes.

## 0. Setup (once per machine)

```bash
cd /Users/tejasveer/Desktop/Eris
source .venv/bin/activate
uv pip install -r requirements.txt
python tests/make_while_loop_data.py      # creates the sample material (safe to re-run)
```

Check `.env`: `OPENROUTER_API_KEY` and `LLM_MODEL` are required. `GNANI_API_KEY` is optional;
without it the browser voice is used.

Start the server and open **http://127.0.0.1:8000**:

```bash
python main.py serve
```

## The sample material

| File | What's in it |
|---|---|
| `while_loops.pptx` | 7 slides: Introduction, Recap for loops, Syntax, Counting, Infinite loops, break, for or while? |
| `while_notes.pdf` | 1 page of notes (syntax, update rule, break/continue, common mistake) |
| `lab5_while.docx` | Aim, Theory, and 3 programs in Courier font (countdown, reach 50 runs, first score > 40) |
| `persona.md` | Prof. Sharma; Must cover: syntax, update, infinite loops, break; Avoid: while-else, nested loops, recursion, input() |

It exists in two places:
- `data/while_loops/`: ready to use (Test A).
- `sample_material/while_loops/`: to test the upload bar (Test B). The website never uploads
  `persona.md`; the persona always comes from the form.

---

## Test A: the ready lecture (fastest)

1. In the sidebar, set **Lecture** to `while_loops` and press Enter.
   - [ ] Three files appear under Study material.
   - [ ] The persona form shows "while-else; nested loops; recursion…" under **Avoid**.
2. Set **Topic** to `Python while loops` and **Duration** to `15` (the topic field does not come from persona.md).
3. Click **Generate script** and wait 1 to 3 minutes.
   - [ ] The log shows `[tool] read_outline()`, several `[tool] search_material(...)` and `[tool] dry_run_python(...)` lines.
   - [ ] It ends with "Script ready below".
   - If it fails, the failed draft is shown with its errors. Fix them with **Edit**, or Generate again.
     After two failures, try `LLM_MODEL=openai/gpt-4o-mini` in `.env` and restart the server.
4. Read the **Script preview**:
   - [ ] It starts with an Opening: Prof. Sharma is at a workshop, plus the message to the class.
   - [ ] It covers syntax, the update line, infinite loops and break.
   - [ ] There are no while-else, nested loops or `input()`.
   - [ ] Each code block is followed by HIGHLIGHT, RUN and READ_OUTPUT.
   - [ ] Every section with code has a notebook card (keywords, a small example with numbers) before the code.
   - [ ] It ends with the next class (Functions in Python) and a final doubt check.
5. Optional edit test: **Edit**, change one sentence, **Save**. The badge goes to `draft`.
6. **Approve.**
   - [ ] The badge shows `approved`.

## Test B: the upload flow

1. Set **Lecture ID** to a new id, e.g. `while_upload_test`.
2. Drag the three non-persona files from `sample_material/while_loops/` onto the upload bar.
   - [ ] All three appear in the file list. **Remove** works.
   - [ ] Uploading an unsupported file (e.g. a `.png`) shows "Skipped".
3. Fill the persona form by hand, or copy the values from `sample_material/while_loops/persona.md`.
4. Generate and approve as in Test A, steps 3 to 6.

---

## Test C: run the class

Use `while_loops` (or your Test B id), open **Classroom**, and click **Start class**.

- [ ] **Status line:** shows the topic, the estimated minutes, and "Gnani voice" or "browser voice".
- [ ] **Left:** the orb pulses while speaking; the caption shows the current sentence; the section title updates.
- [ ] **Right, Notebook tab:** keywords and worked examples are hand-written onto a ruled page;
      `NOTE_HIGHLIGHT` draws a yellow highlighter stroke over the quoted words.
- [ ] **Switching:** the Notebook / Slides / Code indicator moves on its own as the script goes. It cannot be clicked.
- [ ] **Doubt answers on screen:** for a "how" question, the answer writes notes and/or code (e.g. `answer1.py`) before moving on.
      A new notebook page shows as a page tab; after the break the stage returns to the Lecture page.
- [ ] **Right, editor:** code is typed character by character into a file tab; the highlighted lines turn yellow and match what is being said.
- [ ] **Right, Board tab:** a `[SLIDE n]` marker shows that slide's text.
- [ ] **Terminal:** each `$ python <file>.py` shows real output. A countdown should print `5 4 3 2 1` (one per line).
- [ ] **READ_OUTPUT:** the terminal border flashes. If the live output differs from the approved one, an orange `[class]` line appears and the teacher says a short recovery line.
- [ ] **Pause / Resume** pauses and resumes the voice; **Stop** ends after the current step.

### Doubt checks: try one of each

| Type this | Expected behaviour |
|---|---|
| `Why does my while loop never stop?` | Answer about the missing update line / infinite loop, with a citation like `[while_loops.pptx slide 5]` |
| `What does break do?` | Explains break, cites slide 6 or the lab |
| `What is while-else?` (in **Avoid**) | Says it will be covered in a later class |
| `I didn't get why the loop stops. Show me where.` | Scrolls the notebook back to the condition line (`LOOK_BACK`), may open `count.py` again and highlight the `while` line |
| `How would I count down from 5 to 1?` (not in the material) | Answers itself on a new notebook page, writes `answer1.py` and runs it (5 4 3 2 1) |
| `Will this be in the exam?` | Says exactly: "I'll pass this question to Prof. Sharma." |
| `Who won yesterday's match?` (off topic) | Steers back to the lesson politely |
| **No doubts** button | The class moves on |

- [ ] After a doubt check, the conversation stays visible, marked "Done".
- [ ] At the end: "Class complete." and the badge shows `completed`.
- [ ] `workspace/lectures/while_loops/doubts_log.md` lists each question, its answer and `passed_to_teacher`.

---

## Test D: command line (optional, no website)

```bash
python script_parser.py tests/sample_script.md        # OK, 23 segments
python script_parser.py tests/bad_script.md           # 25 errors
python script_parser.py tests/notebook_script.md      # OK: hand-written script that uses the notebook
python main.py status  --lecture while_loops           # status + estimated_min
python main.py session --lecture while_loops --force   # text-mode class in the terminal
python main.py render  --lecture while_loops           # needs GNANI_API_KEY: real audio length
```

## What to report back

For anything that fails, note: the step number, what you saw, and the last 20 lines of the
terminal running `python main.py serve`. Also attach `workspace/lectures/<id>/script.md` if the
script content was the problem.
