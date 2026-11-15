#!/usr/bin/env python3
"""Deterministic TOCTOU demonstration against the identity-aware sandbox prototype.

The recovery worker checks the target inode, pauses, then replaces it. A second
process replaces the target during the pause. Disposable temp files only.
This intentionally demonstrates a vulnerability; it does not fix it.
"""
from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from test_identity_aware_sandbox import AFTER, BEFORE, identity, setup

EXTERNAL = b"[fedora]\nbaseurl=https://external.example.org/\n"


def worker(root_name, pipe):
    root = Path(root_name)
    target = root / "target.repo"
    journal = root / "journal.json"
    try:
        import json
        record = json.loads(journal.read_text())
        checked = identity(target)
        if checked != tuple(record["after"]):
            pipe.send(("unexpected_identity",))
            return
        pipe.send(("checked", checked))
        if pipe.recv() != "continue":
            return
        restored = root / "restore.tmp"
        restored.write_bytes(bytes.fromhex(record["backup_hex"]))
        restored.chmod(record["before"][2])
        with restored.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(restored, target)
        journal.unlink()
        pipe.send(("restored",))
    except Exception as exc:
        pipe.send(("error", repr(exc)))
    finally:
        pipe.close()


def main():
    if os.geteuid() == 0:
        print("REFUSED: do not run as root")
        return 2
    with tempfile.TemporaryDirectory(prefix="mirrorpilot-toctou-") as directory:
        root = Path(directory)
        target, staged, journal = setup(root)
        os.replace(staged, target)
        ctx = mp.get_context("spawn")
        parent, child = ctx.Pipe()
        process = ctx.Process(target=worker, args=(str(root), child))
        process.start()
        child.close()
        try:
            if not parent.poll(10):
                raise RuntimeError("worker did not reach identity check")
            checked = parent.recv()
            if checked[0] != "checked":
                raise RuntimeError(f"worker failed: {checked}")
            attacker = root / "external.repo"
            attacker.write_bytes(EXTERNAL)
            attacker.chmod(0o640)
            os.replace(attacker, target)
            external_identity = identity(target)
            parent.send("continue")
            if not parent.poll(10):
                raise RuntimeError("worker did not finish")
            outcome = parent.recv()
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join()
                raise RuntimeError("worker hung")
            overwritten = target.read_bytes() == BEFORE and identity(target) != external_identity
            print(f"CHECKED: recovery observed its own staged inode, PASS")
            print(f"ATTACK: external replacement inode installed, PASS")
            print(f"RESUME: worker={outcome[0]}, external_change_overwritten={overwritten}, journal_retained={journal.exists()}")
            if outcome[0] == "restored" and overwritten and not journal.exists():
                print("EXPECTED VULNERABILITY DETECTED: identity check and os.replace are not atomic.")
                print("LIMIT: controlled pause demonstrates one interleaving; no production writer or /etc touched.")
                return 0
            print("INCONCLUSIVE: expected unsafe interleaving not observed.")
            return 1
        finally:
            parent.close()
            if process.is_alive():
                process.terminate()
            process.join()


if __name__ == "__main__":
    raise SystemExit(main())
