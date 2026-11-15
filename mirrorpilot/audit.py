"""Read-only mirror index audit against Fedora's live metalink reference.

A matching repomd.xml digest indicates agreement with the current metalink,
not that every referenced metadata file is available or correctly signed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urlsplit, urljoin
from urllib.error import HTTPError, URLError

from mirrorpilot.speed import COUNTRIES, MAX_LIST, _download, _base_from_metalink

@dataclass(frozen=True)
class AuditResult:
    status: str
    message: str
    source: str

def reference_hash(metalink: bytes) -> tuple[str, str] | None:
    """Return strong checksum for repomd.xml from Fedora metalink."""
    root = ET.fromstring(metalink)
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "hash":
            continue
        algorithm = node.attrib.get("type", "").lower()
        value = (node.text or "").strip().lower()
        if algorithm in ("sha256", "sha512") and len(value) == hashlib.new(algorithm).digest_size * 2:
            if all(ch in "0123456789abcdef" for ch in value):
                return algorithm, value
    return None

def audit(base: str, country: str, release: str, repo: str = "fedora") -> AuditResult:
    """Compare a previously discovered mirror with Fedora's current reference.

    No package installation, DNF cache access, or configuration modification.
    """
    if country not in COUNTRIES or not release.isdigit() or len(release) > 3:
        return AuditResult("unsupported", "Invalid country or release", base)
    if repo not in ("fedora", "updates"):
        return AuditResult("unsupported", "Unsupported repository", base)
    p = urlsplit(base)
    if (_base_from_metalink(base + "repodata/repomd.xml") != base
            or not p.hostname or p.port not in (None, 443)):
        return AuditResult("unsupported", "HTTPS mirror base URL required", base)
    name = f"fedora-{release}" if repo == "fedora" else f"updates-released-f{release}"
    query = urlencode({"repo": name, "arch": "x86_64", "country": ",".join(COUNTRIES)})
    try:
        reference = _download("https://mirrors.fedoraproject.org/metalink?" + query, MAX_LIST)
        expected = reference_hash(reference)
        if expected is None:
            return AuditResult("unknown", "No strong checksum in Fedora metalink", base)
        algorithm, digest = expected
        manifest = _download(urljoin(base, "repodata/repomd.xml"), MAX_LIST)
        actual = hashlib.new(algorithm, manifest).hexdigest()
        if actual != digest:
            return AuditResult("different", f"{algorithm.upper()} differs from current Fedora metalink; mirror may be stale", base)
        # A matching manifest alone cannot guarantee referenced files are present.
        ET.fromstring(manifest)
        return AuditResult("index-match", f"{algorithm.upper()} repomd.xml matches Fedora metalink; referenced files not yet verified", base)
    except HTTPError as exc:
        return AuditResult("missing", f"HTTP {exc.code}: {exc.url}", base)
    except (URLError, TimeoutError, ValueError, RuntimeError, OSError, ET.ParseError) as exc:
        return AuditResult("error", str(exc), base)
