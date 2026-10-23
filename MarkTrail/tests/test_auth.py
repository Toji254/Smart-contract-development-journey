from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import patch

from app.auth import (
    SESSION_COOKIE,
    clear_session_cookie,
    current_user,
    login,
    session_cookie,
)
from app.db import Database
from run import create_initial_admin


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "auth.db")
        self.db.init(seed_demo=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_login_creates_session_for_active_user(self):
        result = login(self.db, "student", "student123")

        self.assertIsNotNone(result)
        session_id, must_change = result
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

    def test_expired_user_cannot_login_or_keep_using_an_existing_session(self):
        session_id, _ = login(self.db, "student", "student123")
        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE users SET access_until = ? WHERE username = 'student'",
                (yesterday,),
            )

        self.assertIsNone(login(self.db, "student", "student123"))
        self.assertIsNone(
            current_user(self.db, f"{SESSION_COOKIE}={session_id}")
        )

    def test_access_through_date_includes_that_day(self):
        today = datetime.now(timezone.utc).date().isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE users SET access_until = ? WHERE username = 'student'",
                (today,),
            )

        self.assertIsNotNone(login(self.db, "student", "student123"))

    def test_session_cookies_have_matching_security_attributes(self):
        with patch.dict("os.environ", {}, clear=True):
            session = SimpleCookie()
            session.load(session_cookie("session-token"))
            session_morsel = session[SESSION_COOKIE]
            self.assertEqual(session_morsel["httponly"], True)
            self.assertEqual(session_morsel["path"], "/")
            self.assertEqual(session_morsel["samesite"], "Lax")
            self.assertEqual(session_morsel["max-age"], "43200")
            self.assertTrue(session_morsel["secure"])

            cleared = SimpleCookie()
            cleared.load(clear_session_cookie())
            cleared_morsel = cleared[SESSION_COOKIE]
            self.assertEqual(cleared_morsel["path"], session_morsel["path"])
            self.assertEqual(cleared_morsel["samesite"], session_morsel["samesite"])
            self.assertEqual(cleared_morsel["max-age"], "0")
            self.assertTrue(cleared_morsel["secure"])

    def test_http_cookie_opt_out_is_explicit(self):
        with patch.dict("os.environ", {"MARKTRAIL_COOKIE_SECURE": "0"}, clear=True):
            cookie = SimpleCookie()
            cookie.load(session_cookie("local-session"))
        self.assertFalse(cookie[SESSION_COOKIE]["secure"])

    def test_first_admin_bootstrap_is_secure_and_only_works_for_empty_database(self):
        path = Path(self.tmp.name) / "bootstrap.db"
        db = Database(path)

        user_id = create_initial_admin(
            db,
            " first-admin ",
            " First Admin ",
            "long-unique-admin-password",
        )
        self.assertGreater(user_id, 0)
        self.assertIsNotNone(
            login(db, "first-admin", "long-unique-admin-password")
        )
        with self.assertRaises(ValueError):
            create_initial_admin(
                db,
                "second-admin",
                "Second Admin",
                "another-long-unique-password",
            )

    def test_first_admin_bootstrap_rejects_short_password(self):
        db = Database(Path(self.tmp.name) / "short-password.db")
        with self.assertRaisesRegex(ValueError, "at least 12 characters"):
            create_initial_admin(db, "admin", "Admin", "short")


if __name__ == "__main__":
    unittest.main()
