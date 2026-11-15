"""Threat-model regression tests: no writes, no root, no DNF5.

Probes detect substitutions between observations, but cannot make an external
DNF5 writer atomic or immune to path replacement.
"""
import os

import pytest

from mirrorpilot.fs_identity_probe import inspect_file_identity, identity_still_matches


def test_unchanged_regular_file_matches(tmp_path):
    target = tmp_path / "99-config_manager.repo"
    target.write_bytes(b"[fedora]\n")
    expected = inspect_file_identity(tmp_path, target.name)
    assert identity_still_matches(tmp_path, target.name, expected)


def test_atomic_replacement_detected_even_with_same_bytes(tmp_path):
    target = tmp_path / "99-config_manager.repo"
    target.write_bytes(b"same")
    expected = inspect_file_identity(tmp_path, target.name)
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"same")
    os.replace(replacement, target)
    assert not identity_still_matches(tmp_path, target.name, expected)


def test_symlink_target_rejected(tmp_path):
    target = tmp_path / "99-config_manager.repo"
    outside = tmp_path / "outside"
    outside.write_bytes(b"untouched")
    target.symlink_to(outside)
    with pytest.raises(OSError):
        inspect_file_identity(tmp_path, target.name)
    assert outside.read_bytes() == b"untouched"


def test_hardlink_target_rejected(tmp_path):
    target = tmp_path / "99-config_manager.repo"
    outside = tmp_path / "outside"
    outside.write_bytes(b"untouched")
    os.link(outside, target)
    with pytest.raises(ValueError, match="regular file"):
        inspect_file_identity(tmp_path, target.name)


def test_directory_symlink_rejected(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    (actual / "99-config_manager.repo").write_bytes(b"original")
    link = tmp_path / "alias"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(OSError):
        inspect_file_identity(link, "99-config_manager.repo")


def test_directory_replacement_detected(tmp_path):
    directory = tmp_path / "managed"
    directory.mkdir()
    (directory / "99-config_manager.repo").write_bytes(b"same")
    expected = inspect_file_identity(directory, "99-config_manager.repo")
    directory.rename(tmp_path / "old")
    directory.mkdir()
    (directory / "99-config_manager.repo").write_bytes(b"same")
    assert not identity_still_matches(directory, "99-config_manager.repo", expected)


@pytest.mark.parametrize("basename", ["", ".", "..", "../passwd", "sub/file", "x\x00y"])
def test_invalid_basename_rejected(tmp_path, basename):
    with pytest.raises(ValueError):
        inspect_file_identity(tmp_path, basename)


def test_missing_target_fails_closed(tmp_path):
    assert not identity_still_matches(tmp_path, "99-config_manager.repo", (None, None))


def test_fifo_rejected_without_blocking(tmp_path):
    target = tmp_path / "99-config_manager.repo"
    os.mkfifo(target)
    with pytest.raises(ValueError, match="regular file"):
        inspect_file_identity(tmp_path, target.name)
