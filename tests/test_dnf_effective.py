import subprocess

import pytest

from mirrorpilot.dnf_effective import (
    format_effective_comparison, parse_dump, read_effective_config,
)
from mirrorpilot.config_conflicts import ConfigReport


SAMPLE = '''======== "updates" repository configuration: ========
baseurl = https://www.nic.funet.fi/fedora/44/x86_64/
enabled = 1
metalink =
mirrorlist
fastestmirror = 1
gpgcheck = 1
'''


def test_parses_dnf5_dump_and_bare_keys():
    result = parse_dump("updates", SAMPLE)
    assert result.values["baseurl"].endswith("/x86_64/")
    assert result.values["metalink"] == ""
    assert result.values["mirrorlist"] == ""


def test_rejects_other_repo_header():
    with pytest.raises(ValueError, match="header"):
        parse_dump("fedora", SAMPLE)


def test_rejects_duplicate_fields():
    with pytest.raises(ValueError, match="Duplicate"):
        parse_dump("updates", SAMPLE + "enabled = 0\n")


def test_rejects_bad_repo_id():
    with pytest.raises(ValueError):
        read_effective_config("updates; touch /tmp/foo")


def test_runs_dnf5_without_shell(monkeypatch):
    def fake_run(args, **kwargs):
        assert args == ["dnf5", "--dump-repo-config=updates"]
        assert kwargs["timeout"] == 8
        return subprocess.CompletedProcess(args, 0, SAMPLE, "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert read_effective_config("updates").values["enabled"] == "1"


def test_dnf5_error_is_reported(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 1, "", "failure")
    )
    with pytest.raises(RuntimeError, match="failure"):
        read_effective_config("updates")


def test_comparison_labels_effective_value():
    result = parse_dump("updates", SAMPLE)
    rendered = format_effective_comparison(ConfigReport("updates", (), ()), result)
    assert "DNF5 effective values (read-only)" in rendered
    assert "metalink = ''" in rendered


def test_consolidated_report_does_not_repeat_origins_or_stale_disclaimer():
    from mirrorpilot.config_conflicts import SettingFinding, SettingOrigin
    report = ConfigReport(
        "updates",
        (SettingFinding("metalink", (
            SettingOrigin("/etc/yum.repos.d/fedora-updates.repo", "https://example.org/metalink", "repository file"),
            SettingOrigin("/etc/dnf/repos.override.d/99-config_manager.repo", "", "override fragment"),
        ), "different definitions — precedence unconfirmed"),),
        ("This view shows file-level evidence, not libdnf5's authoritative effective values. No automatic repair or Apply is permitted based on this report.",),
    )
    rendered = format_effective_comparison(report, parse_dump("updates", SAMPLE))
    assert rendered.count("/etc/yum.repos.d/fedora-updates.repo") == 1
    assert "effective values were never checked" not in rendered
    assert "This view shows file-level evidence" not in rendered
    assert "Configuration validity does not establish mirror availability" in rendered
