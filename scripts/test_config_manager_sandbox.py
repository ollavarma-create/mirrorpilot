#!/usr/bin/env python3
"""Bubblewrap-confined DNF5 config-manager experiment.

All of /etc is read-only except two explicitly mounted temporary directories.
Never run with sudo; host repository configuration is never a write target.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, env=env, text=True, capture_output=True,
                            timeout=25, check=False)
    print("$", " ".join(command[-6:]))
    print("exit:", result.returncode)
    if result.stdout:
        print(result.stdout[:1600])
    if result.stderr:
        print("stderr:", result.stderr[:1600])
    return result


def main() -> int:
    if os.geteuid() == 0:
        print("REFUSED: run as a normal user, not root.")
        return 1
    if not shutil.which("bwrap") or not shutil.which("dnf5"):
        print("SKIP: bwrap or dnf5 not installed")
        return 2
    with tempfile.TemporaryDirectory(prefix="mirrorpilot-config-manager-") as directory:
        root = Path(directory)
        etc = root / "etc"
        repo_dir = etc / "yum.repos.d"
        override_dir = etc / "dnf/repos.override.d"
        repo_dir.mkdir(parents=True)
        override_dir.mkdir(parents=True)
        config = etc / "dnf/dnf.conf"
        config.write_text("[main]\nreposdir=/etc/yum.repos.d\n", encoding="utf-8")
        (repo_dir / "fixture.repo").write_text(
            "[fedora]\nname=Sandbox Fedora\nenabled=1\n"
            "baseurl=https://base.example.org/fedora/\nmetalink=\n"
            "[updates]\nname=Sandbox Updates\nenabled=1\n"
            "baseurl=https://base.example.org/updates/\nmetalink=\n",
            encoding="utf-8",
        )
        override = override_dir / "99-config_manager.repo"
        override.write_text(
            "# Sandbox fixture\n[fedora]\n"
            "baseurl=https://old.example.org/fedora/\nmetalink=\n\n"
            "[updates]\nbaseurl=https://old.example.org/updates/\nmetalink=\n",
            encoding="utf-8",
        )
        original_updates = "baseurl=https://old.example.org/updates/"
        env = os.environ.copy()
        env["HOME"] = str(root)
        # Read-only root filesystem; only the temporary fixture directories writable.
        # /etc/dnf bind-mount also contains the isolated dnf.conf.
        prefix = [
            "bwrap", "--die-with-parent", "--unshare-all",
            "--share-net", "--ro-bind", "/", "/",
            "--bind", str(etc / "dnf"), "/etc/dnf",
            "--bind", str(repo_dir), "/etc/yum.repos.d",
            "--tmpfs", "/run",
            "--tmpfs", "/tmp",
            "--proc", "/proc",
            "--dev-bind", "/dev", "/dev",
            "--setenv", "HOME", "/tmp",
            "--",
            "dnf5", "--config=/etc/dnf/dnf.conf", "--releasever=44",
            "--setopt=reposdir=/etc/yum.repos.d",
        ]
        print("Sandbox write test; no host repository files are writable.")
        before = override.read_bytes()
        result = run(prefix + [
            "config-manager", "setopt",
            "fedora.baseurl=https://new.example.org/fedora/",
            "fedora.metalink=",
        ], env)
        after = override.read_bytes()
        if result.returncode:
            print("INCONCLUSIVE: config-manager command failed.")
            return 3
        print("Sandbox override after setopt:\n", after.decode(errors="replace"))
        if before == after:
            print("INCONCLUSIVE: no change to sandbox override.")
            return 4
        if original_updates not in after.decode(errors="replace"):
            print("FAIL: updates repository baseurl was not preserved.")
            return 5
        if "baseurl=https://new.example.org/fedora/" not in after.decode(errors="replace"):
            print("FAIL: Fedora baseurl was not updated in sandbox override.")
            return 6
        print("PASS: sandbox override changed and updates baseurl preserved.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
