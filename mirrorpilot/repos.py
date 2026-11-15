"""Offline, read-only DNF5 repository configuration discovery.

Parses standard .repo files and DNF5 override fragments. No metadata
cache or network access is required. This is a conservative parser:
complex DNF5 configuration features may need a native libdnf5 backend.
"""
from __future__ import annotations

from dataclasses import dataclass
from configparser import ConfigParser
from pathlib import Path
import os
import re

REPO_DIR = Path("/etc/yum.repos.d")
SYSTEM_REPO_DIR = Path("/usr/share/dnf5/repos.d")
_DEFAULT_REPO_DIR = REPO_DIR


def repository_directories() -> tuple[Path, ...]:
    """Inspect packaged DNF5 repos first, then local repo definitions.

    Preserve the single-directory override used by tests and callers that
    monkeypatch REPO_DIR. File-level ordering is not proof of DNF precedence.
    """
    if REPO_DIR != _DEFAULT_REPO_DIR:
        return (REPO_DIR,)
    return (SYSTEM_REPO_DIR, REPO_DIR)

OVERRIDE_DIR = Path("/etc/dnf/repos.override.d")
VERSION_FILE = Path("/etc/os-release")
ARCH = os.uname().machine


@dataclass(frozen=True)
class Repo:
    repo_id: str
    name: str
    status: str
    baseurl: str
    metalink: str
    mirrorlist: str
    filename: str
    raw_baseurl: str = ""

    @property
    def source(self) -> str:
        return self.baseurl or self.metalink or self.mirrorlist or "(not reported)"


def _read_ini(path: Path) -> ConfigParser:
    config = ConfigParser(interpolation=None, strict=False)
    config.optionxform = str.lower
    with path.open(encoding="utf-8") as stream:
        config.read_file(stream)
    return config


def _version() -> str:
    try:
        content = VERSION_FILE.read_text(encoding="utf-8")
        match = re.search(r'^VERSION_ID=["\']?([^"\'\n]+)', content, re.M)
        return match.group(1) if match else "unknown"
    except OSError:
        return "unknown"


def _expand(value: str, releasever: str) -> str:
    """Expand basic DNF variables without interpreting shell syntax."""
    return (value.replace("${releasever}", releasever)
                 .replace("$releasever", releasever)
                 .replace("${basearch}", ARCH)
                 .replace("$basearch", ARCH)
                 .replace("${arch}", ARCH)
                 .replace("$arch", ARCH))


def get_repositories(releasever: str | None = None) -> list[Repo]:
    if releasever and not re.fullmatch(r"[a-zA-Z0-9_.-]{1,32}", releasever):
        raise ValueError("Invalid release version")
    version = releasever or _version()
    records: dict[str, dict[str, str]] = {}
    origins: dict[str, str] = {}

    for directory in repository_directories():
      for path in sorted(directory.glob("*.repo")):
          try:
              config = _read_ini(path)
          except (OSError, ValueError) as exc:
              raise RuntimeError(f"Unable to read {path}: {exc}") from exc
          for section in config.sections():
              values = dict(config.items(section))
              records.setdefault(section, {}).update(values)
              origins[section] = str(path)

    # DNF5 override fragments have higher priority than .repo entries.
    for path in sorted(OVERRIDE_DIR.glob("*.repo")):
        try:
            config = _read_ini(path)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Unable to read {path}: {exc}") from exc
        for section in config.sections():
            if section in records:
                records[section].update(dict(config.items(section)))

    if not records:
        raise RuntimeError("No .repo files found in inspected DNF5 repository directories")

    return [
        Repo(
            repo_id=repo_id,
            name=_expand(data.get("name", repo_id), version),
            status="enabled" if data.get("enabled", "1").strip().lower() in ("1", "true", "yes") else "disabled",
            baseurl=_expand(data.get("baseurl", ""), version),
            metalink=_expand(data.get("metalink", ""), version),
            mirrorlist=_expand(data.get("mirrorlist", ""), version),
            filename=origins[repo_id],
            raw_baseurl=data.get("baseurl", ""),
        )
        for repo_id, data in sorted(records.items())
    ]
