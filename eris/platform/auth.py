"""Accounts and sign-in: salted PBKDF2 password hashes, random session tokens in an HttpOnly cookie."""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from eris.platform.db import connect, now, one

COOKIE = "eris_session"
SESSION_DAYS = 30
ITERATIONS = 200_000


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password, stored):
    try:
        _, iterations, salt, digest = stored.split("$")
        test = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(test, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def public_user(row):
    return {"id": row["id"], "email": row["email"], "name": row["name"], "role": row["role"]}


def create_user(email, name, password, role):
    """A new account. Raises ValueError with a message for the person when something is wrong."""
    email, name = email.strip().lower(), name.strip()
    if "@" not in email or len(email) > 200:
        raise ValueError("Enter a valid email address")
    if not name:
        raise ValueError("Enter your name")
    if len(password) < 8:
        raise ValueError("Use a password of at least 8 characters")
    if role not in ("teacher", "student"):
        raise ValueError("Choose teacher or student")
    with connect() as conn:
        if one(conn, "SELECT id FROM users WHERE email = ?", email):
            raise ValueError("An account with this email already exists")
        cur = conn.execute("INSERT INTO users (email, name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                           (email, name, role, hash_password(password), now()))
        return public_user(one(conn, "SELECT * FROM users WHERE id = ?", cur.lastrowid))


def check_login(email, password):
    with connect() as conn:
        row = one(conn, "SELECT * FROM users WHERE email = ?", email.strip().lower())
    if not row or not verify_password(password, row["password_hash"]):
        return None
    return public_user(row)


def new_session(user_id):
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute("INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                     (token, user_id, now(), expires))
    return token


def end_session(token):
    if token:
        with connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def user_from_request(request: Request):
    """The signed-in user (dict) or None."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with connect() as conn:
        row = one(conn, "SELECT u.* , s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
                  token)
    if not row or row["expires_at"] < now():
        return None
    return public_user(row)


def set_cookie(response, token):
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/")


def require_user(request: Request):
    user = getattr(request.state, "user", None) or user_from_request(request)
    if not user:
        raise HTTPException(401, "Please sign in")
    return user


def require_teacher(request: Request):
    user = require_user(request)
    if user["role"] != "teacher":
        raise HTTPException(403, "Only teachers can do this")
    return user
