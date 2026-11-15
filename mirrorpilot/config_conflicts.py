"""Explain repository setting provenance without claiming to emulate libdnf5.

This is a conservative, offline, read-only analysis of .repo fragments.
File order and last-seen values are observations, NOT proof of DNF5
precedence. Compare with libdnf5 before allowing configuration writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from configparser import Error as ConfigParserError
from pathlib import Path

from mirrorpilot import repos

KEYS = ("enabled", "baseurl", "metalink", "mirrorlist", "proxy")


@dataclass(frozen=True)
class SettingOrigin:
    path: str
    value: str
    layer: str


@dataclass(frozen=True)
class SettingFinding:
    key: str
    occurrences: tuple[SettingOrigin, ...]
    classification: str


@dataclass(frozen=True)
class ConfigReport:
    repo_id: str
    findings: tuple[SettingFinding, ...]
    warnings: tuple[str, ...]


def inspect_configuration(repo_id: str, repo_dir: Path | None = None,
                          override_dir: Path | None = None) -> ConfigReport:
    if not isinstance(repo_id, str) or not repo_id or any(ch in repo_id for ch in "[]\n\r"):
        raise ValueError("Invalid repository ID")
    bases = repos.repository_directories() if repo_dir is None else (Path(repo_dir),)
    overrides = repos.OVERRIDE_DIR if override_dir is None else Path(override_dir)
    observed: dict[str, list[SettingOrigin]] = {key: [] for key in KEYS}
    warnings: list[str] = []
    found = False
    layers = [("repository file", directory) for directory in bases]
    layers.append(("override fragment", overrides))
    for layer, directory in layers:
        for path in sorted(directory.glob("*.repo")):
            try:
                config = repos._read_ini(path)
            except (OSError, ValueError, ConfigParserError) as exc:
                warnings.append(f"Could not parse {path}: {exc}")
                continue
            if not config.has_section(repo_id):
                continue
            found = True
            for key in KEYS:
                if config.has_option(repo_id, key):
                    observed[key].append(SettingOrigin(str(path), config.get(repo_id, key), layer))
    if not found:
        warnings.append("Repository section not found in inspected files.")
    findings = []
    for key in KEYS:
        items = tuple(observed[key])
        if len(items) <= 1:
            classification = "single definition" if items else "not explicitly defined"
        elif len({item.value for item in items}) == 1:
            classification = "repeated identical definition"
        else:
            classification = "different definitions — precedence unconfirmed"
        findings.append(SettingFinding(key, items, classification))
    source_keys = [key for key in ("baseurl", "metalink", "mirrorlist")
                   if any(item.value.strip() for item in observed[key])]
    if len(source_keys) > 1:
        warnings.append(
            "Multiple source mechanisms are configured. DNF5's effective selection "
            "must be checked independently; an empty override may intentionally disable one."
        )
    warnings.append(
        "This view shows file-level evidence, not libdnf5's authoritative effective values. "
        "No automatic repair or Apply is permitted based on this report."
    )
    return ConfigReport(repo_id, tuple(findings), tuple(warnings))


def format_config_report(report: ConfigReport) -> str:
    lines = [f"Configuration origins — [{report.repo_id}]", ""]
    for finding in report.findings:
        lines.append(f"{finding.key}: {finding.classification}")
        for item in finding.occurrences:
            lines.append(f"  {item.layer}: {item.path}")
            lines.append(f"    value: {item.value!r}")
    lines.extend(["", "Notes:"])
    lines.extend(f"• {warning}" for warning in report.warnings)
    return "\n".join(lines)
