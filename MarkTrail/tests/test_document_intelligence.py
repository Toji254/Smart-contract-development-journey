from __future__ import annotations

import base64
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.attachments import EvidenceAttachmentService
from app.db import Database
from app.document_intelligence import EvidenceDocumentIntelligenceService
from app.evidence import AssessmentEvidenceService
from app.service import AppError, AppService


class EvidenceDocumentIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "marktrail.db")
        self.db.init(seed_demo=True)
        self.app = AppService(self.db)
        self.evidence = AssessmentEvidenceService(self.db, self.app)
        self.key = "33" * 32
        self.attachments = EvidenceAttachmentService(
            self.db,
            self.app,
            storage_dir=self.root / "private-evidence",
            scanner=lambda _path: ("CLEAN", "test scanner: clean"),
            encryption_key=self.key,
        )
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

    def create_session(self):
        return self.evidence.create_session(
            self.users["lecturer"],
            "assessment-demo-upload",
            "2026-11-20T09:00:00",
            "Main Campus · Lecture Theatre 2",
            "FINAL_EXAM",
        )["session_id"]

    def upload_register(self, session_id, *, service=None):
        service = service or self.attachments
        payload = b"%PDF-1.7\nSynthetic register source.\n%%EOF"
        result = service.upload(
            self.users["lecturer"],
            "SESSION",
            session_id,
            "attendance-register.pdf",
            base64.b64encode(payload).decode("ascii"),
        )
        return result, payload

    def counts(self, session_id):
        conn = self.db.connect()
        try:
            return {
                table: conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE session_id = ?", (session_id,)
                ).fetchone()[0]
                for table in (
                    "exam_attendance",
                    "exam_session_events",
                    "evidence_cases",
                    "evidence_case_events",
                )
            }
        finally:
            conn.close()

    def test_local_ocr_produces_unverified_suggestions_without_changing_academic_records(self):
        session_id = self.create_session()
        uploaded, payload = self.upload_register(session_id)
        extracted_text = (
            "KARATINA UNIVERSITY ATTENDANCE REGISTER\n"
            "Registration No: S14/12345/2022\n"
            "Date: 20/11/2026\n"
            "PRESENT    ABSENT    SIGNATURE\n"
        )
        service = EvidenceDocumentIntelligenceService(
            self.db,
            self.app,
            self.attachments,
            ocr_runner=lambda document, media_type: {
                "status": "COMPLETE",
                "engine": "FAKE_TESSERACT_FOR_TEST",
                "page_count": 1,
                "text": extracted_text,
                "warning": "",
            },
        )
        before = self.counts(session_id)
        result = service.analyze(self.users["lecturer"], uploaded["id"])
        after = self.counts(session_id)

        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["suggestions"]["suggested_document_type"], "ATTENDANCE_REGISTER")
        self.assertIn("S14/12345/2022", result["suggestions"]["registration_number_candidates"])
        self.assertIn("20/11/2026", result["suggestions"]["date_candidates"])
        self.assertEqual(result["suggestions"]["present_word_occurrences"], 1)
        self.assertEqual(result["suggestions"]["absent_word_occurrences"], 1)
        self.assertTrue(result["review_required"])
        self.assertFalse(result["decision_ready"])
        self.assertEqual(result["decision_authority"], "HUMAN_ONLY")
        self.assertEqual(before, after)

        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT encrypted_result FROM evidence_document_extractions WHERE attachment_id = ?",
                (uploaded["id"],),
            ).fetchone()
            self.assertIsNotNone(row)
            stored = bytes(row["encrypted_result"])
            self.assertNotIn(extracted_text.encode("utf-8"), stored)
            self.assertNotIn(b"S14/12345/2022", stored)
            audit = conn.execute(
                """
                SELECT COUNT(*) FROM audit_events
                WHERE entity_type = 'EVIDENCE_ATTACHMENT'
                  AND entity_id = ? AND action = 'EVIDENCE_DOCUMENT_ANALYZED'
                """,
                (uploaded["id"],),
            ).fetchone()[0]
            self.assertEqual(audit, 1)
        finally:
            conn.close()

    def test_completed_extraction_is_cached_for_the_same_source_hash(self):
        session_id = self.create_session()
        uploaded, _payload = self.upload_register(session_id)
        calls = {"count": 0}

        def runner(_document, _media_type):
            calls["count"] += 1
            return {
                "status": "COMPLETE",
                "engine": "TEST_OCR",
                "page_count": 1,
                "text": "EXAMINATION CARD STUDENT ID",
                "warning": "",
            }

        service = EvidenceDocumentIntelligenceService(
            self.db, self.app, self.attachments, ocr_runner=runner
        )
        first = service.analyze(self.users["lecturer"], uploaded["id"])
        second = service.analyze(self.users["lecturer"], uploaded["id"])
        self.assertEqual(calls["count"], 1)
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["cached"])

    def test_students_cannot_request_staff_document_intelligence(self):
        session_id = self.create_session()
        uploaded, _payload = self.upload_register(session_id)
        service = EvidenceDocumentIntelligenceService(
            self.db,
            self.app,
            self.attachments,
            ocr_runner=lambda _document, _media_type: {
                "status": "COMPLETE", "engine": "TEST", "page_count": 1,
                "text": "ATTENDANCE REGISTER", "warning": "",
            },
        )
        with self.assertRaises(AppError) as denied:
            service.analyze(self.users["student"], uploaded["id"])
        self.assertEqual(denied.exception.status, 403)

    def test_quarantined_attachments_cannot_be_analysed(self):
        session_id = self.create_session()
        quarantined = EvidenceAttachmentService(
            self.db,
            self.app,
            storage_dir=self.root / "quarantine",
            scanner=lambda _path: ("QUARANTINED", "scanner unavailable"),
            encryption_key=self.key,
        )
        uploaded, _payload = self.upload_register(session_id, service=quarantined)
        self.assertEqual(uploaded["scan_status"], "QUARANTINED")
        service = EvidenceDocumentIntelligenceService(
            self.db,
            self.app,
            quarantined,
            ocr_runner=lambda _document, _media_type: {
                "status": "COMPLETE", "engine": "TEST", "page_count": 1,
                "text": "ATTENDANCE REGISTER", "warning": "",
            },
        )
        with self.assertRaises(AppError) as blocked:
            service.analyze(self.users["lecturer"], uploaded["id"])
        self.assertEqual(blocked.exception.status, 409)
        conn = self.db.connect()
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM evidence_document_extractions WHERE attachment_id = ?",
                (uploaded["id"],),
            ).fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            conn.close()

    def test_unavailable_local_ocr_is_reported_without_claiming_a_scan(self):
        session_id = self.create_session()
        uploaded, _payload = self.upload_register(session_id)
        service = EvidenceDocumentIntelligenceService(
            self.db,
            self.app,
            self.attachments,
            ocr_runner=lambda _document, _media_type: {
                "status": "UNAVAILABLE",
                "engine": "LOCAL_TESSERACT",
                "page_count": 0,
                "text": "",
                "warning": "Tesseract is not installed on the test host.",
            },
        )
        result = service.analyze(self.users["lecturer"], uploaded["id"])
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["extracted_character_count"], 0)
        self.assertIn("not installed", result["warning"])
        self.assertTrue(result["review_required"])
        self.assertFalse(result["decision_ready"])

    def test_extraction_history_is_append_only(self):
        session_id = self.create_session()
        uploaded, _payload = self.upload_register(session_id)
        service = EvidenceDocumentIntelligenceService(
            self.db,
            self.app,
            self.attachments,
            ocr_runner=lambda _document, _media_type: {
                "status": "COMPLETE", "engine": "TEST", "page_count": 1,
                "text": "SCRIPT RECEIPT ANSWER BOOKLET", "warning": "",
            },
        )
        result = service.analyze(self.users["lecturer"], uploaded["id"])
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction() as conn:
                conn.execute(
                    "UPDATE evidence_document_extractions SET status = 'FAILED' WHERE id = ?",
                    (result["id"],),
                )
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction() as conn:
                conn.execute(
                    "DELETE FROM evidence_document_extractions WHERE id = ?",
                    (result["id"],),
                )


if __name__ == "__main__":
    unittest.main()
