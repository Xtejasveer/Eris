"""Sketch rows: small drawings in the notebook, one row at a time, like a teacher sketching on the board.

[SKETCH_ROW items="box:Continuous chip | arrow:ductile metal | result:Long ribbon | tick"]

A row is a few simple parts, left to right, separated by "|". The player draws each part with the pen (boxes and
arrows stroke by stroke) and numbers the rows of one sketch 1, 2, 3. The writer picks parts; code lays them out.

  box:<words>     a box with words (the things being compared or the steps)
  result:<words>  a box in the result colour (what comes out; an arrow is drawn before it if the row has none)
  good:<words>    a green box (the right one, the one to keep)
  text:<words>    words written without a box
  arrow           an arrow to the next part; arrow:<words> writes a 1-3 word label over it
  tick / cross    a tick or a cross mark
  icon:<name>     a small drawing: stack, network, gear, person, cycle, bulb
"""

import re

ICONS = ("stack", "network", "gear", "person", "cycle", "bulb")
WORD_KINDS = ("box", "result", "good", "text")
MARK_KINDS = ("tick", "cross")
MAX_ITEMS = 7
MAX_WORDS_CHARS = 32
MAX_ARROW_WORDS = 3   # an arrow's label is a word or two over the line, never a list
MAX_ARROW_CHARS = 20
ITEM_RE = re.compile(r"^\s*([a-z]+)\s*(?::\s*(.*?))?\s*$", re.I)


def parse_items(spec):
    """("box:A | arrow | result:B") -> ([{"kind", "text"}], problems)."""
    items, problems = [], []
    for raw in [p for p in str(spec).split("|") if p.strip()]:
        m = ITEM_RE.match(raw)
        kind, text = (m.group(1).lower(), (m.group(2) or "").strip()) if m else ("", "")
        if kind in WORD_KINDS:
            if not text:
                problems.append(f"'{raw.strip()}' needs words after the colon, like {kind}:Chip")
                continue
            if len(text) > MAX_WORDS_CHARS:
                problems.append(f"'{text}' is too long for a sketch ({len(text)} characters, at most "
                                f"{MAX_WORDS_CHARS}); keep 1-4 words and say the rest")
                continue
        elif kind == "arrow":
            if len(text) > MAX_ARROW_CHARS or len(text.split()) > MAX_ARROW_WORDS or "," in text:
                problems.append(f"the arrow label '{text}' is too long; an arrow label is 1-3 words (put a list in a "
                                f"box, or say it)")
                continue
        elif kind in MARK_KINDS:
            text = ""
        elif kind == "icon":
            if text.lower() not in ICONS:
                problems.append(f"icon '{text}' is not one of {', '.join(ICONS)}")
                continue
            text = text.lower()
        else:
            problems.append(f"'{raw.strip()}' is not a sketch part; use box:, result:, good:, text:, arrow, tick, "
                            f"cross or icon:")
            continue
        if kind == "result" and items and items[-1]["kind"] in WORD_KINDS + ("icon",):
            items.append({"kind": "arrow", "text": ""})  # a result follows from what comes before it
        items.append({"kind": kind, "text": text})
    if not problems and len(items) < 2:
        problems.append("a sketch row needs at least 2 parts, e.g. items=\"box:Input | arrow | result:Output\"")
    if len(items) > MAX_ITEMS:
        problems.append(f"a sketch row has at most {MAX_ITEMS} parts; split it into two rows")
    return items, problems


def plain_long_arrows(spec):
    """The row with every over-long arrow label dropped (a plain arrow stays): what is said explains it. Scripts and
    doubt answers keep their sketch this way; the lesson writer is told the rule instead."""
    def fix(part):
        m = ITEM_RE.match(part)
        if m and m.group(1).lower() == "arrow" and m.group(2):
            text = m.group(2).strip()
            if len(text) > MAX_ARROW_CHARS or len(text.split()) > MAX_ARROW_WORDS or "," in text:
                return " arrow "
        return part
    return "|".join(fix(p) for p in str(spec).split("|"))


def row_words(items):
    """The words in a row, one per part: they are what [LOOK_BACK] and [NOTE_HIGHLIGHT] can quote."""
    return [i["text"] for i in items if i["text"] and i["kind"] != "icon"]


def row_line(items):
    """A row as one line of text (the terminal class, the doubt agent's view of the notebook)."""
    marks = {"tick": "✓", "cross": "✗"}
    out = []
    for i in items:
        if i["kind"] == "arrow":
            out.append(f"→ {i['text']} →" if i["text"] else "→")
        elif i["kind"] in marks:
            out.append(marks[i["kind"]])
        elif i["kind"] == "icon":
            out.append(f"({i['text']})")
        else:
            out.append(f"[{i['text']}]" if i["kind"] != "text" else i["text"])
    return " ".join(out)
