from pathlib import Path

from mirrorpilot.changes import build_change_plan
from mirrorpilot.config_conflicts import ConfigReport, SettingFinding, SettingOrigin
from mirrorpilot.dnf_effective import EffectiveConfig
from mirrorpilot.write_preflight import assess_write_preflight, format_write_preflight


def _plan():
    return build_change_plan(
        "fedora", "https://old.example.org/fedora/44/",
        "https://new.example.org/fedora/44/",
        "/etc/yum.repos.d/fedora.repo", target_release="44", installed_release="44",
    )


def test_unmanaged_override_blocks_even_with_matching_dnf_values(tmp_path):
    report = ConfigReport("fedora", (
        SettingFinding("baseurl", (
            SettingOrigin("/etc/dnf/repos.override.d/99-config_manager.repo",
                          "https://old.example.org/fedora/$releasever/",
                          "override fragment"),
        ), "single definition"),
    ), ())
    effective = EffectiveConfig("fedora", {
        "baseurl": "https://old.example.org/fedora/44/", "enabled": "1",
    })
    result = assess_write_preflight(
        _plan(), report, effective, override_dir=tmp_path,
    )
    assert not result.allowed
    assert any("99-config_manager.repo" in reason for reason in result.reasons)
    assert "WRITE BLOCKED" in format_write_preflight(result)


def test_missing_effective_config_blocks(tmp_path):
    result = assess_write_preflight(
        _plan(), ConfigReport("fedora", (), ()), None, override_dir=tmp_path,
    )
    assert not result.allowed
    assert any("could not be established" in reason for reason in result.reasons)


def test_mismatched_effective_config_blocks(tmp_path):
    result = assess_write_preflight(
        _plan(), ConfigReport("fedora", (), ()),
        EffectiveConfig("fedora", {"baseurl": "https://other.example.org/", "enabled": "1"}),
        override_dir=tmp_path,
    )
    assert not result.allowed
    assert any("differs" in reason for reason in result.reasons)


def test_no_conflicts_still_blocks_until_privileged_writer_is_ready(tmp_path):
    result = assess_write_preflight(
        _plan(), ConfigReport("fedora", (), ()),
        EffectiveConfig("fedora", {"baseurl": "https://old.example.org/fedora/44/", "enabled": "1"}),
        override_dir=tmp_path,
    )
    assert not result.allowed
    assert any("privileged writer" in reason for reason in result.reasons)
