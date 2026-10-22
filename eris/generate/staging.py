"""Step 3 of `generate`: staging. The finished lesson (lesson.py) becomes the class script.

The stager adds the markers that drive the class screen (sections, notes, code, slides, highlights, diagrams,
graphs, question breaks) around the lesson's spoken lines, which it must keep as they are. Then:

1. code checks the script (the parser and every format check) and that no spoken line of the lesson was changed or
   left out; problems go back to the same stager, then the usual last-resort repairs (script_pipeline.py),
2. code adds what it always adds (the slide for a picture, "Let me write..." leads, while-speaking flags),
3. Jev checks only the staging (highlights, diagrams, graphs, what is said while writing); blockers go back to the
   stager, never to the lesson writer (STAGE_ROUNDS). The best staging seen is kept.
"""

import re

from langchain_core.messages import AIMessage, HumanMessage

from eris import config
from eris.generate.lesson import narration
from eris.generate.script_agent import ScriptWriter
from eris.generate.script_judge import better, judge_staging
from eris.generate.script_parser import parse_script
from eris.generate.script_pipeline import ScriptPipeline

STAGE_TASK = """Stage this lesson now: return the whole class script, from [SECTION title="Opening"] to the final
[DOUBT_CHECK].

{context}"""
SLIDE_ADVICE = ("move each [SLIDE] (and its [SLIDE_HIGHLIGHT]) right before the lesson sentence that talks about "
                "that slide, with no other marker between them, in: {where}")
AVOID = "\n\n# An earlier staging had these problems. Avoid all of them:\n"
DRIFT_TOLERANCE = 0.03  # share of the lesson's sentences the stager may lose before it is a problem


class Stager(ScriptWriter):
    """One plain call (no stops: the programs already ran in step 2). Keeps the conversation for fix rounds."""

    def write(self, context, budget, avoid=""):
        task = STAGE_TASK.format(context=context)
        if avoid:
            task += AVOID + avoid
        reply = self._invoke(self.messages + [HumanMessage(task)])
        text = reply.content if isinstance(reply.content, str) else "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in reply.content)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
            text = text[: text.rfind("```")] if "```" in text else text
        self.messages += [HumanMessage(task), AIMessage(text)]
        return text.strip()


def staging_context(lesson_text, slides, figs, env):
    """Everything the stager needs besides the lesson: the slides' exact lines, the figures and how to use each."""
    from eris.material.figures import describe, describe_environments
    clean = lambda t: "\n".join(re.sub(r"^\s*[•\-*]\s*", "", ln) for ln in t.splitlines())  # noqa: E731  as shown in class
    slide_text = "\n\n".join(f"Slide {n}:\n{clean(text)}" for n, text in sorted(slides.items())) or "none"
    used = [f for f in figs or [] if f["kind"] != "picture"]
    return (f"# Lesson\n{lesson_text}\n\n# Slides (quote SLIDE_HIGHLIGHT lines exactly from these)\n{slide_text}\n\n"
            f"# Figures in the material, with how to use each\n{describe(used) if used else 'none'}\n\n"
            f"# Environments for this class\n{describe_environments(env)}")


def _norm(sentence):
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", sentence.lower()).split())


def _sentences(texts):
    out = []
    for t in texts:
        out += [n for s in re.split(r"(?<=[.!?।॥])\s+", t) if (n := _norm(s))]
    return out


def narration_drift(lesson_sentences, segments):
    """Problems when the stager changed or left out the lesson's spoken lines, or added teaching of its own."""
    said = _sentences(s["text"] for s in segments if s["kind"] == "say")
    have, want = set(said), set(lesson_sentences)
    missing = [s for s in dict.fromkeys(lesson_sentences) if s not in have]
    added = [s for s in dict.fromkeys(said) if s not in want and len(s.split()) > 12]
    problems = []
    pieces = [s["text"] for s in segments if s["kind"] == "say" and s["text"].rstrip().endswith((",", ";", ":"))]
    if pieces:
        problems.append("you split sentences across markers (each block or highlight needs a whole sentence after it): "
                        + "; ".join(f'"{p}"' for p in pieces[:3]) + ". Keep every lesson sentence whole")
    if len(missing) > max(1, DRIFT_TOLERANCE * len(want)):
        problems.append(f"you changed or left out {len(missing)} spoken sentence(s) of the lesson; keep every one "
                        "exactly as written, for example: " + "; ".join(f'"{s}"' for s in missing[:4]))
    if added:
        problems.append("you added teaching that is not in the lesson (add only short leads under 10 words): "
                        + "; ".join(f'"{s}"' for s in added[:3]))
    return problems


def late_slider_moves(segments):
    """A slider moved right AFTER the sentence about that value ("Now the dip in 2009." then the move to 2009): the
    class hears it before the graph shows it. Returns problems for the stager."""
    problems = []
    for i, seg in enumerate(segments):
        if seg.get("name") != "VISUAL_SET" or "value" not in seg.get("args", {}):
            continue
        value = str(seg["args"]["value"]).rstrip("0").rstrip(".") if "." in str(seg["args"]["value"]) else str(seg["args"]["value"])
        before = segments[i - 1] if i else {}
        after = next((s for s in segments[i + 1:] if s["kind"] == "say"), {})
        said_before = re.split(r"(?<=[.!?।॥])\s+", before.get("text", "").strip())[-1] if before.get("kind") == "say" else ""
        if re.search(rf"\b{re.escape(value)}\b", said_before) and not re.search(rf"\b{re.escape(value)}\b", after.get("text", "")):
            problems.append(f'[VISUAL_SET id="{seg["args"]["id"]}" control="{seg["args"]["control"]}" value={seg["args"]["value"]}] '
                            f'comes after the sentence about {value} ("{said_before[:70]}"); move it right before that sentence')
    return problems


class StagePipeline(ScriptPipeline):
    """The usual checks and repairs, plus: the lesson's spoken lines stay as they are."""

    def __init__(self, *args, lesson_sentences=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.lesson_sentences = list(lesson_sentences)
        self.drift = []

    def check(self, text):
        text, segments, problems = super().check(text)
        self.drift = narration_drift(self.lesson_sentences, segments)
        # The teaching is fixed by now: advice about what is said or written (longer notes, shorter sentences,
        # "Let me write..." leads, which code adds anyway) is not the stager's job. Only marker advice stays.
        self.advice = [SLIDE_ADVICE.format(where=a.split(" in: ", 1)[-1]) for a in self.advice
                       if a.startswith("after a slide")] + late_slider_moves(segments)  # polish: rides along only
        return text, segments, problems + self.drift  # advice rides along with real problems only

    def real_outputs(self, segments):
        return ""  # the program outputs are the lesson writer's business; the stager doesn't need them

    def ask_fix(self, text, segments, problems):
        listed = "\n".join(f"- {p}" for p in problems + self.advice)
        only = problem_script_sections(text, problems)
        if only:
            current = "\n\n".join(b for t, b in script_sections(text) if t in only)
            print(f"[staging] {len(only)} section(s) go back to the stager: {', '.join(only)}")
            part = self.writer.ask(FIX_SECTIONS.format(titles=", ".join(f'"{t}"' for t in only), current=current,
                                                       problems=listed))
            return splice_script(text, part)
        return self.writer.ask(FIX_ALL.format(current=text, problems=listed))

    def last_resort(self, text):
        text, segments, problems = super().last_resort(text)
        if self.drift:  # code can't restore wording; a reworded line is better than no script
            self.auto_fixes.append("kept the staging although it reworded some of the lesson's sentences")
            problems = [p for p in problems if p not in self.drift]
        return text, segments, problems


def _staging_feedback(report):
    """Only what must be fixed (blockers), each with its evidence. Suggestions and rejected pairs stay out: code
    handles pairs, and polish isn't worth a round."""
    failed = sorted((f for f in report["findings"] if not f["passed"] and f["severity"] == "blocker"), key=lambda f: f["value"])
    return "\n".join(f"- {f['fix']}" + (f"\n    {f['evidence']}" if f.get("evidence") else "") for f in failed)


def stage_lesson(lesson_text, sections, persona_prompt, budget, slides, figs, env, pictures, rounds):
    """Stage the lesson and loop until code and Jev pass the staging. Returns (text, segments, problems, report,
    pipe). problems is non-empty only when no valid script could be made."""
    context = staging_context(lesson_text, slides, figs, env)
    pipe = StagePipeline(Stager(persona_prompt), budget, len(slides), context, figs, env, pictures,
                         lesson_sentences=_sentences(narration(sections)))
    pipe.rounds = rounds
    print("[staging] adding the slides, notes, highlights, diagrams and question breaks ...")
    text, segments, problems = pipe.until_valid(pipe.writer.write(context, budget))
    if problems:
        print(f"[staging] {len(problems)} problem(s) left; a fresh stager tries once more")
        rounds.append({"kind": "restage", "problems": len(problems)})
        text, segments, problems = pipe.until_valid(pipe.rewrite("\n".join(f"- {e}" for e in problems)))
    if problems:
        return text, segments, problems, None, pipe
    text, segments = pipe.finalize(text)
    if not config.JUDGE_ENABLED:
        return text, segments, [], None, pipe
    best = None
    for n in range(config.STAGE_ROUNDS + 1):
        print(f"[staging] checking the staging with {config.JUDGE_MODEL} ...")
        report = judge_staging(segments, figs, pictures)
        for f in report["findings"]:
            f["stage"] = "staging"
        if report["error"]:
            return text, segments, [], report, pipe
        print(f"[staging] score {report['score']:.2f}, {report['blockers']} blocker(s), {report['failed_minor']} minor "
              f"issue(s), {sum(p['unflag'] for p in report['pairs'])}/{len(report['pairs'])} while-speaking pair(s) rejected")
        for f in report["findings"]:
            if not f["passed"]:
                print(f"[staging]   {f['severity']}: {f['check']} [{f['section']}] = {f['value']}")
        if best is None or better(report, best[3]):
            best = (text, segments, list(pipe.auto_fixes), report)
        if not report["blockers"] or n == config.STAGE_ROUNDS:
            break
        rounds.append({"kind": "staging", "problems": report["blockers"]})
        print(f"[staging] the staging goes back to the stager (round {n + 1}/{config.STAGE_ROUNDS})")
        feedback = _staging_feedback(report)
        only = list(dict.fromkeys(f["section"] for f in report["findings"]
                                  if not f["passed"] and f["severity"] == "blocker" and f["section"])) or None
        if only:
            current = "\n\n".join(b for t, b in script_sections(text) if t in only)
            part = pipe.writer.ask(FIX_SECTIONS.format(titles=", ".join(f'"{t}"' for t in only), current=current,
                                                       problems=feedback))
            fixed = splice_script(text, part)
        else:
            fixed = pipe.writer.ask(FIX_ALL.format(current=text, problems=feedback))
        new_text, new_segments, problems = pipe.until_valid(fixed)
        if problems:
            print("[staging] the new staging broke the script; keeping the best so far")
            break
        text, segments = pipe.finalize(new_text)
    text, segments, pipe.auto_fixes, report = best
    return text, segments, [], report, pipe


# ---------- fixing only what is broken, on the script as it really stands ----------

FIX_SECTIONS = """These sections of the script have problems: {titles}. Here they are as they stand now (the class code
may have added slides, pen circles, short leads and while_speaking flags; keep those unless a problem is about them):

{current}

Return ONLY these sections, each starting with its [SECTION title=".."] line exactly as it is now, with every problem
fixed and everything else kept. Keep every spoken line of the lesson exactly. Do not return any other section.

# Problems
{problems}"""
FIX_ALL = """Here is the whole script as it stands now (the class code may have added slides, pen circles, short leads and
while_speaking flags; keep those unless a problem is about them):

{current}

It has these problems. Return the WHOLE script with every one fixed and everything else kept. Keep every spoken line
of the lesson exactly.

# Problems
{problems}"""


def script_sections(text):
    """[(title or None, block)] in order; each block starts with its [SECTION] line."""
    from eris.generate.script_parser import parse_line_marker
    blocks, title, cur = [], None, []
    for line in text.splitlines():
        marker = parse_line_marker(line)
        if marker and marker[0] == "SECTION":
            if cur:
                blocks.append((title, "\n".join(cur)))
            title, cur = marker[1].get("title", ""), [line]
        else:
            cur.append(line)
    if cur:
        blocks.append((title, "\n".join(cur)))
    return blocks


def splice_script(current, part):
    """Replace the sections of `current` that `part` returns (by title); everything else stays exactly."""
    blocks = script_sections(current)
    for title, block in script_sections(part):
        at = next((k for k, (t, _) in enumerate(blocks) if title and t and t.lower() == title.lower()), None)
        if at is not None:
            blocks[at] = (blocks[at][0], block)
    return "\n\n".join(b.strip("\n") for _, b in blocks)


def _section_of_line(text, n):
    title = None
    for k, line in enumerate(text.splitlines(), start=1):
        if k > n:
            break
        m = re.match(r'^\s*\[SECTION\s+title="([^"]*)"', line)
        if m:
            title = m.group(1)
    return title


def _section_of_id(text, marker, vid):
    for title, block in script_sections(text):
        if re.search(rf'\[{marker}\s+id="{re.escape(vid)}"', block):
            return title
    return None


def problem_script_sections(text, problems):
    """The sections each problem is about, or None when any problem concerns the whole script."""
    out = []
    for p in problems:
        m = re.match(r"^line (\d+):", p)
        title = None
        if m:
            title = _section_of_line(text, int(m.group(1)))
        elif (m := re.match(r'^section "([^"]+)"', p)) or (m := re.search(r'In section "([^"]+)"', p)):
            title = m.group(1)
        elif (m := re.search(r'(?:diagram "|FLOW(?:_NEXT|_HIGHLIGHT)? id=")([\w-]+)', p)):
            title = _section_of_id(text, "FLOW", m.group(1))
        elif (m := re.search(r'VISUAL(?:_SET)? id="([\w-]+)"', p)):
            title = _section_of_id(text, "VISUAL", m.group(1))
        if not title:
            return None
        out.append(title)
    return list(dict.fromkeys(out)) or None
