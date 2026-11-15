"""Unprivileged transaction prototype, restricted to a caller-owned sandbox.

NOT a system configuration writer or a privileged helper. No Polkit integration.
A real helper needs independently validated DNF5 policy, root-owned backups,
symlink-safe filesystem operations, metadata preservation and fsync discipline.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import tempfile
from typing import Callable


@dataclass(frozen=True)
class Snapshot:
    existed: bool
    contents: bytes | None
    mode: int | None


class SandboxTransaction:
    """Exercise apply/rollback behavior exclusively inside a fresh sandbox.

    The root must be a real directory within the system temporary directory.
    The target must be a single basename and never a symlink.
    Do not use this class on /etc or for privileged writes.
    """

    def __init__(self, root: Path, filename: str = "99_mirrorpilot.repo"):
        self.root = Path(root)
        temp = Path(tempfile.gettempdir()).resolve()
        if (self.root.is_symlink() or not self.root.is_dir()
                or not self.root.resolve().is_relative_to(temp)
                or self.root.resolve() == temp):
            raise ValueError("Transaction root must be a real sandbox directory")
        if filename in ("", ".", "..") or Path(filename).name != filename or "/" in filename:
            raise ValueError("Target must be a single filename")
        self.target = self.root / filename

    def _snapshot(self) -> Snapshot:
        try:
            info = self.target.lstat()
        except FileNotFoundError:
            return Snapshot(False, None, None)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Only non-linked regular sandbox files are supported")
        return Snapshot(True, self.target.read_bytes(), stat.S_IMODE(info.st_mode))

    def _replace(self, data: bytes, mode: int = 0o600) -> None:
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError("Sandbox changed")
        # Recheck before replacement. This is not sufficient for privileged use.
        self._snapshot()
        fd, name = tempfile.mkstemp(prefix=".mirrorpilot-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
                os.fchmod(stream.fileno(), mode)
            os.replace(name, self.target)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def apply(self, new_contents: bytes, verify: Callable[[Path], bool]) -> Snapshot:
        """Apply test bytes; roll back to the exact prior bytes if verification fails."""
        if not isinstance(new_contents, bytes) or len(new_contents) > 1024 * 1024:
            raise ValueError("Sandbox payload must be bytes (max 1 MiB)")
        before = self._snapshot()
        try:
            self._replace(new_contents, before.mode if before.existed else 0o600)
            if not verify(self.target):
                raise RuntimeError("Sandbox verification rejected change")
        except Exception:
            self.restore(before)
            raise
        return before

    def restore(self, before: Snapshot) -> None:
        """Restore an in-memory snapshot, including absence of a prior file."""
        self._snapshot()
        if before.existed:
            assert before.contents is not None and before.mode is not None
            self._replace(before.contents, before.mode)
        else:
            self.target.unlink(missing_ok=True)
