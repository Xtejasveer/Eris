"""The course platform (v1): accounts, courses with class codes, chapters and topics, lessons (Eris lectures),
sharing to a course, locked script versions, per-student progress and attendance, and doubt logs.

Data lives in one SQLite file (workspace/eris.db); lecture material, scripts and audio stay where they always were
(data/<lecture>/, workspace/lectures/<lecture>/). A lesson is a lecture that belongs to a topic.
"""
