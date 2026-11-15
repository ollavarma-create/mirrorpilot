import pytest
from mirrorpilot.changes import build_change_plan, format_change_plan, validate_mirror_url


def test_preview_is_pure_and_shows_override(tmp_path):
    source = "/etc/yum.repos.d/fedora.repo"
    plan = build_change_plan("updates", "https://old.example.org/updates/45/",
                             "https://new.example.org/updates/45/", source)
    assert plan.target_file == "/etc/dnf/repos.override.d/99_mirrorpilot.repo"
    assert "[updates]\nbaseurl=https://new.example.org/updates/45/\n" in plan.preview
    assert "metalink=\nmirrorlist=\n" in plan.preview
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
        build_change_plan("vscode", "", "https://example.org/repo/", "/etc/yum.repos.d/vscode.repo")
    with pytest.raises(ValueError):
        build_change_plan("updates", "", "https://example.org/repo/", "/tmp/test.repo")
    with pytest.raises(ValueError):
        build_change_plan("updates", "", "https://example.org/repo/", "/etc/yum.repos.d/../evil.repo")


def test_noop_is_rejected():
    with pytest.raises(ValueError, match="already configured"):
        build_change_plan("fedora", "https://example.org/fedora/",
                          "https://example.org/fedora/", "/etc/yum.repos.d/fedora.repo")
