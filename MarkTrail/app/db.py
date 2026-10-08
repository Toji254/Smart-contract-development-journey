from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "marktrail.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    _, candidate = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, digest_hex)


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        raw_path = path or os.getenv("MARKTRAIL_DB_PATH") or DEFAULT_DB_PATH
        self.path = Path(raw_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self, seed_demo: bool = False) -> None:
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('student','lecturer','reviewer','admin')),
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS courses (
                    id TEXT PRIMARY KEY,
                    code TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    lecturer_id INTEGER REFERENCES users(id),
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS enrollments (
                    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (course_id, student_id)
                );

                CREATE TABLE IF NOT EXISTS assessments (
                    id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    max_mark REAL NOT NULL CHECK (max_mark > 0),
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS batches (
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

                CREATE TABLE IF NOT EXISTS batch_revisions (
                    batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL,
                    marks_hash TEXT NOT NULL,
                    reason_hash TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (kind IN ('SUBMISSION','AMENDMENT')),
                    actor_id INTEGER NOT NULL REFERENCES users(id),
                    chain_state TEXT NOT NULL,
                    chain_tx_hash TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (batch_id, revision)
                );

                CREATE TABLE IF NOT EXISTS assessment_marks (
                    assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
                    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    candidate_mark REAL,
                    candidate_status TEXT NOT NULL CHECK (
                        candidate_status IN ('RECORDED','MISSING','NO_MARK')
                    ),
                    published_mark REAL,
                    published_status TEXT NOT NULL CHECK (
                        published_status IN ('RECORDED','MISSING','NO_MARK')
                    ),
                    batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (assessment_id, student_id)
                );

                CREATE TABLE IF NOT EXISTS mark_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
                    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
                    old_mark REAL,
                    new_mark REAL,
                    old_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    actor_id INTEGER NOT NULL REFERENCES users(id),
                    action TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS missing_reports (
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

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    actor_id INTEGER REFERENCES users(id),
                    action TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    chain_tx_hash TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_assessment_marks_student
                    ON assessment_marks(student_id);

                CREATE INDEX IF NOT EXISTS idx_reports_assessment_status
                    ON missing_reports(assessment_id, status);

                CREATE INDEX IF NOT EXISTS idx_audit_entity
                    ON audit_events(entity_type, entity_id, created_at);
                """
            )

        if seed_demo:
            self.seed_demo()

    def seed_demo(self) -> None:
        with self.transaction() as conn:
            existing = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
            if existing:
                return

            def add_user(username: str, full_name: str, role: str, password: str) -> int:
                salt, digest = hash_password(password)
                cur = conn.execute(
                    """
                    INSERT INTO users
                    (username, full_name, role, password_salt, password_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (username, full_name, role, salt, digest, utc_now()),
                )
                return int(cur.lastrowid)

            admin_id = add_user("admin", "MarkTrail Admin", "admin", "admin123")
            lecturer_id = add_user("lecturer", "Dr. Alex Njoroge", "lecturer", "lecturer123")
            reviewer_id = add_user("reviewer", "Prof. Grace Wambui", "reviewer", "reviewer123")
            student_id = add_user("student", "Jane Doe", "student", "student123")
            add_user("student2", "Brian Otieno", "student", "student123")

            course_id = "course-csc201"
            conn.execute(
                """
                INSERT INTO courses (id, code, title, lecturer_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (course_id, "CSC 201", "Smart Contract Fundamentals", lecturer_id, utc_now()),
            )

            conn.execute(
                """
                INSERT INTO enrollments (course_id, student_id, created_at)
                VALUES (?, ?, ?), (?, ?, ?)
                """,
                (course_id, student_id, utc_now(), course_id, student_id + 1, utc_now()),
            )

            assessments = [
                ("assessment-cat1", "CAT 1", 20),
                ("assessment-cat2", "CAT 2", 20),
                ("assessment-exam", "Final Exam", 60),
            ]

            for assessment_id, name, max_mark in assessments:
                conn.execute(
                    """
                    INSERT INTO assessments (id, course_id, name, max_mark, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (assessment_id, course_id, name, max_mark, utc_now()),
                )

            self._seed_verified_batch(
                conn,
                "assessment-cat1",
                lecturer_id,
                {
                    student_id: (18.0, "RECORDED"),
                    student_id + 1: (15.0, "RECORDED"),
                },
                reason="demo initial submission",
            )

            self._seed_verified_batch(
                conn,
                "assessment-cat2",
                lecturer_id,
                {
                    student_id: (None, "MISSING"),
                    student_id + 1: (16.0, "RECORDED"),
                },
                reason="demo initial submission with one missing mark",
            )

            self._seed_verified_batch(
                conn,
                "assessment-exam",
                lecturer_id,
                {
                    student_id: (47.0, "RECORDED"),
                    student_id + 1: (41.0, "RECORDED"),
                },
                reason="demo initial submission",
            )

            conn.execute(
                """
                INSERT INTO audit_events
                (entity_type, entity_id, actor_id, action, metadata_json, created_at)
                VALUES ('SYSTEM', 'seed', ?, 'DEMO_DATA_SEEDED', ?, ?)
                """,
                (
                    admin_id,
                    json.dumps({"course": "CSC 201"}),
                    utc_now(),
                ),
            )

    def _seed_verified_batch(
        self,
        conn: sqlite3.Connection,
        assessment_id: str,
        lecturer_id: int,
        marks: dict[int, tuple[float | None, str]],
        reason: str,
    ) -> None:
        batch_id = "0x" + hashlib.sha256(
            f"seed:{assessment_id}".encode("utf-8")
        ).hexdigest()
        salt = secrets.token_hex(16)

        rows = []
        for sid in sorted(marks):
            mark, status = marks[sid]
            rows.append({"student_id": sid, "mark": mark, "status": status})

        canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
        marks_hash = "0x" + hashlib.sha256(
            (salt + "|" + canonical).encode("utf-8")
        ).hexdigest()

        now = utc_now()
        conn.execute(
            """
            INSERT INTO batches
            (id, assessment_id, submitted_by, status, student_count, marks_hash,
             commitment_salt, revision, chain_state, submitted_at, verified_by, verified_at)
            VALUES (?, ?, ?, 'VERIFIED', ?, ?, ?, 1, 'LOCAL_ONLY', ?, ?, ?)
            """,
            (
                batch_id,
                assessment_id,
                lecturer_id,
                len(rows),
                marks_hash,
                salt,
                now,
                lecturer_id,
                now,
            ),
        )

        reason_hash = "0x" + hashlib.sha256(reason.encode("utf-8")).hexdigest()
        conn.execute(
            """
            INSERT INTO batch_revisions
            (batch_id, revision, marks_hash, reason_hash, kind, actor_id,
             chain_state, created_at)
            VALUES (?, 1, ?, ?, 'SUBMISSION', ?, 'LOCAL_ONLY', ?)
            """,
            (batch_id, marks_hash, reason_hash, lecturer_id, now),
        )

        for sid, (mark, status) in marks.items():
            conn.execute(
                """
                INSERT INTO assessment_marks
                (assessment_id, student_id, candidate_mark, candidate_status,
                 published_mark, published_status, batch_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (assessment_id, sid, mark, status, mark, status, batch_id, now),
            )

        conn.execute(
            """
            INSERT INTO audit_events
            (entity_type, entity_id, actor_id, action, metadata_json, created_at)
            VALUES ('BATCH', ?, ?, 'BATCH_VERIFIED', ?, ?)
            """,
            (
                batch_id,
                lecturer_id,
                json.dumps({"reason": reason, "chain_state": "LOCAL_ONLY"}),
                now,
            ),
        )

    def cleanup_sessions(self) -> None:
        with self.transaction() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE expires_at < ?",
                (utc_now(),),
            )

    def create_session(self, user_id: int, hours: int = 12) -> str:
        session_id = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=hours)
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)",
                (session_id, user_id, expires.isoformat()),
            )
        return session_id

    def get_session_user(self, session_id: str) -> sqlite3.Row | None:
        self.cleanup_sessions()
        conn = self.connect()
        try:
            return conn.execute(
                """
                SELECT u.*
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.id = ? AND s.expires_at >= ? AND u.active = 1
                """,
                (session_id, utc_now()),
            ).fetchone()
        finally:
            conn.close()

    def delete_session(self, session_id: str) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
