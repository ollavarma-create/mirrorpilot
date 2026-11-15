"""Tests for the manual-only DNF5 configuration guidance."""
from mirrorpilot.changes import build_change_plan
from mirrorpilot.manual_edit import prepare_manual_edit, verify_effective_values


def plan():
    return build_change_plan(
        "updates", "https://old.example.org/updates/45/",
        "https://new.example.org/updates/45/",
        "/etc/yum.repos.d/fedora-updates.repo",
        target_release="45", installed_release="45",
    )


def test_manual_snippet_is_section_scoped_and_preserves_other_settings():
    manual = prepare_manual_edit(plan())
    assert manual.file_path == "/etc/yum.repos.d/fedora-updates.repo"
    assert manual.snippet == (
        "[updates]\nbaseurl=https://new.example.org/updates/45/\n"
        "metalink=\nmirrorlist=\n"
    )
    assert "Do NOT append" in manual.instructions
    assert "override" in manual.instructions.lower()


def test_effective_settings_match_only_with_no_competing_metalink():
    p = plan()
    expected = p.proposed_url
    assert verify_effective_values(p, {"baseurl": expected, "metalink": "", "mirrorlist": ""})[0]
    assert not verify_effective_values(p, {"baseurl": expected, "metalink": "https://other.example.org/", "mirrorlist": ""})[0]
    assert not verify_effective_values(p, {"baseurl": "https://other.example.org/", "metalink": "", "mirrorlist": ""})[0]
