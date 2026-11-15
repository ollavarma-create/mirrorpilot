#!/usr/bin/env python3
"""Read-only discovery before testing DNF5 config-manager writes.

Do not execute config-manager setopt until write destinations are isolated.
An installroot alone is NOT treated as proof that host override files are safe.
"""
from __future__ import annotations

import shutil
import subprocess


def probe(label: str, command: list[str]) -> None:
    print(f"\n=== {label} ===")
    print("$", " ".join(command))
    result = subprocess.run(command, capture_output=True, text=True,
                            timeout=15, check=False)
    print("exit:", result.returncode)
    print((result.stdout or "<empty stdout>")[:6000])
    if result.stderr:
        print("stderr:", result.stderr[:1500])


def main() -> int:
    if not shutil.which("dnf5"):
        print("dnf5 not found")
        return 1
    probe("config-manager command help", ["dnf5", "config-manager", "--help"])
    probe("setopt help", ["dnf5", "config-manager", "setopt", "--help"])
    print("\nSandbox availability (no changes made):")
    for name in ("bwrap", "unshare", "podman"):
        print(f"  {name}: {shutil.which(name) or 'not installed'}")
    print("\nNo setopt operation was executed. Host configuration unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
