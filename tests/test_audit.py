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
    assert "country=" not in calls[0]

def test_global_country_audit_and_configured_metadata(monkeypatch):
    manifest = b"<repomd/>"
    digest = hashlib.sha256(manifest).hexdigest()
    def fake(url, limit):
        return _metalink(digest) if "metalink?" in url else manifest
    monkeypatch.setattr(audit, "_download", fake)
    assert audit.audit("https://example.org/fedora/", "BR", "45").status == "index-match"
    assert audit.audit("https://example.org/fedora/", "Configured", "45").status == "index-match"


def test_different_mirror_index(monkeypatch):
    def fake(url, limit):
        return _metalink(hashlib.sha256(b"<repomd/>").hexdigest()) if "metalink?" in url else b"<repomd changed='yes'/>"
    monkeypatch.setattr(audit, "_download", fake)
    assert audit.audit("https://example.org/fedora/", "EE", "45").status == "different"

def test_reject_invalid_without_network(monkeypatch):
    monkeypatch.setattr(audit, "_download", lambda *args: (_ for _ in ()).throw(AssertionError("network")))
    assert audit.audit("http://example.org/fedora/", "EE", "45").status == "unsupported"
    assert audit.audit("https://example.org/fedora/", "R1", "45").status == "unsupported"

def _manifest(href="repodata/primary.xml.zck", content=b"valid", size=None):
    digest = hashlib.sha256(content).hexdigest()
    size_xml = f"<size>{size}</size>" if size is not None else ""
    return (f'<repomd xmlns="http://linux.duke.edu/metadata/repo">'
            f'<data type="primary"><location href="{href}"/>'
            f'<checksum type="sha256">{digest}</checksum>{size_xml}</data></repomd>').encode()

def test_metadata_verified(monkeypatch):
    monkeypatch.setattr(audit, "_download", lambda *args: _manifest(size=5))
    monkeypatch.setattr(audit, "_hash_stream", lambda *args: (hashlib.sha256(b"valid").hexdigest(), 5))
    events = []
    result = audit.audit_referenced("https://example.org/fedora/", "EE", "45", progress=lambda *args: events.append(args))
    assert result.status == "metadata-match"
    assert audit.audit_referenced("https://example.org/fedora/", "Configured", "45").status == "metadata-match"
    assert events[0] == ("primary", 1, 1, 0, 5)

def test_metadata_checksum_mismatch(monkeypatch):
    monkeypatch.setattr(audit, "_download", lambda *args: _manifest())
    monkeypatch.setattr(audit, "_hash_stream", lambda *args: ("0" * 64, 5))
    assert audit.audit_referenced("https://example.org/fedora/", "EE", "45").status == "checksum-mismatch"

def test_metadata_404(monkeypatch):
    from urllib.error import HTTPError
    monkeypatch.setattr(audit, "_download", lambda *args: _manifest())
    def missing(*args):
        raise HTTPError(args[0], 404, "Not Found", {}, None)
    monkeypatch.setattr(audit, "_hash_stream", missing)
    assert audit.audit_referenced("https://example.org/fedora/", "EE", "45").status == "missing"

def test_metadata_too_large(monkeypatch):
    monkeypatch.setattr(audit, "_download", lambda *args: _manifest(size=audit.MAX_FILE_BYTES + 1))
    monkeypatch.setattr(audit, "_hash_stream", audit._hash_stream)
    assert audit.audit_referenced("https://example.org/fedora/", "EE", "45").status == "too-large"

def test_metadata_unsafe_path_no_fetch(monkeypatch):
    monkeypatch.setattr(audit, "_download", lambda *args: _manifest("repodata/../bad"))
    monkeypatch.setattr(audit, "_hash_stream", lambda *args: (_ for _ in ()).throw(AssertionError("unsafe fetch")))
    assert audit.audit_referenced("https://example.org/fedora/", "EE", "45").status == "error"

class FakeResponse:
    status = 200
    headers = {}
    def __init__(self, payload):
        self.payload = payload
        self.offset = 0
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, count):
        chunk = self.payload[self.offset:self.offset + count]
        self.offset += len(chunk)
        return chunk

class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
    def open(self, *args, **kwargs):
        return FakeResponse(self.payload)

def test_streaming_digest_and_chunk_progress(monkeypatch):
    data = b"abcd" * 200
    monkeypatch.setattr(audit, "CHUNK_BYTES", 128)
    monkeypatch.setattr(audit, "build_opener", lambda *args: FakeOpener(data))
    progress = []
    digest, count = audit._hash_stream("https://example.org/file", "sha256", len(data),
                                      lambda *args: progress.append(args))
    assert digest == hashlib.sha256(data).hexdigest()
    assert count == len(data)
    assert len(progress) > 1
    assert progress[-1] == (len(data), len(data))

def test_streaming_size_limit_without_content_length(monkeypatch):
    monkeypatch.setattr(audit, "MAX_FILE_BYTES", 10)
    monkeypatch.setattr(audit, "CHUNK_BYTES", 4)
    monkeypatch.setattr(audit, "build_opener", lambda *args: FakeOpener(b"12345678901"))
    import pytest
    with pytest.raises(audit.MetadataLimitExceeded):
        audit._hash_stream("https://example.org/file", "sha256", None)

def test_declared_size_rejected_before_network(monkeypatch):
    monkeypatch.setattr(audit, "build_opener", lambda *args: (_ for _ in ()).throw(AssertionError("network")))
    import pytest
    with pytest.raises(audit.MetadataLimitExceeded):
        audit._hash_stream("https://example.org/file", "sha256", audit.MAX_FILE_BYTES + 1)
