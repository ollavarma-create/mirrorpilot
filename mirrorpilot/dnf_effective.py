"""Read DNF5's effective repository options without downloading metadata.

Uses dnf5's own --dump-repo-config interface. The command is read-only,
but a subprocess is bounded by a timeout and repository IDs are validated.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess

REPO_ID_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
IMPORTANT = ("enabled", "baseurl", "metalink", "mirrorlist", "fastestmirror",
             "gpgcheck", "proxy", "ip_resolve", "skip_if_unavailable")


@dataclass(frozen=True)
class EffectiveConfig:
    repo_id: str
    values: dict[str, str]


def parse_dump(repo_id: str, output: str) -> EffectiveConfig:
    if not REPO_ID_PATTERN.fullmatch(repo_id):
        raise ValueError("Invalid repository ID")
    header = f'======== "{repo_id}" repository configuration: ========'
    lines = output.splitlines()
    if not lines or lines[0].strip() != header:
        raise ValueError("Unexpected DNF5 configuration output header")
    values: dict[str, str] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        if "=" not in line:
            # DNF5 may print unset options as a bare key (e.g. mirrorlist).
            key = line.strip()
            value = ""
        else:
            key, value = (part.strip() for part in line.split("=", 1))
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            raise ValueError("Unexpected DNF5 configuration field")
        if key in values:
            raise ValueError("Duplicate DNF5 configuration field")
        values[key] = value
    if "enabled" not in values:
        raise ValueError("DNF5 configuration lacks enabled field")
    return EffectiveConfig(repo_id, values)


def read_effective_config(repo_id: str, *, timeout: float = 8) -> EffectiveConfig:
    if not isinstance(repo_id, str) or not REPO_ID_PATTERN.fullmatch(repo_id):
        raise ValueError("Invalid repository ID")
    try:
        result = subprocess.run(
            ["dnf5", f"--dump-repo-config={repo_id}"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Unable to query DNF5: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"DNF5 configuration query failed: {result.stderr.strip()[:500]}")
    return parse_dump(repo_id, result.stdout)


def format_effective_comparison(report, effective: EffectiveConfig) -> str:
    """One consolidated explanation; never infer precedence from file order."""
    lines = [
        f"Configuration explained — [{report.repo_id}]",
        "",
        "DNF5 effective values (read-only)",
        "These are the settings DNF5 actually resolves, not a network health check.",
        "",
    ]
    for key in IMPORTANT:
        if key not in effective.values:
            continue
        actual = effective.values[key]
        lines.append(f"{key} = {actual!r}")
        finding = next((f for f in report.findings if f.key == key), None)
        if finding is None or not finding.occurrences:
            lines.append("  No explicit definition found in inspected repository files.")
            lines.append("")
            continue
        for origin in finding.occurrences:
            lines.append(f"  {origin.layer}: {origin.path}")
            lines.append(f"    declared: {origin.value!r}")
        if len(finding.occurrences) > 1:
            lines.append("  Multiple definitions found; DNF5 effective value is authoritative.")
        elif "$" in finding.occurrences[0].value:
            lines.append("  DNF5 may expand variables in the effective value.")
        lines.append("")
    lines.extend([
        "Interpretation:",
        "  DNF5 values are confirmed for this invocation.",
        "  Source-file precedence cannot be proven solely from these values.",
        "  A deliberately empty metalink may disable the default source.",
        "  Configuration validity does not establish mirror availability.",
        "  No changes or automatic repair are performed.",
    ])
    # Preserve meaningful file-inspection warnings, but not stale disclaimers
    # saying effective DNF5 values were never checked.
    for warning in report.warnings:
        if warning.startswith("This view shows file-level evidence"):
            continue
        if warning.startswith("Multiple source mechanisms are configured."):
            continue
        lines.append(f"  File inspection: {warning}")
    return "\n".join(lines)
