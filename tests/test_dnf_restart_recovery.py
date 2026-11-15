"""Crash/restart regression tests for the sandbox-only DNF5 transaction.

These tests never invoke DNF5 or write to /etc. A fresh Python interpreter
simulates restarting MirrorPilot after the journal has been persisted.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from mirrorpilot.dnf_sandbox_transaction import SandboxDNFTransaction, digest


@pytest.fixture
def sandbox(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("Sandbox transaction explicitly forbids root")
    return tmp_path


def _restart_recover(path):
    script = (
        "import sys; "
        "from pathlib import Path; "
        "from mirrorpilot.dnf_sandbox_transaction import SandboxDNFTransaction; "
        "print(SandboxDNFTransaction(Path(sys.argv[1])).recover())"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        capture_output=True, text=True, timeout=15, check=True,
    )
    return result.stdout.strip()


def _prepare(path, before, expected):
    tx = SandboxDNFTransaction(path)
    tx.tx.target.write_bytes(before)
    tx._save({
        "version": 1, "state": "PREPARED",
        "before_hex": before.hex(), "before_mode": 0o640,
        "before_sha256": digest(before),
        "after_sha256": None, "expected_sha256": digest(expected),
    })
    return tx


def test_expected_digest_survives_process_restart(sandbox):
    before = b"# old\n[fedora]\nbaseurl=old\n"
    expected = b"# new\n[fedora]\nbaseurl=new\n"
    tx = _prepare(sandbox, before, expected)
    assert json.loads(tx.journal.read_text())["expected_sha256"] == digest(expected)
    tx.tx.target.write_bytes(expected)
    assert _restart_recover(sandbox) == "restored"
    assert tx.tx.target.read_bytes() == before
    assert tx.tx.target.stat().st_mode & 0o777 == 0o640
    assert not tx.journal.exists()


def test_partial_write_is_not_overwritten_after_restart(sandbox):
    tx = _prepare(sandbox, b"original", b"expected")
    tx.tx.target.write_bytes(b"expe")
    assert _restart_recover(sandbox) == "conflict-manual-review"
    assert tx.tx.target.read_bytes() == b"expe"
    assert tx.journal.exists()


def test_third_party_change_is_not_overwritten_after_restart(sandbox):
    tx = _prepare(sandbox, b"original", b"expected")
    tx.tx.target.write_bytes(b"third-party edit")
    assert _restart_recover(sandbox) == "conflict-manual-review"
    assert tx.tx.target.read_bytes() == b"third-party edit"
    assert tx.journal.exists()


def test_original_unchanged_clears_journal_after_restart(sandbox):
    tx = _prepare(sandbox, b"original", b"expected")
    assert _restart_recover(sandbox) == "already-original"
    assert tx.tx.target.read_bytes() == b"original"
    assert not tx.journal.exists()


def test_legacy_prepared_without_prediction_still_fails_closed(sandbox):
    tx = _prepare(sandbox, b"original", b"expected")
    document = json.loads(tx.journal.read_text())
    document.pop("expected_sha256")
    tx._save(document)
    tx.tx.target.write_bytes(b"expected")
    assert _restart_recover(sandbox) == "conflict-manual-review"
    assert tx.tx.target.read_bytes() == b"expected"


def test_apply_persists_expected_digest_before_writer_runs(sandbox, monkeypatch):
    tx = SandboxDNFTransaction(sandbox)
    tx.tx.target.write_bytes(b"original")
    expected = b"expected"
    def simulate_writer(command, **kwargs):
        journal = json.loads(tx.journal.read_text())
        assert journal["state"] == "PREPARED"
        assert journal["expected_sha256"] == digest(expected)
        tx.tx.target.write_bytes(expected)
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(subprocess, "run", simulate_writer)
    assert tx.apply(
        ["bwrap", "--ro-bind", "/", "/", "--", "dnf5"],
        lambda: tx.tx.target.read_bytes() == expected,
        expected_sha256=digest(expected),
    ) == "verified"


@pytest.mark.parametrize("bad", ["abc", "Z" * 64, 123, "", None])
def test_invalid_expected_digest_rejected(sandbox, bad):
    if bad is None:
        pytest.skip("None intentionally means no prediction for legacy callers")
    tx = SandboxDNFTransaction(sandbox)
    with pytest.raises(ValueError):
        tx.apply(["bwrap", "--ro-bind", "/", "/", "--", "dnf5"],
                 lambda: True, expected_sha256=bad)
    assert not tx.journal.exists()
