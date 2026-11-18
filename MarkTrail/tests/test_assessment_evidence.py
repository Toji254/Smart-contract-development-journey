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

    def create_session(self, assessment_id="assessment-demo-upload", session_type="FINAL_EXAM"):
        return self.evidence.create_session(
            self.users["lecturer"],
            assessment_id,
            "2026-11-20T09:00:00",
            "Main Campus · Lecture Theatre 2",
            session_type,
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

    def test_lecturer_can_sign_physical_exam_card_after_evidence_reconciles(self):
        session_id = self.create_session(session_type="FINAL_EXAM")
        candidates = self.record_complete_register(session_id)
        present = candidates[0]
        absent = candidates[1]
        self.evidence.receive_script(
            self.users["lecturer"],
            session_id,
            present["student_id"],
            "CARD-SIGNOFF-PACKET-01",
        )

        with self.assertRaisesRegex(AppError, "Close the examination attendance register"):
            self.evidence.sign_exam_cards(
                self.users["lecturer"], session_id,
                [{"student_id": present["student_id"]}],
            )

        self.evidence.close_session(self.users["lecturer"], session_id)
        before = self.evidence.session_detail(self.users["lecturer"], session_id)
        self.assertIn(
            "LECTURER_EXAM_CARD_SIGNOFF_PENDING",
            {
                issue["code"] for issue in before["exceptions"]
                if issue["student_id"] == present["student_id"]
            },
        )

        with self.assertRaisesRegex(AppError, "Only the lecturer in charge"):
            self.evidence.sign_exam_cards(
                self.users["reviewer"], session_id,
                [{"student_id": present["student_id"]}],
            )
        with self.assertRaisesRegex(AppError, "(?i)only be signed for candidates recorded PRESENT"):
            self.evidence.sign_exam_cards(
                self.users["lecturer"], session_id,
                [{"student_id": absent["student_id"]}],
            )

        result = self.evidence.sign_exam_cards(
            self.users["lecturer"], session_id,
            [{
                "student_id": present["student_id"],
                "note": "Physical card signed after checking the unit examination record.",
            }],
        )
        self.assertEqual(result["signed"], 1)

        after = self.evidence.session_detail(self.users["lecturer"], session_id)
        signed_candidate = next(
            row for row in after["candidates"]
            if row["student_id"] == present["student_id"]
        )
        conn = self.db.connect()
        try:
            expected_lecturer_name = conn.execute(
                "SELECT full_name FROM users WHERE id = ?",
                (self.users["lecturer"],),
            ).fetchone()["full_name"]
        finally:
            conn.close()
        self.assertEqual(
            signed_candidate["card_signoff"]["signed_by_name"],
            expected_lecturer_name,
        )
        self.assertNotIn(
            "LECTURER_EXAM_CARD_SIGNOFF_PENDING",
            {issue["code"] for issue in signed_candidate["issues"]},
        )
        self.assertIn(
            "PHYSICAL_CARD_SIGNED",
            {event["event_type"] for event in after["activity"]},
        )

        student_view = self.evidence.student_progress(present["student_id"])
        own = next(
            row for row in student_view
            if row["assessment_id"] == "assessment-demo-upload"
            and row["session_id"] == session_id
        )
        self.assertTrue(own["lecturer_card_signed"])
        self.assertNotIn("lecturer_card_signed_by", own)

        with self.assertRaisesRegex(AppError, "already been signed"):
            self.evidence.sign_exam_cards(
                self.users["lecturer"], session_id,
                [{"student_id": present["student_id"]}],
            )

    def test_cat_session_does_not_require_physical_exam_card_signoff(self):
        session_id = self.create_session(session_type="CAT")
        self.record_complete_register(session_id)
        self.evidence.close_session(self.users["lecturer"], session_id)
        detail = self.evidence.session_detail(self.users["lecturer"], session_id)
        self.assertNotIn(
            "LECTURER_EXAM_CARD_SIGNOFF_PENDING",
            {issue["code"] for issue in detail["exceptions"]},
        )
        with self.assertRaisesRegex(AppError, "(?i)only to final or special examination"):
            self.evidence.sign_exam_cards(
                self.users["lecturer"], session_id,
                [{"student_id": detail["candidates"][0]["student_id"]}],
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

    def test_legacy_evidence_schema_migrates_without_losing_script_history(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(session_id)
        original = self.evidence.receive_script(
            self.users["lecturer"],
            session_id,
            candidates[0]["student_id"],
            "LEGACY-PACKET-01",
        )

        conn = self.db.connect()
        try:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                CREATE TABLE exam_sessions_legacy (
                    id TEXT PRIMARY KEY,
                    assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
                    exam_at TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED')),
                    candidate_count INTEGER NOT NULL,
                    created_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    closed_by INTEGER REFERENCES users(id),
                    closed_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO exam_sessions_legacy
                (id, assessment_id, exam_at, venue, status, candidate_count,
                 created_by, created_at, closed_by, closed_at)
                SELECT id, assessment_id, exam_at, venue, status, candidate_count,
                       created_by, created_at, closed_by, closed_at
                FROM exam_sessions
                """
            )
            conn.execute("DROP TABLE exam_sessions")
            conn.execute("ALTER TABLE exam_sessions_legacy RENAME TO exam_sessions")

            conn.execute(
                """
                CREATE TABLE exam_scripts_legacy (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    student_id INTEGER NOT NULL,
                    script_ref TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('RECEIVED','HANDOFF_PENDING','ASSIGNED','MARKED','FLAGGED')
                    ),
                    current_custodian INTEGER NOT NULL REFERENCES users(id),
                    pending_custodian INTEGER REFERENCES users(id),
                    notes TEXT NOT NULL DEFAULT '',
                    received_by INTEGER NOT NULL REFERENCES users(id),
                    received_at TEXT NOT NULL,
                    marked_by INTEGER REFERENCES users(id),
                    marked_at TEXT,
                    UNIQUE (session_id, student_id),
                    UNIQUE (session_id, script_ref),
                    FOREIGN KEY (session_id, student_id)
                        REFERENCES exam_session_candidates(session_id, student_id)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                INSERT INTO exam_scripts_legacy
                SELECT id, session_id, student_id, script_ref, status, current_custodian,
                       pending_custodian, notes, received_by, received_at, marked_by, marked_at
                FROM exam_scripts
                """
            )
            conn.execute("DROP TABLE exam_scripts")
            conn.execute("ALTER TABLE exam_scripts_legacy RENAME TO exam_scripts")

            conn.execute(
                """
                CREATE TABLE exam_script_events_legacy (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    script_id TEXT NOT NULL REFERENCES exam_scripts(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN (
                            'RECEIVED','HANDOFF_REQUESTED','HANDOFF_ACCEPTED','MARKED','FLAGGED'
                        )
                    ),
                    actor_id INTEGER NOT NULL REFERENCES users(id),
                    recipient_id INTEGER REFERENCES users(id),
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO exam_script_events_legacy
                SELECT id, script_id, event_type, actor_id, recipient_id, note, created_at
                FROM exam_script_events
                """
            )
            conn.execute("DROP TABLE exam_script_events")
            conn.execute(
                "ALTER TABLE exam_script_events_legacy RENAME TO exam_script_events"
            )
            conn.commit()
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.close()

        upgraded = AssessmentEvidenceService(self.db, self.app)
        detail_before = upgraded.session_detail(self.users["lecturer"], session_id)
        self.assertEqual(detail_before["summary"]["scripts_received"], 1)
        self.assertEqual(detail_before["session"]["session_type"], "UNCLASSIFIED")
        self.assertEqual(
            sum(1 for event in detail_before["activity"] if event["event_type"] == "RECEIVED"),
            1,
        )

        unidentified = upgraded.receive_script(
            self.users["lecturer"],
            session_id,
            None,
            "LEGACY-UNIDENTIFIED-02",
            "Registration number is unreadable on the answer booklet.",
        )
        target = detail_before["candidates"][1]
        upgraded.link_unidentified_script(
            self.users["reviewer"],
            unidentified["script_id"],
            target["student_id"],
            "Matched against the signed register and invigilator packet record.",
        )

        detail_after = upgraded.session_detail(self.users["reviewer"], session_id)
        self.assertIn(
            "IDENTITY_LINKED",
            {event["event_type"] for event in detail_after["activity"]},
        )
        check = self.db.connect()
        try:
            self.assertEqual(check.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            check.close()

    def test_evidence_case_opens_clears_and_requires_human_resolution(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(
            session_id,
            first_status="PRESENT",
            first_signature=False,
        )
        first = candidates[0]

        student_cases = self.evidence.list_evidence_cases(first["student_id"])
        signature_case = next(
            item for item in student_cases
            if item["category"] == "ATTENDANCE_SIGNATURE_MISSING"
        )
        self.assertEqual(signature_case["status"], "OPEN")
        self.assertNotIn("resolution_note", signature_case)
        self.assertNotIn("assigned_user_name", signature_case)

        other_student_cases = self.evidence.list_evidence_cases(candidates[1]["student_id"])
        self.assertEqual(other_student_cases, [])

        staff_cases = self.evidence.list_evidence_cases(self.users["exam_office"])
        self.assertTrue(any(item["id"] == signature_case["id"] for item in staff_cases))
        lecturer_cases = self.evidence.list_evidence_cases(self.users["lecturer"])
        self.assertTrue(any(item["category"] == "SCRIPT_NOT_RECEIVED" for item in lecturer_cases))

        self.evidence.record_attendance(self.users["lecturer"], session_id, [{
            "student_id": first["student_id"],
            "attendance_status": "PRESENT",
            "signature_present": True,
            "exam_card_seen": True,
            "student_id_seen": True,
            "note": "",
        }])

        reviewer_cases = self.evidence.list_evidence_cases(self.users["reviewer"])
        cleared = next(item for item in reviewer_cases if item["id"] == signature_case["id"])
        self.assertEqual(cleared["status"], "EVIDENCE_CLEARED")

        with self.assertRaisesRegex(AppError, "8"):
            self.evidence.decide_evidence_case(
                self.users["reviewer"], signature_case["id"], "RESOLVED", "Fix"
            )

        decision = self.evidence.decide_evidence_case(
            self.users["reviewer"],
            signature_case["id"],
            "RESOLVED",
            "Verified the signed physical attendance register against the invigilator record.",
        )
        self.assertEqual(decision["status"], "RESOLVED")
        final_student_cases = self.evidence.list_evidence_cases(first["student_id"])
        final_case = next(item for item in final_student_cases if item["id"] == signature_case["id"])
        self.assertEqual(final_case["status"], "RESOLVED")
        self.assertNotIn("resolution_note", final_case)

        notifications = self.app.student_notifications(first["student_id"])
        self.assertTrue(any(item["event_type"] == "EVIDENCE_CASE_OPENED" for item in notifications))
        self.assertTrue(any(item["event_type"] == "EVIDENCE_CASE_CLEARED" for item in notifications))
        self.assertTrue(any(item["event_type"] == "EVIDENCE_CASE_RESOLVED" for item in notifications))

        with self.assertRaisesRegex(AppError, "terminal decision"):
            self.evidence.decide_evidence_case(
                self.users["reviewer"],
                signature_case["id"],
                "DISMISSED",
                "Duplicate review.",
            )

    def test_resolved_case_reopens_if_the_same_evidence_exception_reappears(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(
            session_id,
            first_status="PRESENT",
            first_signature=False,
        )
        student_id = candidates[0]["student_id"]
        case = next(
            item for item in self.evidence.list_evidence_cases(student_id)
            if item["category"] == "ATTENDANCE_SIGNATURE_MISSING"
        )

        self.evidence.record_attendance(self.users["lecturer"], session_id, [{
            "student_id": student_id,
            "attendance_status": "PRESENT",
            "signature_present": True,
            "exam_card_seen": True,
            "student_id_seen": True,
            "note": "",
        }])
        self.evidence.decide_evidence_case(
            self.users["reviewer"],
            case["id"],
            "RESOLVED",
            "Verified the physical register and corrected the digital attendance evidence.",
        )

        self.evidence.record_attendance(self.users["lecturer"], session_id, [{
            "student_id": student_id,
            "attendance_status": "PRESENT",
            "signature_present": False,
            "exam_card_seen": True,
            "student_id_seen": True,
            "note": "",
        }])

        reopened = next(
            item for item in self.evidence.list_evidence_cases(student_id)
            if item["id"] == case["id"]
        )
        self.assertEqual(reopened["status"], "OPEN")
        conn = self.db.connect()
        try:
            event_types = [
                row["event_type"] for row in conn.execute(
                    "SELECT event_type FROM evidence_case_events WHERE case_id = ? ORDER BY id",
                    (case["id"],),
                ).fetchall()
            ]
        finally:
            conn.close()
        self.assertIn("EVIDENCE_CLEARED", event_types)
        self.assertIn("RESOLVED", event_types)
        self.assertIn("REOPENED", event_types)

    def test_unidentified_script_opens_staff_case_without_exposing_student_identity(self):
        session_id = self.create_session()
        result = self.evidence.receive_script(
            self.users["lecturer"],
            session_id,
            None,
            "UNIDENTIFIED-CASE-PACKET",
            "Registration and candidate name are unreadable.",
        )
        reviewer_cases = self.evidence.list_evidence_cases(self.users["reviewer"])
        case = next(
            item for item in reviewer_cases
            if item["category"] == "SCRIPT_UNIDENTIFIED"
        )
        self.assertEqual(case["script_id"], result["script_id"])
        self.assertIsNone(case["student_id"])
        self.assertEqual(case["status"], "OPEN")
        self.assertEqual(self.evidence.list_evidence_cases(self.users["student"]), [])

    def test_evidence_case_event_history_is_append_only(self):
        import sqlite3

        session_id = self.create_session()
        candidates = self.record_complete_register(
            session_id,
            first_status="PRESENT",
            first_signature=False,
        )
        cases = self.evidence.list_evidence_cases(candidates[0]["student_id"])
        case = next(item for item in cases if item["category"] == "ATTENDANCE_SIGNATURE_MISSING")
        conn = self.db.connect()
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "evidence case history is append-only"):
                conn.execute(
                    "UPDATE evidence_case_events SET note = 'rewritten' WHERE case_id = ?",
                    (case["id"],),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "evidence case history is append-only"):
                conn.execute(
                    "DELETE FROM evidence_case_events WHERE case_id = ?",
                    (case["id"],),
                )
        finally:
            conn.close()

    def test_only_reviewer_or_admin_can_decide_evidence_case(self):
        session_id = self.create_session()
        candidates = self.record_complete_register(
            session_id,
            first_status="PRESENT",
            first_signature=False,
        )
        cases = self.evidence.list_evidence_cases(candidates[0]["student_id"])
        case = next(item for item in cases if item["category"] == "ATTENDANCE_SIGNATURE_MISSING")
        with self.assertRaisesRegex(AppError, "permission"):
            self.evidence.decide_evidence_case(
                self.users["lecturer"],
                case["id"],
                "RESOLVED",
                "Investigation completed with evidence.",
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
