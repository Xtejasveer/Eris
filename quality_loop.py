"""Quality rounds: Jev's findings go back to the same script writer until the script is good enough.

A script goes back when it has any blocker or scores below JUDGE_MIN_SCORE. Every failed check (blocker and
minor) and every rejected while-speaking pair is sent, most important first, with how sure Jev was. Up to
JUDGE_REVISIONS rounds; the best version seen is kept. Pairs Jev rejects in the kept version are un-flagged.
"""

import config
from script_fixes import remove_flags
from script_judge import better, judge_script

QUALITY_FEEDBACK = "A reviewer scored it {score:.2f}. Problems, most important first:\n"


def needs_work(report):
    return not report["error"] and (report["blockers"] > 0 or report["score"] < config.JUDGE_MIN_SCORE)


def quality_feedback(report, segments=()):
    """Every failed check and rejected pair as one message for the writer. For "narration is speech", the
    section's spoken lines are quoted, because the reviewer can say THAT a section is wrong but not WHERE."""
    spoken = {}
    section = None
    for seg in segments:
        if seg.get("name") == "SECTION":
            section = seg["args"]["title"]
        elif seg["kind"] == "say":
            spoken.setdefault(section, []).append(seg["text"])
    failed = sorted((f for f in report["findings"] if not f["passed"]),
                    key=lambda f: (f["severity"] != "blocker", f["value"]))
    lines = []
    for f in failed:
        lines.append(f"- [{f['severity']}] {f['fix']} (the reviewer was {round((1 - f['value']) * 100)}% sure this is wrong)")
        if f["check"] == "narration_is_speech" and f["section"] in spoken:
            lines += [f"    spoken now: \"{t[:110]}\"" for t in spoken[f["section"]][:8]]
    lines += [f"- [minor] In section \"{p['section']}\", the sentence after a note or program is not about it: "
              f"\"{p['said'][:80]}\". Put the sentence that describes it right after it."
              for p in report.get("pairs", []) if p["unflag"]]
    if not lines:  # only the score is low
        lines = ["- Make the narration clearer and closer to the persona's teaching style."]
    return QUALITY_FEEDBACK.format(score=report["score"]) + "\n".join(lines)


def review(pipe, text, segments, persona, topic):
    """Judge; while the script needs work, send the findings back (up to JUDGE_REVISIONS rounds).
    Returns (text, segments, report or None when the judge is off), keeping the best version."""
    if not config.JUDGE_ENABLED:
        return text, segments, None
    print(f"[judge] checking the script with {config.JUDGE_MODEL} ...")
    report = latest = judge_script(segments, persona, topic, pipe.figures)
    report["auto_fixes"] = list(pipe.auto_fixes)
    print_report(report)
    latest_segments = segments
    for n in range(1, config.JUDGE_REVISIONS + 1):
        if not needs_work(latest):
            break
        feedback = quality_feedback(latest, latest_segments)
        print(f"[judge] score {latest['score']:.2f} with {latest['blockers']} blocker(s): a fresh writer rewrites the "
              f"script with the findings (quality round {n}/{config.JUDGE_REVISIONS})")
        pipe.rounds.append({"kind": "quality", "problems": feedback.count("\n- ") + 1})
        new_text, new_segments, problems = pipe.until_valid(pipe.rewrite(feedback))
        if problems:
            print("[judge] the rewrite broke the script; keeping the best version so far")
            break
        new_text, new_segments = pipe.finalize(new_text)
        latest, latest_segments = judge_script(new_segments, persona, topic, pipe.figures), new_segments
        latest["auto_fixes"] = list(pipe.auto_fixes)
        print_report(latest)
        if not latest["error"] and better(latest, report):
            print("[judge] this rewrite is the best so far")
            text, segments, report = new_text, new_segments, latest
        else:
            print("[judge] this rewrite is not better; keeping the best version so far")
    return (*unflag_pairs(text, segments, report), report)


def unflag_pairs(text, segments, report):
    """Pairs where Jev says the sentence is not about the writing go back to 'write first, then speak'."""
    drop = {p["flag"] for p in report.get("pairs", []) if p["unflag"]}
    report["unflagged"] = len(drop)
    if not drop:
        return text, segments
    flagged = [s for s in segments if s.get("args", {}).get("while_speaking")]
    for n, seg in enumerate(flagged):
        if n in drop:
            seg["args"].pop("while_speaking")
    for p in report["pairs"]:
        if p["unflag"]:
            print(f"[judge] un-flagged a pair in \"{p['section']}\" (P={p['value']}): \"{p['said'][:60]}\"")
    return remove_flags(text, drop), segments


def print_report(report):
    if report["error"]:
        return
    pairs = report.get("pairs", [])
    print(f"[judge] score {report['score']:.2f}, {report['blockers']} blocker(s), "
          f"{report['failed_minor']} minor issue(s), {sum(p['unflag'] for p in pairs)}/{len(pairs)} "
          f"while-speaking pair(s) rejected, cost ${report['cost']:.5f}")
    for f in report["findings"]:
        if not f["passed"]:
            where = f" [{f['section']}]" if f["section"] else ""
            print(f"[judge]   {f['severity']}: {f['check']}{where} = {f['value']}")
