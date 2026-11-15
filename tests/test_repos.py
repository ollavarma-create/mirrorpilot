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


def test_fedora45_packaged_repos_and_local_repos(tmp_path, monkeypatch):
    system_dir, local_dir, overrides = (tmp_path / name for name in ("system", "local", "overrides"))
    for directory in (system_dir, local_dir, overrides):
        directory.mkdir()
    (system_dir / "fedora.repo").write_text(
        "[fedora]\nname=Fedora $releasever\nmetalink=https://example.org/fedora\n"
        "[updates]\nname=Updates\nmetalink=https://example.org/updates\n"
    )
    (local_dir / "vscode.repo").write_text("[code]\nname=VS Code\nbaseurl=https://example.org/code\n")
    monkeypatch.setattr(repos, "SYSTEM_REPO_DIR", system_dir)
    monkeypatch.setattr(repos, "REPO_DIR", repos._DEFAULT_REPO_DIR)
    monkeypatch.setattr(repos, "OVERRIDE_DIR", overrides)
    # Keep the local directory isolated by patching the default-path constant too.
    monkeypatch.setattr(repos, "_DEFAULT_REPO_DIR", local_dir)
    monkeypatch.setattr(repos, "REPO_DIR", local_dir)
    found = repos.get_repositories("45")
    assert {item.repo_id for item in found} == {"fedora", "updates", "code"}
    assert next(item for item in found if item.repo_id == "fedora").filename == str(system_dir / "fedora.repo")
