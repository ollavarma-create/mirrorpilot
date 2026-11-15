import hashlib
from mirrorpilot import check


def test_reject_http():
    assert check.check_baseurl("http://example.org").status == "unsupported"


def test_check_valid(monkeypatch):
    contents = b"metadata"
    digest = hashlib.sha256(contents).hexdigest()
    manifest = (
        f'<repomd xmlns="http://linux.duke.edu/metadata/repo">'
        f'<data><location href="repodata/primary.xml"/>'
        f'<checksum type="sha256">{digest}</checksum></data></repomd>'
    ).encode()
    monkeypatch.setattr(
        check, "_fetch",
        lambda url, limit: manifest if url.endswith("repomd.xml") else contents,
    )
    assert check.check_baseurl("https://example.org/repo/").status == "ok"


def test_check_corrupted(monkeypatch):
    manifest = (
        b'<repomd xmlns="http://linux.duke.edu/metadata/repo">'
        b'<data><location href="repodata/file"/>'
        b'<checksum type="sha256">bad</checksum></data></repomd>'
    )
    monkeypatch.setattr(
        check, "_fetch",
        lambda url, limit: manifest if url.endswith("repomd.xml") else b"wrong",
    )
    assert check.check_baseurl("https://example.org/repo").status == "invalid"
