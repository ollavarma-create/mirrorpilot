#!/usr/bin/env python3
"""Sandbox-only hybrid experiment: DNF5 renders, atomic transaction installs.

No sudo, no production paths, no Polkit. Checkpoint exceptions simulate process
death, not physical power loss. Uses a separate staging fixture and target.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mirrorpilot.durable_sandbox import DurableSandboxTransaction


def main() -> int:
    if os.geteuid() == 0:
        print("REFUSED: do not run as root")
        return 2
    if not shutil.which("bwrap") or not shutil.which("dnf5"):
        print("INCONCLUSIVE: bwrap and dnf5 required")
        return 2
    original = (b"# Original fixture\n[fedora]\n"
                b"baseurl=https://old.example.org/fedora/\nmetalink=\n\n"
                b"[updates]\nbaseurl=https://old.example.org/updates/\nmetalink=\n")
    with tempfile.TemporaryDirectory(prefix="mirrorpilot-hybrid-") as directory:
        root = Path(directory)
        stage = root / "stage"
        dnf = stage / "etc/dnf"
        override = dnf / "repos.override.d"
        repos = stage / "etc/yum.repos.d"
        override.mkdir(parents=True)
        repos.mkdir(parents=True)
        (dnf / "dnf.conf").write_text("[main]\nreposdir=/etc/yum.repos.d\n")
        (repos / "fixture.repo").write_text(
            "[fedora]\nname=Fedora sandbox\nenabled=1\n"
            "baseurl=https://base.example.org/fedora/\nmetalink=\n"
            "[updates]\nname=Updates sandbox\nenabled=1\n"
            "baseurl=https://base.example.org/updates/\nmetalink=\n")
        (override / "99-config_manager.repo").write_bytes(original)
        command = [
            "bwrap", "--die-with-parent", "--unshare-all", "--share-net",
            "--ro-bind", "/", "/", "--bind", str(dnf), "/etc/dnf",
            "--bind", str(repos), "/etc/yum.repos.d",
            "--tmpfs", "/run", "--tmpfs", "/tmp",
            "--proc", "/proc", "--dev-bind", "/dev", "/dev",
            "--setenv", "HOME", "/tmp", "--",
            "dnf5", "--config=/etc/dnf/dnf.conf", "--releasever=44",
            "--setopt=reposdir=/etc/yum.repos.d",
            "config-manager", "setopt",
            "fedora.baseurl=https://new.example.org/fedora/",
            "fedora.metalink=",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print("INCONCLUSIVE: DNF5 staging failed:", exc)
            return 2
        if result.returncode:
            print("INCONCLUSIVE: DNF5 staging failed:", result.stderr[:500])
            return 2
        prepared = (override / "99-config_manager.repo").read_bytes()
        if (prepared == original
                or b"https://new.example.org/fedora/" not in prepared
                or b"https://old.example.org/updates/" not in prepared):
            print("FAIL: invalid DNF5 staging output")
            return 1
        print("Staged DNF5 SHA256:", hashlib.sha256(prepared).hexdigest())
        print("Staging is separate from installation directory.")
        cases = ("PREPARED", "TARGET_REPLACED", "APPLIED", "SUCCESS", "VERIFY_FAILURE")
        for case in cases:
            destination = root / ("install-" + case.lower())
            destination.mkdir()
            target = destination / "99_mirrorpilot.repo"
            target.write_bytes(original)
            target.chmod(0o640)
            tx = DurableSandboxTransaction(destination)
            # DurableSandboxTransaction's target is 99_mirrorpilot.repo.
            def checkpoint(name: str) -> None:
                if name == case:
                    raise SystemExit("simulated process death at " + name)
            def verify(path: Path) -> bool:
                return case != "VERIFY_FAILURE" and path.read_bytes() == prepared
            try:
                tx.apply(prepared, verify, checkpoint=checkpoint)
            except SystemExit:
                # Simulates a fresh process using only durable journal state.
                pass
            except RuntimeError:
                if case != "VERIFY_FAILURE":
                    raise
            restarted = DurableSandboxTransaction(destination)
            status = restarted.recover()
            expected = prepared if case == "SUCCESS" else original
            actual = target.read_bytes()
            mode = target.stat().st_mode & 0o777
            ok = actual == expected and mode == 0o640
            if case == "SUCCESS":
                ok = ok and status == "verified"
                restarted.clear_verified()
            else:
                ok = ok and status in ("restored", "unchanged", "clean")
            print(f"{case}: recovery={status}, bytes_correct={actual == expected}, "
                  f"mode={oct(mode)}, journal_cleared={not restarted.journal.exists()}, "
                  f"{'PASS' if ok else 'FAIL'}")
            if not ok:
                return 1
        print("PASS: all sandbox hybrid scenarios completed.")
        print("LIMIT: simulated process termination, not power-loss durability.")
        print("LIMIT: no concurrent writer, adversarial pathname swaps or SELinux/ACL checks.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
