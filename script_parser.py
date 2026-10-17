"""Turn script text into segments (or a list of errors). No LLM here.

Rule: a marker sits on its own line, starts with "[", ends with "]" and the
first word inside is an UPPERCASE name. Every other line is narration.
"""

import json
import re
import sys
import textwrap

import config
from visual_controls import VISUAL_ID_RE, coerce_value, parse_controls

# Marker name -> required args.
MARKERS = {
    "SECTION": ["title"],
    "SLIDE": ["n"],
    "SLIDE_HIGHLIGHT": ["n", "text"],
    "WRITE_CODE": ["file"],
    "HIGHLIGHT": ["file"],  # plus text="..." (preferred) or lines="3-5"
    "RUN": ["cmd"],
    "READ_OUTPUT": [],
    "WRITE": ["text"],
    "NOTE": [],
    "NOTE_TITLE": ["text"],
    "NOTE_HIGHLIGHT": ["text"],
    "PAUSE": ["s"],
    # Pointing back at what is already on the board (mostly used in doubt answers):
    "LOOK_BACK": ["text"],   # scroll the notebook to a line written earlier and highlight it
    "OPEN_FILE": ["file"],   # bring an earlier program back into the editor
    "NEW_PAGE": ["title"],   # start a fresh notebook page with this heading
    "DOUBT_CHECK": [],
    # Interactive visuals (built by a model from the description; see visual_builder.py):
    "VISUAL": ["id", "title"],          # body: what to show, then a "controls: ..." line
    "VISUAL_SET": ["id", "control"],    # move a control (value=...; a button needs none)
    "OPEN_VISUAL": ["id"],              # bring an earlier visual back on screen
}
INT_ARGS = ("n", "s")
# Level 2 sync: these actions may run while the narration right after them is spoken
# (while_speaking=true). RUN, READ_OUTPUT, PAUSE, DOUBT_CHECK and SECTION must happen in order.
WHILE_SPEAKING_OK = {"WRITE_CODE", "NOTE", "NOTE_TITLE", "WRITE", "NOTE_HIGHLIGHT", "HIGHLIGHT",
                     "SLIDE", "SLIDE_HIGHLIGHT", "NEW_PAGE", "OPEN_FILE", "LOOK_BACK",
                     "VISUAL", "VISUAL_SET", "OPEN_VISUAL"}
# Markers with a body that runs until [/NAME]. The body is stored in this arg.
BLOCK_MARKERS = {"WRITE_CODE": "code", "NOTE": "text", "VISUAL": "brief"}

NAME_RE = re.compile(r"^/?[A-Z][A-Z_]*$")
# key=value, key="value with spaces", or key='value with "double quotes"' (code often has them)
# Inside quotes, a backslash escapes the next character: text="print(\"hi\")" -> print("hi").
ARG_RE = re.compile(r"""(\w+)=("((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|\S+)""")
UNESCAPE_RE = re.compile(r"\\(.)")
LINES_RE = re.compile(r"^(\d+)(?:-(\d+))?$")
RUN_RE = re.compile(r"^python (\S+\.py)$")
# Markdown that models put in narration; it would be read out or shown as symbols.
BULLET_RE = re.compile(r"^(?:[-*•]|#{1,6})\s+")
EMPHASIS_RE = re.compile(r"\*\*(.+?)\*\*|(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])")
CODE_SPAN_RE = re.compile(r"(`[^`]*`)")


def clean_narration(line):
    """One narration line without markdown: no bullets or headings, no **bold** or *italic* marks.
    Backticks stay (the class screen shows them as code; TTS drops them)."""
    line = BULLET_RE.sub("", line.strip())
    parts = CODE_SPAN_RE.split(line)  # never touch code inside backticks, e.g. `**kwargs`
    return "".join(p if p.startswith("`") else EMPHASIS_RE.sub(lambda m: m.group(1) or m.group(2), p)
                   for p in parts)


def parse_line_marker(line):
    """Return (name, args) if the line is a marker, else None."""
    stripped = line.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return None
    inner = stripped[1:-1].strip()
    if not inner:
        return None
    name, _, rest = inner.partition(" ")
    if not NAME_RE.match(name):
        return None
    args = {}
    for match in ARG_RE.finditer(rest):
        key, raw, double, single = match.groups()
        quoted = double if double is not None else single
        args[key] = UNESCAPE_RE.sub(r"\1", quoted) if quoted is not None else raw
    # Models often write [SLIDE 3] or [SECTION Intro] instead of n=3 / title="Intro".
    # For markers with exactly one required arg, accept that bare value.
    required = MARKERS.get(name, [])
    if not args and rest.strip() and len(required) == 1:
        args[required[0]] = rest.strip().strip('"')
    return name, args


def _check_marker(name, args, line_no, state, errors):
    """Validate one marker against the current state. Appends to `errors`."""
    def err(msg):
        errors.append(f"line {line_no}: [{name}] {msg}")

    if "while_speaking" in args:
        value = str(args["while_speaking"]).lower()
        if name not in WHILE_SPEAKING_OK:
            err("while_speaking is not allowed here; it must happen in silence and in order")
            return False
        if value not in ("true", "false"):
            err(f"while_speaking must be true or false, got '{args['while_speaking']}'")
            return False
        if value == "true":
            args["while_speaking"] = True
        else:
            del args["while_speaking"]

    for key in MARKERS[name]:
        if not str(args.get(key, "")).strip():
            usage = " ".join(f'{k}="..."' if k not in INT_ARGS else f"{k}=1" for k in MARKERS[name])
            err(f"missing required arg '{key}'. Write it like: [{name} {usage}]")
            return False
    for key in INT_ARGS:
        if key in MARKERS[name]:
            try:
                args[key] = int(args[key])
            except ValueError:
                err(f"'{key}' must be a whole number, got '{args[key]}'")
                return False

    if "n" in MARKERS[name] and state["slide_count"] and not 1 <= args["n"] <= state["slide_count"]:
        err(f"slide {args['n']} does not exist; the deck has {state['slide_count']} slide(s)")
        return False

    if name == "WRITE_CODE" and not args["file"].endswith(".py"):
        err(f"file must end in .py, got '{args['file']}'")
        return False

    if name == "HIGHLIGHT":
        if args["file"] not in state["files"]:
            err(f"file '{args['file']}' was not written with WRITE_CODE before this")
            return False
        lines, problem = _resolve_highlight(args, state["files"][args["file"]])
        if problem:
            err(problem)
            return False
        args["lines"] = lines  # the player always gets line numbers

    if name == "RUN":
        match = RUN_RE.match(args["cmd"])
        if not match:
            err(f"cmd must be exactly 'python <file>.py', got '{args['cmd']}'")
            return False
        if match.group(1) not in state["files"]:
            err(f"file '{match.group(1)}' was not written with WRITE_CODE before this")
            return False
        state["has_run"] = True

    if name in ("NOTE_HIGHLIGHT", "LOOK_BACK"):
        # Quote the text instead of pointing at a line: models quote well and count badly.
        if not any(args["text"].lower() in line.lower() for line in state["notebook"]):
            err(f"text '{args['text']}' is not written in the notebook yet; quote words from an earlier [NOTE]")
            return False

    if name == "VISUAL":
        if not VISUAL_ID_RE.match(args["id"]):
            err(f"id must be short lowercase letters, digits or dashes (like id=\"list-growth\"), got '{args['id']}'")
            return False
        if args["id"] in state["visuals"]:
            err(f"a visual with id '{args['id']}' is already on the board; use a new id, or drive it with [VISUAL_SET]")
            return False

    if name in ("VISUAL_SET", "OPEN_VISUAL"):
        controls = state["visuals"].get(args["id"])
        if controls is None:
            known = ", ".join(state["visuals"]) or "none yet"
            err(f"visual '{args['id']}' is not on the board (visuals: {known}); create it with a [VISUAL] block first")
            return False
        if name == "VISUAL_SET":
            control = next((c for c in controls if c["name"] == str(args["control"]).lower()), None)
            if control is None:
                err(f"visual '{args['id']}' has no control '{args['control']}'; its controls are "
                    f"{', '.join(c['name'] for c in controls) or 'none'}")
                return False
            value, problem = coerce_value(control, args.get("value"))
            if problem:
                err(problem)
                return False
            args["control"] = control["name"]
            if control["type"] == "button":
                args.pop("value", None)
            else:
                args["value"] = value

    if name == "OPEN_FILE" and args["file"] not in state["files"]:
        err(f"file '{args['file']}' is not on the board")
        return False

    if name in ("NOTE_TITLE", "WRITE", "NEW_PAGE"):
        state["notebook"].append(args.get("text") or args["title"])

    if name == "READ_OUTPUT" and not state["has_run"]:
        err("READ_OUTPUT comes before any RUN")
        return False
    return True


def _norm(text):
    """Compare code ignoring differences in spacing."""
    return " ".join(text.split())


def _numbered(code_lines):
    return "\n".join(f"  {n:>3} | {line}" for n, line in enumerate(code_lines, start=1))


def _find_line(code_lines, text, start=1):
    """Line numbers (1-based, >= start) whose code contains `text`."""
    want = _norm(text)
    return [n for n, line in enumerate(code_lines, start=1) if n >= start and want and want in _norm(line)]


def _resolve_highlight(args, code_lines):
    """Turn text="..." (and optional to="...") or lines="3-5" into a "N" / "N-M" string.

    Returns (lines, problem). Quoting is preferred: models quote code well and count lines badly.
    """
    name, count = args["file"], len(code_lines)
    if args.get("text", "").strip():
        hits = _find_line(code_lines, args["text"])
        if not hits:
            return None, (f"text '{args['text']}' is not in {name}. Copy it exactly from one line:\n"
                          + _numbered(code_lines))
        if len(hits) > 1:
            return None, (f"text '{args['text']}' matches lines {', '.join(map(str, hits))} of {name}; "
                          "quote more of the line so it matches only one")
        first = last = hits[0]
        if args.get("to", "").strip():
            ends = _find_line(code_lines, args["to"], start=first)
            if not ends:
                return None, (f"to='{args['to']}' is not in {name} at or after line {first}:\n"
                              + _numbered(code_lines))
            last = ends[0]
        return (str(first) if first == last else f"{first}-{last}"), None

    if not args.get("lines", "").strip():
        return None, f'needs text="..." (the code to highlight, copied from {name}) or lines="3-5"'
    match = LINES_RE.match(args["lines"])
    if not match:
        return None, f"lines must look like 3 or 3-5, got '{args['lines']}'"
    first, last = int(match.group(1)), int(match.group(2) or match.group(1))
    if first > last:
        return None, f"start line {first} is greater than end line {last}"
    if first < 1 or last > count:
        return None, f"lines {args['lines']} out of range; {name} has {count} line(s):\n" + _numbered(code_lines)
    return args["lines"], None


def _close_block(block, line_no, state, segments, errors):
    """Finish a WRITE_CODE or NOTE body and add its segment."""
    if not block["valid"]:
        return
    args = block["segment"]["args"]
    if block["name"] == "WRITE_CODE":
        code = "\n".join(block["lines"]).strip("\n")
        args["code"] = code
        state["files"][args["file"]] = code.splitlines()
    elif block["name"] == "VISUAL":
        brief, controls, problems = parse_controls(textwrap.dedent("\n".join(block["lines"])))
        if problems:
            errors.extend(f"line {block['start']}: [VISUAL] {p}" for p in problems)
            return
        args["brief"], args["controls"] = brief, controls
        state["visuals"][args["id"]] = controls
    else:
        # Keep relative indentation (a syntax shape needs it); drop the block's common indent.
        lines = [ln.rstrip() for ln in textwrap.dedent("\n".join(block["lines"])).splitlines()]
        text = "\n".join(lines).strip("\n")
        if not text:
            errors.append(f"line {block['start']}: [NOTE] is empty; write the keywords or example inside it")
            return
        args["text"] = text
        state["notebook"].extend(text.splitlines())
    segments.append(block["segment"])


def parse_script(text, slide_count=None, require_doubt_check=True, board=None):
    """Return (segments, errors). Collects every error instead of stopping.

    slide_count: number of slides in the deck; if given, SLIDE n is range-checked.
    require_doubt_check: lecture scripts must contain and end with [DOUBT_CHECK].
    board: what is already on the class screen (a doubt answer mid-lecture), as
      {"files": {name: code}, "notebook": [line, ...], "has_run": bool, "visuals": {id: {"controls": [...]}}}.
      Quotes, files and visual controls are checked against it.
    """
    segments, errors = [], []
    board = board or {}
    # files: name -> its code lines; notebook: every line written in the notebook so far
    state = {"files": {n: c.splitlines() for n, c in board.get("files", {}).items()},
             "has_run": bool(board.get("has_run")), "slide_count": slide_count,
             "notebook": list(board.get("notebook", [])),
             "visuals": {v: d["controls"] for v, d in board.get("visuals", {}).items()}}
    say_lines = []
    block = None  # dict while inside a WRITE_CODE or NOTE body

    def end_say():
        if say_lines:
            segments.append({"kind": "say", "text": " ".join(say_lines)})
            say_lines.clear()

    lines = text.splitlines()
    for line_no, line in enumerate(lines, start=1):
        if block is not None:
            if line.strip() == f"[/{block['name']}]":
                _close_block(block, line_no, state, segments, errors)
                block = None
            else:
                block["lines"].append(line)
            continue

        marker = parse_line_marker(line)
        if marker is None:
            if line.strip() and clean_narration(line):
                say_lines.append(clean_narration(line))
            else:
                end_say()
            continue

        end_say()
        name, args = marker
        if name.startswith("/") and name[1:] in BLOCK_MARKERS:
            errors.append(f"line {line_no}: [{name}] without a matching [{name[1:]}]")
            continue
        if name.startswith("/") and name[1:] in MARKERS:
            continue  # Models sometimes "close" markers like [/HIGHLIGHT]; only block markers have a body.
        if name not in MARKERS:
            errors.append(f"line {line_no}: unknown marker [{name}]")
            continue
        valid = _check_marker(name, args, line_no, state, errors)
        segment = {"kind": "action", "name": name, "args": args, "_line": line_no}
        if name in BLOCK_MARKERS:
            # Collect the body even when invalid, so it isn't read as narration.
            block = {"name": name, "lines": [], "segment": segment, "start": line_no, "valid": valid}
        elif valid:
            segments.append(segment)

    end_say()
    if block is not None:
        errors.append(f"line {block['start']}: [{block['name']}] never closed with [/{block['name']}]")

    for i, seg in enumerate(segments):
        line_no = seg.pop("_line", None)
        if seg.get("args", {}).get("while_speaking"):
            after = segments[i + 1] if i + 1 < len(segments) else None
            if not after or after["kind"] != "say":
                errors.append(f"line {line_no}: [{seg['name']}] while_speaking needs narration right after it")
    segments = split_spoken_while_writing(segments)

    if not require_doubt_check:  # e.g. a short doubt answer, not a whole lecture
        return segments, errors
    doubt_checks = [s for s in segments if s.get("name") == "DOUBT_CHECK"]
    if not doubt_checks:
        errors.append("script has no [DOUBT_CHECK] markers")
    elif segments[-1].get("name") != "DOUBT_CHECK":
        errors.append("script must end with [DOUBT_CHECK] as the last line")
    return segments, errors


SPOKEN_WHILE_WRITING_MIN_WORDS = 6  # a shorter first sentence takes the next one along


def split_spoken_while_writing(segments):
    """After a while_speaking note or program, only the first sentence (what is being written) is spoken
    while it is written; the explanation after it becomes its own segment, spoken once the writing is done.
    Without this, every narration line up to the next blank line would play over the writing."""
    out = []
    for i, seg in enumerate(segments):
        prev = segments[i - 1] if i else None
        if seg["kind"] == "say" and prev and prev.get("args", {}).get("while_speaking"):
            sentences = re.split(r"(?<=[.!?])\s+", seg["text"].strip())
            take = 1
            while take < len(sentences) and len(" ".join(sentences[:take]).split()) < SPOKEN_WHILE_WRITING_MIN_WORDS:
                take += 1
            if take < len(sentences):
                out.append({"kind": "say", "text": " ".join(sentences[:take])})
                out.append({"kind": "say", "text": " ".join(sentences[take:])})
                continue
        out.append(seg)
    return out


def estimate_minutes(segments):
    words = sum(len(s["text"].split()) for s in segments if s["kind"] == "say")
    runs = sum(1 for s in segments if s.get("name") == "RUN")
    pause_s = sum(s["args"]["s"] for s in segments if s.get("name") == "PAUSE")
    # Notes written while_speaking overlap the narration, so they add no time.
    note_chars = sum(len(s["args"]["text"]) for s in segments
                     if s.get("name") in ("NOTE", "NOTE_TITLE", "WRITE") and not s["args"].get("while_speaking"))
    write_min = note_chars / config.NOTE_CHARS_PER_S / 60
    return round(words / config.SPEAKING_WPM + runs * config.RUN_MIN_EACH + pause_s / 60 + write_min, 1)


def word_budget(duration_min=None):
    """Narration words that fit the lecture, leaving time for doubts, notebook writing and ~3 RUNs."""
    duration = duration_min or config.LECTURE_DURATION_MIN
    talk_min = duration * (1 - config.DOUBT_TIME_SHARE - config.NOTE_TIME_SHARE) - 3 * config.RUN_MIN_EACH
    return max(int(talk_min * config.SPEAKING_WPM), 100)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python script_parser.py <script.md>")
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        segs, errs = parse_script(f.read())
    if errs:
        print(f"{len(errs)} error(s):")
        for e in errs:
            print("  " + e)
        sys.exit(1)
    print(json.dumps(segs, indent=2, ensure_ascii=False))
    print(f"\nOK: {len(segs)} segments, about {estimate_minutes(segs)} min")
