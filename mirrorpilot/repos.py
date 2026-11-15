"""Read-only DNF5 repository discovery.

Uses DNF's effective configuration rather than separately parsing base
.repo files and override settings, which have different precedence.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import subprocess


@dataclass(frozen=True)
class Repo:
    repo_id: str
    name: str
    status: str
    baseurl: str
    metalink: str
    mirrorlist: str
    filename: str

    @property
    def source(self) -> str:
        return self.baseurl or self.metalink or self.mirrorlist or "(not reported)"


_FIELD = re.compile(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$")


def parse_repo_info(output: str) -> list[Repo]:
    """Parse the English text representation of dnf5 repo info --all."""
    records = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        match = _FIELD.match(line)
        if not match:
            continue
        key, value = match.groups()
        key = key.strip().lower().replace(" ", "-")
        if key == "repo-id":
            if current:
                records.append(current)
            current = {"repo-id": value}
        elif current:
            current[key] = value
    if current:
        records.append(current)
    return [
        Repo(
            repo_id=r["repo-id"],
            name=r.get("repo-name", r["repo-id"]),
            status=r.get("repo-status", r.get("enabled", "unknown")),
            baseurl=r.get("repo-baseurl", ""),
            metalink=r.get("repo-metalink", ""),
            mirrorlist=r.get("repo-mirrorlist", ""),
            filename=r.get("repo-filename", ""),
        )
        for r in records
    ]


def get_repositories(releasever: str | None = None) -> list[Repo]:
    """Read cached DNF5 repository configuration without network refresh."""
    cmd = ["dnf5"]
    if releasever:
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,32}", releasever):
            raise ValueError("Invalid release version")
        cmd.append(f"--releasever={releasever}")
    cmd += ["--cacheonly", "repo", "info", "--all"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=35,
            env={**os.environ, "LC_ALL": "C"}, check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("dnf5 is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("DNF5 timed out") from exc
    if proc.returncode:
        raise RuntimeError((proc.stderr or proc.stdout or "DNF5 failed").strip())
    repos = parse_repo_info(proc.stdout)
    if not repos:
        raise RuntimeError("DNF5 output not recognized; please report this version")
    return repos
