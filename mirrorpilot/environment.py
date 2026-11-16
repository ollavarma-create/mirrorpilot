"""Read-only environment validation before creating the main window."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class EnvironmentCheck:
    supported: bool
    message: str = ""


def check_environment(os_release: str | None = None, *, timeout: float = 5) -> EnvironmentCheck:
    """Require Fedora and a working dnf5 binary; never change system state."""
    if os_release is None:
        try:
            os_release = Path("/etc/os-release").read_text(encoding="utf-8")
        except OSError:
            return EnvironmentCheck(False, "Cannot read /etc/os-release to identify the operating system.")
    values = {}
    for line in os_release.splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    if values.get("ID", "").lower() != "fedora":
        name = values.get("PRETTY_NAME") or values.get("ID") or "Unknown Linux distribution"
        return EnvironmentCheck(False, f"Unsupported operating system: {name}.\nMirrorPilot requires Fedora Linux with DNF5.")
    executable = shutil.which("dnf5")
    if not executable:
        return EnvironmentCheck(False, "DNF5 was not found. MirrorPilot requires a working dnf5 installation.")
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return EnvironmentCheck(False, "DNF5 version check timed out.")
    except OSError as exc:
        return EnvironmentCheck(False, f"Could not execute DNF5: {exc}")
    if result.returncode != 0:
        return EnvironmentCheck(False, f"DNF5 version check failed (exit code {result.returncode}).")
    if "dnf5" not in (result.stdout + result.stderr).lower():
        return EnvironmentCheck(False, "DNF5 returned an unexpected version response.")
    return EnvironmentCheck(True)
