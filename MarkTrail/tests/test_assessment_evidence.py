from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.evidence import AssessmentEvidenceService
from app.service import AppError, AppService


class AssessmentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "marktrail-test.db")
        self.db.init(seed_demo=True)
        self.app = AppService(self.db)
        self.evidence = AssessmentEvidenceService(self.db, self.app)

        conn = self.db.connect()
        try:
            self.users = {
                row["username"]: int(row["id"])
                for row in conn.execute("SELECT id, username FROM users").fetchall()
            }
        finally:
            conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def create_session(self, assessment_id="assessment-demo-upload"):
        return self.evidence.create_session(
            self.users["lecturer"],
            assessment_id,
            "2026-11-20T09:00:00",
            "Main Campus · Lecture Theatre 2",
        )["session_id"]

    def roster(self, session_id):
        return self.evidence.session_detail(self.users["lecturer"], session_id)["candidates"]

    def record_complete_register(self, session_id, first_status="PRESENT", first_signature=True):
        candidates = self.roster(session_id)
        items = []
        for index, candidate in enumerate(candidates):
            is_first = index == 0
            items.append({
                "student_id": candidate["student_id"],
                "attendance_status": first_status if is_first else "ABSENT",
                "signature_present": first_signature if is_first else False,
                "exam_card_seen": is_first,
                "student_id_seen": is_first,
                "note": "" if (first_status if is_first else "ABSENT") == "PRESENT"
                    else "Recorded absent by invigilator register.",
            })
        self.evidence.record_attendance(self.users["lecturer"], session_id, items)
        return candidates

    def test_session_locks_candidate_roster_snapshot(self):
        session_id = self.create_session()
        before = self.roster(session_id)
        self.assertEqual(len(before), 2)

        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM enrollments WHERE course_id = 'course-csc201' AND student_id = ?",
                (before[0]["student_id"],),
            )

        after = self.roster(session_id)
        self.assertEqual(
            {row["student_id"] for row in before},
            {row["student_id"] for row in after},
        )

    def test_missing_signature_does_not_turn_present_candidate_into_absent(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(
            session_id,
            first_status="PRESENT",
            first_signature=False,
        )
        self.evidence.close_session(self.users["lecturer"], session_id)

        detail = self.evidence.session_detail(self.users["lecturer"], session_id)
        first = next(
            item for item in detail["candidates"]
            if item["student_id"] == candidates[0]["student_id"]
        )
        issue_codes = {item["code"] for item in detail["exceptions"]}
        self.assertEqual(first["attendance"]["attendance_status"], "PRESENT")
        self.assertIn("ATTENDANCE_SIGNATURE_MISSING", issue_codes)
        self.assertNotEqual(first["attendance"]["attendance_status"], "ABSENT")

    def test_absent_or_excused_attendance_requires_a_reason(self):
        session_id = self.create_session()
        candidate = self.roster(session_id)[0]
        with self.assertRaisesRegex(AppError, "(?i)absent attendance decisions require"):
            self.evidence.record_attendance(self.users["lecturer"], session_id, [{
                "student_id": candidate["student_id"],
                "attendance_status": "ABSENT",
                "signature_present": False,
                "exam_card_seen": False,
                "student_id_seen": False,
                "note": "",
            }])

    def test_late_script_intake_after_register_closure_requires_reason(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(session_id)
        self.evidence.close_session(self.users["lecturer"], session_id)
        with self.assertRaisesRegex(AppError, "Scripts received after register closure"):
            self.evidence.receive_script(
                self.users["lecturer"],
                session_id,
                candidates[0]["student_id"],
                "LATE-PACKET-01",
            )

    def test_bulk_attendance_is_atomic_when_one_candidate_is_not_in_roster(self):
        session_id = self.create_session()
        candidates = self.roster(session_id)
        with self.assertRaisesRegex(AppError, "not in the locked examination roster"):
            self.evidence.record_attendance(self.users["lecturer"], session_id, [
                {
                    "student_id": candidates[0]["student_id"],
                    "attendance_status": "PRESENT",
                    "signature_present": True,
                    "exam_card_seen": True,
                    "student_id_seen": True,
                    "note": "",
                },
                {
                    "student_id": 999999,
                    "attendance_status": "PRESENT",
                    "signature_present": True,
                    "exam_card_seen": True,
                    "student_id_seen": True,
                    "note": "",
                },
            ])
        detail = self.evidence.session_detail(self.users["lecturer"], session_id)
        first = next(
            row for row in detail["candidates"]
            if row["student_id"] == candidates[0]["student_id"]
        )
        self.assertIsNone(first["attendance"])
        self.assertEqual(detail["activity"], [
            event for event in detail["activity"]
            if event["category"] == "SESSION"
        ])

    def test_bulk_attendance_rejects_duplicate_candidate_rows(self):
        session_id = self.create_session()
        candidate = self.roster(session_id)[0]
        item = {
            "student_id": candidate["student_id"],
            "attendance_status": "PRESENT",
            "signature_present": True,
            "exam_card_seen": True,
            "student_id_seen": True,
            "note": "",
        }
        with self.assertRaisesRegex(AppError, "duplicate candidate"):
            self.evidence.record_attendance(
                self.users["lecturer"], session_id, [item, item]
            )

    def test_register_cannot_close_until_every_candidate_has_a_decision(self):
        session_id = self.create_session()
        with self.assertRaisesRegex(AppError, "attendance decisions are not recorded"):
            self.evidence.close_session(self.users["lecturer"], session_id)

    def test_signed_candidate_recorded_absent_is_a_conflict_not_discarded(self):
        session_id = self.create_session()
        candidates = self.roster(session_id)
        first = candidates[0]
        self.evidence.record_attendance(self.users["lecturer"], session_id, [{
            "student_id": first["student_id"],
            "attendance_status": "ABSENT",
            "signature_present": True,
            "exam_card_seen": True,
            "student_id_seen": True,
            "note": "Register shows signature but attendance disputed.",
        }])
        detail = self.evidence.session_detail(self.users["lecturer"], session_id)
        recorded = next(
            row for row in detail["candidates"]
            if row["student_id"] == first["student_id"]
        )
        self.assertTrue(recorded["attendance"]["signature_present"])
        self.assertEqual(recorded["attendance"]["attendance_status"], "ABSENT")
        self.assertIn(
            "ATTENDANCE_SIGNATURE_STATUS_CONFLICT",
            {item["code"] for item in recorded["issues"]},
        )

    def test_present_candidate_without_script_is_flagged(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(session_id)
        self.evidence.close_session(self.users["lecturer"], session_id)

        detail = self.evidence.session_detail(self.users["lecturer"], session_id)
        issue = next(
            item for item in detail["exceptions"]
            if item["student_id"] == candidates[0]["student_id"]
            and item["code"] == "SCRIPT_NOT_RECEIVED"
        )
        self.assertEqual(issue["severity"], "high")

    def test_script_marked_without_marks_batch_is_flagged(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(session_id)
        result = self.evidence.receive_script(
            self.users["lecturer"],
            session_id,
            candidates[0]["student_id"],
            "PACKET-02-SEAT-14",
        )
        self.assertEqual(result["status"], "RECEIVED")

        self.evidence.mark_script(
            self.users["lecturer"], result["script_id"], "Marking completed."
        )
        detail = self.evidence.session_detail(self.users["lecturer"], session_id)
        self.assertIn(
            "MARK_ENTRY_NOT_FOUND",
            {
                issue["code"] for issue in detail["exceptions"]
                if issue["student_id"] == candidates[0]["student_id"]
            },
        )

    def test_script_received_for_candidate_recorded_absent_is_flagged(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(session_id)
        absent = candidates[1]
        self.evidence.receive_script(
            self.users["lecturer"], session_id, absent["student_id"], "PACKET-02-SEAT-15"
        )

        detail = self.evidence.session_detail(self.users["lecturer"], session_id)
        self.assertIn(
            "SCRIPT_RECEIVED_FOR_RECORDED_ABSENT",
            {
                issue["code"] for issue in detail["exceptions"]
                if issue["student_id"] == absent["student_id"]
            },
        )

    def test_script_handover_requires_recipient_acceptance(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(session_id)
        script = self.evidence.receive_script(
            self.users["lecturer"], session_id, candidates[0]["student_id"], "PACKET-02-SEAT-16"
        )
        request = self.evidence.request_script_handoff(
            self.users["lecturer"], script["script_id"], self.users["reviewer"], "Second marker review."
        )
        self.assertEqual(request["status"], "HANDOFF_PENDING")

        with self.assertRaisesRegex(AppError, "current script custodian"):
            self.evidence.mark_script(self.users["reviewer"], script["script_id"])

        accepted = self.evidence.accept_script_handoff(
            self.users["reviewer"], script["script_id"]
        )
        self.assertEqual(accepted["status"], "ASSIGNED")
        marked = self.evidence.mark_script(
            self.users["reviewer"], script["script_id"], "Second marker completed review."
        )
        self.assertEqual(marked["status"], "MARKED")

    def test_unidentified_script_is_quarantined_until_human_linking(self):
        session_id = self.create_session()
        result = self.evidence.receive_script(
            self.users["lecturer"],
            session_id,
            None,
            "UNMATCHED-PACKET-09",
            "Candidate name and registration number are illegible.",
        )
        self.assertTrue(result["unidentified"])
        self.assertEqual(result["status"], "FLAGGED")

        detail = self.evidence.session_detail(self.users["lecturer"], session_id)
        self.assertEqual(len(detail["unidentified_scripts"]), 1)
        self.assertIn("SCRIPT_UNIDENTIFIED", {item["code"] for item in detail["exceptions"]})

        candidate = detail["candidates"][0]
        with self.assertRaises(AppError):
            self.evidence.link_unidentified_script(
                self.users["lecturer"], result["script_id"], candidate["student_id"],
                "The script appears to belong to this candidate."
            )

        linked = self.evidence.link_unidentified_script(
            self.users["reviewer"], result["script_id"], candidate["student_id"],
            "Matched using the verified attendance and script packet evidence."
        )
        self.assertEqual(linked["student_id"], candidate["student_id"])
        detail = self.evidence.session_detail(self.users["reviewer"], session_id)
        self.assertEqual(detail["unidentified_scripts"], [])
        identity_event = next(
            event for event in detail["activity"]
            if event["category"] == "SCRIPT" and event["event_type"] == "IDENTITY_LINKED"
        )
        self.assertEqual(identity_event["candidate_name"], candidate["full_name"])

    def test_closed_register_correction_requires_reviewer_and_reason(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(session_id)
        self.evidence.close_session(self.users["lecturer"], session_id)

        item = {
            "student_id": candidates[0]["student_id"],
            "attendance_status": "EXCUSED",
            "signature_present": False,
            "exam_card_seen": True,
            "student_id_seen": True,
            "note": "Approved deferred examination.",
        }
        with self.assertRaisesRegex(AppError, "reviewer or administrator"):
            self.evidence.record_attendance(self.users["lecturer"], session_id, [item])

        with self.assertRaisesRegex(AppError, "8-character reason"):
            self.evidence.record_attendance(
                self.users["reviewer"], session_id, [{**item, "note": "Fix"}]
            )

        self.evidence.record_attendance(self.users["reviewer"], session_id, [item])
        detail = self.evidence.session_detail(self.users["reviewer"], session_id)
        corrected = next(
            row for row in detail["candidates"]
            if row["student_id"] == candidates[0]["student_id"]
        )
        self.assertEqual(corrected["attendance"]["attendance_status"], "EXCUSED")

    def test_activity_timeline_keeps_attendance_corrections_and_script_handoffs(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(session_id)
        script = self.evidence.receive_script(
            self.users["lecturer"],
            session_id,
            candidates[0]["student_id"],
            "TIMELINE-PACKET-01",
        )
        self.evidence.request_script_handoff(
            self.users["lecturer"],
            script["script_id"],
            self.users["reviewer"],
            "Second marker review requested.",
        )
        self.evidence.accept_script_handoff(
            self.users["reviewer"], script["script_id"]
        )

        detail = self.evidence.session_detail(self.users["reviewer"], session_id)
        events = detail["activity"]
        event_types = {(event["category"], event["event_type"]) for event in events}
        self.assertIn(("SESSION", "SESSION_CREATED"), event_types)
        self.assertIn(("ATTENDANCE", "RECORDED"), event_types)
        self.assertIn(("SCRIPT", "RECEIVED"), event_types)
        self.assertIn(("SCRIPT", "HANDOFF_REQUESTED"), event_types)
        self.assertIn(("SCRIPT", "HANDOFF_ACCEPTED"), event_types)

        handoff = next(
            event for event in events
            if event["category"] == "SCRIPT" and event["event_type"] == "HANDOFF_REQUESTED"
        )
        self.assertEqual(handoff["recipient_name"], "Prof. Grace Wambui")
        self.assertEqual(handoff["script_ref"], "TIMELINE-PACKET-01")

    def test_evidence_event_tables_reject_update_and_delete(self):
        import sqlite3

        session_id = self.create_session()
        candidates = self.record_complete_register(session_id)
        script = self.evidence.receive_script(
            self.users["lecturer"],
            session_id,
            candidates[0]["student_id"],
            "IMMUTABLE-PACKET-01",
        )
        with self.db.transaction() as conn:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                conn.execute(
                    "UPDATE exam_script_events SET note = 'rewritten' WHERE script_id = ?",
                    (script["script_id"],),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                conn.execute(
                    "DELETE FROM exam_attendance_events WHERE session_id = ?",
                    (session_id,),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                conn.execute(
                    "DELETE FROM exam_session_events WHERE session_id = ?",
                    (session_id,),
                )

    def test_student_progress_is_scoped_and_hides_staff_only_notes(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(session_id)
        first = candidates[0]
        self.evidence.receive_script(
            self.users["lecturer"],
            session_id,
            first["student_id"],
            "STUDENT-VIEW-PACKET-01",
            "Private intake note for staff only.",
        )

        first_progress = self.evidence.student_progress(first["student_id"])
        first_item = next(
            item for item in first_progress
            if item["assessment_id"] == "assessment-demo-upload"
            and item["session_id"] == session_id
        )
        self.assertEqual(first_item["attendance_status"], "PRESENT")
        self.assertEqual(first_item["script_status"], "RECEIVED")
        self.assertTrue(first_item["evidence_available"])
        self.assertNotIn("activity", first_item)
        self.assertNotIn("note", first_item)
        self.assertNotIn("script_ref", first_item)
        self.assertNotIn("current_custodian", first_item)

        second_progress = self.evidence.student_progress(candidates[1]["student_id"])
        second_item = next(
            item for item in second_progress
            if item["assessment_id"] == "assessment-demo-upload"
            and item["session_id"] == session_id
        )
        self.assertEqual(second_item["attendance_status"], "ABSENT")
        self.assertIsNone(second_item["script_status"])

    def test_student_progress_marks_unrecorded_exam_evidence_as_unavailable(self):
        progress = self.evidence.student_progress(self.users["student"])
        item = next(
            row for row in progress
            if row["assessment_id"] == "assessment-demo-upload"
        )
        self.assertFalse(item["evidence_available"])
        self.assertIsNone(item["attendance_status"])
        self.assertIsNone(item["script_status"])

    def test_non_student_cannot_read_student_progress(self):
        with self.assertRaisesRegex(AppError, "permission"):
            self.evidence.student_progress(self.users["lecturer"])

    def test_student_cannot_access_staff_evidence_management(self):
        with self.assertRaisesRegex(AppError, "permission"):
            self.evidence.list_assessments(self.users["student"])


if __name__ == "__main__":
    unittest.main()
