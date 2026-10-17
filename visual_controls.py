"""The controls of an interactive visual, read from its description. No LLM here.

A [VISUAL] block ends with a line like
    controls: step (button), size (slider 1-10), mode (choice fast/slow), labels (toggle)
The parser checks every [VISUAL_SET] against these controls, the builder must implement exactly
these, and the class screen draws them as a panel the teacher (and the students) can use.
"""

import re

CONTROLS_LINE_RE = re.compile(r"^\s*controls?\s*:\s*(.*)$", re.I)
ITEM_RE = re.compile(r"^([A-Za-z][\w-]*)\s*\(\s*(button|slider|toggle|choice)\b\s*([^)]*)\)$", re.I)
RANGE_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*(?:-|to|\.\.)\s*(-?\d+(?:\.\d+)?)(?:\s+step\s+(\d+(?:\.\d+)?))?$", re.I)
VISUAL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
CONTROLS_HELP = ('end the description with a line like: controls: step (button), size (slider 1-10), '
                 'mode (choice fast/slow), labels (toggle)')
TRUE_WORDS, FALSE_WORDS = {"true", "on", "yes", "1"}, {"false", "off", "no", "0"}


def _number(text):
    value = float(text)
    return int(value) if value.is_integer() else value


def _split_items(text):
    """Split on commas that are not inside parentheses."""
    items, depth, cur = [], 0, ""
    for ch in text:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            items.append(cur)
            cur = ""
        else:
            cur += ch
    return [i.strip() for i in items + [cur] if i.strip()]


def parse_controls(body):
    """Return (description, controls, problems) for a [VISUAL] body."""
    desc, controls, problems = [], [], []
    for line in body.splitlines():
        match = CONTROLS_LINE_RE.match(line)
        if not match:
            desc.append(line)
            continue
        for item in _split_items(match.group(1)):
            control, problem = _parse_item(item)
            if problem:
                problems.append(problem)
            elif any(c["name"] == control["name"] for c in controls):
                problems.append(f"control '{control['name']}' is listed twice")
            else:
                controls.append(control)
    description = "\n".join(desc).strip()
    if not description:
        problems.append("describe what the visual shows (one to four sentences) before the controls line")
    if not controls and not problems:
        problems.append(f"the visual has no controls; {CONTROLS_HELP}")
    return description, controls, problems


def _parse_item(item):
    match = ITEM_RE.match(item.strip())
    if not match:
        return None, f"cannot read the control '{item}'; write it as name (button|slider 1-10|toggle|choice a/b)"
    name, kind, extra = match.group(1).lower(), match.group(2).lower(), match.group(3).strip()
    control = {"name": name, "type": kind, "label": name.replace("_", " ").replace("-", " ").capitalize()}
    if kind == "slider":
        rng = RANGE_RE.match(extra)
        if not rng:
            return None, f"slider '{name}' needs a range like (slider 1-10)"
        lo, hi = _number(rng.group(1)), _number(rng.group(2))
        if lo >= hi:
            return None, f"slider '{name}': the first number must be smaller than the second"
        step = _number(rng.group(3)) if rng.group(3) else (1 if isinstance(lo, int) and isinstance(hi, int) else round((hi - lo) / 20, 4))
        control.update({"min": lo, "max": hi, "step": step})
    elif kind == "choice":
        options = [o.strip() for o in re.split(r"[/|]", extra) if o.strip()]
        if len(options) < 2:
            return None, f"choice '{name}' needs two or more options like (choice fast/slow)"
        control["options"] = options
    return control, None


def coerce_value(control, raw):
    """The value a [VISUAL_SET] gives a control, or (None, problem)."""
    kind, name = control["type"], control["name"]
    if kind == "button":
        return None, None  # pressing it; a value is ignored
    if raw is None or str(raw).strip() == "":
        return None, f"control '{name}' is a {kind}: give value=..."
    raw = str(raw).strip()
    if kind == "slider":
        try:
            value = _number(raw)
        except ValueError:
            return None, f"slider '{name}' needs a number, got '{raw}'"
        if not control["min"] <= value <= control["max"]:
            return None, f"slider '{name}' goes from {control['min']} to {control['max']}, got {value}"
        return value, None
    if kind == "toggle":
        if raw.lower() in TRUE_WORDS:
            return True, None
        if raw.lower() in FALSE_WORDS:
            return False, None
        return None, f"toggle '{name}' needs value=on or value=off, got '{raw}'"
    for option in control["options"]:
        if option.lower() == raw.lower():
            return option, None
    return None, f"choice '{name}' has the options {' / '.join(control['options'])}, got '{raw}'"


def describe_control(control):
    """One readable line, e.g. 'size: slider 1-10' (for prompts and the board)."""
    kind = control["type"]
    if kind == "slider":
        step = "" if control["step"] == 1 else f" step {control['step']}"
        return f"{control['name']}: slider {control['min']}-{control['max']}{step}"
    if kind == "choice":
        return f"{control['name']}: choice {' / '.join(control['options'])}"
    return f"{control['name']}: {kind}"
