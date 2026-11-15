"""Conflict-aware sandbox recovery; no privileged writes."""
from pathlib import Path
import tempfile

import pytest

from mirrorpilot.durable_sandbox import DurableSandboxTransaction


@pytest.mark.parametrize("checkpoint", ["PREPARED", "TARGET_REPLACED", "APPLIED"])
def test_recovery_after_interruption(checkpoint):
    with tempfile.TemporaryDirectory(prefix="mirrorpilot-conflict-") as temp:
        root = Path(temp)
        target = root / "99_mirrorpilot.repo"
        target.write_bytes(b"before")
        tx = DurableSandboxTransaction(root)

        def stop(state):
            if state == checkpoint:
                raise SystemExit()

        with pytest.raises(SystemExit):
            tx.apply(b"after", lambda _: True, checkpoint=stop)
        assert DurableSandboxTransaction(root).recover() in ("restored", "unchanged")
        assert target.read_bytes() == b"before"


@pytest.mark.parametrize("checkpoint", ["PREPARED", "TARGET_REPLACED", "APPLIED"])
def test_external_edit_blocks_recovery(checkpoint):
    with tempfile.TemporaryDirectory(prefix="mirrorpilot-conflict-") as temp:
        root = Path(temp)
        target = root / "99_mirrorpilot.repo"
        target.write_bytes(b"before")
        tx = DurableSandboxTransaction(root)

        def stop(state):
            if state == checkpoint:
                raise SystemExit()

        with pytest.raises(SystemExit):
            tx.apply(b"after", lambda _: True, checkpoint=stop)
        target.write_bytes(b"third-party-change")
        with pytest.raises(RuntimeError, match="Recovery conflict"):
            DurableSandboxTransaction(root).recover()
        assert target.read_bytes() == b"third-party-change"
        assert tx.journal.exists()


def test_missing_target_blocks_recovery():
    with tempfile.TemporaryDirectory(prefix="mirrorpilot-conflict-") as temp:
        root = Path(temp)
        target = root / "99_mirrorpilot.repo"
        target.write_bytes(b"before")
        tx = DurableSandboxTransaction(root)

        def stop(state):
            if state == "TARGET_REPLACED":
                raise SystemExit()

        with pytest.raises(SystemExit):
            tx.apply(b"after", lambda _: True, checkpoint=stop)
        target.unlink()
        with pytest.raises(RuntimeError, match="Recovery conflict"):
            DurableSandboxTransaction(root).recover()
        assert not target.exists()
        assert tx.journal.exists()
