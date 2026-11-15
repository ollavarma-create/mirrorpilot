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
