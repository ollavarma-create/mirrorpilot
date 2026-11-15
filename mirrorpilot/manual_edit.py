"""Read-only, conservative instructions for user-managed DNF5 repo edits."""
from __future__ import annotations

from dataclasses import dataclass
from mirrorpilot.changes import ChangePlan


@dataclass(frozen=True)
class ManualEdit:
    file_path: str
    snippet: str
    instructions: str


def prepare_manual_edit(plan: ChangePlan) -> ManualEdit:
    """Provide a copyable DNF5 command; the user runs it, not MirrorPilot."""
    command = (
        f"sudo dnf5 config-manager setopt "
        f"{plan.repo_id}.baseurl={plan.proposed_url} "
        f"{plan.repo_id}.metalink= "
        f"{plan.repo_id}.mirrorlist="
    )
    instructions = (
        f"Repository: {plan.repo_id}\n"
        f"Source file (for reference only): {plan.source_file}\n"
        f"DNF5-managed override: {plan.target_file}\n\n"
        "DNF5 config-manager is the recommended method. Do not edit the "
        "distribution's .repo file or the managed override by hand.\n\n"
        "1. Inspect Configuration origins for existing overrides and conflicts.\n"
        "2. Review the exact command below and make your own backup if needed.\n"
        "3. Copy the command and run it yourself in a terminal. It requires "
        "administrator privileges; MirrorPilot does not execute it.\n"
        "4. Click Verify effective settings to compare DNF5-reported values.\n"
        "5. If verification fails, inspect overrides and correct the configuration "
        "using DNF5 config-manager. This is not an automatic rollback."
    )
    return ManualEdit(plan.target_file, command, instructions)


def verify_effective_values(plan: ChangePlan, values: dict[str, str]) -> tuple[bool, str]:
    """Compare DNF5-reported effective values, not just source-file text."""
    base = values.get("baseurl", "").strip()
    metalink = values.get("metalink", "").strip()
    mirrorlist = values.get("mirrorlist", "").strip()
    if base == plan.proposed_url and not metalink and not mirrorlist:
        return True, "DNF5 effective baseurl matches the recommendation; metalink and mirrorlist are empty."
    return False, (
        f"DNF5 effective values do not match.\n"
        f"baseurl: {base or '(empty)'}\n"
        f"metalink: {metalink or '(empty)'}\n"
        f"mirrorlist: {mirrorlist or '(empty)'}"
    )
