"""Find the graphs and diagrams in the teacher's material. No LLM here.

The script may only turn a graph into an interactive [VISUAL] when the material has one for that topic, so the
writer never invents graphs and has the details (chart type, axes, series) instead of guessing them.
Diagrams are shown as they are, with [SLIDE n]; they are listed so the writer knows where they are.

- PPTX charts are read exactly: chart type, title, categories (x values), series names and a few values.
- PPTX pictures are classified by their alt text and the slide's words ("graph", "histogram", "diagram", ...).
- PDF and DOCX: figure captions ("Figure 2: ...", "Graph of ...") and pages with images, classified the same way.

A figure is {"ref": "slide 4" | "notes.pdf page 2" | "lab.docx figure 1", "kind": "graph" | "diagram",
             "source", "where", "title", "details"}. find_figures(folder) returns the list.
"""

import re
from pathlib import Path

GRAPH_WORDS = re.compile(r"\b(graphs?|charts?|plots?|curves?|histograms?|scatter|bar chart|line chart|pie chart|"
                         r"axis|axes|distribution|trend|regression line|line of best fit|x-axis|y-axis)\b", re.I)
DIAGRAM_WORDS = re.compile(r"\b(diagrams?|flow ?charts?|figures?|illustrations?|tree|cycle|architecture|"
                           r"schematic|map|layout|pipeline)\b", re.I)
NUMBERED_RE = re.compile(r"^\s*(?:step\s*)?(\d+)\s*[.):\-–]\s+(\S.*)$", re.I)
ARROW_RE = re.compile(r"\s*(?:->|→|=>|⟶)\s*")
CAPTION_RE = re.compile(r"^\s*((?:figure|fig\.?|graph|chart|plot|diagram)\s*\d*\s*[:.\-–]\s*.+)$", re.I)


def _kind(*texts):
    text = " ".join(t for t in texts if t)
    if GRAPH_WORDS.search(text):
        return "graph"
    if DIAGRAM_WORDS.search(text):
        return "diagram"
    return None


def step_lists(text):
    """Written processes in a piece of text: numbered steps (1. 2. 3. or Step 1/2/3, at least 3) and arrow chains
    of at least 3 multi-word steps ("take the next item -> run the body -> repeat"). Returns [[step, ...], ...].
    A trace like "count = 1 -> 2 -> 3" is not a process (its parts are not words)."""
    found, run = [], []
    for line in text.splitlines():
        m = NUMBERED_RE.match(line)
        if m and int(m.group(1)) == len(run) + 1:
            run.append(m.group(2).strip())
            continue
        if len(run) >= 3:
            found.append(run)
        run = [m.group(2).strip()] if m and m.group(1) == "1" else []
        parts = [p.strip(" .") for p in ARROW_RE.split(line.strip().lstrip("•*-– ")) if p.strip(" .")]  # no bullet mark
        if len(parts) >= 3 and sum(len(re.findall(r"[A-Za-z]{2,}", p)) >= 2 for p in parts) >= 3:
            found.append(parts)
    if len(run) >= 3:
        found.append(run)
    return found


NOT_PROCESS_RE = re.compile(r"\b(exercises?|questions?|quiz(?:zes)?|homework|assignments?|tasks?|practice|"
                            r"discussion|activit(?:y|ies)|review)\b", re.I)


def _is_process(steps, title):
    """A numbered list of exercises or questions is not a process to draw: its heading says so, or most of its
    items are questions."""
    if NOT_PROCESS_RE.search(title or ""):
        return False
    return sum(s.rstrip().endswith("?") for s in steps) * 2 < len(steps)


def _flow_figures(text, where, ref, title):
    return [{"kind": "flow", "title": title, "where": where, "ref": ref,
             "details": "steps: " + " -> ".join(steps)} for steps in step_lists(text) if _is_process(steps, title)]


def _shapes(shapes):
    """All shapes on a slide, including the ones inside groups."""
    for shape in shapes:
        yield shape
        if getattr(shape, "shape_type", None) == 6:  # MSO_SHAPE_TYPE.GROUP
            yield from _shapes(shape.shapes)


def _chart_details(chart):
    parts = [f"{chart.chart_type.name.lower().replace('_', ' ')} chart" if chart.chart_type else "chart"]
    try:
        plot = chart.plots[0]
        cats = [str(c) for c in plot.categories]
        if cats:
            parts.append(f"x values: {', '.join(cats[:12])}{' ...' if len(cats) > 12 else ''}")
        for s in list(plot.series)[:4]:
            vals = [round(v, 3) if isinstance(v, float) else v for v in list(s.values)[:12]]
            parts.append(f"series '{s.name}': {', '.join(map(str, vals))}{' ...' if len(s.values) > 12 else ''}")
    except Exception:
        pass
    for axis_name in ("category_axis", "value_axis"):
        try:
            axis = getattr(chart, axis_name)
            if axis.has_title and axis.axis_title.text_frame.text.strip():
                parts.append(f"{'x' if axis_name == 'category_axis' else 'y'} axis: {axis.axis_title.text_frame.text.strip()}")
        except Exception:
            pass
    return "; ".join(parts)


def pptx_figures(path):
    from pptx import Presentation
    out = []
    for number, slide in enumerate(Presentation(path).slides, start=1):
        texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame and s.text_frame.text.strip()]
        title = texts[0].strip().splitlines()[0] if texts else f"Slide {number}"
        slide_text = " ".join(texts)
        out += _flow_figures("\n".join(texts), f"slide {number} ({title})", f"slide {number}", title)
        for shape in _shapes(slide.shapes):
            if getattr(shape, "has_chart", False):
                chart = shape.chart
                name = chart.chart_title.text_frame.text.strip() if chart.has_title else title
                out.append({"kind": "graph", "title": name, "where": f"slide {number} ({title})",
                            "ref": f"slide {number}", "details": _chart_details(chart)})
            elif getattr(shape, "shape_type", None) == 13:  # MSO_SHAPE_TYPE.PICTURE
                alt = shape._element.xpath("./p:nvPicPr/p:cNvPr/@descr")
                alt = alt[0].strip() if alt else ""
                kind = _kind(alt, shape.name) or _kind(slide_text)
                if kind:
                    out.append({"kind": kind, "title": alt or title, "where": f"slide {number} ({title})",
                                "ref": f"slide {number}", "details": f"picture{': ' + alt if alt else ''}; slide text: "
                                                                      f"{' / '.join(t.strip() for t in texts[1:3])[:200]}"})
    return out


def _first_words(text, n=8):
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return " ".join(line.split()[:n])


def pdf_figures(path, as_slides=False):
    """as_slides: the PDF is the lesson's deck (eris.material.deck), so a figure is found "on slide N", like a deck's."""
    from pypdf import PdfReader
    out = []
    for number, page in enumerate(PdfReader(path).pages, start=1):
        text = page.extract_text() or ""
        here = f"slide {number}" if as_slides else f"{path.name} page {number}"
        where = f"slide {number} ({_first_words(text) or 'page ' + str(number)})" if as_slides else here
        out += _flow_figures(text, where, here, _first_words(text) or f"page {number}")
        captions = [m.group(1).strip() for line in text.splitlines() if (m := CAPTION_RE.match(line))]
        try:
            images = len(page.images)
        except Exception:
            images = 0
        for cap in captions:
            kind = _kind(cap) or "diagram"
            out.append({"kind": kind, "title": cap[:120], "where": where, "ref": here, "details": f"caption: {cap[:200]}"})
        if images and not captions:
            kind = _kind(text[:400])
            if kind:
                out.append({"kind": kind, "title": f"image on page {number}", "where": where, "ref": here,
                            "details": f"{images} image(s); page text: {text[:200]}"})
    return out


def docx_figures(path):
    from docx import Document
    out = []
    doc = Document(path)
    heading, lines = path.stem, []
    for p in doc.paragraphs + [None]:  # None flushes the last section
        is_heading = p is not None and (p.style.name if p.style is not None else "").startswith("Heading")
        if p is None or is_heading:
            out += _flow_figures("\n".join(lines), f"{path.name} ({heading})", f"{path.name} {heading}", heading)
            heading, lines = (p.text.strip() if p is not None else heading), []
        elif p.text.strip():
            lines.append(p.text)
    for n, p in enumerate(doc.paragraphs):
        style = p.style.name if p.style is not None else ""
        m = CAPTION_RE.match(p.text or "")
        if m or style.lower() == "caption":
            cap = (m.group(1) if m else p.text).strip()
            out.append({"kind": _kind(cap) or "diagram", "title": cap[:120], "where": f"{path.name}",
                        "ref": f"{path.name} figure {len(out) + 1}", "details": f"caption: {cap[:200]}"})
    return out


FINDERS = {".pptx": pptx_figures, ".pdf": pdf_figures, ".docx": docx_figures}


def find_figures(folder, pictures=None):
    """Charts, diagrams and step lists found from the files' text and structure. pictures: the vision model's
    descriptions; when they exist they decide what each picture is, so guesses from alt text are left out."""
    from eris.material.deck import deck_in, is_pdf
    described = bool([p for p in pictures or [] if p.get("description")])
    deck = deck_in(folder)
    figures = []
    for path in sorted(Path(folder).iterdir()):
        finder = FINDERS.get(path.suffix.lower())
        if finder is None or path.name.startswith("."):
            continue
        try:
            for fig in (pdf_figures(path, as_slides=True) if is_pdf(deck) and path == deck else finder(path)):
                guessed = fig["details"].startswith("picture") or "image(s); page text" in fig["details"]
                if described and guessed:
                    continue  # the vision model says what this picture really is
                fig["source"] = path.name
                figures.append(fig)
        except Exception as e:
            print(f"[index] could not look for figures in {path.name}: {e}")
    return figures


def figures_from_pictures(pictures):
    """Figures from the vision model's descriptions: a diagram picture with steps can be drawn as a flow, a chart
    picture with data recreated as a graph, and any other picture (photo, painting, map, ...) taught from its slide."""
    out = []
    for p in pictures or []:
        if not p.get("description"):
            continue
        base = {"source": p["source"], "where": p["where"], "ref": p["ref"],
                "title": p["description"].split(". ")[0][:120]}
        if p.get("kind") in ("diagram", "flowchart") and len(p.get("steps") or []) >= 2:
            out.append({**base, "kind": "diagram", "details": "steps: " + " -> ".join(p["steps"])})
        elif p.get("kind") == "chart" and p.get("data"):
            out.append({**base, "kind": "graph", "details": p["data"]})
        else:
            out.append({**base, "kind": "picture", "details": f"{p.get('kind', 'picture')}: {p['description']}"
                        + (f" Text in it: {p['text'][:150]}" if p.get("text") else "")})
    return out


# How each figure is taught (decided once at index time, see decide_use): "interactive" = a [VISUAL] graph with
# sliders, "draw" = a [FLOW] diagram drawn block by block, "show" = shown on its slide and explained.
def use_of(f):
    return f.get("use") or ("show" if f["kind"] == "picture" else "draw" if f["kind"] in ("diagram", "flow")
                            else "interactive")


def graphs(figures):
    """Charts the class makes interactive."""
    return [f for f in figures or [] if f["kind"] == "graph" and use_of(f) == "interactive"]


def flows(figures):
    """What a flow diagram may be drawn from: a diagram, or a written list of steps (unless it is only shown)."""
    return [f for f in figures or [] if f["kind"] in ("diagram", "flow") and use_of(f) == "draw"]


def shown(figures):
    """Pictures, and charts or diagrams that are best shown on their slide as they are."""
    return [f for f in figures or [] if use_of(f) == "show"]


def describe(figures):
    """The figures as lines for prompts and the board, each with how to use it."""
    if not figures:
        return "none: the material has no graphs or diagrams"
    names = {"graph": "graph", "diagram": "diagram", "flow": "step list", "picture": "picture"}
    return "\n".join(f'- [{use_of(f)}] {names.get(f["kind"], f["kind"])} from="{f["ref"]}" ({f["where"]}): '
                      f'{f["title"]}. {f["details"]}' + (f' Why {use_of(f)}: {f["use_why"]}' if f.get("use_why") else "")
                      for f in figures)


PIE_RE = re.compile(r"\b(pie|doughnut|donut)\b", re.I)


def default_use(f):
    """The rule when Jev can't decide: pictures and pie charts are shown; other charts are interactive; diagrams
    and step lists are drawn."""
    if f["kind"] == "picture" or (f["kind"] == "graph" and PIE_RE.search(f"{f['title']} {f['details']}")):
        return "show"
    return "draw" if f["kind"] in ("diagram", "flow") else "interactive"


def matches(ref, figures, kind="graph"):
    """The figure a [VISUAL from="..."] (kind "graph") or [FLOW from="..."] (kind "flow": a diagram or step list)
    points at, or None. "slide 4" also matches "deck.pptx slide 4"."""
    want = " ".join(str(ref or "").lower().split())
    if not want:
        return None
    for f in figures or []:
        have = f["ref"].lower()
        kinds = ("diagram", "flow") if kind == "flow" else (kind,)
        if f["kind"] in kinds and use_of(f) != "show" and (want == have or have.endswith(want) or want.endswith(have)):
            return f
    return None


# A line that is clearly code (Python and similar): a material with several of these teaches with code.
CODE_LINE_RE = re.compile(r"^\s*(import \w|from \w+ import|def \w+\(|class \w+|for \w+ in .+:|while .+:|if .+:\s*$|"
                          r"elif .+:|else:\s*$|return\b|print\(|\w+\s*=\s*\[|\w+\s*=\s*\w+\(|\w+\s*\+=\s*|```)")
CODE_MIN_LINES = 3


def environments(docs, figures, chunks=()):
    """Which class environments this material allows. The notebook is always there; slides when there is a
    deck; code only when the material has code; graphs only when it has graphs (figures)."""
    code_lines = sum(1 for d in docs for ln in d.page_content.splitlines() if CODE_LINE_RE.match(ln))
    from eris import config
    return {"notebook": True,
            "slides": any("slide" in d.metadata for d in docs),  # a PowerPoint, or a PDF deck (eris.material.deck)
            "code": any(c.metadata.get("has_code") for c in chunks) or code_lines >= CODE_MIN_LINES,
            "flows": bool(flows(figures)),
            "graphs": config.VISUALS_ENABLED and bool(graphs(figures))}


ENV_MARKERS = {  # the markers each optional environment owns
    "code": {"WRITE_CODE", "HIGHLIGHT", "RUN", "READ_OUTPUT", "OPEN_FILE"},
    "flows": {"FLOW", "FLOW_NEXT", "FLOW_HIGHLIGHT", "OPEN_FLOW"},
    "graphs": {"VISUAL", "VISUAL_SET", "OPEN_VISUAL"},
    "slides": {"SLIDE", "SLIDE_HIGHLIGHT", "SLIDE_CIRCLE"},
}


def describe_environments(env):
    """The environments for a prompt. Diagrams and graphs are both drawn on the Visual board."""
    def visual(parts):
        return "visual (" + " and ".join(parts) + ")"
    names = {"notebook": "notebook", "slides": "slides", "code": "code"}
    on = [names[k] for k in ("notebook", "slides", "code") if env.get(k)]
    off = [names[k] for k in ("slides", "code") if not env.get(k)]
    vis_on = [p for k, p in (("flows", "diagrams with [FLOW]"), ("graphs", "graphs with [VISUAL]")) if env.get(k)]
    vis_off = [p for k, p in (("flows", "diagrams with [FLOW]"), ("graphs", "graphs with [VISUAL]")) if not env.get(k)]
    if vis_on:
        on.append(visual(vis_on))
    if vis_off:
        off.append(visual(vis_off))
    text = "Use: " + ", ".join(on) + "."
    if off:
        text += " Not in this class (the material has none): " + ", ".join(off) + "; never use their markers."
    return text


def env_from_segments(segments):
    """The environments a played script used (the doubt agent may use only these)."""
    names = {s.get("name") for s in segments}
    return {"notebook": True, "slides": bool(names & ENV_MARKERS["slides"]), "code": bool(names & ENV_MARKERS["code"]),
            "flows": bool(names & ENV_MARKERS["flows"]), "graphs": bool(names & ENV_MARKERS["graphs"])}


def lecture_environments(lecture_id, manifest=None, slide_count=None):
    """The environments saved at index time; for a lecture indexed before they existed, a safe guess."""
    from eris import config
    manifest = manifest or config.load_manifest(lecture_id)
    if manifest.get("environments"):
        return manifest["environments"]
    return {"notebook": True, "slides": bool(slide_count), "code": True, "flows": bool(flows(load(lecture_id))),
            "graphs": config.VISUALS_ENABLED and bool(graphs(load(lecture_id)))}


def load(lecture_id):
    """The figures saved by the last index run ([] if none)."""
    import json

    from eris import config
    path = config.lecture_dir(lecture_id) / "figures.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
