"""Measure how fast the class voice really speaks, so speaking time turns into the right number of words.

`python main.py measure-voice` speaks a few ordinary teaching lines with the configured Gnani voice (the same
speed, language and pauses as a real class), times the audio, adds the short breath the class player takes after
each line, and saves the result as SPEAKING_WPM in .env. The script writer's word budget is then
speaking minutes x SPEAKING_WPM.
"""

import re
import shutil
import wave
from pathlib import Path

from eris import config

# Ordinary teaching lines (topic-neutral), spoken one by one like the class's narration lines.
SAMPLE = [
    "Let's start with a question. Imagine you have a shopping bill with three prices. How would you add them up?",
    "You start at zero, and you add each price in turn. That running total is the whole idea for today.",
    "So the first price is ten, and our total becomes ten. Then we add twenty-five, and the total is thirty-five.",
    "Now we add the last price, four. What do you think the total is? Take a second. Yes, it is thirty-nine.",
    "Why does this work? Because every price is added exactly once, in order, and nothing is skipped. Make sense so far?",
    "Here is the takeaway: a running total grows one item at a time, and the last value is the answer.",
]
PLAYER_BREATH_S = 0.5  # the class player's short pause after each spoken line (BREATH_MS in web/js/player.js)
CHECK_ID = "voice_speed_check"


def measure():
    """Speak the sample, time it, and return words per minute as the class will hear them."""
    from eris.classroom import voice
    words = seconds = 0
    try:
        for line in SAMPLE:
            path = voice.ensure_clip(CHECK_ID, line)
            with wave.open(str(path)) as w:
                seconds += w.getnframes() / w.getframerate()
            words += len(line.split())
            seconds += PLAYER_BREATH_S
    finally:
        shutil.rmtree(config.lecture_dir(CHECK_ID), ignore_errors=True)  # only a measurement: keep no clips
    return round(words / seconds * 60), words, round(seconds, 1)


def save_wpm(wpm, env_path=".env"):
    """Write SPEAKING_WPM into .env (replacing the old value, or adding it)."""
    path = Path(env_path)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    line = f"SPEAKING_WPM={wpm}"
    text = re.sub(r"(?m)^SPEAKING_WPM=.*$", line, text) if re.search(r"(?m)^SPEAKING_WPM=", text) else text.rstrip("\n") + f"\n{line}\n"
    path.write_text(text, encoding="utf-8")


def run():
    if not config.GNANI_API_KEY:
        print("[voice] GNANI_API_KEY is not set: the class uses the browser voice, so there is nothing to measure.")
        return
    wpm, words, seconds = measure()
    print(f"[voice] {config.TTS_VOICE} at speed {config.TTS_SPEED}: {words} words in {seconds} s "
          f"(with the class's pauses) = {wpm} words per minute")
    save_wpm(wpm)
    print(f"[voice] saved SPEAKING_WPM={wpm} in .env (was {config.SPEAKING_WPM}). A 5-minute speaking time is now "
          f"about {5 * wpm} words for the writer.")
