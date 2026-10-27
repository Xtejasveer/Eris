"""The agent tools. Every tool returns a string and never raises."""

import subprocess
import time
from pathlib import Path

from langchain.tools import tool

from eris import config
from eris.material.indexer import describe_location, get_vectorstore

# Set once per command with set_lecture(); kept simple on purpose for v1.
_lecture_id = None
_store = None
_board = None   # what is on the class screen now (class_board), set before each doubt turn
_slides = {}


def set_lecture(lecture_id):
    global _lecture_id, _store
    _lecture_id = lecture_id
    _store = None  # Built lazily on first search.


def set_board(board, slides=None):
    global _board, _slides
    _board, _slides = board, slides or {}


def _tmp_dir():
    if _lecture_id is None:
        raise ValueError("set_lecture() was not called")
    return (config.lecture_dir(_lecture_id) / "tmp").resolve()


def _cut(text, limit=3000):
    return text if len(text) <= limit else text[:limit] + "\n...(truncated)"


def program_output(exit_code, stdout, stderr):
    """What the class sees for a run: stdout, plus stderr when the program failed or was stopped."""
    if exit_code == 0 or not stderr:
        return stdout
    gap = "" if not stdout or stdout.endswith("\n") else "\n"  # a cut-off line shouldn't run into the error
    return stdout + gap + stderr


def run_code_file(code, filename="dry_run.py", folder=None):
    """Write `code` to tmp/<filename> (or folder/<filename>), run it, return (exit_code, stdout, stderr).

    The program runs in the sandbox (eris/sandbox.py: no network, no project files, no secrets). It is stopped
    (exit code -1, reason at the end of stderr) when it runs longer than DRY_RUN_TIMEOUT_S or prints more than
    OUTPUT_LIMIT_BYTES. Output goes to files, not memory, so an endless print loop can never fill up the server's memory.
    """
    from eris import sandbox
    # Whatever the file name came from (a script, a model, a request), it is a plain name inside its folder.
    if not sandbox.CODE_FILE_RE.match(str(filename)):
        return -1, "", f"ERROR: '{filename}' is not a plain program name like countdown.py"
    base = _tmp_dir() if folder is None else Path(folder).resolve()
    path = (base / filename).resolve()
    if path.parent != base:
        return -1, "", f"ERROR: '{filename}' is not a plain program name like countdown.py"
    try:
        argv, options, stop = sandbox.command(path)
    except sandbox.SandboxUnavailable as e:
        print(f"[sandbox] {e}")
        return -1, "", "ERROR: running code is turned off on this server (no secure sandbox)"
    path.write_text(code, encoding="utf-8")
    out_path, err_path = path.with_suffix(".out"), path.with_suffix(".err")
    limit, reason = config.OUTPUT_LIMIT_BYTES, None
    with open(out_path, "wb") as out, open(err_path, "wb") as err:
        proc = subprocess.Popen(argv, stdout=out, stderr=err, **options)
        started = time.monotonic()
        while proc.poll() is None:
            if time.monotonic() - started > config.DRY_RUN_TIMEOUT_S:
                reason = f"ERROR: timed out after {config.DRY_RUN_TIMEOUT_S}s"
            elif out_path.stat().st_size + err_path.stat().st_size > limit:
                reason = f"ERROR: stopped after {limit} bytes of output (an endless loop?)"
            if reason:
                stop(proc)
                proc.wait()
                break
            time.sleep(0.05)
    # Read only the first `limit` bytes: the same program always gives the same cut.
    stdout = out_path.read_bytes()[:limit].decode("utf-8", errors="replace")
    stderr = err_path.read_bytes()[:limit].decode("utf-8", errors="replace")
    out_path.unlink()
    err_path.unlink()
    if reason:
        return -1, stdout, (stderr + "\n" + reason).strip() + "\n"
    return proc.returncode, stdout, stderr


@tool
def search_material(query: str) -> str:
    """Search the teacher's lecture material. Use before explaining any concept or answering a question."""
    global _store
    print(f'[tool] search_material("{query}")')
    try:
        if _store is None:
            _store = get_vectorstore(_lecture_id)
        hits = _store.similarity_search(query, k=config.TOP_K)
    except Exception as e:
        return f"ERROR: search failed: {e}"
    if not hits:
        return "No matching material found."
    return "\n\n".join(f"[{describe_location(h.metadata)}] {h.page_content}" for h in hits)


@tool
def read_outline() -> str:
    """Return the outline of the teacher's files (slide titles, sections, pages) as JSON."""
    print("[tool] read_outline()")
    try:
        path = config.lecture_dir(_lecture_id) / "outline.json"
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR: could not read outline: {e}"


@tool
def dry_run_python(code: str) -> str:
    """Run Python code and return its exit code, stdout and stderr. Use before every RUN marker."""
    print(f"[tool] dry_run_python({len(code.splitlines())} lines)")
    try:
        exit_code, stdout, stderr = run_code_file(code)
    except Exception as e:
        return f"ERROR: could not run code: {e}"
    if exit_code == -1:
        return (f"{stderr.strip().splitlines()[-1]}. This code never finishes on its own: "
                f"do not RUN it in the script.\nfirst output:\n{_cut(stdout, 500)}")
    return f"exit_code: {exit_code}\nstdout:\n{_cut(stdout)}\nstderr:\n{_cut(stderr)}"


@tool
def read_board() -> str:
    """See what is on the class screen now: every notebook line (by page and section), the code files
    and the slides shown so far. Use it to find where a doubt comes from before answering."""
    print("[tool] read_board()")
    if _board is None:
        return "The board is not available in this mode. Answer by speaking."
    from eris.classroom.class_board import describe
    try:
        return _cut(describe(_board, _slides), 8000)
    except Exception as e:
        return f"ERROR: could not read the board: {e}"


@tool
def ask_class_for_doubts(prompt: str) -> str:
    """Ask the class a question, e.g. 'Any doubts?'. Returns what a student says."""
    # Never actually runs: the human-in-the-loop middleware intercepts this call
    # and returns the student's typed reply instead.
    return "No response."

