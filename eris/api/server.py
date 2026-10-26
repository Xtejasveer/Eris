"""Web backend: a thin HTTP layer over the existing pipeline. Start with: python main.py serve

The browser runs the class player (it is where the audio plays, so it is the right place to
keep narration and actions in order). The backend only does work the browser can't:
generate, approve, TTS, running code, recovery lines and doubt-agent turns.
"""

import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from eris import config
from eris.api import jobs
from main import LECTURE_ID_RE
from eris.persona import REQUIRED, parse_persona, persona_to_markdown
from eris.generate.script_parser import parse_script
from eris.generate.script_writer import approve_script, count_slides
from eris.platform import access
from eris.platform.auth import user_from_request

app = FastAPI(title="AI Substitute Teacher")


@app.on_event("startup")
def _claim_lectures():
    try:
        access.claim_lectures()  # every lecture records its teacher (see access.claim_lectures)
    except Exception as e:
        print(f"[startup] could not record lecture owners: {e}")

# Every /api route needs a signed-in user, except signing in itself. Lecture routes need the lecture's teacher;
# a student may use only the class-time routes, and only for a lecture shared with a course they are in.
PUBLIC_API = re.compile(r"^/api/auth/(login|signup|logout|demo)$")
LECTURE_PATH = re.compile(r"^/api/lectures/([^/]+)(/.*)?$")
STUDENT_LECTURE_ROUTES = re.compile(r"^/(visuals/[^/]+|images/[^/]+|slides/[^/]+|doubts/(start|ask|reply)|recovery)$")
TEACHER_ONLY = re.compile(r"^/api/(lectures|persona/template)$")


def _deny(status, message):
    return JSONResponse({"detail": message}, status_code=status)


@app.middleware("http")
async def auth_gate(request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not PUBLIC_API.match(path):
        user = user_from_request(request)
        if not user:
            return _deny(401, "Please sign in")
        request.state.user = user
        m = LECTURE_PATH.match(path)
        if m:
            lecture_id, rest = m.group(1), m.group(2) or ""
            if user["role"] == "teacher":
                if not access.teacher_owns_lecture(user, lecture_id):
                    return _deny(403, "This lecture belongs to another teacher")
            elif not (STUDENT_LECTURE_ROUTES.match(rest) and access.student_can_play_lecture(user, lecture_id)):
                return _deny(403, "This lesson hasn't been shared with you")
        elif TEACHER_ONLY.match(path) and user["role"] != "teacher":
            return _deny(403, "Only teachers can do this")
    return await call_next(request)


@app.middleware("http")
async def no_stale_frontend(request, call_next):
    """Make the browser re-check web/ files on every load, so a code update shows after a refresh."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response

UPLOAD_TYPES = {".pptx", ".pdf", ".docx", ".txt", ".md"}
MAX_UPLOAD_MB = 25


def _check_id(lecture_id):
    if not LECTURE_ID_RE.match(lecture_id):
        raise HTTPException(400, "Lecture id: 3-63 letters, digits, _ or -")
    return lecture_id


def _manifest_or_none(lecture_id):
    path = config.manifest_path(lecture_id)
    return config.load_manifest(lecture_id) if path.exists() else None


# ---------- home ----------

@app.get("/api/persona/template")
def persona_template():
    values = parse_persona("templates/persona.md")  # the example persona, kept apart from any lecture
    return {"fields": REQUIRED, "values": values, "topic": "", "duration_min": config.LECTURE_DURATION_MIN,
            "speaking_min": config.default_speaking_min(config.LECTURE_DURATION_MIN),
            "language": config.DEFAULT_LANGUAGE, "languages": _languages(), "gnani": bool(config.GNANI_API_KEY)}


def _languages():
    """Each teaching language, its Gnani voices (Studio's voice picker), its default voice and a sample line."""
    return [{"code": code, "name": name, "voices": config.LANGUAGE_VOICES.get(code, []),
             "default_voice": config.language_voice(code), "sample": config.VOICE_SAMPLES.get(code, "")}
            for code, (name, _) in config.LANGUAGES.items()]


def _check_language(code):
    if code not in config.LANGUAGES:
        raise HTTPException(400, f"Unsupported language {code}")
    return code


def _check_times(total, speaking):
    if not 5 <= total <= 120:
        raise HTTPException(400, "Total lecture time must be 5 to 120 minutes")
    if not 1 <= speaking <= total:
        raise HTTPException(400, "Speaking time must be at least 1 minute and no more than the total lecture time")


@app.get("/api/lectures")
def list_lectures(request: Request):
    """The signed-in teacher's lectures: those in their courses, plus any made before courses existed."""
    root = Path(config.DATA_ROOT)
    ids = sorted(p.name for p in root.iterdir() if p.is_dir() and LECTURE_ID_RE.match(p.name))
    user = request.state.user
    out = []
    for i in ids:
        if access.teacher_owns_lecture(user, i):
            out.append({"id": i, "status": (_manifest_or_none(i) or {}).get("status", "new"),
                        "in_course": access.course_of_lecture(i) is not None})
    return out


class NewLecture(BaseModel):
    topic: str
    duration_min: int = 30
    speaking_min: int = 20
    language: str = config.DEFAULT_LANGUAGE


@app.post("/api/lectures/{lecture_id}")
def create_lecture(lecture_id: str, body: NewLecture):
    """A new lecture: the teacher names its topic and length once, at the start (saved in lecture.json)."""
    _check_id(lecture_id)
    if not body.topic.strip():
        raise HTTPException(400, "Enter the lecture topic")
    _check_times(body.duration_min, body.speaking_min)
    _check_language(body.language)
    if _manifest_or_none(lecture_id) or config.data_dir(lecture_id).is_dir():
        raise HTTPException(409, f"A lecture called {lecture_id} already exists")
    config.data_dir(lecture_id).mkdir(parents=True)
    config.save_manifest(lecture_id, {"lecture_id": lecture_id, "topic": body.topic.strip(),
                                      "duration_min": body.duration_min, "speaking_min": body.speaking_min,
                                      "language": body.language, "status": "new"})
    return {"id": lecture_id}


class LectureSetup(BaseModel):
    persona: dict
    topic: str = ""
    duration_min: int = 30
    speaking_min: int = 20
    language: str = ""
    voice: str = ""   # a Gnani voice for the language ("" = the language's default)


@app.put("/api/lectures/{lecture_id}/setup")
def save_setup(lecture_id: str, body: LectureSetup):
    """Studio saves the teacher's fields as they are typed (also half-filled), so nothing is lost before Generate."""
    folder = config.data_dir(_check_id(lecture_id))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "persona.md").write_text(persona_to_markdown(body.persona), encoding="utf-8")
    manifest = _manifest_or_none(lecture_id) or {"lecture_id": lecture_id, "status": "new"}
    if body.topic.strip():
        manifest["topic"] = body.topic.strip()
    if 5 <= body.duration_min <= 120 and 1 <= body.speaking_min <= body.duration_min:  # half-typed values wait
        manifest["duration_min"], manifest["speaking_min"] = body.duration_min, body.speaking_min
    if body.language in config.LANGUAGES:
        manifest["language"] = body.language
    if body.voice in config.LANGUAGE_VOICES.get(config.lecture_language(manifest), []):
        manifest["voice"] = body.voice
    else:
        manifest.pop("voice", None)  # a voice for another language: back to this language's default
    config.save_manifest(lecture_id, manifest)
    return {"saved": True, "voice": config.lecture_voice(manifest)}


@app.get("/api/lectures/{lecture_id}")
def get_lecture(lecture_id: str):
    _check_id(lecture_id)
    folder = config.data_dir(lecture_id)
    files = sorted(p.name for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
    script_md = config.lecture_dir(lecture_id) / "script.md"
    failed_md = config.lecture_dir(lecture_id) / "script_failed.md"
    # Show the last failed draft when it is newer than script.md, so the teacher can fix it here.
    failed = failed_md.exists() and (not script_md.exists()
                                     or failed_md.stat().st_mtime > script_md.stat().st_mtime)
    source = failed_md if failed else script_md
    text = source.read_text(encoding="utf-8") if source.exists() else ""
    segments, errors = parse_script(text, count_slides(lecture_id)) if text else ([], [])
    persona = None
    if (folder / "persona.md").exists():
        try:
            persona = parse_persona(folder / "persona.md", strict=False)  # Studio shows a half-filled one too
        except ValueError:
            persona = None
    judge_json = config.lecture_dir(lecture_id) / "judge.json"
    judge = None
    if judge_json.exists() and not failed:
        try:
            judge = json.loads(judge_json.read_text(encoding="utf-8"))
        except ValueError:
            judge = None
    return {"id": lecture_id, "manifest": _manifest_or_none(lecture_id), "files": files, "judge": judge,
            "persona": persona, "script_md": text, "segments": segments, "errors": errors, "failed_draft": failed,
            "job": jobs.get_job(lecture_id), "course": access.course_of_lecture(lecture_id),
            "model": config.model_name(config.LLM_MODEL),  # writes the next script
            "script_model": config.model_name((_manifest_or_none(lecture_id) or {}).get("llm_model") or config.LLM_MODEL)}


@app.post("/api/lectures/{lecture_id}/files")
async def upload_files(lecture_id: str, files: list[UploadFile]):
    folder = config.data_dir(_check_id(lecture_id))
    folder.mkdir(parents=True, exist_ok=True)
    saved, skipped = [], []
    for f in files:
        name = Path(f.filename or "").name
        data = await f.read()
        if Path(name).suffix.lower() not in UPLOAD_TYPES or name == "persona.md":
            skipped.append(f"{name}: unsupported type")
        elif len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            skipped.append(f"{name}: larger than {MAX_UPLOAD_MB} MB")
        else:
            (folder / name).write_bytes(data)
            saved.append(name)
    return {"saved": saved, "skipped": skipped}


@app.delete("/api/lectures/{lecture_id}/files/{name}")
def delete_file(lecture_id: str, name: str):
    path = config.data_dir(_check_id(lecture_id)) / Path(name).name
    if path.name == "persona.md" or not path.is_file():
        raise HTTPException(404, "File not found")
    path.unlink()
    return {"ok": True}


class GenerateRequest(BaseModel):
    persona: dict
    topic: str
    duration_min: int = 30
    speaking_min: int = 20
    language: str = ""


@app.post("/api/lectures/{lecture_id}/generate")
def generate(lecture_id: str, body: GenerateRequest):
    folder = config.data_dir(_check_id(lecture_id))
    folder.mkdir(parents=True, exist_ok=True)
    if not body.topic.strip():
        raise HTTPException(400, "Enter the lecture topic")
    _check_times(body.duration_min, body.speaking_min)
    if body.language:  # the script is written, said and heard in this language (kept through the re-index)
        manifest = _manifest_or_none(lecture_id) or {"lecture_id": lecture_id, "status": "new"}
        manifest["language"] = _check_language(body.language)
        config.save_manifest(lecture_id, manifest)
    (folder / "persona.md").write_text(persona_to_markdown(body.persona), encoding="utf-8")
    try:
        parse_persona(folder / "persona.md")
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not jobs.start_generate(lecture_id, body.topic.strip(), body.duration_min, body.speaking_min):
        raise HTTPException(409, "A generation is already running for this lecture")
    return {"started": True}


@app.get("/api/lectures/{lecture_id}/job")
def job_status(lecture_id: str):
    return jobs.get_job(_check_id(lecture_id))


class ScriptRequest(BaseModel):
    text: str


@app.put("/api/lectures/{lecture_id}/script")
def save_script(lecture_id: str, body: ScriptRequest):
    from eris.api.server_class import manifest_or_404
    manifest = manifest_or_404(_check_id(lecture_id))
    (config.lecture_dir(lecture_id) / "script.md").write_text(body.text.rstrip() + "\n", encoding="utf-8")
    if manifest.get("status") != "draft":
        manifest["status"] = "draft"  # A saved (edited) script must be approved again.
        config.save_manifest(lecture_id, manifest)
    segments, errors = parse_script(body.text, count_slides(lecture_id))
    return {"segments": segments, "errors": errors, "status": manifest["status"]}


class SectionRewrite(BaseModel):
    section: str
    feedback: str = ""


@app.post("/api/lectures/{lecture_id}/regenerate-section")
def regenerate_section(lecture_id: str, body: SectionRewrite):
    """Rewrite one section from students' feedback. The lecture becomes a draft: the teacher reviews and approves it."""
    from eris.api.server_class import manifest_or_404
    from eris.generate.section_rewrite import rewrite_section
    manifest = manifest_or_404(_check_id(lecture_id))
    if jobs.get_job(lecture_id)["status"] == "running":
        raise HTTPException(409, "A generation is running for this lecture; wait for it to finish")
    try:
        text = rewrite_section(lecture_id, body.section, body.feedback)
    except ValueError as e:
        raise HTTPException(400, str(e))
    (config.lecture_dir(lecture_id) / "script.md").write_text(text.rstrip() + "\n", encoding="utf-8")
    manifest["status"] = "draft"  # the class keeps its version until the teacher approves this one
    config.save_manifest(lecture_id, manifest)
    return {"ok": True, "status": "draft"}


@app.post("/api/lectures/{lecture_id}/approve")
def approve(lecture_id: str):
    from eris.api.server_class import manifest_or_404
    manifest_or_404(_check_id(lecture_id))  # approve_script would exit the process without one
    errors = approve_script(lecture_id)
    if errors:
        return {"ok": False, "errors": errors}
    from eris.api.server_platform import on_approved
    from eris.material.slide_images import render_later
    render_later(lecture_id)  # the class shows the real slides: draw them now, not when the first student opens it
    return {"ok": True, "errors": [], "lesson_version": on_approved(lecture_id)}


@app.post("/api/lectures/{lecture_id}/reset")
def reset_lecture(lecture_id: str):
    """Clear the knowledge base (Chroma collection) and everything generated for this lecture.

    Keeps the study material and persona in data/<id>/, so Generate can start again from scratch.
    """
    _check_id(lecture_id)
    if jobs.get_job(lecture_id)["status"] == "running":
        raise HTTPException(409, "A generation is running for this lecture; wait for it to finish")
    import shutil

    import chromadb
    from eris.api.server_class import forget_lecture

    try:
        chromadb.PersistentClient(path=config.CHROMA_DIR).delete_collection(lecture_id)
    except Exception:
        pass  # No collection yet.
    shutil.rmtree(config.lecture_dir(lecture_id), ignore_errors=True)
    forget_lecture(lecture_id)
    jobs.clear_job(lecture_id)
    print(f"[reset] cleared knowledge base and generated files for '{lecture_id}'")
    return {"ok": True}


from eris.api.server_class import router as class_router  # noqa: E402  (class routes live in their own file)

app.include_router(class_router)
from eris.api.server_platform import router as platform_router  # noqa: E402  (courses, sign-in, attendance)

app.include_router(platform_router)
if Path("web").is_dir():  # the frontend is optional; the API works without it
    app.mount("/", StaticFiles(directory="web", html=True), name="web")
