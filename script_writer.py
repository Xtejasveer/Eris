"""The `generate` command: the model researches and writes the lecture (script_agent.py), code validates it."""

import json
import sys
from datetime import datetime

import config
import figures
from persona import persona_to_text
from prompts import research_prompt, script_prompt
from script_parser import estimate_minutes, parse_script, word_budget
from script_agent import ScriptWriter, run_research
from quality_loop import review
from script_pipeline import ScriptPipeline
from script_fixes import drop_visual
from tools import program_output, run_code_file, set_lecture
from visual_builder import drop_visual_segments, ensure_visuals


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


def build_visuals(lecture_id, topic, text, segments):
    """Build every [VISUAL] (reusing ones already built). A visual that can't be built is removed, with its
    [VISUAL_SET]s, as a recorded last resort. Returns (text, segments, fixes)."""
    failed = ensure_visuals(segments, lecture_id, topic, config.MAX_VISUALS)
    fixes = []
    for vid, reason in failed:
        text = drop_visual(text, vid)
        fixes.append(f"removed the visual '{vid}' ({reason[:200]})")
        print(f"[generate] auto-fixed: {fixes[-1]}")
    if failed:
        segments = drop_visual_segments(segments, [vid for vid, _ in failed])
    return text, segments, fixes


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


def _limit_errors(segments):
    """Rules from the prompt that models often ignore: short notes, few question breaks."""
    errors, section = [], "Opening"
    for seg in segments:
        if seg.get("name") == "SECTION":
            section = seg["args"]["title"]
        elif seg.get("name") == "NOTE":
            lines = [ln for ln in seg["args"]["text"].splitlines() if ln.strip()]
            if len(lines) > config.NOTE_MAX_LINES:
                errors.append(f'section "{section}": the [NOTE] starting "{lines[0][:40]}" has {len(lines)} lines; '
                              "keep each [NOTE] to 2-6 short lines (split it, or show a long "
                              "trace with code instead)")
    checks = sum(1 for s in segments if s.get("name") == "DOUBT_CHECK")
    if checks > config.MAX_DOUBT_CHECKS + 1:
        errors.append(f"the script has {checks} [DOUBT_CHECK] markers; use at most {config.MAX_DOUBT_CHECKS} "
                      "(after the major blocks) plus the final one on the last line. Remove the extra ones")
    return errors


def _flow_errors(segments):
    """Every diagram block is drawn, and the sentence about it comes after its [FLOW_NEXT], not before."""
    import re as _re
    from script_checks import said_too_early
    errors, flows = [], {}
    for i, seg in enumerate(segments):
        a = seg.get("args", {})
        if seg.get("name") == "FLOW":
            flows[a["id"]] = [0, [b["label"] for b in a.get("blocks", [])]]
        elif seg.get("name") == "FLOW_NEXT" and a["id"] in flows:
            k = flows[a["id"]][0]
            flows[a["id"]][0] += 1
            blocks = flows[a["id"]][1]
            before = segments[i - 1] if i else {}
            after = segments[i + 1] if i + 1 < len(segments) else {}
            said_before = _re.split(r"(?<=[.!?])\s+", before["text"].strip())[-1] if before.get("kind") == "say" else ""
            said_after = after["text"].split(". ")[0] if after.get("kind") == "say" else ""
            if said_too_early(said_before, said_after, a.get("label", ""), blocks[k + 1] if k + 1 < len(blocks) else ""):
                errors.append(f'the sentence about block "{a.get("label")}" comes before its [FLOW_NEXT id="{a["id"]}"]; '
                              "put the [FLOW_NEXT] first, then the sentence naming the block, so it appears as you say it")
    for fid, (shown, blocks) in flows.items():
        if shown < len(blocks):
            errors.append(f'the diagram "{fid}" draws only {shown} of its {len(blocks)} blocks; add a [FLOW_NEXT id="{fid}"] '
                          "for each remaining block, each followed by a sentence naming it")
    return errors


def _doubt_check_errors(segments):
    """The prompt asks for a question break after each of the first three concept sections and one at the end."""
    from script_fixes import concept_sections
    want = min(config.MAX_DOUBT_CHECKS, len(concept_sections(segments))) + 1
    have = sum(1 for s in segments if s.get("name") == "DOUBT_CHECK")
    errors = []
    if have < want:
        errors.append(f"the script has {have} [DOUBT_CHECK](s); put one at the end of each of the first "
                      f"{want - 1} concept sections and one as the very last line ({want} in all)")
    errors += _flow_errors(segments)
    from script_fixes import early_doubt_checks
    for section in early_doubt_checks(segments):
        errors.append(f'section "{section}" asks for doubts in the middle: move its [DOUBT_CHECK] to the end of the '
                      "section, after everything it teaches (just before the next [SECTION])")
    return errors


def visual_source_errors(segments, figs):
    """A [VISUAL] is only allowed for a graph in the material: [(visual id, problem)] for the others."""
    out, known = [], figures.graphs(figs)
    listed = "; ".join(f'from="{f["ref"]}" ({f["title"]})' for f in known)
    for seg in segments:
        if seg.get("name") != "VISUAL":
            continue
        a = seg["args"]
        if not known:
            out.append((a["id"], f'[VISUAL id="{a["id"]}"]: the material has no graph, so the script makes none; remove '
                                 "this [VISUAL] and its [VISUAL_SET]s (show a slide or write a note instead)"))
        elif not figures.matches(a.get("from"), figs):
            out.append((a["id"], f'[VISUAL id="{a["id"]}"] must recreate a graph from the material: add from="..." with '
                                 f"one of: {listed}; or remove it"))
    return out


def environment_errors(segments, env):
    """Markers from an environment this class doesn't have (its material has no code / no graphs / no slides)."""
    if not env:
        return []
    errors = []
    for name in ("code", "graphs", "slides"):
        if env.get(name):
            continue
        used = sorted({s["name"] for s in segments if s.get("name") in figures.ENV_MARKERS[name]})
        if used:
            errors.append(f"this class has no {name} (the teacher's material has none), so remove every "
                          f"{', '.join(f'[{u}]' for u in used)} and teach it in the notebook instead")
    return errors


def flow_source_errors(segments, figs):
    """A [FLOW] is only allowed for a diagram or a written step list in the material: [(id, problem)]."""
    out, known = [], figures.flows(figs)
    listed = "; ".join(f'from="{f["ref"]}" ({f["title"]})' for f in known)
    for seg in segments:
        if seg.get("name") != "FLOW":
            continue
        a = seg["args"]
        if not known:
            out.append((a["id"], f'[FLOW id="{a["id"]}"]: the material has no diagram or list of steps, so the script '
                                 "draws none; remove this [FLOW] and its [FLOW_NEXT]s (write a note instead)"))
        elif not figures.matches(a.get("from"), figs, kind="flow"):
            out.append((a["id"], f'[FLOW id="{a["id"]}"] must draw a diagram or list of steps from the material: '
                                 f'add from="..." with one of: {listed}; or remove it'))
    return out


def check_generated(text, budget, slide_count, figs=None, env=None):
    """parse_script plus checks that only make sense for a freshly generated script."""
    segments, errors = parse_script(text, slide_count)
    errors += environment_errors(segments, env)
    if figs is not None:
        errors += [msg for _, msg in visual_source_errors(segments, figs)]
        errors += [msg for _, msg in flow_source_errors(segments, figs)]
    if segments and segments[0].get("name") != "SECTION":
        errors.append("the script must start with [SECTION title=\"Opening\"]; "
                      "your final message must contain the WHOLE script, not just the end")
    errors += _notebook_errors(segments)
    errors += _limit_errors(segments)
    errors += _doubt_check_errors(segments)
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
    # Edited visual descriptions are rebuilt; unchanged ones are reused.
    failed = ensure_visuals(segments, lecture_id, manifest["topic"], config.MAX_VISUALS)
    if failed:
        return [f"the visual '{vid}' could not be built: {reason}. Edit its description or remove it."
                for vid, reason in failed]
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
    args = (persona, persona_to_text(persona), manifest["topic"], manifest["duration_min"], budget)
    prompt = script_prompt(*args)  # the writer: no tools, so no tool instructions
    print(f"[generate] step 1/2: researching the material with {config.LLM_MODEL} ...")
    env = figures.lecture_environments(lecture_id, manifest, count_slides(lecture_id))
    env_text = "\n\n# Environments for this class\n" + figures.describe_environments(env)
    notes = run_research(research_prompt(*args) + env_text, f"script_{lecture_id}")
    figs = figures.load(lecture_id)  # graphs and diagrams found in the material at index time
    notes += env_text
    notes += ("\n\n# Diagrams and step lists in the material (the only processes you may draw with [FLOW])\n"
              + figures.describe(figures.flows(figs)))
    if figures.graphs(figs):
        how = ("make each interactive with [VISUAL]" if env.get("graphs") else "explain each on its slide")
        notes += f"\n\n# Graphs in the material ({how})\n" + figures.describe(figures.graphs(figs))
    print(f"[generate] step 2/2: writing the script (~{budget} words) in one message, no tools ...")
    writer = ScriptWriter(prompt)
    slides = count_slides(lecture_id)

    pipe = ScriptPipeline(writer, budget, slides, notes, figs, env)
    text, segments, errors = pipe.until_valid(writer.write(notes, budget))
    if errors:  # e.g. far too short: code can't repair that, so a fresh writer tries once more
        print(f"[generate] {len(errors)} problem(s) left; a fresh writer rewrites the script once more")
        pipe.rounds.append({"kind": "rewrite", "problems": len(errors)})
        text, segments, errors = pipe.until_valid(pipe.rewrite("\n".join(f"- {e}" for e in errors)))
    if errors:
        failed = config.lecture_dir(lecture_id) / "script_failed.md"
        failed.write_text(text + "\n", encoding="utf-8")
        print(f"[generate] the script still has {len(errors)} error(s):")
        for e in errors:
            print("  " + e)
        print(f"[generate] Saved to {failed}. Fix it by hand, save as script.md, and run approve, or run generate again.")
        sys.exit(1)
    text, segments = pipe.finalize(text)
    text, segments, report = review(pipe, text, segments, persona, manifest["topic"])
    text, segments, visual_fixes = build_visuals(lecture_id, manifest["topic"], text, segments)

    save_script(lecture_id, text, segments)
    (config.lecture_dir(lecture_id) / "script_failed.md").unlink(missing_ok=True)  # now stale
    judge_path = config.lecture_dir(lecture_id) / "judge.json"
    report = report or {"model": "", "findings": [], "error": "the quality check is turned off (JUDGE_ENABLED=false)"}
    report["rounds"] = pipe.rounds  # what happened on the way, for Studio (auto_fixes: set by review)
    report["advice"] = pipe.advice  # soft problems the writer left (long sentences, little notebook use)
    report.setdefault("auto_fixes", pipe.auto_fixes)
    report["auto_fixes"] = list(report["auto_fixes"]) + visual_fixes
    if report:
        judge_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        judge_path.unlink(missing_ok=True)

    minutes = estimate_minutes(segments)
    manifest.update({
        "status": "draft",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "approved_at": None,
        "script_md": "script.md",
        "script_json": "script.json",
        "estimated_min": minutes,
        "judge": {k: report[k] for k in ("score", "blockers", "failed_minor") if k in report} if report else None,
    })
    config.save_manifest(lecture_id, manifest)

    target = manifest["duration_min"] * (1 - config.DOUBT_TIME_SHARE)
    print(f"[generate] estimated {minutes} min of teaching (target about {target:.0f} min + doubts)")
    if abs(minutes - target) > 0.15 * target:
        print("[generate] WARNING: more than 15% off the target. Consider editing script.md.")
    print(f"Script saved as DRAFT. Review script.md, then run: python main.py approve --lecture {lecture_id}")
