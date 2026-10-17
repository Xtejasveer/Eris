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

import config

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


def speech_text(text):
    """Clean narration for TTS: drop markdown backticks and extra spaces."""
    return re.sub(r"\s+", " ", text.replace("`", "")).strip()


def _chunks(text):
    """Split into sentence groups of at most TTS_CHUNK_CHARS (a long sentence stays whole)."""
    groups, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if current and len(current) + len(sentence) + 1 > config.TTS_CHUNK_CHARS:
            groups.append(current)
            current = sentence
        else:
            current = (current + " " + sentence).strip()
    if current:
        groups.append(current)
    return groups


def clip_path(lecture_id, text):
    """Cache file for this text + voice settings."""
    key = f"{config.TTS_VOICE}|{config.TTS_LANGUAGE}|{config.TTS_SPEED}|{speech_text(text)}"
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
    """Synthesize `text` to a WAV file, joining sentence groups into one clip with a clean header."""
    params, frames = None, []
    for chunk in _chunks(speech_text(text)):
        p, f = _pcm_frames(_synthesize_chunk(chunk), path)
        params = params or p
        frames.append(f)
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


def render_lecture(lecture_id, segments):
    """Pre-render every narration clip. Returns (total_seconds, failures)."""
    says = [s for s in segments if s["kind"] == "say" and speech_text(s["text"])]
    total, failures = 0.0, 0
    for n, seg in enumerate(says, start=1):
        try:
            total += wav_seconds(ensure_clip(lecture_id, seg["text"]))
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
