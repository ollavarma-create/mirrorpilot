"""Read-only dirfd identity probes for future privileged-helper design.

This is NOT a writer, authorization boundary, or production filesystem guard.
It checks directory and inode identity with no-follow semantics, then closes
all descriptors. A future helper must additionally bind writes to trusted
directories and address races in DNF5's external writer.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    mode: int
    size: int


def _identity(info: os.stat_result) -> FileIdentity:
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Expected an unlinked regular file")
    return FileIdentity(info.st_dev, info.st_ino, stat.S_IMODE(info.st_mode), info.st_size)


def inspect_file_identity(directory: Path, basename: str) -> tuple[FileIdentity, FileIdentity]:
    """Inspect a sandbox file through directory-relative, no-follow opens.

    Returns (directory identity, file identity). Missing targets fail closed.
    Caller must recheck immediately before use; this alone does not prevent
    subsequent substitution and must not authorize any writes.
    """
    if type(basename) is not str or basename in ("", ".", "..") or "/" in basename or "\\x00" in basename:
        raise ValueError("Invalid basename")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    dirfd = os.open(directory, flags)
    try:
        di = os.fstat(dirfd)
        if not stat.S_ISDIR(di.st_mode):
            raise ValueError("Not a directory")
        fd = os.open(basename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dirfd)
        try:
            return (
                FileIdentity(di.st_dev, di.st_ino, stat.S_IMODE(di.st_mode), di.st_size),
                _identity(os.fstat(fd)),
            )
        finally:
            os.close(fd)
    finally:
        os.close(dirfd)


def identity_still_matches(directory: Path, basename: str, expected: tuple[FileIdentity, FileIdentity]) -> bool:
    """Detect substitutions between two observations, not an atomic guarantee."""
    try:
        return inspect_file_identity(directory, basename) == expected
    except (OSError, ValueError):
        return False
