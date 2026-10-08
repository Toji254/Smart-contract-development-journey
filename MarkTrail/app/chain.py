from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass


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
                "label": "Connected to EVM chain",
                "contract": self.config.contract,
                "block": block,
            }
        except Exception as exc:
            return {
                "mode": "cast",
                "enabled": True,
                "label": "Configured but unavailable",
                "contract": self.config.contract,
                "error": str(exc),
            }

    def _run(self, args: list[str]) -> str:
        if not self.enabled:
            raise ChainError("Chain integration is disabled.")

        try:
            proc = subprocess.run(
                ["cast", *args],
                check=True,
                text=True,
                capture_output=True,
                timeout=90,
            )
        except FileNotFoundError as exc:
            raise ChainError("Foundry 'cast' was not found on PATH.") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout).strip()
            raise ChainError(detail or "cast command failed") from exc
        return (proc.stdout or "").strip()

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
        output = self.call("getRevisionCount(bytes32)", batch_id)
        numbers = re.findall(r"\b\d+\b", output)
        if not numbers:
            raise ChainError(f"Could not parse revision count: {output}")
        return int(numbers[0])

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

    def reconcile(self, batch_id: str, local_revision: int, local_hash: str) -> dict:
        if not self.enabled:
            return {
                "status": "LOCAL_ONLY",
                "match": False,
                "reason": "Blockchain integration is disabled.",
            }

        chain_count = self.get_revision_count(batch_id)
        chain_hash = self.get_revision_hash(batch_id, chain_count - 1)

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
