import pytest
from mirrorpilot.changes import build_change_plan, format_change_plan, validate_mirror_url, release_change_allowed


def test_preview_is_pure_and_shows_config_manager(tmp_path):
    source = "/etc/yum.repos.d/fedora.repo"
    plan = build_change_plan("updates", "https://old.example.org/updates/45/",
                             "https://new.example.org/updates/45/", source, target_release="45", installed_release="45")
    assert plan.target_file == "/etc/dnf/repos.override.d/99-config_manager.repo"
    assert "dnf5 config-manager setopt updates.baseurl=https://new.example.org/updates/45/" in plan.preview
    assert "updates.metalink= updates.mirrorlist=" in plan.preview
    assert "PREVIEW ONLY" in format_change_plan(plan)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("bad", [
    "http://example.org/fedora/", "https://user:secret@example.org/fedora/",
    "https://example.org/fedora/?x=1", "https://example.org/fedora/#fragment",
    "https://example.org/$releasever/", "https://example.org/fedora/\nfoo=bar",
    "https://localhost/fedora/", "https://127.0.0.1/fedora/",
    "https://example.org/fedora/../updates/", "https://example.org/fedora",
])
def test_reject_unsafe_mirror_urls(bad):
    with pytest.raises(ValueError):
        validate_mirror_url(bad)


def test_reject_unmanaged_repositories_and_paths():
    with pytest.raises(ValueError):
        build_change_plan("vscode", "", "https://example.org/repo/", "/etc/yum.repos.d/vscode.repo", target_release="45", installed_release="45")
    with pytest.raises(ValueError):
        build_change_plan("updates", "", "https://example.org/repo/", "/tmp/test.repo", target_release="45", installed_release="45")
    with pytest.raises(ValueError):
        build_change_plan("updates", "", "https://example.org/repo/", "/etc/yum.repos.d/../evil.repo", target_release="45", installed_release="45")


def test_noop_is_rejected():
    with pytest.raises(ValueError, match="already configured"):
        build_change_plan("fedora", "https://example.org/fedora/",
                          "https://example.org/fedora/", "/etc/yum.repos.d/fedora.repo", target_release="45", installed_release="45")


@pytest.mark.parametrize("installed,target,allowed", [
    ("44", "44", True), ("45", "45", True),
    ("44", "45", False), ("45", "44", False),
    ("", "45", False), ("unknown", "45", False),
    ("44", "rawhide", False), ("44", "", False),
])
def test_release_policy(installed, target, allowed):
    assert release_change_allowed(installed, target) is allowed


def test_cross_release_change_plan_is_blocked():
    with pytest.raises(ValueError, match="Release mismatch"):
        build_change_plan(
            "updates", "https://old.example.org/updates/44/",
            "https://new.example.org/updates/45/",
            "/etc/yum.repos.d/fedora-updates.repo",
            target_release="45", installed_release="44"
        )


def test_preview_does_not_propose_competing_fragment():
    plan = build_change_plan(
        "fedora", "https://old.example.org/fedora/44/",
        "https://new.example.org/fedora/44/",
        "/etc/yum.repos.d/fedora.repo", target_release="44", installed_release="44",
    )
    output = format_change_plan(plan)
    assert "99_mirrorpilot.repo" not in output
    assert "DNF5-managed override" in output
    assert "config-manager setopt" in output
    assert "PREVIEW ONLY" in output
