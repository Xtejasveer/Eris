"""Fixes that code makes to a generated script, so we don't depend on the model getting them right.

- add_sync_flags: highlights, pen circles and slider moves followed by narration get while_speaking=true, so they
  happen as that sentence starts. Notes, programs, graphs and diagram blocks are written first, then explained.
- trim_doubt_checks: keep at most N question breaks plus the final one.
- drop_bad_staging: remove highlight / look-back markers the parser rejects (the narration stays).
- drop_visual / drop_bad_visuals: remove a [VISUAL] that can't be built or read, with every [VISUAL_SET] and
  [OPEN_VISUAL] that uses it (the narration stays).
- show_picture_slides: when the script talks about a picture, diagram or chart from the material, its slide is put
  on screen first (if it isn't showing), so the class sees the real picture while it is explained.
- remove_flags: undo while_speaking on pairs where the sentence doesn't describe the writing (judge says so).
They run only during `generate`; the teacher's edits in Studio are never changed by approve.
"""

import re

from eris.generate.script_parser import BLOCK_MARKERS, parse_line_marker

AUTO_FLAG = {"NOTE", "NOTE_TITLE", "WRITE_CODE", "VISUAL", "FLOW_NEXT"}
# Optional staging: if one of these can't be resolved, the lesson still works without it.
DROPPABLE = {"HIGHLIGHT", "NOTE_HIGHLIGHT", "SLIDE_HIGHLIGHT", "SLIDE_CIRCLE", "LOOK_BACK", "VISUAL_SET", "OPEN_VISUAL",
             "FLOW_NEXT", "FLOW_HIGHLIGHT", "OPEN_FLOW"}
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


# Write first, then explain: notes, programs, graphs and diagram blocks appear BEFORE the sentence about them. Only
# instant pointers run while their sentence is spoken: a highlight, a pen circle, a slider move.
PARALLEL = {"HIGHLIGHT", "NOTE_HIGHLIGHT", "SLIDE_HIGHLIGHT", "FLOW_HIGHLIGHT", "LOOK_BACK", "SLIDE_CIRCLE", "VISUAL_SET"}
FLAG_RE = re.compile(r"\s+while_speaking=(?:true|false)")


def add_sync_flags(text):
    """Return (text with while_speaking=true on every highlight, pen circle and slider move followed by narration,
    and on nothing else, number of flags). Any flag on a note, program, graph or diagram is removed: those are shown
    first, then explained."""
    lines = [FLAG_RE.sub("", ln) if (m := parse_line_marker(ln)) and m[0] not in PARALLEL else ln for ln in text.splitlines()]
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
        if name in PARALLEL and "while_speaking" not in args and _narration_follows(lines, end):
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
    from eris.visuals.flow_diagram import parse_flow
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


def _lead_before(lines, i):
    """The spoken line just before the marker at i, looking past the note's own heading ([NOTE_TITLE], [NEW_PAGE]):
    "Let me write the Code." before [NOTE_TITLE] already announces the [NOTE] after it."""
    j = i - 1
    while j >= 0 and (not lines[j].strip() or (parse_line_marker(lines[j]) or ("",))[0] in ("NOTE_TITLE", "NEW_PAGE")):
        j -= 1
    return j if j >= 0 and parse_line_marker(lines[j]) is None else None


def fix_flow_order(text):
    """A block's sentence said BEFORE its [FLOW_NEXT] (the narration runs one block ahead): move the marker in front
    of that sentence. Returns (text, number moved)."""
    from eris.generate.script_checks import said_too_early
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
                    re.split(r"(?<=[.!?।॥])\s+", lines[before].strip())[-1],
                    lines[after].split(". ")[0] if after is not None else "", label, nxt):
                lines.insert(before, lines.pop(i))
                moved += 1
        i += 1
    return "\n".join(lines), moved


def complete_flows(text):
    """Draw every block a diagram leaves out: right before the sentence that already names it (after the last
    [FLOW_NEXT]), or with a short sentence of its own. Returns (text, number added)."""
    from eris.generate.script_checks import block_score
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
    """Remove each [VISUAL] or [FLOW] block a parser error points at, with the markers that use it (the narration
    stays). Returns (text, dropped error messages)."""
    lines, ids, dropped = text.splitlines(), [], []
    for err in errors:
        match = ERROR_LINE_RE.match(err)
        if match and match.group(2) in ("VISUAL", "FLOW") and int(match.group(1)) <= len(lines):
            marker = parse_line_marker(lines[int(match.group(1)) - 1])
            if marker and marker[0] == match.group(2):
                ids.append((marker[1].get("id", ""), marker[0]))
                dropped.append(err.splitlines()[0])
    for vid, block in dict.fromkeys(ids):
        text = drop_visual(text, vid, block=block)
    return text, dropped


FLOW_LEADS = ["Let me draw the next step on the board.", "Let me add the next block.", "Now the next step goes on the board."]
VISUAL_LEADS = ["Let me show you this on a graph.", "Let me put this on a graph you can play with.", "Let me show you how this looks on a graph."]
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m eris.generate.script_fixes <script.md>   (prints the flagged script)")
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        flagged, count = add_sync_flags(f.read())
    print(flagged)
    print(f"\n[sync] {count} flag(s) added", file=sys.stderr)


# ---------- pictures: their slide is on screen while the teacher talks about them ----------

PICTURE_WORD_RE = re.compile(r"\b(pictures?|photos?|photographs?|images?|paintings?|portraits?|maps?|charts?|graphs?|"
                             r"diagrams?|figures?|illustrations?|drawings?|flowcharts?|screenshots?|tables?|sketch(?:es)?|"
                             r"timelines?|posters?|cartoons?)\b", re.I)
# The same words as verbs name no picture: "now picture a ball", "imagine", "figure out", "map out", "chart a course".
PICTURE_VERB_RE = re.compile(r"\b(?:picture|imagine|visuali[sz]e)\s+(?:a|an|the|this|that|it|yourself|how|what|some|your|"
                             r"two|one|each|every|being)\b|\b(?:figure|map|chart|table)\s+(?:it\s+|them\s+)?out\b|"
                             r"\bchart\s+a\s+course\b", re.I)
SLIDE_NAMED_RE = re.compile(r"\bslide\s+(\d+)\b", re.I)
STAY_AFTER = {"NOTE", "NOTE_TITLE", "WRITE_CODE", "NOTE_HIGHLIGHT", "HIGHLIGHT", "LOOK_BACK", "FLOW_HIGHLIGHT",
              "SLIDE_HIGHLIGHT", "SLIDE_CIRCLE",
              "FLOW_NEXT", "VISUAL_SET", "RUN", "READ_OUTPUT", "OPEN_FILE"}
SUMMARY_RE = re.compile(r"^\s*(takeaway|in short|to sum up|so remember|remember)\b", re.I)
FRAMING_RE = re.compile(r"\b(opening|introduction|intro|welcome|recap|summary|review|closing|conclusion|wrap)", re.I)
SCREEN_OF = {  # which workspace a marker brings to the front
    "SLIDE": "slide", "SLIDE_HIGHLIGHT": "slide", "SLIDE_CIRCLE": "slide",
    "NOTE": "notebook", "NOTE_TITLE": "notebook", "NOTE_HIGHLIGHT": "notebook", "NEW_PAGE": "notebook", "LOOK_BACK": "notebook",
    "WRITE_CODE": "code", "HIGHLIGHT": "code", "RUN": "code", "READ_OUTPUT": "code", "OPEN_FILE": "code",
    "FLOW": "visual", "FLOW_NEXT": "visual", "FLOW_HIGHLIGHT": "visual", "OPEN_FLOW": "visual",
    "VISUAL": "visual", "VISUAL_SET": "visual", "OPEN_VISUAL": "visual",
}
_COMMON = set("""this that these those there their them they with from have will what when where which while about into
onto over under than then your yours ours look see shows show showing shown here just like also very more most some
each every only other such much many make made take picture image photo slide notice right left side front back
chart graph diagram figure painting drawing illustration timeline table map photograph flowchart poster cartoon
value number data year percent percentage total shows line bars""".split())  # picture and data words say nothing about WHICH picture


def _words(text):
    """Distinctive words of a text (4+ letters, not common), with a trailing plural 's' dropped."""
    out = set()
    for w in re.findall(r"[a-z]{4,}", text.lower()):
        w = w[:-1] if w.endswith("s") and len(w) > 4 else w
        if w not in _COMMON:
            out.add(w)
    return out


def _slide_pictures(pictures, slide_count=None, figs=None):
    """slide number -> (distinctive words, kind, can circle) for what a slide shows: its pictures (the pen can circle
    those), and the slide's own charts and diagrams drawn in the deck (shown, but there is no picture to circle)."""
    by_slide = {}
    for p in pictures or []:
        n = p.get("slide")
        if not n or not p.get("description") or (slide_count and n > slide_count):
            continue
        words, kind, _, nums = by_slide.get(n, (set(), p.get("kind") or "picture", True, set()))
        by_slide[n] = (words | _words(f"{p['description']} {p.get('text', '')}"), kind, True,
                       nums | _data_numbers(p.get("data", "")))
    for f in figs or []:
        m = SLIDE_NAMED_RE.fullmatch(str(f.get("ref", "")).strip())
        n = int(m.group(1)) if m else None
        if not n or n in by_slide or f.get("kind") not in ("graph", "diagram") or (slide_count and n > slide_count):
            continue  # a slide with a picture is matched by its picture
        by_slide[n] = (_words(f"{f['title']} {f['details']}"), "chart" if f["kind"] == "graph" else "diagram", False,
                       _data_numbers(f["details"]) if f["kind"] == "graph" else set())
    # Words in most of the deck's pictures are the topic's own vocabulary ("metal", "tool" in a machining lesson):
    # they say which lesson a sentence is from, not which picture, so only the rarer words can match a picture.
    if len(by_slide) >= 3:
        counts = {}
        for words, *_ in by_slide.values():
            for w in words:
                counts[w] = counts.get(w, 0) + 1
        common = {w for w, c in counts.items() if c > len(by_slide) / 2}
        by_slide = {n: (words - common, *rest) for n, (words, *rest) in by_slide.items()}
    return by_slide


MIN_SHARED_WORDS = 3  # two shared words ("world", "values") also match a different chart on the same topic
MIN_SHARED_NUMBERS = 2  # "it climbs to 61 percent around 2008": two of a chart's own values name the chart
NUM_RE = re.compile(r"\d[\d,.]*\d")
YEAR_RE = re.compile(r"1[5-9]\d\d|20\d\d")  # 2+ digits: single digits ("2 steps") say nothing about a chart


def _data_numbers(text):
    """Numbers as a teacher says them: "1,465" and "1465.0" are both 1465; "61.0" is 61."""
    out = set()
    for n in NUM_RE.findall(str(text)):
        n = n.replace(",", "").rstrip(".")
        out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def _mentioned_slide(line, by_slide, screen, current=None, how=None):
    """The slide whose picture this sentence talks about, or None. Named ("on slide 3"), or a picture word
    ("this painting", "the chart") plus MIN_SHARED_WORDS distinctive words from one picture's description or text, or
    MIN_SHARED_NUMBERS of a chart's own data values. While a
    diagram or graph is on the Visual board, "this graph" means the board, so only a named slide counts there."""
    named = [int(n) for n in SLIDE_NAMED_RE.findall(line) if int(n) in by_slide]
    if named:
        return named[0]
    if screen == "visual":
        return None
    # A chart is also named by its own values ("it climbs to 61 percent around 2008"), but not on years alone (many
    # charts share them), and not while the class reads a program's output in the terminal.
    nums = _data_numbers(line) if screen != "code" else set()
    if screen == "slide" and current in by_slide and nums & by_slide[current][3]:
        return current  # the chart on screen has this value: it is the one being explained ("25%" on the pie)
    by_values = max(((len(nums & v[3]), n) for n, v in by_slide.items() if v[3] and any(not YEAR_RE.fullmatch(x) for x in nums & v[3])),
                    default=(0, None))
    if by_values[0] >= MIN_SHARED_NUMBERS:
        if how is not None:
            how.append("values")
        return by_values[1]
    if not PICTURE_WORD_RE.search(PICTURE_VERB_RE.sub(" ", line)):
        return None
    said = _words(line)
    best, score = None, MIN_SHARED_WORDS - 1
    for n, (words, _, _, _) in by_slide.items():
        overlap = len(said & words)
        if overlap > score:
            best, score = n, overlap
    return best


def show_picture_slides(text, pictures, slide_count=None, figs=None):
    """Put a picture's slide on screen whenever the script talks about that picture, diagram or chart, if it isn't
    showing already: before the sentence that mentions it, and before a [FLOW]/[VISUAL] drawn from it (with a
    sentence, so the slide doesn't flash past). The first time a picture is explained while its slide shows, the
    teacher's pen circles it ([SLIDE_CIRCLE]). A takeaway or summary line only mentions a picture: no slide for
    it. Returns (text, number of slides and circles added)."""
    by_slide = _slide_pictures(pictures, slide_count, figs)
    if not by_slide:
        return text, 0
    lines, out, added, i = text.splitlines(), [], 0, 0
    screen, current = None, None  # the workspace in front, and the slide showing in the Slides view
    framing = False  # opening, recap and closing only mention pictures in passing: no slide for those
    circled = set()  # slides whose picture was circled while they show (a new [SLIDE] starts again)
    prev = None  # the marker right before the current line
    by_values_shown = set()  # charts brought up by their numbers in this section (each at most once)
    while i < len(lines):
        line = lines[i]
        marker = parse_line_marker(line)
        if marker is None:
            # right after something was written, highlighted or run, the sentence is about that: stay on it
            passing = framing or SUMMARY_RE.match(line) or prev in STAY_AFTER
            how = []
            n = _mentioned_slide(line, by_slide, screen, current, how) if line.strip() and not passing else None
            if n and how and (screen == "slide" or n in by_values_shown):
                n = None  # matched only by its numbers: never swap one slide for another, and once per section
            if n and how:
                by_values_shown.add(n)
            if n and (screen, current) != ("slide", n):
                out.append(f"[SLIDE n={n}]")
                screen, current, added, circled = "slide", n, added + 1, set()
            if n and n not in circled and by_slide[n][2]:
                out.append(f"[SLIDE_CIRCLE n={n}]")
                circled.add(n)
                added += 1
            out.append(line)
            if line.strip():
                prev = None
            i += 1
            continue
        name, args = marker
        prev = name
        end = _block_end(lines, i, name) if name in BLOCK_MARKERS else i
        end = len(lines) - 1 if end is None else end
        if name == "SECTION":
            framing = bool(FRAMING_RE.search(str(args.get("title", ""))))
            by_values_shown = set()
        if name in ("FLOW", "VISUAL"):
            src = SLIDE_NAMED_RE.search(str(args.get("from", "")))
            n = int(src.group(1)) if src else None
            if n in by_slide and (screen, current) != ("slide", n):
                kind = by_slide[n][1] if by_slide[n][1] in ("diagram", "flowchart", "chart", "table", "map") else "picture"
                then = "let me draw it on the board for you" if name == "FLOW" else "let me turn it into a graph you can explore"
                out += [f"[SLIDE n={n}]"] + ([f"[SLIDE_CIRCLE n={n}]"] if by_slide[n][2] else []) + \
                       [f"Here is the {kind} on this slide; {then}."]
                current, added, circled = n, added + 2, {n}
        if name == "SLIDE":
            circled = set()
        if name == "SLIDE_CIRCLE":
            circled.add(_slide_no(args))
        if name in SCREEN_OF:
            screen = SCREEN_OF[name]
            if screen == "slide":
                current = _slide_no(args) or current
        out += lines[i:end + 1]
        i = end + 1
    return "\n".join(out), added


def _slide_no(args):
    try:
        return int(args.get("n"))
    except (TypeError, ValueError):
        return None


# ---------- staging tidy-up: what a stager adds twice ----------

def _norm_sentence(s):
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split())


def _skip_slide_markers(lines, i):
    """Index after a [SLIDE] at i and the slide highlights and circles that follow it."""
    j = i + 1
    while j < len(lines) and (not lines[j].strip() or (parse_line_marker(lines[j]) or ("",))[0] in ("SLIDE_HIGHLIGHT", "SLIDE_CIRCLE")):
        j += 1
    return j


def _flashes(lines, i):
    """True if the [SLIDE] at i is followed (after its own highlights and circles) by another [SLIDE]."""
    j = _skip_slide_markers(lines, i)
    return j < len(lines) and (parse_line_marker(lines[j]) or ("",))[0] == "SLIDE"


def tidy_staging(text, lesson_sentences=()):
    """Remove what staging doubled: a [SLIDE] for the slide already on screen, a "Let me write..." lead right after
    a note, program or diagram whose lead was already said before it, and a lead after a [FLOW_NEXT] when the next
    sentence names the block anyway. Lines from the lesson itself are never removed. Returns (text, removed)."""
    from eris.generate.script_checks import ANNOUNCES_WRITING_RE  # script_checks imports format_fixes, not this module
    lesson = {_norm_sentence(s) for s in lesson_sentences}

    def added_lead(s):
        return (len(s.split()) <= 10 and ANNOUNCES_WRITING_RE.search(s) is not None
                and _norm_sentence(s) not in lesson)

    lines, out, removed, i = text.splitlines(), [], 0, 0
    screen, current, prev, announced, circled = None, None, None, False, set()
    board_from = None  # the slide the diagram or graph on the Visual board was drawn from
    while i < len(lines):
        line, marker = lines[i], parse_line_marker(lines[i])
        if marker:
            name, args = marker
            end = _block_end(lines, i, name) if name in BLOCK_MARKERS else i
            end = len(lines) - 1 if end is None else end
            if name == "SECTION":
                board_from = None
            if name in ("FLOW", "VISUAL"):
                src = SLIDE_NAMED_RE.search(str(args.get("from", "")))
                board_from = src.group(1) if src else None
            if name in ("SLIDE", "SLIDE_HIGHLIGHT") and screen == "visual" and board_from == str(args.get("n")):
                removed += 1  # the board is showing this slide's diagram or graph: no jumping back to the slide
                i = end + 1
                continue
            if name == "SLIDE" and screen == "slide" and str(current) == str(args.get("n")):
                removed += 1  # this slide is already on screen
                i = end + 1
                continue
            if name == "SLIDE" and _flashes(lines, i):
                removed += 1  # shown and replaced before anything is said about it: the class only sees a flash
                i = _skip_slide_markers(lines, i)
                continue
            if name == "SLIDE_HIGHLIGHT" and not (screen == "slide" and str(current) == str(args.get("n"))):
                out.append(f"[SLIDE n={args.get('n')}]")  # its slide wasn't on screen: nothing would light up
                screen, current, circled = "slide", args.get("n"), set()
            if name == "SLIDE_CIRCLE":
                if str(args.get("n")) in circled:
                    removed += 1  # already circled while this slide shows
                    i = end + 1
                    continue
                circled.add(str(args.get("n")))
            if name == "SLIDE":
                circled = set()
            if name in SCREEN_OF:
                screen = SCREEN_OF[name]
                if screen == "slide":
                    current = args.get("n")
            prev = name
            out += lines[i:end + 1]
            i = end + 1
            continue
        s = line.strip()
        if s and added_lead(s):
            nxt = next((ln for ln in lines[i + 1:] if ln.strip()), "")
            doubled = prev in ("NOTE", "WRITE_CODE", "FLOW", "NOTE_TITLE", "VISUAL") and announced
            before_named_block = prev == "FLOW_NEXT" and nxt and parse_line_marker(nxt) is None
            if doubled or before_named_block:
                removed += 1
                i += 1
                continue
        if s:
            announced, prev = bool(ANNOUNCES_WRITING_RE.search(s)), None
        out.append(line)
        i += 1
    return "\n".join(out), removed


def drop_empty_circles(text, pictures):
    """A pen circle needs a picture: one on a slide with no picture (e.g. a chart drawn in the deck) is removed.
    Returns (text, removed)."""
    have = {str(p["slide"]) for p in pictures or [] if p.get("slide")}
    out, removed = [], 0
    for line in text.splitlines():
        m = parse_line_marker(line)
        if m and m[0] == "SLIDE_CIRCLE" and str(m[1].get("n")) not in have:
            removed += 1
            continue
        out.append(line)
    return "\n".join(out), removed
