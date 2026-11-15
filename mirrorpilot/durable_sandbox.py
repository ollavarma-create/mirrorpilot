"""Durable *sandbox-only* transaction journal and restart recovery prototype.

Never invoke with privileges. Not safe for /etc: this does not implement
fd-relative filesystem confinement, concurrent writer locking, SELinux/ACL
preservation, or DNF5 policy validation.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Callable

from mirrorpilot.sandbox_transaction import SandboxTransaction, Snapshot

STATES = frozenset({"PREPARED", "APPLIED", "VERIFIED"})
JOURNAL = ".mirrorpilot-transaction.json"


def _sync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_atomic(path: Path, contents: bytes) -> None:
    fd, temp_path = tempfile.mkstemp(prefix=".mirrorpilot-journal-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        _sync_directory(path.parent)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


class DurableSandboxTransaction:
    """Persistent before-image and recovery, confined to temporary test dirs.

    State transition ordering:
    PREPARED persisted -> target replaced -> APPLIED persisted -> verification
    -> VERIFIED persisted. A crash between replacement and APPLIED still
    leaves PREPARED and is recovered by restoring the before-image.
    """

    def __init__(self, root: Path):
        self.tx = SandboxTransaction(root)
        self.journal = self.tx.root / JOURNAL

    def _load(self) -> dict | None:
        if self.journal.is_symlink():
            raise ValueError("Journal symlink rejected")
        if not self.journal.exists():
            return None
        raw = self.journal.read_bytes()
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Journal too large")
        doc = json.loads(raw)
        if not isinstance(doc, dict) or doc.get("state") not in STATES:
            raise ValueError("Invalid journal")
        data = doc.get("backup")
        if not isinstance(data, dict) or type(data.get("existed")) is not bool:
            raise ValueError("Invalid backup")
        contents = data.get("contents")
        if data["existed"]:
            if not isinstance(contents, str) or len(contents) > 1500000:
                raise ValueError("Invalid backup contents")
            decoded = base64.b64decode(contents, validate=True)
            if len(decoded) > 1024 * 1024 or hashlib.sha256(decoded).hexdigest() != data.get("sha256"):
                raise ValueError("Backup integrity mismatch")
            if type(data.get("mode")) is not int or not 0 <= data["mode"] <= 0o7777:
                raise ValueError("Invalid backup mode")
        else:
            if contents is not None or data.get("mode") is not None:
                raise ValueError("Invalid absent-file backup")
        return doc

    def _save(self, state: str, before: Snapshot) -> None:
        if state not in STATES:
            raise ValueError("Invalid transaction state")
        backup = {
            "existed": before.existed,
            "contents": base64.b64encode(before.contents).decode("ascii") if before.existed else None,
            "mode": before.mode,
            "sha256": hashlib.sha256(before.contents).hexdigest() if before.existed else None,
        }
        _write_atomic(self.journal, json.dumps({"version": 1, "state": state, "backup": backup},
                                                sort_keys=True).encode("utf-8"))

    def _backup(self, doc: dict) -> Snapshot:
        data = doc["backup"]
        return Snapshot(data["existed"],
                        base64.b64decode(data["contents"]) if data["existed"] else None,
                        data["mode"])

    def recover(self) -> str:
        """Restore unfinished work; retain VERIFIED journal for explicit cleanup.

        VERIFIED means the verifier accepted the change, not that DNF5 has
        checked anything. Caller may remove the journal after recording success.
        """
        doc = self._load()
        if doc is None:
            return "clean"
        if doc["state"] == "VERIFIED":
            return "verified"
        self.tx.restore(self._backup(doc))
        _sync_directory(self.tx.root)
        self.journal.unlink()
        _sync_directory(self.tx.root)
        return "restored"

    def apply(self, new_contents: bytes, verify: Callable[[Path], bool],
              checkpoint: Callable[[str], None] | None = None) -> None:
        """Simulate checkpoints, allowing BaseException to mimic process death."""
        if self._load() is not None:
            raise RuntimeError("Pending transaction; recover first")
        if not isinstance(new_contents, bytes) or len(new_contents) > 1024 * 1024:
            raise ValueError("Invalid sandbox payload")
        before = self.tx._snapshot()
        self._save("PREPARED", before)
        if checkpoint:
            checkpoint("PREPARED")
        try:
            self.tx._replace(new_contents, before.mode if before.existed else 0o600)
            _sync_directory(self.tx.root)
            if checkpoint:
                checkpoint("TARGET_REPLACED")
            self._save("APPLIED", before)
            if checkpoint:
                checkpoint("APPLIED")
            if not verify(self.tx.target):
                raise RuntimeError("Verification failed")
            self._save("VERIFIED", before)
        except Exception:
            self.recover()
            raise

    def clear_verified(self) -> None:
        doc = self._load()
        if doc is None or doc["state"] != "VERIFIED":
            raise RuntimeError("Only verified transactions can be cleared")
        self.journal.unlink()
        _sync_directory(self.tx.root)
