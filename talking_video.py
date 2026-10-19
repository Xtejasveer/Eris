"""Pre-render photorealistic teacher video for a lecture: every narration clip is lip-synced by MuseTalk on Modal.

    python main.py video --lecture for_loops --teacher teacher.mp4 [--limit 3]

Needs the narration audio first (`python main.py render --lecture ...`) and a Modal account (`modal setup`).
Videos land next to the audio as workspace/lectures/<id>/video/<teacher>/<clip>.mp4, named like the WAV they
speak, so a clip is only rendered once per teacher.
"""

import hashlib
import json
from pathlib import Path

from eris import config
BATCH = 8  # clips per GPU call: keeps each reply small and lets an interrupted run resume


def teacher_id(video_path):
    """Avatar id = file name + content hash, so a new teacher video is prepared again."""
    data = Path(video_path).read_bytes()
    stem = "".join(c if c.isalnum() else "_" for c in Path(video_path).stem)[:30]
    return f"{stem}_{hashlib.sha1(data).hexdigest()[:10]}"


def video_dir(lecture_id, avatar_id):
    folder = config.lecture_dir(lecture_id) / "video" / avatar_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def render_lecture_video(lecture_id, teacher_video, limit=None):
    import modal

    from eris.classroom import voice
    from musetalk_modal import app, render

    segments = json.loads((config.lecture_dir(lecture_id) / "script.json").read_text(encoding="utf-8"))
    says = [s for s in segments if s["kind"] == "say" and voice.speech_text(s["text"])]
    wavs = [voice.clip_path(lecture_id, s["text"]) for s in says]
    missing = [w for w in wavs if not w.exists()]
    if missing:
        print(f"[video] skipping {len(missing)} narration clip(s) with no audio yet "
              f"(python main.py render --lecture {lecture_id} makes them)")
        wavs = [w for w in wavs if w.exists()]

    avatar_id = teacher_id(teacher_video)
    out_dir = video_dir(lecture_id, avatar_id)
    todo = [w for w in wavs if not (out_dir / f"{w.stem}.mp4").exists()]
    print(f"[video] teacher {avatar_id}: {len(wavs) - len(todo)} clip(s) already rendered, {len(todo)} to go")
    if limit:
        todo = todo[:limit]

    if not todo:
        return out_dir
    teacher_bytes = Path(teacher_video).read_bytes()
    with modal.enable_output(), app.run():
        for start in range(0, len(todo), BATCH):
            batch = todo[start:start + BATCH]
            # The teacher video only travels with the first batch; the avatar is cached on the Volume after that.
            result = render.remote(avatar_id, {w.stem: w.read_bytes() for w in batch},
                                   teacher_video=teacher_bytes if start == 0 else None)
            for name, mp4 in result.items():
                (out_dir / f"{name}.mp4").write_bytes(mp4)
            print(f"[video] {min(start + BATCH, len(todo))}/{len(todo)} clips rendered")
    print(f"[video] done: {out_dir}")
    return out_dir
