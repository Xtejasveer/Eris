"""Settings, paths and the lecture manifest (lecture.json)."""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Settings from .env ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
EMBED_MODEL = os.getenv("EMBED_MODEL", "baai/bge-m3").strip()
TOPIC_NAME = os.getenv("TOPIC_NAME", "Python list comprehensions").strip()
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _int_env(name, default):
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        print(f"[config] {name} must be a whole number, got '{value}'. Fix it in .env.")
        sys.exit(1)


LECTURE_DURATION_MIN = _int_env("LECTURE_DURATION_MIN", 30)
SPEAKING_WPM = _int_env("SPEAKING_WPM", 130)

# --- Voice (Gnani). Only needed for `render` and `session --voice/--mic` ---
GNANI_API_KEY = os.getenv("GNANI_API_KEY", "").strip()
TTS_VOICE = os.getenv("TTS_VOICE", "Kaveri").strip()
TTS_LANGUAGE = os.getenv("TTS_LANGUAGE", "en-IN").strip()
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "en-IN").strip()
try:
    TTS_SPEED = float(os.getenv("TTS_SPEED", "1.0") or "1.0")
except ValueError:
    print("[config] TTS_SPEED must be a number between 0.85 and 1.15. Fix it in .env.")
    sys.exit(1)

# --- Paths ---
CHROMA_DIR = "chroma_db"
DATA_ROOT = "data"
WORKSPACE_ROOT = "workspace/lectures"

# --- Fixed constants ---
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
EMBED_BATCH = 64
TOP_K = 4
DRY_RUN_TIMEOUT_S = 15
OUTPUT_LIMIT_BYTES = 8000   # a run printing more than this is stopped (endless loop guard)
MAX_DOUBTS_PER_CHECK = 3
MAX_DOUBTS_FINAL = 8
DOUBT_TIME_SHARE = 0.2
NOTE_TIME_SHARE = 0.15     # share of the lecture spent writing in the notebook
RUN_MIN_EACH = 0.5
TTS_CHUNK_CHARS = 400      # long narration is synthesized in sentence groups of this size
MIC_MAX_SECONDS = 55       # Gnani REST STT accepts clips up to 60 s
FIX_ATTEMPTS = 2           # times generate asks the model to fix a script that fails the checks
TYPE_DELAY_S = 0.04        # per-line delay when "typing" code on the board
NOTE_CHARS_PER_S = 25      # "handwriting" speed in the notebook, used for time estimates

# Status order. A lecture "has reached" a status if its index is >= that one.
STATUSES = ["indexed", "draft", "approved", "completed"]

# v2: replace InMemorySaver with SqliteSaver for persistence


def check_env():
    """Exit with a clear message if a required setting is missing."""
    missing = []
    if not OPENROUTER_API_KEY:
        missing.append("OPENROUTER_API_KEY")
    if not LLM_MODEL:
        missing.append("LLM_MODEL")
    if missing:
        print(f"[config] Missing required settings in .env: {', '.join(missing)}")
        print("[config] Copy .env.example to .env and fill them in.")
        sys.exit(1)


def check_voice_env():
    """Exit with a clear message if voice is requested without a Gnani key."""
    if not GNANI_API_KEY:
        print("[config] GNANI_API_KEY is missing in .env (needed for voice). Get one at https://app.gnani.ai/voice")
        sys.exit(1)
    if not 0.85 <= TTS_SPEED <= 1.15:
        print(f"[config] TTS_SPEED must be between 0.85 and 1.15, got {TTS_SPEED}.")
        sys.exit(1)


def data_dir(lecture_id):
    """Folder where the teacher drops files for this lecture."""
    return Path(DATA_ROOT) / lecture_id


def lecture_dir(lecture_id):
    """Workspace folder for this lecture (created with its tmp/ if needed)."""
    path = Path(WORKSPACE_ROOT) / lecture_id
    (path / "tmp").mkdir(parents=True, exist_ok=True)
    return path


def manifest_path(lecture_id):
    return lecture_dir(lecture_id) / "lecture.json"


def load_manifest(lecture_id):
    """Read lecture.json. Exit with a hint if it does not exist or is broken."""
    path = manifest_path(lecture_id)
    if not path.exists():
        print(f"[config] No lecture.json for '{lecture_id}'. Run: python main.py index --lecture {lecture_id}")
        sys.exit(1)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[config] {path} is not valid JSON: {e}")
        sys.exit(1)


def save_manifest(lecture_id, manifest):
    path = manifest_path(lecture_id)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def status_at_least(manifest, status):
    """True if the manifest's status is `status` or later in STATUSES."""
    current = manifest.get("status")
    if current not in STATUSES:
        return False
    return STATUSES.index(current) >= STATUSES.index(status)
