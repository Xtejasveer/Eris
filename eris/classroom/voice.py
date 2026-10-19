"""Voice in and out with Gnani: Timbre v2.5 TTS for narration, Prisma STT for doubts.

Narration clips are pre-rendered and cached by text, so the class never waits on TTS
and every clip's real duration is known before the lecture starts.
"""

import hashlib
import os
import re
import threading
import time
import wave

import numpy as np
import sounddevice as sd
from gnani.stt import GnaniSTTClient
from gnani.tts import GnaniTTSClient

from eris import config
TTS_MODEL = "timbre-v2.5"  # Must be explicit: the SDK default (timbre-v2.0) is no longer served.
MIC_RATE = 16000

_tts = None
_stt = None
# Gnani allows one active request per key, and the web server calls us from several threads.
_tts_lock = threading.Lock()


def _tts_client():
    global _tts
    if _tts is None:
        _tts = GnaniTTSClient(api_key=config.GNANI_API_KEY)
    return _tts


def _stt_client():
    global _stt
    if _stt is None:
        _stt = GnaniSTTClient(api_key=config.GNANI_API_KEY)
    return _stt


# How code inside narration is said, longest symbols first. Gnani reads "+" and "÷" itself, but
# "<=", "==" or "my_var" come out as noise, so code spans (`...`) are turned into words first.
CODE_WORDS = [("<=", " less than or equal to "), (">=", " greater than or equal to "), ("==", " equals "),
              ("!=", " is not equal to "), ("+=", " plus equals "), ("-=", " minus equals "), ("**", " to the power of "),
              ("//", " divided by "), ("->", " gives "), ("<", " less than "), (">", " greater than "),
              ("=", " equals "), ("%", " mod "), ("_", " "), ("(", " "), (")", " "), ("[", " "), ("]", " "),
              ("{", " "), ("}", " "), ('"', ""), ("'", ""), (":", " "), ("#", " ")]
OPERATORS_IN_TEXT = [("<=", " less than or equal to "), (">=", " greater than or equal to "),
                     ("==", " equals "), ("!=", " is not equal to ")]


def _say_code(code):
    code = re.sub(r"\b[fFrRbB](?=[\"'])", "", code)  # string prefixes: f"..." is said as "..."
    for symbol, words in CODE_WORDS:
        code = code.replace(symbol, words)
    return code


def speech_text(text):
    """Narration as it should be SAID: code spans in words, operators in words, single spaces."""
    text = re.sub(r"`([^`]*)`", lambda m: _say_code(m.group(1)), text)
    for symbol, words in OPERATORS_IN_TEXT:
        text = text.replace(symbol, words)
    return re.sub(r"\s+", " ", text.replace("`", "")).strip()


def _phrases(sentence):
    """Split a sentence at commas into phrases of at least PHRASE_MIN_WORDS words each, so the voice takes a
    short break there (like a teacher does). Lists of short items ("1, 2 and 3") stay whole."""
    parts, cur = [], ""
    for bit in re.split(r"(?<=,)\s+", sentence):
        cur = f"{cur} {bit}".strip()
        if cur.endswith(",") and len(cur.split()) >= config.PHRASE_MIN_WORDS:
            parts.append(cur)
            cur = ""
    if cur:
        if parts and len(cur.split()) < config.PHRASE_MIN_WORDS:
            parts[-1] = f"{parts[-1]} {cur}"  # too short to stand alone: keep it with the phrase before
        else:
            parts.append(cur)
    return parts


def _chunks(text):
    """One piece per phrase, so we can put real pauses between them: after each sentence, and a short one at
    commas. Very short sentences join the next one; a sentence longer than TTS_CHUNK_CHARS is split at commas."""
    pieces, carry = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = (carry + " " + sentence).strip()
        if len(sentence) < config.SHORT_SENTENCE_CHARS and sentence[-1:] not in "?!":
            carry = sentence
            continue
        carry = ""
        while len(sentence) > config.TTS_CHUNK_CHARS and "," in sentence[:config.TTS_CHUNK_CHARS]:
            cut = sentence[:config.TTS_CHUNK_CHARS].rfind(",") + 1
            pieces.extend(_phrases(sentence[:cut].strip()))
            sentence = sentence[cut:].strip()
        pieces.extend(_phrases(sentence))
    if carry:
        pieces.append(carry)
    return [p for p in pieces if p]


def _pause_after(piece):
    """Seconds of silence after a piece: longest after a question, a breath after a sentence, a short break at a comma."""
    if piece.endswith(("?", "!")):
        return config.QUESTION_PAUSE_S
    return config.SENTENCE_PAUSE_S if piece.endswith((".", ":", ";")) else config.PHRASE_PAUSE_S


def clip_path(lecture_id, text):
    """Cache file for this text + voice settings."""
    pacing = f"{config.SENTENCE_PAUSE_S}/{config.QUESTION_PAUSE_S}/{config.PHRASE_PAUSE_S}/{config.PHRASE_MIN_WORDS}"
    key = f"{config.TTS_VOICE}|{config.TTS_LANGUAGE}|{config.TTS_SPEED}|{pacing}|{speech_text(text)}"  # new pacing = new clips
    folder = config.lecture_dir(lecture_id) / "audio"
    folder.mkdir(exist_ok=True)
    return folder / (hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".wav")


def _synthesize_chunk(chunk):
    """One Gnani TTS call -> WAV bytes. Waits for our turn and retries on 429 (busy)."""
    for attempt in range(5):
        with _tts_lock:
            try:
                return _tts_client().synthesize(chunk, voice=config.TTS_VOICE, model=TTS_MODEL,
                                                language=config.TTS_LANGUAGE, speed=config.TTS_SPEED)
            except Exception as e:
                if getattr(e, "status_code", None) != 429 or attempt == 4:
                    raise
        time.sleep(2 ** attempt)  # 1, 2, 4, 8 s
    raise RuntimeError("unreachable")


def _pcm_frames(wav_bytes, path_hint):
    """(params, frames) from WAV bytes. Gnani's header has placeholder sizes (0xFFFFFFFF),
    so read until the data ends instead of trusting nframes."""
    tmp = path_hint.with_suffix(".part.wav")
    tmp.write_bytes(wav_bytes)
    try:
        with wave.open(str(tmp), "rb") as src:
            params = (src.getnchannels(), src.getsampwidth(), src.getframerate())
            frames = src.readframes(2**31 - 1)
    finally:
        tmp.unlink()
    return params, frames


def synthesize(text, path):
    """Synthesize `text` sentence by sentence and join the pieces, with pauses, into one clip."""
    params, frames = None, []
    pieces = _chunks(speech_text(text))
    for n, piece in enumerate(pieces):
        p, f = _pcm_frames(_synthesize_chunk(piece), path)
        params = params or p
        frames.append(f)
        if n < len(pieces) - 1:  # a real pause between sentences, like a teacher taking a breath
            channels, width, rate = params
            frames.append(b"\x00" * int(rate * _pause_after(piece)) * channels * width)
    tmp = path.with_suffix(".tmp.wav")
    with wave.open(str(tmp), "wb") as out:
        out.setnchannels(params[0])
        out.setsampwidth(params[1])
        out.setframerate(params[2])
        out.writeframes(b"".join(frames))
    os.replace(tmp, path)  # atomic: a half-written clip is never served from the cache


def wav_seconds(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def ensure_clip(lecture_id, text):
    """Return the cached clip for `text`, synthesizing it if needed."""
    path = clip_path(lecture_id, text)
    if not path.exists() or path.stat().st_size <= 44:  # 44 bytes = an empty WAV header
        synthesize(text, path)
    return path


def ensure_timing(clip, text):
    """Word timings for a clip (for lip sync). Never fails the caller: no timings just means audio-only lips."""
    from eris.classroom.lip_timing import ensure_timing as compute
    try:
        return compute(clip, text)
    except Exception as e:
        print(f"[lips] no word timings for {clip.name}: {e}")
        return None


def render_lecture(lecture_id, segments):
    """Pre-render every narration clip. Returns (total_seconds, failures)."""
    says = [s for s in segments if s["kind"] == "say" and speech_text(s["text"])]
    total, failures = 0.0, 0
    for n, seg in enumerate(says, start=1):
        try:
            clip = ensure_clip(lecture_id, seg["text"])
            total += wav_seconds(clip)
            ensure_timing(clip, seg["text"])  # word timings for the avatar's lips, ready before class
            print(f"[render] clip {n}/{len(says)}")
        except Exception as e:
            failures += 1
            print(f"[render] clip {n}/{len(says)} failed: {e}")
    return total, failures


def play(path):
    """Play a 16-bit WAV file and block until it finishes."""
    with wave.open(str(path), "rb") as w:
        rate, channels = w.getframerate(), w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    if channels > 1:
        data = data.reshape(-1, channels)
    try:
        sd.play(data, rate)
        sd.wait()
    except KeyboardInterrupt:
        sd.stop()
        raise


def speak(lecture_id, text):
    """Say `text` out loud (cached). Never raises: prints the problem instead."""
    if not speech_text(text):
        return
    try:
        play(ensure_clip(lecture_id, text))
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"[voice] could not speak: {e}")


def record_until_enter(path):
    """Record from the default microphone until Enter (or MIC_MAX_SECONDS)."""
    frames = []

    def on_audio(indata, frame_count, time_info, status):
        frames.append(indata.copy())

    with sd.InputStream(samplerate=MIC_RATE, channels=1, dtype="int16", callback=on_audio):
        input("🎙  Recording... press Enter to stop ")
    audio = np.concatenate(frames) if frames else np.zeros((0, 1), dtype=np.int16)
    audio = audio[: MIC_RATE * config.MIC_MAX_SECONDS]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(MIC_RATE)
        w.writeframes(audio.tobytes())
    return len(audio) / MIC_RATE


def listen(lecture_id):
    """Get one student doubt: typed, or spoken after typing 'r'. Returns '' for none."""
    typed = input("Student doubt (type it, 'r' + Enter to speak, Enter = none): ").strip()
    if typed.lower() != "r":
        return typed
    path = config.lecture_dir(lecture_id) / "tmp" / "doubt.wav"
    try:
        seconds = record_until_enter(path)
        if seconds < 0.5:
            print("(nothing recorded)")
            return ""
        text = _stt_client().transcribe(path, language_code=config.STT_LANGUAGE).get("transcript", "").strip()
    except Exception as e:
        print(f"[voice] could not hear that ({e}). Please type the doubt instead.")
        return input("Student doubt (Enter = none): ").strip()
    print(f"🧑‍🎓 Student said: {text or '(could not understand)'}")
    return text
