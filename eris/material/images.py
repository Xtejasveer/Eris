"""Pictures in the teacher's material: pulled out of slides, PDFs and Word files, and understood by a vision model.

A painting of Napoleon, a map, a photo, a diagram or a chart saved as a picture carries no text, so reading the
files' text misses it. At index time every picture (big enough to matter) is sent once to a vision model with the
slide's text as context. It answers with what kind of picture it is, what it shows, the text written in it (OCR),
the steps of a diagram and the data of a chart. The answers are cached by the picture's hash, so re-indexing the
same material costs nothing.

The descriptions then feed everything else: the knowledge base (search finds them), the figures (a diagram picture
can be drawn as a flow, a chart picture recreated as a graph), the writer and doubt agent (what each slide shows),
and the class's Slides view, which shows the real pictures next to the slide's text.
"""

import base64
import hashlib
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from eris import config

WEB_TYPES = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "gif": "gif", "webp": "webp"}  # sent and shown as-is
KINDS = ("photo", "painting", "illustration", "diagram", "flowchart", "chart", "map", "screenshot", "table", "other")

VISION_PROMPT = """You are helping a teacher prepare a lecture. Look at this picture from their material.
Where it is: {where}
Text near it: {context}

Reply with JSON only (no ```), with these keys:
"kind": one of {kinds}
"description": 1-3 sentences on what the picture shows and what a student should notice (name people, places,
  events or objects when the picture or the nearby text makes them clear)
"text": every word or number written in the picture, as written ("" if none)
"steps": for a diagram or flowchart, its steps in order, e.g. ["Take the next item", "Run the body"] ([] otherwise)
"data": for a chart, its type, axes and values, e.g. "bar chart; x: A, B, C; y: hours 2, 3, 8" ("" otherwise)"""


# ---------- pulling pictures out of the files (no LLM) ----------

def _shapes(shapes):
    for shape in shapes:
        yield shape
        if getattr(shape, "shape_type", None) == 6:  # a group: look inside
            yield from _shapes(shape.shapes)


def _pptx_images(path):
    """The pictures on each slide, except icons: a picture covering less than MIN_PICTURE of the slide is decoration
    (a bullet icon, a tick), and teaching it as a picture or chart only confuses the lesson and its checks."""
    from pptx import Presentation
    from eris.material.slide_images import MIN_PICTURE
    pres = Presentation(path)
    area = pres.slide_width * pres.slide_height
    out = []
    for number, slide in enumerate(pres.slides, start=1):
        texts = [s.text_frame.text.strip() for s in slide.shapes if s.has_text_frame and s.text_frame.text.strip()]
        for shape in _shapes(slide.shapes):
            if getattr(shape, "shape_type", None) != 13:  # MSO_SHAPE_TYPE.PICTURE
                continue
            if shape.width and shape.height and shape.width * shape.height < MIN_PICTURE * area:
                continue  # an icon
            try:
                blob, ext = shape.image.blob, shape.image.ext.lower()
            except Exception:
                continue
            alt = (shape._element.xpath("./p:nvPicPr/p:cNvPr/@descr") or [""])[0].strip()
            out.append({"blob": blob, "ext": ext, "where": f"slide {number}", "ref": f"slide {number}",
                        "slide": number, "context": " / ".join(texts)[:400], "alt": alt})
    return out


def _pdf_images(path):
    from pypdf import PdfReader
    out = []
    for number, page in enumerate(PdfReader(path).pages, start=1):
        try:
            images = list(page.images)
        except Exception:
            continue
        text = (page.extract_text() or "")[:400]
        for img in images:
            ext = Path(img.name).suffix.lstrip(".").lower() or "png"
            out.append({"blob": img.data, "ext": ext, "where": f"{path.name} page {number}",
                        "ref": f"{path.name} page {number}", "slide": None, "context": text, "alt": ""})
    return out


def _docx_images(path):
    from docx import Document
    doc = Document(path)
    out = []
    text = " ".join(p.text for p in doc.paragraphs[:20])[:400]
    for n, rel in enumerate([r for r in doc.part.rels.values() if "image" in r.reltype], start=1):
        try:
            part = rel.target_part
            ext = Path(part.partname).suffix.lstrip(".").lower()
            out.append({"blob": part.blob, "ext": ext, "where": f"{path.name} picture {n}",
                        "ref": f"{path.name} picture {n}", "slide": None, "context": text, "alt": ""})
        except Exception:
            continue
    return out


EXTRACTORS = {".pptx": _pptx_images, ".pdf": _pdf_images, ".docx": _docx_images}


def _web_image(blob, ext):
    """(bytes, ext) a browser and the vision model accept, or (None, None) for a tiny icon or an unreadable format.
    Other formats (bmp, tiff, ...) are converted to PNG; big pictures are scaled down."""
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(blob))
        img.load()
    except Exception:
        return None, None
    if min(img.size) < config.IMAGE_MIN_SIDE:
        return None, None  # an icon, a bullet or a line: nothing to teach from
    if ext in WEB_TYPES and max(img.size) <= config.IMAGE_MAX_SIDE:
        return blob, ext
    img.thumbnail((config.IMAGE_MAX_SIDE, config.IMAGE_MAX_SIDE))
    out = io.BytesIO()
    img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB").save(out, "PNG")
    return out.getvalue(), "png"


def extract_images(folder):
    """Every picture worth looking at in the folder's files, each once (by content), with where it sits."""
    found, seen = [], {}  # key -> the picture as recorded (once per content)
    for path in sorted(Path(folder).iterdir()):
        extract = EXTRACTORS.get(path.suffix.lower())
        if extract is None or path.name.startswith("."):
            continue
        try:
            items = extract(path)
        except Exception as e:
            print(f"[index] could not read the pictures in {path.name}: {e}")
            continue
        for item in items:
            blob, ext = _web_image(item["blob"], item["ext"])
            if blob is None:
                continue
            key = hashlib.sha1(blob).hexdigest()[:16]
            if key in seen:
                # The same picture in a document and on a slide: keep the slide, so the class can show it.
                first = seen[key]
                if not first.get("slide") and item.get("slide"):
                    first.update({k: item[k] for k in ("where", "ref", "slide", "context", "alt")}, source=path.name)
                continue
            seen[key] = {**item, "blob": blob, "ext": ext, "key": key, "source": path.name}
            found.append(seen[key])
    return found


# ---------- understanding them (vision model) ----------

_model = None


def _ask_vision(blob, ext, where, context):
    global _model
    from langchain.chat_models import init_chat_model
    from langchain_core.messages import HumanMessage
    if _model is None:
        _model = init_chat_model(f"openrouter:{config.VISION_MODEL}", temperature=0, max_retries=1)
    data = base64.b64encode(blob).decode()
    message = HumanMessage(content=[
        {"type": "text", "text": VISION_PROMPT.format(where=where, context=context or "(none)", kinds=", ".join(KINDS))},
        {"type": "image_url", "image_url": {"url": f"data:image/{WEB_TYPES.get(ext, ext)};base64,{data}"}},
    ])
    reply = _model.invoke([message]).content
    if isinstance(reply, list):
        reply = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in reply)
    match = re.search(r"\{.*\}", reply or "", re.S)
    info = json.loads(match.group(0)) if match else {}
    kind = str(info.get("kind", "other")).lower()
    return {"kind": kind if kind in KINDS else "other", "description": str(info.get("description", "")).strip(),
            "text": str(info.get("text", "")).strip(), "steps": [str(s) for s in info.get("steps") or []],
            "data": str(info.get("data", "")).strip()}


def describe_images(folder, lecture_id):
    """Extract the folder's pictures, save them, and describe each with the vision model (cached by content).
    Returns the pictures as dicts (without the bytes) and writes images.json. Never raises."""
    out_dir = config.lecture_dir(lecture_id) / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    pictures = extract_images(folder)
    todo = []
    for pic in pictures:
        (out_dir / f"{pic['key']}.{pic['ext']}").write_bytes(pic["blob"])
        cached = out_dir / f"{pic['key']}.json"
        if cached.exists():
            pic.update(json.loads(cached.read_text(encoding="utf-8")))
        elif config.VISION_ENABLED:
            todo.append(pic)

    def describe(pic):
        try:
            return pic, _ask_vision(pic["blob"], pic["ext"], pic["where"], pic["context"]), None
        except Exception as e:
            return pic, None, e

    if todo:
        print(f"[index] describing {len(todo)} picture(s) with {config.VISION_MODEL} ...")
        with ThreadPoolExecutor(max_workers=min(4, len(todo))) as pool:
            for pic, info, error in pool.map(describe, todo):
                if info is None:
                    print(f"[index] could not describe the picture on {pic['where']}: {str(error)[:150]}")
                    continue
                pic.update(info)
                (out_dir / f"{pic['key']}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    result = [{k: v for k, v in p.items() if k != "blob"} for p in pictures]
    (config.lecture_dir(lecture_id) / "images.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    described = sum(1 for p in result if p.get("description"))
    print(f"[index] found {len(result)} picture(s), {described} described")
    return result


def load(lecture_id):
    path = config.lecture_dir(lecture_id) / "images.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def picture_text(pic):
    """A picture as searchable text for the knowledge base."""
    parts = [f"Picture on {pic['where']} ({pic.get('kind', 'picture')}): {pic.get('description', '')}"]
    if pic.get("text"):
        parts.append(f"Text in the picture: {pic['text']}")
    if pic.get("steps"):
        parts.append("Steps: " + " -> ".join(pic["steps"]))
    if pic.get("data"):
        parts.append(f"Chart data: {pic['data']}")
    return "\n".join(parts)


def describe_list(pictures):
    """The pictures as lines for prompts and the board."""
    rows = [p for p in pictures if p.get("description")]
    if not rows:
        return "none"
    return "\n".join(f"- {p['where']} ({p.get('kind', 'picture')}): {p['description']}"
                     + (f" Text in it: {p['text'][:120]}" if p.get("text") else "") for p in rows)
