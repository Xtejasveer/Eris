"""When a classroom action fails, get one short line to say and move on.

The LLM handles exceptions only; it never moves the lecture forward.
"""

from langchain.chat_models import init_chat_model

import config
from prompts import recovery_prompt

FALLBACK = "Looks like the board had a small hiccup. Let's keep going."

_model = None


def recovery_line(teacher_name, state_text, segment, error):
    """Return a sentence to say. Never raises: falls back to a fixed line."""
    global _model
    expected = segment.get("expected_output", "").strip()
    action = f"[{segment.get('name')}] {segment.get('args', {})}"
    if expected:
        action += f"\nApproved output: {expected[:300]}"
    try:
        if _model is None:
            _model = init_chat_model(f"openrouter:{config.LLM_MODEL}", temperature=0.3,
                                     request_timeout=20, max_retries=1)
        reply = _model.invoke(recovery_prompt(teacher_name, state_text, action, error))
        text = reply.content if isinstance(reply.content, str) else ""
        return text.strip() or FALLBACK
    except Exception as e:
        print(f"[recovery] model unavailable ({e}); using the fallback line")
        return FALLBACK
