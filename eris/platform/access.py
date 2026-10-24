"""Who may do what. A lesson (lecture) belongs to the teacher of its course; students may play a lecture only
through a lesson shared to a course they are enrolled in."""

from fastapi import HTTPException

from eris.platform.db import connect, one

COURSE_OF_LECTURE = """
SELECT c.id AS course_id, c.teacher_id, c.subject, c.year, t.id AS topic_id, t.title AS topic_title,
       l.id AS lesson_id, l.kind, l.title AS lesson_title
FROM lessons l JOIN topics t ON t.id = l.topic_id JOIN chapters ch ON ch.id = t.chapter_id
JOIN courses c ON c.id = ch.course_id WHERE l.lecture_id = ?"""


def course_of_lecture(lecture_id):
    """The course, topic and lesson a lecture belongs to, or None for a lecture made before courses existed."""
    with connect() as conn:
        return one(conn, COURSE_OF_LECTURE, lecture_id)


def teacher_owns_lecture(user, lecture_id):
    """A teacher owns the lectures in their courses. A lecture outside every course (made before courses) is open to
    any teacher, so older lectures stay reachable until they are moved into a course."""
    if user["role"] != "teacher":
        return False
    owner = course_of_lecture(lecture_id)
    return owner is None or owner["teacher_id"] == user["id"]


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
