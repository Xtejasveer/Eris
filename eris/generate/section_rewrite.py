"""Rewrite one section of an approved script from what students said about it (their "confusing" flags and the
doubts they asked there). The result is a draft: the teacher reads it in Studio and approves it, which gives the class
a new version. Everything outside the section stays exactly as it was."""

from langchain_core.messages import HumanMessage, SystemMessage

from eris import config
from eris.generate.script_parser import parse_script
from eris.generate.staging import script_sections, splice_script
from eris.prompts import staging_prompt

REWRITE_SECTION = """Students found this section of the class script hard to follow. Here is what they said, and the
doubts they asked while it played:

{feedback}

The section as it stands:

{current}

Rewrite it so these students would follow it: smaller steps, a concrete example or a worked case, and a short check-in
question where it helps. Keep the facts, the slides, notes, code and diagrams it uses (you may add a short note or
example), and keep its length within about a third of what it is now. Use the same markers, each alone on its line.
Return ONLY this section, starting with its [SECTION title=".."] line exactly as it is now. Do not return any other
section."""
FIX_ERRORS = """The section you returned breaks the script:

{errors}

Return the section again (only it, starting with the same [SECTION] line) with these fixed."""


def _text(reply):
    content = reply.content if isinstance(reply.content, str) else "".join(
        b.get("text", "") if isinstance(b, dict) else str(b) for b in reply.content)
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else ""
        content = content.rsplit("```", 1)[0]
    return content.strip()


def rewrite_section(lecture_id, title, feedback):
    """The whole script.md text with section `title` rewritten. Raises ValueError with a message for the teacher."""
    from langchain.chat_models import init_chat_model
    from eris.generate.script_writer import count_slides
    script_md = config.lecture_dir(lecture_id) / "script.md"
    if not script_md.exists():
        raise ValueError("This lesson has no script yet")
    text = script_md.read_text(encoding="utf-8")
    current = next((block for t, block in script_sections(text) if t and t.strip().lower() == title.strip().lower()), None)
    if current is None:
        raise ValueError(f"The current script has no section called \"{title}\" (it may have been renamed in a newer version)")
    manifest = config.load_manifest(lecture_id)
    model = init_chat_model(f"openrouter:{config.LLM_MODEL}")
    messages = [SystemMessage(staging_prompt(manifest["persona"], manifest.get("topic", ""), config.lecture_language(manifest))),
                HumanMessage(REWRITE_SECTION.format(feedback=feedback.strip() or "(no comments: they marked it as confusing)",
                                                    current=current))]
    slides = count_slides(lecture_id)
    for attempt in (1, 2):
        try:
            reply = model.invoke(messages)
        except Exception as e:
            raise ValueError(f"The model call failed: {str(e)[:200]}")
        part = _text(reply)
        if not part.lstrip().startswith("[SECTION"):
            part = current.splitlines()[0] + "\n" + part  # it left out the title line
        new_text = splice_script(text, part)
        _, errors = parse_script(new_text, slides)
        if not errors:
            return new_text
        if attempt == 2:
            raise ValueError("The rewritten section had problems: " + "; ".join(errors[:3]))
        messages += [reply, HumanMessage(FIX_ERRORS.format(errors="\n".join(f"- {e}" for e in errors[:8])))]
