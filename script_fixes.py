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

AUTO_FLAG = {"NOTE", "NOTE_TITLE", "WRITE_CODE", "VISUAL", "FLOW_NEXT"}
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


NOT_CONCEPT_RE = re.compile(r"\b(opening|introduction|intro|recap|summary|closing|wrap[- ]?up|conclusion)\b", re.I)


def concept_sections(segments):
    """Titles of the teaching sections (not the opening, recap or closing)."""
    titles = [s["args"]["title"] for s in segments if s.get("name") == "SECTION"]
    return [t for t in titles[1:] if not NOT_CONCEPT_RE.search(t)]


def add_doubt_checks(text, keep):
    """Give each of the first `keep` concept sections a [DOUBT_CHECK] at its end (if it has none) and make the
    last line one. Returns (text, number added)."""
    lines = text.splitlines()
    sections = _marker_lines(lines, "SECTION")
    titles = [parse_line_marker(lines[i])[1].get("title", "") for i in sections]
    concept = [k for k, t in enumerate(titles) if k > 0 and not NOT_CONCEPT_RE.search(t)][:keep]
    inserts = []
    for k in concept:
        start, stop = sections[k], sections[k + 1] if k + 1 < len(sections) else len(lines)
        if not any(parse_line_marker(ln) and parse_line_marker(ln)[0] == "DOUBT_CHECK" for ln in lines[start:stop]):
            inserts.append(stop)
    for at in sorted(inserts, reverse=True):
        lines[at:at] = ["[DOUBT_CHECK]", ""]
    added = len(inserts)
    last = next((ln for ln in reversed(lines) if ln.strip()), "")
    if parse_line_marker(last) is None or parse_line_marker(last)[0] != "DOUBT_CHECK":
        lines.append("[DOUBT_CHECK]")
        added += 1
    return "\n".join(lines), added


def _flow_labels(lines):
    """flow id -> its block labels, from the [FLOW] blocks in the text."""
    from flow_diagram import parse_flow
    out = {}
    for i, line in enumerate(lines):
        m = parse_line_marker(line)
        if m and m[0] == "FLOW":
            end = _block_end(lines, i, "FLOW")
            if end is not None:
                out[m[1].get("id")] = [b["label"] for b in parse_flow("\n".join(lines[i + 1:end]))[0]]
    return out


def _say_line(lines, j, step):
    """Index of the nearest non-blank line from j in direction step, if it is narration; else None."""
    while 0 <= j < len(lines) and not lines[j].strip():
        j += step
    return j if 0 <= j < len(lines) and parse_line_marker(lines[j]) is None else None


def fix_flow_order(text):
    """A block's sentence said BEFORE its [FLOW_NEXT] (the narration runs one block ahead): move the marker in front
    of that sentence. Returns (text, number moved)."""
    from script_checks import said_too_early
    lines = text.splitlines()
    labels = _flow_labels(lines)
    counts, moved, i = {}, 0, 0
    while i < len(lines):
        m = parse_line_marker(lines[i])
        if m and m[0] == "FLOW_NEXT" and m[1].get("id") in labels:
            fid = m[1]["id"]
            k = counts.get(fid, 0)
            counts[fid] = k + 1
            blocks = labels[fid]
            label = blocks[k] if k < len(blocks) else ""
            nxt = blocks[k + 1] if k + 1 < len(blocks) else ""
            before, after = _say_line(lines, i - 1, -1), _say_line(lines, i + 1, 1)
            if label and before is not None and said_too_early(
                    re.split(r"(?<=[.!?])\s+", lines[before].strip())[-1],
                    lines[after].split(". ")[0] if after is not None else "", label, nxt):
                lines.insert(before, lines.pop(i))
                moved += 1
        i += 1
    return "\n".join(lines), moved


def complete_flows(text):
    """Draw every block a diagram leaves out: right before the sentence that already names it (after the last
    [FLOW_NEXT]), or with a short sentence of its own. Returns (text, number added)."""
    from script_checks import block_score
    lines = text.splitlines()
    added = 0
    for fid, blocks in _flow_labels(lines).items():
        idx = [i for i, ln in enumerate(lines) if (m := parse_line_marker(ln)) and m[0] == "FLOW_NEXT" and m[1].get("id") == fid]
        for label in blocks[len(idx):]:
            idx = [i for i, ln in enumerate(lines) if (m := parse_line_marker(ln)) and m[0] == "FLOW_NEXT" and m[1].get("id") == fid]
            start = (idx[-1] + 1) if idx else next(i for i, ln in enumerate(lines) if ln.strip() == "[/FLOW]") + 1
            j = start
            while j < len(lines) and parse_line_marker(lines[j]) is None:  # the narration after the last drawn block
                if lines[j].strip() and j > start and block_score(lines[j], label) >= 0.5:
                    break
                j += 1
            if j < len(lines) and parse_line_marker(lines[j]) is None and lines[j].strip():
                lines.insert(j, f'[FLOW_NEXT id="{fid}"]')  # the script already says this block here
            else:
                at = j
                lines[at:at] = [f'[FLOW_NEXT id="{fid}"]', f"Next on the board: {label[0].lower() + label[1:]}."]
            added += 1
    return "\n".join(lines), added


def early_doubt_checks(segments):
    """Titles of sections whose [DOUBT_CHECK] comes before the section has finished teaching."""
    out, section = [], None
    for i, seg in enumerate(segments):
        if seg.get("name") == "SECTION":
            section = seg["args"]["title"]
        elif seg.get("name") == "DOUBT_CHECK" and i + 1 < len(segments):
            following = segments[i + 1:]
            ends = next((k for k, s in enumerate(following) if s.get("name") == "SECTION"), len(following))
            if any(s["kind"] == "action" for s in following[:ends]) and section:
                out.append(section)
    return out


def move_doubt_checks_to_section_end(text):
    """Move each [DOUBT_CHECK] that comes before its section has finished to just before the next [SECTION].
    Returns (text, number moved)."""
    lines = text.splitlines()
    sections = _marker_lines(lines, "SECTION")
    checks = _marker_lines(lines, "DOUBT_CHECK")
    moves = []
    for c in checks[:-1]:
        nxt = next((s for s in sections if s > c), None)
        if nxt is None:
            continue
        between = [ln for ln in lines[c + 1:nxt] if parse_line_marker(ln) and not parse_line_marker(ln)[0].startswith("/")]
        if between:
            moves.append((c, nxt))
    for c, nxt in sorted(moves, reverse=True):
        lines.insert(nxt, "[DOUBT_CHECK]")
        lines.insert(nxt + 1, "")
        del lines[c]
    return "\n".join(lines), len(moves)


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


USERS = {"VISUAL": ("VISUAL", "VISUAL_SET", "OPEN_VISUAL"), "FLOW": ("FLOW", "FLOW_NEXT", "FLOW_HIGHLIGHT", "OPEN_FLOW")}


def drop_visual(text, visual_id, block="VISUAL"):
    """Remove the [VISUAL id=..] (or [FLOW id=..]) block and the markers that use it. Returns the text."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        marker = parse_line_marker(lines[i])
        if marker and marker[1].get("id") == visual_id and marker[0] in USERS[block]:
            end = _block_end(lines, i, block) if marker[0] == block else i
            i = (end if end is not None else i) + 1
            if i < len(lines) and lines[i].strip() in VISUAL_LEADS + FLOW_LEADS:
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


def drop_markers(text, names):
    """Remove every marker line in `names` (and the whole body of block markers among them). The narration
    stays. Returns (text, number removed)."""
    lines, out, removed, i = text.splitlines(), [], 0, 0
    while i < len(lines):
        marker = parse_line_marker(lines[i])
        if marker and marker[0] in BLOCK_MARKERS:
            end = _block_end(lines, i, marker[0])
            end = len(lines) - 1 if end is None else end
            if marker[0] in names:
                removed += 1
            else:
                out += lines[i:end + 1]
            i = end + 1
            continue
        if marker and marker[0] in names:
            removed += 1
        else:
            out.append(lines[i])
        i += 1
    return "\n".join(out), removed


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


FLOW_LEADS = ["Let me draw the next step on the board.", "Let me add the next block.", "Now the next step goes on the board."]
VISUAL_LEADS = ["Let me show you this on a graph.", "Let me put this on a graph you can play with.", "Let me show you how this looks on a graph."]
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
    from flow_diagram import parse_flow
    from script_checks import ANNOUNCES_WRITING_RE, _names_block  # script_checks imports format_fixes, not this module

    lines, out, added, i = text.splitlines(), [], 0, 0
    flows = {}  # flow id -> [labels still to draw], so a reveal whose sentence names its block needs no lead
    while i < len(lines):
        marker = parse_line_marker(lines[i])
        if marker and marker[0] == "FLOW":
            end = _block_end(lines, i, "FLOW")
            if end is not None:
                flows[marker[1].get("id")] = [b["label"] for b in parse_flow("\n".join(lines[i + 1:end]))[0]]
        if marker is None or marker[0] not in AUTO_FLAG:
            out.append(lines[i]); i += 1
            continue
        name, args = marker
        label = flows.get(args.get("id"), [""]).pop(0) if name == "FLOW_NEXT" and flows.get(args.get("id")) else ""
        end = _block_end(lines, i, name) if name in BLOCK_MARKERS else i
        if end is None:
            out += lines[i:]; break
        out += lines[i:end + 1]
        j = end + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        first = lines[j].split(". ")[0] if j < len(lines) else ""
        prev = _say_line(lines, i - 1, -1)
        if prev is not None and ANNOUNCES_WRITING_RE.search(lines[prev]):
            i = end + 1
            continue  # "Let me type the code..." was said just before: a second lead would repeat it
        if j < len(lines) and parse_line_marker(lines[j]) is None and not ANNOUNCES_WRITING_RE.search(first) \
                and not (name == "FLOW_NEXT" and _names_block(first, label)):
            if name == "WRITE_CODE":
                lead = CODE_LEADS[added % len(CODE_LEADS)]
            elif name == "VISUAL":
                lead = VISUAL_LEADS[added % len(VISUAL_LEADS)]
            elif name == "FLOW_NEXT":
                lead = FLOW_LEADS[added % len(FLOW_LEADS)]
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
