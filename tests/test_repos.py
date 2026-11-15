import pytest
from mirrorpilot.repos import parse_repo_info, get_repositories


SAMPLE = """Repo-id            : fedora
Repo-name          : Fedora 44 - x86_64
Repo-status        : enabled
Repo-baseurl       : https://example.org/releases/44/x86_64/
Repo-filename      : /etc/yum.repos.d/fedora.repo

Repo-id            : updates
Repo-name          : Fedora Updates
Repo-status        : enabled
Repo-baseurl       : https://example.org/updates/44/x86_64/
Repo-filename      : /etc/yum.repos.d/fedora-updates.repo
"""


def test_parse_repos():
    repos = parse_repo_info(SAMPLE)
    assert len(repos) == 2
    assert repos[0].repo_id == "fedora"
    assert repos[1].source.endswith("/44/x86_64/")


def test_reject_unsafe_version():
    with pytest.raises(ValueError):
        get_repositories("45; invalid")
