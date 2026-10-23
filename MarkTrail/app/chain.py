from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass

log = logging.getLogger("marktrail.chain")


BYTES32_RE = re.compile(r"0x[a-fA-F0-9]{64}")


def bytes32_hash(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode("utf-8")).hexdigest()


class ChainError(RuntimeError):
    pass


@dataclass
class ChainConfig:
    mode: str
    rpc_url: str | None
    contract: str | None
    private_key: str | None

    @property
    def enabled(self) -> bool:
        return (
            self.mode == "cast"
            and bool(self.rpc_url)
            and bool(self.contract)
            and bool(self.private_key)
        )


class ChainClient:
    def __init__(self) -> None:
        self.config = ChainConfig(
            mode=os.getenv("MARKTRAIL_CHAIN_MODE", "off").lower(),
            rpc_url=os.getenv("MARKTRAIL_CHAIN_RPC"),
            contract=os.getenv("MARKTRAIL_CONTRACT"),
            private_key=os.getenv("MARKTRAIL_CHAIN_PRIVATE_KEY"),
        )

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def status(self) -> dict:
        if not self.enabled:
            return {
                "mode": "off",
                "enabled": False,
                "label": "Local-only audit mode",
                "contract": self.config.contract,
            }

        try:
            block = self.block_number()
            return {
                "mode": "cast",
                "enabled": True,
                "label": f"Connected to EVM chain (block {block})",
                "contract": self.config.contract,
                "block": block,
            }
        except Exception as exc:
            log.warning("Chain status check failed: %s", exc)
            return {
                "mode": "cast",
                "enabled": True,
                "label": "Configured but unavailable",
                "contract": self.config.contract,
                "error": str(exc),
            }

    def _run(self, args: list[str], retries: int = 3) -> str:
        """Execute a cast command with exponential backoff retry."""
        if not self.enabled:
            raise ChainError("Chain integration is disabled.")

        last_error: ChainError | None = None
        for attempt in range(1, retries + 1):
            try:
                proc = subprocess.run(
                    ["cast", *args],
                    check=True,
                    text=True,
                    capture_output=True,
                    timeout=90,
                )
                return (proc.stdout or "").strip()
            except FileNotFoundError as exc:
                raise ChainError("Foundry 'cast' was not found on PATH.") from exc
            except subprocess.TimeoutExpired as exc:
                last_error = ChainError(f"cast timed out after 90s (attempt {attempt}/{retries})")
                log.warning("Chain timeout attempt %d/%d: %s", attempt, retries, last_error)
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or exc.stdout or "").strip()
                last_error = ChainError(detail or f"cast command failed (attempt {attempt}/{retries})")
                log.warning("Chain error attempt %d/%d: %s", attempt, retries, detail)

            if attempt < retries:
                delay = 2 ** (attempt - 1)  # 1s, 2s, 4s
                log.info("Retrying chain operation in %ds...", delay)
                time.sleep(delay)

        raise last_error or ChainError("Chain operation failed after all retries.")

    def block_number(self) -> int:
        output = self._run(
            ["block-number", "--rpc-url", self.config.rpc_url or ""]
        )
        match = re.search(r"\d+", output)
        if not match:
            raise ChainError(f"Could not parse block number: {output}")
        return int(match.group(0))

    def call(self, signature: str, *values: str) -> str:
        return self._run(
            [
                "call",
                self.config.contract or "",
                signature,
                *values,
                "--rpc-url",
                self.config.rpc_url or "",
            ]
        )

    def send(self, signature: str, *values: str) -> str:
        output = self._run(
            [
                "send",
                self.config.contract or "",
                signature,
                *values,
                "--rpc-url",
                self.config.rpc_url or "",
                "--private-key",
                self.config.private_key or "",
            ]
        )

        match = re.search(r'"transactionHash"\s*:\s*"(0x[a-fA-F0-9]{64})"', output)
        if match:
            return match.group(1)

        for line in output.splitlines():
            if "transactionHash" in line:
                candidate = BYTES32_RE.search(line)
                if candidate:
                    return candidate.group(0)

        match = BYTES32_RE.search(output)
        if match:
            return match.group(0)

        raise ChainError("cast send succeeded but no transaction hash was found.")

    def submit_batch(
        self,
        batch_id: str,
        course_id: str,
        assessment_id: str,
        student_count: int,
        marks_hash: str,
    ) -> str:
        return self.send(
            "submitBatch(bytes32,bytes32,bytes32,uint32,bytes32)",
            batch_id,
            bytes32_hash(course_id),
            bytes32_hash(assessment_id),
            str(student_count),
            marks_hash,
        )

    def verify_batch(self, batch_id: str) -> str:
        return self.send("verifyBatch(bytes32)", batch_id)

    def amend_batch(
        self,
        batch_id: str,
        new_marks_hash: str,
        reason_hash: str,
    ) -> str:
        return self.send(
            "amendBatch(bytes32,bytes32,bytes32)",
            batch_id,
            new_marks_hash,
            reason_hash,
        )

    def get_revision_count(self, batch_id: str) -> int:
        output = self.call("getRevisionCount(bytes32)", batch_id).strip()
        if output.startswith("0x"):
            try:
                return int(output, 16)
            except ValueError:
                pass
        match = re.search(r"\d+", output)
        if not match:
            raise ChainError(f"Could not parse revision count: {output}")
        return int(match.group(0))

    def get_revision_hash(self, batch_id: str, revision_index: int) -> str:
        output = self.call(
            "getRevision(bytes32,uint256)",
            batch_id,
            str(revision_index),
        )
        match = BYTES32_RE.search(output)
        if not match:
            raise ChainError(f"Could not parse revision hash: {output}")
        return match.group(0)

    def get_batch_status(self, batch_id: str) -> int:
        output = self.call("getBatch(bytes32)", batch_id).strip()
        if not re.fullmatch(r"0x[a-fA-F0-9]{384}", output):
            raise ChainError(f"Could not decode batch status from getBatch: {output}")
        return int(output[2 + 64 * 3 : 2 + 64 * 4], 16)

    def reconcile(self, batch_id: str, local_revision: int, local_hash: str) -> dict:
        if not self.enabled:
            return {
                "status": "LOCAL_ONLY",
                "match": False,
                "reason": "Blockchain integration is disabled.",
            }

        try:
            chain_count = self.get_revision_count(batch_id)
        except ChainError as exc:
            msg = str(exc)
            if "BatchNotFound" in msg or "revert" in msg.lower():
                return {
                    "status": "NOT_ON_CHAIN",
                    "match": False,
                    "reason": "Batch not found on-chain.",
                    "local_revision": local_revision,
                    "chain_revision": 0,
                    "local_hash": local_hash,
                    "chain_hash": None,
                }
            return {
                "status": "CHAIN_ERROR",
                "match": False,
                "reason": f"Chain query failed: {exc}",
                "local_revision": local_revision,
                "chain_revision": 0,
                "local_hash": local_hash,
                "chain_hash": None,
            }

        if chain_count == 0:
            return {
                "status": "NOT_ON_CHAIN",
                "match": False,
                "reason": "No revisions recorded on-chain.",
                "local_revision": local_revision,
                "chain_revision": 0,
                "local_hash": local_hash,
                "chain_hash": None,
            }

        try:
            chain_hash = self.get_revision_hash(batch_id, chain_count - 1)
        except ChainError as exc:
            return {
                "status": "CHAIN_ERROR",
                "match": False,
                "reason": f"Failed to retrieve revision hash: {exc}",
                "local_revision": local_revision,
                "chain_revision": chain_count,
                "local_hash": local_hash,
                "chain_hash": None,
            }

        matched = (
            chain_count == local_revision
            and chain_hash.lower() == local_hash.lower()
        )

        return {
            "status": "MATCH" if matched else "MISMATCH",
            "match": matched,
            "local_revision": local_revision,
            "chain_revision": chain_count,
            "local_hash": local_hash,
            "chain_hash": chain_hash,
        }
