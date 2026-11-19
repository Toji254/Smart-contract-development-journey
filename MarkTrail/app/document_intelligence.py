from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .db import utc_now
from .service import AppError

MAX_PDF_PAGES = 5
MAX_IMAGE_PIXELS = 40_000_000
MAX_TEXT_CHARS = 24_000
PDF_RENDER_TIMEOUT_SECONDS = 20
PDF_INFO_TIMEOUT_SECONDS = 6
OCR_PAGE_TIMEOUT_SECONDS = 10
OCR_ROLES = {"admin", "reviewer", "exam_office", "lecturer"}
EXTRACTION_MAGIC = b"MT-DOC-INTEL-ENC1"
EXTRACTION_VERSION = 1

RegistrationPattern = re.compile(
    r"\b[A-Z][A-Z0-9]{1,9}/[A-Z0-9]{2,10}/[0-9]{2,4}\b",
    re.IGNORECASE,
)
DatePattern = re.compile(
    r"\b(?:[0-3]?\d[/-][01]?\d[/-](?:19|20)?\d{2}|20\d{2}-[01]\d-[0-3]\d)\b"
)
ControlCharacters = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class EvidenceDocumentIntelligenceService:
    """Optional, local OCR that produces encrypted, human-review-only suggestions."""

    def __init__(
        self,
        db,
        app,
        attachments,
        ocr_runner: Callable[[bytes, str], dict] | None = None,
    ) -> None:
        self.db = db
        self.app = app
        self.attachments = attachments
        self.ocr_runner = ocr_runner or self._run_local_ocr
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.db.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence_document_extractions (
                    id TEXT PRIMARY KEY,
                    attachment_id TEXT NOT NULL
                        REFERENCES evidence_attachments(id) ON DELETE RESTRICT,
                    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
                    engine TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('COMPLETE','PARTIAL','EMPTY','UNAVAILABLE','FAILED')
                    ),
                    page_count INTEGER NOT NULL DEFAULT 0 CHECK (page_count >= 0),
                    text_length INTEGER NOT NULL DEFAULT 0 CHECK (text_length >= 0 AND text_length <= 24000),
                    encrypted_result BLOB NOT NULL,
                    encryption_version INTEGER NOT NULL CHECK (encryption_version = 1),
                    encryption_key_id TEXT NOT NULL,
                    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_document_extractions_latest
                    ON evidence_document_extractions(attachment_id, created_at DESC, id);

                CREATE TRIGGER IF NOT EXISTS evidence_document_extractions_no_update
                BEFORE UPDATE ON evidence_document_extractions
                BEGIN
                    SELECT RAISE(ABORT, 'document extraction history is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS evidence_document_extractions_no_delete
                BEFORE DELETE ON evidence_document_extractions
                BEGIN
                    SELECT RAISE(ABORT, 'document extraction history is append-only');
                END;
                """
            )

    @staticmethod
    def _normalise_text(value: str) -> str:
        value = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
        value = ControlCharacters.sub("", value)
        value = "\n".join(line.rstrip() for line in value.split("\n"))
        return value.strip()[:MAX_TEXT_CHARS]

    @staticmethod
    def _classify(text: str) -> dict:
        upper = text.upper()
        signals = {
            "ATTENDANCE_REGISTER": (
                "ATTENDANCE", "REGISTER", "PRESENT", "ABSENT", "SIGNATURE"
            ),
            "EXAMINATION_CARD": (
                "EXAMINATION CARD", "EXAM CARD", "STUDENT ID",
                "COURSE UNIT", "INDEX NUMBER"
            ),
            "SCRIPT_RECEIPT": (
                "SCRIPT RECEIPT", "ANSWER BOOKLET", "SCRIPT REFERENCE",
                "RECEIVED BY", "BOOKLET"
            ),
        }
        scores = {
            label: sum(1 for phrase in phrases if phrase in upper)
            for label, phrases in signals.items()
        }
        highest = max(scores.values(), default=0)
        winners = [label for label, score in scores.items() if score == highest and score > 0]
        if not winners:
            suggested_type = "UNKNOWN"
        elif len(winners) > 1:
            suggested_type = "AMBIGUOUS"
        else:
            suggested_type = winners[0]

        registration_numbers = sorted({
            value.upper() for value in RegistrationPattern.findall(upper)
        })[:50]
        dates = sorted(set(DatePattern.findall(text)))[:30]
        return {
            "suggested_document_type": suggested_type,
            "classification_basis": "Keyword heuristic over OCR text; not a verified classification.",
            "registration_number_candidates": registration_numbers,
            "date_candidates": dates,
            "present_word_occurrences": len(re.findall(r"\bPRESENT\b", upper)),
            "absent_word_occurrences": len(re.findall(r"\bABSENT\b", upper)),
            "suggested_next_step": (
                "Compare candidate references and dates with the locked assessment roster "
                "and inspect the original document."
            ),
        }

    @staticmethod
    def _image_dimensions(payload: bytes, media_type: str) -> tuple[int, int]:
        if media_type == "image/png":
            if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
                raise ValueError("The PNG image header is invalid.")
            width = int.from_bytes(payload[16:20], "big")
            height = int.from_bytes(payload[20:24], "big")
            return width, height

        if media_type != "image/jpeg" or not payload.startswith(b"\xff\xd8"):
            raise ValueError("The image format is not supported by local OCR.")
        index = 2
        frame_markers = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }
        while index + 4 <= len(payload):
            if payload[index] != 0xFF:
                index += 1
                continue
            while index < len(payload) and payload[index] == 0xFF:
                index += 1
            if index >= len(payload):
                break
            marker = payload[index]
            index += 1
            if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
                continue
            if index + 2 > len(payload):
                break
            segment_length = int.from_bytes(payload[index:index + 2], "big")
            if segment_length < 2 or index + segment_length > len(payload):
                break
            if marker in frame_markers and segment_length >= 7:
                height = int.from_bytes(payload[index + 3:index + 5], "big")
                width = int.from_bytes(payload[index + 5:index + 7], "big")
                return width, height
            index += segment_length
        raise ValueError("The JPEG dimensions could not be read safely.")

    @staticmethod
    def _local_environment() -> dict:
        env = os.environ.copy()
        env["OMP_THREAD_LIMIT"] = "1"
        env["LC_ALL"] = "C"
        return env

    def _run_local_ocr(self, payload: bytes, media_type: str) -> dict:
        tesseract = shutil.which("tesseract")
        if not tesseract:
            return {
                "status": "UNAVAILABLE",
                "engine": "LOCAL_TESSERACT",
                "page_count": 0,
                "text": "",
                "warning": "Tesseract is not installed on the MarkTrail host.",
            }

        env = self._local_environment()
        with tempfile.TemporaryDirectory(prefix="marktrail-document-") as temporary:
            workdir = Path(temporary)
            workdir.chmod(0o700)
            if media_type in {"image/png", "image/jpeg"}:
                width, height = self._image_dimensions(payload, media_type)
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise ValueError("The image dimensions exceed the local OCR safety limit.")
                source = workdir / ("source.png" if media_type == "image/png" else "source.jpg")
                source.write_bytes(payload)
                source.chmod(0o600)
                command = [tesseract, str(source), "stdout", "-l", "eng", "--psm", "6"]
                result = subprocess.run(
                    command, capture_output=True, text=True, timeout=OCR_PAGE_TIMEOUT_SECONDS,
                    check=False, env=env,
                )
                if result.returncode != 0:
                    raise RuntimeError((result.stderr or "Tesseract could not process the image.")[:500])
                text = self._normalise_text(result.stdout)
                return {
                    "status": "COMPLETE" if text else "EMPTY",
                    "engine": "TESSERACT_LOCAL",
                    "page_count": 1,
                    "text": text,
                    "warning": "" if text else "No readable text was detected in this image.",
                }

            if media_type != "application/pdf":
                raise ValueError("Only PDF, PNG and JPEG documents are supported.")
            pdfinfo = shutil.which("pdfinfo")
            pdftoppm = shutil.which("pdftoppm")
            if not pdfinfo or not pdftoppm:
                return {
                    "status": "UNAVAILABLE",
                    "engine": "TESSERACT_LOCAL",
                    "page_count": 0,
                    "text": "",
                    "warning": "PDF OCR requires Poppler utilities (pdfinfo and pdftoppm) as well as Tesseract.",
                }

            source = workdir / "source.pdf"
            source.write_bytes(payload)
            source.chmod(0o600)
            info = subprocess.run(
                [pdfinfo, str(source)], capture_output=True, text=True,
                timeout=PDF_INFO_TIMEOUT_SECONDS, check=False, env=env,
            )
            if info.returncode != 0:
                raise RuntimeError((info.stderr or "Poppler could not inspect this PDF.")[:500])
            page_match = re.search(r"^Pages:\s*(\d+)\s*$", info.stdout, re.MULTILINE)
            if not page_match:
                raise ValueError("The PDF page count could not be determined.")
            total_pages = int(page_match.group(1))
            if total_pages < 1:
                raise ValueError("The PDF does not contain any pages.")

            pages_to_process = min(total_pages, MAX_PDF_PAGES)
            prefix = workdir / "page"
            render = subprocess.run(
                [
                    pdftoppm, "-f", "1", "-l", str(pages_to_process),
                    "-r", "120", "-scale-to", "1600", "-png",
                    str(source), str(prefix),
                ],
                capture_output=True, text=True, timeout=PDF_RENDER_TIMEOUT_SECONDS,
                check=False, env=env,
            )
            if render.returncode != 0:
                raise RuntimeError((render.stderr or "Poppler could not render this PDF.")[:500])

            page_files = sorted(workdir.glob("page-*.png"))
            if not page_files:
                raise RuntimeError("Poppler did not produce any page images.")
            page_texts = []
            for page in page_files[:MAX_PDF_PAGES]:
                result = subprocess.run(
                    [tesseract, str(page), "stdout", "-l", "eng", "--psm", "6"],
                    capture_output=True, text=True, timeout=OCR_PAGE_TIMEOUT_SECONDS,
                    check=False, env=env,
                )
                if result.returncode != 0:
                    raise RuntimeError((result.stderr or f"Tesseract failed on {page.name}.")[:500])
                page_texts.append(self._normalise_text(result.stdout))
                if sum(len(item) for item in page_texts) >= MAX_TEXT_CHARS:
                    break

            text = self._normalise_text("\n\n".join(page_texts))
            partial = total_pages > pages_to_process
            warning = (
                f"Only the first {pages_to_process} of {total_pages} PDF pages were processed."
                if partial else ""
            )
            if not text:
                warning = warning or "No readable text was detected in the processed PDF pages."
            status = "PARTIAL" if partial and text else "COMPLETE" if text else "EMPTY"
            return {
                "status": status,
                "engine": "TESSERACT_LOCAL+POPPLER",
                "page_count": len(page_files[:MAX_PDF_PAGES]),
                "text": text,
                "warning": warning,
            }

    def _aad(self, attachment_id: str, extraction_id: str, source_sha256: str) -> bytes:
        return (
            f"MarkTrail document intelligence v{EXTRACTION_VERSION}|"
            f"{attachment_id}|{extraction_id}|{source_sha256}"
        ).encode("utf-8")

    def _encrypt_result(
        self, attachment_id: str, extraction_id: str, source_sha256: str, payload: bytes
    ) -> bytes:
        key = self.attachments.encryption_key
        if not key:
            raise AppError("Evidence encryption is not configured; document analysis is unavailable.", 503)
        nonce = os.urandom(12)
        encrypted = AESGCM(key).encrypt(
            nonce, payload, self._aad(attachment_id, extraction_id, source_sha256)
        )
        return EXTRACTION_MAGIC + nonce + encrypted

    def _decrypt_result(self, row) -> dict:
        key = self.attachments.encryption_key
        if not key:
            raise AppError("The evidence encryption key is not configured on this server.", 503)
        expected_key_id = self.attachments.encryption_key_id
        if row["encryption_key_id"] != expected_key_id:
            raise AppError("The configured evidence encryption key does not match this extraction.", 503)
        stored = bytes(row["encrypted_result"])
        if not stored.startswith(EXTRACTION_MAGIC):
            raise AppError("The saved document analysis failed its encryption envelope check.", 409)
        offset = len(EXTRACTION_MAGIC)
        try:
            plaintext = AESGCM(key).decrypt(
                stored[offset:offset + 12],
                stored[offset + 12:],
                self._aad(row["attachment_id"], row["id"], row["source_sha256"]),
            )
        except InvalidTag as exc:
            raise AppError("The saved document analysis failed its integrity check.", 409) from exc
        try:
            result = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AppError("The saved document analysis is unreadable.", 409) from exc
        result["cached"] = True
        result["created_at"] = row["created_at"]
        return result

    def analyze(self, user_id: int, attachment_id: str) -> dict:
        self.app.require_role(user_id, OCR_ROLES)
        # This performs owner re-authorization, clean-scan enforcement, AES-GCM
        # authentication and source SHA-256 verification before OCR sees bytes.
        attachment = self.attachments.read_attachment(user_id, attachment_id)
        source_sha256 = attachment["sha256"]

        conn = self.db.connect()
        try:
            latest = conn.execute(
                """
                SELECT * FROM evidence_document_extractions
                WHERE attachment_id = ? ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (attachment_id,),
            ).fetchone()
            if latest and latest["source_sha256"] == source_sha256 and latest["status"] in {
                "COMPLETE", "PARTIAL", "EMPTY"
            }:
                return self._decrypt_result(latest)
        finally:
            conn.close()

        try:
            run = self.ocr_runner(attachment["content"], attachment["media_type"])
            status = str(run.get("status", "FAILED")).upper()
            if status not in {"COMPLETE", "PARTIAL", "EMPTY", "UNAVAILABLE", "FAILED"}:
                status = "FAILED"
            engine = str(run.get("engine") or "LOCAL_OCR")[:80]
            page_count = max(0, min(int(run.get("page_count") or 0), MAX_PDF_PAGES))
            text = self._normalise_text(run.get("text", ""))
            warning = str(run.get("warning") or "")[:1000]
        except subprocess.TimeoutExpired:
            status, engine, page_count, text = "FAILED", "LOCAL_OCR", 0, ""
            warning = "Local OCR exceeded its processing time limit."
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            status, engine, page_count, text = "FAILED", "LOCAL_OCR", 0, ""
            warning = str(exc)[:1000]

        extraction_id = uuid.uuid4().hex
        result = {
            "id": extraction_id,
            "attachment_id": attachment_id,
            "source_sha256": source_sha256,
            "status": status,
            "engine": engine,
            "page_count": page_count,
            "extracted_character_count": len(text),
            "text": text,
            "suggestions": self._classify(text),
            "warning": warning,
            "review_required": True,
            "decision_ready": False,
            "decision_authority": "HUMAN_ONLY",
            "cached": False,
        }
        encoded = json.dumps(result, sort_keys=True, ensure_ascii=False).encode("utf-8")
        encrypted = self._encrypt_result(attachment_id, extraction_id, source_sha256, encoded)
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO evidence_document_extractions
                    (id, attachment_id, source_sha256, engine, status, page_count,
                     text_length, encrypted_result, encryption_version,
                     encryption_key_id, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    extraction_id, attachment_id, source_sha256, engine, status,
                    page_count, len(text), encrypted, EXTRACTION_VERSION,
                    self.attachments.encryption_key_id, user_id, now,
                ),
            )
            self.app._audit(
                conn,
                "EVIDENCE_ATTACHMENT",
                attachment_id,
                user_id,
                "EVIDENCE_DOCUMENT_ANALYZED",
                {
                    "extraction_id": extraction_id,
                    "status": status,
                    "engine": engine,
                    "page_count": page_count,
                    "text_length": len(text),
                    "suggested_document_type": result["suggestions"]["suggested_document_type"],
                    "source_sha256": source_sha256,
                    "decision_authority": "HUMAN_ONLY",
                },
            )
        result["created_at"] = now
        return result
