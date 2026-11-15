import hashlib
from mirrorpilot import releases

def test_installed_release_only_when_network_fails(monkeypatch):
    monkeypatch.setattr(releases, "installed_release", lambda: "44")
    def fail(*args):
        raise TimeoutError("offline")
    monkeypatch.setattr(releases, "_download", fail)
    assert releases.available_targets() == [("44", "Fedora 44 — installed")]

def test_next_release_official_metadata(monkeypatch):
    monkeypatch.setattr(releases, "installed_release", lambda: "44")
    digest = hashlib.sha256(b"index").hexdigest()
    xml = f'<metalink><hash type="sha256">{digest}</hash></metalink>'.encode()
    def get(url, limit):
        assert "fedora-45" in url
        return xml
    monkeypatch.setattr(releases, "_download", get)
    options = releases.available_targets()
    assert options[0][0] == "44"
    assert options[1][0] == "45"
    assert "upgrade not verified" in options[1][1]
