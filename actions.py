"""Classroom actions the player executes, one per script marker.

The "board" is the terminal plus real files in workspace/lectures/<id>/board/.
Every action returns {"ok": bool, "error": str}. Actions never raise.
"""

import re
import time
from pathlib import Path

import config
from indexer import load_pptx
from tools import program_output, run_code_file

BAR = "─" * 60


def new_board(lecture_id):
    folder = config.lecture_dir(lecture_id) / "board"
    folder.mkdir(exist_ok=True)
    return {"dir": folder.resolve(), "files": {}, "slides": _load_slides(lecture_id),
            "last_output": "", "expected_output": "", "last_exit": None, "current_slide": None,
            "notebook": []}


def _load_slides(lecture_id):
    """{slide number: text} from the first PPTX in the data folder."""
    for path in sorted(Path(config.data_dir(lecture_id)).glob("*.pptx")):
        try:
            return {d.metadata["slide"]: d.page_content for d in load_pptx(path)}
        except Exception as e:
            print(f"[board] could not read slides from {path.name}: {e}")
    return {}


def _numbered(code, start=1, end=None, prefix="   "):
    lines = code.splitlines()
    for n in range(start, (end or len(lines)) + 1):
        print(f"{prefix}{n:>3} | {lines[n - 1]}")


def _line_range(lines):
    start, _, end = lines.partition("-")
    return int(start), int(end or start)


def write_code(board, args):
    name, code = args["file"], args["code"]
    (board["dir"] / name).write_text(code + "\n", encoding="utf-8")
    board["files"][name] = code
    print(f"\n▶ [WRITE_CODE {name}]")
    for n, line in enumerate(code.splitlines(), start=1):
        print(f"   {n:>3} | {line}")
        time.sleep(config.TYPE_DELAY_S)  # "typing" on the board
    return {"ok": True, "error": ""}


def highlight(board, args):
    name = args["file"]
    if name not in board["files"]:
        return {"ok": False, "error": f"{name} is not on the board"}
    start, end = _line_range(args["lines"])
    print(f"\n▶ [HIGHLIGHT {name} lines {args['lines']}]")
    _numbered(board["files"][name], start, end, prefix=">> ")
    return {"ok": True, "error": ""}


def run(board, args, expected=""):
    name = re.sub(r"^python\s+", "", args["cmd"]).strip()
    if name not in board["files"]:
        return {"ok": False, "error": f"{name} is not on the board"}
    print(f"\n▶ [RUN {args['cmd']}]")
    exit_code, stdout, stderr = run_code_file(board["files"][name], name, folder=board["dir"])
    board["last_output"] = program_output(exit_code, stdout, stderr)
    board["expected_output"] = expected
    board["last_exit"] = exit_code
    # A non-zero exit is only a problem if it wasn't approved (e.g. a planned error demo is fine).
    if exit_code != 0 and board["last_output"].strip() != expected.strip():
        return {"ok": False, "error": f"{args['cmd']} failed (exit {exit_code}): {stderr.strip()[-300:]}"}
    return {"ok": True, "error": ""}


def read_output(board, args):
    print("\n▶ [OUTPUT]")
    print("   " + (board["last_output"].rstrip() or "(no output)").replace("\n", "\n   "))
    expected = board["expected_output"]
    if expected and board["last_output"].strip() != expected.strip():
        return {"ok": False, "error": f"live output differs from the approved output. "
                                      f"Expected: {expected.strip()[:200]!r}"}
    return {"ok": True, "error": ""}


def show_slide(board, args):
    n = args["n"]
    board["current_slide"] = n
    text = board["slides"].get(n)
    print(f"\n▶ [SLIDE {n}]\n{BAR}")
    print("  " + (text or "(slide not found)").replace("\n", "\n  "))
    print(BAR)
    return {"ok": text is not None, "error": "" if text else f"slide {n} not found"}


def slide_highlight(board, args):
    print(f"\n▶ [SLIDE {args['n']}] highlight: «{args['text']}»")
    return {"ok": True, "error": ""}


def note(board, args, title=False):
    """Write lines in the notebook (printed as a ruled block in the terminal)."""
    lines = args["text"].splitlines()
    board["notebook"].extend(("## " + ln) if title else ln for ln in lines)
    print("\n📓 " + ("NOTEBOOK — " + lines[0].upper() if title else "NOTEBOOK"))
    if not title:
        for ln in lines:
            print(f"   │ {ln}")
            time.sleep(config.TYPE_DELAY_S)
    return {"ok": True, "error": ""}


def note_title(board, args):
    return note(board, args, title=True)


def note_highlight(board, args):
    text = args["text"]
    if not any(text.lower() in ln.lower() for ln in board["notebook"]):
        return {"ok": False, "error": f"'{text}' is not in the notebook"}
    print(f"\n📓 underline: «{text}»")
    return {"ok": True, "error": ""}


def look_back(board, args):
    text = args["text"]
    hit = next((ln for ln in reversed(board["notebook"]) if text.lower() in ln.lower()), None)
    if hit is None:
        return {"ok": False, "error": f"'{text}' is not in the notebook"}
    print(f"\n📓 looking back at: {hit.removeprefix('## ')}")
    return {"ok": True, "error": ""}


def open_file(board, args):
    name = args["file"]
    if name not in board["files"]:
        return {"ok": False, "error": f"{name} is not on the board"}
    print(f"\n▶ [OPEN_FILE {name}]")
    _numbered(board["files"][name])
    return {"ok": True, "error": ""}


def new_page(board, args):
    board["notebook"].append("## " + args["title"])
    print(f"\n📓 NEW PAGE — {args['title'].upper()}")
    return {"ok": True, "error": ""}


def pause(board, args):
    print(f"\n▶ [PAUSE {args['s']}s]")
    time.sleep(args["s"])
    return {"ok": True, "error": ""}


def visual(board, args):
    controls = ", ".join(c["name"] for c in args.get("controls", []))
    print(f"\n🖼  [VISUAL {args['id']}] {args['title']}: {args.get('brief', '')}  (controls: {controls}; "
          "shown in the browser class only)")
    return {"ok": True, "error": ""}


def visual_set(board, args):
    value = f" = {args['value']}" if "value" in args else " (pressed)"
    print(f"\n🖼  [VISUAL_SET {args['id']}] {args['control']}{value}")
    return {"ok": True, "error": ""}


def open_visual(board, args):
    print(f"\n🖼  [OPEN_VISUAL {args['id']}]")
    return {"ok": True, "error": ""}


ACTIONS = {
    "WRITE_CODE": write_code,
    "HIGHLIGHT": highlight,
    "READ_OUTPUT": read_output,
    "SLIDE": show_slide,
    "SLIDE_HIGHLIGHT": slide_highlight,
    "WRITE": note,
    "NOTE": note,
    "NOTE_TITLE": note_title,
    "NOTE_HIGHLIGHT": note_highlight,
    "PAUSE": pause,
    "LOOK_BACK": look_back,
    "OPEN_FILE": open_file,
    "NEW_PAGE": new_page,
    "VISUAL": visual,
    "VISUAL_SET": visual_set,
    "OPEN_VISUAL": open_visual,
}


def execute(board, segment):
    """Run one action segment. Never raises."""
    name, args = segment["name"], segment.get("args", {})
    try:
        if name == "RUN":
            return run(board, args, segment.get("expected_output", ""))
        if name not in ACTIONS:
            return {"ok": False, "error": f"no action for [{name}]"}
        return ACTIONS[name](board, args)
    except Exception as e:
        return {"ok": False, "error": f"{name} crashed: {e}"}


def restore(board, segments):
    """Rebuild the board silently from already-played segments (for --resume)."""
    for seg in segments:
        args = seg.get("args", {})
        if seg.get("name") == "WRITE_CODE":
            (board["dir"] / args["file"]).write_text(args["code"] + "\n", encoding="utf-8")
            board["files"][args["file"]] = args["code"]
        elif seg.get("name") == "RUN":
            board["last_output"] = board["expected_output"] = seg.get("expected_output", "")
        elif seg.get("name") == "SLIDE":
            board["current_slide"] = args["n"]
        elif seg.get("name") in ("NOTE", "WRITE"):
            board["notebook"].extend(args["text"].splitlines())
        elif seg.get("name") == "NOTE_TITLE":
            board["notebook"].append("## " + args["text"])
        elif seg.get("name") == "NEW_PAGE":
            board["notebook"].append("## " + args["title"])
