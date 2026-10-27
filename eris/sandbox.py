"""Where programs run: every program Eris runs (lesson code, doubt answers, generation dry runs) goes through
`command()`, so it never runs as plain code on the main server.

Backends (ERIS_SANDBOX in .env):
- docker: a throwaway container with no network, capped memory, CPU and processes, a read-only system, no Linux
  capabilities, as a nobody user. Only the run's folder is mounted. Needs the image (SANDBOX_IMAGE) pulled once.
- os: macOS's sandbox-exec: no network, no reading the project (so not .env or the database), writing only in the
  run's folder, plus CPU, file size and open-file limits and an environment without any secrets. For local work on a
  Mac only: there is no equally strong one on Linux.
- auto (default): docker when the image is there, else sandbox-exec on a Mac.
- off: no sandbox at all. Only for trusted local work, and only when set explicitly.

It fails closed: when the chosen sandbox isn't available, programs don't run (SandboxUnavailable) rather than run in
something weaker. Every backend runs the plain interpreter (no project packages, no site-packages).
"""

import os
import re
import shutil
import subprocess
import sys
import uuid
from functools import lru_cache
from pathlib import Path

from eris import config

CODE_FILE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}\.py$")  # a program's file: a plain name, never a path
MEMORY_MB = 256
FILE_LIMIT_BYTES = 2 * 1024 * 1024
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PYTHON = os.path.realpath(sys.executable)  # the base interpreter, outside the project's .venv
_CLEAN_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1",
              "HOME": "/tmp"}


@lru_cache(maxsize=1)
def _docker_ready():
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "image", "inspect", config.SANDBOX_IMAGE], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class SandboxUnavailable(RuntimeError):
    """No sandbox strong enough to run a program here, so it isn't run."""


def _macos_ready():
    return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None


def backend():
    """The sandbox programs run in now: "docker", "os", "off", or None when none strong enough is available."""
    mode = config.SANDBOX
    if mode == "auto":
        return "docker" if _docker_ready() else "os" if _macos_ready() else None
    if mode == "docker":
        return "docker" if _docker_ready() else None
    if mode == "os":
        return "os" if _macos_ready() else None
    if mode == "off":
        return "off"
    raise ValueError(f"Unknown ERIS_SANDBOX '{mode}' (use auto, docker, os or off)")


def _limits():
    """Run in the child before the program starts: CPU seconds, file size, open files, memory where the OS allows."""
    import resource
    cpu = config.DRY_RUN_TIMEOUT_S + 1
    for name, value in (("RLIMIT_CPU", cpu), ("RLIMIT_FSIZE", FILE_LIMIT_BYTES), ("RLIMIT_NOFILE", 64),
                        ("RLIMIT_AS", MEMORY_MB * 1024 * 1024)):
        try:
            resource.setrlimit(getattr(resource, name), (value, value))
        except (ValueError, OSError, AttributeError):
            pass  # macOS ignores the memory limit; the others still apply
    os.setsid()  # its own process group, so a stop also ends anything it started


def _macos_profile(folder):
    folder = str(Path(folder).resolve()).replace('"', "")
    project = str(PROJECT_ROOT).replace('"', "")
    return f"""(version 1)
(allow default)
(deny network*)
(deny process-exec)
(allow process-exec (literal "{_PYTHON}"))
(deny file-write*)
(allow file-write* (subpath "{folder}") (literal "/dev/null") (literal "/dev/stdout") (literal "/dev/stderr"))
(deny file-read* (subpath "{project}"))
(allow file-read* (subpath "{folder}"))
(deny file-read* (subpath "{os.path.expanduser('~')}"))
(allow file-read* (subpath "{folder}") (subpath "{os.path.dirname(os.path.dirname(_PYTHON))}"))
"""


def command(path):
    """(argv, popen kwargs, stop) to run the program at `path` inside its folder. stop() ends it for good."""
    path = Path(path).resolve()
    kind = backend()
    if kind is None:
        raise SandboxUnavailable(f"no secure sandbox for ERIS_SANDBOX={config.SANDBOX}: pull the image "
                                 f"(docker pull {config.SANDBOX_IMAGE}) or run on a Mac")
    if kind == "docker":
        name = f"eris-run-{uuid.uuid4().hex[:12]}"
        argv = ["docker", "run", "--rm", "--name", name, "--network", "none", "--memory", f"{MEMORY_MB}m",
                "--memory-swap", f"{MEMORY_MB}m", "--cpus", "1", "--pids-limit", "64", "--read-only",
                "--tmpfs", "/tmp:size=16m", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--user", "65534:65534", "-e", "PYTHONIOENCODING=utf-8", "-e", "PYTHONDONTWRITEBYTECODE=1",
                "-v", f"{path.parent}:/work", "-w", "/work", config.SANDBOX_IMAGE, "python", "-I", "-S", path.name]
        stop = lambda proc: (subprocess.run(["docker", "rm", "-f", name], capture_output=True), proc.kill())
        return argv, {"cwd": path.parent}, stop
    python = [_PYTHON, "-I", "-S", path.name]
    # "os" is sandbox-exec (backend() checked it is there); "off" was asked for explicitly: limits and a clean
    # environment only
    argv = ["sandbox-exec", "-p", _macos_profile(path.parent)] + python if kind == "os" else python

    def stop(proc):
        try:
            os.killpg(proc.pid, 9)
        except OSError:
            proc.kill()
    return argv, {"cwd": path.parent, "env": dict(_CLEAN_ENV), "preexec_fn": _limits}, stop


def describe():
    kind = backend()
    if kind == "docker":
        return f"docker ({config.SANDBOX_IMAGE}, no network, {MEMORY_MB} MB)"
    if kind == "os":
        return "macOS sandbox (no network, no project files)"
    if kind == "off":
        return "off (programs run unsandboxed)"
    return "none available: programs don't run"
