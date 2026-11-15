#!/usr/bin/env python3
"""Observe DNF5 config-manager writes in an isolated, disposable bwrap fixture.

No sudo, no real /etc writes. Does not prove atomicity under arbitrary crashes.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect(path: Path) -> dict:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise RuntimeError("Unsafe fixture target")
    data = path.read_bytes()
    return {
        "dev": info.st_dev, "ino": info.st_ino, "mode": oct(stat.S_IMODE(info.st_mode)),
        "size": len(data), "sha256": sha(data), "bytes": data,
    }


def run(*, trace: bool = False) -> int:
    if os.geteuid() == 0:
        print("REFUSED: never run as root or with sudo")
        return 2
    if not shutil.which("bwrap") or not shutil.which("dnf5"):
        print("INCONCLUSIVE: requires bwrap and dnf5")
        return 2
    if trace and not shutil.which("strace"):
        print("INCONCLUSIVE: strace is not installed")
        return 2
    with tempfile.TemporaryDirectory(prefix="mirrorpilot-dnf-observe-") as temp:
        root = Path(temp)
        dnf = root / "etc/dnf"
        override = dnf / "repos.override.d"
        repos = root / "etc/yum.repos.d"
        override.mkdir(parents=True)
        repos.mkdir(parents=True)
        (dnf / "dnf.conf").write_text("[main]\nreposdir=/etc/yum.repos.d\n")
        (repos / "fixture.repo").write_text(
            "[fedora]\nname=Sandbox Fedora\nenabled=1\n"
            "baseurl=https://base.example.org/fedora/\nmetalink=\n"
            "[updates]\nname=Sandbox Updates\nenabled=1\n"
            "baseurl=https://base.example.org/updates/\nmetalink=\n"
        )
        target = override / "99-config_manager.repo"
        target.write_text(
            "# Preserve this comment\n[fedora]\n"
            "baseurl=https://old.example.org/fedora/\nmetalink=\n\n"
            "[updates]\nbaseurl=https://old.example.org/updates/\nmetalink=\n"
        )
        target.chmod(0o640)
        before = inspect(target)
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
        tracefile = root / "syscalls.log"
        if trace:
            # Trace the actual DNF5 child through bwrap. -yy annotates file
            # descriptors, making write(fd<...>) attributable to the target.
            command = [
                "strace", "-f", "-yy", "-s", "160",
                "-e", "trace=open,openat,openat2,creat,write,writev,pwrite64,"
                "ftruncate,truncate,rename,renameat,renameat2,unlink,unlinkat,"
                "fsync,fdatasync,close",
                "-o", str(tracefile), "--",
                *command,
            ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print("INCONCLUSIVE:", exc)
            return 2
        print("DNF5 return code:", result.returncode)
        if result.stderr:
            print("stderr:", result.stderr[:1500])
        if trace and tracefile.exists():
            lines = tracefile.read_text(errors="replace").splitlines()
            # Output only operations referring to the isolated DNF target.
            # strace -yy annotates fds, including write/close/ftruncate.
            selected = [
                line for line in lines
                if "99_config_manager.repo" in line
                or "repos.override.d/" in line
            ]
            print("TRACE: target-related syscalls (max 100):")
            for line in selected[:100]:
                print(line.replace(str(root), "<SANDBOX>"))
            if len(selected) > 100:
                print(f"TRACE: omitted {len(selected) - 100} additional lines")
            if not selected:
                print("TRACE: no target-related syscalls captured; inconclusive")
        if result.returncode:
            return 2
        if not target.exists() or target.is_symlink():
            print("FAIL: target missing or symlinked")
            return 1
        after = inspect(target)
        print("Before:", {k: v for k, v in before.items() if k != "bytes"})
        print("After: ", {k: v for k, v in after.items() if k != "bytes"})
        print("Same inode:", (before["dev"], before["ino"]) == (after["dev"], after["ino"]))
        print("Mode preserved:", before["mode"] == after["mode"])
        print("Other repo retained:", b"https://old.example.org/updates/" in after["bytes"])
        print("New URL present:", b"https://new.example.org/fedora/" in after["bytes"])
        print("Diff:")
        for line in difflib.unified_diff(
            before["bytes"].decode(errors="replace").splitlines(),
            after["bytes"].decode(errors="replace").splitlines(),
            fromfile="before", tofile="after", lineterm=""
        ):
            print(line)
        if b"https://old.example.org/updates/" not in after["bytes"] or b"https://new.example.org/fedora/" not in after["bytes"]:
            print("FAIL: unexpected resulting content")
            return 1
        print("PASS: observed one completed sandbox DNF5 write.")
        print("NOTE: inode equality alone does not prove in-place writes or atomicity.")
        if trace:
            print("NOTE: strace shows observed syscalls, not power-loss durability.")
            print("NOTE: absence of fsync in a filtered trace is not proof of no durability.")
        else:
            print("NOTE: use --trace to inspect actual syscalls.")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", action="store_true",
                        help="Trace sandbox DNF5 file operations with strace")
    args = parser.parse_args()
    raise SystemExit(run(trace=args.trace))
