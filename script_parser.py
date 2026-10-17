"""Turn script text into segments (or a list of errors). No LLM here.

Rule: a marker sits on its own line, starts with "[", ends with "]" and the
first word inside is an UPPERCASE name. Every other line is narration.
"""

import json
import re
import sys
import textwrap

import config

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
}
INT_ARGS = ("n", "s")
# Markers with a body that runs until [/NAME]. The body is stored in this arg.
BLOCK_MARKERS = {"WRITE_CODE": "code", "NOTE": "text"}

NAME_RE = re.compile(r"^/?[A-Z][A-Z_]*$")
# key=value, key="value with spaces", or key='value with "double quotes"' (code often has them)
# Inside quotes, a backslash escapes the next character: text="print(\"hi\")" -> print("hi").
ARG_RE = re.compile(r"""(\w+)=("((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|\S+)""")
UNESCAPE_RE = re.compile(r"\\(.)")
LINES_RE = re.compile(r"^(\d+)(?:-(\d+))?$")
RUN_RE = re.compile(r"^python (\S+\.py)$")


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
      {"files": {name: code}, "notebook": [line, ...], "has_run": bool}. Quotes are checked against it.
    """
    segments, errors = [], []
    board = board or {}
    # files: name -> its code lines; notebook: every line written in the notebook so far
    state = {"files": {n: c.splitlines() for n, c in board.get("files", {}).items()},
             "has_run": bool(board.get("has_run")), "slide_count": slide_count,
             "notebook": list(board.get("notebook", []))}
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
            if line.strip():
                say_lines.append(line.strip())
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
        segment = {"kind": "action", "name": name, "args": args}
        if name in BLOCK_MARKERS:
            # Collect the body even when invalid, so it isn't read as narration.
            block = {"name": name, "lines": [], "segment": segment, "start": line_no, "valid": valid}
        elif valid:
            segments.append(segment)

    end_say()
    if block is not None:
        errors.append(f"line {block['start']}: [{block['name']}] never closed with [/{block['name']}]")

    if not require_doubt_check:  # e.g. a short doubt answer, not a whole lecture
        return segments, errors
    doubt_checks = [s for s in segments if s.get("name") == "DOUBT_CHECK"]
    if not doubt_checks:
        errors.append("script has no [DOUBT_CHECK] markers")
    elif segments[-1].get("name") != "DOUBT_CHECK":
        errors.append("script must end with [DOUBT_CHECK] as the last line")
    return segments, errors


def estimate_minutes(segments):
    words = sum(len(s["text"].split()) for s in segments if s["kind"] == "say")
    runs = sum(1 for s in segments if s.get("name") == "RUN")
    pause_s = sum(s["args"]["s"] for s in segments if s.get("name") == "PAUSE")
    note_chars = sum(len(s["args"]["text"]) for s in segments
                     if s.get("name") in ("NOTE", "NOTE_TITLE", "WRITE"))
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
