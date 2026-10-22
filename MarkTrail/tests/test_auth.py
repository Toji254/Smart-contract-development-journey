from __future__ import annotations

import tempfile
import unittest
from http.cookies import SimpleCookie
from pathlib import Path

from app.auth import (
    SESSION_COOKIE,
    clear_session_cookie,
    current_user,
    login,
    session_cookie,
)
from app.db import Database


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "auth.db")
        self.db.init(seed_demo=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_login_creates_session_for_active_user(self):
        session_id = login(self.db, "student", "student123")

        self.assertIsNotNone(session_id)
        user = current_user(
            self.db,
            f"{SESSION_COOKIE}={session_id}",
        )
        self.assertEqual(user["username"], "student")

    def test_login_rejects_bad_password_and_unknown_user(self):
        self.assertIsNone(login(self.db, "student", "wrong-password"))
        self.assertIsNone(login(self.db, "unknown", "student123"))

    def test_inactive_user_cannot_login(self):
        with self.db.transaction() as conn:
            conn.execute("UPDATE users SET active = 0 WHERE username = 'student'")

        self.assertIsNone(login(self.db, "student", "student123"))

    def test_session_cookies_have_matching_security_attributes(self):
        session = SimpleCookie()
        session.load(session_cookie("session-token"))
        session_morsel = session[SESSION_COOKIE]
        self.assertEqual(session_morsel["httponly"], True)
        self.assertEqual(session_morsel["path"], "/")
        self.assertEqual(session_morsel["samesite"], "Lax")
        self.assertEqual(session_morsel["max-age"], "43200")

        cleared = SimpleCookie()
        cleared.load(clear_session_cookie())
        cleared_morsel = cleared[SESSION_COOKIE]
        self.assertEqual(cleared_morsel["path"], session_morsel["path"])
        self.assertEqual(cleared_morsel["samesite"], session_morsel["samesite"])
        self.assertEqual(cleared_morsel["max-age"], "0")


if __name__ == "__main__":
    unittest.main()
