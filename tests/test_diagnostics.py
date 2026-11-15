from mirrorpilot import diagnostics as d
from mirrorpilot.speed import MirrorResult
from mirrorpilot.audit import AuditResult

def speed(url, mbps=100, status="measured"):
    return MirrorResult(url, "EE", status, 20, mbps, 1024, "sample")

def check(status):
    return AuditResult(status, status, "https://example.org/")

def test_health_requires_both_checks():
    s = speed("https://example.org/")
    assert d.MirrorHealth(s).health == "unchecked"
    assert d.MirrorHealth(s, check("index-match")).health == "unchecked"
    assert d.MirrorHealth(s, check("index-match"), check("metadata-match")).health == "verified"
    assert d.MirrorHealth(s, check("different"), check("metadata-match")).health == "problem"
    assert d.MirrorHealth(s, check("index-match"), check("too-large")).health == "uncertain"
    assert d.MirrorHealth(speed("https://bad/", status="error")).health == "error"

def test_recommendation_requires_verification():
    quick = d.MirrorHealth(speed("https://quick/", 300), check("index-match"))
    slower = d.MirrorHealth(speed("https://safe/", 180), check("index-match"), check("metadata-match"))
    assert d.fastest_verified([quick]) is None
    assert d.fastest_verified([quick, slower]) is slower

def test_pipeline_only_streams_fastest_matching_mirror(monkeypatch):
    speeds = [speed("https://fast/", 200), speed("https://slow/", 100)]
    monkeypatch.setattr(d, "benchmark", lambda release, repo, progress: speeds)
    monkeypatch.setattr(d, "audit", lambda base, country, release, repo: check("index-match"))
    calls = []
    def metadata(base, country, release, progress):
        calls.append(base)
        return check("metadata-match")
    monkeypatch.setattr(d, "audit_referenced", metadata)
    events = []
    rows = d.run_diagnostics("45", progress=lambda *args: events.append(args))
    assert calls == ["https://fast/"]
    assert [r.health for r in rows] == ["verified", "unchecked"]
    assert any(event[0] == "index" for event in events)

def test_bad_index_never_gets_recommended(monkeypatch):
    monkeypatch.setattr(d, "benchmark", lambda release, repo, progress: [speed("https://bad/", 300)])
    monkeypatch.setattr(d, "audit", lambda *args, **kwargs: check("different"))
    monkeypatch.setattr(d, "audit_referenced", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not fetch")))
    rows = d.run_diagnostics("45")
    assert rows[0].health == "problem"
    assert d.fastest_verified(rows) is None

def test_metadata_count_bounds():
    import pytest
    with pytest.raises(ValueError):
        d.run_diagnostics("45", metadata_count=9)

def test_updates_repo_passed_to_benchmark_and_audit(monkeypatch):
    called = []
    def fake_benchmark(release, repo, progress):
        called.append(("benchmark", release, repo))
        return [speed("https://updates.example/", 200)]
    def fake_audit(base, country, release, repo):
        called.append(("audit", release, repo))
        return check("different")
    monkeypatch.setattr(d, "benchmark", fake_benchmark)
    monkeypatch.setattr(d, "audit", fake_audit)
    rows = d.run_diagnostics("45", repo="updates")
    assert rows[0].health == "problem"
    assert called == [("benchmark", "45", "updates"), ("audit", "45", "updates")]

def test_unknown_repo_rejected():
    import pytest
    with pytest.raises(ValueError):
        d.run_diagnostics("45", repo="nonexistent")

def test_gui_worker_positional_args_with_keyword_progress(monkeypatch):
    """Worker passes release, metadata count, repo positionally and progress by keyword."""
    monkeypatch.setattr(d, "benchmark", lambda release, repo, progress: [])
    events = []
    result = d.run_diagnostics("45", 1, "updates", progress=lambda *args: events.append(args))
    assert result == []
    assert events == []

def test_index_timeout_does_not_abort_other_mirrors(monkeypatch):
    monkeypatch.setattr(d, "benchmark", lambda release, repo, progress: [
        speed("https://slow/", 200), speed("https://good/", 100)])
    def index(base, country, release, repo):
        if "slow" in base:
            raise TimeoutError("The read operation timed out")
        return check("index-match")
    monkeypatch.setattr(d, "audit", index)
    monkeypatch.setattr(d, "audit_referenced", lambda *args, **kwargs: check("metadata-match"))
    rows = d.run_diagnostics("45", repo="updates")
    assert rows[0].health == "uncertain"
    assert rows[0].index.status == "timeout"
    assert rows[1].health == "verified"
    assert d.fastest_verified(rows) is rows[1]

def test_metadata_timeout_keeps_index_results(monkeypatch):
    monkeypatch.setattr(d, "benchmark", lambda release, repo, progress: [speed("https://slow/", 200)])
    monkeypatch.setattr(d, "audit", lambda *args, **kwargs: check("index-match"))
    def fail(*args, **kwargs):
        raise TimeoutError("The read operation timed out")
    monkeypatch.setattr(d, "audit_referenced", fail)
    rows = d.run_diagnostics("45", repo="updates")
    assert rows[0].index.status == "index-match"
    assert rows[0].metadata.status == "error"
    assert rows[0].health == "uncertain"

def test_mirror_search_excludes_configured_even_if_url_given(monkeypatch):
    monkeypatch.setattr(d, "probe", lambda *args: (_ for _ in ()).throw(
        AssertionError("configured source must not be probed")))
    monkeypatch.setattr(d, "benchmark", lambda release, repo, progress:
                        [speed("https://alternative/", 200)])
    monkeypatch.setattr(d, "audit", lambda *args, **kwargs: check("index-match"))
    monkeypatch.setattr(d, "audit_referenced", lambda *args, **kwargs: check("metadata-match"))
    rows = d.run_diagnostics("45", 1, "updates", "https://funet.example/updates/45/")
    assert len(rows) == 1
    assert rows[0].speed.country == "EE"
    assert rows[0].health == "verified"

def test_http_404_explained_without_claiming_full_repository_missing():
    row = d.MirrorHealth(d.MirrorResult(
        "https://funet.example/updates/45/", "Configured", "error", None, None, 0,
        "HTTP Error 404: Not Found"))
    explanation = d.explain_source(row)
    assert "HTTP 404" in explanation
    assert "repodata/repomd.xml" in explanation
    assert "or a referenced metadata file" in explanation
    assert row.health == "error"

def test_timeout_not_presented_as_permanent_failure():
    row = d.MirrorHealth(d.MirrorResult(
        "https://funet.example/", "Configured", "error", None, None, 0,
        "The read operation timed out"))
    assert "retry" in d.explain_source(row)

def test_no_configured_source_not_misreported_healthy():
    assert "not" in d.explain_source(None).lower()
