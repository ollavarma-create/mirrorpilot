"""Read-only Fedora MirrorManager speed test, limited to 8 candidates."""
from dataclasses import dataclass
from time import perf_counter
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET
from mirrorpilot.check import SafeRedirectHandler

COUNTRIES = ("FI", "SE", "EE", "DE", "NL", "DK")
MAX_MIRRORS = 8
SAMPLE_BYTES = 512 * 1024
MAX_LIST = 1024 * 1024

@dataclass(frozen=True)
class MirrorResult:
    url: str
    status: str
    milliseconds: float | None
    mbps: float | None
    message: str

def _download(url: str, limit: int, ranged: bool = False) -> bytes:
    headers = {"User-Agent": "MirrorPilot/0.1"}
    if ranged:
        headers["Range"] = f"bytes=0-{limit-1}"
    request = Request(url, headers=headers)
    with build_opener(SafeRedirectHandler()).open(request, timeout=10) as response:
        if response.status not in (200, 206):
            raise ValueError(f"HTTP {response.status}")
        return response.read(limit)

def parse_metalink(data: bytes, limit: int = MAX_MIRRORS) -> list[str]:
    if not 1 <= limit <= MAX_MIRRORS:
        raise ValueError("Invalid candidate limit")
    result = []
    for element in ET.fromstring(data).iter():
        if element.tag.rsplit("}", 1)[-1] != "url":
            continue
        url = (element.text or "").strip()
        p = urlsplit(url)
        suffix = "repodata/repomd.xml"
        if (p.scheme != "https" or not p.hostname or p.username or p.password
                or p.port not in (None, 443) or p.query or p.fragment
                or not p.path.endswith("/" + suffix)):
            continue
        base = url[:-len(suffix)]
        if base not in result:
            result.append(base)
        if len(result) >= limit:
            break
    return result

def discover(release: str, repo: str = "fedora") -> list[str]:
    if not release.isdigit() or len(release) > 3:
        raise ValueError("Invalid release")
    if repo not in ("fedora", "updates"):
        raise ValueError("Unsupported repository")
    name = f"fedora-{release}" if repo == "fedora" else f"updates-released-f{release}"
    query = urlencode({"repo": name, "arch": "x86_64",
                       "country": ",".join(COUNTRIES)})
    url = f"https://mirrors.fedoraproject.org/metalink?{query}"
    return parse_metalink(_download(url, MAX_LIST))

def probe(base: str) -> MirrorResult:
    # Base URL must have been derived from a HTTPS metalink entry.
    url = base + "repodata/repomd.xml"
    try:
        start = perf_counter()
        data = _download(url, SAMPLE_BYTES, ranged=True)
        elapsed = max(perf_counter() - start, 0.001)
        if not data:
            raise ValueError("Empty response")
        return MirrorResult(base, "reachable", round(elapsed * 1000, 1),
                            round(8 * len(data) / elapsed / 1e6, 2),
                            f"{len(data)} bytes")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
        return MirrorResult(base, "error", None, None, str(exc))

def benchmark(release: str, repo: str = "fedora") -> list[MirrorResult]:
    return [probe(url) for url in discover(release, repo)]
