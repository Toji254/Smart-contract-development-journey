from __future__ import annotations

import os
from http.cookies import CookieError, SimpleCookie

from .db import Database, verify_password


SESSION_COOKIE = "marktrail_session"
SESSION_MAX_AGE = 12 * 60 * 60


def _secure_cookie_enabled() -> bool:
    return os.getenv("MARKTRAIL_COOKIE_SECURE", "1") == "1"


def session_cookie(session_id: str) -> str:
    cookie = SimpleCookie()
    cookie[SESSION_COOKIE] = session_id
    morsel = cookie[SESSION_COOKIE]
    morsel["httponly"] = True
    morsel["max-age"] = str(SESSION_MAX_AGE)
    morsel["path"] = "/"
    morsel["samesite"] = "Lax"
    if _secure_cookie_enabled():
        morsel["secure"] = True
    return morsel.OutputString()


def clear_session_cookie() -> str:
    cookie = SimpleCookie()
    cookie[SESSION_COOKIE] = ""
    morsel = cookie[SESSION_COOKIE]
    morsel["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    morsel["httponly"] = True
    morsel["max-age"] = "0"
    morsel["path"] = "/"
    morsel["samesite"] = "Lax"
    if _secure_cookie_enabled():
        morsel["secure"] = True
    return morsel.OutputString()


def login(db: Database, username: str, password: str) -> tuple[str, bool] | None:
    conn = db.connect()
    try:
        user = conn.execute(
            """
            SELECT id, password_salt, password_hash, must_change_password
            FROM users
            WHERE username = ? AND active = 1
            """,
            (username,),
        ).fetchone()
    finally:
        conn.close()

    if not user or not verify_password(
        password,
        user["password_salt"],
        user["password_hash"],
    ):
        return None

    session_id = db.create_session(int(user["id"]), hours=SESSION_MAX_AGE // 3600)
    return session_id, bool(user["must_change_password"])


def current_user(db: Database, cookie_header: str | None):
    if not cookie_header:
        return None

    cookies = SimpleCookie()
    try:
        cookies.load(cookie_header)
    except CookieError:
        return None

    morsel = cookies.get(SESSION_COOKIE)
    if not morsel or not morsel.value:
        return None
    return db.get_session_user(morsel.value)
