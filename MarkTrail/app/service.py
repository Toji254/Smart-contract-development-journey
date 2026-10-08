from __future__ import annotations

import csv
import hashlib
import io
import json
import secrets
import uuid
from typing import Any

from .chain import ChainClient, ChainError
from .db import Database, utc_now


class AppError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _user_dict(row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
    }


class AppService:
    def __init__(self, db: Database, chain: ChainClient | None = None) -> None:
        self.db = db
        self.chain = chain or ChainClient()

    def user(self, user_id: int):
        conn = self.db.connect()
        try:
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        finally:
            conn.close()

    def require_role(self, user_id: int, roles: set[str]):
        user = self.user(user_id)
        if not user:
            raise AppError("User not found.", 401)
        if user["role"] not in roles:
            raise AppError("You do not have permission for this action.", 403)
        return user

    def _audit(
        self,
        conn,
        entity_type: str,
        entity_id: str,
        actor_id: int | None,
        action: str,
        metadata: dict | None = None,
        chain_tx_hash: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO audit_events
            (entity_type, entity_id, actor_id, action, metadata_json, chain_tx_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_type,
                entity_id,
                actor_id,
                action,
                json.dumps(metadata or {}, sort_keys=True),
                chain_tx_hash,
                utc_now(),
            ),
        )

    def dashboard(self, user_id: int) -> dict:
        user = self.require_role(user_id, {"student", "lecturer", "reviewer", "admin"})
        conn = self.db.connect()
        try:
            counts: dict[str, int] = {}
            if user["role"] == "student":
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(
                            CASE
                                WHEN am.published_status = 'MISSING' OR am.published_status IS NULL
                                THEN 1 ELSE 0
                            END
                        ) AS missing
                    FROM enrollments e
                    JOIN assessments a ON a.course_id = e.course_id
                    LEFT JOIN assessment_marks am
                      ON am.assessment_id = a.id AND am.student_id = e.student_id
                    LEFT JOIN batches b ON b.id = am.batch_id
                    WHERE e.student_id = ?
                    """,
                    (user_id,),
                ).fetchone()
                counts = {
                    "assessments": int(row["total"] or 0),
                    "missing": int(row["missing"] or 0),
                }
            elif user["role"] == "lecturer":
                row = conn.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM batches b
                         JOIN assessments a ON a.id = b.assessment_id
                         JOIN courses c ON c.id = a.course_id
                         WHERE c.lecturer_id = ?) AS batches,
                        (SELECT COUNT(*) FROM missing_reports r
                         JOIN assessments a ON a.id = r.assessment_id
                         JOIN courses c ON c.id = a.course_id
                         WHERE c.lecturer_id = ? AND r.status IN ('OPEN','PENDING_REVIEW')) AS issues
                    """,
                    (user_id, user_id),
                ).fetchone()
                counts = {
                    "batches": int(row["batches"] or 0),
                    "issues": int(row["issues"] or 0),
                }
            elif user["role"] == "reviewer":
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM batches WHERE status IN ('SUBMITTED','AMENDED')"
                ).fetchone()
                counts = {"pending_verification": int(row["n"] or 0)}
            else:
                rows = conn.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM users) AS users,
                        (SELECT COUNT(*) FROM courses) AS courses,
                        (SELECT COUNT(*) FROM assessments) AS assessments,
                        (SELECT COUNT(*) FROM missing_reports WHERE status != 'RESOLVED') AS issues
                    """
                ).fetchone()
                counts = {
                    "users": int(rows["users"] or 0),
                    "courses": int(rows["courses"] or 0),
                    "assessments": int(rows["assessments"] or 0),
                    "issues": int(rows["issues"] or 0),
                }

            return {"user": _user_dict(user), "counts": counts, "chain": self.chain.status()}
        finally:
            conn.close()

    def student_marks(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"student"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    a.id AS assessment_id,
                    a.name AS assessment,
                    a.max_mark,
                    c.code,
                    c.title,
                    COALESCE(b.status, 'NOT_SUBMITTED') AS batch_status,
                    am.published_mark,
                    COALESCE(am.published_status, 'MISSING') AS published_status,
                    b.id AS batch_id
                FROM enrollments e
                JOIN courses c ON c.id = e.course_id
                JOIN assessments a ON a.course_id = c.id
                LEFT JOIN assessment_marks am
                    ON am.assessment_id = a.id AND am.student_id = e.student_id
                LEFT JOIN batches b ON b.id = am.batch_id
                WHERE e.student_id = ?
                ORDER BY c.code, a.created_at
                """,
                (user_id,),
            ).fetchall()
            return [
                {
                    "assessment_id": row["assessment_id"],
                    "assessment": row["assessment"],
                    "max_mark": row["max_mark"],
                    "course": row["code"],
                    "course_title": row["title"],
                    "batch_status": row["batch_status"],
                    "mark": row["published_mark"],
                    "status": row["published_status"],
                    "batch_id": row["batch_id"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def student_reports(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"student"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    r.id,
                    r.status,
                    r.opened_at,
                    r.resolution_type,
                    r.resolution_mark,
                    r.lecturer_note,
                    a.name AS assessment,
                    a.max_mark,
                    c.code AS course,
                    u.full_name AS resolved_by_name
                FROM missing_reports r
                JOIN assessments a ON a.id = r.assessment_id
                JOIN courses c ON c.id = a.course_id
                LEFT JOIN users u ON u.id = r.resolved_by
                WHERE r.student_id = ?
                ORDER BY r.opened_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def report_missing_mark(self, user_id: int, assessment_id: str) -> dict:
        self.require_role(user_id, {"student"})
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT
                    a.id, a.name, a.course_id,
                    am.published_status,
                    b.status AS batch_status
                FROM assessments a
                LEFT JOIN assessment_marks am
                    ON am.assessment_id = a.id AND am.student_id = ?
                LEFT JOIN batches b ON b.id = am.batch_id
                JOIN enrollments e ON e.course_id = a.course_id AND e.student_id = ?
                WHERE a.id = ?
                """,
                (user_id, user_id, assessment_id),
            ).fetchone()
            if not row:
                raise AppError("Assessment not found for this student.", 404)
            if row["batch_status"] != "VERIFIED":
                raise AppError("This assessment is not published yet.")
            if row["published_status"] != "MISSING":
                raise AppError("This assessment does not currently have a missing mark.")

            duplicate = conn.execute(
                """
                SELECT 1 FROM missing_reports
                WHERE assessment_id = ? AND student_id = ?
                  AND status IN ('OPEN','PENDING_REVIEW')
                """,
                (assessment_id, user_id),
            ).fetchone()
            if duplicate:
                raise AppError("You already have an open report for this assessment.")
        finally:
            conn.close()

        report_id = "report-" + uuid.uuid4().hex[:16]
        with self.db.transaction() as tx:
            tx.execute(
                """
                INSERT INTO missing_reports
                (id, assessment_id, student_id, status, opened_at)
                VALUES (?, ?, ?, 'OPEN', ?)
                """,
                (report_id, assessment_id, user_id, utc_now()),
            )
            self._audit(
                tx,
                "REPORT",
                report_id,
                user_id,
                "REPORT_OPENED",
                {"assessment_id": assessment_id},
            )
        return {"id": report_id, "status": "OPEN"}

    def lecturer_assessments(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"lecturer"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    a.id,
                    a.name,
                    a.max_mark,
                    c.code AS course,
                    c.title AS course_title,
                    COUNT(e.student_id) AS enrolled_count,
                    b.id AS batch_id,
                    b.status AS batch_status,
                    b.revision,
                    b.chain_state
                FROM assessments a
                JOIN courses c ON c.id = a.course_id
                LEFT JOIN enrollments e ON e.course_id = c.id
                LEFT JOIN batches b ON b.assessment_id = a.id
                WHERE c.lecturer_id = ?
                GROUP BY a.id, c.code, c.title, b.id, b.status, b.revision, b.chain_state
                ORDER BY c.code, a.created_at
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def lecturer_batches(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"lecturer"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    b.id,
                    b.status,
                    b.student_count,
                    b.revision,
                    b.chain_state,
                    b.chain_tx_hash,
                    b.marks_hash,
                    b.submitted_at,
                    b.verified_at,
                    a.name AS assessment,
                    a.max_mark,
                    c.code AS course,
                    c.title AS course_title
                FROM batches b
                JOIN assessments a ON a.id = b.assessment_id
                JOIN courses c ON c.id = a.course_id
                WHERE c.lecturer_id = ?
                ORDER BY b.submitted_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def lecturer_reports(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"lecturer"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    r.id,
                    r.status,
                    r.opened_at,
                    r.resolution_type,
                    r.resolution_mark,
                    r.lecturer_note,
                    a.id AS assessment_id,
                    a.name AS assessment,
                    a.max_mark,
                    c.code AS course,
                    u.full_name AS student_name,
                    u.username AS student_username
                FROM missing_reports r
                JOIN assessments a ON a.id = r.assessment_id
                JOIN courses c ON c.id = a.course_id
                JOIN users u ON u.id = r.student_id
                WHERE c.lecturer_id = ?
                ORDER BY
                    CASE r.status WHEN 'OPEN' THEN 0 WHEN 'PENDING_REVIEW' THEN 1 ELSE 2 END,
                    r.opened_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def reviewer_batches(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"reviewer"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    b.id,
                    b.status,
                    b.student_count,
                    b.revision,
                    b.chain_state,
                    b.chain_tx_hash,
                    b.marks_hash,
                    b.submitted_at,
                    b.verified_at,
                    a.name AS assessment,
                    a.max_mark,
                    c.code AS course,
                    c.title AS course_title,
                    u.full_name AS lecturer_name
                FROM batches b
                JOIN assessments a ON a.id = b.assessment_id
                JOIN courses c ON c.id = a.course_id
                JOIN users u ON u.id = b.submitted_by
                ORDER BY
                    CASE b.status WHEN 'SUBMITTED' THEN 0 WHEN 'AMENDED' THEN 1 ELSE 2 END,
                    b.submitted_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _parse_csv(csv_text: str) -> list[dict[str, str]]:
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
        if not reader.fieldnames:
            raise AppError("CSV must include headers: student_id,mark.")
        normalized = {h.strip().lower(): h for h in reader.fieldnames if h}
        student_header = normalized.get("student_id") or normalized.get("student")
        mark_header = normalized.get("mark")
        if not student_header or not mark_header:
            raise AppError("CSV headers must include student_id and mark.")

        rows: list[dict[str, str]] = []
        for row in reader:
            sid = (row.get(student_header) or "").strip()
            mark = (row.get(mark_header) or "").strip()
            if not sid and not mark:
                continue
            rows.append({"student_id": sid, "mark": mark})
        return rows

    def _batch_context(self, user_id: int, assessment_id: str):
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT a.*, c.code AS course_code, c.title AS course_title,
                       c.lecturer_id,
                       (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id) AS enrollment_count
                FROM assessments a
                JOIN courses c ON c.id = a.course_id
                WHERE a.id = ?
                """,
                (assessment_id,),
            ).fetchone()
            if not row:
                raise AppError("Assessment not found.", 404)

            user = conn.execute(
                "SELECT role FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if user["role"] == "lecturer" and row["lecturer_id"] != user_id:
                raise AppError("You are not the lecturer for this course.", 403)

            students = conn.execute(
                """
                SELECT u.id, u.username, u.full_name
                FROM enrollments e
                JOIN users u ON u.id = e.student_id
                WHERE e.course_id = ?
                ORDER BY u.id
                """,
                (row["course_id"],),
            ).fetchall()
            return row, students
        finally:
            conn.close()

    def preview_batch(self, user_id: int, assessment_id: str, csv_text: str) -> dict:
        assessment, students = self._batch_context(user_id, assessment_id)
        rows = self._parse_csv(csv_text)

        roster = {str(row["id"]): row for row in students}
        seen: set[str] = set()
        errors: list[str] = []
        normalized_rows: list[dict] = []

        for index, row in enumerate(rows, start=2):
            sid = row["student_id"]
            mark_text = row["mark"]
            if sid in seen:
                errors.append(f"Row {index}: duplicate student_id {sid}.")
                continue
            seen.add(sid)

            if sid not in roster:
                errors.append(
                    f"Row {index}: student_id {sid} is not enrolled in {assessment['course_code']}."
                )
                continue

            try:
                mark = float(mark_text)
            except ValueError:
                errors.append(f"Row {index}: mark for {sid} is not numeric.")
                continue

            if mark < 0 or mark > float(assessment["max_mark"]):
                errors.append(
                    f"Row {index}: mark for {sid} must be between 0 and {assessment['max_mark']}."
                )
                continue

            normalized_rows.append(
                {
                    "student_id": int(sid),
                    "mark": mark,
                    "status": "RECORDED",
                }
            )

        missing = [
            {
                "student_id": int(s["id"]),
                "username": s["username"],
                "full_name": s["full_name"],
            }
            for s in students
            if str(s["id"]) not in seen
        ]

        return {
            "valid": not errors,
            "errors": errors,
            "course": assessment["course_code"],
            "assessment": assessment["name"],
            "max_mark": assessment["max_mark"],
            "enrolled_count": len(students),
            "submitted_count": len(normalized_rows),
            "missing_count": len(missing),
            "missing_students": missing,
            "rows": normalized_rows,
        }

    def submit_batch(self, user_id: int, assessment_id: str, csv_text: str) -> dict:
        preview = self.preview_batch(user_id, assessment_id, csv_text)
        if not preview["valid"]:
            raise AppError("Batch validation failed.", 422)
        if preview["enrolled_count"] == 0:
            raise AppError("Cannot submit marks for a course with no enrolled students.")

        conn = self.db.connect()
        try:
            existing = conn.execute(
                "SELECT status FROM batches WHERE assessment_id = ?",
                (assessment_id,),
            ).fetchone()
        finally:
            conn.close()

        if existing:
            raise AppError(
                "This assessment already has a batch. Use a missing-mark resolution to create an amendment."
            )

        batch_id = "0x" + hashlib.sha256(
            f"batch:{assessment_id}:{secrets.token_hex(16)}".encode("utf-8")
        ).hexdigest()
        salt = secrets.token_hex(16)
        canonical_rows = sorted(preview["rows"], key=lambda item: item["student_id"])
        submitted_ids = {item["student_id"] for item in canonical_rows}

        for missing in preview["missing_students"]:
            canonical_rows.append(
                {
                    "student_id": missing["student_id"],
                    "mark": None,
                    "status": "MISSING",
                }
            )

        canonical_rows.sort(key=lambda item: item["student_id"])
        canonical = json.dumps(canonical_rows, sort_keys=True, separators=(",", ":"))
        marks_hash = "0x" + hashlib.sha256(
            (salt + "|" + canonical).encode("utf-8")
        ).hexdigest()

        now = utc_now()
        chain_state = "PENDING" if self.chain.enabled else "LOCAL_ONLY"

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO batches
                (id, assessment_id, submitted_by, status, student_count, marks_hash,
                 commitment_salt, revision, chain_state, submitted_at)
                VALUES (?, ?, ?, 'SUBMITTED', ?, ?, ?, 1, ?, ?)
                """,
                (
                    batch_id,
                    assessment_id,
                    user_id,
                    preview["enrolled_count"],
                    marks_hash,
                    salt,
                    chain_state,
                    now,
                ),
            )

            reason_hash = "0x" + hashlib.sha256(b"initial marks submission").hexdigest()
            conn.execute(
                """
                INSERT INTO batch_revisions
                (batch_id, revision, marks_hash, reason_hash, kind, actor_id, chain_state, created_at)
                VALUES (?, 1, ?, ?, 'SUBMISSION', ?, ?, ?)
                """,
                (batch_id, marks_hash, reason_hash, user_id, chain_state, now),
            )

            for student in preview["missing_students"]:
                conn.execute(
                    """
                    INSERT INTO assessment_marks
                    (assessment_id, student_id, candidate_mark, candidate_status,
                     published_mark, published_status, batch_id, updated_at)
                    VALUES (?, ?, NULL, 'MISSING', NULL, 'MISSING', ?, ?)
                    """,
                    (assessment_id, student["student_id"], batch_id, now),
                )

            for row in canonical_rows:
                if row["student_id"] not in submitted_ids:
                    continue
                conn.execute(
                    """
                    INSERT INTO assessment_marks
                    (assessment_id, student_id, candidate_mark, candidate_status,
                     published_mark, published_status, batch_id, updated_at)
                    VALUES (?, ?, ?, 'RECORDED', NULL, 'MISSING', ?, ?)
                    """,
                    (assessment_id, row["student_id"], row["mark"], batch_id, now),
                )

            self._audit(
                conn,
                "BATCH",
                batch_id,
                user_id,
                "BATCH_SUBMITTED",
                {
                    "assessment_id": assessment_id,
                    "student_count": preview["enrolled_count"],
                    "submitted_count": preview["submitted_count"],
                    "missing_count": preview["missing_count"],
                },
            )

        chain_tx = None
        if self.chain.enabled:
            try:
                chain_tx = self.chain.submit_batch(
                    batch_id,
                    assessment["course_id"],
                    assessment_id,
                    preview["enrolled_count"],
                    marks_hash,
                )
                self._set_chain_state(
                    batch_id,
                    1,
                    "CONFIRMED",
                    chain_tx,
                    "CHAIN_SUBMISSION_CONFIRMED",
                )
            except ChainError as exc:
                self._set_chain_state(
                    batch_id,
                    1,
                    "ERROR",
                    None,
                    "CHAIN_SUBMISSION_FAILED",
                    {"error": str(exc)},
                )
                raise AppError(
                    "The batch was saved locally, but its blockchain submission failed. "
                    "Retry the chain operation from the batch view. " + str(exc),
                    502,
                )

        return {
            "batch_id": batch_id,
            "status": "SUBMITTED",
            "chain_state": "CONFIRMED" if self.chain.enabled else "LOCAL_ONLY",
            "chain_tx_hash": chain_tx,
            "missing_count": preview["missing_count"],
        }

    def _set_chain_state(
        self,
        batch_id: str,
        revision: int,
        state: str,
        tx_hash: str | None,
        action: str,
        extra: dict | None = None,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE batches SET chain_state = ?, chain_tx_hash = ? WHERE id = ?",
                (state, tx_hash, batch_id),
            )
            conn.execute(
                """
                UPDATE batch_revisions
                SET chain_state = ?, chain_tx_hash = ?
                WHERE batch_id = ? AND revision = ?
                """,
                (state, tx_hash, batch_id, revision),
            )
            self._audit(
                conn,
                "BATCH",
                batch_id,
                None,
                action,
                extra or {},
                chain_tx_hash=tx_hash,
            )

    def resolve_report(
        self,
        user_id: int,
        report_id: str,
        resolution_type: str,
        mark: float | None,
        note: str | None,
    ) -> dict:
        self.require_role(user_id, {"lecturer"})
        if resolution_type not in {"MARK_ENTERED", "NO_MARK_AWARDED"}:
            raise AppError("Unknown resolution type.")

        conn = self.db.connect()
        try:
            report = conn.execute(
                """
                SELECT r.*, a.name AS assessment, a.max_mark, a.course_id,
                       b.id AS batch_id, b.status AS batch_status, b.revision AS current_revision,
                       b.chain_state, b.marks_hash, b.commitment_salt
                FROM missing_reports r
                JOIN assessments a ON a.id = r.assessment_id
                JOIN courses c ON c.id = a.course_id
                JOIN batches b ON b.assessment_id = a.id
                WHERE r.id = ? AND c.lecturer_id = ?
                """,
                (report_id, user_id),
            ).fetchone()
            if not report:
                raise AppError("Report not found.", 404)
            if report["status"] != "OPEN":
                raise AppError("Only open missing-mark reports can be resolved.")
            if report["batch_status"] != "VERIFIED":
                raise AppError("The current published batch is not eligible for amendment.")
            if report["chain_state"] == "ERROR":
                raise AppError("The current batch has a chain error. Reconcile or retry the chain before amending.")

            if resolution_type == "MARK_ENTERED":
                if mark is None:
                    raise AppError("A mark is required.")
                if mark < 0 or mark > float(report["max_mark"]):
                    raise AppError(f"Mark must be between 0 and {report['max_mark']}.")
                new_mark = float(mark)
                new_status = "RECORDED"
            else:
                new_mark = 0.0
                new_status = "NO_MARK"

            all_marks = conn.execute(
                """
                SELECT student_id, candidate_mark, candidate_status
                FROM assessment_marks
                WHERE assessment_id = ?
                ORDER BY student_id
                """,
                (report["assessment_id"],),
            ).fetchall()
        finally:
            conn.close()

        target_student_id = int(report["student_id"])
        updated_rows = []
        for row in all_marks:
            if int(row["student_id"]) == target_student_id:
                updated_rows.append(
                    {
                        "student_id": int(row["student_id"]),
                        "mark": new_mark,
                        "status": new_status,
                    }
                )
            else:
                updated_rows.append(
                    {
                        "student_id": int(row["student_id"]),
                        "mark": row["candidate_mark"],
                        "status": row["candidate_status"],
                    }
                )

        salt = secrets.token_hex(16)
        canonical = json.dumps(
            sorted(updated_rows, key=lambda item: item["student_id"]),
            sort_keys=True,
            separators=(",", ":"),
        )
        new_hash = "0x" + hashlib.sha256(
            (salt + "|" + canonical).encode("utf-8")
        ).hexdigest()
        reason_text = note.strip() if note and note.strip() else (
            "missing mark resolved with entered mark"
            if resolution_type == "MARK_ENTERED"
            else "student confirmed to have no awarded mark"
        )
        reason_hash = "0x" + hashlib.sha256(reason_text.encode("utf-8")).hexdigest()
        new_revision = int(report["current_revision"]) + 1
        chain_state = "PENDING" if self.chain.enabled else "LOCAL_ONLY"
        now = utc_now()

        with self.db.transaction() as tx:
            old = tx.execute(
                """
                SELECT published_mark, published_status
                FROM assessment_marks
                WHERE assessment_id = ? AND student_id = ?
                """,
                (report["assessment_id"], target_student_id),
            ).fetchone()

            tx.execute(
                """
                UPDATE assessment_marks
                SET candidate_mark = ?, candidate_status = ?, updated_at = ?
                WHERE assessment_id = ? AND student_id = ?
                """,
                (
                    new_mark,
                    new_status,
                    now,
                    report["assessment_id"],
                    target_student_id,
                ),
            )

            tx.execute(
                """
                INSERT INTO mark_history
                (assessment_id, student_id, batch_id, old_mark, new_mark,
                 old_status, new_status, actor_id, action, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report["assessment_id"],
                    target_student_id,
                    report["batch_id"],
                    old["published_mark"],
                    new_mark,
                    old["published_status"],
                    new_status,
                    user_id,
                    resolution_type,
                    reason_text,
                    now,
                ),
            )

            tx.execute(
                """
                UPDATE batches
                SET status = 'AMENDED',
                    marks_hash = ?,
                    commitment_salt = ?,
                    revision = ?,
                    chain_state = ?,
                    chain_tx_hash = NULL
                WHERE id = ?
                """,
                (new_hash, salt, new_revision, chain_state, report["batch_id"]),
            )

            tx.execute(
                """
                INSERT INTO batch_revisions
                (batch_id, revision, marks_hash, reason_hash, kind, actor_id, chain_state, created_at)
                VALUES (?, ?, ?, ?, 'AMENDMENT', ?, ?, ?)
                """,
                (
                    report["batch_id"],
                    new_revision,
                    new_hash,
                    reason_hash,
                    user_id,
                    chain_state,
                    now,
                ),
            )

            tx.execute(
                """
                UPDATE missing_reports
                SET status = 'PENDING_REVIEW',
                    resolution_type = ?,
                    resolution_mark = ?,
                    lecturer_note = ?,
                    resolved_by = ?,
                    resolved_at = NULL
                WHERE id = ?
                """,
                (resolution_type, new_mark, reason_text, user_id, report_id),
            )

            self._audit(
                tx,
                "BATCH",
                report["batch_id"],
                user_id,
                "BATCH_AMENDED",
                {
                    "revision": new_revision,
                    "report_id": report_id,
                    "reason": reason_text,
                },
            )

        chain_tx = None
        if self.chain.enabled:
            try:
                chain_tx = self.chain.amend_batch(
                    report["batch_id"],
                    new_hash,
                    reason_hash,
                )
                self._set_chain_state(
                    report["batch_id"],
                    new_revision,
                    "CONFIRMED",
                    chain_tx,
                    "CHAIN_AMENDMENT_CONFIRMED",
                )
            except ChainError as exc:
                self._set_chain_state(
                    report["batch_id"],
                    new_revision,
                    "ERROR",
                    None,
                    "CHAIN_AMENDMENT_FAILED",
                    {"error": str(exc)},
                )
                raise AppError(
                    "The amendment is stored locally but blockchain confirmation failed. "
                    "It remains pending chain reconciliation. " + str(exc),
                    502,
                )

        return {
            "report_id": report_id,
            "status": "PENDING_REVIEW",
            "batch_id": report["batch_id"],
            "revision": new_revision,
            "chain_state": "CONFIRMED" if self.chain.enabled else "LOCAL_ONLY",
            "chain_tx_hash": chain_tx,
        }

    def verify_batch(self, user_id: int, batch_id: str) -> dict:
        self.require_role(user_id, {"reviewer"})
        conn = self.db.connect()
        try:
            batch = conn.execute(
                """
                SELECT b.*, a.name AS assessment, c.code AS course
                FROM batches b
                JOIN assessments a ON a.id = b.assessment_id
                JOIN courses c ON c.id = a.course_id
                WHERE b.id = ?
                """,
                (batch_id,),
            ).fetchone()
            if not batch:
                raise AppError("Batch not found.", 404)
        finally:
            conn.close()

        if batch["status"] not in {"SUBMITTED", "AMENDED"}:
            raise AppError("Only submitted or amended batches can be verified.")
        if batch["chain_state"] in {"ERROR", "PENDING"}:
            raise AppError("The batch must have a confirmed or local-only audit state before verification.")

        chain_tx = None
        if self.chain.enabled:
            try:
                chain_tx = self.chain.verify_batch(batch_id)
            except ChainError as exc:
                self._set_chain_state(
                    batch_id,
                    int(batch["revision"]),
                    "ERROR",
                    None,
                    "CHAIN_VERIFICATION_FAILED",
                    {"error": str(exc)},
                )
                raise AppError("Blockchain verification failed: " + str(exc), 502)

        now = utc_now()
        with self.db.transaction() as tx:
            tx.execute(
                """
                UPDATE batches
                SET status = 'VERIFIED',
                    chain_state = ?,
                    chain_tx_hash = COALESCE(?, chain_tx_hash),
                    verified_by = ?,
                    verified_at = ?
                WHERE id = ?
                """,
                (
                    "CONFIRMED" if self.chain.enabled else "LOCAL_ONLY",
                    chain_tx,
                    user_id,
                    now,
                    batch_id,
                ),
            )

            tx.execute(
                """
                UPDATE assessment_marks
                SET published_mark = candidate_mark,
                    published_status = candidate_status,
                    updated_at = ?
                WHERE batch_id = ?
                """,
                (now, batch_id),
            )

            tx.execute(
                """
                UPDATE missing_reports
                SET status = 'RESOLVED', resolved_at = ?, resolved_by = ?
                WHERE assessment_id = (SELECT assessment_id FROM batches WHERE id = ?)
                  AND status = 'PENDING_REVIEW'
                """,
                (now, user_id, batch_id),
            )

            self._audit(
                tx,
                "BATCH",
                batch_id,
                user_id,
                "BATCH_VERIFIED",
                {"revision": batch["revision"], "published": True},
                chain_tx_hash=chain_tx,
            )

        return {
            "batch_id": batch_id,
            "status": "VERIFIED",
            "revision": int(batch["revision"]),
            "chain_state": "CONFIRMED" if self.chain.enabled else "LOCAL_ONLY",
            "chain_tx_hash": chain_tx,
        }

    def batch_audit(self, user_id: int, batch_id: str) -> dict:
        self.require_role(user_id, {"student", "lecturer", "reviewer", "admin"})
        conn = self.db.connect()
        try:
            batch = conn.execute(
                """
                SELECT b.*, a.name AS assessment, c.code AS course, c.title AS course_title
                FROM batches b
                JOIN assessments a ON a.id = b.assessment_id
                JOIN courses c ON c.id = a.course_id
                WHERE b.id = ?
                """,
                (batch_id,),
            ).fetchone()
            if not batch:
                raise AppError("Batch not found.", 404)

            events = conn.execute(
                """
                SELECT ae.*, u.full_name AS actor_name
                FROM audit_events ae
                LEFT JOIN users u ON u.id = ae.actor_id
                WHERE ae.entity_id = ?
                ORDER BY ae.created_at
                """,
                (batch_id,),
            ).fetchall()

            revisions = conn.execute(
                """
                SELECT br.*, u.full_name AS actor_name
                FROM batch_revisions br
                JOIN users u ON u.id = br.actor_id
                WHERE br.batch_id = ?
                ORDER BY br.revision
                """,
                (batch_id,),
            ).fetchall()

            history = conn.execute(
                """
                SELECT mh.*, u.full_name AS actor_name
                FROM mark_history mh
                JOIN users u ON u.id = mh.actor_id
                WHERE mh.batch_id = ?
                ORDER BY mh.created_at
                """,
                (batch_id,),
            ).fetchall()

            return {
                "batch": dict(batch),
                "events": [
                    {
                        **dict(row),
                        "metadata": json.loads(row["metadata_json"]),
                    }
                    for row in events
                ],
                "revisions": [dict(row) for row in revisions],
                "mark_history": [dict(row) for row in history],
            }
        finally:
            conn.close()

    def reconcile_batch(self, user_id: int, batch_id: str) -> dict:
        self.require_role(user_id, {"reviewer", "admin"})
        conn = self.db.connect()
        try:
            batch = conn.execute(
                "SELECT id, revision, marks_hash, chain_state FROM batches WHERE id = ?",
                (batch_id,),
            ).fetchone()
        finally:
            conn.close()

        if not batch:
            raise AppError("Batch not found.", 404)
        return self.chain.reconcile(
            batch["id"],
            int(batch["revision"]),
            batch["marks_hash"],
        )

    def retry_chain(self, user_id: int, batch_id: str) -> dict:
        self.require_role(user_id, {"lecturer", "reviewer", "admin"})
        if not self.chain.enabled:
            raise AppError("Blockchain integration is not configured.")

        conn = self.db.connect()
        try:
            batch = conn.execute(
                """
                SELECT b.*, a.course_id, a.id AS assessment_id
                FROM batches b
                JOIN assessments a ON a.id = b.assessment_id
                WHERE b.id = ?
                """,
                (batch_id,),
            ).fetchone()
        finally:
            conn.close()

        if not batch:
            raise AppError("Batch not found.", 404)

        try:
            if int(batch["revision"]) == 1:
                tx_hash = self.chain.submit_batch(
                    batch_id,
                    batch["course_id"],
                    batch["assessment_id"],
                    int(batch["student_count"]),
                    batch["marks_hash"],
                )
                action = "CHAIN_SUBMISSION_RETRIED"
            else:
                revision_conn = self.db.connect()
                try:
                    revision = revision_conn.execute(
                        """
                        SELECT reason_hash FROM batch_revisions
                        WHERE batch_id = ? AND revision = ?
                        """,
                        (batch_id, batch["revision"]),
                    ).fetchone()
                finally:
                    revision_conn.close()

                tx_hash = self.chain.amend_batch(
                    batch_id,
                    batch["marks_hash"],
                    revision["reason_hash"],
                )
                action = "CHAIN_AMENDMENT_RETRIED"

            self._set_chain_state(
                batch_id,
                int(batch["revision"]),
                "CONFIRMED",
                tx_hash,
                action,
            )
            return {
                "batch_id": batch_id,
                "chain_state": "CONFIRMED",
                "chain_tx_hash": tx_hash,
            }
        except ChainError as exc:
            self._set_chain_state(
                batch_id,
                int(batch["revision"]),
                "ERROR",
                None,
                "CHAIN_RETRY_FAILED",
                {"error": str(exc)},
            )
            raise AppError("Chain retry failed: " + str(exc), 502)

    def admin_users(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"admin"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT id, username, full_name, role, active, created_at
                FROM users
                ORDER BY role, username
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def admin_courses(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"admin"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT c.id, c.code, c.title, c.lecturer_id,
                       u.full_name AS lecturer_name,
                       (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id) AS students,
                       (SELECT COUNT(*) FROM assessments a WHERE a.course_id = c.id) AS assessments
                FROM courses c
                LEFT JOIN users u ON u.id = c.lecturer_id
                ORDER BY c.code
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def admin_create_user(
        self,
        user_id: int,
        username: str,
        full_name: str,
        role: str,
        password: str,
    ) -> dict:
        self.require_role(user_id, {"admin"})
        if not username.strip() or not full_name.strip():
            raise AppError("Username and full name are required.")
        if role not in {"student", "lecturer", "reviewer", "admin"}:
            raise AppError("Invalid role.")
        if len(password) < 8:
            raise AppError("Password must be at least 8 characters.")

        from .db import hash_password

        salt, digest = hash_password(password)
        try:
            with self.db.transaction() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO users
                    (username, full_name, role, password_salt, password_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (username.strip(), full_name.strip(), role, salt, digest, utc_now()),
                )
                new_id = int(cur.lastrowid)
                self._audit(
                    conn,
                    "USER",
                    str(new_id),
                    user_id,
                    "USER_CREATED",
                    {"username": username, "role": role},
                )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise AppError("Username already exists.")
            raise
        return {"id": new_id}

    def admin_create_course(
        self,
        user_id: int,
        code: str,
        title: str,
        lecturer_id: int,
    ) -> dict:
        self.require_role(user_id, {"admin"})
        if not code.strip() or not title.strip():
            raise AppError("Course code and title are required.")

        course_id = "course-" + uuid.uuid4().hex[:16]
        conn = self.db.connect()
        try:
            lecturer = conn.execute(
                "SELECT id FROM users WHERE id = ? AND role = 'lecturer' AND active = 1",
                (lecturer_id,),
            ).fetchone()
        finally:
            conn.close()

        if not lecturer:
            raise AppError("Selected lecturer is invalid.")

        try:
            with self.db.transaction() as tx:
                tx.execute(
                    """
                    INSERT INTO courses (id, code, title, lecturer_id, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (course_id, code.strip(), title.strip(), lecturer_id, utc_now()),
                )
                self._audit(
                    tx,
                    "COURSE",
                    course_id,
                    user_id,
                    "COURSE_CREATED",
                    {"code": code, "lecturer_id": lecturer_id},
                )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise AppError("Course code already exists.")
            raise
        return {"id": course_id}

    def admin_enroll(
        self,
        user_id: int,
        course_id: str,
        student_ids: list[int],
    ) -> dict:
        self.require_role(user_id, {"admin"})
        if not student_ids:
            raise AppError("Provide at least one student.")

        with self.db.transaction() as conn:
            course = conn.execute(
                "SELECT 1 FROM courses WHERE id = ?",
                (course_id,),
            ).fetchone()
            if not course:
                raise AppError("Course not found.", 404)

            for student_id in student_ids:
                student = conn.execute(
                    "SELECT id FROM users WHERE id = ? AND role = 'student' AND active = 1",
                    (student_id,),
                ).fetchone()
                if not student:
                    raise AppError(f"Student {student_id} is invalid.")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO enrollments (course_id, student_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (course_id, student_id, utc_now()),
                )

            self._audit(
                conn,
                "COURSE",
                course_id,
                user_id,
                "STUDENTS_ENROLLED",
                {"student_ids": student_ids},
            )
        return {"enrolled": len(student_ids)}

    def admin_create_assessment(
        self,
        user_id: int,
        course_id: str,
        name: str,
        max_mark: float,
    ) -> dict:
        self.require_role(user_id, {"admin"})
        if not name.strip():
            raise AppError("Assessment name is required.")
        if max_mark <= 0:
            raise AppError("Maximum mark must be greater than zero.")

        assessment_id = "assessment-" + uuid.uuid4().hex[:16]
        with self.db.transaction() as conn:
            course = conn.execute(
                "SELECT 1 FROM courses WHERE id = ?",
                (course_id,),
            ).fetchone()
            if not course:
                raise AppError("Course not found.", 404)

            conn.execute(
                """
                INSERT INTO assessments (id, course_id, name, max_mark, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (assessment_id, course_id, name.strip(), max_mark, utc_now()),
            )
            self._audit(
                conn,
                "ASSESSMENT",
                assessment_id,
                user_id,
                "ASSESSMENT_CREATED",
                {"course_id": course_id, "max_mark": max_mark},
            )
        return {"id": assessment_id}
