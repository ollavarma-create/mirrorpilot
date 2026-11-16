import pytest
from mirrorpilot import speed

def _xml(*urls):
    return ("<metalink><files><file><resources>" +
            "".join(f"<url>{u}</url>" for u in urls) +
            "</resources></file></files></metalink>").encode()

def _registry(*rows):
    return ("<table><tbody>" + "".join(
        f"<tr><td>{country}</td><td>Operator</td><td>{host}</td><td>Fedora Linux</td></tr>"
        for country, host in rows) + "</tbody></table>").encode()

def test_registry_maps_country_without_hardcoded_hosts():
    result = speed.parse_inventory(_registry(("EE", "mirrors.xtom.ee"), ("DE", "mirror.dogado.de")))
    assert result == {"mirrors.xtom.ee": "EE", "mirror.dogado.de": "DE"}

def test_conflicting_country_fails_closed():
    assert "mirror.example" not in speed.parse_inventory(
        _registry(("DE", "mirror.example"), ("RU", "mirror.example")))

def test_discovery_uses_mirrormanager_without_country_filter(monkeypatch):
    calls = []
    def fake(url, limit):
        calls.append(url)
        if "metalink?" in url:
            return _xml("https://mirror.yandex.ru/fedora/repodata/repomd.xml",
                        "https://mirrors.xtom.ee/fedora/repodata/repomd.xml",
                        "https://mirror.dogado.de/fedora/repodata/repomd.xml")
        return _registry(("RU", "mirror.yandex.ru"), ("EE", "mirrors.xtom.ee"),
                         ("DE", "mirror.dogado.de"))
    monkeypatch.setattr(speed, "_download", fake)
    assert speed.discover("45") == [
        ("https://mirror.yandex.ru/fedora/", "RU"),
        ("https://mirrors.xtom.ee/fedora/", "EE"),
        ("https://mirror.dogado.de/fedora/", "DE"),
    ]
    assert len(calls) == 2
    assert "country=" not in calls[0]
    assert "page_size=500" in calls[1]


def test_country_override_filters_registered_mirrors(monkeypatch):
    calls = []
    def fake(url, limit):
        calls.append(url)
        if "metalink?" in url:
            return _xml("https://de.example/repo/repodata/repomd.xml",
                        "https://fi.example/repo/repodata/repomd.xml")
        return _registry(("DE", "de.example"), ("FI", "fi.example"))
    monkeypatch.setattr(speed, "_download", fake)
    assert speed.discover("45", country="fi") == [("https://fi.example/repo/", "FI")]
    assert "country=FI" in calls[0]


def test_unknown_registry_hosts_fail_closed(monkeypatch):
    def fake(url, limit):
        if "metalink?" in url:
            return _xml("https://unknown.example/repo/repodata/repomd.xml",
                        "https://known.example/repo/repodata/repomd.xml")
        return _registry(("BR", "known.example"))
    monkeypatch.setattr(speed, "_download", fake)
    assert speed.discover("45") == [("https://known.example/repo/", "BR")]


def test_invalid_discovery_settings_rejected():
    for country in ("", "FIN", "F1", "🇫🇮", "FI,DE"):
        with pytest.raises(ValueError):
            speed.discover("45", country=country)
    for count in (0, 25, True, "8"):
        with pytest.raises(ValueError):
            speed.discover("45", max_mirrors=count)

def test_metalink_rejects_unsafe_urls():
    assert speed.parse_metalink(_xml(
        "http://bad.example/r/repodata/repomd.xml",
        "https://user:pass@bad.example/r/repodata/repomd.xml",
        "https://ok.example/r/repodata/repomd.xml"
    )) == ["https://ok.example/r/"]

def test_reject_bad_repo():
    with pytest.raises(ValueError):
        speed.discover("45", "rpmfusion")

def test_primary_sample_path():
    data = (b'<repomd xmlns="http://linux.duke.edu/metadata/repo">'
            b'<data type="primary"><location href="repodata/primary.xml.zck"/></data>'
            b'</repomd>')
    assert speed._sample_path(data) == "repodata/primary.xml.zck"

def test_three_samples_median(monkeypatch):
    index = (b'<repomd xmlns="http://linux.duke.edu/metadata/repo">'
             b'<data type="primary"><location href="repodata/primary.xml.zck"/></data>'
             b'</repomd>')
    monkeypatch.setattr(speed, "_download", lambda url, limit: index)
    values = iter([(10, 20, 100), (20, 200, 100), (30, 50, 100)])
    seen = []
    def fake_transfer(url):
        seen.append(url)
        return next(values)
    monkeypatch.setattr(speed, "_transfer", fake_transfer)
    result = speed.probe("https://example.org/repo/", "EE")
    assert result.mbps == 50
    assert result.ttfb_ms == 20
    assert len(seen) == 3
    assert all(url.endswith("/repodata/primary.xml.zck") for url in seen)

def test_no_unapproved_probes(monkeypatch):
    monkeypatch.setattr(speed, "discover", lambda *args: [])
    monkeypatch.setattr(speed, "probe", lambda *args: pytest.fail("unexpected probe"))
    assert speed.benchmark("45") == []

def test_discovery_preserves_mirrormanager_priority_and_limit(monkeypatch):
    urls = [f"https://de{i}.example/repo/repodata/repomd.xml" for i in range(9)]
    urls += ["https://fi.example/repo/repodata/repomd.xml"]
    def fake(url, limit):
        if "metalink?" in url:
            return _xml(*urls)
        return _registry(*([("DE", f"de{i}.example") for i in range(9)] +
                           [("FI", "fi.example")]))
    monkeypatch.setattr(speed, "_download", fake)
    result = speed.discover("45")
    assert len(result) == 8
    assert [country for _, country in result] == ["DE"] * 8
    assert speed.discover("45", max_mirrors=10)[-1] == ("https://fi.example/repo/", "FI")

def test_range_is_recorded(monkeypatch):
    index = (b'<repomd xmlns="http://linux.duke.edu/metadata/repo">'
             b'<data type="primary"><location href="repodata/primary.xml.zck"/></data>'
             b'</repomd>')
    monkeypatch.setattr(speed, "_download", lambda url, limit: index)
    values = iter([(10, 20, 100), (20, 200, 100), (30, 50, 100)])
    monkeypatch.setattr(speed, "_transfer", lambda url: next(values))
    result = speed.probe("https://example.org/repo/", "EE")
    assert result.min_mbps == 20
    assert result.max_mbps == 200

def test_progress_reports_each_mirror(monkeypatch):
    monkeypatch.setattr(speed, 'discover', lambda *args: [('https://a.example/', 'FI'), ('https://b.example/', 'SE')])
    monkeypatch.setattr(speed, 'probe', lambda base, country: speed.MirrorResult(base, country, 'measured', 10, 100, 100, 'ok'))
    events = []
    results = speed.benchmark('45', progress=lambda done, total: events.append((done, total)))
    assert len(results) == 2
    assert events == [(0, 2), (1, 2), (2, 2)]
