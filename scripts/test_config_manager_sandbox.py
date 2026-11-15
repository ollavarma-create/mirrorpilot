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
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mirrorpilot.dnf_sandbox_transaction import SandboxDNFTransaction


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
        tx = SandboxDNFTransaction(override_dir)
        command = prefix + [
            "config-manager", "setopt",
            "fedora.baseurl=https://new.example.org/fedora/",
            "fedora.metalink=",
        ]
        print("=== transaction-managed DNF5 setopt ===")
        def verify_change():
            result = subprocess.run(
                prefix + ["--dump-repo-config=fedora,updates"],
                env=env, text=True, capture_output=True, timeout=25, check=False,
            )
            return (result.returncode == 0
                    and "baseurl = https://new.example.org/fedora/" in result.stdout
                    and "baseurl = https://old.example.org/updates/" in result.stdout)

        try:
            status = tx.apply(command, verify_change)
        except Exception as error:
            print("FAIL: transaction-managed DNF5 write:", error)
            print("Recovery status:", tx.recover())
            return 3
        if status != "verified":
            print("FAIL: unexpected transaction status:", status)
            return 3
        print("PASS: transaction journal VERIFIED and effective values checked.")
        tx.clear_verified()
        after = override.read_bytes()
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
        print("\n=== rollback via setopt ===")
        rollback = run(prefix + [
            "config-manager", "setopt",
            "fedora.baseurl=https://old.example.org/fedora/",
            "fedora.metalink=",
        ], env)
        restored = override.read_bytes()
        if rollback.returncode:
            print("FAIL: rollback command returned an error.")
            return 7
        restored_text = restored.decode(errors="replace")
        if ("[fedora]" not in restored_text or
            "baseurl=https://old.example.org/fedora/" not in restored_text or
            "[updates]" not in restored_text or
            original_updates not in restored_text or
            "baseurl=https://new.example.org/fedora/" in restored_text):
            print("FAIL: rollback did not restore the expected repository values.")
            return 7
        effective_rollback = run(prefix + ["--dump-repo-config=fedora,updates"], env)
        if (effective_rollback.returncode or
            "baseurl = https://old.example.org/fedora/" not in effective_rollback.stdout or
            "baseurl = https://old.example.org/updates/" not in effective_rollback.stdout):
            print("FAIL: effective repository settings were not restored.")
            return 7
        print("PASS: logical rollback restored both effective baseurl values.")
        if restored == before:
            print("PASS: byte-for-byte file restoration.")
        else:
            print("EXPECTED DIFFERENCE: DNF5 normalized the override file.")
            print("Original:", repr(before))
            print("Restored:", repr(restored))
            print("NOTE: exact rollback requires a separate file backup.")

        print("\n=== unsetopt removes only Fedora overrides ===")
        unset = run(prefix + [
            "config-manager", "unsetopt", "fedora.baseurl", "fedora.metalink",
        ], env)
        unset_bytes = override.read_bytes()
        unset_text = unset_bytes.decode(errors="replace")
        print("Override after unsetopt:\n", unset_text)
        if unset.returncode:
            print("INCONCLUSIVE: unsetopt command failed.")
            return 8
        if "[updates]" not in unset_text or original_updates not in unset_text:
            print("FAIL: updates settings changed or disappeared.")
            return 9
        # The effective value must now come from the ordinary .repo file.
        effective = run(prefix + [
            "--dump-repo-config=fedora",
        ], env)
        if effective.returncode or "baseurl = https://base.example.org/fedora/" not in effective.stdout:
            print("FAIL: Fedora did not fall back to the base .repo URL.")
            return 10
        print("PASS: unsetopt restores effective Fedora URL from the .repo file.")

        print("\n=== rejected invalid option must not change overrides ===")
        snapshot = override.read_bytes()
        invalid = run(prefix + [
            "config-manager", "setopt", "fedora.mirrorpilot_nonexistent_option=1",
        ], env)
        after_invalid = override.read_bytes()
        if invalid.returncode == 0:
            print("INCONCLUSIVE: DNF5 unexpectedly accepted an unknown option.")
            return 11
        if after_invalid != snapshot:
            print("FAIL: failed command changed the override file.")
            return 12
        print("PASS: rejected option left the override file unchanged.")
        print("\nPASS: all sandbox scenarios completed; host configuration untouched.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
