import hashlib
from mirrorpilot import audit

def _metalink(digest):
    return (f'<metalink xmlns="urn:ietf:params:xml:ns:metalink">'
            f'<files><file name="repomd.xml"><hash type="sha256">{digest}</hash>'
            f'</file></files></metalink>').encode()

def test_reference_hash():
    digest = hashlib.sha256(b"hello").hexdigest()
    assert audit.reference_hash(_metalink(digest)) == ("sha256", digest)

def test_reference_missing_or_malformed():
    assert audit.reference_hash(b"<metalink/>") is None
    assert audit.reference_hash(_metalink("not-a-hash")) is None

def test_matching_mirror_index(monkeypatch):
    manifest = b"<repomd/>"
    digest = hashlib.sha256(manifest).hexdigest()
    calls = []
    def fake(url, limit):
        calls.append(url)
        return _metalink(digest) if "metalink?" in url else manifest
    monkeypatch.setattr(audit, "_download", fake)
    result = audit.audit("https://example.org/fedora/", "EE", "45")
    assert result.status == "index-match"
    assert len(calls) == 2

def test_different_mirror_index(monkeypatch):
    def fake(url, limit):
        return _metalink(hashlib.sha256(b"<repomd/>").hexdigest()) if "metalink?" in url else b"<repomd changed='yes'/>"
    monkeypatch.setattr(audit, "_download", fake)
    assert audit.audit("https://example.org/fedora/", "EE", "45").status == "different"

def test_reject_invalid_without_network(monkeypatch):
    monkeypatch.setattr(audit, "_download", lambda *args: (_ for _ in ()).throw(AssertionError("network")))
    assert audit.audit("http://example.org/fedora/", "EE", "45").status == "unsupported"
    assert audit.audit("https://example.org/fedora/", "RU", "45").status == "unsupported"

def _manifest(href="repodata/primary.xml.zck", content=b"valid"):
    digest = hashlib.sha256(content).hexdigest()
    return (f'<repomd xmlns="http://linux.duke.edu/metadata/repo">'
            f'<data type="primary"><location href="{href}"/>'
            f'<checksum type="sha256">{digest}</checksum></data></repomd>').encode()

def test_metadata_verified(monkeypatch):
    monkeypatch.setattr(audit, "_download", lambda *args: _manifest())
    monkeypatch.setattr(audit, "_fetch", lambda *args: b"valid")
    result = audit.audit_referenced("https://example.org/fedora/", "EE", "45")
    assert result.status == "metadata-match"
    assert "primary" in result.message

def test_metadata_checksum_mismatch(monkeypatch):
    monkeypatch.setattr(audit, "_download", lambda *args: _manifest())
    monkeypatch.setattr(audit, "_fetch", lambda *args: b"wrong")
    assert audit.audit_referenced("https://example.org/fedora/", "EE", "45").status == "checksum-mismatch"

def test_metadata_404(monkeypatch):
    from urllib.error import HTTPError
    monkeypatch.setattr(audit, "_download", lambda *args: _manifest())
    def missing(*args):
        raise HTTPError(args[0], 404, "Not Found", {}, None)
    monkeypatch.setattr(audit, "_fetch", missing)
    result = audit.audit_referenced("https://example.org/fedora/", "EE", "45")
    assert result.status == "missing"
    assert "404" in result.message

def test_metadata_too_large(monkeypatch):
    monkeypatch.setattr(audit, "_download", lambda *args: _manifest())
    def too_large(*args):
        raise RuntimeError("Metadata exceeds safety size limit")
    monkeypatch.setattr(audit, "_fetch", too_large)
    assert audit.audit_referenced("https://example.org/fedora/", "EE", "45").status == "too-large"

def test_metadata_unsafe_path_no_fetch(monkeypatch):
    monkeypatch.setattr(audit, "_download", lambda *args: _manifest("repodata/../bad"))
    monkeypatch.setattr(audit, "_fetch", lambda *args: (_ for _ in ()).throw(AssertionError("unsafe fetch")))
    assert audit.audit_referenced("https://example.org/fedora/", "EE", "45").status == "error"
