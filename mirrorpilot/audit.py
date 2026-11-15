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
from mirrorpilot.check import _fetch, MAX_METADATA

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

# A deliberate bounded subset, not a claim that the entire repository is valid.
METADATA_KINDS = ("primary", "filelists", "other")

def _metadata_entries(manifest: bytes) -> list[tuple[str, str, str, str]]:
    root = ET.fromstring(manifest)
    ns = {"r": "http://linux.duke.edu/metadata/repo"}
    entries = []
    for kind in METADATA_KINDS:
        for node in root.findall("r:data", ns):
            if node.get("type") != kind:
                continue
            location = node.find("r:location", ns)
            checksum = node.find("r:checksum", ns)
            if location is None or checksum is None:
                raise ValueError(f"{kind}: missing location or checksum")
            href = location.get("href", "")
            parsed = urlsplit(href)
            if (not href.startswith("repodata/") or ".." in href.split("/")
                    or parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
                    or "\\" in href):
                raise ValueError(f"{kind}: unsafe metadata path")
            algorithm = checksum.get("type", "").lower()
            digest = (checksum.text or "").strip().lower()
            if (algorithm not in ("sha256", "sha512")
                    or len(digest) != hashlib.new(algorithm).digest_size * 2
                    or any(ch not in "0123456789abcdef" for ch in digest)):
                raise ValueError(f"{kind}: unsupported or malformed checksum")
            entries.append((kind, href, algorithm, digest))
            break
    if not entries:
        raise ValueError("No primary/filelists/other metadata entries")
    return entries


def audit_referenced(base: str, country: str, release: str) -> AuditResult:
    """Verify up to three referenced metadata files, at most 32 MiB each.

    This checks presence and stored checksums, but does not validate RPM
    signatures, metadata freshness, or the entire repository.
    """
    if country not in COUNTRIES or not release.isdigit() or len(release) > 3:
        return AuditResult("unsupported", "Invalid country or release", base)
    if _base_from_metalink(base + "repodata/repomd.xml") != base:
        return AuditResult("unsupported", "HTTPS mirror base URL required", base)
    try:
        manifest = _download(urljoin(base, "repodata/repomd.xml"), MAX_LIST)
        entries = _metadata_entries(manifest)
    except HTTPError as exc:
        return AuditResult("missing", f"repomd.xml: HTTP {exc.code}", base)
    except (URLError, TimeoutError, ValueError, RuntimeError, OSError, ET.ParseError) as exc:
        return AuditResult("error", f"repomd.xml: {exc}", base)
    verified = []
    for kind, href, algorithm, expected in entries:
        try:
            data = _fetch(urljoin(base, href), MAX_METADATA)
            actual = hashlib.new(algorithm, data).hexdigest()
            if actual != expected:
                return AuditResult("checksum-mismatch", f"{kind}: checksum differs ({href})", base)
            verified.append(kind)
        except HTTPError as exc:
            return AuditResult("missing", f"{kind}: HTTP {exc.code} ({href})", base)
        except RuntimeError as exc:
            message = str(exc)
            status = "too-large" if "size limit" in message else "error"
            return AuditResult(status, f"{kind}: {message} ({href})", base)
        except (URLError, TimeoutError, ValueError, OSError) as exc:
            return AuditResult("error", f"{kind}: {exc} ({href})", base)
    return AuditResult("metadata-match",
                       f"Verified {len(verified)} metadata files: {', '.join(verified)}; "
                       "other metadata and RPM signatures not checked", base)
