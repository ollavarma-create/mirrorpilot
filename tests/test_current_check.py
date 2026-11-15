from mirrorpilot import diagnostics as d
from mirrorpilot.audit import AuditResult


def test_current_only_never_discovers_or_benchmarks(monkeypatch):
    monkeypatch.setattr(d, "benchmark", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("benchmark called")))
    monkeypatch.setattr(d, "probe", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("probe called")))
    monkeypatch.setattr(d, "audit", lambda *a, **kw: AuditResult("index-match", "matches", a[0]))
    monkeypatch.setattr(d, "audit_referenced", lambda *a, **kw: AuditResult("metadata-match", "three checked", a[0]))
    rows = d.check_current_repository("45", "updates", "https://example.org/updates/45/")
    assert len(rows) == 1
    assert rows[0].health == "verified"
    assert rows[0].speed.mbps is None


def test_current_only_404_is_problem_not_success(monkeypatch):
    monkeypatch.setattr(d, "audit", lambda *a, **kw: AuditResult("missing", "repomd.xml: HTTP 404", a[0]))
    monkeypatch.setattr(d, "audit_referenced", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("metadata called")))
    rows = d.check_current_repository("45", "updates", "https://example.org/updates/45/")
    assert rows[0].health == "error"
    assert "404" in rows[0].speed.detail


def test_current_only_without_supported_base_is_empty():
    assert d.check_current_repository("45", "updates", None) == []


def test_current_only_different_index_is_not_verified(monkeypatch):
    monkeypatch.setattr(d, "audit", lambda *a, **kw: AuditResult("different", "hash differs", a[0]))
    monkeypatch.setattr(d, "audit_referenced", lambda *a, **kw: AuditResult("metadata-match", "three checked", a[0]))
    rows = d.check_current_repository("45", "updates", "https://example.org/updates/45/")
    assert rows[0].health == "problem"
