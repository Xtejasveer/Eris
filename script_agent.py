"""The two LLM steps of `generate`.

1. Research: an agent with tools reads the outline, searches the material and dry-runs every program.
2. Writing: a separate model call with NO tools writes the whole script in one message from those notes.

Models that write the script while they are still calling tools split it over several messages and mix in
chatter ("Oops, let me fix that"). With no tools in step 2 there is nothing to interleave, so the script
arrives whole. Code (script_writer.py) then validates it and asks this same writer to fix errors.
"""

import sys

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

import config
from tools import dry_run_python, read_outline, search_material

RESEARCH_KICKOFF = "Start the research now, then reply with your plan."

WRITE_TASK = """Write the whole lecture script now, in this one message (about {budget} words of narration),
from [SECTION title="Opening"] to the final [DOUBT_CHECK].

# Research notes
{notes}"""


def _text(message):
    """Text of a message, also when the content is a list of blocks; drops ``` fences around a script."""
    content = message.content
    if isinstance(content, list):
        content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    text = (content or "").strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text[: text.rfind("```")].strip()
    return text


def _fail(step, error):
    print(f"[generate] the model call failed during {step}: {error}")
    print("[generate] Check OPENROUTER_API_KEY, and that LLM_MODEL supports tool calling.")
    sys.exit(1)


def research_notes(messages):
    """Readable notes from the research run: every tool call with its result, then the plan."""
    calls = {}
    for msg in messages:
        if isinstance(msg, AIMessage):
            for call in msg.tool_calls:
                calls[call["id"]] = call
    parts = []
    for msg in messages:
        if not isinstance(msg, ToolMessage) or msg.tool_call_id not in calls:
            continue
        call = calls[msg.tool_call_id]
        args = call.get("args", {})
        if call["name"] == "dry_run_python":
            parts.append(f"## dry_run_python\ncode:\n{args.get('code', '')}\nresult:\n{_text(msg)}")
        else:
            shown = ", ".join(f"{k}={v!r}" for k, v in args.items())
            parts.append(f"## {call['name']}({shown})\n{_text(msg)}")
    plan = _text(messages[-1]) if messages and isinstance(messages[-1], AIMessage) else ""
    if plan:
        parts.append(f"## Your plan\n{plan}")
    return "\n\n".join(parts) or "No research was done. Teach only what the persona describes."


def run_research(system_prompt, thread_id):
    """Step 1: the tool-using agent. Returns the research notes as text."""
    agent = create_agent(model=f"openrouter:{config.LLM_MODEL}",
                         tools=[search_material, read_outline, dry_run_python],
                         system_prompt=system_prompt, checkpointer=InMemorySaver(), name="script_researcher")
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}
    try:
        result = agent.invoke({"messages": [{"role": "user", "content": RESEARCH_KICKOFF}]}, cfg)
    except Exception as e:
        _fail("research", e)
    return research_notes(result["messages"])


class ScriptWriter:
    """Step 2: a plain model call with no tools. Keeps the conversation so fixes see the script and notes."""

    def __init__(self, system_prompt):
        self.model = init_chat_model(f"openrouter:{config.LLM_MODEL}")
        self.messages = [SystemMessage(system_prompt)]

    def ask(self, content):
        self.messages.append(HumanMessage(content))
        try:
            reply = self.model.invoke(self.messages)
        except Exception as e:
            _fail("writing", e)
        self.messages.append(reply)
        return _text(reply)

    def write(self, notes, budget, avoid=""):
        """avoid: problems a reviewer found in an earlier version, so this fresh attempt does better."""
        task = WRITE_TASK.format(budget=budget, notes=notes)
        if avoid:
            task += "\n\n# An earlier version of this script had these problems. Avoid all of them:\n" + avoid
        return self.ask(task)
