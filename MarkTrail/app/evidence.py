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

    def _migrate_legacy_schema(self, conn) -> None:
        script_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'exam_scripts'"
        ).fetchone()
        event_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'exam_script_events'"
        ).fetchone()

        script_sql = (script_row["sql"] or "").upper() if script_row else ""
        event_sql = (event_row["sql"] or "").upper() if event_row else ""
        session_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'exam_sessions'"
        ).fetchone()
        session_columns = (
            {row["name"] for row in conn.execute("PRAGMA table_info(exam_sessions)").fetchall()}
            if session_exists else set()
        )
        add_session_type = bool(session_exists and "session_type" not in session_columns)
        rebuild_scripts = bool(script_row and "STUDENT_ID INTEGER NOT NULL" in script_sql)
        rebuild_events = bool(event_row and "IDENTITY_LINKED" not in event_sql)
        if not rebuild_scripts and not rebuild_events and not add_session_type:
            return

        # Toggle foreign-key enforcement outside the migration transaction. The
        # child event table keeps referencing the stable exam_scripts table name.
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute("BEGIN IMMEDIATE")
            if add_session_type:
                conn.execute(
                    """
                    ALTER TABLE exam_sessions
                    ADD COLUMN session_type TEXT NOT NULL DEFAULT 'UNCLASSIFIED'
                    CHECK (
                        session_type IN (
                            'CAT','COURSEWORK','PRACTICAL',
                            'FINAL_EXAM','SPECIAL_EXAM','UNCLASSIFIED'
                        )
                    )
                    """
                )
            if rebuild_scripts:
                conn.execute(
                    """
                    CREATE TABLE exam_scripts_new (
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
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO exam_scripts_new
                    (id, session_id, student_id, script_ref, status, current_custodian,
                     pending_custodian, notes, received_by, received_at, marked_by, marked_at)
                    SELECT id, session_id, student_id, script_ref, status, current_custodian,
                           pending_custodian, notes, received_by, received_at, marked_by, marked_at
                    FROM exam_scripts
                    """
                )
                conn.execute("DROP TABLE exam_scripts")
                conn.execute("ALTER TABLE exam_scripts_new RENAME TO exam_scripts")

            if rebuild_events:
                conn.execute(
                    """
                    CREATE TABLE exam_script_events_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        script_id TEXT NOT NULL REFERENCES exam_scripts(id) ON DELETE CASCADE,
                        event_type TEXT NOT NULL CHECK (
                            event_type IN (
                                'RECEIVED','HANDOFF_REQUESTED','HANDOFF_ACCEPTED',
                                'MARKED','FLAGGED','IDENTITY_LINKED'
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
                    INSERT INTO exam_script_events_new
                    (id, script_id, event_type, actor_id, recipient_id, note, created_at)
                    SELECT id, script_id, event_type, actor_id, recipient_id, note, created_at
                    FROM exam_script_events
                    """
                )
                conn.execute("DROP TABLE exam_script_events")
                conn.execute("ALTER TABLE exam_script_events_new RENAME TO exam_script_events")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    def _ensure_schema(self) -> None:
        conn = self.db.connect()
        try:
            self._migrate_legacy_schema(conn)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS exam_sessions (
                    id TEXT PRIMARY KEY,
                    assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
                    exam_at TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    session_type TEXT NOT NULL DEFAULT 'UNCLASSIFIED' CHECK (
                        session_type IN (
                            'CAT','COURSEWORK','PRACTICAL',
                            'FINAL_EXAM','SPECIAL_EXAM','UNCLASSIFIED'
                        )
                    ),
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

                CREATE TABLE IF NOT EXISTS exam_card_signoffs (
                    session_id TEXT NOT NULL,
                    student_id INTEGER NOT NULL,
                    signed_by INTEGER NOT NULL REFERENCES users(id),
                    signed_at TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (session_id, student_id),
                    FOREIGN KEY (session_id, student_id)
                        REFERENCES exam_session_candidates(session_id, student_id)
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS exam_card_signoff_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    student_id INTEGER NOT NULL,
                    actor_id INTEGER NOT NULL REFERENCES users(id),
                    event_type TEXT NOT NULL CHECK (event_type IN ('PHYSICAL_CARD_SIGNED')),
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id, student_id)
                        REFERENCES exam_session_candidates(session_id, student_id)
                        ON DELETE RESTRICT
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
                            'MARKED','FLAGGED','IDENTITY_LINKED'
                        )
                    ),
                    actor_id INTEGER NOT NULL REFERENCES users(id),
                    recipient_id INTEGER REFERENCES users(id),
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS exam_session_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES exam_sessions(id) ON DELETE RESTRICT,
                    event_type TEXT NOT NULL CHECK (event_type IN ('SESSION_CREATED','REGISTER_CLOSED')),
                    actor_id INTEGER NOT NULL REFERENCES users(id),
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS exam_attendance_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    student_id INTEGER NOT NULL,
                    actor_id INTEGER NOT NULL REFERENCES users(id),
                    event_type TEXT NOT NULL CHECK (event_type IN ('RECORDED','CORRECTED')),
                    old_state_json TEXT,
                    new_state_json TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id, student_id)
                        REFERENCES exam_session_candidates(session_id, student_id)
                        ON DELETE RESTRICT
                );

                CREATE TRIGGER IF NOT EXISTS exam_card_signoff_events_no_update
                BEFORE UPDATE ON exam_card_signoff_events
                BEGIN
                    SELECT RAISE(ABORT, 'exam card sign-off history is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS exam_card_signoff_events_no_delete
                BEFORE DELETE ON exam_card_signoff_events
                BEGIN
                    SELECT RAISE(ABORT, 'exam card sign-off history is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS exam_session_events_no_update
                BEFORE UPDATE ON exam_session_events
                BEGIN
                    SELECT RAISE(ABORT, 'exam session history is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS exam_session_events_no_delete
                BEFORE DELETE ON exam_session_events
                BEGIN
                    SELECT RAISE(ABORT, 'exam session history is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS exam_attendance_events_no_update
                BEFORE UPDATE ON exam_attendance_events
                BEGIN
                    SELECT RAISE(ABORT, 'attendance history is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS exam_attendance_events_no_delete
                BEFORE DELETE ON exam_attendance_events
                BEGIN
                    SELECT RAISE(ABORT, 'attendance history is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS exam_script_events_no_update
                BEFORE UPDATE ON exam_script_events
                BEGIN
                    SELECT RAISE(ABORT, 'script custody history is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS exam_script_events_no_delete
                BEFORE DELETE ON exam_script_events
                BEGIN
                    SELECT RAISE(ABORT, 'script custody history is append-only');
                END;

                CREATE TABLE IF NOT EXISTS evidence_cases (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES exam_sessions(id) ON DELETE RESTRICT,
                    assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE RESTRICT,
                    student_id INTEGER REFERENCES users(id) ON DELETE RESTRICT,
                    script_id TEXT REFERENCES exam_scripts(id) ON DELETE RESTRICT,
                    subject_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL CHECK (severity IN ('high','medium','low')),
                    status TEXT NOT NULL CHECK (
                        status IN ('OPEN','EVIDENCE_CLEARED','RESOLVED','DISMISSED')
                    ),
                    assigned_role TEXT NOT NULL CHECK (
                        assigned_role IN ('lecturer','reviewer','exam_office','admin')
                    ),
                    assigned_user_id INTEGER REFERENCES users(id),
                    opened_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_detected_at TEXT NOT NULL,
                    evidence_cleared_at TEXT,
                    resolved_at TEXT,
                    resolved_by INTEGER REFERENCES users(id),
                    resolution_note TEXT NOT NULL DEFAULT '',
                    UNIQUE (session_id, subject_key, category)
                );

                CREATE TABLE IF NOT EXISTS evidence_case_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL REFERENCES evidence_cases(id) ON DELETE RESTRICT,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN (
                            'OPENED','UPDATED','EVIDENCE_CLEARED','REOPENED',
                            'ASSIGNED','RESOLVED','DISMISSED'
                        )
                    ),
                    actor_id INTEGER REFERENCES users(id),
                    note TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TRIGGER IF NOT EXISTS evidence_case_events_no_update
                BEFORE UPDATE ON evidence_case_events
                BEGIN
                    SELECT RAISE(ABORT, 'evidence case history is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS evidence_case_events_no_delete
                BEFORE DELETE ON evidence_case_events
                BEGIN
                    SELECT RAISE(ABORT, 'evidence case history is append-only');
                END;

                CREATE INDEX IF NOT EXISTS idx_evidence_cases_student
                    ON evidence_cases(student_id, status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_evidence_cases_assignment
                    ON evidence_cases(assigned_role, assigned_user_id, status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_evidence_cases_session
                    ON evidence_cases(session_id, status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_evidence_case_events_case
                    ON evidence_case_events(case_id, created_at, id);

                CREATE INDEX IF NOT EXISTS idx_exam_sessions_assessment
                    ON exam_sessions(assessment_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_exam_card_signoffs_session
                    ON exam_card_signoffs(session_id, student_id);
                CREATE INDEX IF NOT EXISTS idx_exam_card_signoff_events_session
                    ON exam_card_signoff_events(session_id, created_at, id);

                CREATE INDEX IF NOT EXISTS idx_exam_candidates_student
                    ON exam_session_candidates(student_id, session_id);
                CREATE INDEX IF NOT EXISTS idx_exam_scripts_custodian
                    ON exam_scripts(current_custodian, status);
                CREATE INDEX IF NOT EXISTS idx_exam_script_events_script
                    ON exam_script_events(script_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_exam_attendance_events_session
                    ON exam_attendance_events(session_id, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_exam_session_events_session
                    ON exam_session_events(session_id, created_at, id);
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
        session_type: str = "UNCLASSIFIED",
    ) -> dict[str, Any]:
        actor, assessment = self._authorize_assessment(user_id, assessment_id)
        allowed_session_types = {
            "CAT", "COURSEWORK", "PRACTICAL", "FINAL_EXAM", "SPECIAL_EXAM", "UNCLASSIFIED"
        }
        session_type = str(session_type or "UNCLASSIFIED").upper()
        if session_type not in allowed_session_types:
            raise AppError("Session type must be CAT, COURSEWORK, PRACTICAL, FINAL_EXAM or SPECIAL_EXAM.")
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
                (id, assessment_id, exam_at, venue, session_type, status,
                 candidate_count, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
                """,
                (session_id, assessment_id, normalized_exam_at, venue, session_type,
                 len(candidates), user_id, now),
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
            conn.execute(
                """
                INSERT INTO exam_session_events
                (session_id, event_type, actor_id, metadata_json, created_at)
                VALUES (?, 'SESSION_CREATED', ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    json.dumps({
                        "assessment_id": assessment_id,
                        "candidate_count": len(candidates),
                        "venue": venue,
                        "exam_at": normalized_exam_at,
                        "session_type": session_type,
                    }, sort_keys=True),
                    now,
                ),
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
                    "session_type": session_type,
                },
            )
        return {
            "session_id": session_id,
            "candidate_count": len(candidates),
            "session_type": session_type,
            "status": "OPEN",
        }

    def record_attendance(
        self,
        user_id: int,
        session_id: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        actor, session = self._authorize_session(user_id, session_id)
        correction_mode = session["status"] == "CLOSED"
        if correction_mode and actor["role"] not in {"reviewer", "admin"}:
            raise AppError("Only a reviewer or administrator can correct attendance after register closure.", 403)
        if not isinstance(items, list) or not items or len(items) > 5000:
            raise AppError("Provide between 1 and 5,000 attendance records.")
        allowed = ATTENDANCE_STATES
        prepared = []
        seen: set[int] = set()
        for item in items:
            if not isinstance(item, dict):
                raise AppError("Each attendance record must be an object with a candidate ID and decision.")
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
            note = str(item.get("note") or "").strip()
            if len(note) > 1000:
                raise AppError("Attendance notes must be 1,000 characters or fewer.")
            if status in {"ABSENT", "EXCUSED", "CONTESTED"} and len(note) < 8:
                raise AppError(f"{status.title()} attendance decisions require an 8-character reason.")
            if correction_mode and len(note) < 8:
                raise AppError("Closed-register corrections require an 8-character reason.")
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
                new_state = {
                    "attendance_status": status,
                    "signature_present": bool(signature),
                    "exam_card_seen": bool(card),
                    "student_id_seen": bool(identity),
                    "note": note,
                }
                conn.execute(
                    """
                    INSERT INTO exam_attendance_events
                    (session_id, student_id, actor_id, event_type, old_state_json,
                     new_state_json, reason, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        student_id,
                        user_id,
                        "CORRECTED" if previous is not None or correction_mode else "RECORDED",
                        json.dumps(dict(previous), sort_keys=True) if previous else None,
                        json.dumps(new_state, sort_keys=True),
                        note,
                        now,
                    ),
                )
                self.app._audit(
                    conn,
                    "EXAM_ATTENDANCE",
                    f"{session_id}:{student_id}",
                    user_id,
                    "EXAM_ATTENDANCE_CORRECTED" if previous is not None or correction_mode else "EXAM_ATTENDANCE_RECORDED",
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
        self._sync_session_cases(user_id, session_id)
        return {"saved": len(prepared), "recorded_at": now}

    def close_session(self, user_id: int, session_id: str) -> dict[str, Any]:
        _actor, session = self._authorize_session(user_id, session_id)
        if session["status"] != "OPEN":
            raise AppError("This attendance register is already closed.", 409)
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
            conn.execute(
                """
                INSERT INTO exam_session_events
                (session_id, event_type, actor_id, metadata_json, created_at)
                VALUES (?, 'REGISTER_CLOSED', ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    json.dumps({"assessment_id": session["assessment_id"]}, sort_keys=True),
                    utc_now(),
                ),
            )
            self.app._audit(
                conn, "EXAM_SESSION", session_id, user_id, "EXAM_SESSION_CLOSED",
                {"assessment_id": session["assessment_id"]},
            )
        self._sync_session_cases(user_id, session_id)
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
        if student_id is None and len(note.strip()) < 8:
            raise AppError("An unidentified script needs an incident note explaining why it could not be matched.")
        if session["status"] == "CLOSED" and len(note.strip()) < 8:
            raise AppError("Scripts received after register closure require an 8-character reason.")
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
        self._sync_session_cases(user_id, session_id)
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
                   VALUES (?, 'IDENTITY_LINKED', ?, ?, ?)""",
                (script_id, user_id, "Identity linked after review: " + reason, utc_now()),
            )
            self.app._audit(
                conn, "EXAM_SCRIPT", script_id, user_id, "EXAM_SCRIPT_IDENTITY_LINKED",
                {"assessment_id": script["assessment_id"], "student_id": student_id, "reason": reason},
            )
        self._sync_session_cases(user_id, script["session_id"])
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
        self._sync_session_cases(user_id, script["session_id"])
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
                (script_id, event_type, actor_id, recipient_id, note, created_at)
                VALUES (?, 'HANDOFF_ACCEPTED', ?, ?, '', ?)
                """,
                (script_id, user_id, int(script["current_custodian"]), now),
            )
            self.app._audit(
                conn, "EXAM_SCRIPT", script_id, user_id, "EXAM_SCRIPT_HANDOFF_ACCEPTED",
                {"previous_custodian": int(script["current_custodian"])},
            )
        self._sync_session_cases(user_id, script["session_id"])
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
        self._sync_session_cases(user_id, script["session_id"])
        return {"script_id": script_id, "status": "MARKED", "marked_at": now}

    def sign_exam_cards(
        self,
        user_id: int,
        session_id: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        actor, session = self._authorize_session(user_id, session_id)
        if actor["role"] != "lecturer":
            raise AppError("Only the lecturer in charge of this unit can confirm physical exam-card signatures.", 403)
        if session["session_type"] not in {"FINAL_EXAM", "SPECIAL_EXAM"}:
            raise AppError("Lecturer exam-card sign-off applies only to final or special examination sessions.", 409)
        if session["status"] != "CLOSED":
            raise AppError("Close the examination attendance register before signing exam cards.", 409)
        if not isinstance(items, list) or not items or len(items) > 5000:
            raise AppError("Provide between 1 and 5,000 exam-card sign-offs.")

        prepared: list[tuple[int, str]] = []
        seen: set[int] = set()
        for item in items:
            if not isinstance(item, dict):
                raise AppError("Each exam-card sign-off must identify one candidate.")
            try:
                student_id = int(item.get("student_id"))
            except (TypeError, ValueError) as exc:
                raise AppError("Each exam-card sign-off needs a valid candidate ID.") from exc
            if student_id in seen:
                raise AppError("The exam-card sign-off contains a duplicate candidate.")
            seen.add(student_id)
            note = str(item.get("note") or "").strip()
            if len(note) > 1000:
                raise AppError("Exam-card sign-off notes must be 1,000 characters or fewer.")
            prepared.append((student_id, note))

        now = utc_now()
        with self.db.transaction() as conn:
            for student_id, note in prepared:
                candidate = conn.execute(
                    """
                    SELECT
                        c.student_id,
                        a.attendance_status,
                        a.signature_present,
                        a.exam_card_seen,
                        s.id AS script_id
                    FROM exam_session_candidates c
                    LEFT JOIN exam_attendance a
                      ON a.session_id = c.session_id AND a.student_id = c.student_id
                    LEFT JOIN exam_scripts s
                      ON s.session_id = c.session_id AND s.student_id = c.student_id
                    WHERE c.session_id = ? AND c.student_id = ?
                    """,
                    (session_id, student_id),
                ).fetchone()
                if not candidate:
                    raise AppError("One or more candidates are not in the locked examination roster.", 409)
                if candidate["attendance_status"] != "PRESENT":
                    raise AppError("Exam cards can only be signed for candidates recorded PRESENT.", 409)
                if not candidate["signature_present"]:
                    raise AppError("The candidate has no recorded attendance signature; resolve the attendance evidence first.", 409)
                if not candidate["exam_card_seen"]:
                    raise AppError("The invigilator has not recorded that this candidate's exam card was checked.", 409)
                if not candidate["script_id"]:
                    raise AppError("No candidate-linked script receipt exists; reconcile the script before signing the exam card.", 409)
                existing = conn.execute(
                    """
                    SELECT 1 FROM exam_card_signoffs
                    WHERE session_id = ? AND student_id = ?
                    """,
                    (session_id, student_id),
                ).fetchone()
                if existing:
                    raise AppError("This candidate's exam card has already been signed for this unit and examination.", 409)

                conn.execute(
                    """
                    INSERT INTO exam_card_signoffs
                    (session_id, student_id, signed_by, signed_at, note)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, student_id, user_id, now, note),
                )
                conn.execute(
                    """
                    INSERT INTO exam_card_signoff_events
                    (session_id, student_id, actor_id, event_type, note, created_at)
                    VALUES (?, ?, ?, 'PHYSICAL_CARD_SIGNED', ?, ?)
                    """,
                    (session_id, student_id, user_id, note, now),
                )
                self.app._audit(
                    conn,
                    "EXAM_CARD",
                    f"{session_id}:{student_id}",
                    user_id,
                    "PHYSICAL_EXAM_CARD_SIGNED",
                    {
                        "assessment_id": session["assessment_id"],
                        "session_id": session_id,
                        "student_id": student_id,
                        "note": note,
                    },
                )
        self._sync_session_cases(user_id, session_id)
        return {"signed": len(prepared), "signed_at": now}

    def _exceptions_for(
        self,
        candidate: dict[str, Any],
        session_closed: bool,
        session_type: str,
    ) -> list[dict[str, str]]:
        attendance = candidate.get("attendance")
        script = candidate.get("script")
        card_signoff = candidate.get("card_signoff")
        mark = candidate.get("mark")
        issues: list[dict[str, str]] = []

        if attendance is None:
            if session_closed:
                issues.append({"code": "ATTENDANCE_NOT_RECORDED", "severity": "high"})
        else:
            state = attendance["attendance_status"]
            if state == "CONTESTED":
                issues.append({"code": "ATTENDANCE_DISPUTED", "severity": "high"})
            if state == "ABSENT" and attendance["signature_present"]:
                issues.append({"code": "ATTENDANCE_SIGNATURE_STATUS_CONFLICT", "severity": "high"})
            if state == "PRESENT" and not attendance["signature_present"]:
                issues.append({"code": "ATTENDANCE_SIGNATURE_MISSING", "severity": "medium"})
            if state == "PRESENT" and not attendance["exam_card_seen"]:
                issues.append({"code": "EXAM_CARD_CHECK_NOT_RECORDED", "severity": "low"})
            if state == "PRESENT" and not attendance["student_id_seen"]:
                issues.append({"code": "STUDENT_ID_CHECK_NOT_RECORDED", "severity": "low"})
            if state == "PRESENT" and script is None:
                issues.append({"code": "SCRIPT_NOT_RECEIVED", "severity": "high"})
            if (
                session_closed
                and session_type in {"FINAL_EXAM", "SPECIAL_EXAM"}
                and state == "PRESENT"
                and card_signoff is None
            ):
                issues.append({"code": "LECTURER_EXAM_CARD_SIGNOFF_PENDING", "severity": "medium"})
            if state == "ABSENT" and script is not None:
                issues.append({"code": "SCRIPT_RECEIVED_FOR_RECORDED_ABSENT", "severity": "high"})

        if card_signoff is not None:
            if (
                attendance is None
                or attendance["attendance_status"] != "PRESENT"
                or not attendance["signature_present"]
                or not attendance["exam_card_seen"]
                or script is None
            ):
                issues.append({"code": "EXAM_CARD_SIGNOFF_EVIDENCE_CONFLICT", "severity": "high"})

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

    def _case_assignment(self, session, category: str, conn) -> tuple[str, int | None]:
        lecturer_owned = {
            "LECTURER_EXAM_CARD_SIGNOFF_PENDING",
            "SCRIPT_NOT_RECEIVED",
            "SCRIPT_NOT_MARKED",
            "SCRIPT_HANDOFF_NOT_ACCEPTED",
            "MARK_ENTRY_NOT_FOUND",
            "MARK_WITHOUT_SCRIPT_RECEIPT",
        }
        exam_office_owned = {
            "ATTENDANCE_NOT_RECORDED",
            "ATTENDANCE_SIGNATURE_MISSING",
            "EXAM_CARD_CHECK_NOT_RECORDED",
            "STUDENT_ID_CHECK_NOT_RECORDED",
        }
        assigned_role = (
            "lecturer" if category in lecturer_owned
            else "exam_office" if category in exam_office_owned
            else "reviewer"
        )
        if assigned_role == "lecturer":
            assigned_user_id = int(session["lecturer_id"]) if session["lecturer_id"] else None
        else:
            row = conn.execute(
                "SELECT id FROM users WHERE role = ? AND active = 1 ORDER BY id LIMIT 1",
                (assigned_role,),
            ).fetchone()
            assigned_user_id = int(row["id"]) if row else None
        return assigned_role, assigned_user_id

    def _append_case_event(
        self,
        conn,
        case_id: str,
        event_type: str,
        actor_id: int | None,
        note: str,
        metadata: dict[str, Any],
        created_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO evidence_case_events
            (case_id, event_type, actor_id, note, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                event_type,
                actor_id,
                note,
                json.dumps(metadata, sort_keys=True),
                created_at,
            ),
        )

    def _sync_session_cases(self, actor_id: int, session_id: str) -> dict[str, int]:
        """Reconcile detected session exceptions into persistent, owned cases.

        Clearing source evidence only moves a case to EVIDENCE_CLEARED. A human
        reviewer/admin must still record a resolution or dismissal.
        """
        detail = self.session_detail(actor_id, session_id)
        session = self._session_row(session_id)
        now = utc_now()
        active_keys: set[tuple[str, str]] = set()
        opened = 0
        cleared = 0
        reopened = 0

        with self.db.transaction() as conn:
            for issue in detail["exceptions"]:
                category = str(issue["code"])
                student_id = int(issue["student_id"]) if issue.get("student_id") is not None else None
                script_id = str(issue["script_id"]) if issue.get("script_id") else None
                if student_id is not None:
                    subject_key = f"student:{student_id}"
                elif script_id:
                    subject_key = f"script:{script_id}"
                else:
                    # Fail closed rather than merge unrelated unidentifiable evidence.
                    subject_key = "unknown:" + uuid.uuid4().hex
                active_keys.add((subject_key, category))
                existing = conn.execute(
                    """
                    SELECT id, status, severity, assigned_role, assigned_user_id
                    FROM evidence_cases
                    WHERE session_id = ? AND subject_key = ? AND category = ?
                    """,
                    (session_id, subject_key, category),
                ).fetchone()
                assigned_role, assigned_user_id = self._case_assignment(session, category, conn)
                if not existing:
                    case_id = "case-" + uuid.uuid4().hex
                    conn.execute(
                        """
                        INSERT INTO evidence_cases
                        (id, session_id, assessment_id, student_id, script_id,
                         subject_key, category, severity, status, assigned_role,
                         assigned_user_id, opened_at, updated_at, last_detected_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?)
                        """,
                        (
                            case_id,
                            session_id,
                            session["assessment_id"],
                            student_id,
                            script_id,
                            subject_key,
                            category,
                            issue["severity"],
                            assigned_role,
                            assigned_user_id,
                            now,
                            now,
                            now,
                        ),
                    )
                    self._append_case_event(
                        conn,
                        case_id,
                        "OPENED",
                        actor_id,
                        "Evidence exception detected.",
                        {
                            "category": category,
                            "severity": issue["severity"],
                            "registration_number": issue.get("registration_number"),
                            "script_ref": issue.get("script_ref"),
                            "assigned_role": assigned_role,
                        },
                        now,
                    )
                    self.app._audit(
                        conn,
                        "EVIDENCE_CASE",
                        case_id,
                        actor_id,
                        "EVIDENCE_CASE_OPENED",
                        {
                            "session_id": session_id,
                            "assessment_id": session["assessment_id"],
                            "category": category,
                            "severity": issue["severity"],
                        },
                    )
                    if assigned_user_id is not None:
                        self.app._notify(
                            conn,
                            assigned_user_id,
                            "EVIDENCE_CASE_ASSIGNED",
                            "Examination evidence case assigned",
                            f"{category.replace('_', ' ').title()} requires review in MarkTrail.",
                            now,
                        )
                    if student_id is not None:
                        self.app._notify(
                            conn,
                            student_id,
                            "EVIDENCE_CASE_OPENED",
                            "Your examination record is being checked",
                            "MarkTrail detected an examination-record discrepancy for this assessment. A case has been opened for staff review. No academic result has been changed.",
                            now,
                        )
                    opened += 1
                    continue

                case_id = existing["id"]
                if existing["status"] == "EVIDENCE_CLEARED":
                    conn.execute(
                        """
                        UPDATE evidence_cases
                        SET status = 'OPEN', severity = ?, assigned_role = ?,
                            assigned_user_id = ?, updated_at = ?, last_detected_at = ?,
                            evidence_cleared_at = NULL
                        WHERE id = ?
                        """,
                        (
                            issue["severity"], assigned_role, assigned_user_id,
                            now, now, case_id,
                        ),
                    )
                    self._append_case_event(
                        conn,
                        case_id,
                        "REOPENED",
                        actor_id,
                        "The evidence exception appeared again after being cleared.",
                        {"category": category, "severity": issue["severity"]},
                        now,
                    )
                    reopened += 1
                elif existing["status"] == "OPEN":
                    conn.execute(
                        """
                        UPDATE evidence_cases
                        SET severity = ?, assigned_role = ?, assigned_user_id = ?,
                            updated_at = ?, last_detected_at = ?
                        WHERE id = ?
                        """,
                        (
                            issue["severity"], assigned_role, assigned_user_id,
                            now, now, case_id,
                        ),
                    )
                # RESOLVED and DISMISSED are human terminal decisions. A later
                # session sync must not silently reverse those decisions.
                if existing["status"] == "EVIDENCE_CLEARED":
                    if student_id is not None:
                        self.app._notify(
                            conn,
                            student_id,
                            "EVIDENCE_CASE_REOPENED",
                            "Your examination record needs another check",
                            "A previously cleared examination-record discrepancy has appeared again. Staff review has resumed.",
                            now,
                        )

            cases = conn.execute(
                """
                SELECT id, subject_key, category, student_id, status,
                       assigned_role, assigned_user_id
                FROM evidence_cases
                WHERE session_id = ? AND status = 'OPEN'
                """,
                (session_id,),
            ).fetchall()
            cleared_role_row = conn.execute(
                "SELECT id FROM users WHERE role = 'reviewer' AND active = 1 ORDER BY id LIMIT 1"
            ).fetchone()
            cleared_reviewer = int(cleared_role_row["id"]) if cleared_role_row else None
            for case in cases:
                key = (case["subject_key"], case["category"])
                if key in active_keys:
                    continue
                conn.execute(
                    """
                    UPDATE evidence_cases
                    SET status = 'EVIDENCE_CLEARED', assigned_role = 'reviewer',
                        assigned_user_id = ?, evidence_cleared_at = ?,
                        updated_at = ?
                    WHERE id = ? AND status = 'OPEN'
                    """,
                    (cleared_reviewer, now, now, case["id"]),
                )
                self._append_case_event(
                    conn,
                    case["id"],
                    "EVIDENCE_CLEARED",
                    actor_id,
                    "The source evidence no longer shows this exception; reviewer confirmation is required.",
                    {"category": case["category"]},
                    now,
                )
                if cleared_reviewer is not None:
                    self.app._notify(
                        conn,
                        cleared_reviewer,
                        "EVIDENCE_CASE_CLEARED",
                        "Evidence case ready for review",
                        f"{case['category'].replace('_', ' ').title()} has been cleared by new evidence. Confirm the case outcome.",
                        now,
                    )
                if case["student_id"] is not None:
                    self.app._notify(
                        conn,
                        int(case["student_id"]),
                        "EVIDENCE_CASE_CLEARED",
                        "New evidence has been recorded",
                        "The discrepancy in your examination record is no longer detected. It is awaiting staff confirmation; this does not yet mean your academic result has changed.",
                        now,
                    )
                cleared += 1

        return {"opened": opened, "cleared": cleared, "reopened": reopened}

    def list_evidence_cases(self, user_id: int) -> list[dict[str, Any]]:
        actor = self.app.user(user_id)
        role = actor["role"]
        conn = self.db.connect()
        try:
            base = """
                SELECT ec.id, ec.session_id, ec.assessment_id, ec.student_id,
                       ec.script_id, ec.category, ec.severity, ec.status,
                       ec.assigned_role, ec.assigned_user_id,
                       ec.opened_at, ec.updated_at, ec.evidence_cleared_at,
                       ec.resolution_note,
                       a.name AS assessment, c.code AS course,
                       c.title AS course_title, s.session_type, s.exam_at,
                       candidate.reg_number_snapshot,
                       candidate.full_name_snapshot,
                       assigned.full_name AS assigned_user_name
                FROM evidence_cases ec
                JOIN assessments a ON a.id = ec.assessment_id
                JOIN courses c ON c.id = a.course_id
                JOIN exam_sessions s ON s.id = ec.session_id
                LEFT JOIN exam_session_candidates candidate
                  ON candidate.session_id = ec.session_id
                 AND candidate.student_id = ec.student_id
                LEFT JOIN users assigned ON assigned.id = ec.assigned_user_id
            """
            if role == "student":
                rows = conn.execute(
                    base + " WHERE ec.student_id = ? ORDER BY ec.updated_at DESC",
                    (user_id,),
                ).fetchall()
                return [
                    {
                        "id": row["id"],
                        "assessment_id": row["assessment_id"],
                        "course": row["course"],
                        "assessment": row["assessment"],
                        "category": row["category"],
                        "severity": row["severity"],
                        "status": row["status"],
                        "opened_at": row["opened_at"],
                        "updated_at": row["updated_at"],
                    }
                    for row in rows
                ]
            if role == "admin":
                where, params = "", ()
            elif role == "reviewer":
                where, params = " WHERE ec.assigned_role = 'reviewer'", ()
            elif role == "exam_office":
                where, params = " WHERE ec.assigned_role = 'exam_office'", ()
            elif role == "lecturer":
                where, params = (
                    " WHERE ec.assigned_role = 'lecturer' AND ec.assigned_user_id = ?",
                    (user_id,),
                )
            else:
                raise AppError("You do not have access to the evidence case queue.", 403)
            rows = conn.execute(base + where + " ORDER BY ec.updated_at DESC", params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def decide_evidence_case(
        self,
        user_id: int,
        case_id: str,
        decision: str,
        reason: str,
    ) -> dict[str, Any]:
        self.app.require_role(user_id, {"reviewer", "admin"})
        decision = str(decision or "").upper()
        reason = str(reason or "").strip()
        if decision not in {"RESOLVED", "DISMISSED"}:
            raise AppError("Case decision must be RESOLVED or DISMISSED.")
        if len(reason) < 8 or len(reason) > 1000:
            raise AppError("Provide an 8–1,000 character reason for the case decision.")
        now = utc_now()
        with self.db.transaction() as conn:
            case = conn.execute(
                """
                SELECT id, status, student_id, category, assessment_id, session_id
                FROM evidence_cases WHERE id = ?
                """,
                (case_id,),
            ).fetchone()
            if not case:
                raise AppError("Evidence case not found.", 404)
            if case["status"] in {"RESOLVED", "DISMISSED"}:
                raise AppError("This evidence case already has a terminal decision.", 409)
            conn.execute(
                """
                UPDATE evidence_cases
                SET status = ?, resolved_by = ?, resolved_at = ?,
                    resolution_note = ?, updated_at = ?
                WHERE id = ?
                """,
                (decision, user_id, now, reason, now, case_id),
            )
            self._append_case_event(
                conn,
                case_id,
                decision,
                user_id,
                reason,
                {"category": case["category"], "assessment_id": case["assessment_id"]},
                now,
            )
            self.app._audit(
                conn,
                "EVIDENCE_CASE",
                case_id,
                user_id,
                "EVIDENCE_CASE_" + decision,
                {"category": case["category"], "reason": reason},
            )
            if case["student_id"] is not None:
                self.app._notify(
                    conn,
                    int(case["student_id"]),
                    "EVIDENCE_CASE_" + decision,
                    "Your examination evidence case was updated",
                    "Staff have completed a review of the examination evidence case. Contact your department if you need clarification.",
                    now,
                )
        return {"case_id": case_id, "status": decision, "decided_at": now}

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
                       s.current_custodian, current_staff.full_name AS current_custodian_name,
                       s.pending_custodian, pending_staff.full_name AS pending_custodian_name,
                       s.received_at, s.marked_by, s.marked_at, s.notes AS script_note,
                       cs.signed_by AS card_signed_by,
                       card_signer.full_name AS card_signed_by_name,
                       cs.signed_at AS card_signed_at,
                       cs.note AS card_signoff_note,
                       m.candidate_mark, m.candidate_status
                FROM exam_session_candidates c
                LEFT JOIN exam_attendance a
                  ON a.session_id = c.session_id AND a.student_id = c.student_id
                LEFT JOIN exam_scripts s
                  ON s.session_id = c.session_id AND s.student_id = c.student_id
                LEFT JOIN users current_staff ON current_staff.id = s.current_custodian
                LEFT JOIN users pending_staff ON pending_staff.id = s.pending_custodian
                LEFT JOIN exam_card_signoffs cs
                  ON cs.session_id = c.session_id AND cs.student_id = c.student_id
                LEFT JOIN users card_signer ON card_signer.id = cs.signed_by
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
                        "current_custodian_name": row["current_custodian_name"],
                        "pending_custodian": row["pending_custodian"],
                        "pending_custodian_name": row["pending_custodian_name"],
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
                card_signoff = None
                if row["card_signed_by"] is not None:
                    card_signoff = {
                        "signed_by": int(row["card_signed_by"]),
                        "signed_by_name": row["card_signed_by_name"],
                        "signed_at": row["card_signed_at"],
                        "note": row["card_signoff_note"],
                    }
                candidate = {
                    "student_id": int(row["student_id"]),
                    "registration_number": row["reg_number_snapshot"],
                    "full_name": row["full_name_snapshot"],
                    "attendance": attendance,
                    "script": script,
                    "card_signoff": card_signoff,
                    "mark": mark,
                }
                candidate["issues"] = self._exceptions_for(
                    candidate,
                    session["status"] == "CLOSED",
                    session["session_type"],
                )
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
                    "script_id": orphan["id"],
                    "code": "SCRIPT_UNIDENTIFIED",
                    "severity": "high",
                })
            session_activity = conn.execute(
                """
                SELECT e.id, e.event_type, e.metadata_json, e.created_at,
                       u.full_name AS actor_name, u.role AS actor_role
                FROM exam_session_events e
                JOIN users u ON u.id = e.actor_id
                WHERE e.session_id = ?
                """,
                (session_id,),
            ).fetchall()
            attendance_activity = conn.execute(
                """
                SELECT e.id, e.event_type, e.old_state_json, e.new_state_json,
                       e.reason, e.created_at, u.full_name AS actor_name,
                       u.role AS actor_role, c.reg_number_snapshot,
                       c.full_name_snapshot
                FROM exam_attendance_events e
                JOIN users u ON u.id = e.actor_id
                JOIN exam_session_candidates c
                  ON c.session_id = e.session_id AND c.student_id = e.student_id
                WHERE e.session_id = ?
                """,
                (session_id,),
            ).fetchall()
            card_activity = conn.execute(
                """
                SELECT e.id, e.event_type, e.note, e.created_at,
                       u.full_name AS actor_name, u.role AS actor_role,
                       c.reg_number_snapshot, c.full_name_snapshot
                FROM exam_card_signoff_events e
                JOIN users u ON u.id = e.actor_id
                JOIN exam_session_candidates c
                  ON c.session_id = e.session_id AND c.student_id = e.student_id
                WHERE e.session_id = ?
                """,
                (session_id,),
            ).fetchall()
            script_activity = conn.execute(
                """
                SELECT e.id, e.event_type, e.note, e.created_at,
                       e.recipient_id, actor.full_name AS actor_name,
                       actor.role AS actor_role,
                       recipient.full_name AS recipient_name,
                       s.script_ref, c.reg_number_snapshot,
                       c.full_name_snapshot
                FROM exam_script_events e
                JOIN exam_scripts s ON s.id = e.script_id
                JOIN users actor ON actor.id = e.actor_id
                LEFT JOIN users recipient ON recipient.id = e.recipient_id
                LEFT JOIN exam_session_candidates c
                  ON c.session_id = s.session_id AND c.student_id = s.student_id
                WHERE s.session_id = ?
                """,
                (session_id,),
            ).fetchall()

            activity = []
            for row in session_activity:
                try:
                    metadata = json.loads(row["metadata_json"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    metadata = {}
                activity.append({
                    "id": f"session-{row['id']}",
                    "category": "SESSION",
                    "event_type": row["event_type"],
                    "actor_name": row["actor_name"],
                    "actor_role": row["actor_role"],
                    "metadata": metadata,
                    "created_at": row["created_at"],
                })
            for row in attendance_activity:
                try:
                    old_state = json.loads(row["old_state_json"]) if row["old_state_json"] else None
                except (TypeError, json.JSONDecodeError):
                    old_state = None
                try:
                    new_state = json.loads(row["new_state_json"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    new_state = {}
                activity.append({
                    "id": f"attendance-{row['id']}",
                    "category": "ATTENDANCE",
                    "event_type": row["event_type"],
                    "actor_name": row["actor_name"],
                    "actor_role": row["actor_role"],
                    "registration_number": row["reg_number_snapshot"],
                    "candidate_name": row["full_name_snapshot"],
                    "old_state": old_state,
                    "new_state": new_state,
                    "reason": row["reason"],
                    "created_at": row["created_at"],
                })
            for row in card_activity:
                activity.append({
                    "id": f"card-{row['id']}",
                    "category": "EXAM_CARD",
                    "event_type": row["event_type"],
                    "actor_name": row["actor_name"],
                    "actor_role": row["actor_role"],
                    "registration_number": row["reg_number_snapshot"],
                    "candidate_name": row["full_name_snapshot"],
                    "note": row["note"],
                    "created_at": row["created_at"],
                })
            for row in script_activity:
                activity.append({
                    "id": f"script-{row['id']}",
                    "category": "SCRIPT",
                    "event_type": row["event_type"],
                    "actor_name": row["actor_name"],
                    "actor_role": row["actor_role"],
                    "recipient_name": row["recipient_name"],
                    "script_ref": row["script_ref"],
                    "registration_number": row["reg_number_snapshot"],
                    "candidate_name": row["full_name_snapshot"] or "Unidentified candidate",
                    "note": row["note"],
                    "created_at": row["created_at"],
                })
            activity.sort(key=lambda item: (item["created_at"], item["id"]))

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
                    "session_type": session["session_type"],
                    "status": session["status"],
                    "candidate_count": int(session["candidate_count"]),
                    "created_at": session["created_at"],
                },
                "summary": {
                    "candidates": total,
                    "attendance_recorded": attendance_count,
                    "scripts_received": script_count,
                    "scripts_marked": marked_count,
                    "exam_cards_signed": sum(1 for c in candidates if c["card_signoff"] is not None),
                    "exceptions": len(exceptions),
                },
                "candidates": candidates,
                "unidentified_scripts": unidentified_scripts,
                "exceptions": exceptions,
                "activity": activity,
            }
        finally:
            conn.close()

    def student_progress(self, user_id: int) -> list[dict[str, Any]]:
        """Return only the signed-in student's own exam evidence and safe progress states."""
        self.app.require_role(user_id, {"student"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    a.id AS assessment_id,
                    a.name AS assessment,
                    a.max_mark,
                    a.release_policy,
                    c.code AS course_code,
                    c.title AS course_title,
                    x.session_id,
                    x.exam_at,
                    x.venue,
                    x.session_type,
                    x.session_status,
                    x.session_created_at,
                    x.attendance_status,
                    x.attendance_recorded_at,
                    x.signature_present,
                    x.script_status,
                    x.script_received_at,
                    x.script_marked_at,
                    x.card_signed_by,
                    x.card_signed_at,
                    COALESCE(m.candidate_status, 'NOT_ENTERED') AS mark_entry_status,
                    COALESCE(m.published_status, 'MISSING') AS published_status,
                    COALESCE(b.pipeline_stage, 'NOT_SUBMITTED') AS pipeline_stage,
                    COALESCE(b.senate_status, 'NOT_REQUIRED') AS senate_status
                FROM enrollments e
                JOIN courses c ON c.id = e.course_id
                JOIN assessments a ON a.course_id = c.id
                LEFT JOIN (
                    SELECT
                        candidate.student_id,
                        session.assessment_id,
                        session.id AS session_id,
                        session.exam_at,
                        session.venue,
                        session.session_type,
                        session.status AS session_status,
                        session.created_at AS session_created_at,
                        attendance.attendance_status,
                        attendance.recorded_at AS attendance_recorded_at,
                        attendance.signature_present,
                        script.status AS script_status,
                        script.received_at AS script_received_at,
                        script.marked_at AS script_marked_at,
                        card_signoff.signed_by AS card_signed_by,
                        card_signoff.signed_at AS card_signed_at
                    FROM exam_session_candidates candidate
                    JOIN exam_sessions session ON session.id = candidate.session_id
                    LEFT JOIN exam_attendance attendance
                      ON attendance.session_id = candidate.session_id
                     AND attendance.student_id = candidate.student_id
                    LEFT JOIN exam_scripts script
                      ON script.session_id = candidate.session_id
                     AND script.student_id = candidate.student_id
                    LEFT JOIN exam_card_signoffs card_signoff
                      ON card_signoff.session_id = candidate.session_id
                     AND card_signoff.student_id = candidate.student_id
                ) x ON x.student_id = e.student_id AND x.assessment_id = a.id
                LEFT JOIN assessment_marks m
                  ON m.assessment_id = a.id AND m.student_id = e.student_id
                LEFT JOIN batches b ON b.id = m.batch_id
                WHERE e.student_id = ?
                ORDER BY c.code, a.created_at, x.exam_at
                """,
                (user_id,),
            ).fetchall()
            result = []
            for row in rows:
                case_rows = conn.execute(
                    """
                    SELECT id, category, severity, status, opened_at, updated_at
                    FROM evidence_cases
                    WHERE assessment_id = ? AND student_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (row["assessment_id"], user_id),
                ).fetchall()
                result.append({
                    "assessment_id": row["assessment_id"],
                    "assessment": row["assessment"],
                    "course": row["course_code"] + " · " + row["course_title"],
                    "max_mark": row["max_mark"],
                    "release_policy": row["release_policy"],
                    "senate_status": row["senate_status"],
                    "session_id": row["session_id"],
                    "exam_at": row["exam_at"],
                    "venue": row["venue"],
                    "session_type": row["session_type"],
                    "session_status": row["session_status"],
                    "attendance_status": row["attendance_status"],
                    "attendance_recorded_at": row["attendance_recorded_at"],
                    "signature_recorded": (
                        bool(row["signature_present"])
                        if row["signature_present"] is not None else None
                    ),
                    "script_status": row["script_status"],
                    "script_received_at": row["script_received_at"],
                    "script_marked_at": row["script_marked_at"],
                    "lecturer_card_signed": bool(row["card_signed_by"]) if row["card_signed_by"] is not None else None,
                    "lecturer_card_signed_at": row["card_signed_at"],
                    "mark_entry_status": row["mark_entry_status"],
                    "result_status": (
                        row["published_status"]
                        if row["pipeline_stage"] == "PUBLISHED"
                        else (
                            "RELEASE_POLICY_UNCLASSIFIED"
                            if row["release_policy"] == "UNCLASSIFIED" and row["pipeline_stage"] != "NOT_SUBMITTED"
                            else (
                                "SENATE_APPROVAL"
                                if row["release_policy"] == "SENATE" and row["senate_status"] == "PENDING"
                                else (
                                    "SENATE_DEFERRED"
                                    if row["release_policy"] == "SENATE" and row["senate_status"] == "DEFERRED"
                                    else row["pipeline_stage"]
                                )
                            )
                        )
                    ),
                    "evidence_available": row["session_id"] is not None,
                    "cases": [
                        {
                            "id": case["id"],
                            "category": case["category"],
                            "severity": case["severity"],
                            "status": case["status"],
                            "opened_at": case["opened_at"],
                            "updated_at": case["updated_at"],
                        }
                        for case in case_rows
                    ],
                })
            return result
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
                        'lecturer','reviewer','exam_office','senate_office','portal_operator','admin'
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
                    SELECT s.id, s.exam_at, s.venue, s.session_type,
                           s.status, s.candidate_count, s.created_at,
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
