"""Class-time routes: script for the player, TTS, running code, recovery lines and doubt turns."""

import json
import re
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

import actions
import class_board
import config
import doubt_agent
import figures
from main import LECTURE_ID_RE
from recovery import recovery_line
from script_writer import count_slides
from script_fixes import drop_visual
from tools import program_output, run_code_file, set_board, set_lecture
import visual_builder

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
            "estimated_min": manifest.get("estimated_min"), "voice": bool(config.GNANI_API_KEY),
            "avatar": {"enabled": config.AVATAR_ENABLED, "model_url": config.AVATAR_MODEL_URL or None}}


@router.get("/lectures/{lecture_id}/visuals/{key}")
def visual_page(lecture_id: str, key: str):
    """One built visual as a full page, loaded into a sandboxed frame (scripts only: no same-origin access,
    no network). The control panel and messaging come from web/js/visual/runtime.js."""
    visual = visual_builder.load_visual(_check_id(lecture_id), key)
    if visual is None:
        raise HTTPException(404, "Visual not found")
    return HTMLResponse(visual_builder.wrap_document(visual), headers={
        "Content-Security-Policy": visual_builder.CSP + "; sandbox allow-scripts",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"})


def _check_answer_flows(lecture_id, turn):
    """A new diagram in an answer must draw a process from the material; otherwise it is left out."""
    figs = figures.load(lecture_id)
    for seg in [x for x in turn.get("reply_segments", []) if x.get("name") == "FLOW"]:
        if not figures.matches(seg["args"].get("from"), figs, kind="flow"):
            print(f"[doubts] left out the diagram '{seg['args']['id']}': no matching diagram or step list in the material")
            turn["reply_segments"] = visual_builder.drop_visual_segments(turn["reply_segments"], [seg["args"]["id"]])
            turn["reply"] = drop_visual(turn.get("reply", ""), seg["args"]["id"], block="FLOW")


def _build_answer_visuals(lecture_id, turn):
    """A doubt answer may draw a new visual: build it now (the student waits), or leave it out."""
    _check_answer_flows(lecture_id, turn)
    segments = turn.get("reply_segments", [])
    if not any(s.get("name") == "VISUAL" for s in segments):
        return
    topic = (manifest_or_none(lecture_id) or {}).get("topic", "")
    figs = figures.load(lecture_id)
    for seg in [x for x in segments if x.get("name") == "VISUAL"]:  # only graphs from the material
        if not figures.matches(seg["args"].get("from"), figs):
            print(f"[doubts] left out the visual '{seg['args']['id']}': no matching graph in the material")
            segments = visual_builder.drop_visual_segments(segments, [seg["args"]["id"]])
            turn["reply"] = drop_visual(turn.get("reply", ""), seg["args"]["id"])
    turn["reply_segments"] = segments
    failed = visual_builder.ensure_visuals(segments, lecture_id, topic, config.MAX_ANSWER_VISUALS,
                                           board_files=turn.get("_board_files"))
    for vid, reason in failed:
        print(f"[doubts] left out the visual '{vid}': {reason[:200]}")
    if failed:
        turn["reply_segments"] = visual_builder.drop_visual_segments(segments, [vid for vid, _ in failed])
        for vid, _ in failed:
            turn["reply"] = drop_visual(turn.get("reply", ""), vid)


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
    question: str = ""         # the player asked the class and a student asked this (else the agent asks)


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
    board["figures"] = figures.load(lecture_id)  # the material's graphs: the only ones an answer may build
    # Doubts use only what this class used: notebook and slides always, code and graphs if the lecture had them.
    used = figures.env_from_segments(segments)
    board["environments"] = {**used, "notebook": True, "slides": bool(_slides_for(lecture_id))}
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
    question = body.question.strip()
    if question:
        _doubt_counts[thread_id]["asked"] = 1
    try:
        if question:
            _, log_path = _agent(lecture_id)
            turn = doubt_agent.turn_question(agent, thread_id, body.context, question, log_path, body.section)
        else:
            turn = doubt_agent.turn_start(agent, thread_id, body.context + "\n\nNow ask the class for doubts.")
        turn = doubt_agent.with_segments(turn, count_slides(lecture_id), board)
        turn["_board_files"] = board.get("files", {})
        _build_answer_visuals(lecture_id, turn)
        turn.pop("_board_files", None)
    except Exception as e:
        raise HTTPException(502, f"Doubt agent failed: {e}")
    _remember_answer(lecture_id, board, turn)
    return {"thread_id": thread_id, "max": limit, "asked": 1 if question else 0, **turn}


class DoubtAsk(BaseModel):
    question: str
    context: str = ""            # the class snapshot (sent every time; used when the break changed)
    section: str = "Lecture"
    final: bool = False
    cursor: int | None = None
    thread_id: str | None = None  # the class's conversation from an earlier question; None = a new class run
    visuals: str = ""            # what each visual on screen shows now (its Visual.state line), from the player


_class_threads = {}  # thread_id -> {"lecture": id, "cursor": int, "notes": [str]}  (one conversation per class run)


SLIDE_REQUEST_RE = re.compile(r"\b(slides?|deck|ppt|powerpoint|presentation)\b", re.I)


def _show_slide_if_asked(question, board, turn, slides):
    """A student asked to see the slides but the answer shows none: show the slide for the current topic."""
    if not slides or not SLIDE_REQUEST_RE.search(question):
        return
    if any(s.get("name") in ("SLIDE", "SLIDE_HIGHLIGHT") for s in turn.get("reply_segments", [])):
        return
    in_section = [n for section, n in board["slides_shown"] if section == board["section"]]
    n = (in_section or [board.get("current_slide")])[-1] or min(slides, key=int)
    turn["reply_segments"] = [{"kind": "action", "name": "SLIDE", "args": {"n": int(n)}}] + turn.get("reply_segments", [])
    print(f"[doubts] the student asked for the slides and the answer showed none: showing slide {n}")


def _output_notes(turn):
    """What the programs in this answer really printed: told to the agent with the next question."""
    notes = []
    for seg in turn.get("reply_segments", []):
        if seg.get("name") == "RUN":
            out = seg.get("expected_output", "").strip() or "(no output)"
            notes.append(f"{seg['args']['cmd']} was run on the class screen and printed:\n{out[:600]}")
    return notes


@router.post("/lectures/{lecture_id}/doubts/ask")
def doubts_ask(lecture_id: str, body: DoubtAsk):
    """One student question. The whole class run shares ONE agent conversation (thread_id), so the agent
    remembers its earlier answers, programs and outputs across questions and question breaks."""
    agent, log_path = _agent(_check_id(lecture_id))
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Empty question")
    thread = _class_threads.get(body.thread_id or "")
    if thread is None or thread["lecture"] != lecture_id:
        thread_id = f"class_{lecture_id}_{uuid.uuid4().hex[:8]}"
        thread = _class_threads[thread_id] = {"lecture": lecture_id, "cursor": None, "notes": []}
    else:
        thread_id = body.thread_id
    board = _board_at(lecture_id, body.cursor)
    set_board(board, _slides_for(lecture_id))
    parts = []
    if thread["cursor"] != body.cursor:  # a new question break: where the class is now
        parts.append(body.context)
        thread["cursor"] = body.cursor
    if thread["notes"]:
        parts.append("Notes from the class screen since your last answer:\n" + "\n\n".join(thread["notes"]))
        thread["notes"] = []
    if board.get("latest_file"):  # "run this code" = this one (models otherwise guess an older program)
        parts.append(f"The most recent program on the class screen is {board['latest_file']}.")
    parts.append("Environments in this class: " + figures.describe_environments(board["environments"]))
    if body.visuals.strip():  # students may have moved the controls themselves
        parts.append("What the graphs and diagrams on the class screen show right now:\n" + body.visuals.strip()[:1500])
    try:
        turn = doubt_agent.turn_ask(agent, thread_id, question, log_path, body.section, "\n\n".join(parts))
        turn = doubt_agent.with_segments(turn, count_slides(lecture_id), board)
        turn["_board_files"] = board.get("files", {})
        _build_answer_visuals(lecture_id, turn)
        turn.pop("_board_files", None)
    except Exception as e:
        raise HTTPException(502, f"Doubt agent failed: {e}")
    _show_slide_if_asked(question, board, turn, _slides_for(lecture_id))
    _remember_answer(lecture_id, board, turn)
    thread["notes"] += _output_notes(turn)
    limit = config.MAX_DOUBTS_FINAL if body.final else config.MAX_DOUBTS_PER_CHECK
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
        turn["_board_files"] = count["board"].get("files", {})
        _build_answer_visuals(lecture_id, turn)
        turn.pop("_board_files", None)
    except Exception as e:
        raise HTTPException(502, f"Doubt agent failed: {e}")
    _remember_answer(lecture_id, count["board"], turn)
    return {"asked": count["asked"], "max": count["max"], **turn}
