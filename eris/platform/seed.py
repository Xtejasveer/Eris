"""Demo data for a pilot, built from the lectures in data/ and the demo topics in templates/demo/: each lecture's teacher (from its persona.md) gets
an account and a course; the lecture becomes a shared lesson in it, and its study material (slides, notes,
worksheets) is posted to the course. Three students join every course. Run with `python main.py seed`; safe to run
again (what exists is kept).

The accounts are demo accounts for local testing only: the sign-in page offers them while ERIS_DEMO_LOGINS is on
(see .env.example). Turn it off and change or delete them before real users sign in.
"""

import json
import re
import shutil
from pathlib import Path

from eris import config
from eris.platform import auth
from eris.platform.db import connect, now, one

DEMO_PASSWORD = "eris-demo-2026"
STUDENTS = [("aarav@eris.test", "Aarav Mehta"), ("diya@eris.test", "Diya Sharma"), ("kabir@eris.test", "Kabir Singh")]
# A teacher and a student with nothing at all (no course, no class), to try every feature from the start: make a
# course, create a lecture, share it, join with the class code and watch it.
BLANK = [("test.teacher@eris.test", "Test Teacher", "teacher"), ("test.student@eris.test", "Test Student", "student")]
# lecture id (a folder in data/), teacher's email, chapter, topic, lesson title and, optionally, the lesson's kind
# (a lecture unless it says "prerequisite"). Name, subject and class come from the lecture's persona.md, so the course
# matches the teacher the lesson speaks as.
LESSONS = [
    ("dp_coin_change", "ananya@eris.test", "Dynamic programming", "Coin change", "The coin change problem"),
    # One topic each, taught in depth (templates/demo/<id>: the slides, a worksheet and the teacher's persona).
    ("kadane_max_subarray", "ananya@eris.test", "Arrays", "Maximum subarray", "Kadane's algorithm"),
    ("projectile_motion", "kavita@eris.test", "Motion in a plane", "Projectile motion", "Projectile motion: why 45° goes farthest"),
    # The same topic taught from the NCERT book pages and the slides, with a program, a diagram and a graph.
    ("projectile_book_demo", "meera@eris.test", "Motion in a plane", "Projectile motion", "Projectile motion from the NCERT book"),
    # One 10-minute lesson per subject, each with its own teacher: the NCERT chapter in book/ (Python has none), slides
    # made for the topic, and for Python the programs in its notes.
    ("history_french_society", "anjali@eris.test", "The French Revolution", "French society in the late 18th century",
     "French society before the Revolution"),
    ("maths_quadratic_factorisation", "arjun@eris.test", "Quadratic Equations", "Solution by factorisation",
     "Solving quadratic equations by factorisation"),
    ("chemistry_carbonyl_properties", "farah@eris.test", "Aldehydes, Ketones and Carboxylic Acids",
     "Physical properties of aldehydes and ketones", "Physical properties of aldehydes and ketones"),
    ("python_while_loop", "vikram@eris.test", "Loops in Python", "The while loop", "The while loop in Python"),
    # Their prerequisites: the groundwork to watch first, in the same topic.
    ("kadane_prereq_arrays", "ananya@eris.test", "Arrays", "Maximum subarray", "Arrays, subarrays and running sums", "prerequisite"),
    ("projectile_prereq_vectors", "kavita@eris.test", "Motion in a plane", "Projectile motion", "Vectors, sine and cosine", "prerequisite"),
]
DEMO_DIR = Path("templates/demo")
# The demo topics' lecture settings: (topic, teaching language). A lecture is 15 minutes, 5 of them spoken; a
# prerequisite 10, 4 of them spoken.
DEMO_TOPICS = {
    "kadane_max_subarray": ("Kadane's algorithm: the maximum subarray sum", "en-IN"),
    "projectile_motion": ("Projectile motion: why a 45 degree throw goes farthest", "en-IN"),
    "projectile_book_demo": ("Projectile motion: NCERT Example 3.8, a program and the range-angle graph", "en-IN"),
    "history_french_society": ("French society before the Revolution: the three estates, taxes and the subsistence crisis", "en-IN"),
    "maths_quadratic_factorisation": ("Solving quadratic equations by factorisation", "en-IN"),
    "chemistry_carbonyl_properties": ("Physical properties of aldehydes and ketones", "en-IN"),
    "python_while_loop": ("The while loop in Python", "en-IN"),
    "kadane_prereq_arrays": ("Arrays, subarrays and running sums", "en-IN"),
    "projectile_prereq_vectors": ("Vectors, sine and cosine", "en-IN"),
}
# Demo lectures taught from textbook pages (material/book.py): the printed pages in their book/ folder, and where the
# theory and the numericals come from.
DEMO_BOOKS = {
    "projectile_book_demo": {"book": {"first": 38, "last": 40}, "focus": {"theory": "both", "numericals": "book"}},
    "history_french_society": {"book": {"first": 4, "last": 5}, "focus": {"theory": "both", "numericals": "both"}},
    "maths_quadratic_factorisation": {"book": {"first": 42, "last": 42}, "focus": {"theory": "both", "numericals": "book"}},
    "chemistry_carbonyl_properties": {"book": {"first": 235, "last": 235}, "focus": {"theory": "both", "numericals": "book"}},
}
MATERIAL_TYPES = {".pptx": "Slides", ".pdf": "Notes", ".docx": "Notes", ".txt": "Notes", ".md": "Notes"}


def demo_emails():
    """Every demo account: the demo lessons' teachers and the demo students."""
    return {e for _, e, *_ in LESSONS} | {e for e, _ in STUDENTS}


def can_generate(user):
    """False for a demo account on the website (config.DEMO_CAN_GENERATE): it may look, teach and edit, not write scripts."""
    return config.DEMO_CAN_GENERATE or (user or {}).get("email") not in demo_emails()


def demo_accounts():
    """The teachers with a ready lesson (physics, history, maths, chemistry, Python) and every seeded student, when
    seeded, for the demo page's one-click sign-in buttons."""
    emails = ("meera@eris.test", "anjali@eris.test", "arjun@eris.test", "farah@eris.test",
              "vikram@eris.test") + tuple(email for email, _ in STUDENTS)
    with connect() as conn:
        rows = [one(conn, "SELECT u.email, u.name, u.role, (SELECT subject FROM courses c WHERE c.teacher_id = u.id "
                          "ORDER BY c.id LIMIT 1) AS subject FROM users u WHERE u.email = ?", e) for e in emails]
    return [{**r, "password": DEMO_PASSWORD} for r in rows if r]


def _persona(lecture_id):
    """Name, Subject, Class and the absence message from the lecture's persona.md."""
    path = config.data_dir(lecture_id) / "persona.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    field = lambda key: (re.search(rf"^{key}:\s*(.+)$", text, re.M) or [None, ""])[1].strip()
    return {"name": field("Name"), "subject": field("Subject"), "class": field("Class"), "message": field("Message to class")}


def _user(email, name, role):
    with connect() as conn:
        row = one(conn, "SELECT id FROM users WHERE email = ?", email)
    if row:
        return row["id"]
    return auth.create_user(email, name, DEMO_PASSWORD, role)["id"]


def _row(conn, sql, insert, *args):
    """The id of the row `sql` finds, else of the row `insert` adds (both take args)."""
    row = one(conn, sql, *args)
    return row["id"] if row else conn.execute(insert, args + (now(),)).lastrowid


def _post_material(conn, course_id, topic_id, lecture_id, title, body):
    """The lecture's study material (the files in data/<lecture>/) as one post, unless it is already there."""
    files = sorted(p for p in config.data_dir(lecture_id).iterdir()
                   if p.suffix.lower() in MATERIAL_TYPES and p.name != "persona.md")  # the persona is the teacher's, not the class's
    if not files or one(conn, "SELECT id FROM posts WHERE course_id = ? AND kind = 'material' AND title = ?", course_id, title):
        return
    from eris.api.server_platform import COURSE_FILES
    post_id = conn.execute("""INSERT INTO posts (course_id, topic_id, kind, title, body, created_at, updated_at)
                              VALUES (?, ?, 'material', ?, ?, ?, ?)""", (course_id, topic_id, title, body, now(), now())).lastrowid
    folder = COURSE_FILES / str(course_id) / "posts" / str(post_id)
    folder.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy(f, folder / f.name)
        conn.execute("INSERT INTO post_files (post_id, name, path, size) VALUES (?, ?, ?, ?)",
                     (post_id, f.name, str(folder / f.name), f.stat().st_size))


# A demo lesson's approved script, saved with its template (templates/demo/<id>/generated/) by `python main.py
# demo-snapshot`, so a fresh install gets ready lessons without generating them. The voice clips are left out (they
# are large and are made again when the lesson is shared), and so are the slide and book pictures (drawn on demand).
SNAPSHOT = "generated"
SNAPSHOT_FILES = ("script.md", "script.json", "lesson.md", "lecture.json", "judge.json", "figures.json", "images.json",
                  "outline.json")
SNAPSHOT_DIRS = ("images", "visuals")


def snapshot(lecture_ids=None):
    """Save each demo lesson's approved script from workspace/ into its template. Returns the lectures saved."""
    saved = []
    for lecture_id in lecture_ids or DEMO_TOPICS:
        src = config.lecture_dir(lecture_id)
        manifest = config.load_manifest(lecture_id) if config.manifest_path(lecture_id).exists() else {}
        if manifest.get("status") not in ("approved", "completed") or not (src / "script.json").exists():
            continue
        out = DEMO_DIR / lecture_id / SNAPSHOT
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        for name in SNAPSHOT_FILES:
            if (src / name).exists():
                shutil.copy(src / name, out / name)
        for name in SNAPSHOT_DIRS:
            if (src / name).is_dir():
                shutil.copytree(src / name, out / name)
        lecture = json.loads((out / "lecture.json").read_text(encoding="utf-8"))
        lecture.pop("owner_id", None)  # the seed gives it to its demo teacher on the new install
        lecture["status"] = "approved"
        (out / "lecture.json").write_text(json.dumps(lecture, indent=2, ensure_ascii=False), encoding="utf-8")
        saved.append(lecture_id)
    return saved


def _install_snapshot(lecture_id):
    """Put a demo lesson's saved script in place (once: a lesson with a script of its own keeps it). True if done."""
    saved = DEMO_DIR / lecture_id / SNAPSHOT
    out = config.lecture_dir(lecture_id)
    if not (saved / "script.json").exists() or (out / "script.json").exists():
        return False
    shutil.copytree(saved, out, dirs_exist_ok=True)
    return True


def _install_demo(lecture_id, kind, platform_topic):
    """A demo topic becomes a lecture: its material and persona in data/, and its saved approved script when it has
    one (else a lecture.json ready to generate). A prerequisite is generated as one for its platform topic (see
    prompts.prerequisite_rule)."""
    if lecture_id not in DEMO_TOPICS or not (DEMO_DIR / lecture_id).is_dir():
        return
    folder = config.data_dir(lecture_id)
    if not folder.exists():
        shutil.copytree(DEMO_DIR / lecture_id, folder, ignore=shutil.ignore_patterns(SNAPSHOT))
    if _install_snapshot(lecture_id):
        print(f"[seed] {lecture_id}: installed its approved script")
        return
    if not config.manifest_path(lecture_id).exists():
        topic, language = DEMO_TOPICS[lecture_id]
        config.lecture_dir(lecture_id)
        pre = kind == "prerequisite"
        config.save_manifest(lecture_id, {"lecture_id": lecture_id, "topic": topic, "duration_min": 10 if pre else 15,
                                          "speaking_min": 4 if pre else 5, "language": language, "status": "new", "kind": kind,
                                          **DEMO_BOOKS.get(lecture_id, {}),
                                          **({"prerequisite_for": platform_topic} if pre else {})})


def run():
    from eris.api.server_platform import _lock_version, _new_code
    from eris.platform.access import stamp_owner
    students = [_user(email, name, "student") for email, name in STUDENTS]
    for email, name, role in BLANK:
        _user(email, name, role)
    for lecture_id, email, chapter, topic, title, *kind in LESSONS:
        kind = kind[0] if kind else "lecture"
        _install_demo(lecture_id, kind, topic)
        if not config.data_dir(lecture_id).exists():
            print(f"[seed] skipped {lecture_id}: not in data/")
            continue
        p = _persona(lecture_id)
        teacher = _user(email, p["name"] or email.split("@")[0].title(), "teacher")
        stamp_owner(lecture_id, teacher)
        subject, year = p["subject"] or title, p["class"]
        with connect() as conn:
            course = one(conn, "SELECT id FROM courses WHERE teacher_id = ? AND subject = ?", teacher, subject)
            course_id = course["id"] if course else conn.execute(
                "INSERT INTO courses (teacher_id, subject, year, code, created_at) VALUES (?, ?, ?, ?, ?)",
                (teacher, subject, year, _new_code(conn), now())).lastrowid
            chapter_id = _row(conn, "SELECT id FROM chapters WHERE course_id = ? AND title = ?",
                              "INSERT INTO chapters (course_id, title, position, created_at) VALUES (?, ?, 1, ?)", course_id, chapter)
            topic_id = _row(conn, "SELECT id FROM topics WHERE chapter_id = ? AND title = ?",
                            "INSERT INTO topics (chapter_id, title, position, created_at) VALUES (?, ?, 1, ?)", chapter_id, topic)
            lesson = one(conn, "SELECT * FROM lessons WHERE lecture_id = ?", lecture_id)
            if not lesson:
                conn.execute("INSERT INTO lessons (topic_id, lecture_id, kind, title, created_at) VALUES (?, ?, ?, ?, ?)",
                             (topic_id, lecture_id, kind, title, now()))
                lesson = one(conn, "SELECT * FROM lessons WHERE lecture_id = ?", lecture_id)
            for s in students:
                conn.execute("INSERT OR IGNORE INTO enrollments (course_id, user_id, joined_at) VALUES (?, ?, ?)", (course_id, s, now()))
            if kind == "prerequisite":
                _post_material(conn, course_id, topic_id, lecture_id, f"Prerequisite material: {topic}",
                               "The groundwork for this topic: slides and a short worksheet. Go through them before the lecture.")
            else:
                _post_material(conn, course_id, topic_id, lecture_id, f"Study material: {topic}",
                               "The slides and notes for this topic. Go through them before or after the lesson.")
            if not one(conn, "SELECT id FROM posts WHERE lesson_id = ? AND kind = 'lesson'", lesson["id"]):
                try:
                    version_id, _ = _lock_version(conn, lesson)
                    conn.execute("""INSERT INTO posts (course_id, topic_id, kind, title, body, lesson_id, version_id, created_at, updated_at)
                                    VALUES (?, ?, 'lesson', ?, ?, ?, ?, ?, ?)""",
                                 (course_id, topic_id, title, p["message"] or "Watch this before our next class.",
                                  lesson["id"], version_id, now(), now()))
                except Exception as e:  # not approved yet: the lesson is in the course, just not shared
                    print(f"[seed] {lecture_id} not shared: {getattr(e, 'detail', e)}")
            code = one(conn, "SELECT code FROM courses WHERE id = ?", course_id)["code"]
        print(f"[seed] {p['name']}: {subject} ({year}), class code {code}")
    print(f"[seed] students: {', '.join(e for e, _ in STUDENTS)}; blank accounts: {', '.join(e for e, _, _ in BLANK)}. "
          "Passwords: see eris/platform/seed.py")
