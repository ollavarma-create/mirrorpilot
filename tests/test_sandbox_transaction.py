"""Tests operate exclusively in pytest temporary directories."""
import os
import pytest

from mirrorpilot.sandbox_transaction import SandboxTransaction


def test_apply_and_explicit_restore(tmp_path):
    target = tmp_path / "99_mirrorpilot.repo"
    target.write_bytes(b"original\n")
    target.chmod(0o640)
    tx = SandboxTransaction(tmp_path)
    backup = tx.apply(b"new\n", lambda path: path.read_bytes() == b"new\n")
    assert target.read_bytes() == b"new\n"
    tx.restore(backup)
    assert target.read_bytes() == b"original\n"
    assert target.stat().st_mode & 0o777 == 0o640


def test_failed_verification_restores_existing_file(tmp_path):
    target = tmp_path / "99_mirrorpilot.repo"
    target.write_bytes(b"original")
    tx = SandboxTransaction(tmp_path)
    with pytest.raises(RuntimeError, match="verification"):
        tx.apply(b"changed", lambda path: False)
    assert target.read_bytes() == b"original"


def test_failed_verification_removes_new_file(tmp_path):
    tx = SandboxTransaction(tmp_path)
    with pytest.raises(RuntimeError):
        tx.apply(b"new", lambda path: False)
    assert not tx.target.exists()


def test_verifier_exception_restores(tmp_path):
    tx = SandboxTransaction(tmp_path)
    tx.target.write_bytes(b"before")
    def fail(_path):
        raise RuntimeError("verifier crashed")
    with pytest.raises(RuntimeError, match="crashed"):
        tx.apply(b"after", fail)
    assert tx.target.read_bytes() == b"before"


def test_reject_symlink_target(tmp_path):
    other = tmp_path / "other"
    other.write_bytes(b"untouched")
    (tmp_path / "99_mirrorpilot.repo").symlink_to(other)
    tx = SandboxTransaction(tmp_path)
    with pytest.raises(ValueError, match="non-linked"):
        tx.apply(b"evil", lambda _: True)
    assert other.read_bytes() == b"untouched"


def test_reject_hardlinked_target(tmp_path):
    original = tmp_path / "other"
    original.write_bytes(b"untouched")
    os.link(original, tmp_path / "99_mirrorpilot.repo")
    tx = SandboxTransaction(tmp_path)
    with pytest.raises(ValueError):
        tx.apply(b"evil", lambda _: True)
    assert original.read_bytes() == b"untouched"


def test_reject_non_sandbox_path():
    with pytest.raises(ValueError):
        SandboxTransaction("/etc/dnf/repos.override.d")


def test_reject_oversized_payload(tmp_path):
    tx = SandboxTransaction(tmp_path)
    with pytest.raises(ValueError):
        tx.apply(b"x" * (1024 * 1024 + 1), lambda _: True)
