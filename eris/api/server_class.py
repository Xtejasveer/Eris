"""Class-time routes: script for the player, TTS, running code, recovery lines and doubt turns."""

import json
import re
import threading
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

from eris.classroom import actions
from eris.classroom import class_board
from eris import config
from eris.classroom import doubt_agent
from eris.material import figures
from eris.sandbox import CODE_FILE_RE
from eris.material.slide_images import slide_images
from main import LECTURE_ID_RE
from eris.classroom.recovery import recovery_line
from eris.generate.script_writer import count_slides
from eris.generate.script_fixes import drop_visual
from eris.tools import program_output, run_code_file, set_board, set_lecture
from eris.visuals import visual_builder
router = APIRouter(prefix="/api")

_agents = {}        # lecture_id -> (doubt agent, log path); built once per server run
_doubt_counts = {}  # thread_id -> {"asked": int, "max": int, "section": str, "board": dict}
# What earlier doubt answers added to the screen in the current class run (notes, answer1.py, ...).
_answer_extras = {}  # lecture_id or a class run's thread_id -> {"cursor": int, "segments": [segment, ...]}
# The doubt agent's tools read one shared board (eris.tools.set_board), so answers are made one at a time: with many
# students in their own lessons at once, one student's board must never leak into another student's answer.
_doubt_lock = threading.Lock()
# At most a few voice clips are made at once, so a burst of requests can't tie up every server thread.
_tts_slots = threading.BoundedSemaphore(3)
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
            "slides": actions.new_board(lecture_id)["slides"], "slide_pictures": _slide_pictures(lecture_id),
            "slide_images": slide_images(lecture_id),  # the real slides as pictures, when LibreOffice can draw them
            "teacher": manifest["persona"]["Teacher"]["Name"], "topic": manifest["topic"],
            "estimated_min": manifest.get("estimated_min"), "duration_min": config.lecture_times(manifest)[0], "voice": bool(config.GNANI_API_KEY),
            "language": config.lecture_language(manifest), "voice_name": config.lecture_voice(manifest),
            "tutor": tutor_for(manifest),
            "model": config.model_name(manifest.get("llm_model") or config.LLM_MODEL),  # wrote this script
            "live_model": config.model_name(config.LLM_MODEL),  # answers doubts now
            "avatar": {"enabled": config.AVATAR_ENABLED, "model_url": config.AVATAR_MODEL_URL or None}}


def tutor_for(manifest):
    """Which video tutor the class sees (web/assets/tutor): "male" for a man's voice, "" (the default tutor) otherwise,
    so the face matches the voice."""
    return "male" if config.voice_gender(manifest) == "male" else ""


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


PICTURE_NAME_RE = re.compile(r"^[0-9a-f]{16}\.(png|jpeg|jpg|gif|webp)$")
SLIDE_NAME_RE = re.compile(r"^[0-9]{1,3}\.png$")


def _slide_pictures(lecture_id):
    """{slide number: [{url, kind, description}]}: the real pictures on each slide, shown in the Slides view."""
    from eris.material.images import load as load_pictures
    out = {}
    for p in load_pictures(lecture_id):
        if p.get("slide"):
            out.setdefault(str(p["slide"]), []).append({
                "url": f"/api/lectures/{lecture_id}/images/{p['key']}.{p['ext']}",
                "kind": p.get("kind", "picture"), "description": p.get("description", "")})
    return out


@router.get("/lectures/{lecture_id}/images/{name}")
def picture_file(lecture_id: str, name: str):
    """One picture taken from the teacher's material (saved at index time)."""
    if not PICTURE_NAME_RE.match(name):
        raise HTTPException(400, "Bad picture name")
    path = config.lecture_dir(_check_id(lecture_id)) / "images" / name
    if not path.exists():
        raise HTTPException(404, "Picture not found")
    return FileResponse(path, headers={"Cache-Control": "max-age=86400"})


@router.get("/lectures/{lecture_id}/slides/{name}")
def slide_file(lecture_id: str, name: str):
    """One slide of the teacher's deck as a picture (see material/slide_images.py)."""
    if not SLIDE_NAME_RE.match(name):
        raise HTTPException(400, "Bad slide name")
    path = config.lecture_dir(_check_id(lecture_id)) / "slides" / name
    if not path.exists():
        raise HTTPException(404, "Slide not found")
    return FileResponse(path, headers={"Cache-Control": "no-cache"})  # a new deck draws over the same names


@router.post("/lectures/{lecture_id}/complete")
def complete(lecture_id: str):
    manifest = manifest_or_404(_check_id(lecture_id))
    manifest["status"] = "completed"
    config.save_manifest(lecture_id, manifest)
    return {"ok": True}


def _check_user(request, lecture_id):
    _check_id(lecture_id)
    from eris.platform import access
    if not access.can_use_lecture(request.state.user, lecture_id):
        raise HTTPException(403, "You do not have access to this lesson")


def _audio(path):
    """A voice clip for the browser: the small AAC copy when there is one, else the WAV."""
    return FileResponse(path, media_type="audio/mp4" if path.suffix == ".m4a" else "audio/wav")


class TTSRequest(BaseModel):
    lecture_id: str
    text: str


@router.post("/tts")
def tts(body: TTSRequest, request: Request):
    """WAV narration from Gnani (cached). 204 = no voice available: the browser uses its own speech."""
    _check_user(request, body.lecture_id)
    if not config.GNANI_API_KEY or not body.text.strip():
        return Response(status_code=204)
    from eris.classroom import voice
    clip = voice.clip_path(body.lecture_id, body.text)
    if clip.exists() and clip.stat().st_size > 44:  # made already (shared lessons are made ahead): no waiting
        return _audio(voice.web_clip(clip))
    if not _tts_slots.acquire(timeout=30):
        return Response(status_code=204, headers={"X-TTS-Error": "voice busy"})
    try:
        return _audio(voice.web_clip(voice.ensure_clip(body.lecture_id, body.text)))
    except Exception as e:
        print(f"[tts] Gnani failed, browser voice will be used: {e}")  # the details stay in the server log
        return Response(status_code=204, headers={"X-TTS-Error": "voice unavailable"})
    finally:
        _tts_slots.release()


@router.post("/tts/timing")
def tts_timing(body: TTSRequest, request: Request):
    """Word timings of a clip /tts already made, for the avatar's lip sync. 204 = none (lips follow the audio)."""
    _check_user(request, body.lecture_id)
    from eris.classroom import voice
    clip = voice.clip_path(body.lecture_id, body.text)
    if not body.text.strip() or not clip.exists():
        return Response(status_code=204)
    data = voice.ensure_timing(clip, body.text)
    return data if data else Response(status_code=204)


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


def _runs_code(request):
    """May this person's doubts get answers whose programs run on the server? Teachers yes; students only when
    ERIS_STUDENT_CODE_RUNS is on (a student could word a doubt to make the agent run code)."""
    return request.state.user["role"] == "teacher" or config.STUDENT_CODE_RUNS


def _agent(lecture_id, run_code=True):
    """The lecture's doubt agent; one without the tool that runs programs for those who may not run code."""
    key = (lecture_id, run_code)
    if key not in _agents:
        from eris.classroom.session import start_doubts
        _agents[key] = start_doubts(lecture_id, manifest_or_404(lecture_id), run_code=run_code)
    set_lecture(lecture_id)  # search_material reads the current lecture
    return _agents[key]


def _owned(thread, request):
    """A doubt thread belongs to the person who started it; nobody else may continue it, whatever id they send."""
    return thread is not None and thread.get("user") == request.state.user["id"]


AGENT_DOWN = "The doubt helper is unavailable right now. Please try again in a moment."


class DoubtStart(BaseModel):
    context: str
    section: str = "Lecture"
    final: bool = False
    cursor: int | None = None  # index of the DOUBT_CHECK segment: the board is rebuilt up to here
    question: str = ""         # the player asked the class and a student asked this (else the agent asks)
    post_id: int | None = None   # a shared lesson a student is playing: its locked version, and where to log doubts
    version_id: int | None = None


def _locked_segments(lecture_id, body):
    """The locked version a student is playing (None: the lecture's current approved script)."""
    if body.version_id is None:
        return None
    from eris.api.server_platform import version_segments
    return version_segments(body.version_id, lecture_id)


def _log(request, lecture_id, lesson, section, question, turn, flags=()):
    """Keep every question and answer (and what the guardrails flagged), for the teacher's view of the lesson."""
    if not question:
        return
    from eris.api.server_platform import log_doubt
    try:
        log_doubt(request.state.user, lesson.get("post_id"), lesson.get("version_id"), lecture_id, section, question,
                  turn.get("reply_text") or turn.get("reply", ""), turn.get("passed"), flags)
    except Exception as e:  # a missed log must never cost the student their answer
        print(f"[doubts] could not log: {e}")


# ---------- guardrails (eris/guardrails.py): a question is checked before the agent sees it, an answer before
# the student hears it ----------

def _said(text, passed=False):
    """A turn that only says `text`: a guardrail's redirect, or passing the question to the teacher."""
    return {"prompt": None, "reply": text, "reply_text": text, "done": True, "final": "", "passed": passed,
            "reply_segments": [{"kind": "say", "text": text}], "final_segments": []}


def _guard_question(lecture_id, question, section):
    """(flags, the turn to play instead when the question is blocked, else None)."""
    from eris import guardrails
    flags = guardrails.check_question(question, (manifest_or_none(lecture_id) or {}).get("topic", ""), section)
    return flags, _said(guardrails.redirect(flags)) if guardrails.blocked(flags) else None


def _guard_answer(lecture_id, question, turn):
    """(the turn to play, flags): a blocked answer becomes passing the question to the teacher."""
    from eris import guardrails
    manifest = manifest_or_none(lecture_id) or {}
    answer = " ".join(t for t in (turn.get("reply_text") or turn.get("reply", ""), turn.get("final", "")) if t)
    flags = guardrails.check_answer(question, answer, manifest.get("topic", ""))
    if guardrails.blocked(flags):
        name = manifest.get("persona", {}).get("Teacher", {}).get("Name") or "your teacher"
        return _said(f"I'll pass this question to {name}.", passed=True), flags
    return turn, flags


def _board_at(lecture_id, cursor, key=None, segments=None, run_code=True):
    """The class screen at `cursor`: the script so far plus earlier doubt answers in this run. segments: the locked
    version a student is playing (default: the lecture's current approved script). key: one student's class run."""
    if segments is None:
        script_json = config.lecture_dir(lecture_id) / "script.json"
        segments = json.loads(script_json.read_text(encoding="utf-8")) if script_json.exists() else []
    cursor = len(segments) if cursor is None else cursor
    key = key or lecture_id
    extras = _answer_extras.get(key)
    if extras is None or cursor < extras["cursor"]:  # a new run (or a jump back): earlier answers are gone
        extras = _answer_extras[key] = {"cursor": cursor, "segments": []}
    extras["cursor"] = cursor
    board = class_board.rebuild(segments, cursor)
    board["figures"] = figures.load(lecture_id)  # the material's graphs: the only ones an answer may build
    from eris.material.images import load as load_pictures
    board["pictures"] = load_pictures(lecture_id)  # what the pictures on each slide show
    # Doubts use only what this class used: notebook and slides always, code and graphs if the lecture had them.
    used = figures.env_from_segments(segments)
    board["environments"] = {**used, "notebook": True, "slides": bool(_slides_for(lecture_id))}
    if not run_code:  # no programs in answers at all: code is explained in words and notes
        board["environments"]["code"] = False
    return class_board.add_segments(board, extras["segments"])


def _remember_answer(lecture_id, board, turn, key=None):
    """Answers change the screen; later answers (and quotes) must see that."""
    played = turn.get("reply_segments", []) + turn.get("final_segments", [])
    class_board.add_segments(board, played)
    if (key or lecture_id) in _answer_extras:
        _answer_extras[key or lecture_id]["segments"].extend(played)


def _slides_for(lecture_id):
    if lecture_id not in _slides:
        _slides[lecture_id] = actions.new_board(lecture_id)["slides"]
    return _slides[lecture_id]


class DoubtReply(BaseModel):
    thread_id: str
    answer: str


@router.post("/lectures/{lecture_id}/doubts/start")
def doubts_start(lecture_id: str, body: DoubtStart, request: Request):
    run_code = _runs_code(request)
    agent, _ = _agent(_check_id(lecture_id), run_code)
    thread_id = f"web_{uuid.uuid4().hex}"  # unguessable, and bound to this person below
    limit = config.MAX_DOUBTS_FINAL if body.final else config.MAX_DOUBTS_PER_CHECK
    board = _board_at(lecture_id, body.cursor, thread_id, _locked_segments(lecture_id, body), run_code)
    _doubt_counts[thread_id] = {"asked": 0, "max": limit, "section": body.section, "board": board,
                                "post_id": body.post_id, "version_id": body.version_id, "lecture": lecture_id,
                                "user": request.state.user["id"], "run_code": run_code}
    question = body.question.strip()
    if question:
        _doubt_counts[thread_id]["asked"] = 1
    flags, turn = _guard_question(lecture_id, question, body.section) if question else ([], None)
    if turn is None:
        with _doubt_lock:
            set_board(board, _slides_for(lecture_id))
            turn = _start_turn(lecture_id, agent, thread_id, body, question, board, run_code)
        if question:
            turn, answer_flags = _guard_answer(lecture_id, question, turn)
            flags += answer_flags
    _log(request, lecture_id, body.model_dump(), body.section, question, turn, flags)
    return {"thread_id": thread_id, "max": limit, "asked": 1 if question else 0, **turn}


def _start_turn(lecture_id, agent, thread_id, body, question, board, run_code=True):
    try:
        if question:
            _, log_path = _agent(lecture_id, run_code)
            turn = doubt_agent.turn_question(agent, thread_id, body.context, question, log_path, body.section)
        else:
            turn = doubt_agent.turn_start(agent, thread_id, body.context + "\n\nNow ask the class for doubts.")
        turn = doubt_agent.with_segments(turn, count_slides(lecture_id), board)
        turn["_board_files"] = board.get("files", {})
        _build_answer_visuals(lecture_id, turn)
        turn.pop("_board_files", None)
    except Exception as e:  # the details stay in the server log: provider errors are not for students
        print(f"[doubts] agent failed: {type(e).__name__}: {e}")
        raise HTTPException(502, AGENT_DOWN)
    _remember_answer(lecture_id, board, turn, thread_id)
    return turn


class DoubtAsk(BaseModel):
    question: str
    context: str = ""            # the class snapshot (sent every time; used when the break changed)
    section: str = "Lecture"
    final: bool = False
    cursor: int | None = None
    thread_id: str | None = None  # the class's conversation from an earlier question; None = a new class run
    visuals: str = ""            # what each visual on screen shows now (its Visual.state line), from the player
    post_id: int | None = None   # a shared lesson a student is playing: its locked version, and where to log doubts
    version_id: int | None = None


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


def _judged_answer(lecture_id, agent, thread_id, question, turn, board, body, log_path):
    """Jev judges the answer before the class hears it. With a blocker (doesn't answer the question, or says
    something wrong) the agent answers once more with the problems, and the better answer plays. Every judgement
    is logged in doubt_judge.jsonl. Never raises; with Jev off or unreachable the answer plays as it is."""
    if not config.DOUBT_JUDGE or not turn.get("reply_segments"):
        return turn
    from eris.generate.script_judge import better, judge_answer
    from eris.material.images import load as load_pictures
    manifest = manifest_or_none(lecture_id) or {}
    avoid = manifest.get("persona", {}).get("Lecture Structure", {}).get("Avoid", "")
    pictures = board.get("pictures") or load_pictures(lecture_id)
    judge = lambda t: judge_answer(question, t["reply_segments"], body.context, manifest.get("topic", ""), avoid, pictures)  # noqa: E731
    report, entry = judge(turn), {"question": question, "section": body.section, "used": "first"}
    entry["first"] = {k: report.get(k) for k in ("score", "blockers", "findings", "error")}
    entry["first"]["answer"] = turn.get("reply_text", "")[:1500]
    if report.get("blockers"):
        print(f"[doubts] quality check: {report['blockers']} blocker(s); asking for a better answer")
        try:
            fixed = doubt_agent.turn_fix(agent, thread_id, report["fix"], log_path, body.section, question)
            fixed = doubt_agent.with_segments(fixed, count_slides(lecture_id), board)
            again = judge(fixed)
            entry["fixed"] = {k: again.get(k) for k in ("score", "blockers", "findings", "error")}
            entry["fixed"]["answer"] = fixed.get("reply_text", "")[:1500]
            if fixed.get("reply_segments") and (again.get("error") or not better(report, again)):
                turn, report, entry["used"] = fixed, again, "fixed"
        except Exception as e:
            entry["fix_error"] = f"{type(e).__name__}: {e}"[:300]
    turn["quality"] = {k: report.get(k) for k in ("score", "blockers")}
    try:
        with open(config.lecture_dir(lecture_id) / "doubt_judge.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return turn


def _output_notes(turn):
    """What the programs in this answer really printed: told to the agent with the next question."""
    notes = []
    for seg in turn.get("reply_segments", []):
        if seg.get("name") == "RUN":
            out = seg.get("expected_output", "").strip() or "(no output)"
            notes.append(f"{seg['args']['cmd']} was run on the class screen and printed:\n{out[:600]}")
    return notes


@router.post("/lectures/{lecture_id}/doubts/ask")
def doubts_ask(lecture_id: str, body: DoubtAsk, request: Request):
    """One student question. The whole class run shares ONE agent conversation (thread_id), so the agent
    remembers its earlier answers, programs and outputs across questions and question breaks."""
    run_code = _runs_code(request)
    agent, log_path = _agent(_check_id(lecture_id), run_code)
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Empty question")
    thread = _class_threads.get(body.thread_id or "")
    if not _owned(thread, request) or thread["lecture"] != lecture_id:  # someone else's thread: start a new one
        thread_id = f"class_{uuid.uuid4().hex}"
        thread = _class_threads[thread_id] = {"lecture": lecture_id, "cursor": None, "notes": [],
                                              "user": request.state.user["id"], "run_code": run_code}
    else:
        thread_id = body.thread_id
    flags, turn = _guard_question(lecture_id, question, body.section)
    if turn is None:
        with _doubt_lock:
            turn = _ask_turn(lecture_id, agent, log_path, thread_id, thread, question, body)
        turn, answer_flags = _guard_answer(lecture_id, question, turn)
        flags += answer_flags
    _log(request, lecture_id, body.model_dump(), body.section, question, turn, flags)
    limit = config.MAX_DOUBTS_FINAL if body.final else config.MAX_DOUBTS_PER_CHECK
    return {"thread_id": thread_id, "max": limit, **turn}


def _ask_turn(lecture_id, agent, log_path, thread_id, thread, question, body):
    board = _board_at(lecture_id, body.cursor, thread_id, _locked_segments(lecture_id, body), thread["run_code"])
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
        turn = _judged_answer(lecture_id, agent, thread_id, question, turn, board, body, log_path)
        turn["_board_files"] = board.get("files", {})
        _build_answer_visuals(lecture_id, turn)
        turn.pop("_board_files", None)
    except Exception as e:
        print(f"[doubts] agent failed: {type(e).__name__}: {e}")
        raise HTTPException(502, AGENT_DOWN)
    _show_slide_if_asked(question, board, turn, _slides_for(lecture_id))
    _remember_answer(lecture_id, board, turn, thread_id)
    thread["notes"] += _output_notes(turn)
    return turn


@router.post("/lectures/{lecture_id}/doubts/reply")
def doubts_reply(lecture_id: str, body: DoubtReply, request: Request):
    count = _doubt_counts.get(body.thread_id)
    if not _owned(count, request) or count["lecture"] != _check_id(lecture_id):
        raise HTTPException(404, "Unknown doubt session")
    agent, log_path = _agent(lecture_id, count["run_code"])
    answer = body.answer.strip()
    if count["asked"] >= count["max"]:
        answer = "no more doubts"  # Limit reached: tell the agent to wrap up.
    elif answer.lower() not in doubt_agent.NO_DOUBT_WORDS:
        count["asked"] += 1
    asked = answer.lower() not in doubt_agent.NO_DOUBT_WORDS and answer != "no more doubts"
    flags, turn = _guard_question(lecture_id, answer, count["section"]) if asked else ([], None)
    if turn is None:
        with _doubt_lock:
            set_board(count["board"], _slides_for(lecture_id))
            try:
                turn = doubt_agent.with_segments(
                    doubt_agent.turn_reply(agent, body.thread_id, answer, log_path, count["section"]),
                    count_slides(lecture_id), count["board"])
                turn["_board_files"] = count["board"].get("files", {})
                _build_answer_visuals(lecture_id, turn)
                turn.pop("_board_files", None)
            except Exception as e:
                print(f"[doubts] agent failed: {type(e).__name__}: {e}")
                raise HTTPException(502, AGENT_DOWN)
            _remember_answer(lecture_id, count["board"], turn, body.thread_id)
        if asked:
            turn, answer_flags = _guard_answer(lecture_id, answer, turn)
            flags += answer_flags
    if asked:
        _log(request, lecture_id, count, count["section"], answer, turn, flags)
    return {"asked": count["asked"], "max": count["max"], **turn}
