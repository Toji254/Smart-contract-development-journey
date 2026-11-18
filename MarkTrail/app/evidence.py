from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import Database, utc_now
from .service import AppError, AppService


STAFF_ROLES = {"lecturer", "reviewer", "exam_office", "portal_operator", "admin"}
ATTENDANCE_STATES = {"PRESENT", "ABSENT", "EXCUSED", "CONTESTED"}


class AssessmentEvidenceService:
    """Evidence capture and reconciliation for in-person examination workflows.

    This module records what staff observed. It deliberately does not decide
    whether a student deserves a mark, and it never treats a missing signature
    as proof of absence.
    """

    def __init__(self, db: Database, app: AppService) -> None:
        self.db = db
        self.app = app
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        conn = self.db.connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS exam_sessions (
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
                );

                CREATE TABLE IF NOT EXISTS exam_session_candidates (
                    session_id TEXT NOT NULL REFERENCES exam_sessions(id) ON DELETE CASCADE,
                    student_id INTEGER NOT NULL REFERENCES users(id),
                    reg_number_snapshot TEXT,
                    full_name_snapshot TEXT NOT NULL,
                    PRIMARY KEY (session_id, student_id)
                );

                CREATE TABLE IF NOT EXISTS exam_attendance (
                    session_id TEXT NOT NULL,
                    student_id INTEGER NOT NULL,
                    attendance_status TEXT NOT NULL CHECK (
                        attendance_status IN ('PRESENT','ABSENT','EXCUSED','CONTESTED')
                    ),
                    signature_present INTEGER NOT NULL DEFAULT 0 CHECK (signature_present IN (0,1)),
                    exam_card_seen INTEGER NOT NULL DEFAULT 0 CHECK (exam_card_seen IN (0,1)),
                    student_id_seen INTEGER NOT NULL DEFAULT 0 CHECK (student_id_seen IN (0,1)),
                    note TEXT NOT NULL DEFAULT '',
                    recorded_by INTEGER NOT NULL REFERENCES users(id),
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, student_id),
                    FOREIGN KEY (session_id, student_id)
                        REFERENCES exam_session_candidates(session_id, student_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS exam_scripts (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    student_id INTEGER,
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
                );

                CREATE TABLE IF NOT EXISTS exam_script_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    script_id TEXT NOT NULL REFERENCES exam_scripts(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN (
                            'RECEIVED','HANDOFF_REQUESTED','HANDOFF_ACCEPTED',
                            'MARKED','FLAGGED'
                        )
                    ),
                    actor_id INTEGER NOT NULL REFERENCES users(id),
                    recipient_id INTEGER REFERENCES users(id),
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_exam_sessions_assessment
                    ON exam_sessions(assessment_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_exam_candidates_student
                    ON exam_session_candidates(student_id, session_id);
                CREATE INDEX IF NOT EXISTS idx_exam_scripts_custodian
                    ON exam_scripts(current_custodian, status);
                CREATE INDEX IF NOT EXISTS idx_exam_script_events_script
                    ON exam_script_events(script_id, created_at);
                """
            )
        finally:
            conn.close()

    def _require_staff(self, user_id: int):
        return self.app.require_role(user_id, STAFF_ROLES)

    def _assessment_row(self, assessment_id: str):
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT a.id, a.name, a.max_mark, a.submission_deadline,
                       c.id AS course_id, c.code AS course_code, c.title AS course_title,
                       c.lecturer_id,
                       (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id) AS enrolled_count
                FROM assessments a
                JOIN courses c ON c.id = a.course_id
                WHERE a.id = ?
                """,
                (assessment_id,),
            ).fetchone()
            if not row:
                raise AppError("Assessment not found.", 404)
            return row
        finally:
            conn.close()

    def _authorize_assessment(self, user_id: int, assessment_id: str):
        actor = self._require_staff(user_id)
        assessment = self._assessment_row(assessment_id)
        if actor["role"] == "lecturer" and int(assessment["lecturer_id"] or 0) != user_id:
            raise AppError("You can only manage examination evidence for your assigned courses.", 403)
        return actor, assessment

    def _session_row(self, session_id: str):
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT s.*, a.name AS assessment_name, a.course_id,
                       c.code AS course_code, c.title AS course_title,
                       c.lecturer_id
                FROM exam_sessions s
                JOIN assessments a ON a.id = s.assessment_id
                JOIN courses c ON c.id = a.course_id
                WHERE s.id = ?
                """,
                (session_id,),
            ).fetchone()
            if not row:
                raise AppError("Examination session not found.", 404)
            return row
        finally:
            conn.close()

    def _authorize_session(self, user_id: int, session_id: str):
        session = self._session_row(session_id)
        actor = self._require_staff(user_id)
        if actor["role"] == "lecturer" and int(session["lecturer_id"] or 0) != user_id:
            raise AppError("You do not manage this examination session.", 403)
        return actor, session

    def list_assessments(self, user_id: int) -> list[dict[str, Any]]:
        actor = self._require_staff(user_id)
        conn = self.db.connect()
        try:
            query = """
                SELECT a.id, a.name, a.max_mark, a.submission_deadline,
                       c.id AS course_id, c.code AS course_code, c.title AS course_title,
                       (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id) AS enrolled_count,
                       (SELECT COUNT(*) FROM exam_sessions s WHERE s.assessment_id = a.id) AS session_count
                FROM assessments a
                JOIN courses c ON c.id = a.course_id
            """
            params: tuple = ()
            if actor["role"] == "lecturer":
                query += " WHERE c.lecturer_id = ?"
                params = (user_id,)
            query += " ORDER BY c.code, a.created_at DESC"
            return [dict(row) for row in conn.execute(query, params).fetchall()]
        finally:
            conn.close()

    def create_session(
        self,
        user_id: int,
        assessment_id: str,
        exam_at: str,
        venue: str,
    ) -> dict[str, Any]:
        actor, assessment = self._authorize_assessment(user_id, assessment_id)
        if not exam_at.strip():
            raise AppError("Examination date and time are required.")
        try:
            parsed = datetime.fromisoformat(exam_at.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise AppError("Examination date and time must be valid ISO date-time text.") from exc
        if parsed.tzinfo is None:
            # Preserve the local time entered by the invigilator; the institution's
            # configured timezone is applied by the presentation layer.
            normalized_exam_at = parsed.isoformat()
        else:
            normalized_exam_at = parsed.astimezone(timezone.utc).isoformat()
        venue = venue.strip()
        if not venue or len(venue) > 120:
            raise AppError("Provide an examination venue of at most 120 characters.")
        if int(assessment["enrolled_count"]) < 1:
            raise AppError("This course has no enrolled students. Add the approved roster first.")

        session_id = "exam-" + uuid.uuid4().hex
        now = utc_now()
        with self.db.transaction() as conn:
            candidates = conn.execute(
                """
                SELECT u.id, u.reg_number, u.full_name
                FROM enrollments e
                JOIN users u ON u.id = e.student_id
                WHERE e.course_id = ? AND u.role = 'student'
                ORDER BY COALESCE(u.reg_number, u.username)
                """,
                (assessment["course_id"],),
            ).fetchall()
            if not candidates:
                raise AppError("No active enrolled students were found for this assessment.")
            conn.execute(
                """
                INSERT INTO exam_sessions
                (id, assessment_id, exam_at, venue, status, candidate_count, created_by, created_at)
                VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?)
                """,
                (session_id, assessment_id, normalized_exam_at, venue, len(candidates), user_id, now),
            )
            conn.executemany(
                """
                INSERT INTO exam_session_candidates
                (session_id, student_id, reg_number_snapshot, full_name_snapshot)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (session_id, int(row["id"]), row["reg_number"], row["full_name"])
                    for row in candidates
                ],
            )
            self.app._audit(
                conn,
                "EXAM_SESSION",
                session_id,
                user_id,
                "EXAM_SESSION_CREATED",
                {
                    "assessment_id": assessment_id,
                    "candidate_count": len(candidates),
                    "venue": venue,
                    "exam_at": normalized_exam_at,
                },
            )
        return {"session_id": session_id, "candidate_count": len(candidates), "status": "OPEN"}

    def record_attendance(
        self,
        user_id: int,
        session_id: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        _actor, session = self._authorize_session(user_id, session_id)
        if session["status"] != "OPEN":
            raise AppError("Attendance is locked because this examination session is closed.", 409)
        if not isinstance(items, list) or not items or len(items) > 5000:
            raise AppError("Provide between 1 and 5,000 attendance records.")
        allowed = ATTENDANCE_STATES
        prepared = []
        seen: set[int] = set()
        for item in items:
            try:
                student_id = int(item.get("student_id"))
            except (TypeError, ValueError) as exc:
                raise AppError("Each attendance record needs a valid candidate ID.") from exc
            if student_id in seen:
                raise AppError("The attendance submission contains a duplicate candidate.")
            seen.add(student_id)
            status = str(item.get("attendance_status", "")).upper()
            if status not in allowed:
                raise AppError("Attendance status must be PRESENT, ABSENT, EXCUSED or CONTESTED.")
            signature = item.get("signature_present", False)
            card = item.get("exam_card_seen", False)
            identity = item.get("student_id_seen", False)
            if not all(isinstance(value, bool) for value in (signature, card, identity)):
                raise AppError("Signature, exam-card and student-ID checks must be true/false values.")
            if status != "PRESENT" and signature:
                raise AppError("Only a PRESENT candidate can have a recorded attendance signature.")
            note = str(item.get("note", "")).strip()
            if len(note) > 1000:
                raise AppError("Attendance notes must be 1,000 characters or fewer.")
            prepared.append((student_id, status, int(signature), int(card), int(identity), note))

        now = utc_now()
        with self.db.transaction() as conn:
            for student_id, status, signature, card, identity, note in prepared:
                candidate = conn.execute(
                    """
                    SELECT 1 FROM exam_session_candidates
                    WHERE session_id = ? AND student_id = ?
                    """,
                    (session_id, student_id),
                ).fetchone()
                if not candidate:
                    raise AppError("One or more candidates are not in the locked examination roster.", 409)
                previous = conn.execute(
                    """
                    SELECT attendance_status, signature_present, exam_card_seen, student_id_seen
                    FROM exam_attendance WHERE session_id = ? AND student_id = ?
                    """,
                    (session_id, student_id),
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO exam_attendance
                    (session_id, student_id, attendance_status, signature_present,
                     exam_card_seen, student_id_seen, note, recorded_by, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, student_id) DO UPDATE SET
                        attendance_status = excluded.attendance_status,
                        signature_present = excluded.signature_present,
                        exam_card_seen = excluded.exam_card_seen,
                        student_id_seen = excluded.student_id_seen,
                        note = excluded.note,
                        recorded_by = excluded.recorded_by,
                        recorded_at = excluded.recorded_at
                    """,
                    (session_id, student_id, status, signature, card, identity, note, user_id, now),
                )
                self.app._audit(
                    conn,
                    "EXAM_ATTENDANCE",
                    f"{session_id}:{student_id}",
                    user_id,
                    "EXAM_ATTENDANCE_RECORDED" if previous is None else "EXAM_ATTENDANCE_CORRECTED",
                    {
                        "assessment_id": session["assessment_id"],
                        "old_status": previous["attendance_status"] if previous else None,
                        "new_status": status,
                        "signature_present": bool(signature),
                        "exam_card_seen": bool(card),
                        "student_id_seen": bool(identity),
                        "reason": note,
                    },
                )
        return {"saved": len(prepared), "recorded_at": now}

    def close_session(self, user_id: int, session_id: str) -> dict[str, Any]:
        _actor, session = self._authorize_session(user_id, session_id)
        with self.db.transaction() as conn:
            missing = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM exam_session_candidates c
                LEFT JOIN exam_attendance a
                  ON a.session_id = c.session_id AND a.student_id = c.student_id
                WHERE c.session_id = ? AND a.student_id IS NULL
                """,
                (session_id,),
            ).fetchone()["count"]
            if int(missing):
                raise AppError(
                    f"Cannot close this register yet: {missing} candidate attendance decisions are not recorded.",
                    409,
                )
            conn.execute(
                """
                UPDATE exam_sessions
                SET status = 'CLOSED', closed_by = ?, closed_at = ?
                WHERE id = ? AND status = 'OPEN'
                """,
                (user_id, utc_now(), session_id),
            )
            self.app._audit(
                conn, "EXAM_SESSION", session_id, user_id, "EXAM_SESSION_CLOSED",
                {"assessment_id": session["assessment_id"]},
            )
        return {"session_id": session_id, "status": "CLOSED"}

    def receive_script(
        self,
        user_id: int,
        session_id: str,
        student_id: int | None,
        script_ref: str,
        note: str = "",
    ) -> dict[str, Any]:
        _actor, session = self._authorize_session(user_id, session_id)
        if not script_ref.strip() or len(script_ref.strip()) > 80:
            raise AppError("Enter a unique script reference of at most 80 characters.")
        if len(note) > 1000:
            raise AppError("Script notes must be 1,000 characters or fewer.")
        if student_id is None and not note.strip():
            raise AppError("An unidentified script needs an incident note explaining why it could not be matched.")
        with self.db.transaction() as conn:
            candidate = None
            if student_id is not None:
                candidate = conn.execute(
                    """
                    SELECT 1 FROM exam_session_candidates
                    WHERE session_id = ? AND student_id = ?
                    """,
                    (session_id, student_id),
                ).fetchone()
                if not candidate:
                    raise AppError("This student is not in the examination roster.", 404)
            script_id = "script-" + uuid.uuid4().hex
            now = utc_now()
            initial_status = "RECEIVED" if student_id is not None else "FLAGGED"
            try:
                conn.execute(
                    """
                    INSERT INTO exam_scripts
                    (id, session_id, student_id, script_ref, status, current_custodian,
                     notes, received_by, received_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (script_id, session_id, student_id, script_ref.strip(), initial_status, user_id, note.strip(), user_id, now),
                )
            except Exception as exc:
                if "UNIQUE" in str(exc).upper():
                    raise AppError("A script is already recorded for this candidate or this script reference is already used.") from exc
                raise
            conn.execute(
                """
                INSERT INTO exam_script_events
                (script_id, event_type, actor_id, note, created_at)
                VALUES (?, 'RECEIVED', ?, ?, ?)
                """,
                (script_id, user_id, note.strip(), now),
            )
            if student_id is None:
                conn.execute(
                    """
                    INSERT INTO exam_script_events
                    (script_id, event_type, actor_id, note, created_at)
                    VALUES (?, 'FLAGGED', ?, ?, ?)
                    """,
                    (script_id, user_id, "Script received without a verified candidate match.", now),
                )
            self.app._audit(
                conn,
                "EXAM_SCRIPT",
                script_id,
                user_id,
                "EXAM_SCRIPT_RECEIVED",
                {"session_id": session_id, "assessment_id": session["assessment_id"], "script_ref": script_ref.strip()},
            )
        return {"script_id": script_id, "status": initial_status, "received_at": now, "unidentified": student_id is None}

    def link_unidentified_script(self, user_id: int, script_id: str, student_id: int, reason: str) -> dict[str, Any]:
        actor = self.app.require_role(user_id, {"reviewer", "exam_office", "admin"})
        reason = reason.strip()
        if len(reason) < 8 or len(reason) > 1000:
            raise AppError("Provide an evidence-based identity-matching reason (8–1,000 characters).")
        with self.db.transaction() as conn:
            script = conn.execute(
                """SELECT s.*, x.assessment_id, c.lecturer_id
                   FROM exam_scripts s JOIN exam_sessions x ON x.id = s.session_id
                   JOIN assessments a ON a.id = x.assessment_id
                   JOIN courses c ON c.id = a.course_id WHERE s.id = ?""",
                (script_id,),
            ).fetchone()
            if not script:
                raise AppError("Script not found.", 404)
            if script["student_id"] is not None:
                raise AppError("This script is already linked to a candidate.", 409)
            candidate = conn.execute(
                "SELECT 1 FROM exam_session_candidates WHERE session_id = ? AND student_id = ?",
                (script["session_id"], student_id),
            ).fetchone()
            if not candidate:
                raise AppError("The selected candidate is not in this session's locked roster.", 404)
            existing = conn.execute(
                "SELECT 1 FROM exam_scripts WHERE session_id = ? AND student_id = ?",
                (script["session_id"], student_id),
            ).fetchone()
            if existing:
                raise AppError("A different script is already linked to this candidate.", 409)
            conn.execute(
                "UPDATE exam_scripts SET student_id = ?, status = 'RECEIVED', notes = ? WHERE id = ?",
                (student_id, reason, script_id),
            )
            conn.execute(
                """INSERT INTO exam_script_events
                   (script_id, event_type, actor_id, note, created_at)
                   VALUES (?, 'FLAGGED', ?, ?, ?)""",
                (script_id, user_id, "Identity linked after review: " + reason, utc_now()),
            )
            self.app._audit(
                conn, "EXAM_SCRIPT", script_id, user_id, "EXAM_SCRIPT_IDENTITY_LINKED",
                {"assessment_id": script["assessment_id"], "student_id": student_id, "reason": reason},
            )
        return {"script_id": script_id, "student_id": student_id, "status": "RECEIVED"}

    def request_script_handoff(
        self,
        user_id: int,
        script_id: str,
        recipient_id: int,
        note: str = "",
    ) -> dict[str, Any]:
        self._require_staff(user_id)
        if recipient_id == user_id:
            raise AppError("Choose another staff member to receive the script.")
        if len(note) > 1000:
            raise AppError("Handover notes must be 1,000 characters or fewer.")
        conn = self.db.connect()
        try:
            script = conn.execute(
                """
                SELECT s.*, x.assessment_id, c.lecturer_id
                FROM exam_scripts s
                JOIN exam_sessions x ON x.id = s.session_id
                JOIN assessments a ON a.id = x.assessment_id
                JOIN courses c ON c.id = a.course_id
                WHERE s.id = ?
                """,
                (script_id,),
            ).fetchone()
            recipient = conn.execute(
                "SELECT id, role, active FROM users WHERE id = ?",
                (recipient_id,),
            ).fetchone()
        finally:
            conn.close()
        if not script:
            raise AppError("Script not found.", 404)
        actor = self.app.user(user_id)
        if actor["role"] == "lecturer" and int(script["lecturer_id"] or 0) != user_id:
            raise AppError("You do not manage this script.", 403)
        if not recipient or recipient["role"] not in STAFF_ROLES or not recipient["active"]:
            raise AppError("The selected recipient is not an active staff account.")
        if int(script["current_custodian"]) != user_id:
            raise AppError("Only the current script custodian can initiate a handover.", 409)
        if script["status"] == "HANDOFF_PENDING":
            raise AppError("This script already has a handover awaiting acceptance.", 409)
        if script["status"] == "MARKED":
            raise AppError("A marked script cannot be transferred in this workflow.", 409)

        now = utc_now()
        with self.db.transaction() as tx:
            tx.execute(
                """
                UPDATE exam_scripts
                SET status = 'HANDOFF_PENDING', pending_custodian = ?
                WHERE id = ?
                """,
                (recipient_id, script_id),
            )
            tx.execute(
                """
                INSERT INTO exam_script_events
                (script_id, event_type, actor_id, recipient_id, note, created_at)
                VALUES (?, 'HANDOFF_REQUESTED', ?, ?, ?, ?)
                """,
                (script_id, user_id, recipient_id, note.strip(), now),
            )
            self.app._audit(
                tx, "EXAM_SCRIPT", script_id, user_id, "EXAM_SCRIPT_HANDOFF_REQUESTED",
                {"recipient_id": recipient_id},
            )
            self.app._notify(
                tx, recipient_id, "SCRIPT_HANDOFF",
                "Script handover awaiting acceptance",
                "A script has been assigned to you for an examination. Review and accept custody in MarkTrail.",
                now,
            )
        return {"script_id": script_id, "status": "HANDOFF_PENDING", "recipient_id": recipient_id}

    def accept_script_handoff(self, user_id: int, script_id: str) -> dict[str, Any]:
        actor = self._require_staff(user_id)
        now = utc_now()
        with self.db.transaction() as conn:
            script = conn.execute(
                "SELECT * FROM exam_scripts WHERE id = ?",
                (script_id,),
            ).fetchone()
            if not script:
                raise AppError("Script not found.", 404)
            if script["status"] != "HANDOFF_PENDING" or int(script["pending_custodian"] or 0) != user_id:
                raise AppError("There is no handover for this script awaiting your acceptance.", 409)
            conn.execute(
                """
                UPDATE exam_scripts
                SET current_custodian = ?, pending_custodian = NULL, status = 'ASSIGNED'
                WHERE id = ?
                """,
                (user_id, script_id),
            )
            conn.execute(
                """
                INSERT INTO exam_script_events
                (script_id, event_type, actor_id, note, created_at)
                VALUES (?, 'HANDOFF_ACCEPTED', ?, '', ?)
                """,
                (script_id, user_id, now),
            )
            self.app._audit(
                conn, "EXAM_SCRIPT", script_id, user_id, "EXAM_SCRIPT_HANDOFF_ACCEPTED",
                {"previous_custodian": int(script["current_custodian"])},
            )
        return {"script_id": script_id, "status": "ASSIGNED", "custodian": actor["full_name"]}

    def mark_script(self, user_id: int, script_id: str, note: str = "") -> dict[str, Any]:
        self._require_staff(user_id)
        if len(note) > 1000:
            raise AppError("Marking notes must be 1,000 characters or fewer.")
        now = utc_now()
        with self.db.transaction() as conn:
            script = conn.execute(
                """
                SELECT s.*, x.assessment_id, c.lecturer_id
                FROM exam_scripts s
                JOIN exam_sessions x ON x.id = s.session_id
                JOIN assessments a ON a.id = x.assessment_id
                JOIN courses c ON c.id = a.course_id
                WHERE s.id = ?
                """,
                (script_id,),
            ).fetchone()
            if not script:
                raise AppError("Script not found.", 404)
            actor = self.app.user(user_id)
            if actor["role"] == "lecturer" and int(script["lecturer_id"] or 0) != user_id:
                raise AppError("You do not manage this script.", 403)
            if script["student_id"] is None:
                raise AppError("Resolve the script's candidate identity before recording marking completion.", 409)
            if int(script["current_custodian"]) != user_id:
                raise AppError("Only the current script custodian can record marking completion.", 403)
            if script["status"] == "HANDOFF_PENDING":
                raise AppError("Accept or cancel the pending handover before marking this script.", 409)
            if script["status"] == "MARKED":
                raise AppError("This script is already recorded as marked.", 409)
            conn.execute(
                """
                UPDATE exam_scripts
                SET status = 'MARKED', marked_by = ?, marked_at = ?, notes =
                    CASE WHEN ? = '' THEN notes ELSE ? END
                WHERE id = ?
                """,
                (user_id, now, note.strip(), note.strip(), script_id),
            )
            conn.execute(
                """
                INSERT INTO exam_script_events
                (script_id, event_type, actor_id, note, created_at)
                VALUES (?, 'MARKED', ?, ?, ?)
                """,
                (script_id, user_id, note.strip(), now),
            )
            self.app._audit(
                conn, "EXAM_SCRIPT", script_id, user_id, "EXAM_SCRIPT_MARKED",
                {"assessment_id": script["assessment_id"]},
            )
        return {"script_id": script_id, "status": "MARKED", "marked_at": now}

    def _exceptions_for(self, candidate: dict[str, Any], session_closed: bool) -> list[dict[str, str]]:
        attendance = candidate.get("attendance")
        script = candidate.get("script")
        mark = candidate.get("mark")
        issues: list[dict[str, str]] = []

        if attendance is None:
            if session_closed:
                issues.append({"code": "ATTENDANCE_NOT_RECORDED", "severity": "high"})
        else:
            state = attendance["attendance_status"]
            if state == "CONTESTED":
                issues.append({"code": "ATTENDANCE_DISPUTED", "severity": "high"})
            if state == "PRESENT" and not attendance["signature_present"]:
                issues.append({"code": "ATTENDANCE_SIGNATURE_MISSING", "severity": "medium"})
            if state == "PRESENT" and not attendance["exam_card_seen"]:
                issues.append({"code": "EXAM_CARD_CHECK_NOT_RECORDED", "severity": "low"})
            if state == "PRESENT" and not attendance["student_id_seen"]:
                issues.append({"code": "STUDENT_ID_CHECK_NOT_RECORDED", "severity": "low"})
            if state == "PRESENT" and script is None:
                issues.append({"code": "SCRIPT_NOT_RECEIVED", "severity": "high"})
            if state == "ABSENT" and script is not None:
                issues.append({"code": "SCRIPT_RECEIVED_FOR_RECORDED_ABSENT", "severity": "high"})

        if script is not None:
            if attendance is None:
                issues.append({"code": "SCRIPT_WITHOUT_ATTENDANCE", "severity": "high"})
            if script["status"] == "HANDOFF_PENDING":
                issues.append({"code": "SCRIPT_HANDOFF_NOT_ACCEPTED", "severity": "medium"})
            elif script["status"] != "MARKED":
                issues.append({"code": "SCRIPT_NOT_MARKED", "severity": "high"})
            elif mark is None or mark["candidate_status"] != "RECORDED" or mark["candidate_mark"] is None:
                issues.append({"code": "MARK_ENTRY_NOT_FOUND", "severity": "high"})

        if mark is not None and mark["candidate_status"] == "RECORDED":
            if attendance is not None and attendance["attendance_status"] == "ABSENT":
                issues.append({"code": "MARK_RECORDED_FOR_RECORDED_ABSENT", "severity": "high"})
            if attendance is not None and attendance["attendance_status"] == "PRESENT" and script is None:
                issues.append({"code": "MARK_WITHOUT_SCRIPT_RECEIPT", "severity": "medium"})

        return issues

    def session_detail(self, user_id: int, session_id: str) -> dict[str, Any]:
        _actor, session = self._authorize_session(user_id, session_id)
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT c.student_id, c.reg_number_snapshot, c.full_name_snapshot,
                       a.attendance_status, a.signature_present, a.exam_card_seen,
                       a.student_id_seen, a.note AS attendance_note, a.recorded_at,
                       a.recorded_by,
                       s.id AS script_id, s.script_ref, s.status AS script_status,
                       s.current_custodian, s.pending_custodian, s.received_at,
                       s.marked_by, s.marked_at, s.notes AS script_note,
                       m.candidate_mark, m.candidate_status
                FROM exam_session_candidates c
                LEFT JOIN exam_attendance a
                  ON a.session_id = c.session_id AND a.student_id = c.student_id
                LEFT JOIN exam_scripts s
                  ON s.session_id = c.session_id AND s.student_id = c.student_id
                LEFT JOIN assessment_marks m
                  ON m.assessment_id = ? AND m.student_id = c.student_id
                WHERE c.session_id = ?
                ORDER BY COALESCE(c.reg_number_snapshot, CAST(c.student_id AS TEXT))
                """,
                (session["assessment_id"], session_id),
            ).fetchall()
            candidates = []
            exceptions = []
            for row in rows:
                data = dict(row)
                attendance = None
                if row["attendance_status"] is not None:
                    attendance = {
                        "attendance_status": row["attendance_status"],
                        "signature_present": bool(row["signature_present"]),
                        "exam_card_seen": bool(row["exam_card_seen"]),
                        "student_id_seen": bool(row["student_id_seen"]),
                        "note": row["attendance_note"],
                        "recorded_at": row["recorded_at"],
                        "recorded_by": row["recorded_by"],
                    }
                script = None
                if row["script_id"] is not None:
                    script = {
                        "id": row["script_id"],
                        "script_ref": row["script_ref"],
                        "status": row["script_status"],
                        "current_custodian": row["current_custodian"],
                        "pending_custodian": row["pending_custodian"],
                        "received_at": row["received_at"],
                        "marked_by": row["marked_by"],
                        "marked_at": row["marked_at"],
                        "note": row["script_note"],
                    }
                mark = None
                if row["candidate_status"] is not None:
                    mark = {
                        "candidate_mark": row["candidate_mark"],
                        "candidate_status": row["candidate_status"],
                    }
                candidate = {
                    "student_id": int(row["student_id"]),
                    "registration_number": row["reg_number_snapshot"],
                    "full_name": row["full_name_snapshot"],
                    "attendance": attendance,
                    "script": script,
                    "mark": mark,
                }
                candidate["issues"] = self._exceptions_for(candidate, session["status"] == "CLOSED")
                for issue in candidate["issues"]:
                    exceptions.append({
                        "student_id": candidate["student_id"],
                        "registration_number": candidate["registration_number"],
                        "full_name": candidate["full_name"],
                        **issue,
                    })
                candidates.append(candidate)

            orphan_rows = conn.execute(
                """SELECT id, script_ref, status, current_custodian, received_at, notes
                   FROM exam_scripts WHERE session_id = ? AND student_id IS NULL
                   ORDER BY received_at""",
                (session_id,),
            ).fetchall()
            unidentified_scripts = [dict(row) for row in orphan_rows]
            for orphan in unidentified_scripts:
                exceptions.append({
                    "student_id": None,
                    "registration_number": None,
                    "full_name": "Unidentified script",
                    "script_ref": orphan["script_ref"],
                    "code": "SCRIPT_UNIDENTIFIED",
                    "severity": "high",
                })
            total = len(candidates)
            attendance_count = sum(1 for c in candidates if c["attendance"] is not None)
            script_count = sum(1 for c in candidates if c["script"] is not None)
            marked_count = sum(1 for c in candidates if c["script"] and c["script"]["status"] == "MARKED")
            return {
                "session": {
                    "id": session["id"],
                    "assessment_id": session["assessment_id"],
                    "assessment": session["assessment_name"],
                    "course": session["course_code"] + " · " + session["course_title"],
                    "exam_at": session["exam_at"],
                    "venue": session["venue"],
                    "status": session["status"],
                    "candidate_count": int(session["candidate_count"]),
                    "created_at": session["created_at"],
                },
                "summary": {
                    "candidates": total,
                    "attendance_recorded": attendance_count,
                    "scripts_received": script_count,
                    "scripts_marked": marked_count,
                    "exceptions": len(exceptions),
                },
                "candidates": candidates,
                "unidentified_scripts": unidentified_scripts,
                "exceptions": exceptions,
            }
        finally:
            conn.close()

    def staff_options(self, user_id: int) -> list[dict[str, Any]]:
        self._require_staff(user_id)
        conn = self.db.connect()
        try:
            return [
                dict(row) for row in conn.execute(
                    """
                    SELECT id, full_name, role
                    FROM users
                    WHERE active = 1 AND role IN (
                        'lecturer','reviewer','exam_office','portal_operator','admin'
                    )
                    ORDER BY full_name
                    """
                ).fetchall()
            ]
        finally:
            conn.close()

    def assessment_detail(self, user_id: int, assessment_id: str) -> dict[str, Any]:
        _actor, assessment = self._authorize_assessment(user_id, assessment_id)
        conn = self.db.connect()
        try:
            sessions = [
                dict(row) for row in conn.execute(
                    """
                    SELECT s.id, s.exam_at, s.venue, s.status, s.candidate_count, s.created_at,
                           u.full_name AS created_by_name
                    FROM exam_sessions s
                    JOIN users u ON u.id = s.created_by
                    WHERE s.assessment_id = ?
                    ORDER BY s.created_at DESC
                    """,
                    (assessment_id,),
                ).fetchall()
            ]
        finally:
            conn.close()
        return {
            "assessment": {
                "id": assessment["id"],
                "name": assessment["name"],
                "max_mark": assessment["max_mark"],
                "course": assessment["course_code"] + " · " + assessment["course_title"],
                "enrolled_count": int(assessment["enrolled_count"]),
            },
            "sessions": sessions,
        }
