"""Stage a lecture's saved lesson again (step 3 only), without writing the lesson or touching the saved script.

For testing the stager: `python main.py stage --lecture <id> [--runs N]` stages lesson.md and reports how it went:
problems in the first draft, fix rounds, Jev's verdict, code repairs and how often the screen changes.
"""

import time

from eris import config
from eris.generate.lesson import parse_lesson
from eris.generate.script_parser import word_budget
from eris.generate.staging import stage_lesson

SCREEN_MARKERS = {"SLIDE": "slides", "NOTE": "notebook", "NOTE_TITLE": "notebook", "NEW_PAGE": "notebook",
                  "WRITE_CODE": "code", "RUN": "code", "OPEN_FILE": "code", "FLOW": "visual", "VISUAL": "visual",
                  "OPEN_VISUAL": "visual", "OPEN_FLOW": "visual"}


def screen_switches(segments):
    """How often the class screen changes environment, and how often it changes slide."""
    env, slide, envs, slides = None, None, 0, 0
    for seg in segments:
        name = seg.get("name")
        target = SCREEN_MARKERS.get(name)
        if target and target != env:
            envs += env is not None
            env = target
        if name == "SLIDE":
            n = seg["args"].get("n")
            slides += slide is not None and n != slide
            slide = n
    return envs, slides


def run_stage_only(lecture_id, prompt_fn=None):
    """Stage lesson.md once. prompt_fn(persona, topic, language) builds the stager prompt (default: the current one).
    Returns the run's measurements as a dict."""
    from eris.classroom.actions import _load_slides
    from eris.generate.script_writer import count_slides
    from eris.material import figures
    from eris.material.images import load as load_pictures
    from eris.prompts import staging_prompt
    from eris.tools import set_lecture

    manifest = config.load_manifest(lecture_id)
    set_lecture(lecture_id)
    lesson_text = (config.lecture_dir(lecture_id) / "lesson.md").read_text(encoding="utf-8").strip()
    sections, _ = parse_lesson(lesson_text)
    persona = manifest["persona"]
    _, speaking_min = config.lecture_times(manifest)
    language = config.lecture_language(manifest)
    env = figures.lecture_environments(lecture_id, manifest, count_slides(lecture_id))
    figs = figures.load(lecture_id)
    pictures, slides = load_pictures(lecture_id), _load_slides(lecture_id)
    rounds = []
    started = time.time()
    text, segments, problems, report, pipe = stage_lesson(
        lesson_text, sections, (prompt_fn or staging_prompt)(persona, manifest["topic"], language),
        word_budget(speaking_min), slides, figs, env, pictures, rounds)
    first = rounds[0] if rounds and rounds[0]["kind"] == "rules" else None
    envs, slide_changes = screen_switches(segments)
    ok_report = report and not report.get("error")
    return {
        "lecture": lecture_id,
        "failed": bool(problems),
        "first_draft_problems": first["problems"] if first else 0,
        "rule_rounds": sum(r["kind"] == "rules" for r in rounds),
        "restaged": any(r["kind"] == "restage" for r in rounds),
        "jev_rounds": sum(r["kind"] == "staging" for r in rounds),
        "jev_blockers": report["blockers"] if ok_report else None,
        "jev_minor": report["failed_minor"] if ok_report else None,
        "jev_score": round(report["score"], 3) if ok_report else None,
        "jev_failed": sorted({f["check"] for f in report["findings"] if not f["passed"]}) if ok_report else [],
        "code_repairs": len(pipe.auto_fixes),
        "reworded": len(pipe.drift),
        "env_switches": envs,
        "slide_changes": slide_changes,
        "markers": sum(1 for s in segments if s["kind"] != "say"),
        "seconds": round(time.time() - started),
        "script": text,
    }
