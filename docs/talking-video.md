# Photorealistic teacher video (MuseTalk on Modal)

Pre-renders a lip-synced video of a real-looking teacher for every narration clip of a lecture. MuseTalk
re-draws the mouth of a short teacher video so it speaks each Gnani clip; it runs on a rented Modal GPU, so
nothing heavy runs on this machine.

| File | Role |
|---|---|
| `musetalk_modal.py` | Modal app: GPU image, weight download, avatar preparation, `render()` |
| `talking_video.py` | Local side: finds the lecture's WAV clips, sends them in batches, saves the MP4s |
| `main.py video` | CLI entry |

## One-time setup

1. Create a free Modal account at <https://modal.com> (the Starter plan includes $30 of compute a month).
   Modal only allows GPU functions once a payment method is on the account (the free credits are used first);
   set a spend limit under Settings → Usage & Billing so nothing beyond the credits is charged.
2. Install the client and log in (opens the browser):
   ```bash
   .venv/bin/pip install modal
   .venv/bin/modal setup
   ```

## Render a lecture

The narration audio must exist first (`python main.py render --lecture <id>`).

```bash
.venv/bin/python main.py video --lecture for_loops --teacher media/teachers/musetalk_sample.mp4 --limit 3
```

- `--limit 3` renders only the first three clips: use it to judge quality before rendering everything.
- The first run builds the GPU image and downloads about 1.5 GB of weights into the `eris-musetalk` Modal Volume
  (several minutes, once). The first call for a teacher also prepares that teacher (a minute or two, once).
- Output: `workspace/lectures/<id>/video/<teacher id>/<clip>.mp4`, one per narration clip, named like the WAV
  in `audio/`. Re-running skips clips that already have a video.

## The teacher video

`media/teachers/musetalk_sample.mp4` is MuseTalk's demo video, for **testing only**. For the real teacher:

- 10–30 s, 25 fps, face clearly visible and front-facing, steady light, plain background.
- Mouth closed or barely moving, small natural head motion, no hands crossing the face.
- MuseTalk loops it forwards and backwards behind the speech, so a calm, "listening" take works best.
- Use a person who has given consent, or an AI-generated face you have the rights to.

## Licences

Code: MuseTalk (MIT). Weights: MuseTalk v1.5 (MIT), sd-vae-ft-mse (MIT), whisper-tiny (Apache-2.0),
DWPose (Apache-2.0), face-parse-bisent (WTFPL), s3fd (BSD-3). All allow commercial use.

## Cost

An L4 is about $0.80/h on Modal and MuseTalk runs faster than real time on it, so a 30-minute lecture should take
well under an hour of GPU time — inside the free monthly credits. Measure on the first real run.
