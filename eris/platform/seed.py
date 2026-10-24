"""Demo data for a pilot, built from the lectures already in data/: each lecture's teacher (from its persona.md) gets
an account and a course; the lecture becomes a shared lesson in it, and its study material (slides, notes,
worksheets) is posted to the course. Three students join every course. Run with `python main.py seed`; safe to run
again (what exists is kept).

The accounts are demo accounts for local testing only: the sign-in page offers them while ERIS_DEMO_LOGINS is on
(see .env.example). Turn it off and change or delete them before real users sign in.
"""

import re
import shutil

from eris import config
from eris.platform import auth
from eris.platform.db import connect, now, one

DEMO_PASSWORD = "eris-demo-2026"
STUDENTS = [("aarav@eris.test", "Aarav Mehta"), ("diya@eris.test", "Diya Sharma"), ("kabir@eris.test", "Kabir Singh")]
# lecture id (a folder in data/), teacher's email, chapter, topic, lesson title. Name, subject and class come from
# the lecture's persona.md, so the course matches the teacher the lesson speaks as.
LESSONS = [
    ("dp_coin_change", "ananya@eris.test", "Dynamic programming", "Coin change", "The coin change problem"),
    ("napoleon", "meera@eris.test", "Revolution and empire", "Napoleon Bonaparte", "Napoleon: rise and fall"),
    ("globalisation_stats", "rohan@eris.test", "Presenting data", "Line, bar and pie charts", "Globalisation in numbers"),
]
MATERIAL_TYPES = {".pptx": "Slides", ".pdf": "Notes", ".docx": "Notes", ".txt": "Notes", ".md": "Notes"}


def demo_accounts():
    """The demo accounts that exist, for the sign-in page's one-click demo buttons."""
    emails = [e for _, e, *_ in LESSONS] + [e for e, _ in STUDENTS]
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


def run():
    from eris.api.server_platform import _lock_version, _new_code
    students = [_user(email, name, "student") for email, name in STUDENTS]
    for lecture_id, email, chapter, topic, title in LESSONS:
        if not config.data_dir(lecture_id).exists():
            print(f"[seed] skipped {lecture_id}: not in data/")
            continue
        p = _persona(lecture_id)
        teacher = _user(email, p["name"] or email.split("@")[0].title(), "teacher")
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
                conn.execute("INSERT INTO lessons (topic_id, lecture_id, kind, title, created_at) VALUES (?, ?, 'lecture', ?, ?)",
                             (topic_id, lecture_id, title, now()))
                lesson = one(conn, "SELECT * FROM lessons WHERE lecture_id = ?", lecture_id)
            for s in students:
                conn.execute("INSERT OR IGNORE INTO enrollments (course_id, user_id, joined_at) VALUES (?, ?, ?)", (course_id, s, now()))
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
