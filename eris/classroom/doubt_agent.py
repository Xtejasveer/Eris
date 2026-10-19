"""One doubt checkpoint with real human-in-the-loop (students type their doubts)."""

import re
from datetime import datetime

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from eris import config
from eris.tools import ask_class_for_doubts, dry_run_python, read_board, search_material

NO_DOUBT_WORDS = {"", "no", "none", "no doubts", "nope", "n"}
PASS_PHRASE = "i'll pass this question to"


def build_doubt_agent(system_prompt):
    """Build once per session and reuse it for every checkpoint."""
    return create_agent(
        model=f"openrouter:{config.LLM_MODEL}",
        tools=[read_board, search_material, dry_run_python, ask_class_for_doubts],
        system_prompt=system_prompt,
        middleware=[HumanInTheLoopMiddleware(
            interrupt_on={"ask_class_for_doubts": {"allowed_decisions": ["respond"]}},
            description_prefix="Question for the class",
        )],
        checkpointer=InMemorySaver(),
        name="doubt_solver",
    )


def _text(message):
    content = message.content
    if isinstance(content, list):
        content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return (content or "").strip()


def _interrupt_prompt(result):
    # With langgraph 1.2 + batched HITL, interrupts[0].value looks like:
    #   {"action_requests": [{"name": ..., "args": {"prompt": ...}, ...}], "review_configs": [...]}
    requests = result.interrupts[0].value.get("action_requests", [])
    if not requests:
        return "Any doubts?"
    return requests[0].get("args", {}).get("prompt", "Any doubts?")


def _newest_ai_text(messages, start):
    """All AI text added after index `start`, in order.

    The answer can span several messages: e.g. notes and code, then a dry_run_python call,
    then the closing sentence. Keeping only the last one would lose the notes and code.
    """
    parts = [_text(m) for m in messages[start:] if isinstance(m, AIMessage) and _text(m)]
    return "\n".join(parts)


def _log(log_path, section, question, answer):
    passed = PASS_PHRASE in answer.lower().replace("’", "'")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"## {datetime.now().isoformat(timespec='seconds')} | {section}\n")
        f.write(f"**Question:** {question}\n\n**Answer:** {answer}\n\n")
        f.write(f"passed_to_teacher: {str(passed).lower()}\n\n---\n\n")
    return passed


def type_doubt():
    return input("Student doubt (Enter = none): ").strip()


def run_checkpoint(agent, thread_id, context_text, max_doubts, log_path, section="Whole lecture",
                   listen=type_doubt, speak=None):
    """Run one doubt checkpoint. Returns (questions_asked, passed_to_teacher).

    listen(): returns one student doubt ('' = none). speak(text): says a reply out loud.
    """
    speak = speak or (lambda text: None)
    config_ = {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}
    result = agent.invoke({"messages": [{"role": "user", "content": context_text}]}, config_, version="v2")
    asked, passed, rounds = 0, 0, 0
    reply = ""

    while result.interrupts:
        rounds += 1
        prompt = _interrupt_prompt(result)
        if prompt != reply:  # Already said if the model put its answer in the prompt.
            print(f"\n🙋 {prompt}")
            speak(prompt)
        if asked >= max_doubts or rounds > max_doubts + 3:
            answer = "no more doubts"
            print("(doubt limit reached)")
        else:
            answer = listen()

        last_question = None if answer.lower() in NO_DOUBT_WORDS else answer
        if last_question:
            asked += 1

        before = len(result.value["messages"])
        decision = {"decisions": [{"type": "respond", "message": answer or "no doubts"}]}
        result = agent.invoke(Command(resume=decision), config_, version="v2")

        if last_question:
            reply = _newest_ai_text(result.value["messages"], before)
            if not reply and result.interrupts:
                reply = _interrupt_prompt(result)  # Some models put the answer in the next prompt.
            print(f"\n💬 {reply}")
            speak(reply)
            if _log(log_path, section, last_question, reply):
                passed += 1

    final = _text(result.value["messages"][-1])
    if final and final != reply:
        print(f"\n💬 {final}")
        speak(final)
    return asked, passed


# ---------- step API for the web backend (one HTTP request = one turn) ----------

# What a doubt answer may do on the class screen: notes, code, slides, and pointing back at what is
# already there. No sections or doubt checks.
ANSWER_MARKERS = {"NOTE", "NOTE_TITLE", "NOTE_HIGHLIGHT", "WRITE", "WRITE_CODE", "HIGHLIGHT",
                  "RUN", "READ_OUTPUT", "SLIDE", "SLIDE_HIGHLIGHT", "SLIDE_CIRCLE", "LOOK_BACK", "OPEN_FILE", "NEW_PAGE",
                  "VISUAL", "VISUAL_SET", "OPEN_VISUAL", "FLOW", "FLOW_NEXT", "FLOW_HIGHLIGHT", "OPEN_FLOW"}


INLINE_BLOCK_RE = re.compile(r"\[([A-Z_]{3,})\b[^\]]*\].*?\[/\1\]")  # [RUN]cmd=...[/RUN]
INLINE_TAG_RE = re.compile(r"\[/?[A-Z_]{3,}\b[^\]]*\]")                # [RUN cmd="..."]


def _strip_inline_markers(text):
    text = INLINE_TAG_RE.sub("", INLINE_BLOCK_RE.sub("", text))
    return re.sub(r"\s{2,}", " ", text).strip()


def answer_segments(text, slide_count=None, board=None):
    """Turn a doubt answer into player segments. It plays without teacher approval, so it is
    checked by the same parser against what is really on the board (class_board), invalid markers
    are dropped (never shown), and the code is run here to record the real output."""
    from eris.generate.script_parser import parse_script
    from eris.generate.script_writer import fill_expected_outputs
    from eris.generate.script_fixes import add_sync_flags, drop_bad_visuals

    if not text.strip():
        return []
    from eris.generate.format_fixes import fix_format
    text, fixed = fix_format(text)  # the same repairs as a lecture script: markers in sentences, typed output, ...
    for f in fixed:
        print(f"[doubts] repaired: {f}")
    text = _notebook_to_look_back(text, board)
    text = _repair_runs(text, (board or {}).get("latest_file"))
    env = (board or {}).get("environments")
    if env:  # only the environments this class used, whatever the student asked for (before any leads are added)
        from eris.material.figures import ENV_MARKERS
        from eris.generate.script_fixes import drop_markers
        banned = set().union(*(ENV_MARKERS[name] for name in ENV_MARKERS if not env.get(name)))
        text, n = drop_markers(text, banned)
        if n:
            print(f"[doubts] left out {n} marker(s) from an environment this class doesn't use")
    # A visual the parser can't read is removed first, so no "Let me show you..." lead is added for it.
    _, early = parse_script(text, slide_count, require_doubt_check=False, board=board)
    text, broken = drop_bad_visuals(text, early)
    for e in broken:
        print(f"[doubts] left out a visual: {e}")
    if (env or {}).get("slides", True):  # a picture the answer talks about: its slide is on screen
        from eris.generate.script_fixes import show_picture_slides
        text, shown = show_picture_slides(text, (board or {}).get("pictures"), slide_count, (board or {}).get("figures"))
        if shown:
            print(f"[doubts] showed the slide with the picture being explained {shown} time(s)")
    from eris.generate.script_fixes import drop_empty_circles
    text, _ = drop_empty_circles(text, (board or {}).get("pictures"))  # a pen circle needs a picture
    text, _ = add_sync_flags(text)  # written first, then explained; only highlights and slider moves run while speaking
    segments, errors = parse_script(text, slide_count, require_doubt_check=False, board=board)
    for e in errors:
        print(f"[doubts] skipped in answer: {e.splitlines()[0]}")
    segments = [s for s in segments if s["kind"] == "say" or s["name"] in ANSWER_MARKERS]
    if env:  # nothing from a banned environment survives, even a marker written oddly
        segments = [s for s in segments if s.get("name") not in banned]
    for s in segments:
        if s["kind"] == "say":  # markers written inside a sentence are never spoken
            s["text"] = _strip_inline_markers(s["text"])
    segments = [s for s in segments if s["kind"] != "say" or s["text"]]
    if segments and segments[0]["kind"] == "say":  # talk to the student, not about them
        segments[0]["text"] = THIRD_PERSON_RE.sub("", segments[0]["text"]).strip() or segments[0]["text"]
    segments = _run_written_code(segments)
    if any(s.get("name") == "RUN" for s in segments):
        fill_expected_outputs(segments, (board or {}).get("files"))
        segments = _unspeak_output(segments)
    return segments


NOTEBOOK_FILE_RE = re.compile(r'^\s*\[OPEN_FILE\s+file="(?:the\s+)?(?:notebook|notes?|board|page)[^"]*"\]\s*$', re.I | re.M)


def _notebook_to_look_back(text, board):
    """"Open the notebook" written as [OPEN_FILE file="notebook"]: scroll the notebook back to its latest heading."""
    headings = [ln[3:] for _, groups in (board or {}).get("pages", []) for _, lines in groups
                for ln in lines if ln.startswith("## ")]
    if not headings:
        return NOTEBOOK_FILE_RE.sub("", text)
    return NOTEBOOK_FILE_RE.sub(f'[LOOK_BACK text="{headings[-1]}"]', text)


RUN_LINE_RE = re.compile(r"^\s*\[RUN(?P<rest>[^\]]*)\]\s*$", re.M)


def _repair_runs(text, latest_file):
    """Models write [RUN], [RUN countdown.py] or [RUN file="x.py"]: make each one [RUN cmd="python <file>"],
    using the named file, else the program written or opened last in this answer, else the latest on the board."""
    last = latest_file
    out = []
    for line in text.splitlines():
        m = re.match(r'^\s*\[(?:WRITE_CODE|OPEN_FILE)\s+file="([^"]+)"', line)
        if m:
            last = m.group(1)
        run = RUN_LINE_RE.match(line)
        if run and 'cmd="python ' not in line:
            named = re.search(r"([\w-]+\.py)", run.group("rest"))
            target = named.group(1) if named else last
            if target:
                line = f'[RUN cmd="python {target}"]'
        out.append(line)
    return "\n".join(out)


# "The student asks for another example..." / "A student is asking about..." at the start of an answer.
THIRD_PERSON_RE = re.compile(r"^(?:the|a|this|our)\s+student\s+(?:is\s+)?(?:ask(?:s|ing)?|want(?:s|ing)?|wonder(?:s|ing)?|would like)\b[^.!?]*[.!?]\s*", re.I)


def _run_written_code(segments):
    """Every program an answer writes or opens is run before its output is read, even if the model forgot:
      - a READ_OUTPUT before that program's RUN later in the answer is dropped (it would read an old output);
      - a READ_OUTPUT after an OPEN_FILE/WRITE_CODE with no RUN at all gets that RUN in front of it;
      - a program written but never run is run (and read) after the sentence that follows it."""
    def runs_later(i, file):
        return any(s.get("name") == "RUN" and s["args"]["cmd"].endswith(file) for s in segments[i + 1:])

    out, pending, written, ran = [], None, set(), False
    for i, seg in enumerate(segments):
        name = seg.get("name")
        if name == "READ_OUTPUT" and not pending and not ran and not runs_later(i, ""):
            continue  # nothing was run in this answer: there is no output to look at
        if name in ("WRITE_CODE", "OPEN_FILE"):
            pending = seg["args"]["file"]
            if name == "WRITE_CODE":
                written.add(pending)
        elif name == "RUN":
            ran = True
            if pending and seg["args"]["cmd"].endswith(pending):
                pending = None
        elif name == "READ_OUTPUT" and pending:
            if runs_later(i, pending):
                continue  # read too early: the program runs a bit later in this answer
            print(f"[doubts] {pending} was read without being run: running it first")
            out.append({"kind": "action", "name": "RUN", "args": {"cmd": f"python {pending}"}})
            pending = None
        out.append(seg)
        if seg["kind"] == "say" and pending in written and not runs_later(i, pending):
            print(f"[doubts] {pending} was written but not run: running it")
            out += [{"kind": "action", "name": "RUN", "args": {"cmd": f"python {pending}"}},
                    {"kind": "action", "name": "READ_OUTPUT", "args": {}}]
            pending = None
    if pending in written:
        print(f"[doubts] {pending} was written but not run: running it")
        out += [{"kind": "action", "name": "RUN", "args": {"cmd": f"python {pending}"}},
                {"kind": "action", "name": "READ_OUTPUT", "args": {}}]
    # Every RUN is followed by READ_OUTPUT: the class looks at the terminal while the teacher explains it.
    final = []
    for i, seg in enumerate(out):
        final.append(seg)
        if seg.get("name") == "RUN" and (i + 1 >= len(out) or out[i + 1].get("name") != "READ_OUTPUT"):
            final.append({"kind": "action", "name": "READ_OUTPUT", "args": {}})
    return final


def _unspeak_output(segments):
    """The terminal shows the output; the teacher shouldn't read its lines aloud one by one."""
    lines = set()
    for seg in segments:
        if seg.get("name") == "RUN":
            lines |= {ln.strip() for ln in seg.get("expected_output", "").splitlines() if len(ln.strip()) > 3}
        elif seg["kind"] == "say" and lines:
            hits = [ln for ln in lines if ln in seg["text"]]
            if len(hits) >= 2:  # a run of output lines, not one quoted value
                for ln in sorted(hits, key=len, reverse=True):
                    seg["text"] = seg["text"].replace(ln, " ")
                seg["text"] = re.sub(r"\s{2,}", " ", seg["text"]).strip()
    return [s for s in segments if s["kind"] != "say" or s["text"]]


def plain_text(segments):
    """What the answer says, without markers (for the chat panel and the log)."""
    return " ".join(s["text"] for s in segments if s["kind"] == "say").strip()

def _turn(result, reply=""):
    """Shape a v2 result as {prompt, reply, done, final} for the browser."""
    if result.interrupts:
        prompt = _interrupt_prompt(result)
        return {"prompt": prompt, "reply": reply, "done": False, "final": ""}
    final = _text(result.value["messages"][-1])
    return {"prompt": None, "reply": reply if reply != final else "", "done": True, "final": final}


def turn_start(agent, thread_id, context_text):
    """Begin a checkpoint: the agent asks its first question (an interrupt)."""
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}
    result = agent.invoke({"messages": [{"role": "user", "content": context_text}]}, cfg, version="v2")
    return _turn(result)


def turn_question(agent, thread_id, context_text, question, log_path, section):
    """Begin a checkpoint with a student's question already asked (kept for the CLI and older callers)."""
    return turn_ask(agent, thread_id, question, log_path, section, context_text)


def _waiting_for_class(agent, cfg):
    """True if the agent is paused inside ask_class_for_doubts (an unanswered tool call)."""
    snap = agent.get_state(cfg)
    return bool(snap.next) and any(getattr(t, "interrupts", ()) for t in snap.tasks)


def turn_ask(agent, thread_id, question, log_path, section, context_text=""):
    """One student question on the class's ONE conversation, so the agent remembers everything it said and
    showed before ("run this code" means the code it just wrote).
    context_text: the class snapshot and notes, sent when something changed (a new break, program output).
    If the agent is waiting in ask_class_for_doubts, the question is that tool's answer; otherwise it is a
    new message. Returns the turn like turn_reply, with 'passed'."""
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}
    snap = agent.get_state(cfg)
    before = len((snap.values or {}).get("messages", []))
    student = f'Student: "{question}"'
    if before and _waiting_for_class(agent, cfg):
        reply_to_tool = f"{context_text}\n\n{student}" if context_text else student
        decision = {"decisions": [{"type": "respond", "message": reply_to_tool}]}
        result = agent.invoke(Command(resume=decision), cfg, version="v2")
    else:
        message = (f"{context_text}\n\n" if context_text else "") + (
            f"The class was asked for doubts. {student}\n"
            "Answer the student directly, talking to them as \"you\" (never describe their question in the third "
            "person), following your rules, then call ask_class_for_doubts.")
        result = agent.invoke({"messages": [{"role": "user", "content": message}]}, cfg, version="v2")
    reply = _newest_ai_text(result.value["messages"], before)
    if not reply and result.interrupts:
        reply = _interrupt_prompt(result)  # Some models put the answer in the question.
    passed = _log(log_path, section, question, reply)
    # When the agent ends without asking for more doubts, its last message IS the answer: keep it as the reply.
    out = _turn(result, reply) if result.interrupts else {"prompt": None, "reply": reply, "done": True, "final": ""}
    out["passed"] = passed
    return out


def turn_reply(agent, thread_id, answer, log_path, section):
    """Send one student answer ('' = no doubts). Logs real questions. Adds 'passed' to the result."""
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}
    question = None if answer.strip().lower() in NO_DOUBT_WORDS else answer.strip()
    before = len(agent.get_state(cfg).values.get("messages", []))
    decision = {"decisions": [{"type": "respond", "message": answer.strip() or "no doubts"}]}
    result = agent.invoke(Command(resume=decision), cfg, version="v2")
    reply, passed = "", False
    if question:
        reply = _newest_ai_text(result.value["messages"], before)
        if not reply and result.interrupts:
            reply = _interrupt_prompt(result)
        passed = _log(log_path, section, question, reply)
    out = _turn(result, reply)
    out["passed"] = passed
    return out


def with_segments(turn, slide_count=None, board=None):
    """Add playable segments for the reply and the closing line of a turn."""
    turn["reply_segments"] = answer_segments(turn.get("reply", ""), slide_count, board)
    # The closing line only moves the class on; the script teaches the next part, so keep one sentence.
    closing = _strip_inline_markers(turn.get("final", ""))
    closing = re.split(r"(?<=[.!?])\s", closing, maxsplit=1)[0] if closing else ""
    turn["final"] = closing
    turn["final_segments"] = [{"kind": "say", "text": closing}] if closing else []
    turn["reply_text"] = plain_text(turn["reply_segments"]) or turn.get("reply", "")
    turn["final_text"] = plain_text(turn["final_segments"]) or turn.get("final", "")
    return turn


def turn_fix(agent, thread_id, problems, log_path, section, question):
    """The quality check found problems in the last answer: the agent answers the same question again, fixed.
    Sent as a note from the class system, not as a student, on the same conversation. Returns a turn like turn_ask."""
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}
    before = len((agent.get_state(cfg).values or {}).get("messages", []))
    note = ("(This is not a student; it is the class's quality check, and the class hasn't heard your last answer.) "
            f"Your answer to the student's question \"{question}\" has these problems:\n{problems}\n"
            "Answer the same question again with them fixed, talking to the student as \"you\", following your rules. "
            "Do not mention this check. Then call ask_class_for_doubts.")
    if before and _waiting_for_class(agent, cfg):
        result = agent.invoke(Command(resume={"decisions": [{"type": "respond", "message": note}]}), cfg, version="v2")
    else:
        result = agent.invoke({"messages": [{"role": "user", "content": note}]}, cfg, version="v2")
    reply = _newest_ai_text(result.value["messages"], before)
    if not reply and result.interrupts:
        reply = _interrupt_prompt(result)
    passed = _log(log_path, section, question, reply)
    out = _turn(result, reply) if result.interrupts else {"prompt": None, "reply": reply, "done": True, "final": ""}
    out["passed"] = passed
    return out
