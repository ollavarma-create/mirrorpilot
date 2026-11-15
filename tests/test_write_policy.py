"""Security boundary tests for the future write helper request protocol."""
import pytest

from mirrorpilot.write_policy import validate_request, preview_options


@pytest.mark.parametrize("repo", ["fedora", "updates"])
def test_approved_request(repo):
    request = validate_request(repo, "https://mirror.example.fi/fedora/linux/")
    assert preview_options(request) == (
        f"{repo}.baseurl=https://mirror.example.fi/fedora/linux/",
        f"{repo}.metalink=",
        f"{repo}.mirrorlist=",
    )


@pytest.mark.parametrize("repo", [
    "updates-testing", "fedora;rm -rf /", "fedora.baseurl", "", "../fedora",
])
def test_reject_other_repository_ids(repo):
    with pytest.raises(ValueError):
        validate_request(repo, "https://mirror.example.fi/fedora/")


@pytest.mark.parametrize("url", [
    "http://mirror.example.fi/fedora/",
    "https://user:pass@mirror.example.fi/fedora/",
    "https://mirror.example.fi:8443/fedora/",
    "https://mirror.example.fi/fedora/?x=1",
    "https://mirror.example.fi/fedora/#fragment",
    "https://mirror.example.fi/fedora/../updates/",
    "https://mirror.example.fi/fedora/%2e%2e/",
    "https://mirror.example.fi/fedora/;evil/",
    "https://mirror.example.fi/fedora/=evil/",
    "https://mirror.example.fi/fedora/\\evil/",
    "https://mirror.example.fi/fedora/\n",
    "https://127.0.0.1/fedora/",
    "https://mirror.example.ru/fedora/",
    "file:///etc/shadow",
    "https://mirror.example.fi/",
    "https://mirror.example.fi/fedora",
    "https://mirror.example.fi:bad/fedora/",
    "https://[::1]/fedora/",
])
def test_reject_unsafe_urls(url):
    with pytest.raises(ValueError):
        validate_request("fedora", url)


def test_reject_wrong_types():
    with pytest.raises(ValueError):
        validate_request(["fedora"], "https://mirror.example.fi/fedora/")
    with pytest.raises(ValueError):
        validate_request("fedora", None)
