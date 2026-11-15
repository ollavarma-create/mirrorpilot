#!/usr/bin/env python3
"""Real SIGKILL at transaction checkpoints, isolated to disposable files.

Child sends SIGKILL to itself at a checkpoint. A separate interpreter performs
restart recovery. This does not test a kill inside a filesystem syscall,
physical power loss, or production /etc safety.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
BEFORE = b"[fedora]\nbaseurl=https://old.example.org/\n"
AFTER = b"[fedora]\nbaseurl=https://new.example.org/\n"
CASES = ("PREPARED", "TARGET_REPLACED", "APPLIED")
CHILD = """
import os, signal, sys
from pathlib import Path
from mirrorpilot.durable_sandbox import DurableSandboxTransaction
root = Path(sys.argv[1])
stop = sys.argv[2]
def checkpoint(name):
    if name == stop:
        os.kill(os.getpid(), signal.SIGKILL)
DurableSandboxTransaction(root).apply(
    b"[fedora]\\nbaseurl=https://new.example.org/\\n",
    lambda p: p.read_bytes() == b"[fedora]\\nbaseurl=https://new.example.org/\\n",
    checkpoint=checkpoint,
)
"""
RECOVER = """
import sys
from pathlib import Path
from mirrorpilot.durable_sandbox import DurableSandboxTransaction
print(DurableSandboxTransaction(Path(sys.argv[1])).recover())
"""


def main() -> int:
    if os.geteuid() == 0:
        print("REFUSED: no root or sudo")
        return 2
    with tempfile.TemporaryDirectory(prefix="mirrorpilot-real-kill-") as temp:
        for case in CASES:
            root = Path(temp) / case.lower()
            root.mkdir()
            target = root / "99_mirrorpilot.repo"
            target.write_bytes(BEFORE)
            target.chmod(0o640)
            child = subprocess.run(
                [sys.executable, "-c", CHILD, str(root), case],
                cwd=PROJECT, capture_output=True, text=True, timeout=15,
            )
            if child.returncode != -signal.SIGKILL:
                print(f"{case}: FAIL child exit={child.returncode} stderr={child.stderr[:400]}")
                return 1
            recovery = subprocess.run(
                [sys.executable, "-c", RECOVER, str(root)],
                cwd=PROJECT, capture_output=True, text=True, timeout=15,
            )
            expected = "unchanged" if case == "PREPARED" else "restored"
            status = recovery.stdout.strip()
            ok = (recovery.returncode == 0 and status == expected
                  and target.read_bytes() == BEFORE
                  and (target.stat().st_mode & 0o777) == 0o640
                  and not (root / ".mirrorpilot-transaction.json").exists())
            print(f"{case}: killed_by_SIGKILL=True, recovery={status}, "
                  f"original_restored={target.read_bytes() == BEFORE}, "
                  f"{'PASS' if ok else 'FAIL'}")
            if not ok:
                print("recovery stderr:", recovery.stderr[:500])
                return 1
    print("PASS: all real SIGKILL checkpoint recoveries.")
    print("LIMIT: kills occur between operations, not during write/rename/fsync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
