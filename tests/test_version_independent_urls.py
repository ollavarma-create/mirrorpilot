import pytest
from mirrorpilot.changes import build_change_plan, persistent_mirror_url
from mirrorpilot.manual_edit import prepare_manual_edit, verify_effective_values


def test_updates_template_and_command():
    url = "https://mirror.23m.com/fedora/linux/updates/44/Everything/x86_64/"
    plan = build_change_plan("updates", "https://old.example.org/", url,
        "/etc/yum.repos.d/fedora-updates.repo", target_release="44", installed_release="44")
    template = "https://mirror.23m.com/fedora/linux/updates/$releasever/Everything/$basearch/"
    assert persistent_mirror_url("updates", url, "44") == template
    assert f"'updates.baseurl={template}'" in prepare_manual_edit(plan).snippet
    assert verify_effective_values(plan, {"baseurl": template, "metalink": "", "mirrorlist": ""})[0]
    assert not verify_effective_values(plan, {"baseurl": url, "metalink": "", "mirrorlist": ""})[0]


def test_release_repo_template():
    url = "https://example.org/fedora/linux/releases/44/Everything/x86_64/os/"
    assert persistent_mirror_url("fedora", url, "44") == (
        "https://example.org/fedora/linux/releases/$releasever/Everything/$basearch/os/"
    )


@pytest.mark.parametrize("url", [
    "https://example.org/custom/44/x86_64/",
    "https://example.org/fedora/linux/updates/45/Everything/x86_64/",
    "https://example.org/fedora/linux/updates/44/Everything/x86_64/repodata/",
])
def test_unknown_layout_fails_closed(url):
    with pytest.raises(ValueError, match="expected Fedora repository layout"):
        persistent_mirror_url("updates", url, "44")
