"""The lesson's slide deck: the first PowerPoint in its material or, when it has none, the first PDF, whose pages are
then its slides. Everything that counts, reads, draws or shows slides asks here, so lecture notes given as a PDF are
taught with the Slides view just like a deck."""

import re
from pathlib import Path

from eris import config

DECK_TYPES = (".pptx", ".pdf")


def deck_in(folder):
    """The deck file in a material folder, or None."""
    files = sorted(p for p in Path(folder).iterdir() if p.is_file() and not p.name.startswith(".")) if Path(folder).is_dir() else []
    for suffix in DECK_TYPES:
        found = next((p for p in files if p.suffix.lower() == suffix), None)
        if found:
            return found
    return None


def deck_path(lecture_id):
    return deck_in(config.data_dir(lecture_id))


def is_pdf(path):
    return path is not None and path.suffix.lower() == ".pdf"


def slide_count(path):
    """How many slides (or pages) the deck has; 0 when it can't be read."""
    try:
        if is_pdf(path):
            import pymupdf
            with pymupdf.open(path) as pdf:
                return pdf.page_count
        from pptx import Presentation
        return len(Presentation(path).slides)
    except Exception:
        return 0


def plain_image(blob):
    """True for an image of one flat colour: a box's shadow or fill that a PDF stores as a picture, not a picture."""
    import io
    from PIL import Image, ImageStat
    try:
        return max(ImageStat.Stat(Image.open(io.BytesIO(blob)).convert("RGB")).stddev) < 2
    except Exception:
        return False


def page_pictures(pdf, page, min_share):
    """The bounding boxes (in points) of the real pictures on a PDF page: not icons (under min_share of the page)
    and not flat colour (shadows, fills)."""
    area = page.rect.width * page.rect.height
    boxes = []
    for info in page.get_image_info(xrefs=True):
        b = info["bbox"]
        if (b[2] - b[0]) * (b[3] - b[1]) < min_share * area:
            continue
        try:
            if info.get("xref") and plain_image(pdf.extract_image(info["xref"])["image"]):
                continue
        except Exception:
            pass
        boxes.append(b)
    return boxes


BULLET_RE = re.compile(r"\s*(?<!\S)(?=(?:[•▪●◦■□➢►–]|\d{1,2}[.)]\s|[a-z][.)]\s)\s*\S)")  # a marker after a space


def _page_points(page):
    """A PDF page's text as a slide reads: one line per title or bullet point. A PDF breaks a point wherever the page
    ran out of width (justified text even word by word), so a block's lines are joined again and split only where a
    new bullet or number starts. The player finds a highlighted point however the page wrapped it."""
    points = []
    for block in page.get_text("blocks"):
        if block[6] != 0:  # an image block
            continue
        text = " ".join(block[4].split())
        points += [p.strip() for p in BULLET_RE.split(text) if p.strip()]
    return "\n".join(points)


def slide_texts(path):
    """{slide number: its text} for the slides (pages) that have any."""
    if path is None:
        return {}
    if is_pdf(path):
        import pymupdf
        with pymupdf.open(path) as pdf:
            texts = {n: _page_points(page) for n, page in enumerate(pdf, 1)}
        return {n: t for n, t in texts.items() if t}
    from eris.material.indexer import load_pptx
    return {d.metadata["slide"]: d.page_content for d in load_pptx(path)}
