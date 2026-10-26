"""The `session` command: the player. Plain code walks the approved script.

Sync rule: one segment at a time, each finishes before the next starts
(narration audio ends -> action runs -> next narration). The player owns the state;
the doubt agent and recovery only get a read-only snapshot of it.
"""

import json
import sys
from datetime import datetime

from eris.classroom import actions
from eris import config
from eris.classroom.doubt_agent import build_doubt_agent, run_checkpoint, type_doubt
from eris.persona import persona_to_text
from eris.prompts import doubt_prompt, speaker_rule
from eris.classroom.recovery import recovery_line
from eris.tools import set_lecture

LINE = "=" * 70


# ---------- state ----------

def state_path(lecture_id):
    return config.lecture_dir(lecture_id) / "session_state.json"


def new_state():
    return {"cursor": 0, "section": "Introduction", "covered": [], "section_text": [],
            "current": None, "doubts_asked": 0, "passed": 0, "events": [],
            "started_at": datetime.now().isoformat(timespec="seconds")}


def save_state(lecture_id, state):
    state_path(lecture_id).write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def mark(state, index, seg, status, detail=""):
    """Record a segment status change: pending -> running -> done | failed."""
    name = seg.get("name", "SAY")
    state["current"] = {"index": index, "name": name, "status": status}
    state["events"].append({"time": datetime.now().isoformat(timespec="seconds"),
                            "index": index, "name": name, "status": status, "detail": detail[:300]})


def snapshot(state, board):
    """Read-only view of the class for the doubt agent and recovery."""
    files = ", ".join(board["files"]) or "nothing"
    return (f"Current section: {state['section']}\n"
            f"Sections covered so far: {', '.join(state['covered']) or 'none'}\n"
            f"Code on the board: {files}\n"
            f"Current slide: {board['current_slide'] or 'none'}\n"
            f"Last program output: {board['last_output'].strip()[:300] or 'none'}\n"
            f"Notebook (latest lines):\n{chr(10).join(board['notebook'][-12:]) or 'empty'}\n\n"
            f"What was taught in this section (narration and code):\n"
            + "\n".join(state["section_text"])[:3000])


# ---------- setup ----------

def start_doubts(lecture_id, manifest):
    """Common setup for session and the `doubts` test command."""
    set_lecture(lecture_id)
    persona = manifest["persona"]
    language = config.lecture_language(manifest)
    agent = build_doubt_agent(doubt_prompt(persona, persona_to_text(persona), manifest["topic"], language)
                              + speaker_rule(language, config.voice_gender(manifest)))  # answers in the voice's grammar
    log_path = config.lecture_dir(lecture_id) / "doubts_log.md"
    return agent, log_path


def _load(lecture_id, force):
    manifest = config.load_manifest(lecture_id)
    if manifest.get("status") != "approved":
        if not force:
            print("Lecture not approved. Run approve first.")
            sys.exit(1)
        print(f"WARNING: running a lecture with status '{manifest.get('status')}' because of --force.")
    script_path = config.lecture_dir(lecture_id) / "script.json"
    if not script_path.exists():
        print(f"No script.json found. Run: python main.py generate --lecture {lecture_id}")
        sys.exit(1)
    return manifest, json.loads(script_path.read_text(encoding="utf-8"))


def _voice_functions(lecture_id, use_voice, use_mic, segments):
    """Return (speak, listen). Text-only mode prints and reads the keyboard."""
    if not (use_voice or use_mic):
        return (lambda text: None), type_doubt
    config.check_voice_env()
    import voice  # Imported only when voice is on, so text mode needs no audio setup.
    speak = (lambda text: None)
    if use_voice:
        print("[session] preparing narration audio (cached clips are reused) ...")
        total, failures = voice.render_lecture(lecture_id, segments)
        print(f"[session] narration audio: {total / 60:.1f} min, {failures} clip(s) failed")
        speak = lambda text: voice.speak(lecture_id, text)  # noqa: E731
    listen = (lambda: voice.listen(lecture_id)) if use_mic else type_doubt
    return speak, listen


# ---------- player ----------

def play_segment(index, seg, segments, state, board, ctx):
    """Play one segment. Raises only on KeyboardInterrupt."""
    name = ctx["name"]
    if seg["kind"] == "say":
        print(f"\n🗣 {name}: {seg['text']}")
        state["section_text"].append(seg["text"])
        ctx["speak"](seg["text"])  # Blocks until the clip finishes: this is the sync point.
        return

    action, args = seg["name"], seg.get("args", {})
    if action == "SECTION":
        state["section"] = args["title"]
        state["covered"].append(args["title"])
        state["section_text"] = []
        print(f"\n{LINE}\n## {args['title']}\n{LINE}")
        return

    if action == "DOUBT_CHECK":
        is_last = index == len(segments) - 1
        limit = config.MAX_DOUBTS_FINAL if is_last else config.MAX_DOUBTS_PER_CHECK
        print(f"\n⏸  DOUBT CHECK ({state['section']}), up to {limit} questions")
        context = snapshot(state, board) + "\n\nNow ask the class for doubts."
        thread = f"doubts_{ctx['lecture_id']}_{ctx['failures']}"
        asked, passed = run_checkpoint(ctx["agent"], thread, context, limit, ctx["log_path"],
                                       state["section"], listen=ctx["listen"], speak=ctx["speak"])
        state["doubts_asked"] += asked
        state["passed"] += passed
        return

    if action == "WRITE_CODE":
        state["section_text"].append(f"Code in {args['file']}:\n{args['code']}")
    elif action in ("NOTE", "NOTE_TITLE", "WRITE"):
        state["section_text"].append(f"Notebook:\n{args['text']}")
    result = actions.execute(board, seg)
    if not result["ok"]:
        print(f"\n⚠️  {result['error']}")
        line = recovery_line(name, snapshot(state, board), seg, result["error"])
        print(f"\n🗣 {name}: {line}")
        ctx["speak"](line)
        raise RuntimeError(result["error"])  # Logged as failed; the lecture continues.


def run_session(lecture_id, force=False, use_voice=False, use_mic=False, resume=False):
    manifest, segments = _load(lecture_id, force)
    speak, listen = _voice_functions(lecture_id, use_voice, use_mic, segments)
    agent, log_path = start_doubts(lecture_id, manifest)
    board = actions.new_board(lecture_id)

    state = new_state()
    if resume and state_path(lecture_id).exists():
        state = json.loads(state_path(lecture_id).read_text(encoding="utf-8"))
        actions.restore(board, segments[: state["cursor"]])
        print(f"[session] resuming at segment {state['cursor'] + 1}/{len(segments)} ({state['section']})")

    name = manifest["persona"]["Teacher"]["Name"]
    ctx = {"lecture_id": lecture_id, "name": name, "agent": agent, "log_path": log_path,
           "speak": speak, "listen": listen, "failures": 0}
    mode = ("voice" if use_voice else "text") + (" + mic" if use_mic else "")
    print(f"{LINE}\nTeacher: {name} (AI substitute) | Topic: {manifest['topic']}")
    print(f"Estimated: {manifest.get('estimated_min', '?')} min | Mode: {mode} | Board: {board['dir']}\n{LINE}")

    index = state["cursor"]
    while index < len(segments):
        seg = segments[index]
        # while_speaking pairs: the terminal can't overlap them (no threads), so it says the sentence
        # first and then runs the action, keeping the order the script means.
        pair = seg.get("args", {}).get("while_speaking") and index + 1 < len(segments)
        mark(state, index, seg, "running")
        try:
            if pair:
                play_segment(index + 1, segments[index + 1], segments, state, board, ctx)
                mark(state, index + 1, segments[index + 1], "done")
            play_segment(index, seg, segments, state, board, ctx)
            mark(state, index, seg, "done")
        except KeyboardInterrupt:
            mark(state, index, seg, "stopped")
            state["cursor"] = index
            save_state(lecture_id, state)
            print(f"\n[session] paused. Continue with: python main.py session --lecture {lecture_id} --resume"
                  + (" --voice" if use_voice else "") + (" --mic" if use_mic else ""))
            return
        except Exception as e:
            ctx["failures"] += 1  # A failed checkpoint may leave a half-finished thread; use a fresh one.
            mark(state, index, seg, "failed", str(e))
            print(f"[session] segment {index + 1} failed: {e} (continuing)")
        index += 2 if pair else 1
        state["cursor"] = index
        save_state(lecture_id, state)

    manifest["status"] = "completed"
    config.save_manifest(lecture_id, manifest)
    failed = sum(1 for e in state["events"] if e["status"] == "failed")
    print(f"\n{LINE}\nSession complete.")
    print(f"Sections covered: {len(state['covered'])} ({', '.join(state['covered'])})")
    print(f"Doubts asked: {state['doubts_asked']} | passed to {name}: {state['passed']} | failed actions: {failed}")
    print(f"Doubt log: {log_path}\nSession state: {state_path(lecture_id)}")
