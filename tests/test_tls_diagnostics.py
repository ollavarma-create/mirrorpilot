"""Tests for safe headless TLS diagnostics."""
from unittest.mock import patch
from mirrorpilot import tls_diagnostics


def test_diagnostic_lines_report_paths_and_environment():
    lines = tls_diagnostics.diagnostic_lines()
    assert any(line.startswith("OpenSSL: ") for line in lines)
    assert any(line.startswith("Default CA file: ") for line in lines)
    assert any(line.startswith("CA candidate ") for line in lines)


def test_probe_success(capsys):
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    with patch.object(tls_diagnostics, "urlopen", return_value=Response()) as opener:
        assert tls_diagnostics.main() == 0
    opener.assert_called_once_with(tls_diagnostics.PROBE_URL, timeout=10)
    assert "HTTPS result: HTTP 200" in capsys.readouterr().out


def test_probe_failure(capsys):
    with patch.object(tls_diagnostics, "urlopen", side_effect=OSError("unavailable")):
        assert tls_diagnostics.main() == 1
    assert "HTTPS result: OSError: unavailable" in capsys.readouterr().out
