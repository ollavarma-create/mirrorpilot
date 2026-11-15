"""Concise, user-facing summary of read-only repository diagnostics."""
from mirrorpilot.diagnostics import fastest_verified


def summary_lines(rows, release, repo, current=None, configured_url=None):
    if current is None:
        current = next((r for r in rows if r.speed.country == "Configured"), None)
    if current is None:
        current_line = ("Current source: configured HTTPS URL detected; not tested (use Check current)"
                        if configured_url else
                        "Current source: not tested (no supported configured HTTPS base URL)")
    elif current.speed.status != "measured":
        detail = current.speed.detail
        if "404" in detail:
            current_line = "Current source: unavailable (HTTP 404)"
        elif "timed out" in detail.lower():
            current_line = "Current source: timed out (retry recommended)"
        else:
            current_line = "Current source: check failed (see Details)"
    elif current.health == "verified":
        current_line = "Current source: checked metadata OK; no integrity issue detected"
    elif current.index and current.index.status == "different":
        current_line = "Current source: index differs from Fedora reference (see Details)"
    else:
        current_line = f"Current source: {current.health} (see Details)"

    alternatives = [r for r in rows if r.speed.country != "Configured"]
    winner = fastest_verified(alternatives)
    if winner:
        alternative_line = (f"Verified alternative: {winner.speed.country} — "
                            f"{winner.speed.mbps:.1f} Mbit/s (checked metadata)")
    else:
        alternative_line = "Verified alternative: none established"

    other_problems = sum(r.health in ("problem", "error") for r in alternatives)
    inconclusive = sum(r.health == "uncertain" for r in alternatives)
    unchecked = sum(r.health == "unchecked" for r in alternatives)
    current_problem = int(current is not None and current.health in ("problem", "error"))
    total_problems = other_problems + current_problem
    findings_line = (f"Findings: {total_problems} problems (current: {current_problem}, alternatives: {other_problems}) · "
                     f"{inconclusive} inconclusive · "
                     f"{unchecked} not fully checked (Fedora {release} {repo})")
    return current_line, alternative_line, findings_line
