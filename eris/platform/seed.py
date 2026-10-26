"""Demo data for a pilot, built from the lectures in data/ and the demo topics in templates/demo/: each lecture's teacher (from its persona.md) gets
an account and a course; the lecture becomes a shared lesson in it, and its study material (slides, notes,
worksheets) is posted to the course. Three students join every course. Run with `python main.py seed`; safe to run
again (what exists is kept).

The accounts are demo accounts for local testing only: the sign-in page offers them while ERIS_DEMO_LOGINS is on
(see .env.example). Turn it off and change or delete them before real users sign in.
"""

import re
import shutil
from pathlib import Path

from eris import config
from eris.platform import auth
from eris.platform.db import connect, now, one

DEMO_PASSWORD = "eris-demo-2026"
STUDENTS = [("aarav@eris.test", "Aarav Mehta"), ("diya@eris.test", "Diya Sharma"), ("kabir@eris.test", "Kabir Singh")]
# lecture id (a folder in data/), teacher's email, chapter, topic, lesson title and, optionally, the lesson's kind
# (a lecture unless it says "prerequisite"). Name, subject and class come from the lecture's persona.md, so the course
# matches the teacher the lesson speaks as.
LESSONS = [
    ("dp_coin_change", "ananya@eris.test", "Dynamic programming", "Coin change", "The coin change problem"),
    ("napoleon", "meera@eris.test", "Revolution and empire", "Napoleon Bonaparte", "Napoleon: rise and fall"),
    ("globalisation_stats", "rohan@eris.test", "Presenting data", "Line, bar and pie charts", "Globalisation in numbers"),
    # One topic each, taught in depth (templates/demo/<id>: the slides, a worksheet and the teacher's persona).
    ("kadane_max_subarray", "ananya@eris.test", "Arrays", "Maximum subarray", "Kadane's algorithm"),
    ("india_1991_reforms", "rohan@eris.test", "Globalisation", "India's 1991 reforms", "India's 1991 reforms: how opening up changed trade"),
    ("projectile_motion", "kavita@eris.test", "Motion in a plane", "Projectile motion", "Projectile motion: why 45° goes farthest"),
    # Their prerequisites: the groundwork to watch first, in the same topic.
    ("kadane_prereq_arrays", "ananya@eris.test", "Arrays", "Maximum subarray", "Arrays, subarrays and running sums", "prerequisite"),
    ("india_1991_prereq_basics", "rohan@eris.test", "Globalisation", "India's 1991 reforms", "GDP, trade and exchange rates", "prerequisite"),
    ("projectile_prereq_vectors", "kavita@eris.test", "Motion in a plane", "Projectile motion", "Vectors, sine and cosine", "prerequisite"),
]
DEMO_DIR = Path("templates/demo")
# The demo topics' lecture settings: (topic, teaching language). A lecture is 15 minutes, 5 of them spoken; a
# prerequisite 10, 4 of them spoken.
DEMO_TOPICS = {
    "kadane_max_subarray": ("Kadane's algorithm: the maximum subarray sum", "en-IN"),
    "india_1991_reforms": ("India's 1991 reforms: how opening up changed trade", "en-IN"),
    "projectile_motion": ("Projectile motion: why a 45 degree throw goes farthest", "en-IN"),
    "kadane_prereq_arrays": ("Arrays, subarrays and running sums", "en-IN"),
    "india_1991_prereq_basics": ("GDP, trade and exchange rates", "en-IN"),
    "projectile_prereq_vectors": ("Vectors, sine and cosine", "en-IN"),
}
MATERIAL_TYPES = {".pptx": "Slides", ".pdf": "Notes", ".docx": "Notes", ".txt": "Notes", ".md": "Notes"}


def demo_accounts():
    """The demo accounts that exist, for the sign-in page's one-click demo buttons."""
    emails = list(dict.fromkeys([e for _, e, *_ in LESSONS] + [e for e, _ in STUDENTS]))  # a teacher may have two courses
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


def _install_demo(lecture_id, kind, platform_topic):
    """A demo topic becomes a lecture ready to generate: its material and persona in data/, its lecture.json. A
    prerequisite is generated as one for its platform topic (see prompts.prerequisite_rule)."""
    if lecture_id not in DEMO_TOPICS or not (DEMO_DIR / lecture_id).is_dir():
        return
    folder = config.data_dir(lecture_id)
    if not folder.exists():
        shutil.copytree(DEMO_DIR / lecture_id, folder)
    if not config.manifest_path(lecture_id).exists():
        topic, language = DEMO_TOPICS[lecture_id]
        config.lecture_dir(lecture_id)
        pre = kind == "prerequisite"
        config.save_manifest(lecture_id, {"lecture_id": lecture_id, "topic": topic, "duration_min": 10 if pre else 15,
                                          "speaking_min": 4 if pre else 5, "language": language, "status": "new", "kind": kind,
                                          **({"prerequisite_for": platform_topic} if pre else {})})


def run():
    from eris.api.server_platform import _lock_version, _new_code
    from eris.platform.access import stamp_owner
    students = [_user(email, name, "student") for email, name in STUDENTS]
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
    print(f"[seed] students: {', '.join(e for e, _ in STUDENTS)}. Passwords: see eris/platform/seed.py")
