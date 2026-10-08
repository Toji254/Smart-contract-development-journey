from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.service import AppError, AppService


class FakeChain:
    enabled = False

    class Config:
        mode = "off"

    config = Config()

    def status(self):
        return {
            "enabled": False,
            "mode": "off",
            "label": "Local-only audit mode",
        }


class MarkTrailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")
        self.db.init(seed_demo=True)
        self.service = AppService(self.db, FakeChain())

        conn = self.db.connect()
        self.student = conn.execute(
            "SELECT id FROM users WHERE username = 'student'"
        ).fetchone()
        self.lecturer = conn.execute(
            "SELECT id FROM users WHERE username = 'lecturer'"
        ).fetchone()
        self.reviewer = conn.execute(
            "SELECT id FROM users WHERE username = 'reviewer'"
        ).fetchone()
        self.assessment = conn.execute(
            "SELECT id FROM assessments WHERE id = 'assessment-cat2'"
        ).fetchone()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_student_sees_missing_cat2(self):
        marks = self.service.student_marks(self.student["id"])
        cat2 = next(row for row in marks if row["assessment_id"] == "assessment-cat2")
        self.assertEqual(cat2["status"], "MISSING")
        self.assertIsNone(cat2["mark"])
        self.assertEqual(cat2["batch_status"], "VERIFIED")

    def test_student_can_open_one_missing_mark_report(self):
        result = self.service.report_missing_mark(
            self.student["id"], self.assessment["id"]
        )
        self.assertEqual(result["status"], "OPEN")

        with self.assertRaises(AppError):
            self.service.report_missing_mark(
                self.student["id"], self.assessment["id"]
            )

    def _create_fresh_assessment(self):
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO assessments (id, course_id, name, max_mark, created_at)
                VALUES ('assessment-cat3', 'course-csc201', 'CAT 3', 20,
                        '2026-10-08T00:00:00+00:00')
                """
            )

    def test_lecturer_batch_preview_detects_missing_students(self):
        preview = self.service.preview_batch(
            self.lecturer["id"],
            "assessment-cat2",
            "student_id,mark\n4,17\n",
        )
        self.assertTrue(preview["valid"])
        self.assertEqual(preview["enrolled_count"], 2)
        self.assertEqual(preview["submitted_count"], 1)
        self.assertEqual(preview["missing_count"], 1)

    def test_lecturer_can_submit_new_batch(self):
        self._create_fresh_assessment()
        result = self.service.submit_batch(
            self.lecturer["id"],
            "assessment-cat3",
            "student_id,mark\n4,19\n5,16\n",
        )
        self.assertEqual(result["status"], "SUBMITTED")
        self.assertEqual(result["chain_state"], "LOCAL_ONLY")

    def test_reviewer_verification_publishes_candidate_marks(self):
        self._create_fresh_assessment()
        self.service.submit_batch(
            self.lecturer["id"],
            "assessment-cat3",
            "student_id,mark\n4,19\n5,16\n",
        )

        conn = self.db.connect()
        batch = conn.execute(
            "SELECT id FROM batches WHERE assessment_id = 'assessment-cat3'"
        ).fetchone()
        conn.close()

        self.service.verify_batch(self.reviewer["id"], batch["id"])

        conn = self.db.connect()
        rows = conn.execute(
            """
            SELECT published_mark, published_status
            FROM assessment_marks
            WHERE assessment_id = 'assessment-cat3'
            ORDER BY student_id
            """
        ).fetchall()
        conn.close()

        self.assertEqual(rows[0]["published_mark"], 19)
        self.assertEqual(rows[0]["published_status"], "RECORDED")
        self.assertEqual(rows[1]["published_mark"], 16)

    def test_missing_mark_resolution_requires_reviewer_before_publication(self):
        report_id = self.service.report_missing_mark(
            self.student["id"], self.assessment["id"]
        )["id"]

        result = self.service.resolve_report(
            self.lecturer["id"],
            report_id,
            "MARK_ENTERED",
            17,
            "Restored from lecturer mark sheet.",
        )

        self.assertEqual(result["status"], "PENDING_REVIEW")

        conn = self.db.connect()
        report = conn.execute(
            "SELECT status FROM missing_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        mark = conn.execute(
            """
            SELECT candidate_mark, candidate_status, published_mark, published_status
            FROM assessment_marks
            WHERE assessment_id = 'assessment-cat2' AND student_id = ?
            """,
            (self.student["id"],),
        ).fetchone()
        batch = conn.execute(
            "SELECT status, revision FROM batches WHERE id = ?",
            (result["batch_id"],),
        ).fetchone()
        conn.close()

        self.assertEqual(report["status"], "PENDING_REVIEW")
        self.assertEqual(mark["candidate_mark"], 17)
        self.assertEqual(mark["candidate_status"], "RECORDED")
        self.assertIsNone(mark["published_mark"])
        self.assertEqual(mark["published_status"], "MISSING")
        self.assertEqual(batch["status"], "AMENDED")
        self.assertEqual(batch["revision"], 2)

        self.service.verify_batch(self.reviewer["id"], result["batch_id"])

        conn = self.db.connect()
        mark = conn.execute(
            """
            SELECT published_mark, published_status
            FROM assessment_marks
            WHERE assessment_id = 'assessment-cat2' AND student_id = ?
            """,
            (self.student["id"],),
        ).fetchone()
        report = conn.execute(
            "SELECT status, resolved_at FROM missing_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        conn.close()

        self.assertEqual(mark["published_mark"], 17)
        self.assertEqual(mark["published_status"], "RECORDED")
        self.assertEqual(report["status"], "RESOLVED")
        self.assertIsNotNone(report["resolved_at"])

    def test_no_mark_resolution_is_distinguished_from_missing(self):
        report_id = self.service.report_missing_mark(
            self.student["id"], self.assessment["id"]
        )["id"]

        self.service.resolve_report(
            self.lecturer["id"],
            report_id,
            "NO_MARK_AWARDED",
            None,
            "Student did not sit the assessment.",
        )

        conn = self.db.connect()
        mark = conn.execute(
            """
            SELECT candidate_mark, candidate_status, published_mark, published_status
            FROM assessment_marks
            WHERE assessment_id = 'assessment-cat2' AND student_id = ?
            """,
            (self.student["id"],),
        ).fetchone()
        conn.close()

        self.assertEqual(mark["candidate_mark"], 0)
        self.assertEqual(mark["candidate_status"], "NO_MARK")
        self.assertIsNone(mark["published_mark"])
        self.assertEqual(mark["published_status"], "MISSING")


if __name__ == "__main__":
    unittest.main()
