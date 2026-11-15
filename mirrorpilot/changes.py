"""Read-only change planning for a future privileged DNF5 helper.

This module never writes to system paths. Preview targets are *not* an
authorization to write: a future privileged helper must independently
revalidate all inputs and policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import re

from mirrorpilot.repos import _version

ALLOWED_REPOS = frozenset({"fedora", "updates"})
OVERRIDE_PATH = Path("/etc/dnf/repos.override.d/99_mirrorpilot.repo")
_REPO_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


@dataclass(frozen=True)
class ChangePlan:
    repo_id: str
    current_url: str
    proposed_url: str
    source_file: str
    target_file: str
    preview: str
    warnings: tuple[str, ...]
    installed_release: str
    target_release: str


def validate_mirror_url(url: str) -> str:
    """Accept only a concrete HTTPS mirror directory URL, not DNF expressions."""
    if not isinstance(url, str) or len(url) > 2048 or url != url.strip():
        raise ValueError("Invalid mirror URL")
    parts = urlsplit(url)
    if (parts.scheme != "https" or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.query or parts.fragment
            or parts.port not in (None, 443) or "\\" in url
            or any(ord(ch) < 33 or ord(ch) == 127 for ch in url)
            or "$" in url or "%" in url):
        raise ValueError("Expected a concrete HTTPS mirror directory without credentials or variables")
    host = parts.hostname
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Local addresses are not valid mirror targets")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("Non-public mirror addresses are not permitted")
    if not parts.path.endswith("/") or "/../" in parts.path or "/./" in parts.path:
        raise ValueError("Mirror URL must be a directory without path traversal")
    return url


def release_change_allowed(installed_release: str, target_release: str) -> bool:
    """Fail closed unless both releases are known, numeric and identical."""
    return (
        isinstance(installed_release, str)
        and isinstance(target_release, str)
        and bool(re.fullmatch(r"[0-9]{1,3}", installed_release))
        and installed_release == target_release
    )


def build_change_plan(repo_id: str, current_url: str, proposed_url: str,
                      source_file: str, *, target_release: str,
                      installed_release: str | None = None) -> ChangePlan:
    """Describe a change, without writing a file or granting permissions."""
    installed = _version() if installed_release is None else installed_release
    if not release_change_allowed(installed, target_release):
        raise ValueError(
            f"Release mismatch: installed Fedora {installed}, diagnostic Fedora "
            f"{target_release}. Diagnostics are permitted, but configuration "
            "changes for another release are blocked. Use Fedora's official "
            "system-upgrade procedure."
        )
    if not _REPO_ID.fullmatch(repo_id) or repo_id not in ALLOWED_REPOS:
        raise ValueError("Only Fedora release and updates are supported")
    proposed = validate_mirror_url(proposed_url)
    if current_url == proposed:
        raise ValueError("Proposed mirror is already configured")
    if not source_file.startswith("/etc/yum.repos.d/"):
        raise ValueError("Unexpected source configuration path")
    if Path(source_file).name != source_file.removeprefix("/etc/yum.repos.d/"):
        raise ValueError("Invalid source configuration path")
    preview = f"[{repo_id}]\nbaseurl={proposed}\nmetalink=\nmirrorlist=\n"
    return ChangePlan(
        repo_id=repo_id, current_url=current_url or "(not configured)",
        proposed_url=proposed, source_file=source_file,
        target_file=str(OVERRIDE_PATH), preview=preview,
        installed_release=installed, target_release=target_release,
        warnings=(
            "Preview only: nothing has been written or backed up.",
            "A privileged helper must verify DNF5 precedence and the exact existing override before applying.",
            "Backup, authorization, atomic replacement, validation and rollback are required before enabling Apply.",
        ),
    )


def format_change_plan(plan: ChangePlan) -> str:
    return (
        f"PREVIEW ONLY — no changes applied\n"
        f"Repository: {plan.repo_id}\n"
        f"Current: {plan.current_url}\n"
        f"Proposed: {plan.proposed_url}\n"
        f"Configured in: {plan.source_file}\n"
        f"Planned override: {plan.target_file}\n\n"
        f"Proposed override section:\n{plan.preview}\n"
        + "\n".join(f"• {warning}" for warning in plan.warnings)
    )
