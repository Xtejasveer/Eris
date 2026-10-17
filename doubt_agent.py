"""One doubt checkpoint with real human-in-the-loop (students type their doubts)."""

import re
from datetime import datetime

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import config
from tools import ask_class_for_doubts, dry_run_python, read_board, search_material

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
                  "RUN", "READ_OUTPUT", "SLIDE", "SLIDE_HIGHLIGHT", "LOOK_BACK", "OPEN_FILE", "NEW_PAGE"}


INLINE_BLOCK_RE = re.compile(r"\[([A-Z_]{3,})\b[^\]]*\].*?\[/\1\]")  # [RUN]cmd=...[/RUN]
INLINE_TAG_RE = re.compile(r"\[/?[A-Z_]{3,}\b[^\]]*\]")                # [RUN cmd="..."]


def _strip_inline_markers(text):
    text = INLINE_TAG_RE.sub("", INLINE_BLOCK_RE.sub("", text))
    return re.sub(r"\s{2,}", " ", text).strip()


def answer_segments(text, slide_count=None, board=None):
    """Turn a doubt answer into player segments. It plays without teacher approval, so it is
    checked by the same parser against what is really on the board (class_board), invalid markers
    are dropped (never shown), and the code is run here to record the real output."""
    from script_parser import parse_script
    from script_writer import fill_expected_outputs

    if not text.strip():
        return []
    segments, errors = parse_script(text, slide_count, require_doubt_check=False, board=board)
    for e in errors:
        print(f"[doubts] skipped in answer: {e.splitlines()[0]}")
    segments = [s for s in segments if s["kind"] == "say" or s["name"] in ANSWER_MARKERS]
    for s in segments:
        if s["kind"] == "say":  # markers written inside a sentence are never spoken
            s["text"] = _strip_inline_markers(s["text"])
    segments = [s for s in segments if s["kind"] != "say" or s["text"]]
    if any(s.get("name") == "RUN" for s in segments):
        fill_expected_outputs(segments, (board or {}).get("files"))
    return segments


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
