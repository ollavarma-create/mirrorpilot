"""Read-only Fedora mirror benchmark using live MirrorManager inventory.

Candidate URLs come from the release metalink. Host-country attribution
comes independently from the public MirrorManager inventory; missing or
ambiguous matches fail closed. Country means registered location, not a
cryptographic guarantee of physical routing.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from statistics import median
from time import perf_counter
from urllib.parse import urlencode, urlsplit, urljoin
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

from mirrorpilot.check import SafeRedirectHandler

COUNTRIES = ("FI", "SE", "EE", "DE", "NL", "DK")
MAX_MIRRORS = 8
MAX_LIST = 1024 * 1024
MAX_REGISTRY = 3 * 1024 * 1024
SAMPLE_BYTES = 2 * 1024 * 1024
REPEATS = 3
TIMEOUT = 12
REGISTRY_URL = "https://mirrormanager.fedoraproject.org/mirrors/Fedora?page_size=500"


@dataclass(frozen=True)
class MirrorResult:
    url: str
    country: str
    status: str
    ttfb_ms: float | None
    mbps: float | None
    bytes_read: int
    detail: str
    min_mbps: float | None = None
    max_mbps: float | None = None


class _InventoryParser(HTMLParser):
    """Read country and host from the public mirror inventory table rows."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.in_row = False
        self.in_cell = False
        self.cells = []
        self.fragments = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_row = True
            self.cells = []
        elif tag == "td" and self.in_row:
            self.in_cell = True
            self.fragments = []

    def handle_data(self, data):
        if self.in_cell:
            self.fragments.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.in_cell:
            self.cells.append(" ".join(" ".join(self.fragments).split()))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if len(self.cells) >= 3:
                self.rows.append(tuple(self.cells))
            self.in_row = False
            self.in_cell = False


def parse_inventory(html: bytes) -> dict[str, str]:
    parser = _InventoryParser()
    parser.feed(html.decode("utf-8", errors="replace"))
    result = {}
    ambiguous = set()
    for row in parser.rows:
        country = row[0].upper()
        if len(country) != 2 or not country.isalpha():
            continue
        # Mirror Name column contains a hostname, occasionally with a path.
        host = row[2].split()[0].split("/")[0].lower().rstrip(".")
        if not host or "." not in host or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-." for c in host):
            continue
        if host in result and result[host] != country:
            ambiguous.add(host)
        else:
            result[host] = country
    for host in ambiguous:
        result.pop(host, None)
    return result


def _download(url: str, limit: int) -> bytes:
    with build_opener(SafeRedirectHandler()).open(
        Request(url, headers={"User-Agent": "MirrorPilot/0.2"}), timeout=TIMEOUT
    ) as response:
        if response.status != 200:
            raise ValueError(f"Unexpected HTTP {response.status}")
        payload = response.read(limit + 1)
        if len(payload) > limit:
            raise ValueError("Registry or metalink response exceeds size limit")
        return payload


def _base_from_metalink(url: str) -> str | None:
    p = urlsplit(url.strip())
    suffix = "/repodata/repomd.xml"
    if (p.scheme != "https" or not p.hostname or p.username or p.password
        or p.port not in (None, 443) or p.query or p.fragment
        or not p.path.endswith(suffix)):
        return None
    return url.strip()[:-len("repodata/repomd.xml")]


def parse_metalink(data: bytes) -> list[str]:
    result = []
    for element in ET.fromstring(data).iter():
        if element.tag.rsplit("}", 1)[-1] == "url":
            base = _base_from_metalink(element.text or "")
            if base and base not in result:
                result.append(base)
    return result


def discover(release: str, repo: str = "fedora") -> list[tuple[str, str]]:
    if not release.isdigit() or len(release) > 3:
        raise ValueError("Invalid release")
    if repo not in ("fedora", "updates"):
        raise ValueError("Unsupported repository")
    name = f"fedora-{release}" if repo == "fedora" else f"updates-released-f{release}"
    query = urlencode({"repo": name, "arch": "x86_64", "country": ",".join(COUNTRIES)})
    metalink = _download("https://mirrors.fedoraproject.org/metalink?" + query, MAX_LIST)
    # Registry is authoritative for registered country; no hostname heuristics.
    registry = parse_inventory(_download(REGISTRY_URL, MAX_REGISTRY))
    buckets = {country: [] for country in COUNTRIES}
    for base in parse_metalink(metalink):
        host = urlsplit(base).hostname or ""
        country = registry.get(host.lower())
        if country in buckets:
            buckets[country].append((base, country))
    # Round-robin preserves MirrorManager order within each country while
    # preventing the first country's mirrors from filling all eight slots.
    selected = []
    while len(selected) < MAX_MIRRORS:
        added = False
        for country in COUNTRIES:
            if buckets[country] and len(selected) < MAX_MIRRORS:
                selected.append(buckets[country].pop(0))
                added = True
        if not added:
            break
    return selected


def _sample_path(xml: bytes) -> str:
    root = ET.fromstring(xml)
    ns = {"r": "http://linux.duke.edu/metadata/repo"}
    for kind in ("primary", "filelists"):
        for entry in root.findall("r:data", ns):
            if entry.get("type") != kind:
                continue
            loc = entry.find("r:location", ns)
            href = loc.get("href", "") if loc is not None else ""
            p = urlsplit(href)
            if (href.startswith("repodata/") and ".." not in href.split("/")
                and not p.scheme and not p.netloc and not p.query and not p.fragment):
                return href
    raise ValueError("No suitable primary/filelists metadata sample")


def _transfer(url: str) -> tuple[float, float, int]:
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
            chunk = response.read(min(65536, SAMPLE_BYTES - received))
            if not chunk:
                break
            received += len(chunk)
        duration = max(perf_counter() - transfer_start, 0.001)
        return round(ttfb, 1), round(received * 8 / duration / 1e6, 2), received


def probe(base: str, country: str) -> MirrorResult:
    # Direct callers must provide an approved, discovered pair; benchmark()
    # is the only GUI entry point and uses discover() for authorization.
    try:
        index = _download(urljoin(base, "repodata/repomd.xml"), MAX_LIST)
        sample = _sample_path(index)
        measurements = [_transfer(urljoin(base, sample)) for _ in range(REPEATS)]
        return MirrorResult(base, country, "measured",
                            round(median(m[0] for m in measurements), 1),
                            round(median(m[1] for m in measurements), 2),
                            int(median(m[2] for m in measurements)),
                            "Median of 3 bounded transfers; integrity/freshness not checked",
                            round(min(m[1] for m in measurements), 2),
                            round(max(m[1] for m in measurements), 2))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError, ET.ParseError) as exc:
        return MirrorResult(base, country, "error", None, None, 0, str(exc))


def benchmark(release: str, repo: str = "fedora") -> list[MirrorResult]:
    results = [probe(base, country) for base, country in discover(release, repo)]
    return sorted(results, key=lambda r: (r.mbps is None, -(r.mbps or 0)))
