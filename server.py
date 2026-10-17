"""Web backend: a thin HTTP layer over the existing pipeline. Start with: python main.py serve

The browser runs the class player (it is where the audio plays, so it is the right place to
keep narration and actions in order). The backend only does work the browser can't:
generate, approve, TTS, running code, recovery lines and doubt-agent turns.
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import jobs
from main import LECTURE_ID_RE
from persona import REQUIRED, parse_persona, persona_to_markdown
from script_parser import parse_script
from script_writer import approve_script, count_slides

app = FastAPI(title="AI Substitute Teacher")


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
    values = parse_persona("data/example/persona.md")
    return {"fields": REQUIRED, "values": values, "topic": config.TOPIC_NAME,
            "duration_min": config.LECTURE_DURATION_MIN}


@app.get("/api/lectures")
def list_lectures():
    root = Path(config.DATA_ROOT)
    ids = sorted(p.name for p in root.iterdir() if p.is_dir() and LECTURE_ID_RE.match(p.name))
    return [{"id": i, "status": (_manifest_or_none(i) or {}).get("status", "new")} for i in ids]


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
            persona = parse_persona(folder / "persona.md")
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
            "job": jobs.get_job(lecture_id)}


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


@app.post("/api/lectures/{lecture_id}/generate")
def generate(lecture_id: str, body: GenerateRequest):
    folder = config.data_dir(_check_id(lecture_id))
    folder.mkdir(parents=True, exist_ok=True)
    if not 5 <= body.duration_min <= 120:
        raise HTTPException(400, "Duration must be 5 to 120 minutes")
    (folder / "persona.md").write_text(persona_to_markdown(body.persona), encoding="utf-8")
    try:
        parse_persona(folder / "persona.md")
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not jobs.start_generate(lecture_id, body.topic.strip() or config.TOPIC_NAME, body.duration_min):
        raise HTTPException(409, "A generation is already running for this lecture")
    return {"started": True}


@app.get("/api/lectures/{lecture_id}/job")
def job_status(lecture_id: str):
    return jobs.get_job(_check_id(lecture_id))


class ScriptRequest(BaseModel):
    text: str


@app.put("/api/lectures/{lecture_id}/script")
def save_script(lecture_id: str, body: ScriptRequest):
    from server_class import manifest_or_404
    manifest = manifest_or_404(_check_id(lecture_id))
    (config.lecture_dir(lecture_id) / "script.md").write_text(body.text.rstrip() + "\n", encoding="utf-8")
    if manifest.get("status") != "draft":
        manifest["status"] = "draft"  # A saved (edited) script must be approved again.
        config.save_manifest(lecture_id, manifest)
    segments, errors = parse_script(body.text, count_slides(lecture_id))
    return {"segments": segments, "errors": errors, "status": manifest["status"]}


@app.post("/api/lectures/{lecture_id}/approve")
def approve(lecture_id: str):
    from server_class import manifest_or_404
    manifest_or_404(_check_id(lecture_id))  # approve_script would exit the process without one
    errors = approve_script(lecture_id)
    return {"ok": not errors, "errors": errors}


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
    from server_class import forget_lecture

    try:
        chromadb.PersistentClient(path=config.CHROMA_DIR).delete_collection(lecture_id)
    except Exception:
        pass  # No collection yet.
    shutil.rmtree(config.lecture_dir(lecture_id), ignore_errors=True)
    forget_lecture(lecture_id)
    jobs.clear_job(lecture_id)
    print(f"[reset] cleared knowledge base and generated files for '{lecture_id}'")
    return {"ok": True}


from server_class import router as class_router  # noqa: E402  (class routes live in their own file)

app.include_router(class_router)
if Path("web").is_dir():  # the frontend is optional; the API works without it
    app.mount("/", StaticFiles(directory="web", html=True), name="web")
