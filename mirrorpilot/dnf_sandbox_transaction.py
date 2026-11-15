"""Sandbox-only DNF5 config-manager transaction experiment.

This module must never be run as root or pointed at real /etc. It deliberately
does not implement a privileged writer. The caller supplies a fresh temp fixture.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from mirrorpilot.sandbox_transaction import SandboxTransaction, Snapshot
from mirrorpilot.durable_sandbox import _sync_directory, _write_atomic

JOURNAL = ".mirrorpilot-dnf-transaction.json"
LOCK = ".mirrorpilot-dnf-transaction.lock"


def digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


class SandboxDNFTransaction:
    """Crash-recoverable *experiment* with an external DNF5 writer.

    The journal stores a before-image and an expected after-image. Recovery
    refuses to overwrite unknown third-party changes. PREPARED may describe
    an interrupted external writer; in that case recovery reports a conflict
    rather than guessing whether the partial output is safe to replace.
    """

    def __init__(self, root: Path):
        self.tx = SandboxTransaction(root, "99-config_manager.repo")
        self.root = self.tx.root
        self.journal = self.root / JOURNAL
        self.lock_path = self.root / LOCK

    def _load(self) -> dict | None:
        if self.journal.is_symlink():
            raise RuntimeError("Journal symlink rejected")
        if not self.journal.exists():
            return None
        doc = json.loads(self.journal.read_text(encoding="utf-8"))
        if doc.get("version") != 1 or doc.get("state") not in ("PREPARED", "APPLIED", "VERIFIED"):
            raise RuntimeError("Invalid transaction journal")
        return doc

    def _save(self, doc: dict) -> None:
        _write_atomic(self.journal, json.dumps(doc, sort_keys=True).encode())

    def _lock(self):
        if self.lock_path.is_symlink():
            raise RuntimeError("Lock symlink rejected")
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd

    def _read(self) -> bytes | None:
        snap = self.tx._snapshot()
        return snap.contents if snap.existed else None

    def _restore(self, doc: dict) -> None:
        original = bytes.fromhex(doc["before_hex"]) if doc["before_hex"] is not None else None
        mode = doc["before_mode"]
        self.tx.restore(Snapshot(original is not None, original, mode))
        _sync_directory(self.root)

    def _recover_locked(self) -> str:
        doc = self._load()
        if doc is None:
            return "clean"
        if doc["state"] == "VERIFIED":
            return "verified"
        current = digest(self._read())
        if current == doc["before_sha256"]:
            self.journal.unlink()
            _sync_directory(self.root)
            return "already-original"
        if doc["state"] == "PREPARED":
            if doc.get("expected_sha256") is None or current != doc["expected_sha256"]:
                return "conflict-manual-review"
        elif current != doc.get("after_sha256"):
            return "conflict-manual-review"
        self._restore(doc)
        self.journal.unlink()
        _sync_directory(self.root)
        return "restored"

    def recover_expected(self, expected_sha256: str) -> str:
        """Recover PREPARED only when bytes match a separately verified prediction.

        The prediction must be computed before the write from an isolated
        fixture. Unknown or partially written content remains untouched.
        Sandbox prototype only; not a privileged recovery authorization.
        """
        if os.geteuid() == 0:
            raise RuntimeError("Root execution forbidden")
        if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
                or any(ch not in "0123456789abcdef" for ch in expected_sha256)):
            raise ValueError("Invalid SHA-256")
        fd = self._lock()
        try:
            doc = self._load()
            if doc is None:
                return "clean"
            if doc["state"] != "PREPARED":
                return self._recover_locked()
            current = digest(self._read())
            if current == doc["before_sha256"]:
                self.journal.unlink()
                _sync_directory(self.root)
                return "already-original"
            if current != expected_sha256:
                return "conflict-manual-review"
            self._restore(doc)
            self.journal.unlink()
            _sync_directory(self.root)
            return "restored-expected"
        finally:
            os.close(fd)

    def recover(self) -> str:
        if os.geteuid() == 0:
            raise RuntimeError("Root execution forbidden")
        fd = self._lock()
        try:
            return self._recover_locked()
        finally:
            os.close(fd)

    def apply(self, command: list[str], verify, checkpoint=None, *, expected_sha256: str | None = None) -> str:
        """Run a caller-provided sandboxed DNF5 command, never an arbitrary host writer.

        The command must start with bwrap and use a read-only root bind. This
        is a test harness, not a security boundary for untrusted callers.
        """
        if os.geteuid() == 0:
            raise RuntimeError("Root execution forbidden")
        if not command or Path(command[0]).name != "bwrap" or "--ro-bind" not in command:
            raise ValueError("Only bwrap-confined test commands accepted")
        if expected_sha256 is not None and (
                type(expected_sha256) is not str or len(expected_sha256) != 64
                or any(ch not in "0123456789abcdef" for ch in expected_sha256)):
            raise ValueError("Invalid expected SHA-256")
        fd = self._lock()
        try:
            if self._load() is not None:
                raise RuntimeError("Pending journal; inspect or recover first")
            before = self.tx._snapshot()
            doc = {
                "version": 1, "state": "PREPARED",
                "before_hex": before.contents.hex() if before.existed else None,
                "before_mode": before.mode,
                "before_sha256": digest(before.contents),
                "after_sha256": None,
                "expected_sha256": expected_sha256,
            }
            self._save(doc)
            if checkpoint:
                checkpoint("PREPARED")
            result = subprocess.run(command, text=True, capture_output=True, timeout=30, check=False)
            after = self._read()
            doc["after_sha256"] = digest(after)
            doc["state"] = "APPLIED"
            self._save(doc)
            if checkpoint:
                checkpoint("APPLIED")
            if result.returncode or not verify():
                status = self._recover_locked()
                if status not in ("restored", "already-original"):
                    raise RuntimeError("Verification failed; recovery conflict: " + status)
                raise RuntimeError("DNF5 change failed and sandbox original restored")
            doc["state"] = "VERIFIED"
            self._save(doc)
            return "verified"
        finally:
            os.close(fd)

    def clear_verified(self) -> None:
        fd = self._lock()
        try:
            doc = self._load()
            if doc is None or doc["state"] != "VERIFIED":
                raise RuntimeError("No verified transaction")
            self.journal.unlink()
            _sync_directory(self.root)
        finally:
            os.close(fd)
