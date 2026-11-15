import pytest
from mirrorpilot import speed

def _xml(*urls):
    return ("<metalink><files><file><resources>" +
            "".join(f"<url>{u}</url>" for u in urls) +
            "</resources></file></files></metalink>").encode()

def test_country_list_and_repo(monkeypatch):
    seen = []
    def fake(url, limit, ranged=False):
        seen.append(url)
        return _xml("https://mirror.example/fedora/repodata/repomd.xml")
    monkeypatch.setattr(speed, "_download", fake)
    assert speed.discover("45") == ["https://mirror.example/fedora/"]
    assert "country=FI%2CSE%2CEE%2CDE%2CNL%2CDK" in seen[0]
    assert "fedora-45" in seen[0]

def test_dedup_https_only():
    assert speed.parse_metalink(_xml(
        "http://bad.example/r/repodata/repomd.xml",
        "https://good.example/r/repodata/repomd.xml",
        "https://good.example/r/repodata/repomd.xml",
        "https://user:pass@bad.example/r/repodata/repomd.xml"
    )) == ["https://good.example/r/"]

def test_limit():
    with pytest.raises(ValueError):
        speed.parse_metalink(_xml(), 9)

def test_reject_unexpected_repo():
    with pytest.raises(ValueError):
        speed.discover("45", "rpmfusion")

def test_bounded_probe(monkeypatch):
    calls = []
    def fake(url, limit, ranged=False):
        calls.append((url, limit, ranged))
        return b"metadata"
    monkeypatch.setattr(speed, "_download", fake)
    result = speed.probe("https://good.example/r/")
    assert result.status == "reachable"
    assert calls == [("https://good.example/r/repodata/repomd.xml", 524288, True)]
