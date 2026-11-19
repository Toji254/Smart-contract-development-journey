from __future__ import annotations

import os
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = PROJECT_ROOT / "scripts" / "backup.sh"
RESTORE_SCRIPT = PROJECT_ROOT / "scripts" / "restore.sh"


class PairedBackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db_path = root / "data" / "marktrail.db"
        self.evidence_dir = root / "data" / "private-evidence"
        self.backup_dir = root / "backups"
        self.db_path.parent.mkdir(parents=True)
        self.evidence_dir.mkdir(parents=True)
        self.backup_dir.mkdir(parents=True)
        self.env = {
            **os.environ,
            "MARKTRAIL_DB_PATH": str(self.db_path),
            "MARKTRAIL_EVIDENCE_DIR": str(self.evidence_dir),
            "MARKTRAIL_BACKUP_DIR": str(self.backup_dir),
            "MARKTRAIL_BACKUP_RETENTION_DAYS": "14",
        }
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE evidence_attachments (
                    id TEXT PRIMARY KEY,
                    storage_key TEXT NOT NULL UNIQUE,
                    byte_size INTEGER NOT NULL,
                    encryption_version INTEGER NOT NULL DEFAULT 0,
                    sha256 TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE TABLE backup_probe (value TEXT NOT NULL)")
            conn.execute("INSERT INTO backup_probe(value) VALUES ('snapshot-value')")

        self.file_id = "a" * 32
        self.document_path = self.evidence_dir / f"{self.file_id}.pdf"
        self.original_document = b"%PDF-1.7\nSynthetic private exam evidence.\n%%EOF"
        self.document_path.write_bytes(self.original_document)
        self.document_path.chmod(0o600)
        import hashlib
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO evidence_attachments
                    (id, storage_key, byte_size, encryption_version, sha256)
                VALUES (?, ?, ?, 0, ?)
                """,
                (
                    self.file_id,
                    self.document_path.name,
                    len(self.original_document),
                    hashlib.sha256(self.original_document).hexdigest(),
                ),
            )

    def tearDown(self):
        self.tmp.cleanup()

    def backup(self):
        completed = subprocess.run(
            ["bash", str(BACKUP_SCRIPT)],
            cwd=PROJECT_ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"backup failed:\n{completed.stdout}\n{completed.stderr}",
        )
        databases = list(self.backup_dir.glob("marktrail_backup_*.db.gz"))
        evidence = list(self.backup_dir.glob("marktrail_evidence_*.tar.gz"))
        self.assertEqual(len(databases), 1)
        self.assertEqual(len(evidence), 1)
        stamp = databases[0].name.removeprefix("marktrail_backup_").removesuffix(".db.gz")
        self.assertEqual(evidence[0].name, f"marktrail_evidence_{stamp}.tar.gz")
        return databases[0], evidence[0]

    def test_backup_refuses_database_snapshot_with_missing_referenced_file(self):
        self.document_path.unlink()
        completed = subprocess.run(
            ["bash", str(BACKUP_SCRIPT)],
            cwd=PROJECT_ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Referenced evidence file is missing", completed.stdout)
        self.assertEqual(list(self.backup_dir.glob("marktrail_backup_*.db.gz")), [])
        self.assertEqual(list(self.backup_dir.glob("marktrail_evidence_*.tar.gz")), [])

    def test_restore_refuses_archive_missing_a_database_referenced_file(self):
        database_backup, evidence_backup = self.backup()
        with tarfile.open(evidence_backup, "w:gz"):
            pass
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE backup_probe SET value = 'live-value-must-survive'")
        live_document = b"%PDF-1.7\nCurrent live file.\n%%EOF"
        self.document_path.write_bytes(live_document)
        restored = subprocess.run(
            ["bash", str(RESTORE_SCRIPT), str(database_backup), "--force"],
            cwd=PROJECT_ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(restored.returncode, 0)
        self.assertIn("Attachment file is missing from evidence archive", restored.stdout)
        with sqlite3.connect(self.db_path) as conn:
            value = conn.execute("SELECT value FROM backup_probe").fetchone()[0]
        self.assertEqual(value, "live-value-must-survive")
        self.assertEqual(self.document_path.read_bytes(), live_document)

    def test_backup_and_restore_recover_database_and_private_files_as_a_pair(self):
        database_backup, _evidence_backup = self.backup()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE backup_probe SET value = 'changed-after-backup'")
        self.document_path.write_bytes(b"%PDF-1.7\nChanged after backup.\n%%EOF")

        restored = subprocess.run(
            ["bash", str(RESTORE_SCRIPT), str(database_backup), "--force"],
            cwd=PROJECT_ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            restored.returncode,
            0,
            msg=f"restore failed:\n{restored.stdout}\n{restored.stderr}",
        )
        with sqlite3.connect(self.db_path) as conn:
            value = conn.execute("SELECT value FROM backup_probe").fetchone()[0]
        self.assertEqual(value, "snapshot-value")
        self.assertEqual(self.document_path.read_bytes(), self.original_document)
        self.assertEqual(self.document_path.stat().st_mode & 0o777, 0o600)

    def test_restore_refuses_attachment_database_when_evidence_sidecar_is_missing(self):
        database_backup, evidence_backup = self.backup()
        evidence_backup.unlink()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE backup_probe SET value = 'live-value-must-survive'")
        self.document_path.write_bytes(b"%PDF-1.7\nCurrent live file.\n%%EOF")

        restored = subprocess.run(
            ["bash", str(RESTORE_SCRIPT), str(database_backup), "--force"],
            cwd=PROJECT_ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(restored.returncode, 0)
        self.assertIn("matching evidence archive is missing", restored.stdout)
        with sqlite3.connect(self.db_path) as conn:
            value = conn.execute("SELECT value FROM backup_probe").fetchone()[0]
        self.assertEqual(value, "live-value-must-survive")
        self.assertEqual(
            self.document_path.read_bytes(),
            b"%PDF-1.7\nCurrent live file.\n%%EOF",
        )


if __name__ == "__main__":
    unittest.main()
