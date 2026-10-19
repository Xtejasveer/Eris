"""Word timings for a narration clip, so the 3D teacher's lips follow the words and not just the loudness.

Gnani gives no timestamps, so we measure them: faster-whisper (MIT, runs on the CPU in well under a second per
clip) finds when each word is said, and the words are matched back to the script text we already know. Whisper's
word edges are loose (a word often swallows the pause after it), so every word is then tightened to the audio
that is actually voiced. Without faster-whisper, or when its words don't match the script, an energy aligner
spreads the script's words over the voiced parts of the clip instead.

Result (cached next to the clip as <clip>.timing.json):
    {"words": [...], "times": [ms], "durations": [ms], "levels": [0-1], "source": "whisper" | "energy"}
levels: each word's loudness relative to the clip's loud speech, so stressed words open the mouth wider.
"""

import difflib
import json
import os
import re
import threading
import wave

import numpy as np

VERSION = 2           # bump to recompute every cached timing file
RATE = 16000          # whisper's sample rate
HOP = 160             # 10 ms analysis frames
MIN_WORD_S = 0.06     # a word never shrinks below this when tightened to the voiced audio
GAP_S = 0.12          # silence at least this long separates voiced runs (energy aligner)
MATCH_MIN = 0.6       # below this share of matched script words, whisper's result is not trusted

WHISPER_MODEL = os.getenv("LIP_WHISPER_MODEL", "base.en").strip()

_model = None
_model_failed = False
_model_lock = threading.Lock()


def timing_path(clip):
    return clip.with_suffix(".timing.json")


def ensure_timing(clip, text):
    """Timings for `clip` (a WAV saying `text`), computed once and cached."""
    path = timing_path(clip)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("version") == VERSION:
                return data
        except (OSError, ValueError):
            pass
    data = word_timings(clip, text)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)
    return data


def word_timings(clip, text):
    audio = _load_16k(clip)
    words = script_words(text)
    voiced = _voiced_frames(audio)
    timed = None
    if words and voiced.any():
        heard = _whisper_words(audio)
        if heard:
            timed = _match(words, heard)
    source = "whisper"
    if timed is None:
        timed, source = _energy_align(words, voiced), "energy"
    timed = [_tighten(start, end, voiced) for start, end in timed]
    return {
        "version": VERSION, "source": source, "words": words,
        "times": [round(s * 1000) for s, _ in timed],
        "durations": [round((e - s) * 1000) for s, e in timed],
        "levels": _levels(audio, timed),
    }


def script_words(text):
    """The words as spoken (code already turned into words by voice.speech_text)."""
    from eris.classroom.voice import speech_text
    return [w for w in speech_text(text).split() if re.search(r"[\w']", w)]


# ---------- audio ----------

def _load_16k(path):
    with wave.open(str(path), "rb") as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(2**31 - 1)
    if width != 2:
        raise ValueError(f"{path}: expected 16-bit PCM")
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    if channels > 1:
        audio = audio[: len(audio) // channels * channels].reshape(-1, channels).mean(axis=1)
    if rate != RATE and len(audio):
        n = int(len(audio) * RATE / rate)
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
    return audio


def _frame_db(audio):
    n = len(audio) // HOP
    frames = audio[: n * HOP].reshape(n, HOP)
    return 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)


def _levels(audio, timed):
    """Per word: 0 (quiet, 20 dB under the loud speech) to 1 (as loud as the loudest speech), 2 decimals."""
    db = _frame_db(audio)
    if not len(db):
        return [0.5] * len(timed)
    top = np.percentile(db, 95)
    out = []
    for start, end in timed:
        part = db[int(start * 100):max(int(start * 100) + 1, int(np.ceil(end * 100)))]
        peak = np.percentile(part, 80) if len(part) else top - 20
        out.append(round(float(np.clip((peak - (top - 20)) / 20, 0, 1)), 2))
    return out


def _voiced_frames(audio):
    """One bool per 10 ms frame: is there speech? Gate relative to the clip's own loud frames."""
    n = len(audio) // HOP
    if n == 0:
        return np.zeros(0, dtype=bool)
    db = _frame_db(audio)
    gate = max(-55.0, np.percentile(db, 95) - 35)
    voiced = db > gate
    # Close 1-2 frame holes (stop consonants) and drop 1-frame blips.
    for i in range(1, n - 1):
        if not voiced[i] and voiced[i - 1] and voiced[i + 1]:
            voiced[i] = True
    for i in range(1, n - 1):
        if voiced[i] and not voiced[i - 1] and not voiced[i + 1]:
            voiced[i] = False
    return voiced


def _tighten(start, end, voiced):
    """Shrink [start, end] (seconds) to its voiced frames, keeping at least MIN_WORD_S."""
    a, b = int(start * 100), int(np.ceil(end * 100))
    inside = np.flatnonzero(voiced[a:b]) if b > a else []
    if len(inside):
        s, e = (a + inside[0]) / 100, (a + inside[-1] + 1) / 100
        if e - s >= MIN_WORD_S:
            return s, e
        mid = (s + e) / 2
        return max(start, mid - MIN_WORD_S / 2), min(max(end, start + MIN_WORD_S), mid + MIN_WORD_S / 2)
    return start, max(end, start + MIN_WORD_S)


# ---------- whisper ----------

def _whisper():
    global _model, _model_failed
    with _model_lock:
        if _model is None and not _model_failed:
            try:
                from faster_whisper import WhisperModel
                _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
            except Exception as e:  # not installed, or the model can't be downloaded: energy aligner only
                print(f"[lips] faster-whisper unavailable, using the energy aligner: {e}")
                _model_failed = True
        return _model


def _whisper_words(audio):
    model = _whisper()
    if model is None:
        return []
    with _model_lock:  # one transcription at a time: the server calls us from several threads
        segments, _ = model.transcribe(audio, language="en", word_timestamps=True, beam_size=1,
                                       condition_on_previous_text=False)
        return [(w.word.strip(), w.start, w.end) for s in segments for w in s.words]


def _norm(word):
    return re.sub(r"[^a-z0-9]", "", word.lower())


def _spread(words, lo, hi):
    """Share [lo, hi] between words in proportion to their length."""
    weights = [max(1, len(_norm(w))) for w in words]
    total, t, out = sum(weights), lo, []
    for wgt in weights:
        step = (hi - lo) * wgt / total
        out.append((t, t + step))
        t += step
    return out


def _match(words, heard):
    """Give each script word the time of the whisper word it matches. Where the two differ ("Dr." heard as
    "Doctor", "1769" as "seventeen sixty-nine") the script words share the time of the words heard there; script
    words nobody heard share the gap between their neighbours. None if too little matched."""
    a, b = [_norm(w) for w in words], [_norm(w) for w, _, _ in heard]
    times = [None] * len(words)
    matched = 0
    unheard = []  # (i1, i2) runs of script words with no whisper words opposite them
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = heard[j1 + k][1:]
            matched += i2 - i1
        elif op == "replace":
            times[i1:i2] = _spread(words[i1:i2], heard[j1][1], heard[j2 - 1][2])
        elif op == "delete":
            unheard.append((i1, i2))
    if matched < MATCH_MIN * len(words):
        return None
    for i1, i2 in unheard:
        lo = times[i1 - 1][1] if i1 > 0 else 0.0
        hi = times[i2][0] if i2 < len(words) else heard[-1][2]
        times[i1:i2] = _spread(words[i1:i2], min(lo, hi), hi)
    return times


# ---------- energy aligner (fallback) ----------

def _energy_align(words, voiced):
    """Lay the words end to end over the voiced frames only, each taking time in proportion to its length,
    so pauses in the audio stay pauses. Rough, but the mouth still moves with real speech."""
    if not words:
        return []
    frames = np.flatnonzero(voiced)
    if not len(frames):
        n = max(1, len(voiced))
        frames = np.arange(n)
    weights = np.array([max(1, len(_norm(w))) + 1 for w in words], dtype=float)  # +1: every word has an onset
    edges = np.concatenate([[0], np.cumsum(weights) / weights.sum() * len(frames)])
    out = []
    for k in range(len(words)):
        first = frames[min(int(edges[k]), len(frames) - 1)]
        last = frames[max(min(int(np.ceil(edges[k + 1])) - 1, len(frames) - 1), 0)]
        out.append((first / 100, (max(last, first) + 1) / 100))
    return out
