from pathlib import Path

from mirrorpilot.changes import build_change_plan
from mirrorpilot.config_conflicts import ConfigReport, SettingFinding, SettingOrigin
from mirrorpilot.dnf_effective import EffectiveConfig
from mirrorpilot.write_preflight import assess_write_preflight, format_write_preflight


def _plan():
    return build_change_plan(
        "fedora", "https://old.example.org/fedora/linux/releases/44/Everything/x86_64/os/",
        "https://new.example.org/fedora/linux/releases/44/Everything/x86_64/os/",
        "/etc/yum.repos.d/fedora.repo", target_release="44", installed_release="44",
    )


def test_dnf_managed_override_is_recognized_but_writes_remain_blocked(tmp_path):
    report = ConfigReport("fedora", (
        SettingFinding("baseurl", (
            SettingOrigin("/etc/dnf/repos.override.d/99-config_manager.repo",
                          "https://old.example.org/fedora/linux/releases/$releasever/Everything/$basearch/os/",
                          "override fragment"),
        ), "single definition"),
    ), ())
    effective = EffectiveConfig("fedora", {
        "baseurl": "https://old.example.org/fedora/linux/releases/44/Everything/x86_64/os/", "enabled": "1",
    })
    result = assess_write_preflight(
        _plan(), report, effective, override_dir=tmp_path,
    )
    assert not result.allowed
    assert not any("Other override" in reason for reason in result.reasons)
    assert any("privileged writer" in reason for reason in result.reasons)
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
        EffectiveConfig("fedora", {"baseurl": "https://old.example.org/fedora/linux/releases/44/Everything/x86_64/os/", "enabled": "1"}),
        override_dir=tmp_path,
    )
    assert not result.allowed
    assert any("privileged writer" in reason for reason in result.reasons)


def test_other_override_is_flagged(tmp_path):
    report = ConfigReport("fedora", (
        SettingFinding("baseurl", (
            SettingOrigin("/etc/dnf/repos.override.d/90-other.repo",
                          "https://other.example.org/fedora/", "override fragment"),
        ), "single definition"),
    ), ())
    effective = EffectiveConfig("fedora", {
        "baseurl": "https://old.example.org/fedora/linux/releases/44/Everything/x86_64/os/", "enabled": "1",
    })
    result = assess_write_preflight(_plan(), report, effective, override_dir=tmp_path)
    assert not result.allowed
    assert any("90-other.repo" in reason for reason in result.reasons)
