"""Background "generate" jobs for the web backend: index + generate, with a captured log.

The web server is the one place that needs a thread: generating takes a minute or more,
and the browser polls /job for progress meanwhile. One job per lecture at a time.

The teacher sees plain steps ("Reading your material", "Writing the script", ...) and a plain message if it fails.
The full technical log still goes to the server's terminal; it is never sent to the browser.
"""

import contextlib
import io
import re
import sys
import threading
import traceback

_jobs = {}  # lecture_id -> {"status": "running" | "done" | "failed", "log": [str], "error": str, "step": int}
_lock = threading.Lock()

# The steps a teacher sees, in order, and the log lines that start each one.
STEPS = [
    ("material", "Reading your material", re.compile(r"^\[index\]")),
    ("plan", "Planning the lecture", re.compile(r"step 1/3")),
    ("write", "Writing the lesson", re.compile(r"step 2/3")),
    ("lesson_check", "Checking the teaching", re.compile(r"^\[lesson\] (checking|\d+ problem)")),
    ("stage", "Adding slides, notes and highlights", re.compile(r"step 3/3")),
    ("stage_check", "Checking the staging", re.compile(r"^\[staging\] checking")),
    ("visuals", "Drawing the graphs", re.compile(r"^\[visual\] building")),
    ("done", "Script ready", re.compile(r"Script saved")),
]

# A failure in the teacher's words, from what the log says went wrong.
FAILURES = [
    (re.compile(r"model call failed|could not be reached|OPENROUTER|credits|timed out", re.I),
     "The AI service couldn't be reached just now. Please try again in a minute."),
    (re.compile(r"No PPTX, PDF or DOCX", re.I), "Upload at least one slide deck, PDF or Word file first."),
    (re.compile(r"persona", re.I), "The teacher persona is incomplete. Fill in every field, then try again."),
    (re.compile(r"still has \d+ error", re.I),
     "The script still had a few problems after several tries. Open Edit to see and fix them, or generate again."),
    (re.compile(r"embedding failed", re.I), "Your material couldn't be read into the knowledge base. Please try again."),
]
GENERIC_FAILURE = "Something went wrong while making the script. Please try again."


class _LogWriter(io.TextIOBase):
    """File-like object (required by redirect_stdout) that copies prints into the job log."""

    def __init__(self, job):
        self.job = job

    def write(self, text):
        sys.__stdout__.write(text)
        for line in text.splitlines():
            if line.strip():
                self.job["log"].append(line)
                for n, (_, _, pattern) in enumerate(STEPS):
                    if n > self.job["step"] and pattern.search(line):
                        self.job["step"] = n
        return len(text)


def _friendly_error(job):
    text = "\n".join(job["log"][-12:]) + "\n" + job.get("error", "")
    return next((msg for pattern, msg in FAILURES if pattern.search(text)), GENERIC_FAILURE)


def get_job(lecture_id):
    """What the browser sees: status, the plain steps (done / now / later) and a plain error. No log lines."""
    job = _jobs.get(lecture_id)
    if job is None:
        return {"status": "idle", "steps": [], "error": ""}
    current = job["step"]
    steps = []
    for n, (key, label, _) in enumerate(STEPS):
        if key == "visuals" and current < n:
            continue  # only shown once graphs are actually being drawn
        state = "done" if n < current or job["status"] == "done" else "now" if n == current else "later"
        if job["status"] == "failed" and n == current:
            state = "failed"
        steps.append({"key": key, "label": label, "state": state})
    return {"status": job["status"], "steps": steps,
            "error": _friendly_error(job) if job["status"] == "failed" else ""}


def clear_job(lecture_id):
    _jobs.pop(lecture_id, None)


def start_generate(lecture_id, topic, duration_min, speaking_min=None):
    """Start index + generate in the background. Returns False if one is already running."""
    with _lock:
        if get_job(lecture_id)["status"] == "running":
            return False
        job = {"status": "running", "log": [], "error": "", "step": 0}
        _jobs[lecture_id] = job
    worker = threading.Thread(target=_work, args=(lecture_id, topic, duration_min, speaking_min, job), daemon=True)
    worker.start()
    return True


def _work(lecture_id, topic, duration_min, speaking_min, job):
    from eris.material.indexer import run_index
    from eris.generate.script_writer import run_generate

    # Note: redirect_stdout is process-wide, so other prints during the job also land in its log.
    with contextlib.redirect_stdout(_LogWriter(job)):
        try:
            run_index(lecture_id, topic=topic, duration_min=duration_min, speaking_min=speaking_min)
            run_generate(lecture_id)
            job["status"] = "done"
        except SystemExit:
            # The pipeline exits with a printed reason; the last lines of the log explain it.
            job["status"] = "failed"
            job["error"] = "\n".join(job["log"][-6:]) or "Generation stopped."
        except Exception as e:
            traceback.print_exc(file=sys.__stdout__)
            job["status"] = "failed"
            job["error"] = f"{type(e).__name__}: {e}"
