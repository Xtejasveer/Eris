"""Background "generate" jobs for the web backend: index + generate, with a captured log.

The web server is the one place that needs a thread: generating takes a minute or more,
and the browser polls /job for progress meanwhile. One job per lecture at a time.
"""

import contextlib
import io
import sys
import threading
import traceback

_jobs = {}  # lecture_id -> {"status": "running" | "done" | "failed", "log": [str], "error": str}
_lock = threading.Lock()


class _LogWriter(io.TextIOBase):
    """File-like object (required by redirect_stdout) that copies prints into the job log."""

    def __init__(self, job):
        self.job = job

    def write(self, text):
        sys.__stdout__.write(text)
        for line in text.splitlines():
            if line.strip():
                self.job["log"].append(line)
        return len(text)


def get_job(lecture_id):
    return _jobs.get(lecture_id, {"status": "idle", "log": [], "error": ""})


def clear_job(lecture_id):
    _jobs.pop(lecture_id, None)


def start_generate(lecture_id, topic, duration_min):
    """Start index + generate in the background. Returns False if one is already running."""
    with _lock:
        if get_job(lecture_id)["status"] == "running":
            return False
        job = {"status": "running", "log": [], "error": ""}
        _jobs[lecture_id] = job
    worker = threading.Thread(target=_work, args=(lecture_id, topic, duration_min, job), daemon=True)
    worker.start()
    return True


def _work(lecture_id, topic, duration_min, job):
    from indexer import run_index
    from script_writer import run_generate

    # Note: redirect_stdout is process-wide, so other prints during the job also land in its log.
    with contextlib.redirect_stdout(_LogWriter(job)):
        try:
            run_index(lecture_id, topic=topic, duration_min=duration_min)
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
