from pathlib import Path
import pytest
from mirrorpilot import repos


def test_offline_repo_and_override(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repos"
    override_dir = tmp_path / "overrides"
    repo_dir.mkdir()
    override_dir.mkdir()
    (repo_dir / "fedora.repo").write_text(
        "[fedora]\nname=Fedora $releasever\nenabled=1\n"
        "metalink=https://example.org/list?release=$releasever\n"
        "[updates]\nname=Updates\nenabled=1\n"
        "metalink=https://example.org/list\n"
    )
    (override_dir / "99.repo").write_text(
        "[updates]\nbaseurl=https://mirror.example.org/$releasever/$basearch/\nmetalink=\n"
    )
    monkeypatch.setattr(repos, "REPO_DIR", repo_dir)
    monkeypatch.setattr(repos, "OVERRIDE_DIR", override_dir)
    result = repos.get_repositories("45")
    assert len(result) == 2
    assert result[0].name == "Fedora 45"
    assert result[1].source == f"https://mirror.example.org/45/{repos.ARCH}/"
    assert result[1].metalink == ""
    assert result[1].raw_baseurl == "https://mirror.example.org/$releasever/$basearch/"


def test_reject_unsafe_version():
    with pytest.raises(ValueError):
        repos.get_repositories("45; invalid")


def test_no_repos(tmp_path, monkeypatch):
    monkeypatch.setattr(repos, "REPO_DIR", tmp_path)
    monkeypatch.setattr(repos, "OVERRIDE_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="No .repo"):
        repos.get_repositories("45")
