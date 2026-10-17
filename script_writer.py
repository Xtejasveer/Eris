"""The `generate` command: the script agent writes the lecture, code validates it."""

import json
import sys
from datetime import datetime

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

import config
from persona import persona_to_text
from prompts import script_prompt
from script_parser import estimate_minutes, parse_script, word_budget
from tools import dry_run_python, program_output, read_outline, run_code_file, search_material, set_lecture


# Smaller models skip the tools unless the first message spells the steps out.
KICKOFF = """Write the full lecture script now. Work in this order:
1. Call read_outline().
2. Call search_material for each concept you will teach.
3. Call dry_run_python with the exact code of every file you will RUN.
4. Then output the whole script, about {budget} words of narration. Write every marker with key=value args,
   e.g. [SLIDE n=1], [SECTION title="Recap"]. Put keywords and worked examples in [NOTE] blocks.
   Highlight code by quoting it: [HIGHLIGHT file="demo.py" text="<exact code from one line>"].
Do not write any part of the script while you are still calling tools. Your FINAL message must contain
the ENTIRE script, from the Opening section to the last [DOUBT_CHECK]."""


def build_script_agent(system_prompt):
    return create_agent(
        model=f"openrouter:{config.LLM_MODEL}",
        tools=[search_material, read_outline, dry_run_python],
        system_prompt=system_prompt,
        checkpointer=InMemorySaver(),
        name="script_writer",
    )


def extract_text(result):
    """Text of the last message. Handles content given as a list of blocks."""
    content = result["messages"][-1].content
    if isinstance(content, list):
        parts = [b.get("text", "") if isinstance(b, dict) else str(b) for b in content]
        content = "".join(parts)
    text = content.strip()
    # Models sometimes wrap the whole script in ``` fences despite the prompt.
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text[: text.rfind("```")].strip()
    return text


def fill_expected_outputs(segments, files=None):
    """Run the code for every RUN ourselves and store expected_output. Never trust the model here.

    files: code already on the board ({name: code}), for a doubt answer that re-runs a lecture program.
    """
    latest_code = dict(files or {})
    for seg in segments:
        if seg.get("name") == "WRITE_CODE":
            latest_code[seg["args"]["file"]] = seg["args"]["code"]
        elif seg.get("name") == "RUN":
            file = seg["args"]["cmd"].split(" ", 1)[1]
            exit_code, stdout, stderr = run_code_file(latest_code.get(file, ""), filename=file)
            seg["expected_output"] = program_output(exit_code, stdout, stderr)
            label = "ok" if exit_code == 0 else f"exit {exit_code}"
            print(f"[generate] ran {file}: {label}")


def count_slides(lecture_id):
    """Total PPTX slides listed in outline.json (0 if unknown)."""
    try:
        outline = json.loads((config.lecture_dir(lecture_id) / "outline.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return sum(len(entry["items"]) for entry in outline if entry.get("type") == "pptx")


def _notebook_errors(segments):
    """Every section with code needs a [NOTE] block, so the notebook is really used."""
    errors, section, has_note, has_code = [], "Opening", False, False

    def close():
        if has_code and not has_note:
            errors.append(f'section "{section}" has code but no [NOTE] block; write its keywords '
                          "and a small example in the notebook before the code")

    for seg in segments:
        if seg.get("name") == "SECTION":
            close()
            section, has_note, has_code = seg["args"]["title"], False, False
        elif seg.get("name") == "NOTE":
            has_note = True
        elif seg.get("name") == "WRITE_CODE":
            has_code = True
    close()
    return errors


def check_generated(text, budget, slide_count):
    """parse_script plus checks that only make sense for a freshly generated script."""
    segments, errors = parse_script(text, slide_count)
    if segments and segments[0].get("name") != "SECTION":
        errors.append("the script must start with [SECTION title=\"Opening\"]; "
                      "your final message must contain the WHOLE script, not just the end")
    errors += _notebook_errors(segments)
    for seg in segments:
        if seg.get("name") == "HIGHLIGHT" and "text" not in seg["args"]:
            errors.append(f'[HIGHLIGHT file="{seg["args"]["file"]}" lines="{seg["args"]["lines"]}"] uses a line number; '
                          'quote the code instead: text="<exact code from that line>"')
    words = sum(len(s["text"].split()) for s in segments if s["kind"] == "say")
    if words < 0.6 * budget:
        errors.append(f"the script has only {words} words of narration; write about {budget}")
    return segments, errors


def approve_script(lecture_id):
    """Re-read script.md, validate it, refresh outputs and approve. Returns a list of errors ([] = approved)."""
    manifest = config.load_manifest(lecture_id)
    if manifest.get("status") != "draft":
        return [f"Only a draft can be approved; this lecture is '{manifest.get('status')}'."]
    script_md = config.lecture_dir(lecture_id) / "script.md"
    if not script_md.exists():
        return ["script.md not found. Generate the script first."]
    # Re-read from disk: the teacher may have edited it by hand.
    segments, errors = parse_script(script_md.read_text(encoding="utf-8"), count_slides(lecture_id))
    if errors:
        return errors
    set_lecture(lecture_id)
    fill_expected_outputs(segments)  # Edits may have changed the code.
    out = config.lecture_dir(lecture_id) / "script.json"
    out.write_text(json.dumps(segments, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest.update({
        "status": "approved",
        "approved_at": datetime.now().isoformat(timespec="seconds"),
        "estimated_min": estimate_minutes(segments),
    })
    config.save_manifest(lecture_id, manifest)
    return []


def save_script(lecture_id, text, segments):
    out = config.lecture_dir(lecture_id)
    (out / "script.md").write_text(text + "\n", encoding="utf-8")
    (out / "script.json").write_text(json.dumps(segments, indent=2, ensure_ascii=False), encoding="utf-8")


def _ask(agent, message, thread_id):
    """Invoke the agent once; exit with a hint on API/model problems."""
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}
    try:
        return extract_text(agent.invoke({"messages": [{"role": "user", "content": message}]}, cfg))
    except Exception as e:
        print(f"[generate] the model call failed: {e}")
        print("[generate] Check OPENROUTER_API_KEY, and that LLM_MODEL supports tool calling.")
        sys.exit(1)


def run_generate(lecture_id):
    manifest = config.load_manifest(lecture_id)
    if not config.status_at_least(manifest, "indexed"):
        print(f"[generate] Lecture must be indexed first. Run: python main.py index --lecture {lecture_id}")
        sys.exit(1)
    if manifest["status"] == "approved":
        print("[generate] note: this lecture was approved; the new script goes back to DRAFT.")

    set_lecture(lecture_id)
    persona = manifest["persona"]
    budget = word_budget(manifest["duration_min"])
    prompt = script_prompt(persona, persona_to_text(persona), manifest["topic"], manifest["duration_min"], budget)
    agent = build_script_agent(prompt)
    thread_id = f"script_{lecture_id}"

    print(f"[generate] writing script (~{budget} words) with {config.LLM_MODEL} ...")
    slides = count_slides(lecture_id)
    text = _ask(agent, KICKOFF.format(budget=budget), thread_id)
    segments, errors = check_generated(text, budget, slides)

    for attempt in range(1, config.FIX_ATTEMPTS + 1):
        if not errors:
            break
        print(f"[generate] {len(errors)} error(s) in the script; asking the model to fix them "
              f"(attempt {attempt}/{config.FIX_ATTEMPTS})")
        fix = "Your script has these errors. Return the full corrected script only:\n" + "\n".join(errors)
        text = _ask(agent, fix, thread_id)
        segments, errors = check_generated(text, budget, slides)

    if errors:
        failed = config.lecture_dir(lecture_id) / "script_failed.md"
        failed.write_text(text + "\n", encoding="utf-8")
        print(f"[generate] the script still has {len(errors)} error(s):")
        for e in errors:
            print("  " + e)
        print(f"[generate] Saved to {failed}. Fix it by hand, save as script.md, and run approve, or run generate again.")
        sys.exit(1)

    fill_expected_outputs(segments)
    save_script(lecture_id, text, segments)
    (config.lecture_dir(lecture_id) / "script_failed.md").unlink(missing_ok=True)  # now stale

    minutes = estimate_minutes(segments)
    manifest.update({
        "status": "draft",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "approved_at": None,
        "script_md": "script.md",
        "script_json": "script.json",
        "estimated_min": minutes,
    })
    config.save_manifest(lecture_id, manifest)

    target = manifest["duration_min"] * (1 - config.DOUBT_TIME_SHARE)
    print(f"[generate] estimated {minutes} min of teaching (target about {target:.0f} min + doubts)")
    if abs(minutes - target) > 0.15 * target:
        print("[generate] WARNING: more than 15% off the target. Consider editing script.md.")
    print(f"Script saved as DRAFT. Review script.md, then run: python main.py approve --lecture {lecture_id}")
