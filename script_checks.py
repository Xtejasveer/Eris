"""Find formatting problems in a generated script and say what to change, by line. Never edits anything.

The messages go back to the script writer as feedback (same rules as FORMAT_RULES in prompts.py).
clean_cosmetic is the one exception that edits text: markdown symbols only (stars, # headings, bullet
dashes), which change nothing about the lesson.
"""

import re

import config
from format_fixes import BULLET_RE, INLINE_RE, _looks_like_notes
from script_parser import BLOCK_MARKERS, MARKERS, parse_line_marker

HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
STARS_RE = re.compile(r"\*\*(.+?)\*\*|(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])")


def _blocks(lines):
    """Yield (index, line, marker, body_end) for every top-level line; block bodies are skipped."""
    i = 0
    while i < len(lines):
        marker = parse_line_marker(lines[i])
        end = i
        if marker and marker[0] in BLOCK_MARKERS:
            end = next((j for j in range(i + 1, len(lines)) if lines[j].strip() == f"[/{marker[0]}]"), len(lines) - 1)
        yield i, lines[i], marker, end
        i = end + 1


def clean_cosmetic(text):
    """Strip markdown symbols: from narration (**, *, # headings, bullet dashes/numbers) and from notes
    (** and backticks). Returns (text, number of lines changed)."""
    lines = text.splitlines()
    out, changed = [], 0
    for i, line, marker, end in _blocks(lines):
        if marker and marker[0] == "NOTE":
            body = [ln.replace("**", "").replace("`", "") for ln in lines[i + 1:end]]
            changed += sum(a != b for a, b in zip(body, lines[i + 1:end]))
            out += [line, *body, *lines[end:end + 1]]
            continue
        if marker:
            out += lines[i:end + 1]
            continue
        new = STARS_RE.sub(lambda m: m.group(1) or m.group(2), BULLET_RE.sub("", HEADING_RE.sub("", line)))
        changed += new != line
        out.append(new)
    return "\n".join(out), changed


def format_problems(text, outputs=()):
    """Formatting problems as feedback lines. outputs: real program outputs in [RUN] order (to spot typed output)."""
    lines, problems, runs = text.splitlines(), [], -1
    for i, line, marker, end in _blocks(lines):
        n = i + 1
        if marker is None:
            for m in INLINE_RE.finditer(line):
                inner = parse_line_marker(m.group(0))
                if inner and inner[0] in MARKERS:
                    problems.append(f"line {n}: {m.group(0)} is inside a sentence; put it alone on its own line "
                                    "before the sentence (formatting rule 1)")
            continue
        name, args = marker
        if name.startswith("/") and name[1:] in MARKERS and name[1:] not in BLOCK_MARKERS:
            problems.append(f"line {n}: [{name}] is not a marker; delete it (formatting rule 2)")
        elif name == "RUN":
            runs += 1
        elif name == "READ_OUTPUT":
            want = {ln.strip() for ln in (outputs[runs] if 0 <= runs < len(outputs) else "").splitlines() if ln.strip()}
            following = [ln.strip() for ln in lines[i + 1:i + 4] if ln.strip()]
            if following and (following[0] in want or following[0] == "[/READ_OUTPUT]"):
                problems.append(f"line {n}: the program output is typed after [READ_OUTPUT]; delete it and go straight "
                                "to a sentence that describes the output (formatting rule 2)")
        elif name == "NOTE_TITLE":
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            paragraph = []
            while j < len(lines) and lines[j].strip() and parse_line_marker(lines[j]) is None:
                paragraph.append(lines[j])
                j += 1
            if _looks_like_notes(paragraph):
                problems.append(f"line {n}: the lines after [NOTE_TITLE text=\"{args.get('text', '')}\"] are notes but "
                                "not inside [NOTE] ... [/NOTE], so they would be spoken; wrap them (formatting rule 3)")
        elif name == "PAUSE" and str(args.get("s", "0")).isdigit() and int(args["s"]) > config.PAUSE_MAX_S:
            problems.append(f"line {n}: [PAUSE s={args['s']}] is too long; use at most {config.PAUSE_MAX_S} seconds "
                            "(formatting rule 6)")
    return problems


def teaching_problems(segments):
    """Soft problems (advice): they go back to the writer as feedback but never fail a generation.
    Long spoken sentences sound rushed; a notebook written once per section looks like a slide, not a teacher."""
    problems, long_ones = [], []
    sections, current = [], None
    for seg in segments:
        if seg.get("name") == "SECTION":
            current = {"title": seg["args"]["title"], "words": 0, "notes": 0}
            sections.append(current)
        elif seg.get("name") == "NOTE" and current:
            current["notes"] += 1
        elif seg["kind"] == "say":
            if current:
                current["words"] += len(seg["text"].split())
            long_ones += [s for s in re.split(r"(?<=[.!?])\s+", seg["text"]) if len(s.split()) > config.MAX_SENTENCE_WORDS]
    for sentence in long_ones[:5]:
        problems.append(f"this spoken sentence has {len(sentence.split())} words; split it into short sentences "
                        f"(under 20 words each): \"{sentence[:90]}...\"")
    if len(long_ones) > 5:
        problems.append(f"{len(long_ones) - 5} more spoken sentences are over {config.MAX_SENTENCE_WORDS} words; split them too")
    words = sum(s["words"] for s in sections)
    notes = sum(s["notes"] for s in sections)
    wanted = words // config.WORDS_PER_NOTE
    if notes < wanted:
        problems.append(f"the notebook is under-used: {notes} [NOTE] blocks for {words} spoken words; write at least "
                        f"{wanted}. Come back to the notebook after each program's output, and add worked examples, "
                        "traces, comparisons or common mistakes as [NOTE] blocks")
    visuals = sum(1 for seg in segments if seg.get("name") == "VISUAL")
    if visuals > config.MAX_VISUALS:
        problems.append(f"the script has {visuals} [VISUAL]s; keep the {config.MAX_VISUALS} that help most "
                        "(something that moves or changes), and teach the rest with notes")
    for s in sections[1:-1]:  # the Opening and Closing are messages, not lessons
        if s["words"] > config.SECTION_TWO_NOTES_WORDS and s["notes"] < 2:
            problems.append(f"section \"{s['title']}\" has {s['words']} spoken words but {s['notes']} [NOTE] block(s); "
                            "write at least two (the idea, then an example, a trace or a comparison)")
    return problems


# The sentence spoken while a note or program appears should say what is being written.
ANNOUNCES_WRITING_RE = re.compile(
    r"\b(let me|let's|let us|i'll|i will|i'm|i am|we'll|we will|we're)\s+(now\s+)?"
    r"(write|type|jot|note|put|draw|add|list|sketch|copy|show|open)|\b(writing|typing|jotting)\b", re.I)


def narration_problems(segments, limit=4):
    """Soft: a while_speaking note/program whose spoken sentence doesn't say what is being written
    (the class sees one thing appear while hearing about another)."""
    problems = []
    for i, seg in enumerate(segments[:-1]):
        if not seg.get("args", {}).get("while_speaking") or segments[i + 1]["kind"] != "say":
            continue
        said = segments[i + 1]["text"]
        if ANNOUNCES_WRITING_RE.search(said):
            continue
        a = seg["args"]
        written = ((a.get("code") or a.get("text") or a.get("title") or "").strip().splitlines() or [""])[0][:50]
        problems.append(f"while [{seg['name']}] \"{written}...\" appears, the narration says \"{said[:70]}\"; "
                        "start with a short sentence that says what you are writing (\"Let me write...\", "
                        "\"I'll type...\"), then explain")
    if len(problems) > limit:
        problems = problems[:limit] + [f"{len(problems) - limit} more notes or programs start without saying what is being written"]
    return problems