"""What is on the class screen at a point in the lecture, rebuilt from segments. No LLM here.

The doubt agent reads it (read_board tool) and its answers are checked against it, so a
[LOOK_BACK], [OPEN_FILE] or [HIGHLIGHT] in an answer can only point at something really shown.
"""


def new_board():
    return {"section": "Introduction", "files": {}, "notebook": [], "pages": [["Lecture", []]],
            "slides_shown": [], "current_slide": None, "has_run": False, "last_output": "", "latest_file": None,
            "visuals": {}, "latest_visual": None}


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
            board["latest_file"] = args["file"]
        elif name == "OPEN_FILE":
            board["latest_file"] = args["file"]
        elif name == "RUN":
            board["has_run"] = True
            board["latest_file"] = args["cmd"].split(" ", 1)[-1]
            board["last_output"] = seg.get("expected_output", "")
        elif name == "SLIDE":
            board["current_slide"] = args["n"]
            board["slides_shown"].append([board["section"], args["n"]])
        elif name == "NEW_PAGE":
            board["pages"].append([args["title"], []])
            board["notebook"].append(args["title"])
            _page_lines(board, board["section"]).append("## " + args["title"])
        elif name == "VISUAL":
            board["visuals"][args["id"]] = {"title": args["title"], "brief": args.get("brief", ""),
                                            "controls": args.get("controls", []), "values": {}, "presses": {}}
            board["latest_visual"] = args["id"]
        elif name in ("VISUAL_SET", "OPEN_VISUAL") and args["id"] in board.get("visuals", {}):
            board["latest_visual"] = args["id"]
            visual = board["visuals"][args["id"]]
            if name == "VISUAL_SET" and "value" in args:
                visual["values"][args["control"]] = args["value"]
            elif name == "VISUAL_SET":
                visual["presses"][args["control"]] = visual["presses"].get(args["control"], 0) + 1
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
        latest = "  <- the most recent program: \"this code\" / \"run it\" means this one" if name == board.get("latest_file") else ""
        parts.append(f"\n## {name}{latest}")
        parts.extend(f"  {n:>3} | {ln}" for n, ln in enumerate(code.splitlines(), start=1))
    if not board["files"]:
        parts.append("  nothing yet")
    parts.append("\n# INTERACTIVE VISUALS (move a control with [VISUAL_SET id=\"...\" control=\"...\" value=...], "
                 "show one again with [OPEN_VISUAL id=\"...\"])")
    from visual_controls import describe_control
    for vid, v in board.get("visuals", {}).items():
        latest = "  <- the most recent visual" if vid == board.get("latest_visual") else ""
        parts.append(f"\n## {vid}: {v['title']}{latest}\n  shows: {v['brief'][:300]}")
        for c in v["controls"]:
            now = v["values"].get(c["name"])
            pressed = v["presses"].get(c["name"])
            extra = f" (now {now})" if now is not None else f" (pressed {pressed}x)" if pressed else ""
            parts.append(f"  control {describe_control(c)}{extra}")
    if not board.get("visuals"):
        parts.append("  none yet")
    shown = {}
    for section, n in board["slides_shown"]:
        shown.setdefault(n, section)
    parts.append("\n# THE TEACHER'S SLIDES (show ANY of them with [SLIDE n=...], e.g. when a student asks to see the slides)")
    for n in sorted(slides, key=lambda k: int(k)):
        lines = [ln.strip() for ln in str(slides[n]).splitlines() if ln.strip()]
        title = lines[0] if lines else ""
        rest = " / ".join(lines[1:4])
        seen = f"  (shown in '{shown[n]}')" if n in shown else ""
        current = "  <- on screen now" if n == board.get("current_slide") else ""
        parts.append(f"  slide {n}: {title}{' - ' + rest if rest else ''}{seen}{current}")
    if not slides:
        parts.append("  this lecture has no slides")
    parts.append(f"\nCurrent section: {board['section']} | Last program output: "
                 f"{board['last_output'].strip()[:200] or 'none'}")
    return "\n".join(parts)
