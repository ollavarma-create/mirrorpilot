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
        return _xml("https://mirrors.xtom.ee/fedora/repodata/repomd.xml")
    monkeypatch.setattr(speed, "_download", fake)
    assert speed.discover("45") == ["https://mirrors.xtom.ee/fedora/"]
    assert "country=FI%2CSE%2CEE%2CDE%2CNL%2CDK" in seen[0]
    assert "fedora-45" in seen[0]

def test_forbidden_yandex_never_selected():
    assert speed.parse_metalink(_xml(
        "https://mirror.yandex.ru/fedora/repodata/repomd.xml",
        "https://mirror.dogado.de/fedora/repodata/repomd.xml"
    )) == ["https://mirror.dogado.de/fedora/"]

def test_reject_lookalike_and_credentials():
    assert speed.parse_metalink(_xml(
        "https://mirror.dogado.de.evil.example/fedora/repodata/repomd.xml",
        "https://user:password@mirror.dogado.de/fedora/repodata/repomd.xml",
        "http://mirror.dogado.de/fedora/repodata/repomd.xml"
    )) == []

def test_limit():
    with pytest.raises(ValueError):
        speed.parse_metalink(_xml(), 9)

def test_bad_repo():
    with pytest.raises(ValueError):
        speed.discover("45", "rpmfusion")

def test_probe_never_connects_to_blocked_host(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network called for blocked host")
    monkeypatch.setattr(speed, "_download", forbidden)
    monkeypatch.setattr(speed, "_transfer", forbidden)
    assert speed.probe("https://mirror.yandex.ru/fedora/").status == "blocked"

def test_sample_path():
    data = (b'<repomd xmlns="http://linux.duke.edu/metadata/repo">'
            b'<data type="primary"><location href="repodata/primary.xml.zck"/></data>'
            b'</repomd>')
    assert speed._sample_path(data) == "repodata/primary.xml.zck"

def test_probe_uses_large_sample(monkeypatch):
    data = (b'<repomd xmlns="http://linux.duke.edu/metadata/repo">'
            b'<data type="primary"><location href="repodata/primary.xml.zck"/></data>'
            b'</repomd>')
    seen = []
    monkeypatch.setattr(speed, "_download", lambda url, limit: data)
    def transfer(url):
        seen.append(url)
        return 12.5, 120.0, speed.SAMPLE_BYTES
    monkeypatch.setattr(speed, "_transfer", transfer)
    result = speed.probe("https://mirror.dogado.de/fedora/")
    assert result.status == "measured"
    assert result.mbps == 120.0
    assert seen == ["https://mirror.dogado.de/fedora/repodata/primary.xml.zck"]
