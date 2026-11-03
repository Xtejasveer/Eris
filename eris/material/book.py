"""The textbook: the pages of a book the teacher teaches this topic from (NCERT and the like).

The teacher uploads the book's PDF in Studio and gives the printed page numbers the topic spans ("38-40"). The PDF is
kept in data/<id>/book/, so it is never taken for the slide deck, and only those pages are read, indexed and shown.

Each page is drawn as a picture (like a PDF deck, slide_images.py) with where every line and word sits, as fractions
of the page, so the class can highlight, underline and circle the printed words. The worked examples on the pages are
found here too: where each example's question and its printed answer sit (the class covers the answer while the
teacher solves it) and the answer's text (its numbers are what the script's results must match). A scanned page (a
picture, no text) is read by OCR (_ocr): Tesseract when installed, else the vision model, with approximate boxes.

The class's slides and the book are taught together; which one teaches the theory and which the worked examples is the
teacher's choice (manifest "focus", see focus_rule; its key "numericals" means worked examples and exercises).
"""

import json
import re
import shutil
import threading

from eris import config

WIDTH = 1600  # pixels across, as the slides
HEADER_BAND, FOOTER_BAND = 0.09, 0.95  # page furniture: running heads, page numbers, "Reprint 2025-26"
# What books call a worked problem and its answer (English books, v1): "Example 3.8", "Solved Example 2",
# "Illustration 4", "Sample Problem 1.2", "Question 5"; "Answer", "Ans.", "Solution", "Sol.", "Hint".
EXAMPLE_RE = re.compile(r"^\W*((?:(?:Worked|Solved)\s+)?Examples?|Illustrations?|Sample\s+Problems?|Problems?|Exercises?|"
                        r"Questions?)\s+(\d+(?:\.\d+)*)\b", re.I)
ANSWER_RE = re.compile(r"^\W*(Answers?|Ans|Solutions?|Sol|Hints?)\b", re.I)
SECTION_RE = re.compile(r"^\W*\d+\.\d+(?:\.\d+)?\s+[A-Z][A-Za-z ]{3,}")  # "3.10 UNIFORM CIRCULAR MOTION"
NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?")  # 69, 2.9, -4, 3/4
# A printed answer that gives quantities, not only an argument: a decimal, or a number with a unit.
QUANTITY_RE = re.compile(r"\d+\.\d+|\d+\s*(?:m|cm|mm|km|s|ms|h|min|kg|g|mg|N|J|kJ|W|kW|K|mol|L|mL|Hz|V|A|Pa|atm|%|"
                         r"rupees|Rs)(?!\w)|(?:Rs\.?|₹)\s*\d+")
FOCUS_CHOICES = ("slides", "book", "both")
_lock = threading.Lock()


def folder(lecture_id):
    return config.data_dir(lecture_id) / "book"


def book_file(lecture_id):
    """The book's PDF, or None."""
    d = folder(lecture_id)
    return next((p for p in sorted(d.iterdir()) if p.suffix.lower() == ".pdf"), None) if d.is_dir() else None


def page_range(manifest):
    """(first, last) printed page numbers the teacher gave, or None."""
    b = (manifest or {}).get("book") or {}
    try:
        first, last = int(b["first"]), int(b["last"])
    except (KeyError, TypeError, ValueError):
        return None
    return (first, last) if 0 < first <= last else None


def focus(manifest):
    """Where the theory and the worked examples and exercises are taught from: {"theory": .., "numericals": ..}, each slides/book/both."""
    f = (manifest or {}).get("focus") or {}
    return {k: f.get(k) if f.get(k) in FOCUS_CHOICES else "both" for k in ("theory", "numericals")}


PAGE_NUMBER_BAND = 0.13  # page numbers sit in the top or bottom 13% of a page (books place them differently)


def _printed_numbers(pdf):
    """{pdf page index: the page number printed in its running head or foot}, for the pages that show one.
    Every number near the top or bottom of a page is a candidate (a unit number, a figure label and the page number
    can all sit there); the gap between print and PDF numbering that most pages agree on decides."""
    candidates = {}
    for i, page in enumerate(pdf):
        h = page.rect.height
        candidates[i] = {int(text) for x0, y0, x1, y1, text, *_ in page.get_text("words")
                         if (y0 < PAGE_NUMBER_BAND * h or y0 > (1 - PAGE_NUMBER_BAND) * h) and re.fullmatch(r"\d{1,4}", text)}
    votes = {}
    for i, nums in candidates.items():
        for off in {n - i for n in nums}:
            votes[off] = votes.get(off, 0) + 1
    if not votes or max(votes.values()) < 2:  # no numbering two pages agree on
        return {}
    offset = max(votes, key=lambda o: (votes[o], -abs(o)))
    return {i: i + offset for i, nums in candidates.items() if i + offset in nums}


def pdf_pages(pdf, first, last):
    """{printed page: pdf page index} for the teacher's printed pages. The book's own numbering (read from its running
    heads) wins; when the PDF shows none, the teacher's numbers are taken as PDF page numbers."""
    printed = _printed_numbers(pdf)
    offsets = [n - i for i, n in printed.items()]
    offset = max(set(offsets), key=offsets.count) if offsets else 1  # the usual gap between print and PDF numbering
    return {p: p - offset for p in range(first, last + 1) if 0 <= p - offset < pdf.page_count}


def _frac(box, w, h):
    return [round(box[0] / w, 4), round(box[1] / h, 4), round(box[2] / w, 4), round(box[3] / h, 4)]


def _column(box):
    """0 for the left column, 1 for the right; a line across the page counts as the left (it is read first)."""
    return 0 if (box[0] + box[2]) / 2 < 0.5 or box[2] - box[0] > 0.6 else 1


def _union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _by_column(lines):
    """[box] covering the lines, one per column they fall in (an answer can run on into the next column)."""
    cols = {}
    for ln in lines:
        cols.setdefault(_column(ln["box"]), []).append(ln["box"])
    return [_union(b) for _, b in sorted(cols.items())]


LABEL_ONLY_RE = re.compile(r"^\W*(?:(?:(?:Worked|Solved)\s+)?Examples?|Illustrations?|Sample\s+Problems?|Problems?|"
                           r"Exercises?|Questions?)\s+\d+(?:\.\d+)*\W*$|^\W*(?:Answers?|Ans|Solutions?|Sol|Hints?)\W*$", re.I)


def _with_margin_labels(lines):
    """The page's lines, each with its column ("col") and whether it is only a label ("Example 8.2", "Solution").
    Some books print such labels in the margin beside the text they label (and several times over, as a styling
    effect): the repeats are dropped, and a margin label takes the column of the text level with it, just before it,
    so it starts that text in reading order."""
    seen, out = set(), []
    for ln in lines:
        key = (ln["text"], round(ln["box"][0], 2), round(ln["box"][1], 2))
        if key not in seen:
            seen.add(key)
            out.append({**ln, "col": _column(ln["box"]), "label": bool(LABEL_ONLY_RE.match(ln["text"]))})
    for ln in out:
        if ln["label"]:
            beside = [b for b in out if not b["label"] and abs(b["box"][1] - ln["box"][1]) < 0.02
                      and (b["box"][2] < ln["box"][0] or b["box"][0] > ln["box"][2])]
            if beside:
                ln["col"] = min(beside, key=lambda b: abs(b["box"][1] - ln["box"][1]))["col"]
    return out


def find_examples(lines, page):
    """The worked examples on a page, in reading order (left column, then right):
    [{name, page, question: [box], answer: [box], question_text, answer_text}]. An example without a printed answer
    on this page has answer [] (nothing to cover or reveal)."""
    body = sorted(_with_margin_labels([ln for ln in lines if HEADER_BAND <= ln["box"][1] <= FOOTER_BAND]),
                  key=lambda ln: (ln["col"], ln["box"][1] - (0.002 if ln["label"] else 0)))
    out, cur = [], None
    for ln in body:
        text = ln["text"]
        m = EXAMPLE_RE.match(text)
        if m or (cur and SECTION_RE.match(text)):
            if cur:
                out.append(cur)
            cur = {"name": f'{" ".join(m.group(1).split()).title()} {m.group(2)}', "page": page, "q": [ln], "a": []} if m else None
            continue
        if cur is None:
            continue
        if not cur["a"] and ANSWER_RE.match(text):
            cur["a"].append(ln)
        else:
            (cur["a"] if cur["a"] else cur["q"]).append(ln)
    if cur:
        out.append(cur)
    return [{"name": e["name"], "page": page, "question": _by_column(e["q"]), "answer": _by_column(e["a"]) if e["a"] else [],
             "question_text": " ".join(ln["text"] for ln in e["q"]), "answer_text": " ".join(ln["text"] for ln in e["a"])}
            for e in out]


SCANNED_CHARS = 40  # a page with less text than this (and a picture on it) is a scan: its text is read by OCR
OCR_PROMPT = """This is one page of a textbook, with a percent grid over it (0 to 100 across the top and down the left).
Transcribe every line of printed text on it, in reading order (a two-column page: the whole left column, then the
right), exactly as printed: keep every number, unit, symbol and label ("Example 3.8", "Answer"). For each line give
its box on the grid in percent: [left, top, right, bottom]. Leave out pictures and the words inside them.
Return only JSON: {"lines": [{"text": "...", "box": [left, top, right, bottom]}]}"""


def is_scanned(path):
    """Whether the book is a scan (pictures of pages, no text): its first pages carry almost no text. Its page numbers
    can't be read either, so the teacher's page numbers are the PDF's own (pdf_pages)."""
    import pymupdf
    try:
        with pymupdf.open(path) as pdf:
            sample = [pdf[i] for i in range(min(3, pdf.page_count))]
            return bool(sample) and all(len(p.get_text().strip()) < SCANNED_CHARS for p in sample)
    except Exception:
        return False


def _words_of(lines):
    """Approximate word boxes from line boxes: each word gets a share of its line's width by its length."""
    words = []
    for ln in lines:
        parts = ln["text"].split()
        total = sum(len(p) for p in parts) + max(0, len(parts) - 1)
        x0, y0, x1, y1 = ln["box"]
        at = 0
        for p in parts:
            a, b = x0 + (x1 - x0) * at / total, x0 + (x1 - x0) * (at + len(p)) / total
            words.append({"text": p, "box": [round(a, 4), y0, round(b, 4), y1]})
            at += len(p) + 1
    return words


def _ocr(page, w, h):
    """(lines, words, how) for a scanned page, or None. Tesseract through PyMuPDF when it is installed (exact word
    boxes); else the vision model already used for pictures (images.py), which reads the lines and where each sits on
    a grid, so the word boxes are close but approximate."""
    try:
        tp = page.get_textpage_ocr(language="eng", dpi=200, full=True)
        lines = [{"text": " ".join("".join(s["text"] for s in line["spans"]).split()), "box": _frac(line["bbox"], w, h)}
                 for block in page.get_text("dict", textpage=tp)["blocks"] if block.get("type") == 0 for line in block["lines"]]
        words = [{"text": t, "box": _frac((x0, y0, x1, y1), w, h)} for x0, y0, x1, y1, t, *_ in page.get_text("words", textpage=tp)]
        return [ln for ln in lines if ln["text"]], words, "tesseract"
    except Exception:
        pass  # no Tesseract here: the vision model reads the page
    if not config.VISION_ENABLED or not config.VISION_MODEL:
        return None
    import pymupdf
    from eris.material.images import _ask, _with_grid
    try:
        info = _ask(OCR_PROMPT, _with_grid(page.get_pixmap(matrix=pymupdf.Matrix(1200 / w, 1200 / w)).tobytes("png")), "png")
    except Exception as e:
        print(f"[book] OCR failed: {e}")
        return None
    lines = []
    for ln in info.get("lines") or []:
        try:
            text = " ".join(str(ln["text"]).split())
            x0, y0, x1, y1 = (min(100.0, max(0.0, float(v))) / 100 for v in ln["box"])
        except (KeyError, TypeError, ValueError):
            continue
        if text and x1 > x0 and y1 > y0:
            lines.append({"text": text, "box": [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]})
    return (lines, _words_of(lines), "vision") if lines else None


def _out_dir(lecture_id):
    return config.lecture_dir(lecture_id) / "book"


def _render(lecture_id, path, first, last):
    import pymupdf
    out = _out_dir(lecture_id)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    pages = {}
    with pymupdf.open(path) as pdf:
        for printed, index in pdf_pages(pdf, first, last).items():
            page = pdf[index]
            w, h = page.rect.width, page.rect.height
            page.get_pixmap(matrix=pymupdf.Matrix(WIDTH / w, WIDTH / w)).save(out / f"{printed}.png")
            lines = [{"text": " ".join("".join(s["text"] for s in line["spans"]).split()),
                      "box": _frac(line["bbox"], w, h)}
                     for block in page.get_text("dict")["blocks"] if block.get("type") == 0 for line in block["lines"]]
            lines = [ln for ln in lines if ln["text"]]
            words = [{"text": t, "box": _frac((x0, y0, x1, y1), w, h)} for x0, y0, x1, y1, t, *_ in page.get_text("words")]
            ocr = None
            if sum(len(ln["text"]) for ln in lines) < SCANNED_CHARS and page.get_images():
                print(f"[book] page {printed} is a scan: reading its text with OCR ...")
                read = _ocr(page, w, h)
                if read:
                    lines, words, ocr = read
                    print(f"[book] page {printed}: {len(lines)} line(s) read ({ocr})")
            pages[str(printed)] = {"ratio": round(w / h, 4), "pdf_page": index + 1, "lines": lines, "words": words,
                                   "examples": find_examples(lines, printed), **({"ocr": ocr} if ocr else {})}
    info = {"file": path.name, "mtime": path.stat().st_mtime, "first": first, "last": last, "pages": pages}
    (out / "book.json").write_text(json.dumps(info), encoding="utf-8")
    return info


def load(lecture_id, manifest=None, render=True):
    """The book's pages as drawn ({file, first, last, pages: {printed: {ratio, lines, words, examples}}}), or None when
    the lecture has no book or no page range. Drawn once and kept until the file or the pages change."""
    manifest = manifest or config.load_manifest(lecture_id)
    path, pages = book_file(lecture_id), page_range(manifest)
    if not path or not pages:
        return None
    meta = _out_dir(lecture_id) / "book.json"
    with _lock:
        info = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else None
        if not info or (info["file"], info["mtime"], info["first"], info["last"]) != (path.name, path.stat().st_mtime, *pages):
            if not render:
                return None
            try:
                info = _render(lecture_id, path, *pages)
            except Exception as e:
                print(f"[book] could not draw {path.name}: {e}")
                return None
    return info if info["pages"] else None


def page_text(page):
    """A page's text in reading order, without its running head and foot."""
    body = sorted(_with_margin_labels([ln for ln in page["lines"] if HEADER_BAND <= ln["box"][1] <= FOOTER_BAND]),
                  key=lambda ln: (ln["col"], ln["box"][1] - (0.002 if ln["label"] else 0)))
    return "\n".join(ln["text"] for ln in body)


def examples(info):
    return [e for p in (info or {}).get("pages", {}).values() for e in p["examples"]]


def find_example(info, page, name):
    p = (info or {}).get("pages", {}).get(str(page))
    want = " ".join(str(name).split()).lower()
    return next((e for e in (p or {}).get("examples", []) if e["name"].lower() == want), None)


def _norm(text):
    # letters and digits of any script, so a word in another alphabet (a name, a symbol) is matched, not dropped
    return re.sub(r"[^\w.]+", " ", text.lower().replace("–", "-").replace("−", "-")).replace("_", " ").split()


def find_words(page, text):
    """Boxes of the printed words that read `text` (one per line they run over), or []. Matches words loosely:
    "28 m s-1" finds "28 m s–1"."""
    want = _norm(text)
    if not want:
        return []
    words = page["words"]
    toks = [(_norm(w["text"]), i) for i, w in enumerate(words)]
    flat = [(t, i) for parts, i in toks for t in parts]
    for start in range(len(flat)):
        if [t for t, _ in flat[start:start + len(want)]] == want:
            idx = sorted({i for _, i in flat[start:start + len(want)]})
            rows = {}
            for i in idx:
                b = words[i]["box"]
                rows.setdefault(round(b[1], 2), []).append(b)
            return [_union(r) for r in rows.values()]
    return []


def _value(n):
    """3/4 -> 0.75; 2.9 -> 2.9."""
    a, _, b = n.replace(" ", "").partition("/")
    return float(a) / float(b) if b and float(b) else float(a)


def _numbers(text):
    """Every number in the text; a fraction counts as its value and as its two parts (a book may print either)."""
    out = []
    for n in NUMBER_RE.findall(text.replace("–", "-").replace("−", "-")):
        out.append(_value(n))
        if "/" in n:
            out += [float(x) for x in n.replace(" ", "").split("/") if x]
    return out


def numeric_answer(answer_text):
    """Whether a printed answer gives quantities (so the notebook's results can be checked against it), not only a
    proof, a definition or words."""
    return bool(QUANTITY_RE.search(answer_text or ""))


def close(a, b):
    """Equal as a book prints them: 2.857 and 2.9 match, 69.3 and 69 match, 10 and 100 don't."""
    if a == b:
        return True
    return abs(a - b) <= max(0.05 * abs(b), 0.051 if b != int(b) else 0.5)


def matches(results, answer_text):
    """The script's results (["10.0 m", "2.9 s", "69 m"]) that the book's printed answer also gives."""
    book = _numbers(answer_text)
    return [r for r in results if (n := NUMBER_RE.search(r)) and any(close(_value(n.group(0)), b) for b in book)]


def describe(info, manifest=None, answers=True):
    """The book's pages and worked examples, for the writer's and the stager's prompts. answers=False (the stager):
    only each example's name and page, since the stager places markers and code checks the results."""
    if not info:
        return ""
    name = info["file"]
    pages = "\n\n".join(f"Book page {n}:\n{page_text(p)}" for n, p in sorted(info["pages"].items(), key=lambda x: int(x[0])))
    if answers:
        exs = "\n".join(f'- "{e["name"]}" on page {e["page"]}: {e["question_text"][:400]}'
                        + (f'\n  The book\'s printed answer: {e["answer_text"][:500]}' if e["answer_text"] else
                           " (no printed answer on this page)")
                        for e in examples(info))
    else:
        exs = "\n".join(f'- "{e["name"]}" on page {e["page"]}' for e in examples(info))
    return (f"# The textbook ({name}, pages {info['first']}-{info['last']})\n{pages}\n\n"
            f"# Worked examples in the textbook\n{exs or 'none'}")


def drop_book_hits(notes, info):
    """The research notes without the passages its searches found in the textbook: the writer gets every chosen page
    in full (describe), so those passages would be in front of it twice."""
    if not info:
        return notes
    # A search hit is "[<file> page <n>] <text>" and ends at a blank line (page text has no blank lines in it).
    return re.sub(rf"(?m)^\[{re.escape(info['file'])} page \d+\][^\n]*(?:\n(?!\n|\[|## )[^\n]*)*\n*", "", notes)


def focus_rule(manifest, has_slides):
    """What to teach from which source, as the teacher chose it in Studio."""
    f = focus(manifest)
    where = {"slides": "the slides", "book": "the textbook pages", "both": "both the slides and the textbook pages"}
    if not has_slides:
        where = {k: "the textbook pages" for k in where}
    return ("\n\n# Where to teach from (the teacher's choice)\n"
            f"- Theory (ideas, definitions, formulas, explanations): teach it from {where[f['theory']]}.\n"
            f"- Worked examples and exercises: work them from {where[f['numericals']]}."
            + (" Take them from the textbook's worked examples, by their name as printed (\"Example 3.8\"), and work "
               "each step by step in the notebook. When the answer is a quantity, write one result per line "
               "(\"Total cost = 3 x 40 = 120 rupees\"), give every final result with its unit, using the book's own "
               "numbers and rounding. The book's printed answer stays covered while the class works it out, so "
               "never mention the book's answer, or say a result agrees with the book, until every part is worked "
               "out. Then say ONE short sentence that checks all the results against the book together (\"120 "
               "rupees and 15 days. That matches the book.\"). When the answer is an argument, a proof or words, "
               "write its key points in the notebook, then compare them with the book's answer in that one "
               "sentence at the end." if f["numericals"] != "slides" or not has_slides
               else ""))


def documents(lecture_id, manifest):
    """The book's pages for the knowledge base, one Document each (source: the book's file, page: its printed
    number), and the outline entry for Studio. ([], None) without a book."""
    from langchain_core.documents import Document
    info = load(lecture_id, manifest)
    if not info:
        return [], None
    docs = [Document(page_content=page_text(p), metadata={"source": info["file"], "type": "book", "page": int(n),
                                                          "book": True})
            for n, p in sorted(info["pages"].items(), key=lambda x: int(x[0]))]
    entry = {"source": info["file"], "type": "book", "book": True, "pages": f"{info['first']}-{info['last']}",
             "items": [f"page {d.metadata['page']}: {d.page_content.splitlines()[0][:80] if d.page_content else ''}"
                       for d in docs] + [f"{e['name']} (page {e['page']})" for e in examples(info)]}
    return docs, entry


def player_pages(lecture_id, manifest=None):
    """{printed page: {url, ratio, lines, words, examples}} for the class, or {}."""
    info = load(lecture_id, manifest)
    if not info:
        return {}
    return {"file": info["file"], "first": info["first"], "last": info["last"], "count": len(info["pages"]),
            "pages": {n: {**p, "url": f"/api/lectures/{lecture_id}/book/{n}.png"} for n, p in info["pages"].items()}}
