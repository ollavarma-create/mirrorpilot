"""Tests for the manual-only DNF5 configuration guidance."""
from mirrorpilot.changes import build_change_plan
from mirrorpilot.manual_edit import prepare_manual_edit, verify_effective_values


def plan():
    return build_change_plan(
        "updates", "https://old.example.org/fedora/linux/updates/45/Everything/x86_64/",
        "https://new.example.org/fedora/linux/updates/45/Everything/x86_64/",
        "/etc/yum.repos.d/fedora-updates.repo",
        target_release="45", installed_release="45",
    )


def test_manual_command_uses_dnf5_config_manager():
    manual = prepare_manual_edit(plan())
    assert manual.file_path == "/etc/dnf/repos.override.d/99_config_manager.repo" or (
        manual.file_path == "/etc/dnf/repos.override.d/99-config_manager.repo"
    )
    assert manual.snippet == (
        "sudo dnf5 config-manager setopt "
        "'updates.baseurl=https://new.example.org/fedora/linux/updates/$releasever/Everything/$basearch/' "
        "updates.metalink= updates.mirrorlist="
    )
    assert "do not edit" in manual.instructions.lower()
    assert "MirrorPilot does not execute it" in manual.instructions


def test_effective_settings_match_only_with_no_competing_metalink():
    p = plan()
    expected = "https://new.example.org/fedora/linux/updates/$releasever/Everything/$basearch/"
    assert verify_effective_values(p, {"baseurl": expected, "metalink": "", "mirrorlist": ""}, raw_baseurl=expected)[0]
    assert not verify_effective_values(p, {"baseurl": expected, "metalink": "https://other.example.org/", "mirrorlist": ""}, raw_baseurl=expected)[0]
    assert not verify_effective_values(p, {"baseurl": "https://other.example.org/", "metalink": "", "mirrorlist": ""})[0]


def test_instructions_contain_real_newlines_not_literal_escape_sequences():
    manual = prepare_manual_edit(plan())
    assert "\n" in manual.instructions
    assert "\\n" not in manual.instructions
    assert any(line.startswith("1. Inspect") for line in manual.instructions.splitlines())


def test_mismatch_is_informational_and_shows_both_mirrors():
    p = plan()
    ok, message = verify_effective_values(
        p, {"baseurl": "https://old.example.org/fedora/linux/updates/45/Everything/x86_64/", "metalink": "", "mirrorlist": ""}
    )
    assert not ok
    assert "Current configuration differs from recommendation." in message
    assert "Current mirror: https://old.example.org/fedora/linux/updates/45/Everything/x86_64/" in message
    assert "Recommended setting: https://new.example.org/fedora/linux/updates/$releasever/Everything/$basearch/" in message
    assert "No changes have been made by MirrorPilot." in message


def test_expanded_effective_and_saved_template():
    p = plan()
    template = "https://new.example.org/fedora/linux/updates/$releasever/Everything/$basearch/"
    expanded = "https://new.example.org/fedora/linux/updates/45/Everything/x86_64/"
    assert verify_effective_values(p, {"baseurl": expanded, "metalink": "", "mirrorlist": ""}, raw_baseurl=template)[0]
    assert not verify_effective_values(p, {"baseurl": expanded, "metalink": "", "mirrorlist": ""}, raw_baseurl=expanded)[0]
    assert not verify_effective_values(p, {"baseurl": expanded, "metalink": "", "mirrorlist": ""})[0]
