"""Tests for sandbox-only transaction recovery; no DNF5 or root needed."""
import os
from pathlib import Path
import tempfile

import pytest

from mirrorpilot.dnf_sandbox_transaction import SandboxDNFTransaction, digest


@pytest.fixture
def sandbox():
    if os.geteuid() == 0:
        pytest.skip("sandbox transaction forbids root")
    with tempfile.TemporaryDirectory(prefix="mirrorpilot-dnf-tx-") as name:
        yield Path(name)


def test_recover_applied_restores_exact_bytes(sandbox):
    tx = SandboxDNFTransaction(sandbox)
    original = b"# original comment\n[fedora]\nbaseurl=old\n"
    tx.tx.target.write_bytes(original)
    tx.tx.target.chmod(0o640)
    changed = b"# generated\n[fedora]\nbaseurl=new\n"
    tx._save({"version": 1, "state": "APPLIED",
              "before_hex": original.hex(), "before_mode": 0o640,
              "before_sha256": digest(original), "after_sha256": digest(changed)})
    tx.tx.target.write_bytes(changed)
    assert tx.recover() == "restored"
    assert tx.tx.target.read_bytes() == original
    assert tx.tx.target.stat().st_mode & 0o777 == 0o640
    assert tx.recover() == "clean"


def test_unknown_concurrent_change_is_not_overwritten(sandbox):
    tx = SandboxDNFTransaction(sandbox)
    original, expected, third_party = b"old", b"new", b"someone else's change"
    tx._save({"version": 1, "state": "APPLIED",
              "before_hex": original.hex(), "before_mode": 0o600,
              "before_sha256": digest(original), "after_sha256": digest(expected)})
    tx.tx.target.write_bytes(third_party)
    assert tx.recover() == "conflict-manual-review"
    assert tx.tx.target.read_bytes() == third_party
    assert tx.journal.exists()


def test_prepared_unknown_state_refuses_guessing(sandbox):
    tx = SandboxDNFTransaction(sandbox)
    tx._save({"version": 1, "state": "PREPARED",
              "before_hex": b"old".hex(), "before_mode": 0o600,
              "before_sha256": digest(b"old"), "after_sha256": None})
    tx.tx.target.write_bytes(b"partial")
    assert tx.recover() == "conflict-manual-review"
    assert tx.tx.target.read_bytes() == b"partial"


def test_prepared_unchanged_clears_journal(sandbox):
    tx = SandboxDNFTransaction(sandbox)
    tx.tx.target.write_bytes(b"old")
    tx._save({"version": 1, "state": "PREPARED",
              "before_hex": b"old".hex(), "before_mode": 0o600,
              "before_sha256": digest(b"old"), "after_sha256": None})
    assert tx.recover() == "already-original"
    assert not tx.journal.exists()
