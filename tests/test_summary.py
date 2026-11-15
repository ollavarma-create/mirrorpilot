from mirrorpilot.summary import summary_lines
from mirrorpilot.diagnostics import MirrorHealth
from mirrorpilot.speed import MirrorResult
from mirrorpilot.audit import AuditResult


def row(country, status="measured", detail="", mbps=100, index="index-match", metadata="metadata-match"):
    speed = MirrorResult("https://example.org/repo/", country, status, 20, mbps, 1024, detail)
    idx = AuditResult(index, "index detail", speed.url) if index else None
    meta = AuditResult(metadata, "metadata detail", speed.url) if metadata else None
    return MirrorHealth(speed, idx, meta)


def test_unavailable_current_and_verified_alternative():
    rows = [
        row("Configured", status="error", detail="HTTP Error 404: Not Found", mbps=None, index=None, metadata=None),
        row("EE", mbps=284.9),
        row("DK", mbps=145, index="different", metadata=None),
        row("SE", mbps=120, metadata=None),
    ]
    lines = summary_lines(rows, "45", "updates")
    assert len(lines) == 3
    assert "HTTP 404" in lines[0]
    assert "EE" in lines[1] and "284.9" in lines[1]
    assert "1 problems" in lines[2]
    assert "1 not fully checked" in lines[2]


def test_verified_current_does_not_require_replacement():
    lines = summary_lines([row("Configured"), row("EE", metadata=None)], "44", "fedora")
    assert "no integrity issue detected" in lines[0]
    assert "none established" in lines[1]


def test_absent_configured_source_not_called_healthy():
    lines = summary_lines([row("EE")], "45", "updates")
    assert "not tested" in lines[0]
    assert "EE" in lines[1]


def test_timeout_distinguished_from_404():
    lines = summary_lines([row("Configured", status="error", detail="The read operation timed out", mbps=None)], "45", "updates")
    assert "timed out" in lines[0]
    assert "404" not in lines[0]
