"""The code side of `generate`: check each draft, send problems back to the writer, finish the script.

For every draft the writer returns:
  cosmetic cleanup (stars, # headings, bullet dashes) -> checks -> problems? -> the SAME writer fixes them
After FIX_ATTEMPTS rounds, anything still broken is repaired by code as a last resort, and every such
repair is recorded (auto_fixes) so the teacher sees it in Studio. A valid script then gets its
while_speaking flags and the real output of every program.
"""

import copy

from eris import config
from eris.generate.format_fixes import fix_format, strip_typed_output
from eris.generate.script_checks import clean_cosmetic, format_problems, teaching_problems
from eris.generate.script_fixes import (add_doubt_checks, add_sync_flags, drop_bad_staging, drop_bad_visuals,
                          complete_flows, drop_markers, drop_visual, fix_flow_order, move_doubt_checks_to_section_end,
                          drop_empty_circles, show_picture_slides, tidy_staging,
                          trim_doubt_checks)
from eris.generate.script_parser import parse_script

RULES_FEEDBACK = ("Your script breaks these rules. Fix every one of them, keep everything else the same, "
                  "and return the full corrected script only:\n")
ADVICE_FEEDBACK = "\nAlso improve these (the lesson must sound and look like a real teacher):\n"


class ScriptPipeline:
    def __init__(self, writer, budget, slides, notes="", figures=None, env=None, pictures=None):
        self.writer, self.budget, self.slides, self.notes = writer, budget, slides, notes
        self.figures = figures or []  # graphs and diagrams in the material (figures.py)
        self.pictures = pictures or []  # the material's pictures and what each shows (images.py)
        self.env = env or {}          # environments this class may use (notebook, slides, code, graphs)
        self.rounds = []      # every feedback round: {"kind": "rules" | "quality", "problems": n}
        self.auto_fixes = []  # repairs code made to the latest version because the writer did not
        self.advice = []      # soft problems in the latest version: sent as feedback, never fail a script

    def rewrite(self, problems):
        """A fresh writer (same prompt and research notes) writes the script again, avoiding these problems.
        A new conversation, because a writer asked to revise its own script mostly copies it."""
        self.writer = type(self.writer)(self.writer.messages[0].content)
        return self.writer.write(self.notes, self.budget, avoid=problems)

    def _with_outputs(self, segments):
        """A copy of the segments with the real output of every RUN filled in (runs the code)."""
        from eris.generate.script_writer import fill_expected_outputs  # script_writer imports this module

        copied = copy.deepcopy(segments)
        fill_expected_outputs(copied)
        return copied

    def real_outputs(self, segments):
        """What every program in the script really prints (run in a terminal), so a rewrite describes exactly that."""
        runs = [s for s in self._with_outputs(segments) if s.get("name") == "RUN"]
        if not runs:
            return ""
        shown = "\n".join(f'{s["args"]["cmd"]} prints:\n{(s.get("expected_output") or "(no output)").rstrip()[:600]}'
                          for s in runs)
        return ("\n\n# What each program really prints (from a real terminal). After its [READ_OUTPUT], describe "
                "exactly this; if you change a program, its output changes too.\n" + shown)

    def check(self, text):
        """Cosmetic cleanup, then every check. Returns (text, segments, problems)."""
        from eris.generate.script_writer import check_generated

        text, cleaned = clean_cosmetic(text)
        if cleaned:
            print(f"[generate] cleanup: removed markdown symbols from {cleaned} line(s)")
        segments, problems = check_generated(text, self.budget, self.slides, self.figures, self.env)
        outputs = [s.get("expected_output", "") for s in self._with_outputs(segments) if s.get("name") == "RUN"]
        problems += format_problems(text, outputs)
        self.advice = teaching_problems(segments, self.figures, self.slides if self.env.get("slides", True) else None,
                                        self.env)
        return text, segments, problems

    def until_valid(self, text):
        """Check; send the problems to the writer up to FIX_ATTEMPTS times; then repair by code as a last resort."""
        self.auto_fixes = []
        text, segments, problems = self.check(text)
        for attempt in range(1, config.FIX_ATTEMPTS + 1):
            if not problems:  # advice alone never costs a rewrite: it rides along with real problems only
                return text, segments, problems
            print(f"[generate] {len(problems)} problem(s) and {len(self.advice)} piece(s) of advice; sending them "
                  f"to the writer (round {attempt}/{config.FIX_ATTEMPTS})")
            for p in problems + self.advice:
                print(f"[generate]   {p.splitlines()[0]}")
            self.rounds.append({"kind": "rules", "problems": len(problems) + len(self.advice)})
            text, segments, problems = self.check(self.ask_fix(text, segments, problems))
        if problems:
            text, segments, problems = self.last_resort(text)
        return text, segments, problems

    def ask_fix(self, text, segments, problems):
        """Send the problems (and advice) to the writer; returns its new full text."""
        message = RULES_FEEDBACK + "\n".join(problems)
        if self.advice:
            message += ADVICE_FEEDBACK + "\n".join(self.advice)
        message += self.real_outputs(segments)
        return self.writer.ask(message)

    def last_resort(self, text):
        """The writer did not fix these: code repairs what it can, and records each repair."""
        print("[generate] the writer did not fix everything; repairing the rest in code")
        text, fixed = fix_format(text)
        from eris.material.figures import ENV_MARKERS
        for name in ("code", "graphs", "slides"):  # markers of an environment this class doesn't have
            if self.env and not self.env.get(name):
                text, n = drop_markers(text, ENV_MARKERS[name])
                fixed += [f"removed {n} {name} marker(s): this class's material has no {name}"] if n else []
        text, trimmed = trim_doubt_checks(text, config.MAX_DOUBT_CHECKS)
        fixed += [f"removed {trimmed} extra question break(s)"] if trimmed else []
        text, reordered = fix_flow_order(text)
        fixed += [f"moved {reordered} diagram block(s) so each appears as its sentence is said"] if reordered else []
        text, completed = complete_flows(text)
        fixed += [f"drew {completed} diagram block(s) the script left out"] if completed else []
        text, moved = move_doubt_checks_to_section_end(text)
        fixed += [f"moved {moved} question break(s) to the end of their section"] if moved else []
        text, added = add_doubt_checks(text, config.MAX_DOUBT_CHECKS)
        fixed += [f"added {added} missing question break(s)"] if added else []
        segments, _ = parse_script(text, self.slides)
        text, removed = strip_typed_output(text, self._with_outputs(segments))
        fixed += [f"removed {removed} line(s) of typed program output"] if removed else []
        text, segments, problems = self.check(text)
        text, broken = drop_bad_visuals(text, problems)
        fixed += [f"removed a diagram or graph that could not be read: {d}" for d in broken]
        from eris.generate.script_writer import flow_source_errors, visual_source_errors  # script_writer imports this module
        segments_now = parse_script(text, self.slides)[0]
        for vid, _ in visual_source_errors(segments_now, self.figures):
            text = drop_visual(text, vid)
            fixed.append(f"removed the visual '{vid}': the material has no matching graph")
            broken.append(vid)
        for fid, _ in flow_source_errors(segments_now, self.figures):
            text = drop_visual(text, fid, block="FLOW")
            fixed.append(f"removed the diagram '{fid}': the material has no matching diagram or list of steps")
            broken.append(fid)
        if broken:
            text, segments, problems = self.check(text)
        text, dropped = drop_bad_staging(text, problems)
        fixed += [f"dropped a marker that could not work: {d}" for d in dropped]
        if dropped:
            text, segments, problems = self.check(text)
        fixed = list(dict.fromkeys(fixed))
        for f in fixed:
            print(f"[generate] auto-fixed: {f}")
        self.auto_fixes += fixed
        return text, segments, problems

    def finalize(self, text):
        """Add Level 2 sync flags and record the real output of every RUN. Returns (text, segments)."""
        if self.env.get("slides", True):  # the class sees a picture while the teacher talks about it
            text, shown = show_picture_slides(text, self.pictures, self.slides, self.figures)
            if shown:
                print(f"[generate] auto-fixed: showed the slide with the picture being explained {shown} time(s)")
                self.auto_fixes.append(f"showed a picture's slide while it is explained ({shown} time(s))")
        # Write first, then explain: no leads are added; notes and programs simply appear before their sentences.
        text, empty = drop_empty_circles(text, self.pictures)
        if empty:
            self.auto_fixes.append(f"removed {empty} pen circle(s) on slides that have no picture")
        text, tidied = tidy_staging(text, getattr(self, "lesson_sentences", ()))
        if tidied:
            print(f"[generate] auto-fixed: removed {tidied} repeated slide(s), highlight(s) or circle(s)")
            self.auto_fixes.append(f"removed {tidied} repeated slide(s), highlight(s) or circle(s)")
        text, flagged = add_sync_flags(text)
        segments, _ = parse_script(text, self.slides)
        print(f"[generate] {flagged} highlight(s), circle(s) and slider move(s) happen as their sentence starts")
        return text, self._with_outputs(segments)
