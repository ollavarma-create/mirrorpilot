"""Read-only, opt-in Fedora mirror benchmark with conservative host approval.

Only exact, explicitly curated hostnames are contacted. A hostname is not
proof of physical server location; future versions should use an authoritative
mirror inventory with verified operator/location data.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from urllib.parse import urlencode, urlsplit, urljoin
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

from mirrorpilot.check import SafeRedirectHandler

COUNTRIES = ("FI", "SE", "EE", "DE", "NL", "DK")
# Conservative initial exact-host allowlist; no wildcard/TLD-based trust.
# Operator domains indicate likely country, not independently verified location.
APPROVED_HOSTS = {
    "www.nic.funet.fi": "FI",
    "mirrors.xtom.ee": "EE",
    "mirror.dogado.de": "DE",
}
MAX_MIRRORS = 8
MAX_LIST = 1024 * 1024
SAMPLE_BYTES = 2 * 1024 * 1024
TIMEOUT = 12


@dataclass(frozen=True)
class MirrorResult:
    url: str
    country: str
    status: str
    ttfb_ms: float | None
    mbps: float | None
    bytes_read: int
    detail: str


def _download(url: str, limit: int, ranged: bool = False) -> bytes:
    headers = {"User-Agent": "MirrorPilot/0.2"}
    if ranged:
        headers["Range"] = f"bytes=0-{limit-1}"
    with build_opener(SafeRedirectHandler()).open(Request(url, headers=headers), timeout=TIMEOUT) as response:
        if response.status not in (200, 206):
            raise ValueError(f"Unexpected HTTP {response.status}")
        return response.read(limit + 1)[:limit]


def _base_from_metalink(url: str) -> str | None:
    p = urlsplit(url.strip())
    suffix = "/repodata/repomd.xml"
    if (p.scheme != "https" or not p.hostname or p.username or p.password
        or p.port not in (None, 443) or p.query or p.fragment
        or not p.path.endswith(suffix)):
        return None
    if p.hostname.lower() not in APPROVED_HOSTS:
        return None
    return url.strip()[:-len("repodata/repomd.xml")]


def parse_metalink(data: bytes, limit: int = MAX_MIRRORS) -> list[str]:
    if not 1 <= limit <= MAX_MIRRORS:
        raise ValueError("Invalid mirror limit")
    result = []
    for element in ET.fromstring(data).iter():
        if element.tag.rsplit("}", 1)[-1] != "url":
            continue
        base = _base_from_metalink(element.text or "")
        if base and base not in result:
            result.append(base)
            if len(result) == limit:
                break
    return result


def discover(release: str, repo: str = "fedora") -> list[str]:
    if not release.isdigit() or len(release) > 3:
        raise ValueError("Invalid release")
    if repo not in ("fedora", "updates"):
        raise ValueError("Unsupported repository")
    name = f"fedora-{release}" if repo == "fedora" else f"updates-released-f{release}"
    query = urlencode({"repo": name, "arch": "x86_64", "country": ",".join(COUNTRIES)})
    return parse_metalink(_download("https://mirrors.fedoraproject.org/metalink?" + query, MAX_LIST))


def _sample_path(xml: bytes) -> str:
    root = ET.fromstring(xml)
    ns = {"r": "http://linux.duke.edu/metadata/repo"}
    # Prefer primary metadata: much larger than the tiny repomd.xml index.
    for kind in ("primary", "filelists"):
        for entry in root.findall("r:data", ns):
            if entry.get("type") != kind:
                continue
            loc = entry.find("r:location", ns)
            if loc is None:
                continue
            href = loc.get("href", "")
            if (href.startswith("repodata/") and ".." not in href.split("/")
                and not urlsplit(href).scheme and not urlsplit(href).netloc
                and not urlsplit(href).query and not urlsplit(href).fragment):
                return href
    raise ValueError("No suitable primary/filelists metadata sample")


def _transfer(url: str) -> tuple[float, float, int]:
    """Return first-byte time, payload throughput and bytes, bounded to 2 MiB."""
    request = Request(url, headers={
        "User-Agent": "MirrorPilot/0.2",
        "Range": f"bytes=0-{SAMPLE_BYTES-1}",
        "Accept-Encoding": "identity",
    })
    start = perf_counter()
    with build_opener(SafeRedirectHandler()).open(request, timeout=TIMEOUT) as response:
        if response.status not in (200, 206):
            raise ValueError(f"HTTP {response.status}")
        first = response.read(1)
        ttfb = (perf_counter() - start) * 1000
        if not first:
            raise ValueError("Empty metadata response")
        transfer_start = perf_counter()
        received = len(first)
        while received < SAMPLE_BYTES:
            block = response.read(min(65536, SAMPLE_BYTES - received))
            if not block:
                break
            received += len(block)
        duration = max(perf_counter() - transfer_start, 0.001)
        return round(ttfb, 1), round(received * 8 / duration / 1e6, 2), received


def probe(base: str) -> MirrorResult:
    host = urlsplit(base).hostname or ""
    country = APPROVED_HOSTS.get(host.lower(), "unknown")
    if country not in COUNTRIES or _base_from_metalink(base + "repodata/repomd.xml") != base:
        return MirrorResult(base, country, "blocked", None, None, 0, "Host not approved")
    try:
        index = _download(urljoin(base, "repodata/repomd.xml"), MAX_LIST)
        sample = _sample_path(index)
        ttfb, rate, size = _transfer(urljoin(base, sample))
        return MirrorResult(base, country, "measured", ttfb, rate, size,
                            "Bounded metadata transfer; integrity/freshness not checked")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError, ET.ParseError) as exc:
        return MirrorResult(base, country, "error", None, None, 0, str(exc))


def benchmark(release: str, repo: str = "fedora") -> list[MirrorResult]:
    return [probe(base) for base in discover(release, repo)]
