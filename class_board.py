"""What is on the class screen at a point in the lecture, rebuilt from segments. No LLM here.

The doubt agent reads it (read_board tool) and its answers are checked against it, so a
[LOOK_BACK], [OPEN_FILE] or [HIGHLIGHT] in an answer can only point at something really shown.
"""


def new_board():
    return {"section": "Introduction", "files": {}, "notebook": [], "pages": [["Lecture", []]],
            "slides_shown": [], "current_slide": None, "has_run": False, "last_output": ""}


def _page_lines(board, section):
    """The current notebook page's list for `section` (a page holds [section, lines] groups)."""
    groups = board["pages"][-1][1]
    if not groups or groups[-1][0] != section:
        groups.append([section, []])
    return groups[-1][1]


def add_segments(board, segments):
    """Apply played segments to the board (lecture segments or a doubt answer)."""
    for seg in segments:
        args = seg.get("args", {})
        name = seg.get("name")
        if name == "SECTION":
            board["section"] = args["title"]
        elif name == "WRITE_CODE":
            board["files"][args["file"]] = args["code"]
        elif name == "RUN":
            board["has_run"] = True
            board["last_output"] = seg.get("expected_output", "")
        elif name == "SLIDE":
            board["current_slide"] = args["n"]
            board["slides_shown"].append([board["section"], args["n"]])
        elif name == "NEW_PAGE":
            board["pages"].append([args["title"], []])
            board["notebook"].append(args["title"])
            _page_lines(board, board["section"]).append("## " + args["title"])
        elif name in ("NOTE", "WRITE", "NOTE_TITLE"):
            lines = args["text"].splitlines()
            board["notebook"].extend(lines)
            prefix = "## " if name == "NOTE_TITLE" else ""
            _page_lines(board, board["section"]).extend(prefix + ln for ln in lines)
    return board


def rebuild(segments, upto):
    """The board after the first `upto` segments of the approved script."""
    return add_segments(new_board(), segments[:max(0, upto)])


def describe(board, slides=None):
    """Readable board for the doubt agent: notebook by page and section, code, slides shown."""
    slides = slides or {}
    parts = ["# NOTEBOOK (quote a line exactly in [LOOK_BACK text=\"...\"] to scroll back to it)"]
    for title, groups in board["pages"]:
        parts.append(f"\n## Page: {title}")
        for section, lines in groups:
            parts.append(f"### Section: {section}")
            parts.extend(f"  {ln}" for ln in lines if ln.strip())
    parts.append("\n# CODE ON THE BOARD (use [OPEN_FILE file=\"...\"] then [HIGHLIGHT ...] to show it again)")
    for name, code in board["files"].items():
        parts.append(f"\n## {name}")
        parts.extend(f"  {n:>3} | {ln}" for n, ln in enumerate(code.splitlines(), start=1))
    if not board["files"]:
        parts.append("  nothing yet")
    parts.append("\n# SLIDES SHOWN (use [SLIDE n=...] to show one again)")
    for section, n in board["slides_shown"]:
        text = " / ".join(str(slides.get(n, "")).splitlines()[:4])
        parts.append(f"  slide {n} (in '{section}'): {text}")
    if not board["slides_shown"]:
        parts.append("  none yet")
    parts.append(f"\nCurrent section: {board['section']} | Last program output: "
                 f"{board['last_output'].strip()[:200] or 'none'}")
    return "\n".join(parts)
