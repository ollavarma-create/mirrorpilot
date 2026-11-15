"""Conservative metadata consistency test for an explicit HTTPS base URL."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_INDEX = 5 * 1024 * 1024
MAX_METADATA = 32 * 1024 * 1024


@dataclass(frozen=True)
class Diagnostic:
    status: str
    message: str
    source: str


class SafeRedirectHandler(HTTPRedirectHandler):
    """Never follow an HTTP or cross-host metadata redirect."""

    def redirect_request(self, request, fp, code, msg, headers, url):
        old, new = urlsplit(request.full_url), urlsplit(url)
        if new.scheme != "https" or new.hostname != old.hostname or new.port != old.port:
            raise RuntimeError("Cross-host or insecure metadata redirect refused")
        return super().redirect_request(request, fp, code, msg, headers, url)


def _fetch(url: str, limit: int) -> bytes:
    request = Request(url, headers={"User-Agent": "MirrorPilot/0.1"})
    with build_opener(SafeRedirectHandler()).open(request, timeout=12) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        length = response.headers.get("Content-Length")
        if length and int(length) > limit:
            raise RuntimeError("Metadata exceeds safety size limit")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise RuntimeError("Metadata exceeds safety size limit")
        return data


def check_baseurl(baseurl: str) -> Diagnostic:
    """Validate repomd.xml and referenced SHA-256/512 metadata files.

    Does not mutate DNF caches or configuration and requires no root access.
    """
    source = baseurl.strip()
    parts = urlsplit(source)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return Diagnostic("unsupported", "A direct HTTPS base URL is required", source)
    if "$" in source or " " in source:
        return Diagnostic("unsupported", "URL contains unexpanded variables", source)
    root = source.rstrip("/") + "/"
    try:
        manifest = _fetch(urljoin(root, "repodata/repomd.xml"), MAX_INDEX)
        metadata = ET.fromstring(manifest)
        ns = {"r": "http://linux.duke.edu/metadata/repo"}
        checked = 0
        entries = metadata.findall("r:data", ns)
        if not entries:
            return Diagnostic("invalid", "No metadata entries in repomd.xml", root)
        for entry in entries:
            loc = entry.find("r:location", ns)
            checksum = entry.find("r:checksum", ns)
            if loc is None or checksum is None:
                continue
            href = loc.attrib.get("href", "")
            algo = checksum.attrib.get("type", "")
            if algo not in ("sha256", "sha512"):
                continue
            if (not href.startswith("repodata/") or
                ".." in href.split("/") or
                urlsplit(href).scheme):
                return Diagnostic("invalid", f"Unsafe path: {href}", root)
            blob = _fetch(urljoin(root, href), MAX_METADATA)
            digest = hashlib.new(algo, blob).hexdigest()
            if digest.lower() != (checksum.text or "").strip().lower():
                return Diagnostic("invalid", f"Checksum mismatch: {href}", root)
            checked += 1
        if not checked:
            return Diagnostic("invalid", "No supported checksums in metadata", root)
        return Diagnostic("ok", f"Validated {checked} metadata files", root)
    except HTTPError as exc:
        return Diagnostic("missing", f"HTTP {exc.code}: {exc.url}", root)
    except (URLError, TimeoutError) as exc:
        return Diagnostic("network", str(exc), root)
    except (ET.ParseError, ValueError, RuntimeError, OSError) as exc:
        return Diagnostic("invalid", str(exc), root)
