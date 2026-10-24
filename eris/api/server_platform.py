"""Course platform routes: sign-in, courses and class codes, chapters and topics, lessons, sharing (lessons and
material), each student's lesson session (a locked script version), progress, attendance and doubt logs.

Attendance: a student is present for a shared lesson once every spoken line of it has been played on their device
(100%). Lines are counted by the player (only while the tab is visible) and merged here; doubt answers don't count.
"""

import json
import re
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from eris import config
from eris.platform import access, auth
from eris.platform.db import all_rows, connect, loads, now, one

router = APIRouter(prefix="/api")

VERSIONS_DIR = Path("workspace/versions")
COURSE_FILES = Path("workspace/courses")
MAX_FILE_MB = 25
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I: codes are read aloud and typed


def _newer(path, stamp):
    """True when the file was written after the (UTC) time stamp, by more than a few seconds."""
    written = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return written > datetime.fromisoformat(stamp) + timedelta(seconds=5)


def _manifest(lecture_id):
    path = config.manifest_path(lecture_id)
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        return {}


# ---------- sign-in ----------

class Signup(BaseModel):
    name: str
    email: str
    password: str
    role: str


class Login(BaseModel):
    email: str
    password: str


@router.post("/auth/signup")
def signup(body: Signup, response: Response):
    try:
        user = auth.create_user(body.email, body.name, body.password, body.role)
    except ValueError as e:
        raise HTTPException(400, str(e))
    auth.set_cookie(response, auth.new_session(user["id"]))
    return user


@router.post("/auth/login")
def login(body: Login, response: Response):
    user = auth.check_login(body.email, body.password)
    if not user:
        raise HTTPException(401, "Wrong email or password")
    auth.set_cookie(response, auth.new_session(user["id"]))
    return user


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    auth.end_session(request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/demo")
def demo_logins():
    """The demo accounts the sign-in page offers (python main.py seed), while ERIS_DEMO_LOGINS is on."""
    if not config.DEMO_LOGINS:
        return []
    from eris.platform.seed import demo_accounts
    return demo_accounts()


@router.get("/auth/me")
def me(request: Request):
    return auth.require_user(request)


# ---------- courses ----------

def _new_code(conn):
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not one(conn, "SELECT id FROM courses WHERE code = ?", code):
            return code


class CourseIn(BaseModel):
    subject: str
    year: str = ""


@router.get("/courses")
def list_courses(request: Request):
    user = auth.require_user(request)
    with connect() as conn:
        if user["role"] == "teacher":
            rows = all_rows(conn, """
                SELECT c.*, (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id) AS students,
                       (SELECT COUNT(*) FROM lessons l JOIN topics t ON t.id = l.topic_id
                        JOIN chapters ch ON ch.id = t.chapter_id WHERE ch.course_id = c.id) AS lessons
                FROM courses c WHERE c.teacher_id = ? ORDER BY c.created_at""", user["id"])
        else:
            rows = all_rows(conn, """
                SELECT c.id, c.subject, c.year, c.created_at, u.name AS teacher,
                       (SELECT COUNT(*) FROM posts p WHERE p.course_id = c.id AND p.kind = 'lesson'
                        AND NOT EXISTS (SELECT 1 FROM progress pr WHERE pr.post_id = p.id AND pr.user_id = ?
                                        AND pr.completed_at IS NOT NULL)) AS to_watch
                FROM enrollments e JOIN courses c ON c.id = e.course_id JOIN users u ON u.id = c.teacher_id
                WHERE e.user_id = ? ORDER BY e.joined_at""", user["id"], user["id"])
    return rows


@router.post("/courses")
def create_course(body: CourseIn, request: Request):
    user = auth.require_teacher(request)
    if not body.subject.strip():
        raise HTTPException(400, "Enter the subject")
    with connect() as conn:
        cur = conn.execute("INSERT INTO courses (teacher_id, subject, year, code, created_at) VALUES (?, ?, ?, ?, ?)",
                           (user["id"], body.subject.strip(), body.year.strip(), _new_code(conn), now()))
        return one(conn, "SELECT * FROM courses WHERE id = ?", cur.lastrowid)


@router.put("/courses/{course_id}")
def update_course(course_id: int, body: CourseIn, request: Request):
    access.need_course(auth.require_teacher(request), course_id, teacher=True)
    with connect() as conn:
        conn.execute("UPDATE courses SET subject = ?, year = ? WHERE id = ?", (body.subject.strip(), body.year.strip(), course_id))
    return {"ok": True}


@router.post("/courses/{course_id}/code")
def new_course_code(course_id: int, request: Request):
    access.need_course(auth.require_teacher(request), course_id, teacher=True)
    with connect() as conn:
        code = _new_code(conn)
        conn.execute("UPDATE courses SET code = ? WHERE id = ?", (code, course_id))
    return {"code": code}


class JoinIn(BaseModel):
    code: str


@router.post("/join")
def join_course(body: JoinIn, request: Request):
    user = auth.require_user(request)
    if user["role"] != "student":
        raise HTTPException(403, "Teachers create courses; students join them")
    code = re.sub(r"[^A-Za-z0-9]", "", body.code).upper()
    with connect() as conn:
        course = one(conn, "SELECT id, subject, year FROM courses WHERE code = ?", code)
        if not course:
            raise HTTPException(404, "No course has this code. Check it with your teacher.")
        conn.execute("INSERT OR IGNORE INTO enrollments (course_id, user_id, joined_at) VALUES (?, ?, ?)",
                     (course["id"], user["id"], now()))
    return course


def _progress_of(conn, user_id, post):
    """{percent, completed, started, last_index} of one student on one shared lesson (its current version)."""
    rows = all_rows(conn, "SELECT * FROM progress WHERE user_id = ? AND post_id = ?", user_id, post["id"])
    completed = any(r["completed_at"] for r in rows)
    current = next((r for r in rows if r["version_id"] == post["version_id"]), None)
    say_count = post.get("say_count") or 1
    played = len(loads(current["played"], [])) if current else 0
    return {"percent": 100 if completed else min(99, round(100 * played / say_count)), "completed": completed,
            "started": bool(rows), "last_index": current["last_index"] if current else 0,
            "updated_at": max((r["updated_at"] for r in rows), default=None)}


def _post_view(conn, post, user, role):
    view = {k: post[k] for k in ("id", "kind", "title", "body", "topic_id", "due_at", "created_at", "updated_at")}
    view["topic_title"] = post.get("topic_title")
    view["files"] = all_rows(conn, "SELECT id, name, size FROM post_files WHERE post_id = ? ORDER BY id", post["id"])
    if post["kind"] == "lesson":
        view["lesson"] = {"id": post["lesson_id"], "kind": post["lesson_kind"], "lecture_id": post["lecture_id"]}
        view["version"] = {"id": post["version_id"], "number": post["version_number"], "say_count": post["say_count"]}
        if role == "student":
            view["my_progress"] = _progress_of(conn, user["id"], post)
        else:
            students = [r["user_id"] for r in all_rows(conn, "SELECT user_id FROM enrollments WHERE course_id = ?", post["course_id"])]
            present = sum(1 for s in students if one(conn, "SELECT 1 AS x FROM progress WHERE user_id = ? AND post_id = ? "
                                                           "AND completed_at IS NOT NULL", s, post["id"]))
            started = sum(1 for s in students if one(conn, "SELECT 1 AS x FROM progress WHERE user_id = ? AND post_id = ?", s, post["id"]))
            view["attendance"] = {"present": present, "started": started, "total": len(students)}
    return view


POSTS_SQL = """
SELECT p.*, t.title AS topic_title, l.kind AS lesson_kind, l.lecture_id, v.number AS version_number, v.say_count
FROM posts p LEFT JOIN topics t ON t.id = p.topic_id LEFT JOIN lessons l ON l.id = p.lesson_id
LEFT JOIN versions v ON v.id = p.version_id"""


@router.get("/courses/{course_id}")
def get_course(course_id: int, request: Request):
    user = auth.require_user(request)
    role = access.need_course(user, course_id)
    with connect() as conn:
        course = one(conn, "SELECT c.*, u.name AS teacher_name FROM courses c JOIN users u ON u.id = c.teacher_id "
                           "WHERE c.id = ?", course_id)
        posts = all_rows(conn, POSTS_SQL + " WHERE p.course_id = ? ORDER BY p.created_at DESC", course_id)
        shared = {p["lesson_id"]: p for p in posts if p["kind"] == "lesson"}
        chapters = all_rows(conn, "SELECT id, title FROM chapters WHERE course_id = ? ORDER BY position, id", course_id)
        for ch in chapters:
            ch["topics"] = all_rows(conn, "SELECT id, title FROM topics WHERE chapter_id = ? ORDER BY position, id", ch["id"])
            for t in ch["topics"]:
                lessons = all_rows(conn, "SELECT * FROM lessons WHERE topic_id = ? ORDER BY id", t["id"])
                if role == "student":  # students see only what was shared
                    lessons = [l for l in lessons if l["id"] in shared]
                for l in lessons:
                    post = shared.get(l["id"])
                    l["post_id"] = post["id"] if post else None
                    if role == "teacher":
                        m = _manifest(l["lecture_id"])
                        l["status"] = m.get("status", "new")
                        script = config.lecture_dir(l["lecture_id"]) / "script.json"
                        version = one(conn, "SELECT created_at FROM versions WHERE id = ?", post["version_id"]) if post else None
                        # A newer approved script than the shared copy: the teacher can share the new version.
                        l["update_available"] = bool(post and version and l["status"] in ("approved", "completed")
                                                     and script.exists() and _newer(script, version["created_at"]))
                        l["versions"] = one(conn, "SELECT COUNT(*) AS n FROM versions WHERE lesson_id = ?", l["id"])["n"]
                t["lessons"] = lessons
        people = all_rows(conn, """SELECT u.id, u.name, u.email, e.joined_at FROM enrollments e JOIN users u ON u.id = e.user_id
                                   WHERE e.course_id = ? ORDER BY u.name""", course_id)
        result = {"id": course["id"], "subject": course["subject"], "year": course["year"], "role": role,
                  "teacher": {"name": course["teacher_name"]}, "chapters": chapters,
                  "posts": [_post_view(conn, p, user, role) for p in posts],
                  "students": people if role == "teacher" else [{"name": p["name"]} for p in people]}
        if role == "teacher":
            result["code"] = course["code"]
    return result


# ---------- chapters and topics ----------

class TitleIn(BaseModel):
    title: str


def _chapter(conn, chapter_id):
    row = one(conn, "SELECT * FROM chapters WHERE id = ?", chapter_id)
    if not row:
        raise HTTPException(404, "Chapter not found")
    return row


def _topic(conn, topic_id):
    row = one(conn, "SELECT t.*, ch.course_id FROM topics t JOIN chapters ch ON ch.id = t.chapter_id WHERE t.id = ?", topic_id)
    if not row:
        raise HTTPException(404, "Topic not found")
    return row


def _title(body):
    if not body.title.strip():
        raise HTTPException(400, "Enter a title")
    return body.title.strip()[:200]


@router.post("/courses/{course_id}/chapters")
def add_chapter(course_id: int, body: TitleIn, request: Request):
    access.need_course(auth.require_teacher(request), course_id, teacher=True)
    with connect() as conn:
        pos = (one(conn, "SELECT MAX(position) AS m FROM chapters WHERE course_id = ?", course_id)["m"] or 0) + 1
        cur = conn.execute("INSERT INTO chapters (course_id, title, position, created_at) VALUES (?, ?, ?, ?)",
                           (course_id, _title(body), pos, now()))
    return {"id": cur.lastrowid}


@router.put("/chapters/{chapter_id}")
def rename_chapter(chapter_id: int, body: TitleIn, request: Request):
    user = auth.require_teacher(request)
    with connect() as conn:
        access.need_course(user, _chapter(conn, chapter_id)["course_id"], teacher=True)
        conn.execute("UPDATE chapters SET title = ? WHERE id = ?", (_title(body), chapter_id))
    return {"ok": True}


@router.delete("/chapters/{chapter_id}")
def delete_chapter(chapter_id: int, request: Request):
    user = auth.require_teacher(request)
    with connect() as conn:
        access.need_course(user, _chapter(conn, chapter_id)["course_id"], teacher=True)
        conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
    return {"ok": True}


@router.post("/chapters/{chapter_id}/topics")
def add_topic(chapter_id: int, body: TitleIn, request: Request):
    user = auth.require_teacher(request)
    with connect() as conn:
        access.need_course(user, _chapter(conn, chapter_id)["course_id"], teacher=True)
        pos = (one(conn, "SELECT MAX(position) AS m FROM topics WHERE chapter_id = ?", chapter_id)["m"] or 0) + 1
        cur = conn.execute("INSERT INTO topics (chapter_id, title, position, created_at) VALUES (?, ?, ?, ?)",
                           (chapter_id, _title(body), pos, now()))
    return {"id": cur.lastrowid}


@router.put("/topics/{topic_id}")
def rename_topic(topic_id: int, body: TitleIn, request: Request):
    user = auth.require_teacher(request)
    with connect() as conn:
        access.need_course(user, _topic(conn, topic_id)["course_id"], teacher=True)
        conn.execute("UPDATE topics SET title = ? WHERE id = ?", (_title(body), topic_id))
    return {"ok": True}


@router.delete("/topics/{topic_id}")
def delete_topic(topic_id: int, request: Request):
    user = auth.require_teacher(request)
    with connect() as conn:
        access.need_course(user, _topic(conn, topic_id)["course_id"], teacher=True)
        conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
    return {"ok": True}


# ---------- lessons: an Eris lecture inside a topic ----------

class LessonIn(BaseModel):
    kind: str = "lecture"
    title: str
    language: str = ""
    duration_min: int = 0
    speaking_min: int = 0


def _slug(text, n=36):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:n].strip("_") or "lesson"


@router.post("/topics/{topic_id}/lessons")
def add_lesson(topic_id: int, body: LessonIn, request: Request):
    """A new lesson: a new lecture (folder + lecture.json), opened in Studio next. A prerequisite lesson is generated
    as a prerequisite for this topic (see prompts.prerequisite_rule)."""
    user = auth.require_teacher(request)
    if body.kind not in ("lecture", "prerequisite"):
        raise HTTPException(400, "Lesson kind is lecture or prerequisite")
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Enter what this lesson teaches")
    with connect() as conn:
        topic = _topic(conn, topic_id)
        access.need_course(user, topic["course_id"], teacher=True)
        course = one(conn, "SELECT subject, year FROM courses WHERE id = ?", topic["course_id"])
        lecture_id = f"{_slug(course['subject'], 16)}_{_slug(title, 30)}_{secrets.token_hex(3)}"
        total = body.duration_min or config.LECTURE_DURATION_MIN
        speaking = body.speaking_min or config.default_speaking_min(total)
        if not (5 <= total <= 120 and 1 <= speaking <= total):
            raise HTTPException(400, "Total time must be 5-120 minutes and speaking time 1 minute up to the total")
        language = body.language if body.language in config.LANGUAGES else config.DEFAULT_LANGUAGE
        manifest = {"lecture_id": lecture_id, "topic": title, "duration_min": total, "speaking_min": speaking,
                    "language": language, "status": "new", "kind": body.kind,
                    "course_label": " · ".join(x for x in (course["subject"], course["year"]) if x),
                    "topic_title": topic["title"]}
        if body.kind == "prerequisite":
            manifest["prerequisite_for"] = topic["title"]
        config.data_dir(lecture_id).mkdir(parents=True, exist_ok=True)
        config.save_manifest(lecture_id, manifest)
        # Start from the teacher's last persona, so it is described once, not for every lesson.
        last = one(conn, """SELECT l.lecture_id FROM lessons l JOIN topics t ON t.id = l.topic_id JOIN chapters ch ON ch.id = t.chapter_id
                            JOIN courses c ON c.id = ch.course_id WHERE c.teacher_id = ? ORDER BY l.id DESC LIMIT 1""", user["id"])
        if last and (config.data_dir(last["lecture_id"]) / "persona.md").exists():
            shutil.copy(config.data_dir(last["lecture_id"]) / "persona.md", config.data_dir(lecture_id) / "persona.md")
        cur = conn.execute("INSERT INTO lessons (topic_id, lecture_id, kind, title, created_at) VALUES (?, ?, ?, ?, ?)",
                           (topic_id, lecture_id, body.kind, title, now()))
    return {"id": cur.lastrowid, "lecture_id": lecture_id}


def _lesson(conn, lesson_id):
    row = one(conn, """SELECT l.*, ch.course_id FROM lessons l JOIN topics t ON t.id = l.topic_id
                       JOIN chapters ch ON ch.id = t.chapter_id WHERE l.id = ?""", lesson_id)
    if not row:
        raise HTTPException(404, "Lesson not found")
    return row


@router.delete("/lessons/{lesson_id}")
def delete_lesson(lesson_id: int, request: Request):
    """Removes the lesson from the course (and its shared post); the lecture's files stay on disk."""
    user = auth.require_teacher(request)
    with connect() as conn:
        access.need_course(user, _lesson(conn, lesson_id)["course_id"], teacher=True)
        conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    return {"ok": True}


class ShareIn(BaseModel):
    note: str = ""
    due_at: str | None = None


def _lock_version(conn, lesson):
    """Copy the approved script (and everything the player needs) into a read-only version file."""
    from eris.api.server_class import class_data
    data = class_data(lesson["lecture_id"])
    if not data.get("ready"):
        raise HTTPException(400, "Approve the script in Studio before sharing it")
    number = (one(conn, "SELECT MAX(number) AS m FROM versions WHERE lesson_id = ?", lesson["id"])["m"] or 0) + 1
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = VERSIONS_DIR / f"lesson{lesson['id']}-v{number}.json"
    data = {**data, "lecture_id": lesson["lecture_id"], "kind": lesson["kind"], "title": lesson["title"]}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    say_count = sum(1 for s in data["segments"] if s.get("kind") == "say")
    cur = conn.execute("INSERT INTO versions (lesson_id, number, path, say_count, created_at) VALUES (?, ?, ?, ?, ?)",
                       (lesson["id"], number, str(path), say_count, now()))
    return cur.lastrowid, number


def _current_version(conn, lesson):
    """The version of the lesson's approved script as it is now: the newest version, unless the script changed since."""
    latest = one(conn, "SELECT id, number, created_at FROM versions WHERE lesson_id = ? ORDER BY number DESC LIMIT 1", lesson["id"])
    script = config.lecture_dir(lesson["lecture_id"]) / "script.json"
    if latest and not (script.exists() and _newer(script, latest["created_at"])):
        return latest["id"], latest["number"]
    return _lock_version(conn, lesson)


def on_approved(lecture_id):
    """Studio approved a script. A lesson keeps every approved script as a numbered version; once the lesson is shared,
    the class gets the new version straight away (attendance already taken stays). None for a lecture outside courses."""
    with connect() as conn:
        lesson = one(conn, "SELECT * FROM lessons WHERE lecture_id = ?", lecture_id)
        if not lesson:
            return None
        version_id, number = _lock_version(conn, lesson)
        post = one(conn, "SELECT id FROM posts WHERE lesson_id = ? AND kind = 'lesson'", lesson["id"])
        if post:
            conn.execute("UPDATE posts SET version_id = ?, updated_at = ? WHERE id = ?", (version_id, now(), post["id"]))
    return {"version": number, "shared": bool(post)}


@router.get("/lessons/{lesson_id}/versions")
def lesson_versions(lesson_id: int, request: Request):
    """Every approved script of a lesson, newest first, and which one the class has."""
    user = auth.require_teacher(request)
    with connect() as conn:
        lesson = _lesson(conn, lesson_id)
        access.need_course(user, lesson["course_id"], teacher=True)
        post = one(conn, "SELECT id, version_id FROM posts WHERE lesson_id = ? AND kind = 'lesson'", lesson_id)
        versions = all_rows(conn, """SELECT v.id, v.number, v.say_count, v.created_at,
                                     (SELECT COUNT(DISTINCT p.user_id) FROM progress p WHERE p.version_id = v.id) AS students
                                     FROM versions v WHERE v.lesson_id = ? ORDER BY v.number DESC""", lesson_id)
    return {"lesson": {"id": lesson["id"], "title": lesson["title"], "lecture_id": lesson["lecture_id"]},
            "post_id": post["id"] if post else None, "shared_version_id": post["version_id"] if post else None, "versions": versions}


@router.get("/versions/{version_id}")
def version_script(version_id: int, request: Request):
    """One locked version's script, for the teacher to read."""
    user = auth.require_teacher(request)
    with connect() as conn:
        v = one(conn, "SELECT v.lesson_id FROM versions v WHERE v.id = ?", version_id)
        if not v:
            raise HTTPException(404, "Version not found")
        access.need_course(user, _lesson(conn, v["lesson_id"])["course_id"], teacher=True)
    _, data = _version_data(version_id)
    return {"segments": data["segments"], "teacher": data.get("teacher", ""), "lecture_id": data.get("lecture_id")}


@router.post("/lessons/{lesson_id}/versions/{version_id}/share")
def share_version(lesson_id: int, version_id: int, request: Request):
    """Give the class an earlier (or later) version of the lesson, e.g. to roll back a new script."""
    user = auth.require_teacher(request)
    with connect() as conn:
        lesson = _lesson(conn, lesson_id)
        access.need_course(user, lesson["course_id"], teacher=True)
        v = one(conn, "SELECT number FROM versions WHERE id = ? AND lesson_id = ?", version_id, lesson_id)
        post = one(conn, "SELECT id FROM posts WHERE lesson_id = ? AND kind = 'lesson'", lesson_id)
        if not v:
            raise HTTPException(404, "Version not found")
        if not post:
            raise HTTPException(400, "Share the lesson with the class first")
        conn.execute("UPDATE posts SET version_id = ?, updated_at = ? WHERE id = ?", (version_id, now(), post["id"]))
    return {"version": v["number"]}


@router.post("/lessons/{lesson_id}/share")
def share_lesson(lesson_id: int, body: ShareIn, request: Request):
    """Share an approved lesson with the course (a locked copy of its script), or share its newest approved script
    again: students get the new version from then on; earlier attendance stays."""
    user = auth.require_teacher(request)
    with connect() as conn:
        lesson = _lesson(conn, lesson_id)
        access.need_course(user, lesson["course_id"], teacher=True)
        version_id, number = _current_version(conn, lesson)
        post = one(conn, "SELECT id FROM posts WHERE lesson_id = ? AND kind = 'lesson'", lesson_id)
        if post:
            conn.execute("UPDATE posts SET version_id = ?, updated_at = ? WHERE id = ?", (version_id, now(), post["id"]))
            if body.note.strip() or body.due_at:
                conn.execute("UPDATE posts SET body = ?, due_at = ? WHERE id = ?", (body.note.strip(), body.due_at, post["id"]))
            return {"post_id": post["id"], "version": number}
        label = "Prerequisite: " if lesson["kind"] == "prerequisite" else ""
        cur = conn.execute("""INSERT INTO posts (course_id, topic_id, kind, title, body, lesson_id, version_id, due_at, created_at, updated_at)
                              VALUES (?, ?, 'lesson', ?, ?, ?, ?, ?, ?, ?)""",
                           (lesson["course_id"], lesson["topic_id"], label + lesson["title"], body.note.strip(), lesson_id,
                            version_id, body.due_at, now(), now()))
    return {"post_id": cur.lastrowid, "version": number}


# ---------- material posts ----------

def _post(conn, post_id):
    row = one(conn, POSTS_SQL + " WHERE p.id = ?", post_id)
    if not row:
        raise HTTPException(404, "Not found")
    return row


@router.post("/courses/{course_id}/materials")
async def add_material(course_id: int, request: Request, title: str = Form(...), body: str = Form(""),
                       topic_id: str = Form(""), due_at: str = Form(""), files: list[UploadFile] = File(default=[])):
    access.need_course(auth.require_teacher(request), course_id, teacher=True)
    if not title.strip():
        raise HTTPException(400, "Enter a title")
    with connect() as conn:
        tid = int(topic_id) if topic_id.strip().isdigit() else None
        if tid and _topic(conn, tid)["course_id"] != course_id:
            raise HTTPException(400, "That topic is in another course")
        cur = conn.execute("""INSERT INTO posts (course_id, topic_id, kind, title, body, due_at, created_at, updated_at)
                              VALUES (?, ?, 'material', ?, ?, ?, ?, ?)""",
                           (course_id, tid, title.strip()[:200], body.strip(), due_at or None, now(), now()))
        post_id = cur.lastrowid
        folder = COURSE_FILES / str(course_id) / "posts" / str(post_id)
        folder.mkdir(parents=True, exist_ok=True)
        for f in files:
            name = Path(f.filename or "file").name
            data = await f.read()
            if len(data) > MAX_FILE_MB * 1024 * 1024:
                raise HTTPException(400, f"{name} is larger than {MAX_FILE_MB} MB")
            (folder / name).write_bytes(data)
            conn.execute("INSERT INTO post_files (post_id, name, path, size) VALUES (?, ?, ?, ?)",
                         (post_id, name, str(folder / name), len(data)))
    return {"id": post_id}


class PostEdit(BaseModel):
    title: str | None = None
    body: str | None = None
    due_at: str | None = None


@router.put("/posts/{post_id}")
def edit_post(post_id: int, body: PostEdit, request: Request):
    user = auth.require_teacher(request)
    with connect() as conn:
        post = _post(conn, post_id)
        access.need_course(user, post["course_id"], teacher=True)
        conn.execute("UPDATE posts SET title = ?, body = ?, due_at = ?, updated_at = ? WHERE id = ?",
                     ((body.title or post["title"]).strip(), post["body"] if body.body is None else body.body.strip(),
                      body.due_at or None, now(), post_id))
    return {"ok": True}


@router.delete("/posts/{post_id}")
def delete_post(post_id: int, request: Request):
    user = auth.require_teacher(request)
    with connect() as conn:
        post = _post(conn, post_id)
        access.need_course(user, post["course_id"], teacher=True)
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    shutil.rmtree(COURSE_FILES / str(post["course_id"]) / "posts" / str(post_id), ignore_errors=True)
    return {"ok": True}


@router.get("/posts/{post_id}/files/{file_id}")
def download_file(post_id: int, file_id: int, request: Request):
    user = auth.require_user(request)
    with connect() as conn:
        post = _post(conn, post_id)
        access.need_course(user, post["course_id"])
        f = one(conn, "SELECT * FROM post_files WHERE id = ? AND post_id = ?", file_id, post_id)
    if not f or not Path(f["path"]).is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(f["path"], filename=f["name"])


# ---------- a student's lesson session ----------

def _version_data(version_id):
    with connect() as conn:
        v = one(conn, "SELECT * FROM versions WHERE id = ?", version_id)
    if not v:
        raise HTTPException(404, "This lesson version is missing")
    return v, json.loads(Path(v["path"]).read_text(encoding="utf-8"))


def version_segments(version_id, lecture_id):
    """The locked script of a version of this lecture (the doubt agent rebuilds the board from it); None when the
    version is not one of this lecture's."""
    with connect() as conn:
        v = one(conn, "SELECT v.path FROM versions v JOIN lessons l ON l.id = v.lesson_id WHERE v.id = ? AND l.lecture_id = ?",
                version_id, lecture_id)
    if not v or not Path(v["path"]).exists():
        return None
    return json.loads(Path(v["path"]).read_text(encoding="utf-8"))["segments"]


@router.get("/posts/{post_id}/class")
def post_class(post_id: int, request: Request):
    """Everything the player needs for a shared lesson: the locked script version, plus where this student left off."""
    user = auth.require_user(request)
    with connect() as conn:
        post = _post(conn, post_id)
        role = access.need_course(user, post["course_id"])
        if post["kind"] != "lesson":
            raise HTTPException(400, "This post is not a lesson")
        course = one(conn, "SELECT id, subject, year FROM courses WHERE id = ?", post["course_id"])
        progress = _progress_of(conn, user["id"], post) if role == "student" else None
        played = []
        if role == "student":
            row = one(conn, "SELECT played FROM progress WHERE user_id = ? AND post_id = ? AND version_id = ?",
                      user["id"], post_id, post["version_id"])
            played = loads(row["played"], []) if row else []
    version, data = _version_data(post["version_id"])
    return {**data, "ready": True, "post": {"id": post_id, "title": post["title"], "due_at": post["due_at"]},
            "version_id": post["version_id"], "version_number": version["number"], "course": course, "role": role, "progress": progress, "played": played}


class ProgressIn(BaseModel):
    version_id: int
    lines: list[int] = []
    last_index: int = 0


@router.post("/posts/{post_id}/progress")
def report_progress(post_id: int, body: ProgressIn, request: Request):
    """The player reports spoken lines it played (while visible). Merged; complete once every line is in."""
    user = auth.require_user(request)
    with connect() as conn:
        post = _post(conn, post_id)
        role = access.need_course(user, post["course_id"])
        if role != "student":
            return {"ignored": True}  # a teacher previewing doesn't take attendance
        if post["kind"] != "lesson":
            raise HTTPException(400, "This post is not a lesson")
        v = one(conn, "SELECT v.* FROM versions v WHERE v.id = ? AND v.lesson_id = ?", body.version_id, post["lesson_id"])
        if not v:
            raise HTTPException(400, "Unknown lesson version")
        segments = json.loads(Path(v["path"]).read_text(encoding="utf-8"))["segments"]
        say_lines = {i for i, s in enumerate(segments) if s.get("kind") == "say"}
        row = one(conn, "SELECT * FROM progress WHERE user_id = ? AND post_id = ? AND version_id = ?", user["id"], post_id, v["id"])
        played = set(loads(row["played"], [])) if row else set()
        played |= {i for i in body.lines if i in say_lines}
        last = max(0, min(body.last_index, len(segments)))
        done = say_lines <= played
        stamp = now()
        if row:
            conn.execute("""UPDATE progress SET played = ?, last_index = ?, updated_at = ?,
                            completed_at = COALESCE(completed_at, ?) WHERE user_id = ? AND post_id = ? AND version_id = ?""",
                         (json.dumps(sorted(played)), last, stamp, stamp if done else None, user["id"], post_id, v["id"]))
        else:
            conn.execute("""INSERT INTO progress (user_id, post_id, version_id, played, last_index, started_at, updated_at, completed_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                         (user["id"], post_id, v["id"], json.dumps(sorted(played)), last, stamp, stamp, stamp if done else None))
    return {"percent": round(100 * len(played & say_lines) / max(1, len(say_lines))), "completed": done}


# ---------- attendance and doubts (teacher) ----------

@router.get("/posts/{post_id}/attendance")
def attendance(post_id: int, request: Request):
    user = auth.require_teacher(request)
    with connect() as conn:
        post = _post(conn, post_id)
        access.need_course(user, post["course_id"], teacher=True)
        students = all_rows(conn, """SELECT u.id, u.name, u.email FROM enrollments e JOIN users u ON u.id = e.user_id
                                     WHERE e.course_id = ? ORDER BY u.name""", post["course_id"])
        rows = []
        for s in students:
            p = _progress_of(conn, s["id"], post)
            doubts = one(conn, "SELECT COUNT(*) AS n, SUM(passed) AS passed FROM doubts WHERE post_id = ? AND user_id = ?",
                         post_id, s["id"])
            completed = one(conn, "SELECT MIN(completed_at) AS at FROM progress WHERE user_id = ? AND post_id = ?", s["id"], post_id)
            status = "present" if p["completed"] else "started" if p["started"] else "not_started"
            rows.append({**s, "status": status, "percent": p["percent"], "last_activity": p["updated_at"],
                         "completed_at": completed["at"], "doubts": doubts["n"] or 0, "passed": doubts["passed"] or 0})
    return {"post": {"id": post_id, "title": post["title"], "due_at": post["due_at"], "version": post["version_number"]},
            "students": rows}


@router.get("/posts/{post_id}/doubts")
def post_doubts(post_id: int, request: Request, user_id: int | None = None):
    teacher = auth.require_teacher(request)
    with connect() as conn:
        post = _post(conn, post_id)
        access.need_course(teacher, post["course_id"], teacher=True)
        sql = """SELECT d.id, d.question, d.answer, d.passed, d.section, d.created_at, u.name AS student
                 FROM doubts d JOIN users u ON u.id = d.user_id WHERE d.post_id = ?"""
        args = [post_id]
        if user_id:
            sql += " AND d.user_id = ?"
            args.append(user_id)
        return all_rows(conn, sql + " ORDER BY d.created_at", *args)


def log_doubt(user, post_id, version_id, lecture_id, section, question, answer, passed):
    """Called by the doubt route after every answer to a signed-in user."""
    with connect() as conn:
        if post_id is not None and not one(conn, "SELECT id FROM posts WHERE id = ?", post_id):
            post_id = None
        conn.execute("""INSERT INTO doubts (user_id, post_id, version_id, lecture_id, section, question, answer, passed, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                     (user["id"], post_id, version_id, lecture_id, section[:200], question[:2000], (answer or "")[:8000],
                      int(bool(passed)), now()))
