"""Checks for the textbook markers ([BOOK...], see material/book.py), and the answer check.

Code checks what can be checked exactly: the page is one of the teacher's pages, the words a highlight, underline or
circle points at are printed on it, the worked example is on it. And when the book's printed answer is a quantity
(book.numeric_answer): the final results the notebook works out for the example must be the ones the book prints. An
answer that is a proof, an argument or words is covered and revealed the same way, with nothing for code to check. A script whose results differ goes back to the writer,
so the class never sees "Matches the book" over a wrong answer. Each [BOOK_ANSWER] keeps its results and the ones
that match (args results / matches) for the class.
"""

import re

from eris.material import book

# The value after a line's last "=": a number or a fraction, with its unit ("10.0 m", "20 m/s", "3/4"). An algebraic
# answer ("x = 2a + b") has none: such an example is covered and revealed, but not checked by code.
RESULT_RE = re.compile(r"=\s*(-?\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?(?:\s*[A-Za-z°/^²³\-]+(?:\s*[A-Za-z/^²³\-]+)?)?)\s*$")
# A result given with its rounded value too ("T = 28 / 9.8 = 2.86, about 2.9 s"): the rounded one is the answer, as the
# book prints it.
ROUNDED_RE = re.compile(r"=[^=]*?\b(?:about|approx\.?|approximately|roughly|rounds? to|nearly)\s*[≈~]?\s*"
                        r"(-?\d+(?:\.\d+)?(?:\s*[A-Za-z°/^²³\-]+(?:\s*[A-Za-z/^²³\-]+)?)?)\s*\)?\.?\s*$|"
                        r"[≈~]\s*(-?\d+(?:\.\d+)?(?:\s*[A-Za-z°/^²³\-]+(?:\s*[A-Za-z/^²³\-]+)?)?)\s*\)?\.?\s*$", re.I)


def _notes(segments):
    return [ln.strip(" -•") for s in segments if s.get("name") in ("NOTE", "WRITE") for ln in s["args"]["text"].splitlines()]


def final_results(segments):
    """The final results worked out in these notes: the value after the last "=" of a line ("h = 14 x 14 / 19.6 =
    10.0 m" -> "10.0 m"), unless a later line uses it (then it was a step on the way, like uy = 14 m/s)."""
    lines = _notes(segments)
    out = []
    for i, ln in enumerate(lines):
        r = ROUNDED_RE.search(ln)
        m = RESULT_RE.search(ln)
        if not (r or m):
            continue
        value = " ".join((r.group(1) or r.group(2)).split()) if r else " ".join(m.group(1).split())
        number = book.NUMBER_RE.match(value).group(0)
        later = " ".join(lines[i + 1:])
        if not re.search(rf"(?<![\d.]){re.escape(number)}(?![\d])", later) and value not in out:
            out.append(value)
    return out


def _inside(box, region):
    return box[0] >= region[0] - 0.01 and box[2] <= region[2] + 0.01 and box[1] >= region[1] - 0.01 and box[3] <= region[3] + 0.01


def covered_marks(segments, info):
    """(name, page, text) of every highlight, underline or circle that points at a worked example's printed answer
    while it is still covered (between its [BOOK_EXAMPLE] and [BOOK_ANSWER]): the pen would give the answer away."""
    out, covered = set(), {}
    for seg in segments:
        name, a = seg.get("name", ""), seg.get("args", {})
        page = (info or {}).get("pages", {}).get(str(a.get("page")))
        if not name.startswith("BOOK") or page is None:
            continue
        ex = book.find_example(info, a["page"], a.get("name")) if name in ("BOOK_EXAMPLE", "BOOK_ANSWER") else None
        if name == "BOOK_EXAMPLE" and ex:
            covered[ex["name"]] = (str(a["page"]), ex["answer"])
        elif name == "BOOK_ANSWER" and ex:
            covered.pop(ex["name"], None)
        elif name in ("BOOK_HIGHLIGHT", "BOOK_UNDERLINE", "BOOK_CIRCLE"):
            boxes = book.find_words(page, a["text"])
            if any(pg == str(a["page"]) and any(_inside(b, r) for b in boxes for r in regions)
                   for pg, regions in covered.values()):
                out.add((name, str(a["page"]), a["text"]))
    return out


def book_errors(segments, info):
    """Problems with the book markers: [str]. info: book.load() (None: the lecture has no book)."""
    used = [s for s in segments if s.get("name", "").startswith("BOOK")]
    if not used:
        return []
    if not info:
        return ["this class has no textbook pages, so remove every [BOOK...] marker"]
    pages = info["pages"]
    listed = ", ".join(sorted(pages, key=int))
    errors, open_examples = [], {}
    for name, page, text in sorted(covered_marks(segments, info)):
        errors.append(f'[{name} page={page} text="{text}"] points at the book\'s printed answer while it is still covered: '
                      "mark the notebook instead, and point at the book's answer only after [BOOK_ANSWER]")
    for i, seg in enumerate(segments):
        name, a = seg.get("name", ""), seg.get("args", {})
        if not name.startswith("BOOK"):
            continue
        page = pages.get(str(a.get("page")))
        if page is None:
            errors.append(f"[{name} page={a.get('page')}]: the teacher gave only book pages {listed}")
            continue
        if name in ("BOOK_HIGHLIGHT", "BOOK_UNDERLINE", "BOOK_CIRCLE") and not book.find_words(page, a["text"]):
            errors.append(f'[{name} page={a["page"]} text="{a["text"]}"]: these words are not printed on book page '
                          f"{a['page']}; quote a few words exactly as the page prints them")
        if name in ("BOOK_EXAMPLE", "BOOK_ANSWER"):
            ex = book.find_example(info, a["page"], a["name"])
            if not ex:
                here = ", ".join(f'"{e["name"]}"' for e in page["examples"]) or "none"
                errors.append(f'[{name} page={a["page"]} name="{a["name"]}"]: no such worked example on that page '
                              f"(examples there: {here})")
                continue
            if name == "BOOK_EXAMPLE":
                open_examples[ex["name"]] = i
                continue
            if ex["name"] not in open_examples:
                errors.append(f'[BOOK_ANSWER name="{ex["name"]}"] comes before its [BOOK_EXAMPLE]: show the example '
                              "first, solve it in the notebook, then reveal the answer")
                continue
            if not ex["answer"]:
                errors.append(f'[BOOK_ANSWER name="{ex["name"]}"]: the book prints no answer for it on page '
                              f"{a['page']}; remove this [BOOK_ANSWER]")
                continue
            results = final_results(segments[open_examples.pop(ex["name"]):i])
            if not book.numeric_answer(ex["answer_text"]):
                continue  # a proof or words: revealed for the class to compare, nothing to check by code
            if not results:
                errors.append(f'"{ex["name"]}": write each final result in the notebook as "<quantity> = <working> = '
                              '<value> <unit>" before [BOOK_ANSWER], so it can be checked against the book')
                continue
            wrong = [r for r in results if r not in book.matches(results, ex["answer_text"])]
            if wrong:
                errors.append(f'"{ex["name"]}": the notebook\'s result(s) {", ".join(wrong)} are not in the book\'s '
                              f'printed answer ({ex["answer_text"][:300]}). Redo the working so every final result '
                              "matches the book (a step on the way is fine once a later line uses it)")
    return errors


def drop_bad_book(text, info):
    """Last resort (the writer did not fix them): remove book markers that can't work. A highlight, underline or
    circle on words not on the page goes, as does an answer the notebook doesn't match (its page stays covered
    until the next page or slide). Returns (text, [what was dropped])."""
    from eris.generate.script_parser import parse_line_marker, parse_script
    segments, _ = parse_script(text)
    bad_answers = {m.group(1).lower() for e in book_errors(segments, info)
                   if (m := re.match(r'^(?:\[BOOK_ANSWER name=)?"([^"]+)"', e))}
    covered = covered_marks(segments, info)
    out, dropped = [], []
    for line in text.splitlines():
        marker = parse_line_marker(line)
        name, a = marker if marker else ("", {})
        if name.startswith("BOOK"):
            page = (info or {}).get("pages", {}).get(str(a.get("page")))
            bad = (page is None
                   or (name in ("BOOK_HIGHLIGHT", "BOOK_UNDERLINE", "BOOK_CIRCLE") and not book.find_words(page, a.get("text", "")))
                   or (name in ("BOOK_EXAMPLE", "BOOK_ANSWER") and not book.find_example(info, a.get("page"), a.get("name")))
                   or (name == "BOOK_ANSWER" and " ".join(str(a.get("name")).split()).lower() in bad_answers)
                   or (name, str(a.get("page")), a.get("text")) in covered)
            if bad:
                dropped.append(line.strip())
                continue
        out.append(line)
    return "\n".join(out), dropped


def mark_answers(segments, info):
    """Give each [BOOK_ANSWER] its notebook results and the ones the book's answer matches, for the class."""
    if not info:
        return segments
    start = {}
    for i, seg in enumerate(segments):
        name, a = seg.get("name"), seg.get("args", {})
        if name == "BOOK_EXAMPLE":
            start[" ".join(str(a.get("name")).split()).lower()] = i
        elif name == "BOOK_ANSWER":
            ex = book.find_example(info, a.get("page"), a.get("name"))
            at = start.get(" ".join(str(a.get("name")).split()).lower())
            if ex and at is not None:
                results = final_results(segments[at:i]) if book.numeric_answer(ex["answer_text"]) else []
                a["results"], a["matches"] = results, book.matches(results, ex["answer_text"])  # no chip without matches
    return segments
