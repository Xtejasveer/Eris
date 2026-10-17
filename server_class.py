"""Class-time routes: script for the player, TTS, running code, recovery lines and doubt turns."""

import json
import re
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import actions
import class_board
import config
import doubt_agent
from main import LECTURE_ID_RE
from recovery import recovery_line
from script_writer import count_slides
from tools import program_output, run_code_file, set_board, set_lecture

router = APIRouter(prefix="/api")

CODE_FILE_RE = re.compile(r"^[A-Za-z0-9_-]+\.py$")
_agents = {}        # lecture_id -> (doubt agent, log path); built once per server run
_doubt_counts = {}  # thread_id -> {"asked": int, "max": int, "section": str, "board": dict}
# What earlier doubt answers added to the screen in the current class run (notes, answer1.py, ...).
_answer_extras = {}  # lecture_id -> {"cursor": int, "segments": [segment, ...]}
_slides = {}         # lecture_id -> {slide number: text}


def forget_lecture(lecture_id):
    """Drop cached doubt agents and search handles after a reset."""
    _agents.pop(lecture_id, None)
    _answer_extras.pop(lecture_id, None)
    _slides.pop(lecture_id, None)
    set_lecture(lecture_id)  # also clears the cached vector store


def manifest_or_none(lecture_id):
    if not config.manifest_path(lecture_id).exists():
        return None
    try:
        return config.load_manifest(lecture_id)
    except SystemExit:  # broken lecture.json: config printed why
        raise HTTPException(500, f"workspace/lectures/{lecture_id}/lecture.json is not valid JSON")


def manifest_or_404(lecture_id):
    """lecture.json for a web request. (config.load_manifest exits the process, which a server must not do.)"""
    if not config.manifest_path(lecture_id).exists():
        raise HTTPException(404, f"Lecture '{lecture_id}' has no generated script yet")
    return manifest_or_none(lecture_id)


def _check_id(lecture_id):
    if not LECTURE_ID_RE.match(lecture_id):
        raise HTTPException(400, "Bad lecture id")
    return lecture_id


@router.get("/lectures/{lecture_id}/class")
def class_data(lecture_id: str):
    """Everything the browser player needs: segments, slides and who is teaching.

    A lecture that isn't approved yet is a normal state, not an error: the answer says why
    (ready=false) and the Class page shows it.
    """
    _check_id(lecture_id)
    script_json = config.lecture_dir(lecture_id) / "script.json"
    status = (manifest_or_none(lecture_id) or {}).get("status", "new")
    if status not in ("approved", "completed") or not script_json.exists():
        reasons = {
            "new": "No script yet. Go to Home, upload material and click Generate.",
            "indexed": "The material is indexed but there is no approved script. On Home, generate "
                       "(or fix the failed draft) and click Approve.",
            "draft": "The script is a draft. Review it on Home and click Approve.",
        }
        return {"ready": False, "status": status, "message": reasons.get(status, "Approve the script on Home first.")}
    manifest = manifest_or_none(lecture_id)
    return {"ready": True, "segments": json.loads(script_json.read_text(encoding="utf-8")),
            "slides": actions.new_board(lecture_id)["slides"],
            "teacher": manifest["persona"]["Teacher"]["Name"], "topic": manifest["topic"],
            "estimated_min": manifest.get("estimated_min"), "voice": bool(config.GNANI_API_KEY)}


@router.post("/lectures/{lecture_id}/complete")
def complete(lecture_id: str):
    manifest = manifest_or_404(_check_id(lecture_id))
    manifest["status"] = "completed"
    config.save_manifest(lecture_id, manifest)
    return {"ok": True}


class TTSRequest(BaseModel):
    lecture_id: str
    text: str


@router.post("/tts")
def tts(body: TTSRequest):
    """WAV narration from Gnani (cached). 204 = no voice available: the browser uses its own speech."""
    _check_id(body.lecture_id)
    if not config.GNANI_API_KEY or not body.text.strip():
        return Response(status_code=204)
    try:
        import voice
        return FileResponse(voice.ensure_clip(body.lecture_id, body.text), media_type="audio/wav")
    except Exception as e:
        print(f"[tts] Gnani failed, browser voice will be used: {e}")
        return Response(status_code=204, headers={"X-TTS-Error": str(e)[:200]})


class RunRequest(BaseModel):
    file: str
    code: str


@router.post("/lectures/{lecture_id}/run")
def run_code(lecture_id: str, body: RunRequest):
    """Run one board file for real, in workspace/lectures/<id>/board/."""
    if not CODE_FILE_RE.match(body.file):
        raise HTTPException(400, "File must be a simple name ending in .py")
    folder = config.lecture_dir(_check_id(lecture_id)) / "board"
    folder.mkdir(exist_ok=True)
    exit_code, stdout, stderr = run_code_file(body.code, body.file, folder=folder.resolve())
    return {"exit_code": exit_code, "stdout": stdout, "stderr": stderr,
            "output": program_output(exit_code, stdout, stderr)}


class RecoveryRequest(BaseModel):
    segment: dict
    error: str
    state_text: str = ""


@router.post("/lectures/{lecture_id}/recovery")
def recovery(lecture_id: str, body: RecoveryRequest):
    manifest = manifest_or_404(_check_id(lecture_id))
    teacher = manifest["persona"]["Teacher"]["Name"]
    return {"line": recovery_line(teacher, body.state_text, body.segment, body.error)}


def _agent(lecture_id):
    if lecture_id not in _agents:
        from session import start_doubts
        _agents[lecture_id] = start_doubts(lecture_id, manifest_or_404(lecture_id))
    set_lecture(lecture_id)  # search_material reads the current lecture
    return _agents[lecture_id]


class DoubtStart(BaseModel):
    context: str
    section: str = "Lecture"
    final: bool = False
    cursor: int | None = None  # index of the DOUBT_CHECK segment: the board is rebuilt up to here


def _board_at(lecture_id, cursor):
    """The class screen at `cursor`: the approved script so far plus earlier doubt answers in this run."""
    script_json = config.lecture_dir(lecture_id) / "script.json"
    segments = json.loads(script_json.read_text(encoding="utf-8")) if script_json.exists() else []
    cursor = len(segments) if cursor is None else cursor
    extras = _answer_extras.get(lecture_id)
    if extras is None or cursor < extras["cursor"]:  # a new run (or a jump back): earlier answers are gone
        extras = _answer_extras[lecture_id] = {"cursor": cursor, "segments": []}
    extras["cursor"] = cursor
    board = class_board.rebuild(segments, cursor)
    return class_board.add_segments(board, extras["segments"])


def _remember_answer(lecture_id, board, turn):
    """Answers change the screen; later answers (and quotes) must see that."""
    played = turn.get("reply_segments", []) + turn.get("final_segments", [])
    class_board.add_segments(board, played)
    if lecture_id in _answer_extras:
        _answer_extras[lecture_id]["segments"].extend(played)


def _slides_for(lecture_id):
    if lecture_id not in _slides:
        _slides[lecture_id] = actions.new_board(lecture_id)["slides"]
    return _slides[lecture_id]


class DoubtReply(BaseModel):
    thread_id: str
    answer: str


@router.post("/lectures/{lecture_id}/doubts/start")
def doubts_start(lecture_id: str, body: DoubtStart):
    agent, _ = _agent(_check_id(lecture_id))
    thread_id = f"web_{lecture_id}_{uuid.uuid4().hex[:8]}"
    limit = config.MAX_DOUBTS_FINAL if body.final else config.MAX_DOUBTS_PER_CHECK
    board = _board_at(lecture_id, body.cursor)
    _doubt_counts[thread_id] = {"asked": 0, "max": limit, "section": body.section, "board": board}
    set_board(board, _slides_for(lecture_id))
    try:
        turn = doubt_agent.with_segments(
            doubt_agent.turn_start(agent, thread_id, body.context + "\n\nNow ask the class for doubts."),
            count_slides(lecture_id), board)
    except Exception as e:
        raise HTTPException(502, f"Doubt agent failed: {e}")
    _remember_answer(lecture_id, board, turn)
    return {"thread_id": thread_id, "max": limit, **turn}


@router.post("/lectures/{lecture_id}/doubts/reply")
def doubts_reply(lecture_id: str, body: DoubtReply):
    agent, log_path = _agent(_check_id(lecture_id))
    count = _doubt_counts.get(body.thread_id)
    if count is None:
        raise HTTPException(404, "Unknown doubt session")
    answer = body.answer.strip()
    if count["asked"] >= count["max"]:
        answer = "no more doubts"  # Limit reached: tell the agent to wrap up.
    elif answer.lower() not in doubt_agent.NO_DOUBT_WORDS:
        count["asked"] += 1
    set_board(count["board"], _slides_for(lecture_id))
    try:
        turn = doubt_agent.with_segments(
            doubt_agent.turn_reply(agent, body.thread_id, answer, log_path, count["section"]),
            count_slides(lecture_id), count["board"])
    except Exception as e:
        raise HTTPException(502, f"Doubt agent failed: {e}")
    _remember_answer(lecture_id, count["board"], turn)
    return {"asked": count["asked"], "max": count["max"], **turn}
