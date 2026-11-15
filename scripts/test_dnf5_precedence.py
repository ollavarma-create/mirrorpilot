#!/usr/bin/env python3
"""Isolated, read-only DNF5 repository override precedence experiment.

Creates only temporary files. Never uses --use-host-config, sudo or pkexec.
The experiment reports observed effective values; it does not enable Apply.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile


def _run(root: Path, label: str, *, override_a: str | None = None,
         override_b: str | None = None) -> tuple[int, str, str]:
    config = root / "etc/dnf/dnf.conf"
    repo_dir = root / "etc/yum.repos.d"
    override_dir = root / "etc/dnf/repos.override.d"
    repo_dir.mkdir(parents=True, exist_ok=True)
    override_dir.mkdir(parents=True, exist_ok=True)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[main]\nreposdir=/etc/yum.repos.d\n", encoding="utf-8")
    (repo_dir / "test.repo").write_text(
        "[mirrorpilot-precedence-test]\n"
        "name=MirrorPilot isolated precedence test\n"
        "enabled=1\n"
        "baseurl=https://base.example.org/fedora/44/\n"
        "metalink=https://base.example.org/metalink\n",
        encoding="utf-8",
    )
    for filename, value in (
        ("90-mirrorpilot.repo", override_a),
        ("99-config_manager.repo", override_b),
    ):
        target = override_dir / filename
        if value is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(
                "[mirrorpilot-precedence-test]\n"
                f"baseurl={value}\nmetalink=\n",
                encoding="utf-8",
            )
    args = [
        "dnf5", f"--installroot={root}", f"--config={config}",
        "--releasever=44", "--setopt=reposdir=/etc/yum.repos.d",
        "--dump-repo-config=mirrorpilot-precedence-test",
    ]
    env = os.environ.copy()
    # DNF5 should not use user-specific configuration for this test.
    env["HOME"] = str(root)
    result = subprocess.run(
        args, cwd=root, env=env, capture_output=True, text=True,
        timeout=15, check=False,
    )
    print(f"\n=== {label} ===")
    if result.returncode:
        print(f"DNF5 exit code: {result.returncode}")
        print(result.stderr.strip()[:1500])
    for line in result.stdout.splitlines():
        if line.startswith(("baseurl =", "metalink =", "mirrorlist =", "enabled =")):
            print(line)
    return result.returncode, result.stdout, result.stderr


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mirrorpilot-dnf5-precedence-") as directory:
        root = Path(directory)
        cases = (
            ("base only", None, None),
            ("90 only", "https://ninety.example.org/fedora/44/", None),
            ("99 only", None, "https://ninetynine.example.org/fedora/44/"),
            ("90 then 99", "https://ninety.example.org/fedora/44/",
             "https://ninetynine.example.org/fedora/44/"),
        )
        for label, a, b in cases:
            try:
                _run(root, label, override_a=a, override_b=b)
            except (OSError, subprocess.TimeoutExpired) as exc:
                print(f"{label}: experiment failed: {exc}")
                return 1
    print("\nThis experiment is observational only. No system configuration was changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
