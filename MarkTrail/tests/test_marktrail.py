from __future__ import annotations

import csv
import io
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
        self.other_student = conn.execute(
            "SELECT id FROM users WHERE username = 'student2'"
        ).fetchone()
        self.lecturer = conn.execute(
            "SELECT id FROM users WHERE username = 'lecturer'"
        ).fetchone()
        self.reviewer = conn.execute(
            "SELECT id FROM users WHERE username = 'reviewer'"
        ).fetchone()
        self.exam_office = conn.execute(
            "SELECT id FROM users WHERE username = 'exam_office'"
        ).fetchone()
        self.portal_operator = conn.execute(
            "SELECT id FROM users WHERE username = 'portal_operator'"
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

    def test_pipeline_audit_shows_owner_and_each_handoff_duration(self):
        conn = self.db.connect()
        batch = conn.execute(
            "SELECT id FROM batches WHERE assessment_id = 'assessment-cat1'"
        ).fetchone()
        conn.close()

        pipeline = self.service.batch_pipeline(self.student["id"], batch["id"])

        self.assertEqual(pipeline["current_stage"], "PUBLISHED")
        self.assertEqual(pipeline["current_owner"], "Published to students")
        self.assertEqual(
            [stage["owner"] for stage in pipeline["stages"]],
            [
                "Department / reviewer",
                "Exam office",
                "Portal operator",
            ],
        )
        self.assertTrue(all(stage["duration_seconds"] >= 0 for stage in pipeline["stages"]))
        self.assertEqual(
            pipeline["stages"][0]["completed_by"],
            "Prof. Grace Wambui",
        )

    def test_student_notifications_are_private_and_can_be_marked_read(self):
        report_id = self.service.report_missing_mark(
            self.student["id"], self.assessment["id"]
        )["id"]
        self.service.reject_report(
            self.lecturer["id"], report_id, "Please check the answer script."
        )

        notifications = self.service.student_notifications(self.student["id"])
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["event_type"], "REPORT_REJECTED")
        self.assertEqual(
            self.service.student_notifications(self.other_student["id"]),
            [],
        )
        with self.assertRaises(AppError) as error:
            self.service.mark_notification_read(
                self.other_student["id"], notifications[0]["id"]
            )
        self.assertEqual(error.exception.status, 404)

        result = self.service.mark_notification_read(
            self.student["id"], notifications[0]["id"]
        )
        self.assertTrue(result["read"])
        self.assertIsNotNone(
            self.service.student_notifications(self.student["id"])[0]["read_at"]
        )

    def test_student_audit_csv_escapes_formulas_and_omits_mark_history(self):
        conn = self.db.connect()
        batch = conn.execute(
            "SELECT id FROM batches WHERE assessment_id = 'assessment-cat1'"
        ).fetchone()
        conn.close()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE batches SET chain_tx_hash = '＝1+1' WHERE id = ?",
                (batch["id"],),
            )

        report = self.service.batch_report_csv(self.student["id"], batch["id"])
        rows = list(csv.reader(io.StringIO(report)))
        self.assertIn(["chain_tx_hash", "'＝1+1"], rows)
        self.assertFalse(any("Student ID" in cell for row in rows for cell in row))

    def test_csv_cell_sanitizer_handles_ascii_unicode_and_whitespace_prefixes(self):
        dangerous = [
            "=1+1",
            "+1+1",
            "-1+1",
            "@SUM(A1:A2)",
            "\t=1+1",
            "\r=1+1",
            "\n=1+1",
            " \t=1+1",
            "＝1+1",
            "＋1+1",
            "－1+1",
            "＠SUM(A1:A2)",
            "\u200b=1+1",
        ]
        for value in dangerous:
            with self.subTest(value=value):
                self.assertEqual(
                    self.service._sanitize_csv_cell(value),
                    "'" + value,
                )
        self.assertEqual(self.service._sanitize_csv_cell("ordinary text"), "ordinary text")
        self.assertEqual(self.service._sanitize_csv_cell(12.5), 12.5)

    def test_student_batch_audit_excludes_salt_and_private_event_notes(self):
        conn = self.db.connect()
        batch = conn.execute(
            "SELECT id FROM batches WHERE assessment_id = 'assessment-cat1'"
        ).fetchone()
        conn.close()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO audit_events
                (entity_type, entity_id, actor_id, action, metadata_json, created_at)
                VALUES ('BATCH', ?, ?, 'BATCH_AMENDED', ?, '2026-10-22T12:00:00+00:00')
                """,
                (
                    batch["id"],
                    self.lecturer["id"],
                    '{"reason":"private note about another student","report_id":"secret-report"}',
                ),
            )
            conn.execute(
                """
                INSERT INTO batch_revisions
                (batch_id, revision, marks_hash, reason_hash, kind, actor_id,
                 chain_state, created_at)
                VALUES (?, 2, 'marks-hash-2', 'reason-hash-secret',
                        'AMENDMENT', ?, 'LOCAL_ONLY', '2026-10-22T12:00:00+00:00')
                """,
                (batch["id"], self.lecturer["id"]),
            )

        student_audit = self.service.batch_audit(self.student["id"], batch["id"])
        self.assertNotIn("commitment_salt", student_audit["batch"])
        self.assertNotIn("submitted_by", student_audit["batch"])
        self.assertNotIn("lecturer_id", student_audit["batch"])
        self.assertNotIn("reason_hash", student_audit["revisions"][-1])
        self.assertNotIn("actor_id", student_audit["revisions"][-1])
        student_event = next(
            event for event in student_audit["events"]
            if event["action"] == "BATCH_AMENDED"
        )
        self.assertEqual(student_event["metadata"], {})
        self.assertNotIn("actor_id", student_event)
        self.assertNotIn("metadata_json", student_event)

        staff_audit = self.service.batch_audit(self.reviewer["id"], batch["id"])
        staff_event = next(
            event for event in staff_audit["events"]
            if event["action"] == "BATCH_AMENDED"
        )
        self.assertEqual(
            staff_event["metadata"]["reason"],
            "private note about another student",
        )

    def test_only_course_lecturer_can_preview_or_submit_batches(self):
        forbidden_users = [
            self.student["id"],
            self.reviewer["id"],
            self.exam_office["id"],
            self.portal_operator["id"],
        ]
        for index, user_id in enumerate(forbidden_users, start=3):
            assessment_id = f"assessment-role-{index}"
            with self.db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO assessments (id, course_id, name, max_mark, created_at)
                    VALUES (?, 'course-csc201', 'Role test', 20, '2026-10-08T00:00:00+00:00')
                    """,
                    (assessment_id,),
                )
            with self.subTest(role_user_id=user_id):
                with self.assertRaises(AppError) as preview_error:
                    self.service.preview_batch(
                        user_id, assessment_id, "student_id,mark\n4,18\n"
                    )
                self.assertEqual(preview_error.exception.status, 403)
                with self.assertRaises(AppError) as submit_error:
                    self.service.submit_batch(
                        user_id, assessment_id, "student_id,mark\n4,18\n"
                    )
                self.assertEqual(submit_error.exception.status, 403)

    def test_lecturer_cannot_preview_or_submit_for_another_lecturers_course(self):
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO users
                (username, full_name, role, password_salt, password_hash, created_at)
                VALUES ('other_lecturer', 'Other Lecturer', 'lecturer', 'salt', 'hash', ?)
                """,
                ("2026-10-08T00:00:00+00:00",),
            )
            other_lecturer = conn.execute(
                "SELECT id FROM users WHERE username = 'other_lecturer'"
            ).fetchone()
            conn.execute(
                """
                INSERT INTO courses (id, code, title, lecturer_id, created_at)
                VALUES ('course-other', 'CSC 999', 'Other course', ?, ?)
                """,
                (other_lecturer["id"], "2026-10-08T00:00:00+00:00"),
            )
            conn.execute(
                """
                INSERT INTO assessments (id, course_id, name, max_mark, created_at)
                VALUES ('assessment-other', 'course-other', 'Exam', 20, ?)
                """,
                ("2026-10-08T00:00:00+00:00",),
            )

        for operation in (
            self.service.preview_batch,
            self.service.submit_batch,
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(AppError) as error:
                    operation(
                        self.lecturer["id"],
                        "assessment-other",
                        "student_id,mark\n4,18\n",
                    )
                self.assertEqual(error.exception.status, 403)

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

    def test_marks_publish_only_after_ordered_office_handoffs(self):
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

        pipeline = self.service.batch_pipeline(self.reviewer["id"], batch["id"])
        self.assertEqual(pipeline["current_stage"], "DEPARTMENT_REVIEW")
        self.assertEqual(pipeline["current_owner"], "Department / reviewer")
        self.assertIsNotNone(pipeline["waiting_since"])
        self.assertIsNone(pipeline["stages"][-1]["completed_at"])

        verified = self.service.verify_batch(self.reviewer["id"], batch["id"])
        self.assertEqual(verified["pipeline_stage"], "EXAM_OFFICE")
        pipeline = self.service.batch_pipeline(self.exam_office["id"], batch["id"])
        self.assertEqual(pipeline["current_owner"], "Exam office")

        marks = self.service.student_marks(self.student["id"])
        cat3 = next(row for row in marks if row["assessment_id"] == "assessment-cat3")
        self.assertEqual(cat3["status"], "AWAITING_PUBLICATION")
        self.assertIsNone(cat3["mark"])

        with self.assertRaises(AppError):
            self.service.publish_portal_batch(
                self.portal_operator["id"], batch["id"]
            )

        processed = self.service.process_exam_office_batch(
            self.exam_office["id"], batch["id"]
        )
        self.assertEqual(processed["pipeline_stage"], "PORTAL_IMPORT")
        pipeline = self.service.batch_pipeline(self.portal_operator["id"], batch["id"])
        self.assertEqual(pipeline["current_owner"], "Portal operator")
        self.service.publish_portal_batch(self.portal_operator["id"], batch["id"])
        pipeline = self.service.batch_pipeline(self.student["id"], batch["id"])
        self.assertEqual(pipeline["current_stage"], "PUBLISHED")
        self.assertEqual(pipeline["waiting_seconds"], 0)

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
        for student_id in (self.student["id"], self.other_student["id"]):
            notifications = self.service.student_notifications(student_id)
            self.assertEqual(len(notifications), 1)
            self.assertEqual(notifications[0]["event_type"], "MARKS_PUBLISHED")
            self.assertIn("published", notifications[0]["body"].lower())

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
        notifications = self.service.student_notifications(self.student["id"])
        self.assertEqual(notifications[0]["event_type"], "MARK_AMENDED")
        self.assertIn("awaiting department review", notifications[0]["body"])

        self.service.verify_batch(self.reviewer["id"], result["batch_id"])
        self.service.process_exam_office_batch(
            self.exam_office["id"], result["batch_id"]
        )
        self.service.publish_portal_batch(
            self.portal_operator["id"], result["batch_id"]
        )

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
        notifications = self.service.student_notifications(self.student["id"])
        self.assertEqual(
            [item["event_type"] for item in notifications].count("REPORT_RESOLVED"),
            1,
        )
        self.assertEqual(
            [item["event_type"] for item in notifications].count("MARKS_PUBLISHED"),
            0,
        )
        self.assertEqual(
            [item["event_type"] for item in notifications].count("MARK_AMENDED"),
            1,
        )

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

    def test_rejection_is_visible_and_student_can_report_again(self):
        report_id = self.service.report_missing_mark(
            self.student["id"], self.assessment["id"]
        )["id"]

        with self.assertRaises(AppError):
            self.service.reject_report(self.lecturer["id"], report_id, "  ")

        result = self.service.reject_report(
            self.lecturer["id"],
            report_id,
            "The mark sheet shows the assessment was not attempted.",
        )
        self.assertEqual(result["status"], "REJECTED")

        student_reports = self.service.student_reports(self.student["id"])
        rejected = next(row for row in student_reports if row["id"] == report_id)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertEqual(
            rejected["lecturer_note"],
            "The mark sheet shows the assessment was not attempted.",
        )
        lecturer_reports = self.service.lecturer_reports(self.lecturer["id"])
        self.assertTrue(any(row["id"] == report_id for row in lecturer_reports))

        reopened = self.service.report_missing_mark(
            self.student["id"], self.assessment["id"]
        )
        self.assertEqual(reopened["status"], "OPEN")


if __name__ == "__main__":
    unittest.main()
