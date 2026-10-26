"""Who may do what. A lesson (lecture) belongs to the teacher of its course; students may play a lecture only
through a lesson shared to a course they are enrolled in."""

import json

from fastapi import HTTPException

from eris import config
from eris.platform.db import all_rows, connect, one

COURSE_OF_LECTURE = """
SELECT c.id AS course_id, c.teacher_id, c.subject, c.year, t.id AS topic_id, t.title AS topic_title,
       l.id AS lesson_id, l.kind, l.title AS lesson_title
FROM lessons l JOIN topics t ON t.id = l.topic_id JOIN chapters ch ON ch.id = t.chapter_id
JOIN courses c ON c.id = ch.course_id WHERE l.lecture_id = ?"""


def course_of_lecture(lecture_id):
    """The course, topic and lesson a lecture belongs to, or None for a lecture made before courses existed."""
    with connect() as conn:
        return one(conn, COURSE_OF_LECTURE, lecture_id)


def lecture_owner(lecture_id):
    """The teacher who made a lecture (owner_id in its lecture.json), or None for one made before courses existed."""
    try:
        return json.loads(config.manifest_path(lecture_id).read_text(encoding="utf-8")).get("owner_id")
    except (OSError, ValueError):
        return None


def stamp_owner(lecture_id, teacher_id):
    """Write the owner into lecture.json, so the lecture stays the teacher's even outside every course."""
    path = config.manifest_path(lecture_id)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if manifest.get("owner_id") != teacher_id:
        manifest["owner_id"] = teacher_id
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def teacher_owns_lecture(user, lecture_id):
    """A teacher owns the lectures in their courses, and the ones they made that are no longer in a course. A lecture
    with no owner at all (made before courses existed) is open to any teacher until it is moved into a course."""
    if user["role"] != "teacher":
        return False
    course = course_of_lecture(lecture_id)
    if course is not None:
        return course["teacher_id"] == user["id"]
    owner = lecture_owner(lecture_id)
    return owner is None or owner == user["id"]


def student_can_play_lecture(user, lecture_id):
    """Enrolled in a course where a lesson with this lecture was shared."""
    with connect() as conn:
        return one(conn, """
            SELECT p.id FROM posts p JOIN lessons l ON l.id = p.lesson_id
            JOIN enrollments e ON e.course_id = p.course_id AND e.user_id = ?
            WHERE p.kind = 'lesson' AND l.lecture_id = ? LIMIT 1""", user["id"], lecture_id) is not None


def can_use_lecture(user, lecture_id):
    return teacher_owns_lecture(user, lecture_id) or (user["role"] == "student" and student_can_play_lecture(user, lecture_id))


def course_role(user, course_id):
    """'teacher' (owns it), 'student' (enrolled) or None."""
    with connect() as conn:
        course = one(conn, "SELECT teacher_id FROM courses WHERE id = ?", course_id)
        if not course:
            return None
        if course["teacher_id"] == user["id"]:
            return "teacher"
        if one(conn, "SELECT 1 AS x FROM enrollments WHERE course_id = ? AND user_id = ?", course_id, user["id"]):
            return "student"
    return None


def need_course(user, course_id, teacher=False):
    """The caller's role in the course; 404 when they have no access, 403 when a teacher is needed."""
    role = course_role(user, course_id)
    if role is None:
        raise HTTPException(404, "Course not found")
    if teacher and role != "teacher":
        raise HTTPException(403, "Only the course's teacher can do this")
    return role


def claim_lectures():
    """Run at startup: every lecture records its teacher. Lectures in a course get their course's teacher; a lecture
    that left its course (made inside one, then its lesson, topic or course was deleted) is matched by the course name
    it was made in. Lectures from before courses (no course name) stay open to any teacher."""
    from pathlib import Path
    with connect() as conn:
        for row in all_rows(conn, """SELECT l.lecture_id, c.teacher_id FROM lessons l JOIN topics t ON t.id = l.topic_id
                                     JOIN chapters ch ON ch.id = t.chapter_id JOIN courses c ON c.id = ch.course_id"""):
            if lecture_owner(row["lecture_id"]) is None:
                stamp_owner(row["lecture_id"], row["teacher_id"])
        courses = all_rows(conn, "SELECT teacher_id, subject, year FROM courses")
    labels = {" · ".join(x for x in (c["subject"], c["year"]) if x): c["teacher_id"] for c in courses}
    for folder in Path(config.DATA_ROOT).iterdir():
        if not folder.is_dir() or lecture_owner(folder.name) is not None or course_of_lecture(folder.name):
            continue
        try:
            label = json.loads(config.manifest_path(folder.name).read_text(encoding="utf-8")).get("course_label")
        except (OSError, ValueError):
            continue
        if label in labels:
            stamp_owner(folder.name, labels[label])
