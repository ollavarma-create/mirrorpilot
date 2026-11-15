"""Adversarial tests of sandbox-only transaction journal and filesystem.

No privileged execution, no DNF5, no /etc writes.
"""
import json
import os
from pathlib import Path

import pytest

from mirrorpilot.dnf_sandbox_transaction import SandboxDNFTransaction, digest


@pytest.fixture
def sandbox(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("Sandbox transaction forbids root")
    return tmp_path


def _journal(tx, before=b"before", after=b"after", state="PREPARED"):
    tx._save({
        "version": 1, "state": state,
        "before_hex": before.hex(), "before_mode": 0o640,
        "before_sha256": digest(before), "after_sha256": digest(after),
        "expected_sha256": digest(after),
    })


@pytest.mark.parametrize("bad", [
    b"not-json", b"{", b"[]", b"null", b'{"version":999,"state":"PREPARED"}',
])
def test_corrupt_journal_rejected_without_modifying_target(sandbox, bad):
    tx = SandboxDNFTransaction(sandbox)
    tx.tx.target.write_bytes(b"keep")
    tx.journal.write_bytes(bad)
    with pytest.raises((ValueError, RuntimeError, TypeError, AttributeError)):
        tx.recover()
    assert tx.tx.target.read_bytes() == b"keep"
    assert tx.journal.read_bytes() == bad


def test_symlink_journal_rejected(sandbox):
    tx = SandboxDNFTransaction(sandbox)
    outside = sandbox / "outside"
    outside.write_text("untouched")
    tx.journal.symlink_to(outside)
    with pytest.raises(RuntimeError, match="symlink"):
        tx.recover()
    assert outside.read_text() == "untouched"


def test_symlink_lock_rejected(sandbox):
    tx = SandboxDNFTransaction(sandbox)
    outside = sandbox / "outside"
    outside.write_text("untouched")
    tx.lock_path.symlink_to(outside)
    with pytest.raises(RuntimeError, match="symlink"):
        tx.recover()
    assert outside.read_text() == "untouched"


def test_symlink_target_rejected(sandbox):
    tx = SandboxDNFTransaction(sandbox)
    outside = sandbox / "outside"
    outside.write_bytes(b"untouched")
    tx.tx.target.symlink_to(outside)
    _journal(tx)
    with pytest.raises(ValueError, match="non-linked"):
        tx.recover()
    assert outside.read_bytes() == b"untouched"


def test_hardlink_target_rejected(sandbox):
    tx = SandboxDNFTransaction(sandbox)
    outside = sandbox / "outside"
    outside.write_bytes(b"untouched")
    os.link(outside, tx.tx.target)
    _journal(tx)
    with pytest.raises(ValueError, match="non-linked"):
        tx.recover()
    assert outside.read_bytes() == b"untouched"


def test_lock_contention_blocks_second_transaction(sandbox):
    tx1 = SandboxDNFTransaction(sandbox)
    tx2 = SandboxDNFTransaction(sandbox)
    fd = tx1._lock()
    try:
        with pytest.raises(BlockingIOError):
            tx2.recover()
    finally:
        os.close(fd)


def test_unknown_output_does_not_overwrite_existing_bytes(sandbox):
    tx = SandboxDNFTransaction(sandbox)
    tx.tx.target.write_bytes(b"other")
    _journal(tx)
    assert tx.recover() == "conflict-manual-review"
    assert tx.tx.target.read_bytes() == b"other"
    assert tx.journal.exists()


def test_restore_preserves_bytes_and_mode(sandbox):
    tx = SandboxDNFTransaction(sandbox)
    before, after = b"# old\n[fedora]\nbaseurl=old\n", b"# new\n[fedora]\nbaseurl=new\n"
    tx.tx.target.write_bytes(after)
    _journal(tx, before, after, state="APPLIED")
    assert tx.recover() == "restored"
    assert tx.tx.target.read_bytes() == before
    assert tx.tx.target.stat().st_mode & 0o777 == 0o640


@pytest.mark.xfail(strict=True, reason="Journal snapshot authenticity is not yet enforced")
def test_tampered_before_image_is_rejected(sandbox):
    tx = SandboxDNFTransaction(sandbox)
    tx.tx.target.write_bytes(b"after")
    _journal(tx, b"before", b"after", state="APPLIED")
    doc = json.loads(tx.journal.read_text())
    doc["before_hex"] = b"forged".hex()
    tx._save(doc)
    with pytest.raises(RuntimeError, match="journal integrity"):
        tx.recover()
    assert tx.tx.target.read_bytes() == b"after"
