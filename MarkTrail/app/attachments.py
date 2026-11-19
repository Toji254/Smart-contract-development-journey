from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Callable

from .db import Database, utc_now
from .service import AppError, AppService

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class EvidenceAttachmentService:
    """Private, append-only evidence storage with fail-closed malware scanning."""

    def __init__(
        self,
        db: Database,
        app: AppService,
        storage_dir: str | Path | None = None,
        scanner: Callable[[Path], tuple[str, str] | str] | None = None,
    ) -> None:
        self.db = db
        self.app = app
        configured = storage_dir or os.getenv("MARKTRAIL_EVIDENCE_DIR")
        self.storage_dir = Path(configured) if configured else db.path.parent / "private-evidence"
        self.storage_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.storage_dir.chmod(0o700)
        except OSError:
            pass
        self.scanner = scanner
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        conn = self.db.connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence_attachments (
                    id TEXT PRIMARY KEY,
                    owner_type TEXT NOT NULL CHECK (owner_type IN ('CASE','SESSION','SCRIPT')),
                    case_id TEXT REFERENCES evidence_cases(id) ON DELETE RESTRICT,
                    session_id TEXT REFERENCES exam_sessions(id) ON DELETE RESTRICT,
                    script_id TEXT REFERENCES exam_scripts(id) ON DELETE RESTRICT,
                    uploaded_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                    original_name TEXT NOT NULL,
                    media_type TEXT NOT NULL CHECK (
                        media_type IN ('application/pdf','image/png','image/jpeg')
                    ),
                    byte_size INTEGER NOT NULL CHECK (byte_size > 0 AND byte_size <= 10485760),
                    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
                    storage_key TEXT NOT NULL UNIQUE,
                    scan_status TEXT NOT NULL CHECK (
                        scan_status IN ('CLEAN','QUARANTINED','INFECTED','SCAN_ERROR','CORRUPT')
                    ),
                    scan_engine TEXT NOT NULL,
                    scan_detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    scanned_at TEXT,
                    CHECK (
                        (owner_type = 'CASE' AND case_id IS NOT NULL AND session_id IS NULL AND script_id IS NULL)
                        OR
                        (owner_type = 'SESSION' AND case_id IS NULL AND session_id IS NOT NULL AND script_id IS NULL)
                        OR
                        (owner_type = 'SCRIPT' AND case_id IS NULL AND session_id IS NULL AND script_id IS NOT NULL)
                    ),
                    CHECK (storage_key NOT LIKE '%/%' AND storage_key NOT LIKE '%..%')
                );

                CREATE TABLE IF NOT EXISTS evidence_attachment_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attachment_id TEXT NOT NULL REFERENCES evidence_attachments(id) ON DELETE RESTRICT,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN (
                            'UPLOADED','SCANNED_CLEAN','QUARANTINED','INFECTED',
                            'SCAN_ERROR','SCAN_RETRIED','INTEGRITY_FAILED'
                        )
                    ),
                    actor_id INTEGER REFERENCES users(id) ON DELETE RESTRICT,
                    note TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_attachments_case
                    ON evidence_attachments(case_id, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_evidence_attachments_session
                    ON evidence_attachments(session_id, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_evidence_attachments_script
                    ON evidence_attachments(script_id, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_evidence_attachment_events
                    ON evidence_attachment_events(attachment_id, created_at, id);

                CREATE TRIGGER IF NOT EXISTS evidence_attachment_events_no_update
                BEFORE UPDATE ON evidence_attachment_events
                BEGIN
                    SELECT RAISE(ABORT, 'evidence attachment history is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS evidence_attachment_events_no_delete
                BEFORE DELETE ON evidence_attachment_events
                BEGIN
                    SELECT RAISE(ABORT, 'evidence attachment history is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS evidence_attachments_metadata_immutable
                BEFORE UPDATE ON evidence_attachments
                WHEN
                    OLD.id IS NOT NEW.id
                    OR OLD.owner_type IS NOT NEW.owner_type
                    OR OLD.case_id IS NOT NEW.case_id
                    OR OLD.session_id IS NOT NEW.session_id
                    OR OLD.script_id IS NOT NEW.script_id
                    OR OLD.uploaded_by IS NOT NEW.uploaded_by
                    OR OLD.original_name IS NOT NEW.original_name
                    OR OLD.media_type IS NOT NEW.media_type
                    OR OLD.byte_size IS NOT NEW.byte_size
                    OR OLD.sha256 IS NOT NEW.sha256
                    OR OLD.storage_key IS NOT NEW.storage_key
                    OR OLD.created_at IS NOT NEW.created_at
                BEGIN
                    SELECT RAISE(ABORT, 'evidence attachment metadata is immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS evidence_attachments_no_delete
                BEFORE DELETE ON evidence_attachments
                BEGIN
                    SELECT RAISE(ABORT, 'evidence attachments are retained; deletion is not permitted');
                END;
                """
            )
        finally:
            conn.close()

    @staticmethod
    def _event(conn, attachment_id, event_type, actor_id, note, metadata, now) -> None:
        conn.execute(
            """
            INSERT INTO evidence_attachment_events
                (attachment_id, event_type, actor_id, note, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (attachment_id, event_type, actor_id, str(note or "")[:1000],
             json.dumps(metadata, sort_keys=True), now),
        )

    def _authorize_owner(self, conn, user_id, owner_type, owner_id, *, for_upload=False):
        actor = conn.execute(
            "SELECT id, role, active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not actor or not actor["active"]:
            raise AppError("Your account is not active.", 403)
        role = actor["role"]

        if owner_type == "CASE":
            row = conn.execute(
                """
                SELECT ec.id, ec.student_id, ec.assigned_role, ec.assigned_user_id,
                       ec.status, ec.session_id
                FROM evidence_cases ec WHERE ec.id = ?
                """,
                (owner_id,),
            ).fetchone()
            if not row:
                raise AppError("Evidence case not found.", 404)
            allowed = (
                role == "admin"
                or (role == "student" and int(row["student_id"] or 0) == user_id)
                or (role == "reviewer" and row["assigned_role"] == "reviewer")
                or (role == "exam_office" and row["assigned_role"] == "exam_office")
                or (
                    role == "lecturer"
                    and row["assigned_role"] == "lecturer"
                    and int(row["assigned_user_id"] or 0) == user_id
                )
            )
            if not allowed:
                raise AppError("You do not have access to this evidence case.", 403)
            if for_upload and row["status"] in {"RESOLVED", "DISMISSED"}:
                raise AppError(
                    "This case has a final decision; new evidence must use the institution's appeal/review process.",
                    409,
                )
            return dict(row)

        if role not in {"admin", "reviewer", "exam_office", "lecturer"}:
            raise AppError("Only assigned academic staff may access session or script attachments.", 403)

        if owner_type == "SESSION":
            row = conn.execute(
                """
                SELECT s.id, c.lecturer_id
                FROM exam_sessions s
                JOIN assessments a ON a.id = s.assessment_id
                JOIN courses c ON c.id = a.course_id
                WHERE s.id = ?
                """,
                (owner_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT s.id AS session_id, c.lecturer_id
                FROM exam_scripts script
                JOIN exam_sessions s ON s.id = script.session_id
                JOIN assessments a ON a.id = s.assessment_id
                JOIN courses c ON c.id = a.course_id
                WHERE script.id = ?
                """,
                (owner_id,),
            ).fetchone()
        if not row:
            raise AppError("Examination evidence record not found.", 404)
        if role == "lecturer" and int(row["lecturer_id"] or 0) != user_id:
            raise AppError("You can only manage attachments for your assigned courses.", 403)
        return dict(row)

    @staticmethod
    def _safe_filename(value: str) -> tuple[str, str]:
        raw = str(value or "").replace("\\", "/")
        name = raw.rsplit("/", 1)[-1].strip()
        if (
            not name or len(name) > 128 or name in {".", ".."}
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
        ):
            raise AppError("Provide a valid file name of at most 128 characters.")
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED_TYPES:
            raise AppError("Only PDF, PNG and JPEG evidence files are accepted.")
        return name, suffix

    @staticmethod
    def _validate_content(suffix: str, payload: bytes) -> str:
        if not payload:
            raise AppError("The selected file is empty.")
        if suffix == ".pdf" and payload.startswith(b"%PDF-"):
            return "application/pdf"
        if suffix == ".png" and payload.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if suffix in {".jpg", ".jpeg"} and payload.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        raise AppError("The file extension does not match a supported PDF, PNG or JPEG file.")

    def _scan(self, path: Path) -> tuple[str, str, str]:
        if self.scanner is not None:
            try:
                result = self.scanner(path)
                status, detail = result if isinstance(result, tuple) else (str(result), "Configured scanner")
            except Exception as exc:
                return "SCAN_ERROR", "CUSTOM_SCANNER", str(exc)[:500]
            status = str(status).upper()
            if status not in {"CLEAN", "INFECTED", "QUARANTINED", "SCAN_ERROR"}:
                return "SCAN_ERROR", "CUSTOM_SCANNER", "Scanner returned an invalid status."
            return status, "CUSTOM_SCANNER", str(detail)[:500]

        executable = shutil.which("clamscan")
        if not executable:
            return "QUARANTINED", "NOT_CONFIGURED", "ClamAV is not installed; file is quarantined."
        try:
            result = subprocess.run(
                [executable, "--no-summary", "--infected", str(path)],
                capture_output=True, text=True, timeout=30, check=False,
            )
        except subprocess.TimeoutExpired:
            return "QUARANTINED", "CLAMAV", "ClamAV scan timed out; file remains quarantined."
        except OSError as exc:
            return "SCAN_ERROR", "CLAMAV", str(exc)[:500]
        detail = (result.stdout or result.stderr or "").strip()[:500]
        if result.returncode == 0:
            return "CLEAN", "CLAMAV", detail or "No malware detected."
        if result.returncode == 1:
            return "INFECTED", "CLAMAV", detail or "ClamAV detected an infected file."
        return "SCAN_ERROR", "CLAMAV", detail or f"ClamAV exited with status {result.returncode}."

    @staticmethod
    def _scan_event(status: str) -> str:
        return {
            "CLEAN": "SCANNED_CLEAN", "INFECTED": "INFECTED",
            "QUARANTINED": "QUARANTINED", "SCAN_ERROR": "SCAN_ERROR",
        }[status]

    @staticmethod
    def _public_row(row) -> dict:
        owner_id = row["case_id"] or row["session_id"] or row["script_id"]
        return {
            "id": row["id"], "owner_type": row["owner_type"], "owner_id": owner_id,
            "filename": row["original_name"], "media_type": row["media_type"],
            "byte_size": int(row["byte_size"]), "sha256": row["sha256"],
            "scan_status": row["scan_status"], "scan_engine": row["scan_engine"],
            "scan_detail": row["scan_detail"], "uploaded_by": row["uploaded_by"],
            "uploaded_by_name": row["uploaded_by_name"], "created_at": row["created_at"],
        }

    def upload(self, user_id, owner_type, owner_id, filename, content_base64) -> dict:
        owner_type = str(owner_type or "").upper()
        owner_id = str(owner_id or "").strip()
        if owner_type not in {"CASE", "SESSION", "SCRIPT"}:
            raise AppError("Attachment owner must be CASE, SESSION or SCRIPT.")
        if not owner_id or len(owner_id) > 128 or "/" in owner_id or "\\" in owner_id:
            raise AppError("A valid evidence record ID is required.")
        safe_name, suffix = self._safe_filename(filename)
        encoded = str(content_base64 or "")
        max_encoded = ((MAX_ATTACHMENT_BYTES + 2) // 3) * 4 + 8
        if not encoded or len(encoded) > max_encoded:
            raise AppError("The file is empty or exceeds the 10 MB upload limit.", 413)
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AppError("The evidence file must be valid base64 data.") from exc
        if len(payload) > MAX_ATTACHMENT_BYTES:
            raise AppError("Evidence files must be 10 MB or smaller.", 413)
        media_type = self._validate_content(suffix, payload)

        conn = self.db.connect()
        try:
            self._authorize_owner(conn, user_id, owner_type, owner_id, for_upload=True)
        finally:
            conn.close()

        attachment_id = uuid.uuid4().hex
        storage_key = attachment_id + suffix
        root = self.storage_dir.resolve()
        target = (root / storage_key).resolve()
        if target.parent != root:
            raise AppError("Invalid private storage key.", 400)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            target.unlink(missing_ok=True)
            raise

        scan_status, scan_engine, scan_detail = self._scan(target)
        now = utc_now()
        digest = hashlib.sha256(payload).hexdigest()
        try:
            with self.db.transaction() as conn:
                self._authorize_owner(conn, user_id, owner_type, owner_id, for_upload=True)
                conn.execute(
                    """
                    INSERT INTO evidence_attachments
                        (id, owner_type, case_id, session_id, script_id, uploaded_by,
                         original_name, media_type, byte_size, sha256, storage_key,
                         scan_status, scan_engine, scan_detail, created_at, scanned_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attachment_id, owner_type,
                        owner_id if owner_type == "CASE" else None,
                        owner_id if owner_type == "SESSION" else None,
                        owner_id if owner_type == "SCRIPT" else None,
                        user_id, safe_name, media_type, len(payload), digest, storage_key,
                        scan_status, scan_engine, scan_detail, now,
                        now if scan_status in {"CLEAN", "INFECTED", "SCAN_ERROR"} else None,
                    ),
                )
                metadata = {
                    "owner_type": owner_type, "owner_id": owner_id, "filename": safe_name,
                    "media_type": media_type, "byte_size": len(payload), "sha256": digest,
                    "scan_status": scan_status, "scan_engine": scan_engine,
                }
                self._event(conn, attachment_id, "UPLOADED", user_id,
                            "Evidence attachment uploaded.", metadata, now)
                self._event(conn, attachment_id, self._scan_event(scan_status), user_id,
                            scan_detail, {"scan_engine": scan_engine, "scan_status": scan_status}, now)
                self.app._audit(
                    conn, "EVIDENCE_ATTACHMENT", attachment_id, user_id,
                    "ATTACHMENT_UPLOADED", metadata,
                )
        except Exception:
            target.unlink(missing_ok=True)
            raise

        return {
            "id": attachment_id, "owner_type": owner_type, "owner_id": owner_id,
            "filename": safe_name, "media_type": media_type, "byte_size": len(payload),
            "sha256": digest, "scan_status": scan_status, "scan_engine": scan_engine,
            "scan_detail": scan_detail, "created_at": now, "downloadable": scan_status == "CLEAN",
        }

    def list_attachments(self, user_id, owner_type, owner_id=None) -> list[dict]:
        owner_type = str(owner_type or "").upper()
        if owner_type not in {"CASE", "SESSION", "SCRIPT"}:
            raise AppError("Attachment owner must be CASE, SESSION or SCRIPT.")
        conn = self.db.connect()
        try:
            if owner_type == "CASE" and not owner_id:
                actor = conn.execute(
                    "SELECT role FROM users WHERE id = ? AND active = 1", (user_id,)
                ).fetchone()
                if not actor:
                    raise AppError("Your account is not active.", 403)
                role = actor["role"]
                where, params = "", ()
                if role == "student":
                    where, params = "WHERE ec.student_id = ?", (user_id,)
                elif role == "reviewer":
                    where, params = "WHERE ec.assigned_role = 'reviewer'", ()
                elif role == "exam_office":
                    where, params = "WHERE ec.assigned_role = 'exam_office'", ()
                elif role == "lecturer":
                    where, params = "WHERE ec.assigned_role = 'lecturer' AND ec.assigned_user_id = ?", (user_id,)
                elif role != "admin":
                    raise AppError("You do not have access to evidence case attachments.", 403)
                query = """
                    SELECT a.*, u.full_name AS uploaded_by_name
                    FROM evidence_attachments a
                    JOIN evidence_cases ec ON ec.id = a.case_id
                    JOIN users u ON u.id = a.uploaded_by
                """
                query += (where + " AND a.owner_type = 'CASE'" if where else "WHERE a.owner_type = 'CASE'")
                query += " ORDER BY a.created_at, a.id"
                rows = conn.execute(query, params).fetchall()
            else:
                if not owner_id:
                    raise AppError("An evidence record ID is required for this attachment query.")
                self._authorize_owner(conn, user_id, owner_type, str(owner_id))
                column = {"CASE": "case_id", "SESSION": "session_id", "SCRIPT": "script_id"}[owner_type]
                rows = conn.execute(
                    f"""
                    SELECT a.*, u.full_name AS uploaded_by_name
                    FROM evidence_attachments a
                    JOIN users u ON u.id = a.uploaded_by
                    WHERE a.{column} = ?
                    ORDER BY a.created_at, a.id
                    """,
                    (owner_id,),
                ).fetchall()
            return [self._public_row(row) for row in rows]
        finally:
            conn.close()

    def read_attachment(self, user_id, attachment_id) -> dict:
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT a.*, u.full_name AS uploaded_by_name
                FROM evidence_attachments a
                JOIN users u ON u.id = a.uploaded_by
                WHERE a.id = ?
                """,
                (attachment_id,),
            ).fetchone()
            if not row:
                raise AppError("Evidence attachment not found.", 404)
            attachment = dict(row)
            owner_id = attachment["case_id"] or attachment["session_id"] or attachment["script_id"]
            self._authorize_owner(conn, user_id, attachment["owner_type"], owner_id)
        finally:
            conn.close()

        if attachment["scan_status"] != "CLEAN":
            raise AppError("This file is not available for download until a clean malware scan has completed.", 409)
        root = self.storage_dir.resolve()
        target = (root / attachment["storage_key"]).resolve()
        if target.parent != root or not target.is_file():
            raise AppError("The private evidence file is unavailable; contact an administrator.", 404)
        payload = target.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if len(payload) != attachment["byte_size"] or not hmac.compare_digest(digest, attachment["sha256"]):
            now = utc_now()
            with self.db.transaction() as conn:
                conn.execute(
                    """
                    UPDATE evidence_attachments
                    SET scan_status = 'CORRUPT', scan_engine = 'INTEGRITY_CHECK',
                        scan_detail = 'Stored file integrity check failed.', scanned_at = ?
                    WHERE id = ?
                    """,
                    (now, attachment_id),
                )
                self._event(
                    conn, attachment_id, "INTEGRITY_FAILED", user_id,
                    "Private evidence file failed its SHA-256 integrity check.",
                    {"expected_sha256": attachment["sha256"], "actual_sha256": digest}, now,
                )
                self.app._audit(
                    conn, "EVIDENCE_ATTACHMENT", attachment_id, user_id,
                    "ATTACHMENT_INTEGRITY_FAILED",
                    {"expected_sha256": attachment["sha256"], "actual_sha256": digest},
                )
            raise AppError("Evidence integrity check failed. The file has been quarantined.", 409)

        result = self._public_row(attachment)
        result["filename"] = attachment["original_name"]
        result["media_type"] = attachment["media_type"]
        result["content"] = payload
        return result

    def rescan(self, user_id, attachment_id) -> dict:
        self.app.require_role(user_id, {"admin"})
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM evidence_attachments WHERE id = ?", (attachment_id,)
            ).fetchone()
            if not row:
                raise AppError("Evidence attachment not found.", 404)
            attachment = dict(row)
        finally:
            conn.close()
        root = self.storage_dir.resolve()
        target = (root / attachment["storage_key"]).resolve()
        if target.parent != root or not target.is_file():
            raise AppError("The private evidence file is unavailable.", 404)
        status, engine, detail = self._scan(target)
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE evidence_attachments
                SET scan_status = ?, scan_engine = ?, scan_detail = ?, scanned_at = ?
                WHERE id = ?
                """,
                (status, engine, detail, now if status != "QUARANTINED" else None, attachment_id),
            )
            self._event(
                conn, attachment_id, "SCAN_RETRIED", user_id, detail,
                {"scan_status": status, "scan_engine": engine}, now,
            )
            if status != "CLEAN":
                self._event(
                    conn, attachment_id, self._scan_event(status), user_id, detail,
                    {"scan_status": status, "scan_engine": engine}, now,
                )
            self.app._audit(
                conn, "EVIDENCE_ATTACHMENT", attachment_id, user_id,
                "ATTACHMENT_RESCANNED", {"scan_status": status, "scan_engine": engine},
            )
        return {"id": attachment_id, "scan_status": status, "scan_engine": engine, "scan_detail": detail}
