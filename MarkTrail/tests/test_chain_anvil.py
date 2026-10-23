from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from app.chain import ChainClient, ChainConfig
from app.db import Database, hash_password, utc_now
from app.service import AppService


class AnvilIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Verify anvil and cast and forge exist
        for cmd in ["anvil", "cast", "forge"]:
            if not shutil.which(cmd):
                raise unittest.SkipTest(f"Command '{cmd}' not found in PATH")

        cls.port = 8548
        cls.rpc_url = f"http://127.0.0.1:{cls.port}"
        # Start anvil on dedicated test port
        cls.anvil_proc = subprocess.Popen(
            ["anvil", "--port", str(cls.port), "--silent"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for anvil to be ready
        ready = False
        for _ in range(30):
            try:
                res = subprocess.run(
                    ["cast", "block-number", "--rpc-url", cls.rpc_url],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if res.returncode == 0:
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.2)

        if not ready:
            cls.anvil_proc.terminate()
            raise unittest.SkipTest("Could not connect to ephemeral Anvil instance")

        # Deploy MarkTrailAudit contract using Anvil default private key #0
        cls.private_key = (
            "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        )
        cls.account = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

        deploy_cmd = [
            "forge",
            "create",
            "src/MarkTrailAudit.sol:MarkTrailAudit",
            "--rpc-url",
            cls.rpc_url,
            "--private-key",
            cls.private_key,
            "--broadcast",
        ]
        deploy_res = subprocess.run(
            deploy_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        match = None
        for line in deploy_res.stdout.splitlines():
            if "Deployed to:" in line:
                match = line.split("Deployed to:")[1].strip()
                break

        if not match:
            cls.anvil_proc.terminate()
            raise RuntimeError(
                f"Could not parse deployed contract address: {deploy_res.stdout}"
            )

        cls.contract = match

        # Authorize account as both lecturer and reviewer on the contract
        for role_func in ["setLecturer(address,bool)", "setReviewer(address,bool)"]:
            subprocess.run(
                [
                    "cast",
                    "send",
                    cls.contract,
                    role_func,
                    cls.account,
                    "true",
                    "--rpc-url",
                    cls.rpc_url,
                    "--private-key",
                    cls.private_key,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "anvil_proc"):
            cls.anvil_proc.terminate()
            try:
                cls.anvil_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.anvil_proc.kill()

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db = Database(self.db_path)
        self.db.init(seed_demo=False)

        # Set up chain client pointing to Anvil
        self.chain = ChainClient()
        self.chain.config = ChainConfig(
            mode="cast",
            rpc_url=self.rpc_url,
            contract=self.contract,
            private_key=self.private_key,
        )
        self.service = AppService(self.db, chain=self.chain)

        # Seed standard academic structure with reg numbers
        self._seed_data()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _seed_data(self):
        salt, p_hash = hash_password("pass12345678")
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO users (id, username, full_name, role, password_salt, password_hash, created_at)
                VALUES (1, 'lecturer1', 'Lecturer One', 'lecturer', ?, ?, ?),
                       (2, 'reviewer1', 'Reviewer One', 'reviewer', ?, ?, ?),
                       (3, 'office1', 'Office One', 'exam_office', ?, ?, ?),
                       (4, 'portal1', 'Portal One', 'portal_operator', ?, ?, ?),
                       (5, 'admin1', 'Admin One', 'admin', ?, ?, ?),
                       (6, 'student1', 'Alice Wanjiku', 'student', ?, ?, ?),
                       (7, 'student2', 'Bob Kiprono', 'student', ?, ?, ?),
                       (8, 'student3', 'Carol Muthoni', 'student', ?, ?, ?)
                """,
                (
                    salt, p_hash, now,
                    salt, p_hash, now,
                    salt, p_hash, now,
                    salt, p_hash, now,
                    salt, p_hash, now,
                    salt, p_hash, now,
                    salt, p_hash, now,
                    salt, p_hash, now,
                ),
            )
            conn.execute("UPDATE users SET reg_number = 'SCT/001/2025' WHERE id = 6")
            conn.execute("UPDATE users SET reg_number = 'SCT/002/2025' WHERE id = 7")
            conn.execute("UPDATE users SET reg_number = 'SCT/003/2025' WHERE id = 8")

            conn.execute(
                """
                INSERT INTO courses (id, code, title, lecturer_id, created_at)
                VALUES ('course-cs101', 'CS101', 'Intro to Computer Science', 1, ?)
                """,
                (now,),
            )
            for sid in [6, 7, 8]:
                conn.execute(
                    "INSERT INTO enrollments (course_id, student_id, created_at) VALUES ('course-cs101', ?, ?)",
                    (sid, now),
                )
            conn.execute(
                """
                INSERT INTO assessments (id, course_id, name, max_mark, created_at)
                VALUES ('assess-cat1', 'course-cs101', 'CAT 1', 30.0, ?)
                """,
                (now,),
            )

    def test_full_blockchain_audit_lifecycle(self):
        # 1. Lecturer submits batch with CSV using registration numbers
        csv_data = "registration_number,mark\nSCT/001/2025,24\nSCT/002/2025,28\n"
        # SCT/003/2025 will be missing
        sub_res = self.service.submit_batch(
            user_id=1,
            assessment_id="assess-cat1",
            csv_text=csv_data,
        )

        batch_id = sub_res["batch_id"]
        self.assertEqual(sub_res["chain_state"], "CONFIRMED")
        self.assertTrue(sub_res["chain_tx_hash"].startswith("0x"))
        self.assertEqual(sub_res["missing_count"], 1)

        # 2. Check on-chain state
        rev_count = self.chain.get_revision_count(batch_id)
        self.assertEqual(rev_count, 1)

        conn = self.db.connect()
        try:
            marks_hash = conn.execute(
                "SELECT marks_hash FROM batches WHERE id = ?", (batch_id,)
            ).fetchone()["marks_hash"]
        finally:
            conn.close()

        reconcile = self.chain.reconcile(batch_id, 1, marks_hash)
        self.assertTrue(reconcile["match"])
        self.assertEqual(reconcile["status"], "MATCH")

        # 3. Reviewer verifies batch on-chain (revision 1)
        v_res = self.service.verify_batch(user_id=2, batch_id=batch_id)
        self.assertEqual(v_res["status"], "VERIFIED")
        self.assertEqual(v_res["chain_state"], "CONFIRMED")
        self.assertTrue(v_res["chain_tx_hash"].startswith("0x"))

        # 4. Exam office processes revision 1
        exo_res1 = self.service.process_exam_office_batch(user_id=3, batch_id=batch_id)
        self.assertEqual(exo_res1["pipeline_stage"], "PORTAL_IMPORT")

        # 5. Portal operator imports and publishes initial batch
        pub_res1 = self.service.publish_portal_batch(user_id=4, batch_id=batch_id)
        self.assertEqual(pub_res1["pipeline_stage"], "PUBLISHED")

        # 6. Student 3 discovers their mark is MISSING and opens a missing mark report
        rep_res = self.service.report_missing_mark(
            user_id=8,
            assessment_id="assess-cat1",
        )
        report_id = rep_res["id"]

        # 7. Lecturer resolves report (awards mark 22) -> triggers batch amendment on-chain
        res_res = self.service.resolve_report(
            user_id=1,
            report_id=report_id,
            resolution_type="MARK_ENTERED",
            mark=22.0,
            note="Found script in physical department archive.",
        )
        self.assertEqual(res_res["status"], "PENDING_REVIEW")
        self.assertEqual(res_res["chain_state"], "CONFIRMED")
        self.assertEqual(res_res["revision"], 2)

        # 8. Verify on-chain has revision 2 and reconcile matches revision 2
        rev_count_2 = self.chain.get_revision_count(batch_id)
        self.assertEqual(rev_count_2, 2)

        conn = self.db.connect()
        try:
            marks_hash_2 = conn.execute(
                "SELECT marks_hash FROM batches WHERE id = ?", (batch_id,)
            ).fetchone()["marks_hash"]
        finally:
            conn.close()

        reconcile_2 = self.chain.reconcile(batch_id, 2, marks_hash_2)
        self.assertTrue(reconcile_2["match"])
        self.assertEqual(reconcile_2["chain_revision"], 2)

        # 9. Reviewer approves amended batch (revision 2)
        v_res2 = self.service.verify_batch(user_id=2, batch_id=batch_id)
        self.assertEqual(v_res2["status"], "VERIFIED")

        # 10. Exam office processes amended batch
        exo_res2 = self.service.process_exam_office_batch(user_id=3, batch_id=batch_id)
        self.assertEqual(exo_res2["pipeline_stage"], "PORTAL_IMPORT")

        # 11. Portal operator imports and publishes (auto-reconciliation triggers)
        pub_res2 = self.service.publish_portal_batch(user_id=4, batch_id=batch_id)
        self.assertEqual(pub_res2["pipeline_stage"], "PUBLISHED")

        # 12. Check all student published marks
        conn = self.db.connect()
        try:
            marks_rows = conn.execute(
                """
                SELECT student_id, published_mark, published_status
                FROM assessment_marks
                WHERE batch_id = ?
                ORDER BY student_id
                """,
                (batch_id,),
            ).fetchall()
        finally:
            conn.close()

        self.assertEqual(len(marks_rows), 3)
        self.assertEqual(marks_rows[0]["published_mark"], 24.0)
        self.assertEqual(marks_rows[1]["published_mark"], 28.0)
        self.assertEqual(marks_rows[2]["published_mark"], 22.0)
        self.assertEqual(marks_rows[2]["published_status"], "RECORDED")
