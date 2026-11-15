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
    """Produce section-scoped values, never a replacement for an entire .repo file.

    A user must inspect effective DNF5 configuration and competing overrides.
    """
    snippet = (
        f"[{plan.repo_id}]\n"
        f"baseurl={plan.proposed_url}\n"
        "metalink=\n"
        "mirrorlist=\n"
    )
    instructions = (
        f"Edit the existing [{plan.repo_id}] section in:\n"
        f"{plan.source_file}\n\n"
        "Copy only the setting lines into the existing section. Do NOT append "
        "a second section header, overwrite the entire file, or paste this "
        "block into a terminal. The header is shown only for context.\n\n"
        "1. Back up the file yourself before editing.\n"
        "2. Inspect Configuration origins for overrides and competing definitions. "
        "If an override takes precedence, editing this source file may have no effect.\n"
        "3. Replace the existing baseurl with the suggested URL; clear or comment "
        "out metalink and mirrorlist in that same section. Preserve all other keys.\n"
        "4. Save in your editor with administrator privileges if necessary, "
        "then use Verify effective settings here.\n"
        "5. If verification fails, restore your backup or inspect the effective "
        "DNF5 configuration. MirrorPilot never writes these files."
    )
    return ManualEdit(plan.source_file, snippet, instructions)


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
