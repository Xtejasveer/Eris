"""Interactive visuals: the script describes one in a [VISUAL] block, a model builds it as a small HTML
fragment, code checks it, and the class page shows it in a sandboxed frame next to the notebook, slides
and code. The teacher moves its controls with [VISUAL_SET] (in the script and in doubt answers).

The model writes only the picture and the control handlers; the control panel, the messaging and the
safety settings (no network, no same-origin access) come from web/js/visual/runtime.js and wrap_document,
so every visual looks and behaves the same way.
"""

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import config
from visual_controls import describe_control

RUNTIME_JS = Path(__file__).parent / "web" / "js" / "visual" / "runtime.js"
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}-[0-9a-f]{8}$")
VISUAL_MARKERS = {"VISUAL", "VISUAL_SET", "OPEN_VISUAL"}
FENCE_RE = re.compile(r"^```[a-z]*\s*|\s*```$", re.I)
SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.I | re.S)
# Things a visual may not do; the frame's sandbox and CSP block them anyway, but the builder gets told.
FORBIDDEN = [
    (re.compile(r"<script[^>]*\bsrc\s*=", re.I), "no <script src>: write all code inline, without libraries"),
    (re.compile(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""", re.I), "no links or images from the web"),
    (re.compile(r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\b"), "no network calls"),
    (re.compile(r"\b(?:localStorage|sessionStorage|indexedDB|document\.cookie)\b"), "no storage"),
    (re.compile(r"\b(?:alert|confirm|prompt)\s*\("), "no alert, confirm or prompt"),
    (re.compile(r"<input\b(?![^>]*type\s*=\s*[\"']?(?:range|checkbox|radio))", re.I), "no text inputs: the controls panel is made for you"),
    (re.compile(r"\bimport\s*\(|^\s*import\s", re.M), "no imports"),
]
MAX_CHARS = 30000

BASE_CSS = """
:root { --bg:#fbfaf7; --panel:#ffffff; --ink:#1b1c21; --muted:#74757e; --line:#e2ded4; --accent:#2d5be3;
  --accent-soft:#e6ecfd; --good:#17885d; --bad:#c93a3a; --warn:#b96a12; --violet:#6d47d9; --marker:#ffe066;
  --font:"Inter",system-ui,-apple-system,"Segoe UI",sans-serif; --mono:"JetBrains Mono",ui-monospace,Menlo,monospace; }
* { box-sizing:border-box; }
html, body { margin:0; height:100%; background:var(--bg); color:var(--ink); font:16px/1.4 var(--font); overflow:hidden; }
body { display:flex; flex-direction:column; }
#stage { position:relative; flex:1; min-height:0; display:flex; align-items:center; justify-content:center; padding:12px; }
#stage > svg { width:100%; height:100%; display:block; }
#stage svg text { font-family:var(--font); fill:var(--ink); }
#visual-controls { display:flex; flex-wrap:wrap; gap:10px 18px; align-items:center; padding:10px 16px;
  background:var(--panel); border-top:1px solid var(--line); }
.vc { display:inline-flex; align-items:center; gap:8px; padding:4px 6px; border-radius:9px; transition:background .3s, box-shadow .3s; }
.vc-label { font-size:13px; font-weight:600; color:var(--muted); }
.vc button { font:inherit; font-size:14px; border:1px solid var(--line); background:#fff; color:var(--ink);
  border-radius:8px; padding:6px 14px; cursor:pointer; transition:transform .12s, background .2s; }
.vc button:hover { background:var(--accent-soft); }
.vc-btn { background:var(--accent) !important; color:#fff !important; border-color:var(--accent) !important; font-weight:600; }
.vc-btn.vc-press { transform:scale(.93); }
.vc-toggle[aria-pressed="true"], .vc-opt[aria-pressed="true"] { background:var(--accent-soft); border-color:var(--accent); color:var(--accent); font-weight:600; }
.vc-seg { display:inline-flex; gap:4px; }
.vc input[type=range] { width:150px; accent-color:var(--accent); }
.vc-out { min-width:2.5em; font:600 14px var(--mono); color:var(--accent); }
.vc-driven { animation:vc-driven 1.4s ease-out; }
@keyframes vc-driven { 0% { background:var(--marker); box-shadow:0 0 0 3px var(--marker); } 100% { background:transparent; box-shadow:0 0 0 0 transparent; } }
"""
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
       "img-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'")


def visual_key(args):
    """A file name that changes whenever the description or controls change (so edits rebuild it)."""
    digest = hashlib.sha1(json.dumps([args["title"], args["brief"], args["controls"]],
                                     sort_keys=True).encode()).hexdigest()[:8]
    return f"{args['id']}-{digest}"


def visuals_dir(lecture_id):
    return config.lecture_dir(lecture_id) / "visuals"


def load_visual(lecture_id, key):
    if not KEY_RE.match(key):
        return None
    path = visuals_dir(lecture_id) / f"{key}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# ---------- checks (no LLM) ----------

def clean_fragment(text):
    """The model's reply as an HTML fragment: no fences, and the inside of <body> if it wrote a whole page."""
    text = FENCE_RE.sub("", text.strip()).strip()
    if re.search(r"<body\b", text, re.I):
        styles = "".join(re.findall(r"<style\b.*?</style>", text, re.I | re.S))
        body = re.search(r"<body\b[^>]*>(.*?)(?:</body>|$)", text, re.I | re.S).group(1)
        text = styles + body
    text = re.sub(r"</?(?:html|head|body)\b[^>]*>|<!doctype[^>]*>|<meta\b[^>]*>|<title>.*?</title>", "", text, flags=re.I | re.S)
    return text.strip()


def _syntax_problems(scripts):
    """Ask node to check the JavaScript syntax (skipped when node is not installed)."""
    node = shutil.which("node")
    if not node or not scripts:
        return []
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write("\n;\n".join(scripts))
        path = f.name
    try:
        res = subprocess.run([node, "--check", path], capture_output=True, text=True, timeout=15)
    except Exception:
        return []
    finally:
        Path(path).unlink(missing_ok=True)
    if res.returncode == 0:
        return []
    lines = [ln for ln in res.stderr.splitlines() if ln.strip() and not ln.startswith(("    at ", "Node.js"))]
    return ["JavaScript syntax error: " + " | ".join(lines[1:4] or lines[:3])[:300]]


def check_fragment(html, controls):
    """Problems with a built visual ([] = fine)."""
    problems = []
    if len(html) > MAX_CHARS:
        problems.append(f"too long ({len(html)} characters); keep it under {MAX_CHARS // 1000}k, about 200 lines")
    scripts = [body for attrs, body in SCRIPT_RE.findall(html) if "src" not in attrs.lower()]
    code = "\n".join(scripts)
    if not code.strip():
        problems.append("there is no <script>: the visual must draw itself and register its controls")
    for pattern, message in FORBIDDEN:
        if pattern.search(html):
            problems.append(message)
    for c in controls:
        if not re.search(r"""Visual\.on\(\s*["'`]""" + re.escape(c["name"]) + r"""["'`]""", code):
            problems.append(f'control "{c["name"]}" has no handler: add Visual.on("{c["name"]}", ...)')
    if "Visual.state(" not in code:
        problems.append("call Visual.state(\"...\") after drawing and after every change")
    problems += _syntax_problems(scripts)
    return problems


def wrap_document(visual):
    """The full page served into the class frame: CSP, theme, controls, runtime, then the model's fragment."""
    controls = json.dumps(visual["controls"]).replace("</", "<\\/")
    runtime = RUNTIME_JS.read_text(encoding="utf-8")
    title = re.sub(r"[<>&\"]", "", visual.get("title", "Visual"))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{BASE_CSS}</style>
<script>window.__VISUAL_CONTROLS__ = {controls};</script>
<script>{runtime}</script>
</head><body>
<div id="stage">
{visual["html"]}
</div>
<div id="visual-controls" aria-label="Visual controls"></div>
<script>Visual._start();</script>
</body></html>"""


# ---------- building (LLM) ----------

_model = None


def _ask_model(prompt):
    global _model
    from langchain.chat_models import init_chat_model
    if _model is None:
        _model = init_chat_model(f"openrouter:{config.VISUAL_MODEL}", temperature=0.2,
                                 request_timeout=config.VISUAL_TIMEOUT_S, max_retries=1)
    reply = _model.invoke(prompt)
    content = reply.content
    if isinstance(content, list):  # some providers return content parts
        content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return content or ""


def build_visual(topic, args):
    """Build one visual; returns (visual dict, None) or (None, reason). The builder gets its problems back
    and tries again, up to VISUAL_BUILD_ATTEMPTS times."""
    from prompts import visual_prompt
    controls_text = "\n".join(f"- {describe_control(c)}" for c in args["controls"])
    feedback = ""
    problems = ["not built"]
    for attempt in range(1, config.VISUAL_BUILD_ATTEMPTS + 1):
        try:
            html = clean_fragment(_ask_model(visual_prompt(topic, args["title"], args["brief"], controls_text, feedback)))
        except Exception as e:  # e.g. a timeout: try again, the next request usually works
            problems = [f"the visual model failed: {e}"]
            print(f"[visual] '{args['id']}' attempt {attempt}: {problems[0]}")
            continue
        problems = check_fragment(html, args["controls"])
        if not problems:
            print(f"[visual] built '{args['id']}' (attempt {attempt}, {len(html)} chars)")
            return {"id": args["id"], "title": args["title"], "brief": args["brief"],
                    "controls": args["controls"], "html": html, "model": config.VISUAL_MODEL}, None
        print(f"[visual] '{args['id']}' attempt {attempt}: {'; '.join(problems)}")
        feedback = "\n".join(f"- {p}" for p in problems)
    return None, "; ".join(problems)


def ensure_visuals(segments, lecture_id, topic, limit=None):
    """Build (or reuse) every [VISUAL] in `segments` and set its args["key"]. Returns [(id, reason)] for
    the visuals that could not be built, so the caller can remove them."""
    wanted = [s for s in segments if s.get("name") == "VISUAL"]
    failed = []
    if limit is not None and len(wanted) > limit:
        failed += [(s["args"]["id"], f"more than {limit} visuals") for s in wanted[limit:]]
        wanted = wanted[:limit]
    if not config.VISUALS_ENABLED:
        return failed + [(s["args"]["id"], "visuals are turned off (VISUALS_ENABLED=false)") for s in wanted]
    folder = visuals_dir(lecture_id)
    folder.mkdir(parents=True, exist_ok=True)
    todo = []
    for seg in wanted:
        seg["args"]["key"] = visual_key(seg["args"])
        if not (folder / f"{seg['args']['key']}.json").exists():
            todo.append(seg)
    if todo:
        print(f"[visual] building {len(todo)} visual(s) with {config.VISUAL_MODEL} ...")
        with ThreadPoolExecutor(max_workers=min(4, len(todo))) as pool:
            results = list(pool.map(lambda s: build_visual(topic, s["args"]), todo))
        for seg, (visual, reason) in zip(todo, results):
            if visual is None:
                failed.append((seg["args"]["id"], reason))
                seg["args"].pop("key", None)
            else:
                (folder / f"{seg['args']['key']}.json").write_text(json.dumps(visual, indent=2), encoding="utf-8")
    return failed


def drop_visual_segments(segments, ids):
    """Remove these visuals and every [VISUAL_SET]/[OPEN_VISUAL] that uses them (the narration stays)."""
    ids = set(ids)
    return [s for s in segments if not (s.get("name") in VISUAL_MARKERS and s["args"].get("id") in ids)]
