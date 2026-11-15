from mirrorpilot.config_conflicts import inspect_configuration, format_config_report


def test_distinguishes_override_from_base_file(tmp_path):
    base, overrides = tmp_path / "repos", tmp_path / "overrides"
    base.mkdir()
    overrides.mkdir()
    (base / "fedora.repo").write_text(
        "[fedora]\nbaseurl=https://example.org/default/\nmetalink=https://example.org/list\n"
    )
    (overrides / "99_custom.repo").write_text(
        "[fedora]\nbaseurl=https://example.org/custom/\nmetalink=\n"
    )
    report = inspect_configuration("fedora", base, overrides)
    baseurl = next(item for item in report.findings if item.key == "baseurl")
    assert baseurl.classification == "different definitions — precedence unconfirmed"
    assert len(baseurl.occurrences) == 2
    assert "override fragment" in format_config_report(report)
    assert any("Multiple source mechanisms" in w for w in report.warnings)


def test_identical_repeated_definition_is_not_called_conflict(tmp_path):
    base, overrides = tmp_path / "repos", tmp_path / "overrides"
    base.mkdir()
    overrides.mkdir()
    (base / "a.repo").write_text("[updates]\nenabled=1\n")
    (overrides / "b.repo").write_text("[updates]\nenabled=1\n")
    report = inspect_configuration("updates", base, overrides)
    enabled = next(item for item in report.findings if item.key == "enabled")
    assert enabled.classification == "repeated identical definition"


def test_missing_repo_reports_uncertainty(tmp_path):
    base, overrides = tmp_path / "repos", tmp_path / "overrides"
    base.mkdir()
    overrides.mkdir()
    report = inspect_configuration("fedora", base, overrides)
    assert any("not found" in warning for warning in report.warnings)


def test_malformed_file_is_reported_not_silently_ignored(tmp_path):
    base, overrides = tmp_path / "repos", tmp_path / "overrides"
    base.mkdir()
    overrides.mkdir()
    (base / "broken.repo").write_text("this is not ini")
    report = inspect_configuration("fedora", base, overrides)
    assert any("Could not parse" in warning for warning in report.warnings)


def test_other_repo_is_not_misattributed(tmp_path):
    base, overrides = tmp_path / "repos", tmp_path / "overrides"
    base.mkdir()
    overrides.mkdir()
    (base / "fedora.repo").write_text("[fedora]\nbaseurl=https://example.org/\n")
    (overrides / "other.repo").write_text("[updates]\nbaseurl=https://other.org/\n")
    report = inspect_configuration("fedora", base, overrides)
    assert "other.org" not in format_config_report(report)


def test_default_origins_include_fedora45_packaged_repos(tmp_path, monkeypatch):
    from mirrorpilot import repos
    system_dir, local_dir, overrides = (tmp_path / name for name in ("system", "local", "overrides"))
    for directory in (system_dir, local_dir, overrides):
        directory.mkdir()
    (system_dir / "fedora.repo").write_text("[fedora]\nmetalink=https://example.org/list\n")
    (overrides / "custom.repo").write_text("[fedora]\nmetalink=\n")
    monkeypatch.setattr(repos, "SYSTEM_REPO_DIR", system_dir)
    monkeypatch.setattr(repos, "_DEFAULT_REPO_DIR", local_dir)
    monkeypatch.setattr(repos, "REPO_DIR", local_dir)
    monkeypatch.setattr(repos, "OVERRIDE_DIR", overrides)
    report = inspect_configuration("fedora")
    metalink = next(item for item in report.findings if item.key == "metalink")
    assert len(metalink.occurrences) == 2
    assert metalink.occurrences[0].path == str(system_dir / "fedora.repo")
