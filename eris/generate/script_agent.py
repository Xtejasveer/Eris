"""The two LLM steps of `generate`.

1. Research: an agent with tools reads the outline, searches the material and dry-runs every program.
2. Writing: a separate model call with NO tools writes the whole script from those notes. It stops at every
   [READ_OUTPUT]: code runs the program just written in a real terminal, and the writer continues with what it
   really printed. So the narration about an output is always written after seeing that output, never guessed.

Models that write the script while they are still calling tools split it over several messages and mix in
chatter ("Oops, let me fix that"). With no tools in step 2 there is nothing to interleave, so the script
arrives whole. Code (script_writer.py) then validates it and asks this same writer to fix errors.
"""

import re
import sys
import time

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from eris import config
from eris.tools import dry_run_python, program_output, read_outline, run_code_file, search_material

RESEARCH_KICKOFF = "Start the research now, then reply with your plan."

READ_OUTPUT = "[READ_OUTPUT]"
MAX_RUNS = 12            # programs one script may run (each one is a pause for the real output)
OUTPUT_SHOWN_CHARS = 1500
RUN_LINE_RE = re.compile(r'^\s*\[RUN\s+cmd="python\s+([^"\s]+)"[^\]]*\]\s*$')
CONTINUE_AFTER_RUN = """The terminal really printed this for {file}:
```
{output}
```
Continue the script exactly where you stopped, starting with the line right after [READ_OUTPUT]: describe what it
printed above (never type the output itself), then go on with the rest of the script. Do not repeat anything you
already wrote."""
NO_PROGRAM = """There is no program called {file} written above this [RUN], so nothing ran. Continue the script
exactly where you stopped: first write that program with [WRITE_CODE file="{file}"] ... [/WRITE_CODE] and
[RUN cmd="python {file}"] again, or go on without it. Do not repeat anything you already wrote."""


def _last_program(script):
    """The program the writer stopped for: (file, code) of the last [RUN] after the last [READ_OUTPUT], with that
    file's latest [WRITE_CODE] (code None if there is none). (None, None) when no [RUN] is waiting for its output
    (the script is finished)."""
    text = script.rstrip()
    after = text[text.rfind(READ_OUTPUT) + len(READ_OUTPUT):] if READ_OUTPUT in text else text
    runs = [m.group(1) for ln in after.splitlines() if (m := RUN_LINE_RE.match(ln))]
    if not runs:
        return None, None
    file, code = runs[-1], None
    for block in re.finditer(r'\[WRITE_CODE\s+file="([^"]+)"[^\]]*\]\n(.*?)\n\[/WRITE_CODE\]', script, re.S):
        if block.group(1) == file:
            code = block.group(2)
    return file, code


WRITE_TASK = """Write the whole lecture script now, in this one message (about {budget} words of narration),
from [SECTION title="Opening"] to the end of the Closing.

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
    for attempt in (1, 2):  # one retry: OpenRouter sometimes fails a request briefly ("retry shortly")
        try:
            result = agent.invoke({"messages": [{"role": "user", "content": RESEARCH_KICKOFF}]},
                                  {**cfg, "configurable": {"thread_id": f"{thread_id}_{attempt}"}})
            break
        except Exception as e:
            if attempt == 2:
                _fail("research", e)
            print(f"[generate] the research call failed ({str(e)[:120]}); retrying once in 5 s")
            time.sleep(5)
    return research_notes(result["messages"])


class ScriptWriter:
    """Step 2: a plain model call with no tools. Keeps the conversation so fixes see the script and notes."""

    def __init__(self, system_prompt):
        self.model = init_chat_model(f"openrouter:{config.LLM_MODEL}")
        self.messages = [SystemMessage(system_prompt)]

    def ask(self, content):
        self.messages.append(HumanMessage(content))
        for attempt in (1, 2):  # one retry for a brief OpenRouter failure
            try:
                reply = self.model.invoke(self.messages)
                break
            except Exception as e:
                if attempt == 2:
                    _fail("writing", e)
                print(f"[generate] the writing call failed ({str(e)[:120]}); retrying once in 5 s")
                time.sleep(5)
        self.messages.append(reply)
        return _text(reply)

    def _invoke(self, messages, stop=None):
        for attempt in (1, 2):  # one retry for a brief OpenRouter failure
            try:
                return self.model.invoke(messages, stop=stop)
            except Exception as e:
                if attempt == 2:
                    _fail("writing", e)
                print(f"[generate] the writing call failed ({str(e)[:120]}); retrying once in 5 s")
                time.sleep(5)

    def write(self, notes, budget, avoid=""):
        """Write the whole script, pausing at every [READ_OUTPUT] to run the program in a real terminal and hand the
        writer its real output before it says anything about it.
        avoid: problems a reviewer found in an earlier version, so this fresh attempt does better."""
        task = WRITE_TASK.format(budget=budget, notes=notes)
        if avoid:
            task += "\n\n# An earlier version of this script had these problems. Avoid all of them:\n" + avoid
        talk = self.messages + [HumanMessage(task)]
        script = ""
        for _ in range(MAX_RUNS + 1):
            part = _text(self._invoke(talk, stop=[READ_OUTPUT]))
            script = (script.rstrip("\n") + "\n" + part.lstrip("\n")) if script else part
            file, code = _last_program(script)
            if file is None:  # the writer finished (it didn't stop at an output)
                break
            if code is None:
                note = NO_PROGRAM.format(file=file)
            else:
                exit_code, stdout, stderr = run_code_file(code, filename=file)
                output = program_output(exit_code, stdout, stderr).rstrip() or "(no output)"
                print(f"[generate] ran {file} for the writer: {'ok' if exit_code == 0 else f'exit {exit_code}'}")
                note = CONTINUE_AFTER_RUN.format(file=file, output=output[:OUTPUT_SHOWN_CHARS])
                script = script.rstrip("\n") + "\n" + READ_OUTPUT
            talk = talk + [AIMessage(script), HumanMessage(note)]
        # Later fix rounds see one plain conversation: the task and the whole script.
        self.messages += [HumanMessage(task), AIMessage(script)]
        return script
