#!/usr/bin/env python3
"""Kill only a Bubblewrap-contained DNF5 process; inspect conservative recovery.

This is an integration experiment, not a deterministic mid-write fault injector.
Never run as root. Host /etc is mounted read-only.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mirrorpilot.dnf_sandbox_transaction import SandboxDNFTransaction, digest


def main() -> int:
    if os.geteuid() == 0:
        print("REFUSED: run without sudo.")
        return 1
    with tempfile.TemporaryDirectory(prefix="mirrorpilot-kill-dnf-") as directory:
        root = Path(directory)
        dnf = root / "etc/dnf"
        overrides = dnf / "repos.override.d"
        repos = root / "etc/yum.repos.d"
        overrides.mkdir(parents=True)
        repos.mkdir(parents=True)
        (dnf / "dnf.conf").write_text("[main]\nreposdir=/etc/yum.repos.d\n")
        (repos / "fixture.repo").write_text(
            "[fedora]\nname=Sandbox Fedora\nenabled=1\n"
            "baseurl=https://base.example.org/fedora/\nmetalink=\n"
            "[updates]\nname=Sandbox Updates\nenabled=1\n"
            "baseurl=https://base.example.org/updates/\nmetalink=\n")
        target = overrides / "99-config_manager.repo"
        target.write_text(
            "# Sandbox fixture\n[fedora]\n"
            "baseurl=https://old.example.org/fedora/\nmetalink=\n\n"
            "[updates]\nbaseurl=https://old.example.org/updates/\nmetalink=\n")
        tx = SandboxDNFTransaction(overrides)
        before = tx.tx._snapshot()
        tx._save({
            "version": 1, "state": "PREPARED",
            "before_hex": before.contents.hex(), "before_mode": before.mode,
            "before_sha256": digest(before.contents), "after_sha256": None,
        })
        command = [
            "bwrap", "--die-with-parent", "--unshare-all", "--share-net",
            "--ro-bind", "/", "/",
            "--bind", str(dnf), "/etc/dnf",
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
        print("Launching isolated DNF5; will SIGKILL only its process group.")
        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True,
            )
        except OSError as error:
            print("Could not launch sandbox:", error)
            return 2
        observed_change = False
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if target.read_bytes() != before.contents:
                observed_change = True
                break
            if process.poll() is not None:
                break
            time.sleep(0.001)
        was_running = process.poll() is None
        if was_running:
            os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=10)
        print("DNF5 exit:", process.returncode)
        print("Observed changed file before kill:", observed_change)
        print("Process still running when kill attempted:", was_running)
        if stderr:
            print("stderr:", stderr[:500])
        after = target.read_bytes()
        print("Original bytes preserved:", after == before.contents)
        print("Journal state:", tx._load()["state"])
        outcome = tx.recover()
        print("Recovery:", outcome)
        if outcome == "conflict-manual-review":
            print("PASS: unknown PREPARED result retained for manual review.")
        elif outcome == "already-original":
            print("PASS: no write observed; unchanged snapshot recovered.")
        else:
            print("UNEXPECTED recovery outcome:", outcome)
            return 3
        if was_running and observed_change:
            print("NOTE: write was observed, but not necessarily interrupted mid-write.")
        elif not was_running:
            print("NOTE: DNF5 finished before kill; this is not a mid-write test.")
        else:
            print("NOTE: kill preceded observed write; this is not a mid-write test.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
