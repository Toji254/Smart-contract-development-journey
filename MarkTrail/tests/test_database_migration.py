from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db import Database, hash_password, utc_now


class DatabaseMigrationTests(unittest.TestCase):
    def test_existing_database_gains_workflow_roles_and_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing.db"
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('student','lecturer','reviewer','admin')),
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE courses (
                    id TEXT PRIMARY KEY,
                    code TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    lecturer_id INTEGER REFERENCES users(id),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE assessments (
                    id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    max_mark REAL NOT NULL CHECK (max_mark > 0),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE batches (
                    id TEXT PRIMARY KEY,
                    assessment_id TEXT NOT NULL UNIQUE REFERENCES assessments(id) ON DELETE CASCADE,
                    submitted_by INTEGER NOT NULL REFERENCES users(id),
                    status TEXT NOT NULL CHECK (status IN ('SUBMITTED','VERIFIED','AMENDED')),
                    student_count INTEGER NOT NULL,
                    marks_hash TEXT NOT NULL,
                    commitment_salt TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    chain_state TEXT NOT NULL CHECK (
                        chain_state IN ('PENDING','CONFIRMED','ERROR','LOCAL_ONLY')
                    ),
                    chain_tx_hash TEXT,
                    submitted_at TEXT NOT NULL,
                    verified_by INTEGER REFERENCES users(id),
                    verified_at TEXT
                );
                CREATE TABLE missing_reports (
                    id TEXT PRIMARY KEY,
                    assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
                    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    status TEXT NOT NULL CHECK (
                        status IN ('OPEN','PENDING_REVIEW','RESOLVED')
                    ),
                    opened_at TEXT NOT NULL,
                    resolution_type TEXT,
                    resolution_mark REAL,
                    lecturer_note TEXT,
                    resolved_by INTEGER REFERENCES users(id),
                    resolved_at TEXT
                );
                """
            )
            salt, password_hash = hash_password("student-pass")
            now = utc_now()
            conn.execute(
                """
                INSERT INTO users
                (id, username, full_name, role, password_salt, password_hash, created_at)
                VALUES (1, 'student', 'Test Student', 'student', ?, ?, ?)
                """,
                (salt, password_hash, now),
            )
            conn.execute(
                "INSERT INTO courses VALUES ('course-1', 'C1', 'Course', NULL, ?)",
                (now,),
            )
            conn.execute(
                "INSERT INTO assessments VALUES ('assessment-1', 'course-1', 'Exam', 20, ?)",
                (now,),
            )
            conn.execute(
                "INSERT INTO assessments VALUES ('assessment-2', 'course-1', 'CAT', 20, ?)",
                (now,),
            )
            conn.execute(
                """
                INSERT INTO batches
                (id, assessment_id, submitted_by, status, student_count, marks_hash,
                 commitment_salt, chain_state, submitted_at)
                VALUES ('batch-1', 'assessment-1', 1, 'VERIFIED', 1, 'hash', 'salt',
                        'LOCAL_ONLY', ?)
                """,
                (now,),
            )
            conn.execute(
                """
                INSERT INTO batches
                (id, assessment_id, submitted_by, status, student_count, marks_hash,
                 commitment_salt, chain_state, submitted_at)
                VALUES ('batch-2', 'assessment-2', 1, 'SUBMITTED', 1, 'hash', 'salt',
                        'LOCAL_ONLY', ?)
                """,
                (now,),
            )
            conn.execute(
                """
                INSERT INTO missing_reports (id, assessment_id, student_id, status, opened_at)
                VALUES ('report-1', 'assessment-1', 1, 'OPEN', ?)
                """,
                (now,),
            )
            conn.execute(
                """
                INSERT INTO missing_reports (id, assessment_id, student_id, status, opened_at)
                VALUES ('report-duplicate', 'assessment-1', 1, 'OPEN', ?)
                """,
                (now,),
            )
            conn.commit()
            conn.close()

            db = Database(path)
            db.init()
            with db.transaction() as migrated:
                office_salt, office_hash = hash_password("office-pass")
                migrated.execute(
                    """
                    INSERT INTO users
                    (username, full_name, role, password_salt, password_hash, created_at)
                    VALUES ('office', 'Office User', 'exam_office', ?, ?, ?)
                    """,
                    (office_salt, office_hash, now),
                )
                batch = migrated.execute(
                    "SELECT pipeline_stage FROM batches WHERE id = 'batch-1'"
                ).fetchone()
                submitted_batch = migrated.execute(
                    "SELECT pipeline_stage FROM batches WHERE id = 'batch-2'"
                ).fetchone()
                report = migrated.execute(
                    "SELECT status FROM missing_reports WHERE id = 'report-1'"
                ).fetchone()
                duplicate_report = migrated.execute(
                    """
                    SELECT status, lecturer_note FROM missing_reports
                    WHERE id = 'report-duplicate'
                    """
                ).fetchone()

            check = db.connect()
            try:
                violations = check.execute("PRAGMA foreign_key_check").fetchall()
            finally:
                check.close()

            self.assertEqual(batch["pipeline_stage"], "PUBLISHED")
            self.assertEqual(
                submitted_batch["pipeline_stage"],
                "DEPARTMENT_REVIEW",
            )
            self.assertEqual(report["status"], "OPEN")
            self.assertEqual(duplicate_report["status"], "REJECTED")
            self.assertIn("Automatically closed during migration", duplicate_report["lecturer_note"])
            self.assertEqual(violations, [])
            for status in ("OPEN", "PENDING_REVIEW"):
                with self.subTest(active_status=status):
                    with self.assertRaises(sqlite3.IntegrityError):
                        with db.transaction() as migrated:
                            migrated.execute(
                                """
                                INSERT INTO missing_reports
                                (id, assessment_id, student_id, status, opened_at)
                                VALUES (?, 'assessment-1', 1, ?, ?)
                                """,
                                (f"report-third-{status}", status, now),
                            )


if __name__ == "__main__":
    unittest.main()
