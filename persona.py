"""Parse and validate persona.md.

Format:
    # Heading
    Key: value
    (lines that are not "Key: value" are added to the previous key's value)
"""

import re
import sys

REQUIRED = {
    "Teacher": ["Name", "Subject", "Class"],
    "Absence Note": ["Reason", "Message to class"],
    "Teaching Style": ["Tone", "Pace", "Language", "Habits"],
    "Lecture Structure": ["Order", "Must cover", "Avoid"],
    "Next Class": ["Topic", "Prep"],
}

KEY_LINE = re.compile(r"^([A-Za-z][A-Za-z ]*?)\s*:\s*(.*)$")


def _canonical(name, choices):
    """Return the matching name from `choices` (case-insensitive), else `name`."""
    for choice in choices:
        if choice.lower() == name.lower():
            return choice
    return name


def parse_persona(path):
    """Read persona.md into {heading: {key: value}}. Raises ValueError listing every problem."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    persona = {}
    heading = None
    last_key = None
    for line in lines:
        stripped = line.strip()
        if line.startswith("# "):
            heading = _canonical(line[2:].strip(), REQUIRED)
            persona.setdefault(heading, {})
            last_key = None
            continue
        if heading is None or not stripped:
            continue
        match = KEY_LINE.match(stripped)
        if match:
            last_key = _canonical(match.group(1).strip(), REQUIRED.get(heading, []))
            persona[heading][last_key] = match.group(2).strip()
        elif last_key:
            # Continuation line, e.g. a bullet under "Must cover:".
            joined = (persona[heading][last_key] + "\n" + stripped).strip()
            persona[heading][last_key] = joined

    missing = []
    for section, keys in REQUIRED.items():
        if section not in persona:
            missing.append(f"heading '# {section}'")
            continue
        for key in keys:
            if not persona[section].get(key, "").strip():
                missing.append(f"'{key}' under '# {section}'")
    if missing:
        raise ValueError("persona.md is missing or has empty: " + "; ".join(missing))
    return persona


def load_persona_or_exit(path):
    """parse_persona for setup code: print a clear message and exit on any problem."""
    try:
        return parse_persona(path)
    except FileNotFoundError:
        print(f"[persona] Not found: {path}. Copy data/example/persona.md there and fill it in.")
    except ValueError as e:
        print(f"[persona] {e}")
    sys.exit(1)


def persona_to_markdown(persona):
    """Inverse of parse_persona: {heading: {key: value}} -> persona.md text."""
    parts = []
    for section, keys in REQUIRED.items():
        parts.append(f"# {section}")
        for key in keys:
            value = str(persona.get(section, {}).get(key, "")).strip()
            value = "; ".join(line.strip() for line in value.splitlines() if line.strip())  # one line per key
            parts.append(f"{key}: {value}")
        parts.append("")
    return "\n".join(parts)


def persona_to_text(persona):
    """Readable block for prompts."""
    parts = []
    for section, fields in persona.items():
        parts.append(f"## {section}")
        for key, value in fields.items():
            parts.append(f"- {key}: {value}")
        parts.append("")
    return "\n".join(parts).strip()


if __name__ == "__main__":
    import json

    target = sys.argv[1] if len(sys.argv) > 1 else "data/example/persona.md"
    print(json.dumps(load_persona_or_exit(target), indent=2, ensure_ascii=False))
