"""Judge a generated script with Jev: yes/no questions answered as probabilities. No text is generated.

Code already checks everything that can be checked exactly (format, quotes, limits). Jev checks meaning:
do the notes match the code, is "Must cover" taught, does it sound like the teacher, and so on.
Each question has a weight, a severity and a ready-made fix; quality_loop.py sends the failed ones back
to the script writer. Never raises: if Jev can't be reached, the report says so and generation goes on.
"""

import httpx

import config

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
        1, "blocker", 'In section "{section}", the narration must contain only spoken sentences; put notes in [NOTE] and markers on their own lines.'),
    "graph_matches_text": (_noul(
        "Does each graph in graphs fit what this section teaches: what it plots agrees with the narration, notebook "
        "and code, and after each slider move in slider_moves, does teacher_says describe correctly what the graph "
        "shows at that value?",
        "Every graph agrees with the lesson, and every sentence after a slider move matches what the graph shows.",
        "A graph plots something the lesson doesn't teach, or a sentence after a slider move describes something "
        "the graph does not show at that value."),
        2, "blocker", 'In section "{section}", make each graph and what you say after each slider move agree: say what '
                      "the graph really shows at that value, consistent with the notes and code."),
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


PAIR_QUESTION = ("In spoken_while_writing, is {pair}'s 'said' sentence about {pair}'s 'written' text, so it fits "
                 "to say it while that text is being written on screen?")


def _said_after(segments, i):
    """The first two sentences spoken after segment i (what the teacher says about a slider move)."""
    import re
    if i + 1 < len(segments) and segments[i + 1].get("name") == "VISUAL_SET":
        return "(another move follows straight away)"
    said = next((s["text"] for s in segments[i + 1:i + 4] if s["kind"] == "say"), "")
    return " ".join(re.split(r"(?<=[.!?])\s+", said)[:2])


def section_states(segments, figs=None):
    """One state per [SECTION]: its narration, notebook, code, real outputs, graphs and while-speaking pairs.
    Pairs are keyed pair_0, pair_1, ... and remember their position among all flagged markers (flag).
    figs: the material's graphs (figures.py), so each graph can be compared with the one it recreates."""
    from figures import matches
    states, cur, flag = [], None, -1
    graphs = {}  # visual id -> its entry in the section that made it
    for i, seg in enumerate(segments):
        name, args = seg.get("name"), seg.get("args", {})
        flag += 1 if args.get("while_speaking") else 0  # counted everywhere, so it matches remove_flags
        if name == "SECTION":
            cur = {"section": args["title"], "narration": [], "notebook": [], "code": [],
                   "real_outputs": [], "graphs": {}, "flows": {}, "spoken_while_writing": {}, "_flags": {}}
            states.append(cur)
            continue
        if cur is None:
            continue
        if seg["kind"] == "say":
            cur["narration"].append(seg["text"])
        elif name in ("NOTE", "NOTE_TITLE", "WRITE"):
            cur["notebook"].append(args["text"])
        elif name == "WRITE_CODE":
            cur["code"].append(f"{args['file']}:\n{args['code']}")
        elif name == "RUN":
            cur["real_outputs"].append(f"$ {args['cmd']}\n{seg.get('expected_output', '')}")
        elif name == "FLOW":
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
        if args.get("while_speaking") and i + 1 < len(segments) and segments[i + 1]["kind"] == "say":
            key = f"pair_{len(cur['spoken_while_writing'])}"
            cur["spoken_while_writing"][key] = {"written": args.get("code") or args.get("text") or (
                                                    f"interactive graph: {args['title']}" if name == "VISUAL" else
                                                    f"diagram block: {args.get('label', '')}" if name == "FLOW_NEXT" else ""),
                                                "said": segments[i + 1]["text"]}
            cur["_flags"][key] = flag
    return states


def _section_questions(state):
    """Only ask what applies: no output questions without a RUN, no example question without code."""
    wanted = {"narration_is_speech"}
    if state["code"] and state["notebook"]:
        wanted.add("notes_match_code")
    if state["real_outputs"]:
        wanted.add("narration_matches_output")
    if state["code"]:  # Opening / Closing notes are messages and recaps, not lessons
        wanted.add("has_worked_example")
    if any(f["material_steps"] for f in state["flows"].values()):
        wanted.add("flow_matches_material")
    if state["graphs"]:
        wanted.add("graph_matches_text")
        if any(g["material_graph"] for g in state["graphs"].values()):
            wanted.add("graph_matches_material")
    questions = {k: v for k, v in SECTION_QUESTIONS.items() if k in wanted}
    for key in state["spoken_while_writing"]:  # one question per while_speaking pair
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


def judge_script(segments, persona, topic, figs=None):
    """Ask every applicable question. Returns the report (see blockers() and fix_message())."""
    report = {"model": config.JUDGE_MODEL, "findings": [], "cost": 0.0, "error": ""}
    jobs = [(None, script_state(segments, persona, topic), SCRIPT_QUESTIONS)]
    report["pairs"] = []
    jobs += [(s["section"], s, _section_questions(s)) for s in section_states(segments, figs)]
    for section, state, questions in jobs:
        flags = state.pop("_flags", {}) if section else {}
        try:
            values, cost = _decide(state, questions)
        except Exception as e:
            report["error"] = f"{type(e).__name__}: {e}"[:300]
            print(f"[judge] Jev could not be reached, skipping the quality check: {report['error']}")
            return report
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
                                       "passed": value >= config.JUDGE_PASS, "severity": severity,
                                       "weight": weight, "fix": fix.format(section=section)})
    total = sum(f["weight"] for f in report["findings"]) or 1
    report["score"] = round(sum(f["weight"] * f["value"] for f in report["findings"]) / total, 2)
    report["blockers"] = len(blockers(report))
    report["failed_minor"] = sum(1 for f in report["findings"] if not f["passed"] and f["severity"] == "minor")
    return report


GRAPH_ALIGNMENT = _noul(
    "For every move in moves, does teacher_says agree with graph_reports, which is what the interactive graph itself "
    "reports it shows after that slider move?",
    "Every sentence the teacher says after a slider move agrees with what the graph shows at that value.",
    "At least one sentence describes something the graph does not show at that value (different numbers or shape).")


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
