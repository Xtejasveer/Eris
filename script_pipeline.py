"""The code side of `generate`: check each draft, send problems back to the writer, finish the script.

For every draft the writer returns:
  cosmetic cleanup (stars, # headings, bullet dashes) -> checks -> problems? -> the SAME writer fixes them
After FIX_ATTEMPTS rounds, anything still broken is repaired by code as a last resort, and every such
repair is recorded (auto_fixes) so the teacher sees it in Studio. A valid script then gets its
while_speaking flags and the real output of every program.
"""

import copy

import config
from format_fixes import fix_format, strip_typed_output
from script_checks import clean_cosmetic, format_problems, narration_problems, teaching_problems
from script_fixes import add_sync_flags, announce_writing, drop_bad_staging, drop_bad_visuals, trim_doubt_checks
from script_parser import parse_script

RULES_FEEDBACK = ("Your script breaks these rules. Fix every one of them, keep everything else the same, "
                  "and return the full corrected script only:\n")
ADVICE_FEEDBACK = "\nAlso improve these (the lesson must sound and look like a real teacher):\n"


class ScriptPipeline:
    def __init__(self, writer, budget, slides, notes=""):
        self.writer, self.budget, self.slides, self.notes = writer, budget, slides, notes
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
        from script_writer import fill_expected_outputs  # script_writer imports this module

        copied = copy.deepcopy(segments)
        fill_expected_outputs(copied)
        return copied

    def check(self, text):
        """Cosmetic cleanup, then every check. Returns (text, segments, problems)."""
        from script_writer import check_generated

        text, cleaned = clean_cosmetic(text)
        if cleaned:
            print(f"[generate] cleanup: removed markdown symbols from {cleaned} line(s)")
        segments, problems = check_generated(text, self.budget, self.slides)
        outputs = [s.get("expected_output", "") for s in self._with_outputs(segments) if s.get("name") == "RUN"]
        problems += format_problems(text, outputs)
        flagged, _ = add_sync_flags(text)  # the pairs the class will see: written while this sentence plays
        self.advice = teaching_problems(segments) + narration_problems(parse_script(flagged, self.slides)[0])
        return text, segments, problems

    def until_valid(self, text):
        """Check; send the problems to the writer up to FIX_ATTEMPTS times; then repair by code as a last resort."""
        self.auto_fixes = []
        text, segments, problems = self.check(text)
        for attempt in range(1, config.FIX_ATTEMPTS + 1):
            if not problems and not self.advice:
                return text, segments, problems
            print(f"[generate] {len(problems)} problem(s) and {len(self.advice)} piece(s) of advice; sending them "
                  f"to the writer (round {attempt}/{config.FIX_ATTEMPTS})")
            for p in problems + self.advice:
                print(f"[generate]   {p.splitlines()[0]}")
            self.rounds.append({"kind": "rules", "problems": len(problems) + len(self.advice)})
            message = RULES_FEEDBACK + "\n".join(problems) if problems else "Your script is valid. Return the full script with these improvements:\n"
            if self.advice:
                message += (ADVICE_FEEDBACK if problems else "") + "\n".join(self.advice)
            text, segments, problems = self.check(self.writer.ask(message))
        if problems:
            text, segments, problems = self.last_resort(text)
        return text, segments, problems

    def last_resort(self, text):
        """The writer did not fix these: code repairs what it can, and records each repair."""
        print("[generate] the writer did not fix everything; repairing the rest in code")
        text, fixed = fix_format(text)
        text, trimmed = trim_doubt_checks(text, config.MAX_DOUBT_CHECKS)
        fixed += [f"removed {trimmed} extra question break(s)"] if trimmed else []
        segments, _ = parse_script(text, self.slides)
        text, removed = strip_typed_output(text, self._with_outputs(segments))
        fixed += [f"removed {removed} line(s) of typed program output"] if removed else []
        text, segments, problems = self.check(text)
        text, broken = drop_bad_visuals(text, problems)
        fixed += [f"removed a visual that could not be read: {d}" for d in broken]
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
        text, leads = announce_writing(text)  # last resort: the writer had its feedback rounds
        if leads:
            print(f"[generate] auto-fixed: added a 'Let me write...' lead before {leads} note(s)/program(s)")
            self.auto_fixes.append(f"added a short 'Let me write...' sentence before {leads} note(s)/program(s)")
        text, flagged = add_sync_flags(text)
        segments, _ = parse_script(text, self.slides)
        print(f"[generate] {flagged} note/code block(s) will be written while the teacher speaks")
        return text, self._with_outputs(segments)
