"""Crash-window tests use pytest tmp_path only; never touch real DNF."""
import json
import pytest

from mirrorpilot.durable_sandbox import DurableSandboxTransaction


class SimulatedPowerLoss(BaseException):
    pass


@pytest.mark.parametrize("checkpoint", ["PREPARED", "TARGET_REPLACED", "APPLIED"])
def test_recovery_after_simulated_crash(tmp_path, checkpoint):
    target = tmp_path / "99_mirrorpilot.repo"
    target.write_bytes(b"original")
    target.chmod(0o640)
    tx = DurableSandboxTransaction(tmp_path)

    def crash(state):
        if state == checkpoint:
            raise SimulatedPowerLoss()

    with pytest.raises(SimulatedPowerLoss):
        tx.apply(b"new", lambda _: True, checkpoint=crash)

    # Fresh object models a restarted process.
    recovered = DurableSandboxTransaction(tmp_path)
    expected = "unchanged" if checkpoint == "PREPARED" else "restored"
    assert recovered.recover() == expected
    assert target.read_bytes() == b"original"
    assert target.stat().st_mode & 0o777 == 0o640
    assert recovered.recover() == "clean"


@pytest.mark.parametrize("checkpoint", ["PREPARED", "TARGET_REPLACED", "APPLIED"])
def test_recovery_restores_absence(tmp_path, checkpoint):
    def crash(state):
        if state == checkpoint:
            raise SimulatedPowerLoss()
    tx = DurableSandboxTransaction(tmp_path)
    with pytest.raises(SimulatedPowerLoss):
        tx.apply(b"new", lambda _: True, checkpoint=crash)
    assert DurableSandboxTransaction(tmp_path).recover() == "restored"
    assert not (tmp_path / "99_mirrorpilot.repo").exists()


def test_verified_keeps_new_contents_until_explicit_cleanup(tmp_path):
    tx = DurableSandboxTransaction(tmp_path)
    tx.apply(b"good", lambda path: path.read_bytes() == b"good")
    fresh = DurableSandboxTransaction(tmp_path)
    assert fresh.recover() == "verified"
    assert fresh.tx.target.read_bytes() == b"good"
    with pytest.raises(RuntimeError, match="Pending"):
        fresh.apply(b"second", lambda _: True)
    fresh.clear_verified()
    assert fresh.recover() == "clean"


def test_failed_verification_automatically_restores(tmp_path):
    tx = DurableSandboxTransaction(tmp_path)
    tx.tx.target.write_bytes(b"old")
    with pytest.raises(RuntimeError, match="Verification"):
        tx.apply(b"bad", lambda _: False)
    assert tx.tx.target.read_bytes() == b"old"
    assert tx.recover() == "clean"


def test_tampered_backup_fails_closed(tmp_path):
    tx = DurableSandboxTransaction(tmp_path)
    tx.tx.target.write_bytes(b"old")
    def crash(state):
        if state == "PREPARED":
            raise SimulatedPowerLoss()
    with pytest.raises(SimulatedPowerLoss):
        tx.apply(b"new", lambda _: True, checkpoint=crash)
    doc = json.loads(tx.journal.read_text())
    doc["backup"]["sha256"] = "0" * 64
    tx.journal.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="integrity"):
        tx.recover()
    assert tx.journal.exists()


def test_reject_new_transaction_with_unfinished_journal(tmp_path):
    tx = DurableSandboxTransaction(tmp_path)
    def crash(state):
        if state == "PREPARED":
            raise SimulatedPowerLoss()
    with pytest.raises(SimulatedPowerLoss):
        tx.apply(b"one", lambda _: True, checkpoint=crash)
    with pytest.raises(RuntimeError, match="Pending"):
        tx.apply(b"two", lambda _: True)
