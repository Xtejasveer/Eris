"""Prepare the video tutor: two short clips of the same character (idle, talking) become matched square loops.

`python main.py tutor-video --idle idle.mp4 --talking talking.mp4` writes web/assets/tutor/: tutor-idle.mp4,
tutor-talking.mp4 and a poster image for each. With --name male they are tutor-male-idle.mp4 and so on: the classroom
shows that tutor when the lesson's voice is a man's (config.voice_gender). --idle-start/--idle-end keep only part of
the idle clip (e.g. where the generator opened the mouth). The classroom shows the talking loop while the voice speaks and the
idle loop otherwise, so the two must line up exactly:
- same framing: each clip is cropped around the character's head, scaled so the head has the same size and place,
- same colour: the talking clip is tinted to the idle clip's background (measured on the square crops),
- seamless loops: the idle clip plays forward then backward (its end never matches its start), the talking clip
  fades its last frames into its first,
- web size: 400 x 400 H.264, no sound, fast start.
Works from any video size (the generators make 16:9) as long as the background is plain and the head is in frame.
"""

from pathlib import Path

import av
from PIL import Image, ImageChops, ImageStat

OUT_DIR = Path("web/assets/tutor")
SIZE = 400              # output pixels (the circle is 84 px; 400 stays sharp on high-density screens)
MAX_ZOOM_OUT = 1.35     # crop size at most this many head widths (more room around the head when the clip allows it)
TOP_ROOM = 0.08         # room above the hair, in head widths, when the clip has it
FADE_FRAMES = 24        # talking loop: frames blended at the loop point (one second at 24 fps)
CRF = "24"              # H.264 quality (lower = better, bigger)


def read_clip(path, start=None, end=None):
    """(frames as PIL images, frames per second), only those from `start` to `end` seconds when given."""
    with av.open(str(path)) as c:
        stream = c.streams.video[0]
        fps = stream.average_rate or 24
        frames = [f.to_image() for f in c.decode(video=0)]
    first = round((start or 0) * float(fps))
    last = len(frames) if end is None else round(end * float(fps))
    return frames[first:last], fps


def background(img):
    """The plain background colour: the average of the four corners."""
    w, h = img.size
    corners = [img.crop(box) for box in ((0, 0, 40, 40), (w - 40, 0, w, 40), (0, h - 40, 40, h), (w - 40, h - 40, w, h))]
    stats = [ImageStat.Stat(c).mean for c in corners]
    return tuple(sum(s[i] for s in stats) / 4 for i in range(3))


NECK_RATIO = 0.7        # a row this much narrower than the head below it is the neck


def head_box(img):
    """Box around the head: from the top of the hair down to the neck, as wide as the head. Measured on the head, not
    the whole character, so wide shoulders don't make the face small in the circle. Without a clear neck (long hair,
    a scarf) it is the box around everything that is not background."""
    bg = tuple(round(v) for v in background(img))
    mask = ImageChops.difference(img, Image.new("RGB", img.size, bg)).convert("L").point(lambda p: 255 if p > 30 else 0)
    box = mask.getbbox()
    if not box:
        return box
    x0, y0, x1, y1 = box
    rows = {}
    for y in range(y0, y1, 4):
        r = mask.crop((0, y, img.width, y + 1)).getbbox()
        if r:
            rows[y] = r
    search = [y for y in rows if y0 + 0.3 * (y1 - y0) <= y <= y0 + 0.8 * (y1 - y0)]
    if not search:
        return box
    neck = min(search, key=lambda y: rows[y][2] - rows[y][0])
    above = [rows[y] for y in rows if y < neck]
    head = (min(r[0] for r in above), max(r[2] for r in above))
    if rows[neck][2] - rows[neck][0] > NECK_RATIO * (head[1] - head[0]):
        return box  # no clear neck: keep the whole character
    return head[0], y0, head[1], neck


def typical_box(frames, samples=12):
    """The head box across the clip (the median of each edge over a dozen frames): one frame can catch an odd pose
    and make the two clips' heads differ in size, which shows as a jump when the tutor starts or stops talking."""
    import statistics
    boxes = [b for b in (head_box(frames[i]) for i in range(0, len(frames), max(1, len(frames) // samples))) if b]
    return tuple(round(statistics.median(edge)) for edge in zip(*boxes))


def matched_crops(boxes, sizes):
    """One square crop per clip, so the head has the same size and position in each, as large as all clips allow."""
    top_room = min([TOP_ROOM] + [y0 / (x1 - x0) for (x0, y0, x1, _) in boxes])
    # wide enough for the head, and tall enough to show the chin and neck under it
    zoom = max([MAX_ZOOM_OUT] + [top_room + 1.12 * (y1 - y0) / (x1 - x0) for (x0, y0, x1, y1) in boxes])
    for (x0, y0, x1, _), (w, h) in zip(boxes, sizes):
        hw, cx = x1 - x0, (x0 + x1) / 2
        zoom = min(zoom, (h - y0 + top_room * hw) / hw,                 # the crop must not run past the bottom
                   2 * cx / hw, 2 * (w - cx) / hw)                       # or past either side
    crops = []
    for (x0, y0, x1, _) in boxes:
        hw, cx = x1 - x0, (x0 + x1) / 2
        side, top = zoom * hw, max(0.0, y0 - top_room * hw)  # max(): rounding must not put the crop above the frame
        crops.append((max(0.0, cx - side / 2), top, cx + side / 2, top + side))
    return crops, zoom


def tint(frames, source_bg, target_bg):
    """Shift a clip's colours so its background matches the other clip's."""
    gains = [t / max(s, 1) for s, t in zip(source_bg, target_bg)]
    lut = [min(255, round(v * g)) for g in gains for v in range(256)]
    return [f.point(lut) for f in frames]


def ping_pong(frames):
    """Forward then backward: the loop point always matches."""
    return frames + frames[-2:0:-1]


def fade_loop(frames, n=FADE_FRAMES):
    """Blend the last n frames into the first n, and start after them: the end flows into the start."""
    n = min(n, len(frames) // 4)
    body = frames[n:len(frames) - n]
    tail = [Image.blend(frames[len(frames) - n + i], frames[i], (i + 1) / (n + 1)) for i in range(n)]
    return body + tail


def write_mp4(frames, fps, path):
    with av.open(str(path), "w", options={"movflags": "+faststart"}) as out:
        stream = out.add_stream("libx264", rate=fps)
        stream.width = stream.height = SIZE
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": CRF, "preset": "slow", "tune": "animation"}
        for img in frames:
            for packet in stream.encode(av.VideoFrame.from_image(img)):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)


def prepare(idle_path, talking_path, out_dir=OUT_DIR, name="", idle_start=None, idle_end=None):
    (idle, fps_i), (talk, fps_t) = read_clip(idle_path, idle_start, idle_end), read_clip(talking_path)
    if len(idle) < 24:
        raise SystemExit(f"[tutor] only {len(idle)} idle frames between {idle_start} and {idle_end} s: keep at least one second")
    boxes = [typical_box(idle), typical_box(talk)]
    (crop_i, crop_t), zoom = matched_crops(boxes, [idle[0].size, talk[0].size])
    print(f"[tutor] head boxes: idle {boxes[0]}, talking {boxes[1]}; crop = {zoom:.2f} head widths")
    square = lambda frames, box: [f.resize((SIZE, SIZE), Image.LANCZOS, box=box) for f in frames]  # noqa: E731
    idle_sq, talk_sq = square(idle, crop_i), square(talk, crop_t)
    talk_sq = tint(talk_sq, background(talk_sq[0]), background(idle_sq[0]))  # measured where the circle shows them
    idle_loop = ping_pong(idle_sq)
    talk_loop = fade_loop(talk_sq)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"tutor-{name}-" if name else "tutor-"
    for clip, frames, fps in (("idle", idle_loop, fps_i), ("talking", talk_loop, fps_t)):
        path = out_dir / f"{prefix}{clip}.mp4"
        write_mp4(frames, fps, path)
        frames[0].save(out_dir / f"{prefix}{clip}-poster.webp", quality=88)
        print(f"[tutor] {path}: {len(frames)} frames, {len(frames) / float(fps):.1f} s, {path.stat().st_size // 1024} KB")
    return idle_loop, talk_loop
