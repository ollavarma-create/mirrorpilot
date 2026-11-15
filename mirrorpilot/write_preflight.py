"""Fail-closed assessment before any future privileged DNF5 write.

This module never writes. A GUI preview is not a grant of authority.
In particular, competing override fragments must be resolved with a
controlled DNF5 precedence test before any privileged helper is enabled.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mirrorpilot.changes import ChangePlan, OVERRIDE_PATH
from mirrorpilot.config_conflicts import ConfigReport
from mirrorpilot.dnf_effective import EffectiveConfig


@dataclass(frozen=True)
class WritePreflight:
    allowed: bool
    reasons: tuple[str, ...]


def assess_write_preflight(plan: ChangePlan, report: ConfigReport,
                           effective: EffectiveConfig | None,
                           *, override_dir: Path = Path("/etc/dnf/repos.override.d"),
                           target_path: Path = OVERRIDE_PATH) -> WritePreflight:
    """Conservatively refuse unknown precedence and unmanaged overrides.

    'allowed' currently remains False: there is no production-safe privileged
    writer, filesystem confinement or recovery procedure yet.
    """
    reasons: list[str] = []
    if report.repo_id != plan.repo_id or (effective and effective.repo_id != plan.repo_id):
        reasons.append("Repository identity mismatch.")
    if effective is None:
        reasons.append("DNF5 effective configuration could not be established.")
    else:
        actual = effective.values.get("baseurl", "")
        if not actual or actual != plan.current_url:
            reasons.append("Current DNF5 baseurl differs from the change preview.")
        if effective.values.get("enabled") != "1":
            reasons.append("Repository is not enabled according to DNF5.")
    if not target_path.is_absolute() or target_path != OVERRIDE_PATH:
        reasons.append("Unexpected managed target path.")
    for finding in report.findings:
        for origin in finding.occurrences:
            if origin.layer != "override fragment":
                continue
            # We must not infer precedence from a lexical filename order.
            if Path(origin.path) != target_path:
                reason = f"Unmanaged override defines {finding.key}: {origin.path}"
                if reason not in reasons:
                    reasons.append(reason)
    if target_path.is_symlink():
        reasons.append("Managed target is a symlink.")
    elif target_path.exists():
        reasons.append("Existing managed target requires an ownership and content audit.")
    if not reasons:
        reasons.append("No production-safe privileged writer or verified DNF5 precedence policy is installed.")
    return WritePreflight(False, tuple(reasons))


def format_write_preflight(result: WritePreflight) -> str:
    return ("WRITE BLOCKED — configuration unchanged\n"
            + "\n".join(f"• {reason}" for reason in result.reasons))
