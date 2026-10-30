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


def model_name(model_id):
    """A model id as people say it: "anthropic/claude-haiku-5.5" -> "Claude Haiku 5.5", "openai/gpt-4o" -> "GPT 4o"."""
    words = (model_id or "").split("/")[-1].replace("_", "-").split("-")
    upper = {"gpt", "llm", "ai"}
    return " ".join(w.upper() if w.lower() in upper else w if any(c.isdigit() for c in w) else w.capitalize()
                    for w in words if w)
EMBED_MODEL = os.getenv("EMBED_MODEL", "baai/bge-m3").strip()
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


# Defaults for a new lecture; each lecture keeps its own. The total runs the class clock (warnings when 10% and 5%
# of it is left); only the speaking time goes to the script writer (doubts, writing and code fill the rest).
LECTURE_DURATION_MIN = _int_env("LECTURE_DURATION_MIN", 15)
SPEAKING_MIN = _int_env("SPEAKING_MIN", 5)
SPEAKING_WPM = _int_env("SPEAKING_WPM", 115)  # with the slower voice and pauses; sets the script's word budget

# --- Voice (Gnani). Only needed for `render` and `session --voice/--mic` ---
GNANI_API_KEY = os.getenv("GNANI_API_KEY", "").strip()
# Guardrails on student doubts (eris/guardrails.py): Jev checks every question and answer (uses OPENROUTER_API_KEY).
GUARDRAILS_ENABLED = os.getenv("GUARDRAILS_ENABLED", "true").strip().lower() in ("1", "true", "yes")
# Where programs run (eris/sandbox.py): auto (docker when SANDBOX_IMAGE is pulled, else the OS sandbox), docker, os, off.
SANDBOX = os.getenv("ERIS_SANDBOX", "auto").strip().lower()
SANDBOX_IMAGE = os.getenv("ERIS_SANDBOX_IMAGE", "python:3.12-slim").strip()
# A student's doubt may get an answer with a program that runs on the server (in the sandbox). Off: answers to students
# explain code in words and notes but never run it; teachers previewing still get runnable answers.
STUDENT_CODE_RUNS = os.getenv("ERIS_STUDENT_CODE_RUNS", "false").strip().lower() in ("1", "true", "yes")
# Anyone may create a teacher account on the sign-in page. Off: only students sign up; teachers are made by the
# admin (python main.py seed, or a new account switched to teacher in the database).
TEACHER_SIGNUP = os.getenv("ERIS_TEACHER_SIGNUP", "false").strip().lower() in ("1", "true", "yes")
# The sign-in cookie is sent over HTTPS only. Turn on when the site has a domain with HTTPS (deploy/Caddyfile).
SECURE_COOKIES = os.getenv("ERIS_SECURE_COOKIES", "false").strip().lower() in ("1", "true", "yes")
# The sign-in page offers the demo accounts (python main.py seed). Local pilots only: turn off for real users.
DEMO_LOGINS = os.getenv("ERIS_DEMO_LOGINS", "true").strip().lower() in ("1", "true", "yes")
TTS_VOICE = os.getenv("TTS_VOICE", "Kaveri").strip()
TTS_LANGUAGE = os.getenv("TTS_LANGUAGE", "en-IN").strip()
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "en-IN").strip()
try:
    TTS_SPEED = float(os.getenv("TTS_SPEED", "0.85") or "0.85")  # Gnani's slowest; 1.0 sounds rushed for teaching
except ValueError:
    print("[config] TTS_SPEED must be a number between 0.85 and 1.15. Fix it in .env.")
    sys.exit(1)
# Teaching languages (each lecture picks one in Studio): the script is written in it, Gnani says it and hears the
# students in it. Code, program output and the material's own terms may stay in English. One Timbre v2.5 voice
# per language; override one with TTS_VOICE_<CODE> in .env (TTS_VOICE_TE_IN=Lavanya). English uses TTS_VOICE.
LANGUAGES = {
    "en-IN": ("English", "Kaveri"), "hi-IN": ("Hindi", "Nalini"), "ta-IN": ("Tamil", "Asmita"),
    "te-IN": ("Telugu", "Suhana"), "kn-IN": ("Kannada", "Saanvi"), "ml-IN": ("Malayalam", "Reshma"),
    "mr-IN": ("Marathi", "Zahira"), "bn-IN": ("Bengali", "Kirra"), "gu-IN": ("Gujarati", "Falak"),
    "pa-IN": ("Punjabi", "Mehuli"),
}
DEFAULT_LANGUAGE = TTS_LANGUAGE if TTS_LANGUAGE in LANGUAGES else "en-IN"
# Gnani Timbre v2.5 voices that suit each language; the teacher picks one per lecture in Studio (else the default).
LANGUAGE_VOICES = {
    "en-IN": ["Kaveri", "Trupti", "Devika", "Pranav", "Shlok", "Girish"],
    "hi-IN": ["Nalini", "Bhavna", "Yashvi", "Urmila", "Jwala", "Chitra", "Ambuja", "Deepak", "Roopesh", "Vikrant",
              "Hemraj", "Jalaj", "Omkar"],
    "ta-IN": ["Asmita", "Trisha", "Brinda", "Vedika", "Noopur"], "te-IN": ["Suhana", "Lehara", "Lavanya", "Yukti", "Varuni"],
    "kn-IN": ["Saanvi", "Kavin"], "ml-IN": ["Reshma", "Riyaan"], "mr-IN": ["Zahira", "Ishaan"], "bn-IN": ["Kirra", "Dhruva"],
    "gu-IN": ["Falak", "Veera"], "pa-IN": ["Mehuli", "Zayan"],
}
# Which Gnani voices are men's (all others are women's), from Gnani's voice catalog
# (https://docs.gnani.ai/api/TTS/available-voices). Many languages mark the speaker's gender in the grammar
# ("मैं पढ़ा रही हूँ" / "पढ़ा रहा हूँ"), so the script must match the voice that says it.
MALE_VOICES = {"Pranav", "Shlok", "Girish", "Deepak", "Roopesh", "Vikrant", "Hemraj", "Jalaj", "Omkar", "Kavin",
               "Riyaan", "Ishaan", "Dhruva", "Veera", "Zayan"}
# What Studio's voice preview says, in the lecture's language.
VOICE_SAMPLES = {
    "en-IN": "Hello class. Today I'm teaching in place of your teacher.",
    "hi-IN": "नमस्ते दोस्तों, आज की क्लास में आपका स्वागत है।", "ta-IN": "வணக்கம், இன்றைய வகுப்புக்கு வரவேற்கிறேன்.",
    "te-IN": "నమస్కారం, ఈ రోజు తరగతికి స్వాగతం.", "kn-IN": "ನಮಸ್ಕಾರ, ಇಂದಿನ ತರಗತಿಗೆ ಸ್ವಾಗತ.",
    "ml-IN": "നമസ്കാരം, ഇന്നത്തെ ക്ലാസ്സിലേക്ക് സ്വാഗതം.", "mr-IN": "नमस्कार, आजच्या वर्गात तुमचे स्वागत आहे.",
    "bn-IN": "নমস্কার, আজকের ক্লাসে স্বাগত।", "gu-IN": "નમસ્તે, આજના વર્ગમાં તમારું સ્વાગત છે.",
    "pa-IN": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਅੱਜ ਦੀ ਕਲਾਸ ਵਿੱਚ ਤੁਹਾਡਾ ਸਵਾਗਤ ਹੈ।",
}
if not 0.85 <= TTS_SPEED <= 1.15:  # Gnani refuses anything else, and the class would fall silent
    print(f"[config] TTS_SPEED {TTS_SPEED} is outside Gnani's 0.85-1.15; using {min(max(TTS_SPEED, 0.85), 1.15)}")
    TTS_SPEED = min(max(TTS_SPEED, 0.85), 1.15)

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
MAX_DOUBTS_PER_CHECK = 4
MAX_DOUBTS_FINAL = 8
RUN_MIN_EACH = 0.5
TTS_CHUNK_CHARS = 400      # a sentence longer than this is split at commas before synthesis
SHORT_SENTENCE_CHARS = 20  # only very short sentences ("Right.") join the next one; others get their own pause
SENTENCE_PAUSE_S = 0.6     # silence after a sentence (Gnani has no pause markup, so we add it to the audio)
QUESTION_PAUSE_S = 0.85    # silence after a question or exclamation: time to think
PHRASE_PAUSE_S = 0.25      # a short break at a comma inside a sentence
PHRASE_MIN_WORDS = 4       # a comma splits a sentence only when both sides have this many words
MIC_MAX_SECONDS = 55       # Gnani REST STT accepts clips up to 60 s
FIX_ATTEMPTS = 2           # times generate asks the model to fix a script that fails the checks
TYPE_DELAY_S = 0.04        # per-line delay when "typing" code on the board
NOTE_CHARS_PER_S = 25      # "handwriting" speed in the notebook, used for time estimates
NOTE_MAX_LINES = 10        # generate rejects a [NOTE] longer than this (the prompt asks for 2-6 lines)
PAUSE_MAX_S = 3            # generate shortens longer [PAUSE]s: silence in class feels broken
MAX_SENTENCE_WORDS = 30    # longer narration sentences go back to the writer (they sound rushed when spoken)
WORDS_PER_NOTE = 180       # about one [NOTE] per this many spoken words, or the writer is told to use the notebook more
SECTION_TWO_NOTES_WORDS = 250  # a section with more narration than this needs at least two [NOTE] blocks

# --- Talking avatar (web/js/avatar): 3D head that lip-syncs the teacher's voice, rendered in the browser ---
AVATAR_ENABLED = os.getenv("AVATAR_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
AVATAR_MODEL_URL = os.getenv("AVATAR_MODEL_URL", "").strip()  # empty = the bundled CC0 avatar

# --- Pictures in the material: a vision model describes each one at index time (what it shows, its text, a
# diagram's steps, a chart's data). The model must accept images; it defaults to LLM_MODEL. ---
VISION_ENABLED = os.getenv("VISION_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
VISION_MODEL = os.getenv("VISION_MODEL", "").strip() or LLM_MODEL
IMAGE_MIN_SIDE = 80     # smaller pictures are icons, bullets or lines: not described
IMAGE_MAX_SIDE = 1600   # larger pictures are scaled down before they are sent and shown

# --- Interactive visuals ([VISUAL]): a model builds each one as a small HTML page shown in the Visual workspace ---
# On: a chart in the slides becomes an interactive graph ([VISUAL]) on the Visual board, next to the flow
# diagrams ([FLOW]) drawn from step lists. Off: charts are only explained on their slide.
VISUALS_ENABLED = os.getenv("VISUALS_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
VISUAL_MODEL = os.getenv("VISUAL_MODEL", "").strip() or LLM_MODEL  # a stronger coding model draws better visuals
VISUAL_BUILD_ATTEMPTS = 3  # the builder gets its problems (checks, test run, layout) back and tries again
VISUAL_TIMEOUT_S = 180     # a visual is a few hundred lines of HTML; slow models need time
MAX_VISUALS = 2            # per lecture (each one takes class time); extra ones are removed
MAX_ANSWER_VISUALS = 1     # per doubt answer (the student waits while it is built)

# --- Script judge (Jev, a decision model on OpenRouter: answers yes/no questions with probabilities) ---
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "typesafe/jev-1.13")  # pinned so pass thresholds stay meaningful
JUDGE_ENABLED = os.getenv("JUDGE_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
JUDGE_PASS = 0.5           # a question passes when P(yes) >= this
JUDGE_REVISIONS = 2        # quality rounds: times generate sends the judge's findings back to the writer
CONTENT_ROUNDS = 2         # step 2: times the lesson goes back to its writer (code problems or Jev blockers)
STAGE_ROUNDS = 2           # step 3: times the staged script goes back to the stager for Jev blockers
# Doubt answers: Jev judges each one. By default the judgement is only logged (doubt_judge.jsonl), after the answer
# plays; DOUBT_JUDGE_BLOCKS=true makes the class wait for it, and a blocker gets the agent to answer once more
# (better answers, several seconds slower).
DOUBT_JUDGE = os.getenv("DOUBT_JUDGE", "true").strip().lower() not in ("0", "false", "no", "off")
DOUBT_JUDGE_BLOCKS = os.getenv("DOUBT_JUDGE_BLOCKS", "false").strip().lower() in ("1", "true", "yes", "on")
PAIR_UNFLAG = 0.3          # a while_speaking pair is un-flagged when P(sentence describes the writing) < this

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


def default_speaking_min(total_min):
    return max(1, min(SPEAKING_MIN, total_min))


def lecture_language(manifest):
    """The lecture's teaching language code (en-IN, te-IN, ...)."""
    code = (manifest or {}).get("language") or DEFAULT_LANGUAGE
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def language_name(code):
    return LANGUAGES.get(code, LANGUAGES[DEFAULT_LANGUAGE])[0]


def lecture_voice(manifest):
    """The Gnani voice a lecture speaks with: the teacher's pick if it suits the lecture's language, else the default."""
    language = lecture_language(manifest)
    chosen = (manifest or {}).get("voice", "")
    return chosen if chosen in LANGUAGE_VOICES.get(language, []) else language_voice(language)


def voice_gender(manifest):
    """"female" or "male": who the lecture's voice sounds like (the browser voice, without Gnani, is a woman's)."""
    return "male" if lecture_voice(manifest) in MALE_VOICES else "female"


def language_voice(code):
    """The Gnani voice for a language: TTS_VOICE_<CODE> in .env, else TTS_VOICE for English, else the default."""
    custom = os.getenv("TTS_VOICE_" + code.replace("-", "_").upper(), "").strip()
    if custom:
        return custom
    return TTS_VOICE if code == "en-IN" else LANGUAGES.get(code, LANGUAGES["en-IN"])[1]


def class_minutes(lesson_min):
    """The class clock for a lesson of lesson_min minutes: the lesson plus room for doubts (a third more, at least 5
    minutes), so a student who asks questions isn't hurried to the recap."""
    import math
    return math.ceil((lesson_min or 0) + max(5, (lesson_min or 0) / 3))


def lecture_times(manifest):
    """(total lecture minutes, speaking minutes) of a lecture. The total runs the class clock; only the speaking
    time goes to the script writer."""
    total = manifest.get("duration_min") or LECTURE_DURATION_MIN
    speaking = manifest.get("speaking_min") or default_speaking_min(total)
    return total, min(speaking, total)
