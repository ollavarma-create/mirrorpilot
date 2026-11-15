#!/usr/bin/env python3
"""Probe ABA/identity limitations in disposable sandbox recovery.

Demonstrates whether equal bytes but a different inode are accepted. This is a
diagnostic test, NOT a claim that current recovery is safe against ABA.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mirrorpilot.durable_sandbox import DurableSandboxTransaction

BEFORE = b"[fedora]\nbaseurl=https://old.example.org/\n"
AFTER = b"[fedora]\nbaseurl=https://new.example.org/\n"


def scenario(checkpoint: str, replacement: bytes) -> bool:
    with tempfile.TemporaryDirectory(prefix="mirrorpilot-aba-") as temp:
        root = Path(temp)
        target = root / "99_mirrorpilot.repo"
        target.write_bytes(BEFORE)
        target.chmod(0o640)
        tx = DurableSandboxTransaction(root)

        def stop(name: str) -> None:
            if name == checkpoint:
                raise SystemExit("simulated crash")

        try:
            tx.apply(AFTER, lambda path: path.read_bytes() == AFTER, checkpoint=stop)
        except SystemExit:
            pass
        else:
            raise AssertionError("Checkpoint did not fire")

        old_ino = target.stat().st_ino
        replacement_path = root / "external-replacement"
        replacement_path.write_bytes(replacement)
        replacement_path.chmod(0o640)
        os.replace(replacement_path, target)
        new_ino = target.stat().st_ino
        if old_ino == new_ino:
            raise RuntimeError("Inode identity did not change; inconclusive")
        try:
            result = DurableSandboxTransaction(root).recover()
        except (RuntimeError, ValueError) as exc:
            result = "REFUSED: " + str(exc)
        preserved = target.read_bytes() == replacement and target.stat().st_ino == new_ino
        journal = tx.journal.exists()
        print(f"{checkpoint}, replacement={'BEFORE' if replacement == BEFORE else 'AFTER'}: "
              f"inode_changed=True, recovery={result}, "
              f"external_inode_preserved={preserved}, journal_retained={journal}")
        return preserved and journal


def main() -> int:
    if os.geteuid() == 0:
        print("REFUSED: do not run as root")
        return 2
    outcomes = [
        scenario("PREPARED", BEFORE),
        scenario("TARGET_REPLACED", AFTER),
        scenario("APPLIED", AFTER),
    ]
    if all(outcomes):
        print("PASS: all same-content inode substitutions were rejected.")
        return 0
    print("EXPECTED VULNERABILITY DETECTED: content-only recovery does not protect inode identity.")
    print("Do not enable privileged writes. This probe intentionally reports a security gap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
