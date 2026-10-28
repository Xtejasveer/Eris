"""Step 2 of `generate`: the lesson. What the teacher says and what goes on the board, with no markers.

The lesson writer only teaches: the explanation, the notes, the programs and which figure to explain where, in a
plain format (prompts.lesson_prompt). It stops at every OUTPUT so a real terminal runs the program first, and the
writer describes what it really printed. Then:

1. code checks what can be checked exactly (sections, length, notes, programs, figures),
2. Jev checks the teaching (must cover, avoid, explanation, notes vs code, outputs, pictures, the teacher's style),
3. any problem or Jev blocker goes back to the same writer, which returns the whole lesson fixed (CONTENT_ROUNDS).

Only a lesson that passes goes to step 3 (staging.py), which adds the markers without touching the teaching.
"""

import re

from langchain_core.messages import AIMessage, HumanMessage

from eris import config
from eris.generate.script_agent import ScriptWriter
from eris.tools import program_output, run_code_file

STOP = "\nOUTPUT"
MAX_RUNS = 12
OUTPUT_SHOWN_CHARS = 1500
COMMAND_RE = re.compile(r"^(NOTE:|CODE\s+\S+|OUTPUT|FIGURE\s+.+|END)\s*$")
LESSON_TASK = """Write the whole lesson now, in this one message (about {budget} spoken words, as the length plan
says), from "# Opening" to "# Closing".

# Research notes
{notes}"""
CONTINUE = """The terminal really printed this for {file}:
```
{output}
```
It is pasted under your OUTPUT line. Continue the lesson exactly where you stopped, starting with the line after
that output's END: describe what it printed (never type the output itself), then go on. Do not repeat anything."""
REVISE_SECTIONS = """These sections of your lesson have problems: {titles}.
Return ONLY those sections, each starting with its heading line exactly as it is now ("# <title>"), rewritten with
the problems fixed and everything that is fine kept. Keep each section to its own part of the lesson: don't move in
content that another section teaches, and don't add sections. The other sections stay exactly as they are.
{problems}"""
REVISE = """Your lesson has these problems. Return the WHOLE lesson again, in the same format, with every one fixed
and everything else kept:
{problems}"""


# ---------- the writer (stops at every OUTPUT for the real output) ----------

def _last_program(text):
    """(file, code) of the last CODE block in the text, or (None, None)."""
    blocks = re.findall(r"^CODE\s+(\S+)\s*\n(.*?)\n^END\s*$", text, re.S | re.M)
    return blocks[-1] if blocks else (None, None)


class LessonWriter(ScriptWriter):
    """Writes the lesson; every program runs in a real terminal before the writer says what it printed."""

    def _write(self, talk):
        text = ""
        for _ in range(MAX_RUNS + 1):
            reply = self._invoke(talk, stop=[STOP])
            part = reply.content if isinstance(reply.content, str) else "".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in reply.content)
            text = (text.rstrip("\n") + "\n" + part.lstrip("\n")) if text else part.strip()
            if not _waiting(text):  # finished (or cut short: the checks will say so)
                break
            file, code = _last_program(text)
            exit_code, stdout, stderr = run_code_file(code, filename=file)
            output = (program_output(exit_code, stdout, stderr).rstrip() or "(no output)")[:OUTPUT_SHOWN_CHARS]
            print(f"[generate] ran {file} for the writer: {'ok' if exit_code == 0 else f'exit {exit_code}'}")
            text = text.rstrip("\n") + f"\nOUTPUT\n{output}\nEND"
            talk = talk + [AIMessage(text), HumanMessage(CONTINUE.format(file=file, output=output))]
        return _strip_fences(text)

    def write(self, notes, budget, avoid=""):
        task = LESSON_TASK.format(budget=budget, notes=notes)
        if avoid:
            task += "\n\n# An earlier version had these problems. Avoid all of them:\n" + avoid
        text = self._write(self.messages + [HumanMessage(task)])
        self.messages += [HumanMessage(task), AIMessage(text)]
        return text

    def revise_sections(self, problems, titles, current):
        """Only the sections with problems are rewritten; the rest of the lesson is kept exactly. The writer's
        conversation then holds the whole lesson as it now stands. Returns the spliced lesson."""
        message = REVISE_SECTIONS.format(titles=", ".join(f'"{t}"' for t in titles), problems=problems)
        part = self._write(self.messages + [HumanMessage(message)])
        text = splice_sections(current, part, titles)
        self.messages += [HumanMessage(message), AIMessage(text)]
        return text

    def revise(self, problems):
        """The same writer returns the whole lesson with these problems fixed (it keeps the conversation)."""
        message = REVISE.format(problems=problems)
        text = self._write(self.messages + [HumanMessage(message)])
        self.messages += [HumanMessage(message), AIMessage(text)]
        return text


def _waiting(text):
    """True when the writer stopped at an OUTPUT line: its last program has no output yet and the lesson isn't done."""
    if re.search(r"^# Closing", text, re.M):
        return False
    last_code = max((m.start() for m in re.finditer(r"^CODE\s+\S+\s*$", text, re.M)), default=-1)
    last_output = max((m.start() for m in re.finditer(r"^OUTPUT\s*$", text, re.M)), default=-1)
    return last_code > last_output and _last_program(text)[0] is not None


def _strip_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text[: text.rfind("```")] if "```" in text else text
    return text.strip()


# ---------- fixing only what is broken: sections in, sections out ----------

def _split_sections(text):
    """[(title or None, block text)] in order; the block starts with its "# Title" line."""
    blocks, title, cur = [], None, []
    for line in text.splitlines():
        if line.startswith("# "):
            if cur:
                blocks.append((title, "\n".join(cur)))
            title, cur = line[2:].strip(), [line]
        else:
            cur.append(line)
    if cur:
        blocks.append((title, "\n".join(cur)))
    return blocks


def splice_sections(current, part, wanted=None):
    """Put the rewritten sections of `part` into `current`: each replaces the section with its title. wanted: the
    sections that were asked for; a returned section with another title takes the place of a wanted one that came
    back renamed, and anything else returned (an extra section) is left out, so a fix can't duplicate teaching.
    Sections not asked for stay exactly as they were."""
    blocks = _split_sections(current)
    returned = [(t, b) for t, b in _split_sections(part) if t is not None]
    wanted = [w.lower() for w in (wanted or [t for t, _ in returned])]
    missing = [w for w in wanted if w not in {t.lower() for t, _ in returned}]
    for title, block in returned:
        key = title.lower()
        if key not in wanted:
            if not missing:
                continue  # an extra section nobody asked for
            key = missing.pop(0)  # the wanted section, returned under a new title: keep its heading
            block = "# " + next(t for t, _ in blocks if t and t.lower() == key) + "\n" + block.split("\n", 1)[-1]
        at = next((k for k, (t, _) in enumerate(blocks) if t and t.lower() == key), None)
        if at is not None:
            blocks[at] = (blocks[at][0], block)
    return "\n\n".join(b.strip("\n") for _, b in blocks)


SECTION_PROBLEM_RE = re.compile(r'^section "([^"]+)"')


def problem_sections(problems, findings, titles):
    """The sections the feedback is about, or None when any of it concerns the whole lesson."""
    wanted = []
    for p in problems:
        m = SECTION_PROBLEM_RE.match(p)
        if not m:
            return None
        wanted.append(m.group(1))
    for f in findings:
        if not f.get("section"):
            return None
        wanted.append(f["section"])
    known = {t.lower(): t for t in titles}
    if not wanted or any(w.lower() not in known for w in wanted):
        return None
    return list(dict.fromkeys(known[w.lower()] for w in wanted))


# ---------- reading a lesson ----------

def parse_lesson(text):
    """[{title, items}] where items are {"kind": "say" | "note" | "code" | "output" | "figure", ...}, and the
    format problems found while reading."""
    sections, problems, cur = [], [], None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip()
        line = raw.strip()
        i += 1
        if not line:
            continue
        if line.startswith("# "):
            cur = {"title": line[2:].strip(), "items": []}
            sections.append(cur)
            continue
        if cur is None:
            cur = {"title": "Opening", "items": []}
            sections.append(cur)
        block = None
        if line.startswith("NOTE:"):
            block = {"kind": "note", "title": line[5:].strip()}
        elif re.match(r"^CODE\s+\S+$", line):
            block = {"kind": "code", "file": line.split(None, 1)[1]}
        elif line == "OUTPUT":
            block = {"kind": "output"}
        if block:
            body = []
            while i < len(lines) and lines[i].strip() != "END":
                body.append(lines[i] if block["kind"] == "code" else lines[i].strip())
                i += 1
            if i >= len(lines):
                problems.append(f'section "{cur["title"]}": a {block["kind"].upper()} block has no END line')
            i += 1  # the END
            if block["kind"] == "note":
                block["lines"] = [b for b in body if b]
            elif block["kind"] == "code":
                block["code"] = "\n".join(body).strip("\n")
            else:
                block["text"] = "\n".join(body)
            cur["items"].append(block)
            continue
        if line.startswith("FIGURE "):
            cur["items"].append({"kind": "figure", "ref": line[7:].strip()})
            continue
        if line == "END":
            continue
        if "[" in line and "]" in line and re.search(r"\[[A-Z_]+[ \]]", line):
            problems.append(f'section "{cur["title"]}": a spoken line has a marker in it ("{line[:60]}"); write only '
                            "plain sentences, the markers are added later")
        cur["items"].append({"kind": "say", "text": re.sub(r"\*\*|__|`", "", line).lstrip("-* ").strip()})
    return sections, problems


def narration(sections):
    return [it["text"] for s in sections for it in s["items"] if it["kind"] == "say"]


def word_count(sections):
    return sum(len(t.split()) for t in narration(sections))


# ---------- length: speaking time x voice speed = words, shared out over the sections ----------

MIN_SECTION_WORDS = 120  # a concept with its question, notes, a worked example and a takeaway needs about this much
LENGTH_SLACK = 0.15      # a lesson more than this far from its word budget goes back to the writer


def length_plan(budget, order=""):
    """How the word budget is shared: the opening, recap and closing get small fixed shares; the rest is split over
    as many concept sections as fit (at least MIN_SECTION_WORDS each). If "Order" lists more parts than fit, the
    writer merges them. Returns (plan text for the prompt, number of concept sections)."""
    items = [x.strip() for x in re.split(r"[,;\n]", order or "") if x.strip()]
    opening, recap, closing = round(0.08 * budget), round(0.07 * budget), round(0.05 * budget)
    rest = budget - opening - recap - closing
    fits = max(1, rest // MIN_SECTION_WORDS)
    count = min(len(items), fits) if items else fits
    merge = (f' "Order" has {len(items)} parts but only {count} fit: merge them into {count} sections, keeping every '
             '"Must cover" item.') if len(items) > count else ""
    plan = (f"Opening about {opening} words; {count} concept section(s) of about {rest // count} words each; Recap about "
            f"{recap}; Closing about {closing}. Total about {budget} words (a guide: covering every Must cover item well matters more)."
            + merge)
    return plan, count


def length_problem(sections, budget):
    """The lesson must fit its speaking time: within LENGTH_SLACK of the word budget."""
    words = word_count(sections)
    low, high = round(budget * (1 - LENGTH_SLACK)), round(budget * (1 + LENGTH_SLACK))
    if low <= words <= high:
        return None
    per = ", ".join(f'{s["title"]} {sum(len(it["text"].split()) for it in s["items"] if it["kind"] == "say")}'
                    for s in sections)
    if words > high:
        return (f"the lesson has {words} spoken words but its speaking time allows about {budget} (at most {high}). "
                f"Cut it to about {budget}: fewer, merged sections, shorter openings and recaps, one worked example per "
                f"concept; keep every \"Must cover\" item. Words per section now: {per}")
    return f"the lesson has only {words} spoken words; its speaking time needs about {budget} (at least {low}). Words per section now: {per}"


# ---------- a calculation said aloud is written in the notebook as it is said ----------

CALC_WORDS_RE = re.compile(r"\b(plus|minus|times|multipl\w*|divid\w*|over|equals?|percent of|squared|sum of|average of)\b"
                           r"|[+×÷=]|\d\s*[-*/x]\s*\d", re.I)
CALC_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _calc_numbers(text):
    return {n.replace(",", "") for n in CALC_NUM_RE.findall(text)}


SOFT_PROBLEM_RE = re.compile(r"works through calculations that are not written|explain each of its \d+ steps"
                             r"|is (?:brief|normal|in depth) in the plan"
                             r"|writes calculation steps it never explains|writes calculation steps back to back"
                             r"|already teaches \(the same notes")


def _results(note_lines):
    """The results of a note's calculation lines: the numbers after the last "=" of each line ("-1065", "48.6")."""
    out = set()
    for line in note_lines:
        if "=" in line:
            out |= _calc_numbers(line.rsplit("=", 1)[1])
    return out


def write_steps_first(text):
    """Write first, then explain: a one-line calculation note (NOTE: with no title) placed right AFTER the sentence
    that says its numbers is moved in front of that sentence. Returns (text, notes moved)."""
    lines, out, moved, i = text.splitlines(), [], 0, 0
    while i < len(lines):
        if lines[i].strip() == "NOTE:":
            end = next((k for k in range(i + 1, len(lines)) if lines[k].strip() == "END"), None)
            prev = len(out) - 1
            while prev >= 0 and not out[prev].strip():
                prev -= 1
            said = out[prev].strip() if prev >= 0 else ""
            is_speech = said and not COMMAND_RE.match(said) and not said.startswith("# ") and not said.startswith("- ")
            if end is not None and is_speech:
                result = _results(lines[i + 1:end])  # the step's result: what its sentence must say
                sentences = [x for x in re.split(r"(?<=[.!?।॥])\s+", said) if x]
                k = next((k for k in range(len(sentences) - 1, -1, -1) if _calc_numbers(sentences[k]) & result), None) \
                    if result else None
                if k is not None:
                    before, after = " ".join(sentences[:k]), " ".join(sentences[k:])
                    out[prev:prev + 1] = ([before] if before else []) + lines[i:end + 1] + [after]
                    moved += 1
                    i = end + 1
                    continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), moved


REPEAT_SHARE = 0.6  # a section whose notes are mostly already written in an earlier section repeats it


def _note_lines(section):
    return [" ".join(ln.lstrip("-* ").lower().split()) for it in section["items"] if it["kind"] == "note"
            for ln in it["lines"] if ln.strip()]


def repeated_sections(sections):
    """[(later title, earlier title, repeated lines)] for each section that mostly re-teaches an earlier one."""
    out = []
    for k, s in enumerate(sections):
        mine = _note_lines(s)
        if len(mine) < 2 or FRAMING_RE.search(s["title"]):
            continue
        for earlier in sections[:k]:
            theirs = set(_note_lines(earlier))
            same = [ln for ln in mine if ln in theirs]
            if len(same) >= max(2, REPEAT_SHARE * len(mine)):
                out.append((s["title"], earlier["title"], same))
                break
    return out


def repeat_problems(sections):
    return [f'section "{later}" repeats what section "{earlier}" already teaches (the same notes: '
            + "; ".join(f'"{x}"' for x in same[:3]) + "). Teach each idea once: keep it in one section and remove the repeat"
            for later, earlier, same in repeated_sections(sections)]


def drop_repeated_sections(text):
    """Last resort: a section that still mostly repeats an earlier one is removed. Returns (text, removed titles)."""
    sections, _ = parse_lesson(text)
    repeats = {later.lower() for later, _, _ in repeated_sections(sections)}
    if not repeats:
        return text, []
    blocks = _split_sections(text)
    kept = [(t, b) for t, b in blocks if not (t and t.lower() in repeats)]
    return "\n\n".join(b.strip("\n") for _, b in kept), [t for t, _ in blocks if t and t.lower() in repeats]


def unexplained_steps_said(sections):
    """Write first, then explain: every calculation step written as a one-line note (no title) must have its result
    said after it in the same section ("so the range is 38"), before the next step is written. Returns one problem per
    section for each rule broken."""
    problems = []
    for s in sections:
        items, missing, stacked = s["items"], [], []
        for k, it in enumerate(items):
            if it["kind"] != "note" or it.get("title"):
                continue
            nxt = items[k + 1] if k + 1 < len(items) else None
            if nxt and nxt["kind"] == "note" and not nxt.get("title"):
                stacked.append(" | ".join(it["lines"])[:60])
            result = _results(it["lines"])
            later = " ".join(x["text"] for x in items[k + 1:] if x["kind"] == "say")
            if result and not (result & _calc_numbers(later)):
                missing.append(" | ".join(it["lines"])[:60])
        if missing:
            problems.append(f'section "{s["title"]}" writes calculation steps it never explains: '
                            + "; ".join(f'"{m}"' for m in missing[:4])
                            + ". After writing each step, say what it does and its result (\"so the range is 38\")")
        if stacked:
            problems.append(f'section "{s["title"]}" writes calculation steps back to back: '
                            + "; ".join(f'"{m}"' for m in stacked[:4])
                            + ". Say each step once, right after its note and before the next note is written; "
                              "never announce a step twice")
    return problems


def unwritten_calculations(sections):
    """A sentence that works through a calculation (numbers with plus, minus, times, divided, equals...) must have
    its working in a note placed before it in the same section, so the class sees it written as it is said.
    Returns one problem per section, naming the sentences."""
    problems = []
    for s in sections:
        if FRAMING_RE.search(s["title"]):
            continue
        noted, missing = set(), []
        for it in s["items"]:
            if it["kind"] == "note":
                noted |= _calc_numbers(" ".join(it["lines"]))
            elif it["kind"] in ("code", "output"):
                noted |= _calc_numbers(it.get("code", "") + " " + it.get("text", ""))
            elif it["kind"] == "say":
                for sentence in re.split(r"(?<=[.!?।॥])\s+", it["text"]):
                    nums = _calc_numbers(sentence)
                    if len(nums) >= 2 and CALC_WORDS_RE.search(sentence) and not nums <= noted:
                        missing.append(sentence.strip())
        if missing:
            problems.append(f'section "{s["title"]}" works through calculations that are not written in the notebook: '
                            + "; ".join(f'"{m[:90]}"' for m in missing[:4])
                            + '. Put each step\'s working in a one-line note with no title ("NOTE:", "- 400 - 1465 = -1065", '
                              "END) right before the sentence that says it")
    return problems


# ---------- a drawn figure: each of its steps gets its own sentence, after FIGURE ----------

def _step_words(text):
    from eris.generate.script_fixes import _words
    return _words(text)


def unexplained_steps(sections, figs):
    """For each "draw" figure, the sentences after its FIGURE line (until the next figure or program) must explain
    its steps in order, one sentence each: each block is drawn while its sentence is said. Returns problems."""
    from eris.material.figures import use_of
    problems = []
    for s in sections:
        items = s["items"]
        for k, it in enumerate(items):
            fig = it.get("fig") if it["kind"] == "figure" else None
            if not fig or use_of(fig) != "draw" or "steps:" not in fig.get("details", ""):
                continue
            steps = [x.strip() for x in fig["details"].split("steps:", 1)[1].split("->") if x.strip()]
            sentences = []
            for later in items[k + 1:]:
                if later["kind"] in ("figure", "code"):
                    break
                if later["kind"] == "say":
                    sentences += [x for x in re.split(r"(?<=[.!?।॥])\s+", later["text"]) if x.strip()]
            found, j = 0, 0
            for step in steps:
                words = _step_words(step)
                while j < len(sentences) and not (words & _step_words(sentences[j])):
                    j += 1
                if j == len(sentences):
                    break
                found, j = found + 1, j + 1
            if found < len(steps):
                problems.append(f'section "{s["title"]}": after FIGURE {it["ref"]}, explain each of its {len(steps)} steps '
                                f"in its own sentence, in this order (each block is drawn as its sentence is said): "
                                + "; ".join(steps))
    return problems


# ---------- code checks ----------

FRAMING_RE = re.compile(r"\b(opening|introduction|recap|summary|review|closing|conclusion|wrap)", re.I)


def lesson_problems(sections, budget, figs, env, slide_count, extra=()):
    """What code can check exactly. Returns a list of problems for the writer."""
    from eris.material.figures import use_of
    problems = list(extra)
    titles = [s["title"] for s in sections]
    if not titles or not titles[0].lower().startswith("opening"):
        problems.append('the lesson must start with "# Opening"')
    if not any(t.lower().startswith("closing") for t in titles[-2:]):
        problems.append('the lesson must end with "# Recap" and "# Closing"')
    if len([t for t in titles if not FRAMING_RE.search(t)]) < 1:
        problems.append("the lesson needs at least one concept section between the Opening and the Recap")
    # Length and "every number in the notes" are guidance in the prompt, not problems: they pull against teaching
    # every "Must cover" item well, so they cost rounds without making the lesson better (write_lesson warns).
    refs = {f["ref"].lower(): f for f in figs or []}
    last_code = {}
    for s in sections:
        for it in s["items"]:
            if it["kind"] == "note":
                n = len(it["lines"])
                if n < 1 or n > config.NOTE_MAX_LINES:
                    problems.append(f'section "{s["title"]}": the note "{it["title"]}" has {n} lines; keep notes to '
                                    f"2-{config.NOTE_MAX_LINES} short lines")
            elif it["kind"] == "code":
                if not env.get("code"):
                    problems.append(f'section "{s["title"]}": this class has no code in its material, so no programs '
                                    f'(remove CODE {it["file"]})')
                last_code[it["file"]] = it
            elif it["kind"] == "output":
                if "Traceback (most recent call last)" in it["text"] or re.search(r"^\w*Error\b", it["text"], re.M):
                    problems.append(f'section "{s["title"]}": the program fails when it runs:\n{it["text"][-300:]}\n'
                                    "fix the program so it runs")
            elif it["kind"] == "figure":
                ref = it["ref"].lower().strip('"')
                m = re.match(r"slide\s+(\d+)$", ref)
                known = refs.get(ref) or next((f for r, f in refs.items() if r.endswith(ref) or ref.endswith(r)), None)
                if not known and not (m and slide_count and 1 <= int(m.group(1)) <= slide_count):
                    choices = "; ".join(f'"{f["ref"]}"' for f in (figs or [])[:12])
                    problems.append(f'section "{s["title"]}": FIGURE {it["ref"]} is not in the material; use one of: '
                                    f"{choices}")
                elif known:
                    it["use"], it["fig"] = use_of(known), known
    return (problems + unexplained_steps(sections, figs) + unwritten_calculations(sections)
            + unexplained_steps_said(sections) + repeat_problems(sections))


# ---------- Jev on the teaching ----------

def _pictures_on(ref, pictures):
    m = re.match(r"slide\s+(\d+)$", ref.lower().strip())
    if m:
        return [p for p in pictures or [] if p.get("slide") == int(m.group(1)) and p.get("description")]
    return [p for p in pictures or [] if p.get("description") and (p.get("ref", "").lower().endswith(ref.lower())
                                                                     or ref.lower().endswith(p.get("ref", "").lower()))]


def content_states(sections, pictures=None):
    """One Jev state per section of the lesson (the same keys script_judge.section_states uses)."""
    states, seen = [], set()
    for k, s in enumerate(sections):
        st = {"section": s["title"], "narration": [], "notebook": [], "code": [], "real_outputs": [], "graphs": {},
              "flows": {}, "pictures_shown": {}, "spoken_while_writing": {},
              "concept": 0 < k < len(sections) - 1 and not FRAMING_RE.search(s["title"])}
        file = None
        for it in s["items"]:
            if it["kind"] == "say":
                st["narration"].append(it["text"])
            elif it["kind"] == "note":
                st["notebook"].append(it["title"] + "\n" + "\n".join(it["lines"]))
            elif it["kind"] == "code":
                file = it["file"]
                st["code"].append(f'{it["file"]}:\n{it["code"]}')
            elif it["kind"] == "output":
                st["real_outputs"].append(f"$ python {file}\n{it['text']}")
            elif it["kind"] == "figure" and it["ref"].lower() not in seen and not FRAMING_RE.search(s["title"]):
                seen.add(it["ref"].lower())
                pics = _pictures_on(it["ref"], pictures)
                if pics:
                    st["pictures_shown"][it["ref"]] = " | ".join(
                        f"{p.get('kind', 'picture')}: {p['description']}" + (f" Text in it: {p['text'][:200]}" if p.get("text") else "")
                        for p in pics)
        states.append(st)
    return states


def content_script_state(sections, persona, topic):
    from eris.generate.script_judge import MIDDLE_CHARS
    get = lambda sec, key: persona.get(sec, {}).get(key, "")  # noqa: E731
    say = lambda s: " ".join(it["text"] for it in s["items"] if it["kind"] == "say")  # noqa: E731
    inner = sections[1:-1]
    share = MIDDLE_CHARS // max(1, len(inner))
    return {"topic": topic, "class": get("Teacher", "Class"), "must_cover": get("Lecture Structure", "Must cover"),
            "avoid": get("Lecture Structure", "Avoid"), "absence_reason": get("Absence Note", "Reason"),
            "message_to_class": get("Absence Note", "Message to class"),
            "teaching_style": {k: get("Teaching Style", k) for k in ("Tone", "Pace", "Language", "Habits")},
            "next_class_topic": get("Next Class", "Topic"), "next_class_prep": get("Next Class", "Prep"),
            "section_titles": [s["title"] for s in sections],
            "opening": say(sections[0]) if sections else "", "closing": say(sections[-1]) if len(sections) > 1 else "",
            "narration": {s["title"]: say(s)[:share] for s in inner}}


MATERIAL_CHARS = 12000  # what Jev sees of the teacher's material with each section (its context is 32k tokens)


def material_text(lecture_id):
    """The teacher's material as plain text (slides, documents, notes, what each picture shows), for checking that
    the lesson stays true to it."""
    import contextlib
    import io
    from eris import config
    from eris.material.images import load as load_pictures
    from eris.material.indexer import load_folder
    with contextlib.redirect_stdout(io.StringIO()):  # load_folder reports each file; not needed here
        docs, _ = load_folder(config.data_dir(lecture_id))
    parts = [d.page_content for d in docs if d.metadata.get("source") != "persona.md"]
    parts += [f"Picture on {p['where']}: {p['description']}" for p in load_pictures(lecture_id) if p.get("description")]
    from eris.material import figures
    parts += [f"Chart or diagram on {f['ref']} ({f['title']}): {f['details']}" for f in figures.load(lecture_id)
              if f["kind"] in ("graph", "diagram", "flow")]  # chart data isn't slide text
    return "\n\n".join(parts)[:MATERIAL_CHARS]


def judge_content(sections, persona, topic, pictures=None, material=""):
    """Jev on the teaching only. material: the teacher's material as text (material_text), for "stays true".
    Returns the report (script_judge.run_jobs)."""
    from eris.generate.script_judge import CONTENT_CHECKS, SCRIPT_QUESTIONS, _section_questions, attach_evidence, run_jobs
    script_state, states = content_script_state(sections, persona, topic), content_states(sections, pictures)
    if material:
        for st in states:
            st["material"] = material
    jobs = [(None, dict(script_state), SCRIPT_QUESTIONS)]
    jobs += [(st["section"], dict(st), _section_questions(st, CONTENT_CHECKS)) for st in states]
    report = attach_evidence(run_jobs(jobs), {st["section"]: st for st in states}, script_state)
    for f in report["findings"]:
        f["stage"] = "lesson"
    return report


def jev_feedback(report):
    failed = sorted((f for f in report["findings"] if not f["passed"]), key=lambda f: (f["severity"] != "blocker", f["value"]))
    return "\n".join(f"- [{f['severity']}] {f['fix']} (the reviewer was {round((1 - f['value']) * 100)}% sure this is wrong)"
                     + (f"\n    {f['evidence']}" if f.get("evidence") else "") for f in failed)


# ---------- step 2 ----------

def write_lesson(prompt, notes, budget, persona, topic, figs, env, slide_count, pictures, rounds, material="", plan=None):
    """Write the lesson and loop until code and Jev pass it (CONTENT_ROUNDS revisions). Returns (lesson text,
    sections, Jev report, problems left). rounds: the pipeline's list of rounds, for Studio. plan: the depth plan
    (depth.py); a section far from its planned length goes back to the writer."""
    from eris.generate.depth import section_problems
    writer = LessonWriter(prompt)
    text = writer.write(notes, budget)
    best = None
    for n in range(config.CONTENT_ROUNDS + 1):
        text, moved = write_steps_first(text)  # code puts calculation notes in front of their sentence
        if moved:
            print(f"[lesson] moved {moved} calculation note(s) in front of the sentence that explains them")
        sections, problems = parse_lesson(text)
        problems = lesson_problems(sections, budget, figs, env, slide_count, problems)
        if plan:
            problems += section_problems(sections, plan)
        words = word_count(sections)
        report = None
        if problems:
            print(f"[lesson] {len(problems)} problem(s) in the lesson ({words} words)")
            for p in problems:
                print(f"[lesson]   {p.splitlines()[0]}")
        # Jev every round, also when code found problems: one round then fixes both (Jev is a few seconds)
        if config.JUDGE_ENABLED:
            print(f"[lesson] checking the teaching with {config.JUDGE_MODEL} ({words} words) ...")
            report = judge_content(sections, persona, topic, pictures, material)
            if not report["error"]:
                print(f"[lesson] score {report['score']:.2f}, {report['blockers']} blocker(s), "
                      f"{report['failed_minor']} minor issue(s)")
                for f in report["findings"]:
                    if not f["passed"]:
                        print(f"[lesson]   {f['severity']}: {f['check']}{' [' + f['section'] + ']' if f['section'] else ''} = {f['value']}")
        key = (len(problems), report["blockers"] if report and not report["error"] else 0,
               -(report["score"] if report and not report["error"] else 0))
        if best is None or key < best[0]:
            best = (key, text, sections, report, problems)
        passed = not problems and (report is None or report["error"] or not report["blockers"])
        if passed or n == config.CONTENT_ROUNDS:
            break
        blocking = [f for f in report["findings"] if f["severity"] == "blocker" and not f["passed"]] \
            if report and not report["error"] else []
        teaching = jev_feedback({"findings": blocking})
        feedback = "\n".join(f"- {p}" for p in problems) + ("\n" if problems and teaching else "") + teaching
        rounds.append({"kind": "lesson", "problems": feedback.count("\n- ") + 1})
        only = problem_sections(problems, blocking, [s["title"] for s in sections])
        if only:  # fix just those sections; the rest of the lesson is not rewritten (and can't break)
            print(f"[lesson] {len(only)} section(s) go back to the writer (round {n + 1}/{config.CONTENT_ROUNDS}): {', '.join(only)}")
            text = writer.revise_sections(feedback, only, text)
        else:
            print(f"[lesson] the lesson goes back to the writer (round {n + 1}/{config.CONTENT_ROUNDS})")
            text = writer.revise(feedback)
    _, text, sections, report, problems = best
    if (off := length_problem(sections, budget)):  # reported, never sent back
        print(f"[lesson] note: {off.split('. ')[0]}")
    # How the teaching is laid out (calculation notes, one sentence per diagram step) is worth rounds, never worth
    # failing the whole generation: what is left is reported and the lesson goes on to staging.
    if any("already teaches (the same notes" in p for p in problems):
        text, dropped = drop_repeated_sections(text)  # a repeat the writer left: removed rather than taught twice
        if dropped:
            print(f"[lesson] removed section(s) that repeated earlier teaching: {', '.join(dropped)}")
            sections, _ = parse_lesson(text)
    soft = [p for p in problems if SOFT_PROBLEM_RE.search(p)]
    for p in soft:
        print(f"[lesson] note (kept): {p.split('. Put')[0][:200]}")
    problems = [p for p in problems if p not in soft]
    if not problems and not (report and not report["error"] and report["blockers"]):
        print("[lesson] the lesson passed; it goes to staging")
    return text, sections, report, problems
