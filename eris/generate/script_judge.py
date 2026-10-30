"""Judge a generated script with Jev: yes/no questions answered as probabilities. No text is generated.

Code already checks everything that can be checked exactly (format, quotes, limits). Jev checks meaning:
do the notes match the code, is "Must cover" taught, does it sound like the teacher, and so on.
Each question has a weight, a severity and a ready-made fix; quality_loop.py sends the failed ones back
to the script writer. Never raises: if Jev can't be reached, the report says so and generation goes on.
"""

import httpx

from eris import config
from eris.generate.script_fixes import FRAMING_RE
DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"


def _noul(instructions, true, false):
    return {"type": "noul", "instructions": instructions, "criteria": {"true": true, "false": false}}


# id: (question, weight, severity, fix). {section} is filled in for section questions.
SECTION_QUESTIONS = {
    "notes_match_code": (_noul(
        "Do the worked examples and traces in the notebook describe the same behaviour as the code and its real output?",
        "Every notebook example or trace matches the code: same start values, direction and stopping point.",
        "A notebook example or trace describes different behaviour from the code or its output."),
        2, "blocker", 'In section "{section}", make every notebook example and trace match the program and its real output exactly.'),
    "narration_matches_output": (_noul(
        "Does the narration describe the program output correctly, as shown in real_outputs?",
        "Whatever the narration says about the output agrees with real_outputs.",
        "The narration states an output that differs from real_outputs."),
        2, "blocker", 'In section "{section}", describe the program output exactly as it really prints.'),
    "narration_is_speech": (_noul(
        "Is every narration line natural speech a teacher would say aloud?",
        "Narration contains only sentences meant to be spoken.",
        "Narration contains markup, raw program output, or note fragments that would sound wrong read aloud."),
        1, "minor", 'In section "{section}", the narration must contain only spoken sentences; put notes in [NOTE] and markers on their own lines.'),
    "graph_matches_text": (_noul(
        "Does each graph in graphs fit what this section teaches: what it plots agrees with the narration, notebook "
        "and code, and after each slider move in slider_moves, does teacher_says describe correctly what the graph "
        "shows at that value?",
        "Every graph agrees with the lesson, and every sentence after a slider move matches what the graph shows.",
        "A graph plots something the lesson doesn't teach, or a sentence after a slider move describes something "
        "the graph does not show at that value."),
        2, "blocker", 'In section "{section}", make the [VISUAL] plot what the lesson teaches. Set each [VISUAL_SET] '
                      "to the value that the next sentence is about. Move a [VISUAL_SET] if it is before the wrong "
                      "sentence. Do not change the sentences."),
    "graph_matches_material": (_noul(
        "Does each graph in graphs show the same quantity, axes and kind of graph as its material_graph?",
        "Each graph recreates the graph from the teacher's material.",
        "A graph plots something different from the graph in the material."),
        1, "minor", 'In section "{section}", make the [VISUAL] recreate the graph from the material: same quantity, '
                    "axes and kind of graph, with a slider for the value worth exploring."),
    "flow_matches_material": (_noul(
        "Does each diagram in flows show the same steps, in the same order, as its material_steps?",
        "Each diagram follows the steps from the teacher's material.",
        "A diagram leaves out, adds or reorders steps compared with the material."),
        1, "minor", 'In section "{section}", make the diagram follow the steps from the material, in the same order.'),
    "pictures_explained": (_noul(
        "For each picture in pictures_shown (what the vision model saw in it and the text written in it), does the "
        "narration talk about it, describe it correctly and say what students should notice?",
        "Every picture shown is explained, and nothing said about it contradicts what it shows or the text in it.",
        "A picture is shown but never explained, or the narration says something the picture does not show."),
        1, "minor", 'In section "{section}", explain each picture you show: say what it shows (what whole, data or '
                      "scene, as it really is) and what to notice in it."),
    "explains_clearly": (_noul(
        "Would a student in this class understand this section's idea, and why it works, from what the teacher says "
        "here? Any way of explaining is fine; what matters is that it makes sense to them.",
        "A student in this class would understand the idea and why it works.",
        "A student would be left with facts or steps they can't follow or don't see the reason for."),
        2, "minor", 'In section "{section}", make the idea understandable to this class: explain what it means and why '
                      "it works, in whatever way suits them best."),
    "stays_true": (_noul(
        "Look only at the concrete facts this section states as true: dates, years, numbers, figures, names and events, "
        "and claims about the material's data itself (which years or items it covers, how they are spaced, which value "
        "is highest or lowest). Does each one agree with material (the teacher's own material, including its chart "
        "data)? Ignore explanations, analogies, opinions and examples clearly given as examples or with made-up numbers "
        "('say a shop sells 30').",
        "Every date, number, name, event and claim about the data agrees with the teacher's material.",
        "A date, number, name, event or claim about the data contradicts the material, or isn't in it."),
        2, "minor", 'In section "{section}", keep every date, number, name, event and claim about the data true to the '
                    "teacher's material; give invented numbers clearly as examples."),
    "highlights_fit": (_noul(
        "For each item in highlights, is said_next about the very thing points_at shows (the class sees that word, "
        "line, block or slide line light up while the teacher talks about it)?",
        "Every highlight lights up what the teacher is talking about at that moment.",
        "A highlight lights up something the next sentence does not talk about."),
        1, "minor", 'In section "{section}", put each highlight right before the sentence that talks about exactly '
                      "what it highlights, or remove it."),
    "has_worked_example": (_noul(
        "Does this section teach with a small worked example using concrete numbers?",
        "There is a concrete example with real values.", "The section stays abstract."),
        1, "minor", 'Add a small worked example with real numbers to section "{section}".'),
}

SCRIPT_QUESTIONS = {
    "covers_must_cover": (_noul(
        "Do opening, narration and closing together teach every item listed in must_cover?",
        "Every must_cover item is taught.", "At least one must_cover item is missing."),
        2, "blocker", "Teach every item in the persona's Must cover list."),
    "respects_avoid": (_noul(
        "Does the script stay away from every topic listed in avoid?",
        "Nothing from avoid is taught.", "The script teaches something listed in avoid."),
        2, "blocker", "Remove everything the persona lists under Avoid."),
    "opening_absence": (_noul(
        "Does the opening narration say why the teacher is absent and pass on message_to_class?",
        "Both the reason and the message are in the opening.", "The reason or the message is missing."),
        1, "minor", "In the Opening, say why the teacher is absent and give the teacher's message to the class."),
    "closing_next_class": (_noul(
        "Does the closing narration mention next_class_topic and what to prepare (next_class_prep)?",
        "Both are mentioned.", "The next class topic or the preparation is missing."),
        1, "minor", "End with the next class topic and what to prepare."),
    "sounds_like_teacher": ({"type": "score", "instructions": "How well does the narration match teaching_style?",
                             "criteria": ["Not at all", "A little", "Mostly", "Fully"]},
                            1, "minor", "Make the narration follow the persona's tone, pace, language and habits."),
}


WRITTEN = ("NOTE", "NOTE_TITLE", "WRITE", "WRITE_CODE", "VISUAL", "FLOW_NEXT", "SKETCH_ROW")
HIGHLIGHTS = ("NOTE_HIGHLIGHT", "HIGHLIGHT", "SLIDE_HIGHLIGHT", "FLOW_HIGHLIGHT", "LOOK_BACK", "SLIDE_CIRCLE")
PASS_AT = {"explains_clearly": 0.35, "pictures_explained": 0.35}  # fail only when Jev is fairly sure: a rewrite costs a round
CONTENT_CHECKS = {"notes_match_code", "narration_matches_output", "narration_is_speech", "has_worked_example",
                  "pictures_explained", "explains_clearly", "stays_true"}
STAGING_CHECKS = {"graph_matches_text", "graph_matches_material", "flow_matches_material", "highlights_fit"}

PAIR_QUESTION = ("In spoken_while_writing, is {pair}'s 'said' sentence about {pair}'s 'written' text, so it fits "
                 "to say it while that text is being written on screen?")


def _said_after(segments, i):
    """The first two sentences spoken after segment i (what the teacher says about a slider move)."""
    import re
    if i + 1 < len(segments) and segments[i + 1].get("name") == "VISUAL_SET":
        return "(another move follows straight away)"
    said = next((s["text"] for s in segments[i + 1:i + 4] if s["kind"] == "say"), "")
    return " ".join(re.split(r"(?<=[.!?।॥])\s+", said)[:2])


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def section_states(segments, figs=None, pictures=None):
    """One state per [SECTION]: its narration, notebook, code, real outputs, graphs and while-speaking pairs.
    Pairs are keyed pair_0, pair_1, ... and remember their position among all flagged markers (flag).
    figs: the material's graphs (figures.py), so each graph can be compared with the one it recreates.
    pictures: the material's pictures as the vision model read them (images.py), per slide."""
    from eris.material.figures import matches
    states, cur, flag = [], None, -1
    graphs = {}  # visual id -> its entry in the section that made it
    block_labels = {}  # flow id -> {block id: label}
    on_slide, seen_pictures = {}, set()  # slide number -> what its pictures show; slides already judged
    for p in pictures or []:
        if p.get("slide") and p.get("description"):
            on_slide.setdefault(p["slide"], []).append(
                f"{p.get('kind', 'picture')}: {p['description']}" + (f" Text in it: {p['text'][:200]}" if p.get("text") else ""))
    for i, seg in enumerate(segments):
        name, args = seg.get("name"), seg.get("args", {})
        flag += 1 if args.get("while_speaking") else 0  # counted everywhere, so it matches remove_flags
        if name == "SECTION":
            cur = {"section": args["title"], "narration": [], "notebook": [], "code": [],
                   "real_outputs": [], "graphs": {}, "flows": {}, "pictures_shown": {}, "spoken_while_writing": {},
                   "highlights": [], "_flags": {}}
            states.append(cur)
            continue
        if cur is None:
            continue
        if seg["kind"] == "say":
            cur["narration"].append(seg["text"])
        elif name in ("NOTE", "NOTE_TITLE", "WRITE"):
            cur["notebook"].append(args["text"])
        elif name == "SKETCH_ROW":
            from eris.visuals.sketch import row_line
            cur["notebook"].append("sketch: " + row_line(args["parts"]))
        elif name == "WRITE_CODE":
            cur["code"].append(f"{args['file']}:\n{args['code']}")
        elif name == "RUN":
            cur["real_outputs"].append(f"$ {args['cmd']}\n{seg.get('expected_output', '')}")
        elif name == "SLIDE" and on_slide.get(_int(args.get("n"))) and _int(args.get("n")) not in seen_pictures:
            seen_pictures.add(_int(args.get("n")))  # judged where it is first shown and explained, not when shown again
            if not FRAMING_RE.search(cur["section"]):
                cur["pictures_shown"][f"slide {args['n']}"] = " | ".join(on_slide[_int(args.get("n"))])
        elif name in HIGHLIGHTS:
            what = args.get("text") or ""
            if name == "SLIDE_CIRCLE":  # the circled picture, as the vision model saw it
                what = "the picture: " + " | ".join(on_slide.get(_int(args.get("n")), ["(no description)"]))[:300]
            if name == "FLOW_HIGHLIGHT":  # the block's words, not its id
                what = block_labels.get(args.get("id"), {}).get(args.get("block"), args.get("block", ""))
            cur["highlights"].append({"marker": name, "points_at": what, "said_next": _said_after(segments, i)})
        elif name == "FLOW":
            block_labels[args["id"]] = {b.get("id"): b["label"] for b in args.get("blocks", [])}
            fig = matches(args.get("from"), figs, kind="flow")
            cur["flows"][args["id"]] = {"title": args["title"], "blocks": [b["label"] for b in args.get("blocks", [])],
                                        "material_steps": fig["details"] if fig else ""}
        elif name == "VISUAL":
            fig = matches(args.get("from"), figs)
            graphs[args["id"]] = cur["graphs"][args["id"]] = {
                "title": args["title"], "plots": args.get("brief", ""),
                "sliders": [f"{c['name']} {c.get('min', '')}-{c.get('max', '')}" for c in args.get("controls", [])],
                "material_graph": f"{fig['title']}: {fig['details']}" if fig else "", "slider_moves": []}
        elif name == "VISUAL_SET" and args["id"] in graphs:
            if args["id"] not in cur["graphs"]:  # reopened in a later section
                cur["graphs"][args["id"]] = graphs[args["id"]]
            graphs[args["id"]]["slider_moves"].append({"control": args["control"], "value": args.get("value", "pressed"),
                                                      "teacher_says": _said_after(segments, i)})
        # Only something WRITTEN while a sentence plays is a pair to check; highlights and slider moves are checked
        # by highlights_fit / graph_matches_text. Notes and code are written first now, so this is rarely used.
        if args.get("while_speaking") and name in WRITTEN and i + 1 < len(segments) and segments[i + 1]["kind"] == "say":
            key = f"pair_{len(cur['spoken_while_writing'])}"
            cur["spoken_while_writing"][key] = {"written": args.get("code") or args.get("text") or (
                                                    f"interactive graph: {args['title']}" if name == "VISUAL" else
                                                    f"diagram block: {args.get('label', '')}" if name == "FLOW_NEXT" else
                                                    f"sketch row: {args.get('items', '')}" if name == "SKETCH_ROW" else ""),
                                                "said": segments[i + 1]["text"]}
            cur["_flags"][key] = flag
    return states


def _section_questions(state, keys=None):
    """Only ask what applies: no output questions without a RUN, no example question without code.
    keys: limit to these checks (content checks after step 2, staging checks after step 3)."""
    wanted = {"narration_is_speech"}
    if state.get("concept"):
        wanted.add("explains_clearly")
        if state.get("material"):
            wanted.add("stays_true")
    if state.get("highlights"):
        wanted.add("highlights_fit")
    if state["code"] and state["notebook"]:
        wanted.add("notes_match_code")
    if state["real_outputs"]:
        wanted.add("narration_matches_output")
    if state["code"]:  # Opening / Closing notes are messages and recaps, not lessons
        wanted.add("has_worked_example")
    if state["pictures_shown"]:
        wanted.add("pictures_explained")
    if any(f["material_steps"] for f in state["flows"].values()):
        wanted.add("flow_matches_material")
    if state["graphs"]:
        wanted.add("graph_matches_text")
        if any(g["material_graph"] for g in state["graphs"].values()):
            wanted.add("graph_matches_material")
    questions = {k: v for k, v in SECTION_QUESTIONS.items() if k in wanted and (keys is None or k in keys)}
    for key in state.get("spoken_while_writing", {}):  # one question per while_speaking pair
        questions[key] = (_noul(PAIR_QUESTION.format(pair=key), "The sentence describes what is being written.",
                                "The sentence talks about something else."), 0, "pair", "")
    return questions


MIDDLE_CHARS = 9000  # middle sections share this much narration; the opening and closing are sent whole


def script_state(segments, persona, topic):
    sections = section_states(segments)
    opening = " ".join(sections[0]["narration"]) if sections else ""
    closing = " ".join(sections[-1]["narration"]) if len(sections) > 1 else ""
    inner = sections[1:-1]
    share = MIDDLE_CHARS // max(1, len(inner))  # every section gets an equal share, so none is cut out
    middle = {s["section"]: " ".join(s["narration"])[:share] for s in inner}
    get = lambda sec, key: persona.get(sec, {}).get(key, "")  # noqa: E731
    return {"topic": topic, "class": get("Teacher", "Class"), "must_cover": get("Lecture Structure", "Must cover"),
            "avoid": get("Lecture Structure", "Avoid"), "absence_reason": get("Absence Note", "Reason"),
            "message_to_class": get("Absence Note", "Message to class"),
            "teaching_style": {k: get("Teaching Style", k) for k in ("Tone", "Pace", "Language", "Habits")},
            "next_class_topic": get("Next Class", "Topic"), "next_class_prep": get("Next Class", "Prep"),
            "section_titles": [s["section"] for s in sections],
            "opening": opening, "narration": middle, "closing": closing}


def _decide(state, questions):
    """One Jev request. Returns ({id: value 0-1}, cost)."""
    body = {"model": config.JUDGE_MODEL, "state": state, "questions": {k: q[0] for k, q in questions.items()}}
    resp = httpx.post(DECISIONS_URL, json=body, timeout=90,
                      headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"})
    resp.raise_for_status()
    data = resp.json()
    values = {}
    for key, answer in data["answers"].items():
        if answer["type"] == "noul":
            values[key] = answer["noul"]
        else:  # score: position on the scale, 0 = worst level, 1 = best
            values[key] = answer["score"] / max(1, len(questions[key][0]["criteria"]) - 1)
    return values, data.get("usage", {}).get("cost") or 0


def run_jobs(jobs):
    """Jev requests [(section or None, state, questions)], sent in parallel (one per section). Returns the report:
    findings, while-speaking pairs, score, blockers. If Jev can't be reached, report["error"] says so."""
    from concurrent.futures import ThreadPoolExecutor
    report = {"model": config.JUDGE_MODEL, "findings": [], "pairs": [], "cost": 0.0, "error": ""}
    jobs = [(sec, st, qs, st.pop("_flags", {}) if sec else {}) for sec, st, qs in jobs if qs]

    def ask(job):
        try:
            return job, _decide(job[1], job[2]), None
        except Exception as e:
            return job, None, e

    with ThreadPoolExecutor(max_workers=min(8, len(jobs) or 1)) as pool:
        results = list(pool.map(ask, jobs))
    for (section, state, questions, flags), answer, error in results:
        if error is not None:
            report["error"] = f"{type(error).__name__}: {error}"[:300]
            print(f"[judge] Jev could not be reached, skipping the quality check: {report['error']}")
            return report
        values, cost = answer
        report["cost"] += cost
        for key, value in values.items():
            _, weight, severity, fix = questions[key]
            if severity == "pair":  # not a score item: decides whether the pair keeps its flag
                pair = state["spoken_while_writing"][key]
                report["pairs"].append({"section": section, "flag": flags[key], "value": round(value, 2),
                                        "written": pair["written"][:80], "said": pair["said"][:120],
                                        "unflag": value < config.PAIR_UNFLAG})
                continue
            report["findings"].append({"check": key, "section": section, "value": round(value, 2),
                                       "passed": value >= PASS_AT.get(key, config.JUDGE_PASS), "severity": severity,
                                       "weight": weight, "fix": fix.format(section=section)})
    return summarize(report)


def summarize(report):
    total = sum(f["weight"] for f in report["findings"]) or 1
    report["score"] = round(sum(f["weight"] * f["value"] for f in report["findings"]) / total, 2)
    report["blockers"] = len(blockers(report))
    report["failed_minor"] = sum(1 for f in report["findings"] if not f["passed"] and f["severity"] == "minor")
    return report


def judge_script(segments, persona, topic, figs=None, pictures=None):
    """Every applicable question on a whole staged script (used for hand-edited scripts and older callers)."""
    jobs = [(None, script_state(segments, persona, topic), SCRIPT_QUESTIONS)]
    jobs += [(s["section"], s, _section_questions(s)) for s in section_states(segments, figs, pictures)]
    return run_jobs(jobs)


def judge_staging(segments, figs=None, pictures=None):
    """Step 3's check: only how the lesson is staged (highlights, diagrams, graphs, what is said while writing)."""
    states = section_states(segments, figs, pictures)
    keep = {s["section"]: {k: v for k, v in s.items() if k != "_flags"} for s in states}
    report = run_jobs([(s["section"], s, _section_questions(s, STAGING_CHECKS)) for s in states])
    return attach_evidence(report, keep)


GRAPH_ALIGNMENT = _noul(
    "For every move in moves, is everything teacher_says states consistent with graph_reports (what the interactive "
    "graph itself reports it shows after that slider move)? The graph may show more than the teacher mentions, and "
    "other sliders may not have been moved yet; only a direct contradiction counts.",
    "Nothing the teacher says after a slider move contradicts what the graph shows at that point.",
    "At least one sentence states a value or shape that the graph clearly does not show at that point.")


def check_graph_alignment(title, plots, moves):
    """Jev on one built graph: does the narration after each slider move match what the graph reports?
    Returns (P(yes), cost), or (None, 0) if Jev can't be reached (the graph is kept)."""
    try:
        values, cost = _decide({"graph": title, "plots": plots, "moves": moves}, {"aligned": (GRAPH_ALIGNMENT, 1, "blocker", "")})
        return values.get("aligned"), cost
    except Exception as e:
        print(f"[visual] Jev could not check the graph: {type(e).__name__}: {str(e)[:120]}")
        return None, 0


def blockers(report):
    return [f for f in report["findings"] if not f["passed"] and f["severity"] == "blocker"]


def better(a, b):
    """True if report a is better than report b: fewer blockers first, then a higher score."""
    return (a.get("blockers", 99), -a.get("score", 0)) < (b.get("blockers", 99), -b.get("score", 0))


# ---------- how to teach each figure in the material (decided once, at index time) ----------

USE_GRAPH = ("Would letting students drag a slider on figures.{key} (change the value the chart is about and watch it "
             "redraw) teach something the static chart cannot? Yes for a trend over time, a formula, a distribution "
             "or a rate the class can explore; no for a pie chart, a one-off comparison of fixed categories, or a "
             "chart whose point is clear at a glance.")
USE_DIAGRAM = ("Is figures.{key} a process with an order (steps, a loop or a decision) that students understand better "
               "when it is drawn block by block while explained? No for a list of separate facts, dates, causes or "
               "examples.")


def decide_use(figs, topic):
    """Set each chart's and diagram's "use" ("interactive" / "draw" / "show") with one Jev request, from the
    figure itself. Pictures are always shown. Falls back to figures.default_use. Returns the Jev cost."""
    from eris.material.figures import default_use
    todo = {f"fig_{i}": f for i, f in enumerate(figs) if f["kind"] in ("graph", "diagram", "flow")}
    for f in figs:
        f["use"] = default_use(f)
    if not todo or not config.JUDGE_ENABLED:
        return 0
    state = {"topic": topic, "figures": {k: {"kind": f["kind"], "title": f["title"], "details": f["details"][:400]}
                                         for k, f in todo.items()}}
    questions = {k: (_noul((USE_GRAPH if f["kind"] == "graph" else USE_DIAGRAM).format(key=k),
                           "Yes, it should be interactive." if f["kind"] == "graph" else "Yes, draw it block by block.",
                           "No, show it as it is on its slide."), 1, "use", "") for k, f in todo.items()}
    try:
        values, cost = _decide(state, questions)
    except Exception as e:
        print(f"[index] Jev could not decide how to use the figures ({type(e).__name__}); using the default rule")
        return 0
    for k, f in todo.items():
        p = values.get(k)
        if p is None:
            continue
        yes = "interactive" if f["kind"] == "graph" else "draw"
        f["use"], f["use_p"] = (yes if p >= 0.5 else "show"), round(p, 2)
        f["use_why"] = ("students can explore it with a slider" if f["use"] == "interactive" else
                        "it is a process to draw step by step" if f["use"] == "draw" else
                        "its point is clear as it is on the slide")
    return cost


# ---------- doubt answers: the small scripts the doubt agent writes live ----------

ANSWER_QUESTIONS = {
    "answers_question": (_noul(
        "Does answer respond directly to the student's question? Saying it will be passed to the teacher, or that it "
        "belongs to a later class, also counts when that fits the question.",
        "The student's question is answered (or rightly passed on).",
        "The answer talks about something else or leaves the question unanswered."),
        2, "blocker", "Answer exactly what the student asked, directly, in the first sentences."),
    "answer_correct": (_noul(
        "Is everything answer says correct for this subject, and consistent with the notes and code it wrote and "
        "the real_outputs of the programs it ran?",
        "Everything stated is correct and agrees with what was written and what the programs really printed.",
        "Something stated is wrong, or contradicts the notes, the code or what a program really printed."),
        2, "blocker", "Make every statement correct and say exactly what the programs really printed."),
    "fits_class": (_noul(
        "Does the answer use this class's terms and examples (class_so_far) or connect to them, staying within "
        "what this class covers and away from avoid?",
        "It builds on what the class was taught.", "It ignores what was taught or goes into avoided topics."),
        1, "minor", "Build on the examples and notes the class already has, and stay within this lecture."),
    "answer_clear": (_noul(
        "Is the answer clear and simple for this class: short spoken sentences and a concrete example where it helps?",
        "Clear and simple.", "Confusing, too long or too abstract."),
        1, "minor", "Keep it short and simple, with one concrete example."),
    "answer_pictures": (_noul(
        "For each slide picture in pictures_shown, is what the answer says about it consistent with what it shows "
        "and the text in it?",
        "Consistent.", "The answer says something the picture does not show."),
        1, "minor", "Describe the pictures you show as they really are."),
}


def answer_state(question, segments, context, topic, avoid, pictures=None):
    """What Jev sees of one doubt answer: what was said, written, run and shown."""
    on_slide = {}
    for p in pictures or []:
        if p.get("slide") and p.get("description"):
            on_slide.setdefault(p["slide"], []).append(p["description"] + (f" Text in it: {p['text'][:200]}" if p.get("text") else ""))
    state = {"topic": topic, "avoid": avoid, "question": question, "class_so_far": (context or "")[-2500:],
             "answer": " ".join(s["text"] for s in segments if s["kind"] == "say"),
             "notes_written": [s["args"]["text"] for s in segments if s.get("name") in ("NOTE", "NOTE_TITLE", "WRITE")],
             "code_written": [f"{s['args']['file']}:\n{s['args']['code']}" for s in segments if s.get("name") == "WRITE_CODE"],
             "real_outputs": [f"$ {s['args']['cmd']}\n{s.get('expected_output', '')}" for s in segments if s.get("name") == "RUN"],
             "pictures_shown": {f"slide {s['args']['n']}": " | ".join(on_slide[_int(s['args'].get('n'))])
                                for s in segments if s.get("name") == "SLIDE" and on_slide.get(_int(s["args"].get("n")))}}
    return state


def judge_answer(question, segments, context, topic, avoid, pictures=None):
    """Jev on one doubt answer. Returns {findings, blockers, score, fix, cost, error}; never raises."""
    state = answer_state(question, segments, context, topic, avoid, pictures)
    wanted = {"answers_question", "answer_correct", "fits_class", "answer_clear"}
    if state["pictures_shown"]:
        wanted.add("answer_pictures")
    questions = {k: v for k, v in ANSWER_QUESTIONS.items() if k in wanted}
    report = {"findings": [], "cost": 0, "error": ""}
    try:
        values, report["cost"] = _decide(state, questions)
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"[:300]
        return report
    for key, value in values.items():
        _, weight, severity, fix = questions[key]
        report["findings"].append({"check": key, "value": round(value, 2), "passed": value >= config.JUDGE_PASS,
                                   "severity": severity, "weight": weight, "fix": fix})
    total = sum(f["weight"] for f in report["findings"]) or 1
    report["score"] = round(sum(f["weight"] * f["value"] for f in report["findings"]) / total, 2)
    report["blockers"] = len(blockers(report))
    report["fix"] = "\n".join(f"- {f['fix']}" for f in report["findings"] if not f["passed"])
    return report


# ---------- evidence: what the agent is shown with a failed check, so it knows WHERE and WHAT, not only THAT ----------

def _clip(text, n):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _key_words(text):
    import re
    return {w for w in re.findall(r"[a-z]{4,}", text.lower())} - {"with", "from", "that", "this", "when", "what", "into"}


def evidence(finding, state=None, script_state=None):
    """A short, concrete note for a failed check: the facts Jev was given and the part of the text it judged.
    state: the section's state (script_judge.section_states or lesson.content_states); script_state: the whole
    lesson's (for must cover, avoid, opening, closing)."""
    key, st, ss = finding["check"], state or {}, script_state or {}
    said = _clip(" ".join(st.get("narration", [])), 380)
    if key == "covers_must_cover" and ss:
        import re
        items = [x.strip() for x in re.split(r"[;\n]", ss.get("must_cover", "")) if x.strip()]
        taught = " ".join([ss.get("opening", ""), ss.get("closing", "")] + list(ss.get("narration", {}).values())).lower()
        weak = [it for it in items if len(_key_words(it) & _key_words(taught)) < max(1, len(_key_words(it)) // 2)]
        return (f"Must cover: {'; '.join(items)}." + (f" Taught least (check these first): {'; '.join(weak)}." if weak else
                " Each item must be taught (explained, not only named)."))
    if key == "respects_avoid" and ss:
        return f"Avoid: {ss.get('avoid', '')}."
    if key == "opening_absence" and ss:
        return f"Reason: {ss.get('absence_reason', '')}. Message: {ss.get('message_to_class', '')}. Opening now: \"{_clip(ss.get('opening', ''), 250)}\""
    if key == "closing_next_class" and ss:
        return f"Next class: {ss.get('next_class_topic', '')}. Prep: {ss.get('next_class_prep', '')}. Closing now: \"{_clip(ss.get('closing', ''), 250)}\""
    if key == "pictures_explained":
        pics = "; ".join(f"{ref}: {_clip(desc, 230)}" for ref, desc in st.get("pictures_shown", {}).items())
        return f"Pictures in this section (what they really show): {pics}. The section now says: \"{said}\""
    if key in ("notes_match_code", "narration_matches_output"):
        return (f"Notes: {_clip(' | '.join(st.get('notebook', [])), 300)}. Real output: "
                f"{_clip(' | '.join(st.get('real_outputs', [])), 300)}. The section now says: \"{_clip(said, 250)}\"")
    if key == "highlights_fit":
        return "Highlights now: " + "; ".join(f"{h['marker']} lights up \"{_clip(h['points_at'], 70)}\" then says \"{_clip(h['said_next'], 90)}\""
                                              for h in st.get("highlights", [])[:8])
    if key == "graph_matches_text":
        moves = [f"{g['title']}: {m['control']}={m['value']} then says \"{_clip(m['teacher_says'], 90)}\""
                 for g in st.get("graphs", {}).values() for m in g.get("slider_moves", [])]
        return "Slider moves now: " + "; ".join(moves[:8])
    if key == "graph_matches_material":
        return "; ".join(f"{g['title']} plots \"{_clip(g['plots'], 120)}\", the material's chart: {_clip(g['material_graph'], 160)}"
                         for g in st.get("graphs", {}).values())
    if key == "flow_matches_material":
        return "; ".join(f"{f['title']} blocks: {' -> '.join(f['blocks'])}; the material's steps: {_clip(f['material_steps'], 200)}"
                         for f in st.get("flows", {}).values())
    if said:
        return f"The section now says: \"{said}\""
    return ""


def attach_evidence(report, states, script_state=None):
    """Add evidence to every failed finding. states: {section title: state}."""
    for f in report.get("findings", []):
        if not f["passed"]:
            f["evidence"] = evidence(f, states.get(f["section"]) if f["section"] else None, script_state)
    return report
