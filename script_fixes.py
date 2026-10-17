"""Fixes that code makes to a generated script, so we don't depend on the model getting them right.

- add_sync_flags: a [NOTE], [NOTE_TITLE] or [WRITE_CODE] followed by narration gets while_speaking=true,
  so it is written while that sentence is spoken (Level 2 sync).
- trim_doubt_checks: keep at most N question breaks plus the final one.
- drop_bad_staging: remove highlight / look-back markers the parser rejects (the narration stays).
- announce_writing: before the narration of a note/program that doesn't say what is being written, add a short
  lead that does ("Let me write this down: ..."), so the class hears what appears.
- drop_visual / drop_bad_visuals: remove a [VISUAL] that can't be built or read, with every [VISUAL_SET] and
  [OPEN_VISUAL] that uses it (the narration stays).
- remove_flags: undo while_speaking on pairs where the sentence doesn't describe the writing (judge says so).
They run only during `generate`; the teacher's edits in Studio are never changed by approve.
"""

import re

from script_parser import BLOCK_MARKERS, parse_line_marker

AUTO_FLAG = {"NOTE", "NOTE_TITLE", "WRITE_CODE", "VISUAL"}
# Optional staging: if one of these can't be resolved, the lesson still works without it.
DROPPABLE = {"HIGHLIGHT", "NOTE_HIGHLIGHT", "SLIDE_HIGHLIGHT", "LOOK_BACK", "VISUAL_SET", "OPEN_VISUAL"}
ERROR_LINE_RE = re.compile(r"^line (\d+): \[([A-Z_]+)\]")


def _block_end(lines, start, name):
    """Index of the [/NAME] line closing the block that starts at `start` (None if never closed)."""
    for j in range(start + 1, len(lines)):
        if lines[j].strip() == f"[/{name}]":
            return j
    return None


def _narration_follows(lines, after):
    """True if the first non-blank line after index `after` is narration (not a marker)."""
    for line in lines[after + 1:]:
        if line.strip():
            return parse_line_marker(line) is None
    return False


def add_sync_flags(text):
    """Return (text with while_speaking=true added where it fits, number of flags added)."""
    lines = text.splitlines()
    added = 0
    i = 0
    while i < len(lines):
        marker = parse_line_marker(lines[i])
        if marker is None:
            i += 1
            continue
        name, args = marker
        end = i
        if name in BLOCK_MARKERS:
            end = _block_end(lines, i, name)
            if end is None:  # broken block: leave it to the parser to report
                break
        if name in AUTO_FLAG and "while_speaking" not in args and _narration_follows(lines, end):
            line = lines[i].rstrip()
            lines[i] = line[:-1].rstrip() + " while_speaking=true]"
            added += 1
        i = end + 1  # never look for markers inside a code or note body
    return "\n".join(lines), added


def _marker_lines(lines, name):
    """Indexes of top-level [NAME] marker lines (not inside a code or note body)."""
    found, i = [], 0
    while i < len(lines):
        marker = parse_line_marker(lines[i])
        if marker and marker[0] in BLOCK_MARKERS:
            end = _block_end(lines, i, marker[0])
            i = (end if end is not None else len(lines)) + 1
            continue
        if marker and marker[0] == name:
            found.append(i)
        i += 1
    return found


def remove_flags(text, ordinals):
    """Remove while_speaking=true from the flagged markers at these positions (0 = first flagged marker)."""
    lines, n, i = text.splitlines(), -1, 0
    while i < len(lines):
        marker = parse_line_marker(lines[i])
        if marker and marker[1].get("while_speaking") in ("true", True):
            n += 1
            if n in ordinals:
                lines[i] = re.sub(r"\s+while_speaking=true", "", lines[i])
        if marker and marker[0] in BLOCK_MARKERS:
            end = _block_end(lines, i, marker[0])
            i = (end if end is not None else len(lines)) + 1
            continue
        i += 1
    return "\n".join(lines)


def trim_doubt_checks(text, keep):
    """Keep the last [DOUBT_CHECK] and `keep` evenly spaced earlier ones. Returns (text, number removed)."""
    lines = text.splitlines()
    checks = _marker_lines(lines, "DOUBT_CHECK")
    earlier = checks[:-1]
    if len(earlier) <= keep:
        return text, 0
    step = len(earlier) / keep
    kept = {earlier[int(step * (k + 1)) - 1] for k in range(keep)}
    drop = set(earlier) - kept
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop), len(drop)


def drop_bad_staging(text, errors):
    """Remove the marker lines named in parser errors when they are optional staging (DROPPABLE).
    Returns (text, dropped error messages)."""
    lines = text.splitlines()
    drop, dropped = set(), []
    for err in errors:
        match = ERROR_LINE_RE.match(err)
        if match and match.group(2) in DROPPABLE:
            drop.add(int(match.group(1)) - 1)
            dropped.append(err.splitlines()[0])
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop), dropped


def drop_visual(text, visual_id):
    """Remove the [VISUAL id=visual_id] block and the markers that use it. Returns the text."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        marker = parse_line_marker(lines[i])
        if marker and marker[1].get("id") == visual_id and marker[0] in ("VISUAL", "VISUAL_SET", "OPEN_VISUAL"):
            end = _block_end(lines, i, "VISUAL") if marker[0] == "VISUAL" else i
            i = (end if end is not None else i) + 1
            if marker[0] == "VISUAL" and i < len(lines) and lines[i].strip() in VISUAL_LEADS:
                i += 1  # the lead code added for it ("Let me show you...") would announce nothing
            continue
        if marker and marker[0] in BLOCK_MARKERS:
            end = _block_end(lines, i, marker[0])
            end = len(lines) - 1 if end is None else end
            out += lines[i:end + 1]
            i = end + 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def drop_bad_visuals(text, errors):
    """Remove each [VISUAL] block a parser error points at. Returns (text, dropped error messages)."""
    lines, ids, dropped = text.splitlines(), [], []
    for err in errors:
        match = ERROR_LINE_RE.match(err)
        if match and match.group(2) == "VISUAL" and int(match.group(1)) <= len(lines):
            marker = parse_line_marker(lines[int(match.group(1)) - 1])
            if marker and marker[0] == "VISUAL":
                ids.append(marker[1].get("id", ""))
                dropped.append(err.splitlines()[0])
    for vid in dict.fromkeys(ids):
        text = drop_visual(text, vid)
    return text, dropped


VISUAL_LEADS = ["Let me show you this as a picture.", "Let me draw this so you can see it.", "Let me show you how this looks."]
NOTE_LEADS = ["Let me write this down: {}.", "I'll note this down: {}.", "Let me jot this down: {}."]
CODE_LEADS = ["Let me type this program out for you.", "I'll type the code into the editor now.",
              "Let me write this as a small program."]


def _spoken_phrase(line):
    """A note line as a short phrase to say, or None if it is code-like or a bare heading."""
    phrase = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip().rstrip(".:")
    if not phrase or re.search(r"[=<>{}\[\]()_#]|->", phrase) or len(phrase.split()) < 2:
        return None
    words = phrase.split()[:9]
    return " ".join(words)[0].lower() + " ".join(words)[1:]


def _generic_note_lead(body, n):
    """A lead for a note whose first line can't be read aloud (code, symbols, a bare heading)."""
    joined = " ".join(body).lower()
    if "->" in joined:
        return "Let me trace it step by step on the board."
    if re.search(r"\b(shape|syntax|form|template)\b", joined):
        return "Let me write the shape on the board."
    if re.search(r"\b(example|e\.g\.)\b", joined):
        return "Let me write a small example on the board."
    return ["Let me write this down on the board.", "Let me put this on the board.", "I'll write this out for you."][n % 3]


def announce_writing(text):
    """For each note/program followed by narration whose first sentence doesn't say what is being written,
    insert a lead sentence that does. Returns (text, number of leads added)."""
    from script_checks import ANNOUNCES_WRITING_RE  # script_checks imports format_fixes, not this module

    lines, out, added, i = text.splitlines(), [], 0, 0
    while i < len(lines):
        marker = parse_line_marker(lines[i])
        if marker is None or marker[0] not in AUTO_FLAG:
            out.append(lines[i]); i += 1
            continue
        name, args = marker
        end = _block_end(lines, i, name) if name in BLOCK_MARKERS else i
        if end is None:
            out += lines[i:]; break
        out += lines[i:end + 1]
        j = end + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and parse_line_marker(lines[j]) is None and not ANNOUNCES_WRITING_RE.search(lines[j].split(". ")[0]):
            if name == "WRITE_CODE":
                lead = CODE_LEADS[added % len(CODE_LEADS)]
            elif name == "VISUAL":
                lead = VISUAL_LEADS[added % len(VISUAL_LEADS)]
            elif name == "NOTE_TITLE":
                lead = f"Let me write the heading: {args.get('text', '').strip()}."
            else:
                body = [ln for ln in lines[i + 1:end] if ln.strip()]
                phrase = _spoken_phrase(body[0] if body else "")
                lead = NOTE_LEADS[added % len(NOTE_LEADS)].format(phrase) if phrase else _generic_note_lead(body, added)
            out.append(lead)
            added += 1
        i = end + 1
    return "\n".join(out), added


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python script_fixes.py <script.md>   (prints the flagged script)")
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        flagged, count = add_sync_flags(f.read())
    print(flagged)
    print(f"\n[sync] {count} flag(s) added", file=sys.stderr)
