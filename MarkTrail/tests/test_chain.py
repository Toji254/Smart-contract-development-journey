from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from app.chain import ChainClient, ChainConfig, ChainError, ChainPendingError


class ChainClientTests(unittest.TestCase):
    def setUp(self):
        self.client = ChainClient()
        self.client.config = ChainConfig(
            mode="cast",
            rpc_url="http://127.0.0.1:8545",
            contract="0x" + "11" * 20,
            private_key="0x" + "22" * 32,
        )

    def test_transaction_submission_is_not_automatically_retried(self):
        timeout = subprocess.TimeoutExpired("cast send", 90)
        with patch("app.chain.subprocess.run", side_effect=timeout) as run:
            with patch("app.chain.time.sleep") as sleep:
                with self.assertRaisesRegex(ChainError, "timed out"):
                    self.client.verify_batch("0x" + "33" * 32)

        self.assertEqual(run.call_count, 1)
        sleep.assert_not_called()

    def test_retryable_read_commands_keep_bounded_retries(self):
        failure = subprocess.CalledProcessError(1, ["cast", "block-number"], stderr="temporary failure")
        success = subprocess.CompletedProcess(["cast"], 0, stdout="123\n", stderr="")
        with patch(
            "app.chain.subprocess.run",
            side_effect=[failure, success],
        ) as run:
            with patch("app.chain.time.sleep"):
                self.assertEqual(self.client.block_number(), 123)

        self.assertEqual(run.call_count, 2)

    def test_send_waits_for_receipt_after_async_broadcast(self):
        tx_hash = "0x" + "ab" * 32
        with patch.object(
            self.client,
            "_run",
            side_effect=[tx_hash, '{"status":"0x1"}'],
        ) as run:
            with patch("app.chain.time.sleep") as sleep:
                result = self.client.verify_batch("0x" + "33" * 32)

        self.assertEqual(result, tx_hash)
        self.assertIn("--async", run.call_args_list[0].args[0])
        self.assertIn("receipt", run.call_args_list[1].args[0])
        sleep.assert_not_called()

    def test_unknown_receipt_is_not_treated_as_safe_to_resubmit(self):
        tx_hash = "0x" + "cd" * 32
        with patch.object(self.client, "_run", side_effect=ChainError("RPC unavailable")):
            with self.assertRaises(ChainPendingError) as error:
                self.client.get_transaction_status(tx_hash)

        self.assertEqual(error.exception.tx_hash, tx_hash)

    def test_send_reports_mined_reverts(self):
        tx_hash = "0x" + "ef" * 32
        with patch.object(
            self.client,
            "_run",
            side_effect=[tx_hash, '{"status":"0x0"}'],
        ):
            with self.assertRaisesRegex(ChainError, "mined but reverted"):
                self.client.verify_batch("0x" + "33" * 32)

    def test_get_batch_details_decodes_all_contract_fields(self):
        words = [
            "11" * 32,
            "22" * 32,
            f"{87:064x}",
            f"{2:064x}",
            f"{123456:064x}",
            f"{3:064x}",
        ]
        with patch.object(self.client, "call", return_value="0x" + "".join(words)):
            details = self.client.get_batch_details("0x" + "33" * 32)

        self.assertEqual(details, {
            "course_id": "0x" + "11" * 32,
            "assessment_id": "0x" + "22" * 32,
            "student_count": 87,
            "status": 2,
            "submitted_at": 123456,
            "revision_count": 3,
        })


if __name__ == "__main__":
    unittest.main()
