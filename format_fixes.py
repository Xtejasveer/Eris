"""Repair formatting mistakes that make screen instructions get spoken aloud. No LLM here.

A marker only works alone on its line. Models sometimes:
1. put a marker inside a sentence:   The keyword is [NOTE_HIGHLIGHT text="while"].
2. type the program output under [READ_OUTPUT] ... [/READ_OUTPUT] (the terminal already shows the real one)
3. write note bullets after [NOTE_TITLE] without a [NOTE] block around them
In all three cases the text would be read out by the teacher. fix_format repairs them and says what it did.
It also shortens long [PAUSE]s and strips markdown (** and backticks) from notebook lines.
strip_typed_output runs later, once the real program output is known, for typed output with no closing tag.
"""

import re

import config
from script_parser import BLOCK_MARKERS, MARKERS, parse_line_marker

INLINE_RE = re.compile(r"\[([A-Z][A-Z_]+)\b[^\[\]]*\]")
QUOTED_MARKERS = {"NOTE_HIGHLIGHT", "SLIDE_HIGHLIGHT", "LOOK_BACK"}  # their text= words are also said
BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
NOTE_LINE_MAX = 80  # longer lines are sentences, not notes


def _body_end(lines, start, name):
    for j in range(start + 1, len(lines)):
        if lines[j].strip() == f"[/{name}]":
            return j
    return None


def _hoist_inline(line):
    """Return (marker lines to put before the sentence, the sentence without them)."""
    hoisted = []

    def replace(match):
        marker = parse_line_marker(match.group(0))
        if not marker or marker[0] not in MARKERS or marker[0] in BLOCK_MARKERS:
            return match.group(0)  # brackets that are not a marker, e.g. [expression for item in list]
        hoisted.append(match.group(0))
        return marker[1].get("text", "") if marker[0] in QUOTED_MARKERS else ""

    sentence = INLINE_RE.sub(replace, line)
    sentence = re.sub(r"\s+([.,!?;:])", r"\1", re.sub(r"\s{2,}", " ", sentence)).strip()
    indent = line[: len(line) - len(line.lstrip())]
    return [indent + m for m in hoisted], sentence


def _looks_like_notes(paragraph):
    """A paragraph of short lines with bullets, indentation or 'Heading:' lines is notebook content."""
    if not paragraph or any(len(ln.strip()) > NOTE_LINE_MAX for ln in paragraph):
        return False
    return any(BULLET_RE.match(ln) or ln.startswith((" ", "\t")) or ln.rstrip().endswith(":") for ln in paragraph)


def _wrap_loose_notes(lines, start):
    """After a [NOTE_TITLE] at `start`: wrap the note-like paragraphs that follow in [NOTE] ... [/NOTE].
    Returns (replacement lines for lines[start+1:end], end) or (None, start+1) when nothing to wrap."""
    i, body = start + 1, []
    while i < len(lines):
        j = i
        while j < len(lines) and not lines[j].strip():
            j += 1
        paragraph = []
        while j < len(lines) and lines[j].strip() and parse_line_marker(lines[j]) is None:
            paragraph.append(lines[j])
            j += 1
        if not _looks_like_notes(paragraph):
            break
        body += ([""] if body else []) + paragraph
        i = j
    if not body:
        return None, start + 1
    return ["[NOTE]", *body, "[/NOTE]"], i


def _split_note(body, size=6):
    """Split note lines into chunks of at most `size` lines, preferring blank-line paragraph breaks."""
    paragraphs, cur = [], []
    for ln in body:
        if ln.strip():
            cur.append(ln)
        elif cur:
            paragraphs.append(cur); cur = []
    if cur:
        paragraphs.append(cur)
    parts, part = [], []
    for para in paragraphs:
        for k in range(0, len(para), size):
            piece = para[k:k + size]
            if part and len(part) + len(piece) > size:
                parts.append(part); part = []
            part = part + piece
    if part:
        parts.append(part)
    return parts


def fix_format(text):
    """Return (fixed text, list of what was fixed)."""
    lines, out, fixed = text.splitlines(), [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        marker = parse_line_marker(line)
        if marker and marker[0] in BLOCK_MARKERS:  # code bodies stay untouched; note lines lose markdown
            end = _body_end(lines, i, marker[0])
            end = len(lines) - 1 if end is None else end
            body = lines[i + 1:end]
            if marker[0] == "NOTE":
                clean = [ln.replace("**", "").replace("`", "") for ln in body]
                if clean != body:
                    fixed.append("removed markdown (** or backticks) from notebook lines")
                body = clean
                if sum(1 for ln in body if ln.strip()) > config.NOTE_MAX_LINES:
                    parts = _split_note(body)
                    fixed.append(f"split a {sum(1 for ln in body if ln.strip())}-line note into {len(parts)} notes")
                    for n, part in enumerate(parts):
                        out += ([lines[i]] if n == 0 else ["[NOTE]"]) + part + ["[/NOTE]"]
                    i = end + 1
                    continue
            out += [lines[i], *body] + ([lines[end]] if end < len(lines) and end > i else [])
            i = end + 1
            continue
        if marker and marker[0] == "PAUSE" and str(marker[1].get("s", "0")).isdigit() \
                and int(marker[1]["s"]) > config.PAUSE_MAX_S:
            fixed.append(f"shortened [PAUSE s={marker[1]['s']}] to {config.PAUSE_MAX_S} seconds")
            out.append(re.sub(r"\bs=\S+?(?=[\s\]])", f"s={config.PAUSE_MAX_S}", line))
            i += 1
            continue
        if marker and marker[0] == "READ_OUTPUT":
            out.append(line)
            end = _body_end(lines, i, "READ_OUTPUT")
            if end is not None and all(parse_line_marker(ln) is None for ln in lines[i + 1:end]):
                fixed.append(f"removed {end - i - 1} line(s) of typed program output after [READ_OUTPUT]")
                i = end + 1
            else:
                i += 1
            continue
        if marker and marker[0].startswith("/") and marker[0][1:] in MARKERS and marker[0][1:] not in BLOCK_MARKERS:
            fixed.append(f"removed a stray [{marker[0]}]")
            i += 1
            continue
        if marker and marker[0] == "NOTE_TITLE":
            out.append(line)
            wrapped, end = _wrap_loose_notes(lines, i)
            if wrapped:
                fixed.append(f'wrapped the notes under [NOTE_TITLE text="{marker[1].get("text", "")}"] in a [NOTE] block')
                out += wrapped
                i = end
            else:
                i += 1
            continue
        if marker is None and INLINE_RE.search(line):
            hoisted, sentence = _hoist_inline(line)
            if hoisted:
                fixed += [f"moved {m.strip()} out of a sentence onto its own line" for m in hoisted]
                out += hoisted + ([sentence] if sentence else [])
                i += 1
                continue
        out.append(line)
        i += 1
    return "\n".join(out), fixed


def strip_typed_output(text, segments):
    """Remove narration lines after [READ_OUTPUT] that are copies of the program's real output.
    Needs segments with expected_output filled (run order = order of [RUN] lines). Returns (text, lines removed)."""
    outputs = [s.get("expected_output", "") for s in segments if s.get("name") == "RUN"]
    lines, out, removed, runs = text.splitlines(), [], 0, -1
    i = 0
    while i < len(lines):
        marker = parse_line_marker(lines[i])
        out.append(lines[i])
        if marker and marker[0] in BLOCK_MARKERS:
            end = _body_end(lines, i, marker[0])
            end = len(lines) - 1 if end is None else end
            out += lines[i + 1:end + 1]
            i = end + 1
            continue
        if marker and marker[0] == "RUN":
            runs += 1
        if marker and marker[0] == "READ_OUTPUT" and 0 <= runs < len(outputs):
            want = [ln.strip() for ln in outputs[runs].splitlines() if ln.strip()]
            j, k = i + 1, 0
            while j < len(lines) and k < len(want):
                line = lines[j].strip()
                if line == want[k]:
                    k += 1
                elif line:
                    break
                j += 1
            if k:  # drop the copied lines (and blank lines between them), keep everything after
                removed += j - i - 1
                i = j
                continue
        i += 1
    return "\n".join(out), removed


if __name__ == "__main__":
    import sys

    with open(sys.argv[1], encoding="utf-8") as f:
        result, notes = fix_format(f.read())
    print(result)
    print("\n".join(f"[fix] {n}" for n in notes), file=sys.stderr)
