from __future__ import annotations

import csv
import hashlib
import io
import json
import secrets
import uuid
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .chain import ChainClient, ChainError, ChainPendingError, bytes32_hash
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

    @staticmethod
    def _notify(
        conn,
        user_id: int,
        event_type: str,
        title: str,
        body: str,
        created_at: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO notifications (user_id, event_type, title, body, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, event_type, title, body, created_at or utc_now()),
        )

    def student_notifications(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"student"})
        conn = self.db.connect()
        try:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, event_type, title, body, created_at, read_at
                    FROM notifications
                    WHERE user_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT 100
                    """,
                    (user_id,),
                ).fetchall()
            ]
        finally:
            conn.close()

    def mark_notification_read(self, user_id: int, notification_id: int) -> dict:
        self.require_role(user_id, {"student"})
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE notifications SET read_at = ?
                WHERE id = ? AND user_id = ? AND read_at IS NULL
                """,
                (utc_now(), notification_id, user_id),
            )
            if cursor.rowcount == 0:
                exists = conn.execute(
                    "SELECT 1 FROM notifications WHERE id = ? AND user_id = ?",
                    (notification_id, user_id),
                ).fetchone()
                if not exists:
                    raise AppError("Notification not found.", 404)
        return {"id": notification_id, "read": True}

    @staticmethod
    def _timestamp(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _pipeline_summary(self, conn, batch) -> dict:
        labels = {
            "DEPARTMENT_REVIEW": ("Department / reviewer", "reviewer"),
            "EXAM_OFFICE": ("Exam office", "exam_office"),
            "PORTAL_IMPORT": ("Portal operator", "portal_operator"),
            "PUBLISHED": ("Published to students", None),
        }
        rows = conn.execute(
            """
            SELECT ae.action, ae.created_at, u.full_name AS actor_name
            FROM audit_events ae
            LEFT JOIN users u ON u.id = ae.actor_id
            WHERE ae.entity_type = 'BATCH' AND ae.entity_id = ?
              AND ae.action IN (
                  'BATCH_SUBMITTED','BATCH_AMENDED','BATCH_VERIFIED',
                  'EXAM_OFFICE_PROCESSED','PORTAL_IMPORTED'
              )
            ORDER BY ae.created_at, ae.id
            """,
            (batch["id"],),
        ).fetchall()

        completed: list[dict] = []
        active: dict | None = None

        def close_stage(ended_at: str, actor_name: str | None) -> None:
            nonlocal active
            if active is None:
                return
            duration = max(
                0,
                int((self._timestamp(ended_at) - self._timestamp(active["started_at"])).total_seconds()),
            )
            completed.append(
                {
                    **active,
                    "completed_at": ended_at,
                    "duration_seconds": duration,
                    "completed_by": actor_name,
                }
            )
            active = None

        starts = {
            "BATCH_SUBMITTED": "DEPARTMENT_REVIEW",
            "BATCH_AMENDED": "DEPARTMENT_REVIEW",
            "BATCH_VERIFIED": "EXAM_OFFICE",
            "EXAM_OFFICE_PROCESSED": "PORTAL_IMPORT",
            "PORTAL_IMPORTED": "PUBLISHED",
        }
        for row in rows:
            action = row["action"]
            when = row["created_at"]
            actor = row["actor_name"]
            if action in {"BATCH_SUBMITTED", "BATCH_AMENDED"}:
                close_stage(when, actor)
            elif action == "BATCH_VERIFIED":
                close_stage(when, actor)
            elif action == "EXAM_OFFICE_PROCESSED":
                close_stage(when, actor)
            elif action == "PORTAL_IMPORTED":
                close_stage(when, actor)

            stage = starts[action]
            active = (
                {
                    "stage": stage,
                    "owner": labels[stage][0],
                    "owner_role": labels[stage][1],
                    "started_at": when,
                }
                if stage != "PUBLISHED"
                else None
            )

        current_stage = batch["pipeline_stage"]
        if current_stage == "PUBLISHED":
            active = None
        elif active is None or active["stage"] != current_stage:
            started_at = (
                batch["submitted_at"]
                if current_stage == "DEPARTMENT_REVIEW"
                else batch["verified_at"] or batch["submitted_at"]
            )
            active = {
                "stage": current_stage,
                "owner": labels[current_stage][0],
                "owner_role": labels[current_stage][1],
                "started_at": started_at,
            }

        now = datetime.now(timezone.utc)
        current_wait = 0
        if active:
            current_wait = max(
                0,
                int((now - self._timestamp(active["started_at"])).total_seconds()),
            )
        return {
            "current_stage": current_stage,
            "current_owner": labels[current_stage][0],
            "current_owner_role": labels[current_stage][1],
            "waiting_since": active["started_at"] if active else None,
            "waiting_seconds": current_wait,
            "stages": completed
            + (
                [
                    {
                        **active,
                        "completed_at": None,
                        "duration_seconds": current_wait,
                        "completed_by": None,
                    }
                ]
                if active
                else []
            ),
        }

    def batch_pipeline(self, user_id: int, batch_id: str) -> dict:
        self.require_role(
            user_id,
            {
                "student", "lecturer", "reviewer", "exam_office",
                "portal_operator", "admin",
            },
        )
        conn = self.db.connect()
        try:
            batch = conn.execute(
                """
                SELECT b.id, b.status, b.pipeline_stage, b.submitted_at, b.verified_at,
                       a.course_id, c.lecturer_id
                FROM batches b
                JOIN assessments a ON a.id = b.assessment_id
                JOIN courses c ON c.id = a.course_id
                WHERE b.id = ?
                """,
                (batch_id,),
            ).fetchone()
            if not batch:
                raise AppError("Batch not found.", 404)
            user = self.user(user_id)
            if user["role"] == "student":
                allowed = conn.execute(
                    "SELECT 1 FROM enrollments WHERE course_id = ? AND student_id = ?",
                    (batch["course_id"], user_id),
                ).fetchone()
                if not allowed:
                    raise AppError("You do not have access to this batch.", 403)
            if user["role"] == "lecturer" and batch["lecturer_id"] != user_id:
                raise AppError("You do not have access to this batch.", 403)
            return {"batch_id": batch_id, **self._pipeline_summary(conn, batch)}
        finally:
            conn.close()

    def dashboard(self, user_id: int) -> dict:
        user = self.require_role(
            user_id,
            {
                "student", "lecturer", "reviewer", "exam_office",
                "portal_operator", "admin",
            },
        )
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
                                WHEN b.pipeline_stage = 'PUBLISHED'
                                 AND (am.published_status = 'MISSING' OR am.published_status IS NULL)
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
                    """
                    SELECT COUNT(*) AS n FROM batches
                    WHERE status IN ('SUBMITTED','AMENDED')
                      AND pipeline_stage = 'DEPARTMENT_REVIEW'
                    """
                ).fetchone()
                counts = {"pending_verification": int(row["n"] or 0)}
            elif user["role"] == "exam_office":
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM batches WHERE pipeline_stage = 'EXAM_OFFICE'"
                ).fetchone()
                counts = {"pending_processing": int(row["n"] or 0)}
            elif user["role"] == "portal_operator":
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM batches WHERE pipeline_stage = 'PORTAL_IMPORT'"
                ).fetchone()
                counts = {"pending_import": int(row["n"] or 0)}
            else:
                rows = conn.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM users) AS users,
                        (SELECT COUNT(*) FROM courses) AS courses,
                        (SELECT COUNT(*) FROM assessments) AS assessments,
                        (SELECT COUNT(*) FROM missing_reports
                         WHERE status IN ('OPEN','PENDING_REVIEW')) AS issues
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
            now = utc_now()
            rows = conn.execute(
                """
                SELECT
                    a.id AS assessment_id,
                    a.name AS assessment,
                    a.max_mark,
                    a.submission_deadline,
                    c.code,
                    c.title,
                    COALESCE(b.status, 'NOT_SUBMITTED') AS batch_status,
                    COALESCE(b.pipeline_stage, 'NOT_SUBMITTED') AS pipeline_stage,
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
            result = []
            for row in rows:
                pipeline_stage = row["pipeline_stage"]
                deadline = row["submission_deadline"]
                overdue = bool(
                    deadline
                    and now > deadline
                    and pipeline_stage == "NOT_SUBMITTED"
                )
                status = (
                    row["published_status"]
                    if (
                        pipeline_stage == "PUBLISHED"
                        or row["published_mark"] is not None
                    )
                    else (
                        "OVERDUE" if overdue
                        else (
                            "NOT_SUBMITTED"
                            if pipeline_stage == "NOT_SUBMITTED"
                            else "AWAITING_PUBLICATION"
                        )
                    )
                )
                result.append({
                    "assessment_id": row["assessment_id"],
                    "assessment": row["assessment"],
                    "max_mark": row["max_mark"],
                    "course": row["code"],
                    "course_title": row["title"],
                    "batch_status": row["batch_status"],
                    "mark": row["published_mark"],
                    "status": status,
                    "batch_id": row["batch_id"],
                    "pipeline_stage": pipeline_stage,
                    "submission_deadline": deadline,
                    "overdue": overdue,
                })
            return result
        finally:
            conn.close()

    def student_mark_detail(self, user_id: int, assessment_id: str) -> dict:
        """Per-assessment drill-down: pipeline status + student's own mark history."""
        self.require_role(user_id, {"student"})
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT
                    a.id AS assessment_id,
                    a.name AS assessment,
                    a.max_mark,
                    a.submission_deadline,
                    c.code,
                    c.title,
                    COALESCE(b.status, 'NOT_SUBMITTED') AS batch_status,
                    COALESCE(b.pipeline_stage, 'NOT_SUBMITTED') AS pipeline_stage,
                    am.published_mark,
                    COALESCE(am.published_status, 'MISSING') AS published_status,
                    b.id AS batch_id
                FROM enrollments e
                JOIN courses c ON c.id = e.course_id
                JOIN assessments a ON a.course_id = c.id AND a.id = ?
                LEFT JOIN assessment_marks am
                    ON am.assessment_id = a.id AND am.student_id = e.student_id
                LEFT JOIN batches b ON b.id = am.batch_id
                WHERE e.student_id = ?
                """,
                (assessment_id, user_id),
            ).fetchone()
            if not row:
                raise AppError("Assessment not found or you are not enrolled.", 404)

            pipeline = None
            if row["batch_id"]:
                batch = conn.execute(
                    "SELECT id, status, pipeline_stage, submitted_at, verified_at FROM batches WHERE id = ?",
                    (row["batch_id"],),
                ).fetchone()
                pipeline = self._pipeline_summary(conn, batch)

            # Own mark history only — filtered to this student
            mark_history = conn.execute(
                """
                SELECT mh.created_at, mh.old_mark, mh.new_mark,
                       mh.old_status, mh.new_status, mh.action, mh.reason,
                       u.full_name AS actor_name
                FROM mark_history mh
                JOIN users u ON u.id = mh.actor_id
                WHERE mh.assessment_id = ? AND mh.student_id = ?
                ORDER BY mh.created_at
                """,
                (assessment_id, user_id),
            ).fetchall()

            # Check for open report
            open_report = conn.execute(
                """
                SELECT id, status, opened_at, resolution_type, lecturer_note
                FROM missing_reports
                WHERE assessment_id = ? AND student_id = ?
                  AND status IN ('OPEN','PENDING_REVIEW')
                LIMIT 1
                """,
                (assessment_id, user_id),
            ).fetchone()

            return {
                "assessment_id": row["assessment_id"],
                "assessment": row["assessment"],
                "max_mark": row["max_mark"],
                "submission_deadline": row["submission_deadline"],
                "course": row["code"],
                "course_title": row["title"],
                "batch_status": row["batch_status"],
                "mark": row["published_mark"],
                "published_status": row["published_status"],
                "batch_id": row["batch_id"],
                "pipeline_stage": row["pipeline_stage"],
                "pipeline": pipeline,
                "mark_history": [dict(h) for h in mark_history],
                "open_report": dict(open_report) if open_report else None,
            }
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
                    b.status AS batch_status,
                    b.pipeline_stage
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
            if (
                row["batch_status"] != "VERIFIED"
                or row["pipeline_stage"] != "PUBLISHED"
            ):
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
                    b.chain_state,
                    b.pipeline_stage
                FROM assessments a
                JOIN courses c ON c.id = a.course_id
                LEFT JOIN enrollments e ON e.course_id = c.id
                LEFT JOIN batches b ON b.assessment_id = a.id
                WHERE c.lecturer_id = ?
                GROUP BY
                    a.id, c.code, c.title, b.id, b.status, b.revision,
                    b.chain_state, b.pipeline_stage
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
                    b.pipeline_stage,
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
                JOIN batches b ON b.assessment_id = a.id
                WHERE c.lecturer_id = ?
                ORDER BY
                    CASE r.status
                        WHEN 'OPEN' THEN 0
                        WHEN 'PENDING_REVIEW' THEN 1
                        WHEN 'REJECTED' THEN 2
                        ELSE 3
                    END,
                    r.opened_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def reject_report(self, user_id: int, report_id: str, reason: str) -> dict:
        self.require_role(user_id, {"lecturer"})
        reason = reason.strip()
        if not reason:
            raise AppError("A reason is required to reject a report.")

        with self.db.transaction() as conn:
            report = conn.execute(
                """
                SELECT r.id, r.status, a.id AS assessment_id, b.status AS batch_status,
                       b.pipeline_stage
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
                raise AppError("Only open reports can be rejected.")
            if (
                report["batch_status"] != "VERIFIED"
                or report["pipeline_stage"] != "PUBLISHED"
            ):
                raise AppError("The assessment is not currently published.")

            now = utc_now()
            conn.execute(
                """
                UPDATE missing_reports
                SET status = 'REJECTED',
                    resolution_type = 'REPORT_REJECTED',
                    lecturer_note = ?,
                    resolved_by = ?,
                    resolved_at = ?
                WHERE id = ?
                """,
                (reason, user_id, now, report_id),
            )
            self._audit(
                conn,
                "REPORT",
                report_id,
                user_id,
                "REPORT_REJECTED",
                {"assessment_id": report["assessment_id"], "reason": reason},
            )
            student_id = conn.execute(
                "SELECT student_id FROM missing_reports WHERE id = ?",
                (report_id,),
            ).fetchone()["student_id"]
            self._notify(
                conn,
                int(student_id),
                "REPORT_REJECTED",
                "Missing-mark report rejected",
                reason,
                now,
            )
        return {"report_id": report_id, "status": "REJECTED"}

    def exam_office_batches(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"exam_office"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT b.id, b.status, b.pipeline_stage, b.student_count, b.revision,
                       b.submitted_at, a.name AS assessment, c.code AS course,
                       u.full_name AS lecturer_name
                FROM batches b
                JOIN assessments a ON a.id = b.assessment_id
                JOIN courses c ON c.id = a.course_id
                JOIN users u ON u.id = b.submitted_by
                WHERE b.pipeline_stage = 'EXAM_OFFICE'
                ORDER BY b.verified_at, b.submitted_at
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def portal_batches(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"portal_operator"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT b.id, b.status, b.pipeline_stage, b.student_count, b.revision,
                       b.submitted_at, a.name AS assessment, c.code AS course,
                       u.full_name AS lecturer_name
                FROM batches b
                JOIN assessments a ON a.id = b.assessment_id
                JOIN courses c ON c.id = a.course_id
                JOIN users u ON u.id = b.submitted_by
                WHERE b.pipeline_stage = 'PORTAL_IMPORT'
                ORDER BY b.verified_at, b.submitted_at
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def _advance_handoff(
        self,
        user_id: int,
        batch_id: str,
        required_role: str,
        from_stage: str,
        to_stage: str,
        action: str,
    ) -> dict:
        self.require_role(user_id, {required_role})
        now = utc_now()
        with self.db.transaction() as conn:
            batch = conn.execute(
                "SELECT status, pipeline_stage FROM batches WHERE id = ?",
                (batch_id,),
            ).fetchone()
            if not batch:
                raise AppError("Batch not found.", 404)
            if batch["status"] != "VERIFIED" or batch["pipeline_stage"] != from_stage:
                raise AppError("This batch is not ready for this handoff.")
            conn.execute(
                "UPDATE batches SET pipeline_stage = ? WHERE id = ?",
                (to_stage, batch_id),
            )
            self._audit(
                conn,
                "BATCH",
                batch_id,
                user_id,
                action,
                {"from_stage": from_stage, "to_stage": to_stage},
            )
        return {"batch_id": batch_id, "pipeline_stage": to_stage}

    def process_exam_office_batch(self, user_id: int, batch_id: str) -> dict:
        return self._advance_handoff(
            user_id,
            batch_id,
            "exam_office",
            "EXAM_OFFICE",
            "PORTAL_IMPORT",
            "EXAM_OFFICE_PROCESSED",
        )

    def publish_portal_batch(self, user_id: int, batch_id: str) -> dict:
        self.require_role(user_id, {"portal_operator"})
        now = utc_now()
        conn = self.db.connect()
        try:
            batch = conn.execute(
                """
                SELECT status, pipeline_stage, revision, marks_hash
                FROM batches WHERE id = ?
                """,
                (batch_id,),
            ).fetchone()
        finally:
            conn.close()
        if not batch:
            raise AppError("Batch not found.", 404)
        if batch["status"] != "VERIFIED" or batch["pipeline_stage"] != "PORTAL_IMPORT":
            raise AppError("This batch is not ready for portal publication.")

        integrity = self._chain_integrity(batch_id)
        if not integrity.get("match"):
            raise AppError(
                "Publication blocked: the complete local commitment and "
                "configured on-chain batch history could not be verified. "
                f"{integrity.get('reason', 'Resolve the discrepancy before publishing.')}",
                409,
            )

        with self.db.transaction() as conn:
            current = conn.execute(
                """
                SELECT status, pipeline_stage, revision, marks_hash,
                       commitment_salt, student_count
                FROM batches WHERE id = ?
                """,
                (batch_id,),
            ).fetchone()
            if (
                not current
                or current["status"] != "VERIFIED"
                or current["pipeline_stage"] != "PORTAL_IMPORT"
                or current["revision"] != batch["revision"]
                or current["marks_hash"] != batch["marks_hash"]
            ):
                raise AppError(
                    "Publication blocked: the batch changed while its history was being checked.",
                    409,
                )
            latest_revision = conn.execute(
                """
                SELECT marks_hash, commitment_salt, canonical_marks
                FROM batch_revisions
                WHERE batch_id = ? AND revision = ?
                """,
                (batch_id, current["revision"]),
            ).fetchone()
            current_marks = conn.execute(
                """
                SELECT m.student_id, m.candidate_mark AS mark,
                       m.candidate_status AS status, u.reg_number
                FROM assessment_marks m
                JOIN users u ON u.id = m.student_id
                WHERE m.batch_id = ?
                ORDER BY m.student_id
                """,
                (batch_id,),
            ).fetchall()
            current_forms = {
                self._canonical_mark_snapshot(current_marks, "mark", "status", False),
                self._canonical_mark_snapshot(current_marks, "mark", "status", True),
            }
            if (
                not latest_revision
                or not latest_revision["canonical_marks"]
                or not latest_revision["commitment_salt"]
                or len(current_marks) != int(current["student_count"])
                or latest_revision["marks_hash"].lower() != current["marks_hash"].lower()
                or latest_revision["commitment_salt"] != current["commitment_salt"]
                or latest_revision["canonical_marks"] not in current_forms
                or (
                    "0x"
                    + hashlib.sha256(
                        (
                            latest_revision["commitment_salt"]
                            + "|"
                            + latest_revision["canonical_marks"]
                        ).encode("utf-8")
                    ).hexdigest()
                ).lower()
                != current["marks_hash"].lower()
            ):
                raise AppError(
                    "Publication blocked: marks changed while publication was being prepared.",
                    409,
                )
            conn.execute(
                """
                UPDATE assessment_marks
                SET published_mark = candidate_mark,
                    published_status = candidate_status,
                    updated_at = ?
                WHERE batch_id = ?
                """,
                (now, batch_id),
            )
            conn.execute(
                "UPDATE batches SET pipeline_stage = 'PUBLISHED' WHERE id = ?",
                (batch_id,),
            )
            conn.execute(
                """
                UPDATE missing_reports
                SET status = 'RESOLVED', resolved_at = ?, resolved_by = ?
                WHERE assessment_id = (SELECT assessment_id FROM batches WHERE id = ?)
                  AND status = 'PENDING_REVIEW'
                """,
                (now, user_id, batch_id),
            )
            self._audit(
                conn,
                "BATCH",
                batch_id,
                user_id,
                "PORTAL_IMPORTED",
                {"revision": batch["revision"], "published": True},
            )
            assessment = conn.execute(
                "SELECT assessment_id FROM batches WHERE id = ?",
                (batch_id,),
            ).fetchone()
            students = conn.execute(
                """
                SELECT student_id FROM enrollments
                WHERE course_id = (
                    SELECT course_id FROM assessments WHERE id = ?
                )
                """,
                (assessment["assessment_id"],),
            ).fetchall()
            reports = conn.execute(
                """
                SELECT student_id FROM missing_reports
                WHERE assessment_id = ? AND status = 'RESOLVED'
                  AND resolved_at = ?
                """,
                (assessment["assessment_id"], now),
            ).fetchall()
            resolved_students = {int(report["student_id"]) for report in reports}
            for student in students:
                student_id = int(student["student_id"])
                if student_id in resolved_students:
                    self._notify(
                        conn,
                        student_id,
                        "REPORT_RESOLVED",
                        "Missing-mark report resolved",
                        "Your reported assessment outcome has been published.",
                        now,
                    )
                else:
                    self._notify(
                        conn,
                        student_id,
                        "MARKS_PUBLISHED",
                        "Marks published",
                        "Marks for this assessment have been imported and published.",
                        now,
                    )
        return {
            "batch_id": batch_id,
            "pipeline_stage": "PUBLISHED",
            "status": "VERIFIED",
        }

    def reviewer_batches(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"reviewer"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    b.id,
                    b.status,
                    b.pipeline_stage,
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
            raise AppError("CSV must include headers: registration_number,mark.")
        normalized = {h.strip().lower(): h for h in reader.fieldnames if h}
        # Accept registration_number, reg_number, or student_id for backwards compat
        reg_header = (
            normalized.get("registration_number")
            or normalized.get("reg_number")
            or normalized.get("student_id")
            or normalized.get("student")
        )
        mark_header = normalized.get("mark")
        if not reg_header or not mark_header:
            raise AppError("CSV headers must include registration_number and mark.")

        rows: list[dict[str, str]] = []
        for row in reader:
            reg = (row.get(reg_header) or "").strip().upper()
            mark = (row.get(mark_header) or "").strip()
            if not reg and not mark:
                continue
            rows.append({"registration_number": reg, "mark": mark})
        return rows

    def _batch_context(self, user_id: int, assessment_id: str):
        self.require_role(user_id, {"lecturer"})
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

            if row["lecturer_id"] != user_id:
                raise AppError("You are not the lecturer for this course.", 403)

            students = conn.execute(
                """
                SELECT u.id, u.username, u.full_name, u.reg_number
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

        # Build roster keyed by uppercase reg_number -> student dict
        roster: dict[str, dict] = {}
        for s in students:
            reg = (s["reg_number"] or "").strip().upper()
            if reg:
                roster[reg] = dict(s)
        seen: set[str] = set()
        errors: list[str] = []
        normalized_rows: list[dict] = []

        for index, row in enumerate(rows, start=2):
            reg = row["registration_number"]
            mark_text = row["mark"]

            if not reg:
                errors.append(f"Row {index}: registration_number is empty.")
                continue

            if reg in seen:
                errors.append(f"Row {index}: duplicate registration_number {reg}.")
                continue
            seen.add(reg)

            if reg not in roster:
                errors.append(
                    f"Row {index}: registration_number {reg} is not enrolled in {assessment['course_code']}."
                )
                continue

            try:
                mark = float(mark_text)
            except ValueError:
                errors.append(f"Row {index}: mark for {reg} is not numeric.")
                continue

            if mark < 0 or mark > float(assessment["max_mark"]):
                errors.append(
                    f"Row {index}: mark for {reg} must be between 0 and {assessment['max_mark']}."
                )
                continue

            normalized_rows.append(
                {
                    "student_id": int(roster[reg]["id"]),
                    "registration_number": reg,
                    "mark": mark,
                    "status": "RECORDED",
                }
            )

        missing = [
            {
                "student_id": int(s["id"]),
                "username": s["username"],
                "full_name": s["full_name"],
                "registration_number": (s["reg_number"] or "").strip().upper(),
            }
            for s in students
            if (s["reg_number"] or "").strip().upper() not in seen
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
        canonical_rows = [
            {
                "student_id": item["student_id"],
                "mark": item["mark"],
                "status": item["status"],
            }
            for item in preview["rows"]
        ]
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
                 commitment_salt, revision, chain_state, submitted_at, pipeline_stage)
                VALUES (?, ?, ?, 'SUBMITTED', ?, ?, ?, 1, ?, ?, 'DEPARTMENT_REVIEW')
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
                (batch_id, revision, marks_hash, reason_hash, commitment_salt,
                 canonical_marks, kind, actor_id, chain_state, created_at)
                VALUES (?, 1, ?, ?, ?, ?, 'SUBMISSION', ?, ?, ?)
                """,
                (
                    batch_id,
                    marks_hash,
                    reason_hash,
                    salt,
                    canonical,
                    user_id,
                    chain_state,
                    now,
                ),
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
                _conn = self.db.connect()
                try:
                    _arow = _conn.execute(
                        "SELECT course_id FROM assessments WHERE id = ?",
                        (assessment_id,),
                    ).fetchone()
                finally:
                    _conn.close()
                chain_tx = self.chain.submit_batch(
                    batch_id,
                    _arow["course_id"],
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
                pending = isinstance(exc, ChainPendingError)
                self._set_chain_state(
                    batch_id,
                    1,
                    "PENDING" if pending else "ERROR",
                    getattr(exc, "tx_hash", None),
                    "CHAIN_SUBMISSION_PENDING" if pending else "CHAIN_SUBMISSION_FAILED",
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
        update_revision: bool = True,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE batches
                SET chain_state = ?, chain_tx_hash = COALESCE(?, chain_tx_hash)
                WHERE id = ?
                """,
                (state, tx_hash, batch_id),
            )
            if update_revision:
                conn.execute(
                    """
                    UPDATE batch_revisions
                    SET chain_state = ?, chain_tx_hash = COALESCE(?, chain_tx_hash)
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

    def _checkpoint_recovered_revision(
        self,
        batch_id: str,
        revision: int,
        tx_hash: str,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE batches
                SET chain_state = 'PENDING', chain_tx_hash = ?
                WHERE id = ?
                """,
                (tx_hash, batch_id),
            )
            conn.execute(
                """
                UPDATE batch_revisions
                SET chain_state = 'CONFIRMED', chain_tx_hash = ?
                WHERE batch_id = ? AND revision = ?
                """,
                (tx_hash, batch_id, revision),
            )
            self._audit(
                conn,
                "BATCH",
                batch_id,
                None,
                "CHAIN_REVISION_RECOVERY_CHECKPOINTED",
                {"revision": revision},
                chain_tx_hash=tx_hash,
            )

    def _checkpoint_recovered_action(
        self,
        batch_id: str,
        tx_hash: str,
        action: str,
        metadata: dict,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE batches
                SET chain_state = 'PENDING', chain_tx_hash = ?
                WHERE id = ?
                """,
                (tx_hash, batch_id),
            )
            self._audit(
                conn,
                "BATCH",
                batch_id,
                None,
                action,
                metadata,
                chain_tx_hash=tx_hash,
            )

    def _set_recovered_chain_state(
        self,
        batch_id: str,
        tx_hash: str | None,
        revision_tx_hashes: list[str | None],
        action: str,
        metadata: dict,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE batches
                SET chain_state = 'CONFIRMED',
                    chain_tx_hash = COALESCE(?, chain_tx_hash)
                WHERE id = ?
                """,
                (tx_hash, batch_id),
            )
            for revision, revision_tx_hash in enumerate(revision_tx_hashes, start=1):
                conn.execute(
                    """
                    UPDATE batch_revisions
                    SET chain_state = 'CONFIRMED',
                        chain_tx_hash = COALESCE(?, chain_tx_hash)
                    WHERE batch_id = ? AND revision = ?
                    """,
                    (revision_tx_hash, batch_id, revision),
                )
            self._audit(
                conn,
                "BATCH",
                batch_id,
                None,
                action,
                metadata,
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
                       b.id AS batch_id, b.status AS batch_status,
                       b.pipeline_stage, b.revision AS current_revision,
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
            if (
                report["batch_status"] != "VERIFIED"
                or report["pipeline_stage"] != "PUBLISHED"
            ):
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
                    chain_tx_hash = NULL,
                    pipeline_stage = 'DEPARTMENT_REVIEW'
                WHERE id = ?
                """,
                (new_hash, salt, new_revision, chain_state, report["batch_id"]),
            )

            tx.execute(
                """
                INSERT INTO batch_revisions
                (batch_id, revision, marks_hash, reason_hash, commitment_salt,
                 canonical_marks, kind, actor_id, chain_state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'AMENDMENT', ?, ?, ?)
                """,
                (
                    report["batch_id"],
                    new_revision,
                    new_hash,
                    reason_hash,
                    salt,
                    canonical,
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
            self._notify(
                tx,
                target_student_id,
                "MARK_AMENDED",
                "Mark amendment submitted",
                "A proposed mark update is awaiting department review and publication.",
                now,
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
                pending = isinstance(exc, ChainPendingError)
                self._set_chain_state(
                    report["batch_id"],
                    new_revision,
                    "PENDING" if pending else "ERROR",
                    getattr(exc, "tx_hash", None),
                    "CHAIN_AMENDMENT_PENDING" if pending else "CHAIN_AMENDMENT_FAILED",
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

        if (
            batch["status"] not in {"SUBMITTED", "AMENDED"}
            or batch["pipeline_stage"] != "DEPARTMENT_REVIEW"
        ):
            raise AppError("Only submitted or amended batches can be verified.")
        if batch["chain_state"] in {"ERROR", "PENDING"}:
            raise AppError("The batch must have a confirmed or local-only audit state before verification.")

        chain_tx = None
        if self.chain.enabled:
            try:
                chain_tx = self.chain.verify_batch(batch_id)
            except ChainError as exc:
                pending = isinstance(exc, ChainPendingError)
                self._set_chain_state(
                    batch_id,
                    int(batch["revision"]),
                    "PENDING" if pending else "ERROR",
                    getattr(exc, "tx_hash", None),
                    "CHAIN_VERIFICATION_PENDING" if pending else "CHAIN_VERIFICATION_FAILED",
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
                    verified_at = ?,
                    pipeline_stage = 'EXAM_OFFICE'
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

            self._audit(
                tx,
                "BATCH",
                batch_id,
                user_id,
                "BATCH_VERIFIED",
                {
                    "revision": batch["revision"],
                    "from_stage": "DEPARTMENT_REVIEW",
                    "to_stage": "EXAM_OFFICE",
                    "published": False,
                },
                chain_tx_hash=chain_tx,
            )

        return {
            "batch_id": batch_id,
            "status": "VERIFIED",
            "pipeline_stage": "EXAM_OFFICE",
            "revision": int(batch["revision"]),
            "chain_state": "CONFIRMED" if self.chain.enabled else "LOCAL_ONLY",
            "chain_tx_hash": chain_tx,
        }

    def batch_audit(self, user_id: int, batch_id: str) -> dict:
        user = self.require_role(
            user_id,
            {
                "student", "lecturer", "reviewer", "exam_office",
                "portal_operator", "admin",
            },
        )
        conn = self.db.connect()
        try:
            batch = conn.execute(
                """
                SELECT b.id, b.assessment_id, b.status, b.student_count,
                       b.marks_hash, b.revision, b.chain_state, b.chain_tx_hash,
                       b.submitted_at, b.verified_at, b.pipeline_stage,
                       a.name AS assessment, a.course_id,
                       c.code AS course, c.title AS course_title, c.lecturer_id
                FROM batches b
                JOIN assessments a ON a.id = b.assessment_id
                JOIN courses c ON c.id = a.course_id
                WHERE b.id = ?
                """,
                (batch_id,),
            ).fetchone()
            if not batch:
                raise AppError("Batch not found.", 404)

            if user["role"] == "student":
                allowed = conn.execute(
                    """
                    SELECT 1
                    FROM enrollments
                    WHERE course_id = ? AND student_id = ?
                    """,
                    (batch["course_id"], user_id),
                ).fetchone()
                if not allowed:
                    raise AppError("You do not have access to this batch.", 403)

            if user["role"] == "lecturer" and batch["lecturer_id"] != user_id:
                raise AppError("You do not have access to this batch.", 403)

            events = conn.execute(
                """
                SELECT ae.created_at, ae.action, ae.actor_id, ae.chain_tx_hash,
                       ae.metadata_json, u.full_name AS actor_name
                FROM audit_events ae
                LEFT JOIN users u ON u.id = ae.actor_id
                WHERE ae.entity_type = 'BATCH' AND ae.entity_id = ?
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
            revision_data = []
            for row in revisions:
                revision = dict(row)
                if user["role"] == "student":
                    revision = {
                        key: revision[key]
                        for key in (
                            "revision", "marks_hash", "kind", "chain_state",
                            "chain_tx_hash", "created_at", "actor_name",
                        )
                    }
                revision_data.append(revision)

            history = []
            if user["role"] != "student":
                history_rows = conn.execute(
                    """
                    SELECT mh.*, u.full_name AS actor_name,
                           student.full_name AS student_name,
                           student.reg_number AS student_reg_number
                    FROM mark_history mh
                    JOIN users u ON u.id = mh.actor_id
                    JOIN users student ON student.id = mh.student_id
                    WHERE mh.batch_id = ?
                    ORDER BY mh.created_at
                    """,
                    (batch_id,),
                ).fetchall()
                history = [dict(row) for row in history_rows]

            safe_batch_fields = (
                "id", "assessment_id", "status", "student_count", "marks_hash",
                "revision", "chain_state", "chain_tx_hash", "submitted_at",
                "verified_at", "pipeline_stage", "assessment", "course_id",
                "course", "course_title",
            )
            event_data = []
            for row in events:
                metadata = json.loads(row["metadata_json"])
                event = {
                    "created_at": row["created_at"],
                    "action": row["action"],
                    "actor_name": row["actor_name"],
                    "chain_tx_hash": row["chain_tx_hash"],
                }
                if user["role"] == "student":
                    public_metadata = {
                        "revision", "from_stage", "to_stage", "published",
                        "student_count", "submitted_count", "missing_count",
                        "chain_state",
                    }
                    metadata = {
                        key: value
                        for key, value in metadata.items()
                        if key in public_metadata
                    }
                else:
                    event["actor_id"] = row["actor_id"]
                event["metadata"] = metadata
                event_data.append(event)

            return {
                "batch": {key: batch[key] for key in safe_batch_fields},
                "pipeline": self._pipeline_summary(conn, batch),
                "events": event_data,
                "revisions": revision_data,
                "mark_history": history,
            }
        finally:
            conn.close()

    def batch_report_csv(self, user_id: int, batch_id: str) -> str:
        report = self.batch_audit(user_id, batch_id)
        rows = [["MarkTrail batch audit report"], ["Field", "Value"]]
        batch = report["batch"]
        for key in (
            "id",
            "course",
            "assessment",
            "status",
            "pipeline_stage",
            "revision",
            "student_count",
            "submitted_at",
            "verified_at",
            "marks_hash",
            "chain_state",
            "chain_tx_hash",
        ):
            rows.append([key, batch.get(key)])

        rows.extend(
            [
                [],
                ["Pipeline stage", "Started", "Completed", "Duration seconds", "Owner", "Completed by"],
            ]
        )
        for stage in report["pipeline"]["stages"]:
            rows.append(
                [
                    stage["stage"],
                    stage["started_at"],
                    stage["completed_at"],
                    stage["duration_seconds"],
                    stage["owner"],
                    stage["completed_by"],
                ]
            )

        rows.extend([[], ["Event time", "Actor", "Action", "Details"]])
        for event in report["events"]:
            rows.append(
                [
                    event["created_at"],
                    event["actor_name"],
                    event["action"],
                    json.dumps(event["metadata"], sort_keys=True),
                ]
            )

        if report["mark_history"]:
            rows.extend(
                [
                    [],
                    [
                        "Mark change time",
                        "Student ID",
                        "Actor",
                        "Action",
                        "Previous mark",
                        "New mark",
                        "Reason",
                    ],
                ]
            )
            for item in report["mark_history"]:
                rows.append(
                    [
                        item["created_at"],
                        item["student_id"],
                        item["actor_name"],
                        item["action"],
                        item["old_mark"],
                        item["new_mark"],
                        item["reason"],
                    ]
                )

        output = io.StringIO(newline="")
        writer = csv.writer(output)
        for row in rows:
            writer.writerow([self._sanitize_csv_cell(value) for value in row])
        return output.getvalue()

    @staticmethod
    def _sanitize_csv_cell(value: Any) -> Any:
        if not isinstance(value, str) or not value:
            return value

        normalized = unicodedata.normalize("NFKC", value)
        if value[0] in "\t\r\n":
            return "'" + value

        for char in normalized:
            if char.isspace() or unicodedata.category(char) in {"Cc", "Cf"}:
                continue
            if char in "=+-@":
                return "'" + value
            break
        return value

    def _chain_integrity(self, batch_id: str) -> dict:
        conn = self.db.connect()
        try:
            batch = conn.execute(
                """
                SELECT b.id, b.revision, b.marks_hash, b.status, b.chain_state,
                       b.commitment_salt, b.student_count, b.assessment_id,
                       a.course_id, b.pipeline_stage
                FROM batches b
                JOIN assessments a ON a.id = b.assessment_id
                WHERE b.id = ?
                """,
                (batch_id,),
            ).fetchone()
            revisions = conn.execute(
                """
                SELECT revision, marks_hash, reason_hash, commitment_salt,
                       canonical_marks
                FROM batch_revisions WHERE batch_id = ?
                ORDER BY revision
                """,
                (batch_id,),
            ).fetchall()
            mark_rows = conn.execute(
                """
                SELECT m.student_id, m.candidate_mark AS mark,
                       m.candidate_status AS status, m.published_mark,
                       m.published_status, u.reg_number
                FROM assessment_marks m
                JOIN users u ON u.id = m.student_id
                WHERE m.batch_id = ?
                ORDER BY m.student_id
                """,
                (batch_id,),
            ).fetchall()
        finally:
            conn.close()

        if not batch:
            raise AppError("Batch not found.", 404)
        expected_status = {
            "SUBMITTED": 1,
            "VERIFIED": 2,
            "AMENDED": 3,
        }.get(batch["status"])
        if (
            not revisions
            or len(revisions) != int(batch["revision"])
            or any(
                int(revision["revision"]) != index
                for index, revision in enumerate(revisions, start=1)
            )
            or revisions[-1]["marks_hash"].lower() != batch["marks_hash"].lower()
            or expected_status is None
            or (batch["status"] == "SUBMITTED" and int(batch["revision"]) != 1)
            or (batch["status"] == "AMENDED" and int(batch["revision"]) < 2)
        ):
            return {
                "status": "LOCAL_HISTORY_MISMATCH",
                "match": False,
                "reason": "The batch does not match its complete local revision history.",
            }

        canonical_forms = [
            self._canonical_mark_snapshot(mark_rows, "mark", "status", False),
            self._canonical_mark_snapshot(mark_rows, "mark", "status", True),
        ]
        canonical_marks = canonical_forms
        if len(mark_rows) != int(batch["student_count"]):
            return {
                "status": "MARK_COUNT_MISMATCH",
                "match": False,
                "reason": "The saved marks no longer contain the committed number of students.",
            }

        for index, revision in enumerate(revisions):
            snapshot = revision["canonical_marks"]
            salt = revision["commitment_salt"]
            if not snapshot or not salt:
                return {
                    "status": "REVISION_SNAPSHOT_UNAVAILABLE",
                    "match": False,
                    "reason": (
                        f"The saved mark snapshot for revision {index + 1} is unavailable; "
                        "the complete commitment history cannot be verified."
                    ),
                }
            snapshot_hash = "0x" + hashlib.sha256(
                (salt + "|" + snapshot).encode("utf-8")
            ).hexdigest()
            if snapshot_hash.lower() != revision["marks_hash"].lower():
                return {
                    "status": "REVISION_COMMITMENT_MISMATCH",
                    "match": False,
                    "reason": f"The saved mark snapshot for revision {index + 1} does not match its commitment.",
                }
            if index == len(revisions) - 1 and (
                salt != batch["commitment_salt"]
                or snapshot not in canonical_marks
                or snapshot_hash.lower() != batch["marks_hash"].lower()
            ):
                return {
                    "status": "CURRENT_MARKS_MISMATCH",
                    "match": False,
                    "reason": "The current marks no longer match the latest saved commitment.",
                }

        if batch["pipeline_stage"] == "PUBLISHED":
            published_forms = [
                self._canonical_mark_snapshot(
                    mark_rows, "published_mark", "published_status", False
                ),
                self._canonical_mark_snapshot(
                    mark_rows, "published_mark", "published_status", True
                ),
            ]
            latest_snapshot = revisions[-1]["canonical_marks"]
            if latest_snapshot not in published_forms:
                return {
                    "status": "PUBLISHED_MARKS_MISMATCH",
                    "match": False,
                    "reason": "Published marks no longer match the committed revision.",
                }

        if not self.chain.enabled:
            return {
                "status": "LOCAL_ONLY",
                "match": True,
                "reason": (
                    "Local marks match the saved commitment. No independent "
                    "on-chain anchor is configured."
                ),
                "on_chain": False,
            }

        result = self.chain.reconcile(
            batch["id"],
            int(batch["revision"]),
            revisions[-1]["marks_hash"],
        )
        if not result.get("match"):
            return result

        try:
            for index, revision in enumerate(revisions):
                on_chain = self.chain.get_revision_details(batch_id, index)
                expected_reason = (
                    "0x" + "00" * 32
                    if index == 0
                    else revision["reason_hash"]
                )
                if (
                    on_chain["marks_hash"].lower() != revision["marks_hash"].lower()
                    or on_chain["reason_hash"].lower() != expected_reason.lower()
                ):
                    return {
                        **result,
                        "status": "REVISION_MISMATCH",
                        "match": False,
                        "reason": f"On-chain revision {index + 1} differs from local history.",
                    }

            chain_batch = self.chain.get_batch_details(batch_id)
        except ChainError as exc:
            return {
                **result,
                "status": "CHAIN_ERROR",
                "match": False,
                "reason": str(exc),
            }

        expected_metadata = {
            "course_id": bytes32_hash(batch["course_id"]),
            "assessment_id": bytes32_hash(batch["assessment_id"]),
            "student_count": int(batch["student_count"]),
        }
        mismatched_metadata = any(
            chain_batch.get(key) != value
            for key, value in expected_metadata.items()
        )
        if mismatched_metadata:
            return {
                **result,
                "status": "BATCH_METADATA_MISMATCH",
                "match": False,
                "reason": "On-chain course, assessment, or student-count details differ from the application record.",
            }

        chain_status = chain_batch["status"]
        if chain_status != expected_status:
            return {
                **result,
                "status": "STATUS_MISMATCH",
                "match": False,
                "local_status": batch["status"],
                "chain_status": chain_status,
                "reason": "The application and contract workflow statuses differ.",
            }

        return {
            **result,
            "status": "MATCH",
            "match": True,
            "on_chain": True,
            "local_status": batch["status"],
            "chain_status": chain_status,
        }

    @staticmethod
    def _canonical_mark_snapshot(
        rows: list,
        mark_key: str,
        status_key: str,
        include_registration_number: bool,
    ) -> str:
        canonical_rows = []
        for row in rows:
            item = {
                "student_id": int(row["student_id"]),
                "mark": row[mark_key],
                "status": row[status_key],
            }
            if include_registration_number and item["status"] == "RECORDED":
                item["registration_number"] = (row["reg_number"] or "").strip().upper()
            canonical_rows.append(item)
        return json.dumps(
            canonical_rows,
            sort_keys=True,
            separators=(",", ":"),
        )

    def reconcile_batch(self, user_id: int, batch_id: str) -> dict:
        self.require_role(user_id, {"admin"})
        return self._chain_integrity(batch_id)

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

        pending_revision: int | None = None
        try:
            if batch["chain_tx_hash"]:
                previous_tx = batch["chain_tx_hash"]
                tx_status = self.chain.get_transaction_status(previous_tx)
                if tx_status == "PENDING":
                    raise ChainPendingError(
                        f"Transaction {previous_tx} is still awaiting confirmation.",
                        previous_tx,
                    )

            local_rev = int(batch["revision"])
            revision_conn = self.db.connect()
            try:
                revisions = revision_conn.execute(
                    """
                    SELECT revision, marks_hash, reason_hash, chain_tx_hash
                    FROM batch_revisions
                    WHERE batch_id = ?
                    ORDER BY revision
                    """,
                    (batch_id,),
                ).fetchall()
            finally:
                revision_conn.close()

            if len(revisions) != local_rev or any(
                int(revision["revision"]) != index
                for index, revision in enumerate(revisions, start=1)
            ):
                raise ChainError("Local batch revision history is incomplete.")
            if batch["status"] == "SUBMITTED" and local_rev != 1:
                raise ChainError(
                    "Local batch is marked SUBMITTED despite having amendment revisions."
                )
            if batch["status"] == "AMENDED" and local_rev < 2:
                raise ChainError(
                    "Local batch is marked AMENDED without an amendment revision."
                )

            if revisions[-1]["marks_hash"].lower() != batch["marks_hash"].lower():
                raise ChainError(
                    "The current batch hash does not match its latest local revision."
                )

            reconcile = self.chain.reconcile(
                batch_id,
                local_rev,
                revisions[-1]["marks_hash"],
            )
            if reconcile.get("status") == "CHAIN_ERROR":
                raise ChainError(reconcile.get("reason", "Unable to inspect on-chain history."))

            chain_rev = int(reconcile.get("chain_revision", 0))
            if chain_rev > local_rev:
                raise ChainError(
                    f"On-chain history has {chain_rev} revisions but local history has {local_rev}."
                )

            chain_status = None
            revision_tx_hashes = [revision["chain_tx_hash"] for revision in revisions]
            if chain_rev:
                for index in range(chain_rev):
                    chain_revision = self.chain.get_revision_details(batch_id, index)
                    if chain_revision["marks_hash"].lower() != revisions[index]["marks_hash"].lower():
                        raise ChainError(
                            f"On-chain revision {index + 1} does not match local history."
                        )
                    expected_reason = (
                        "0x" + "00" * 32
                        if index == 0
                        else revisions[index]["reason_hash"]
                    )
                    if chain_revision["reason_hash"].lower() != expected_reason.lower():
                        raise ChainError(
                            f"On-chain reason for revision {index + 1} does not match local history."
                        )
                chain_status = self.chain.get_batch_status(batch_id)
                if chain_status == 0:
                    raise ChainError("On-chain batch status is missing despite its revision history.")
                if chain_rev > 1 and chain_status == 1:
                    raise ChainError(
                        "On-chain status is SUBMITTED despite having amendment revisions."
                    )

            tx_hash = batch["chain_tx_hash"]
            if chain_rev == 0:
                pending_revision = 1
                tx_hash = self.chain.submit_batch(
                    batch_id,
                    batch["course_id"],
                    batch["assessment_id"],
                    int(batch["student_count"]),
                    revisions[0]["marks_hash"],
                )
                self._checkpoint_recovered_revision(batch_id, 1, tx_hash)
                pending_revision = None
                chain_rev = 1
                chain_status = 1
                revision_tx_hashes[0] = tx_hash

            while chain_rev < local_rev:
                if chain_status != 2:
                    pending_revision = None
                    tx_hash = self.chain.verify_batch(batch_id)
                    self._checkpoint_recovered_action(
                        batch_id,
                        tx_hash,
                        "CHAIN_RECOVERY_VERIFICATION_CONFIRMED",
                        {"before_revision": chain_rev + 1},
                    )
                    chain_status = 2
                revision = revisions[chain_rev]
                pending_revision = chain_rev + 1
                tx_hash = self.chain.amend_batch(
                    batch_id,
                    revision["marks_hash"],
                    revision["reason_hash"],
                )
                self._checkpoint_recovered_revision(
                    batch_id,
                    chain_rev + 1,
                    tx_hash,
                )
                pending_revision = None
                revision_tx_hashes[chain_rev] = tx_hash
                chain_rev += 1
                chain_status = 3

            expected_status = {
                "SUBMITTED": 1,
                "VERIFIED": 2,
                "AMENDED": 3,
            }.get(batch["status"])
            if expected_status is None:
                raise ChainError(f"Unsupported local batch status: {batch['status']}.")
            if (
                batch["status"] == "VERIFIED"
                and chain_status in {1, 3}
            ):
                pending_revision = None
                tx_hash = self.chain.verify_batch(batch_id)
                self._checkpoint_recovered_action(
                    batch_id,
                    tx_hash,
                    "CHAIN_RECOVERY_VERIFICATION_CONFIRMED",
                    {"revision": local_rev},
                )
                chain_status = 2
            elif chain_status != expected_status:
                raise ChainError(
                    "Local workflow status "
                    f"{batch['status']} does not match on-chain status {chain_status}; "
                    "manual reconciliation is required."
                )

            previous_chain_revision = int(reconcile.get("chain_revision", 0))
            action = (
                "CHAIN_HISTORY_RECOVERED"
                if chain_rev > previous_chain_revision
                else "CHAIN_RECONCILED_CONFIRMED"
                if reconcile.get("match")
                else "CHAIN_SUBMISSION_RETRIED"
                if local_rev == 1
                else "CHAIN_AMENDMENT_RETRIED"
            )
            self._set_recovered_chain_state(
                batch_id,
                tx_hash,
                revision_tx_hashes,
                action,
                {
                    "local_revision": local_rev,
                    "previous_chain_revision": previous_chain_revision,
                },
            )
            return {
                "batch_id": batch_id,
                "chain_state": "CONFIRMED",
                "chain_tx_hash": tx_hash,
                "reconciled": True,
                "replayed_revisions": local_rev - previous_chain_revision,
            }
        except ChainError as exc:
            pending = isinstance(exc, ChainPendingError)
            self._set_chain_state(
                batch_id,
                pending_revision or int(batch["revision"]),
                "PENDING" if pending else "ERROR",
                getattr(exc, "tx_hash", None),
                "CHAIN_RETRY_PENDING" if pending else "CHAIN_RETRY_FAILED",
                {"error": str(exc)},
                update_revision=not (pending and pending_revision is None),
            )
            raise AppError("Chain retry failed: " + str(exc), 502)

    def recover_pending_batches(self) -> dict:
        """Scan for batches stuck in PENDING or ERROR state and attempt safe recovery."""
        if not self.chain.enabled:
            return {"recovered": 0, "errors": 0, "skipped": "chain_disabled"}

        conn = self.db.connect()
        try:
            pending = conn.execute(
                """
                SELECT b.id, b.revision, b.chain_state, b.submitted_by
                FROM batches b
                WHERE b.chain_state IN ('PENDING', 'ERROR')
                ORDER BY b.submitted_at ASC
                """
            ).fetchall()
        finally:
            conn.close()

        recovered = 0
        errors = 0
        for row in pending:
            try:
                self.retry_chain(user_id=row["submitted_by"], batch_id=row["id"])
                recovered += 1
                log.info("Successfully recovered batch %s on-chain.", row["id"])
            except Exception as exc:
                errors += 1
                log.warning("Could not recover batch %s: %s", row["id"], exc)

        return {"recovered": recovered, "errors": errors, "total": len(pending)}

    def admin_batches(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"admin"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    b.id,
                    b.status,
                    b.pipeline_stage,
                    b.student_count,
                    b.revision,
                    b.chain_state,
                    b.chain_tx_hash,
                    b.marks_hash,
                    b.submitted_at,
                    b.verified_at,
                    a.name AS assessment,
                    c.code AS course,
                    u.full_name AS lecturer_name
                FROM batches b
                JOIN assessments a ON a.id = b.assessment_id
                JOIN courses c ON c.id = a.course_id
                JOIN users u ON u.id = b.submitted_by
                ORDER BY b.submitted_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def admin_users(self, user_id: int) -> list[dict]:
        self.require_role(user_id, {"admin"})
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT id, username, full_name, role, active, reg_number,
                       access_until, created_at
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
        reg_number: str | None = None,
        access_until: str | None = None,
    ) -> dict:
        self.require_role(user_id, {"admin"})
        if not username.strip() or not full_name.strip():
            raise AppError("Username and full name are required.")
        if role not in {
            "student", "lecturer", "reviewer", "exam_office",
            "portal_operator", "admin",
        }:
            raise AppError("Invalid role.")
        if len(password) < 8:
            raise AppError("Password must be at least 8 characters.")
        access_until = self._validate_access_until(access_until)
        if role == "student" and access_until is None:
            raise AppError("Student accounts require a graduation or access end date.")

        # Non-admin users must change their temporary password on first login
        must_change = 1 if role != "admin" else 0

        from .db import hash_password

        salt, digest = hash_password(password)
        try:
            with self.db.transaction() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO users
                    (username, full_name, role, password_salt, password_hash,
                     must_change_password, reg_number, access_until, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        username.strip(), full_name.strip(), role,
                        salt, digest, must_change,
                        reg_number.strip() if reg_number else None,
                        access_until,
                        utc_now(),
                    ),
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

    @staticmethod
    def _validate_access_until(value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError as exc:
            raise AppError("Access end date must be a valid calendar date.") from exc

    def admin_update_user_access(
        self,
        actor_id: int,
        target_id: int,
        active: bool,
        access_until: str | None,
    ) -> dict:
        self.require_role(actor_id, {"admin"})
        if not isinstance(active, bool):
            raise AppError("Account status must be enabled or disabled.")
        end_date = self._validate_access_until(access_until)
        today = datetime.now(timezone.utc).date().isoformat()
        conn = self.db.connect()
        try:
            target = conn.execute(
                "SELECT id, role FROM users WHERE id = ?", (target_id,)
            ).fetchone()
            if not target:
                raise AppError("User not found.", 404)
            if target_id == actor_id and (
                not active or (end_date is not None and end_date <= today)
            ):
                raise AppError("You cannot disable or expire your own account.")
            if target["role"] == "admin":
                admins = conn.execute(
                    """
                    SELECT id, active, access_until FROM users WHERE role = 'admin'
                    """
                ).fetchall()
                projected = []
                for admin in admins:
                    projected.append(
                        {
                            "id": int(admin["id"]),
                            "active": bool(admin["active"]),
                            "access_until": admin["access_until"],
                        }
                    )
                updated_admin = next(
                    admin for admin in projected if admin["id"] == target_id
                )
                updated_admin["active"] = active
                updated_admin["access_until"] = end_date

                expiry_checks = {today}
                expiry_checks.update(
                    (date.fromisoformat(admin["access_until"]) + timedelta(days=1)).isoformat()
                    for admin in projected
                    if admin["active"] and admin["access_until"]
                )
                if any(
                    not any(
                        admin["active"]
                        and (
                            admin["access_until"] is None
                            or admin["access_until"] >= check_date
                        )
                        for admin in projected
                    )
                    for check_date in expiry_checks
                ):
                    raise AppError(
                        "This change would leave the institution without an "
                        "active, unexpired administrator."
                    )
        finally:
            conn.close()

        with self.db.transaction() as tx:
            tx.execute(
                "UPDATE users SET active = ?, access_until = ? WHERE id = ?",
                (int(active), end_date, target_id),
            )
            self._audit(
                tx,
                "USER",
                str(target_id),
                actor_id,
                "USER_ACCESS_UPDATED",
                {"active": active, "access_until": end_date},
            )
        return {"ok": True}

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
                    """
                    SELECT id FROM users
                    WHERE id = ? AND role = 'student' AND active = 1
                      AND (access_until IS NULL OR date(access_until) >= date('now'))
                    """,
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
        submission_deadline: str | None = None,
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
                INSERT INTO assessments (id, course_id, name, max_mark, submission_deadline, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (assessment_id, course_id, name.strip(), max_mark, submission_deadline or None, utc_now()),
            )
            self._audit(
                conn,
                "ASSESSMENT",
                assessment_id,
                user_id,
                "ASSESSMENT_CREATED",
                {"course_id": course_id, "max_mark": max_mark, "submission_deadline": submission_deadline},
            )
        return {"id": assessment_id}

    def admin_bulk_enroll_csv(
        self,
        user_id: int,
        course_id: str,
        csv_text: str,
        access_until: str | None = None,
    ) -> dict:
        """Bulk create + enroll students from a CSV.

        Expected CSV columns (any order, case-insensitive):
            reg_number – registration number (e.g. SCT/221/2023)
            full_name  – student's full name
            username   – login username (optional; defaults to reg_number with / replaced by -)

        Returns counts and one-time activation credentials for new accounts.
        """
        self.require_role(user_id, {"admin"})
        access_until = self._validate_access_until(access_until)
        reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
        headers = reader.fieldnames or []
        normalized_headers: dict[str, str] = {}
        for header in headers:
            normalized = header.strip().lower()
            if normalized in normalized_headers:
                raise AppError(f"CSV contains a duplicate column: {normalized}.")
            normalized_headers[normalized] = header

        reg_col = normalized_headers.get("reg_number") or normalized_headers.get("reg")
        name_col = normalized_headers.get("full_name") or normalized_headers.get("name")
        username_col = normalized_headers.get("username")

        if not reg_col or not name_col:
            raise AppError(
                "CSV must include reg_number (or reg) and full_name (or name) columns."
            )

        rows = [
            (row_number, row)
            for row_number, row in enumerate(reader, start=2)
            if row and any((value or "").strip() for value in row.values() if isinstance(value, str))
        ]
        if not rows:
            raise AppError("CSV is empty or has no data rows.")

        conn = self.db.connect()
        try:
            course = conn.execute(
                "SELECT id FROM courses WHERE id = ?", (course_id,)
            ).fetchone()
        finally:
            conn.close()
        if not course:
            raise AppError("Course not found.", 404)

        from .db import hash_password

        enrolled = 0
        created = 0
        skipped = 0
        errors: list[str] = []
        credentials: list[dict[str, str]] = []
        now = utc_now()
        seen_registrations: set[str] = set()
        seen_usernames: set[str] = set()

        for index, row in rows:
            if None in row:
                errors.append(f"Row {index}: too many CSV columns.")
                continue
            reg = (row.get(reg_col) or "").strip()
            full = (row.get(name_col) or "").strip()
            if not reg or not full:
                errors.append(f"Row {index}: reg_number and full_name are required.")
                continue
            uname = (
                (row.get(username_col) or "").strip()
                if username_col
                else reg.replace("/", "-").lower()
            )
            if not uname:
                errors.append(f"Row {index}: username cannot be empty.")
                continue
            normalized_reg = reg.casefold()
            normalized_username = uname.casefold()
            if normalized_reg in seen_registrations:
                errors.append(f"Row {index}: duplicate registration number {reg!r}.")
                continue
            if normalized_username in seen_usernames:
                errors.append(f"Row {index}: duplicate username {uname!r}.")
                continue
            seen_registrations.add(normalized_reg)
            seen_usernames.add(normalized_username)

            try:
                row_created = False
                row_enrolled = False
                activation_password: str | None = None
                with self.db.transaction() as tx:
                    matches = tx.execute(
                        """
                        SELECT id, username, reg_number, role, active, access_until
                        FROM users WHERE reg_number = ? OR username = ?
                        """,
                        (reg, uname),
                    ).fetchall()

                    if len(matches) > 1:
                        errors.append(
                            f"Row {index}: registration number and username match different accounts."
                        )
                        continue
                    existing = matches[0] if matches else None

                    if existing:
                        if (
                            existing["role"] != "student"
                            or not existing["active"]
                            or (
                               existing["access_until"]
                               and existing["access_until"] < datetime.now(timezone.utc).date().isoformat()
                            )
                        ):
                            errors.append(
                                f"Row {index}: the matched account is not an active student."
                            )
                            continue
                        if (
                            existing["username"].casefold() == normalized_username
                            and existing["reg_number"] != reg
                        ):
                            errors.append(
                                f"Row {index}: username {uname!r} belongs to a different registration."
                            )
                            continue
                        student_id = int(existing["id"])
                    else:
                        if access_until is None:
                            errors.append(
                                f"Row {index}: provide a graduation or access end date for new students."
                            )
                            continue
                        activation_password = secrets.token_urlsafe(24)
                        salt, digest = hash_password(activation_password)
                        cur = tx.execute(
                            """
                            INSERT INTO users
                            (username, full_name, role, password_salt, password_hash,
                             must_change_password, reg_number, access_until, created_at)
                            VALUES (?, ?, 'student', ?, ?, 1, ?, ?, ?)
                            """,
                            (uname, full, salt, digest, reg, access_until, now),
                        )
                        student_id = int(cur.lastrowid)
                        row_created = True

                    already = tx.execute(
                        "SELECT 1 FROM enrollments WHERE course_id = ? AND student_id = ?",
                        (course_id, student_id),
                    ).fetchone()

                    if already:
                        skipped += 1
                    else:
                        tx.execute(
                            "INSERT INTO enrollments (course_id, student_id, created_at) VALUES (?, ?, ?)",
                            (course_id, student_id, now),
                        )
                        row_enrolled = True
                created += int(row_created)
                enrolled += int(row_enrolled)
                if row_created and activation_password:
                    credentials.append(
                        {
                            "username": uname,
                            "full_name": full,
                            "activation_password": activation_password,
                        }
                    )
            except Exception as exc:
                if "UNIQUE" in str(exc).upper():
                    errors.append(f"Row {index}: username conflict for {uname!r}.")
                else:
                    errors.append(f"Row {index}: {exc}")

        if errors and enrolled == 0 and created == 0:
            raise AppError("Bulk enroll failed: " + "; ".join(errors[:5]))

        return {
            "enrolled": enrolled,
            "created": created,
            "skipped": skipped,
            "errors": errors,
            "credentials": credentials,
        }

    def change_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
    ) -> dict:
        """Allow any logged-in user to change their own password."""
        from .db import hash_password, verify_password

        if len(new_password) < 8:
            raise AppError("New password must be at least 8 characters.")

        conn = self.db.connect()
        try:
            user = conn.execute(
                "SELECT id, password_salt, password_hash FROM users WHERE id = ? AND active = 1",
                (user_id,),
            ).fetchone()
        finally:
            conn.close()

        if not user:
            raise AppError("User not found.", 404)
        if not verify_password(current_password, user["password_salt"], user["password_hash"]):
            raise AppError("Current password is incorrect.", 403)

        salt, digest = hash_password(new_password)
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE users
                SET password_salt = ?, password_hash = ?, must_change_password = 0
                WHERE id = ?
                """,
                (salt, digest, user_id),
            )
            self._audit(conn, "USER", str(user_id), user_id, "PASSWORD_CHANGED", {})
        return {"ok": True}
