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
from urllib.request import Request, build_opener
from time import monotonic

from mirrorpilot.speed import COUNTRIES, MAX_LIST, _download, _base_from_metalink
from mirrorpilot.check import SafeRedirectHandler

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
    if country not in (*COUNTRIES, "Configured") or not release.isdigit() or len(release) > 3:
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

# A bounded subset; no claim of full repository validation.
METADATA_KINDS = ("primary", "filelists", "other")
MAX_FILE_BYTES = 512 * 1024 * 1024
CHUNK_BYTES = 256 * 1024
MAX_SECONDS_PER_FILE = 120

class MetadataLimitExceeded(Exception):
    pass

def _metadata_entries(manifest: bytes):
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
            size_node = node.find("r:size", ns)
            size = None
            if size_node is not None:
                raw = (size_node.text or "").strip()
                if not raw.isdecimal():
                    raise ValueError(f"{kind}: invalid declared size")
                size = int(raw)
            entries.append((kind, href, algorithm, digest, size))
            break
    if not entries:
        raise ValueError("No primary/filelists/other metadata entries")
    return entries

def _hash_stream(url: str, algorithm: str, expected_size: int | None, progress=None):
    """Hash compressed bytes in fixed-size chunks; cap size and wall-clock time."""
    if expected_size is not None and expected_size > MAX_FILE_BYTES:
        raise MetadataLimitExceeded("Declared metadata size exceeds 512 MiB safety limit")
    request = Request(url, headers={"User-Agent": "MirrorPilot/0.3", "Accept-Encoding": "identity"})
    start = monotonic()
    with build_opener(SafeRedirectHandler()).open(request, timeout=12) as response:
        if response.status != 200:
            raise ValueError(f"Unexpected HTTP {response.status}")
        length = response.headers.get("Content-Length")
        if length is not None and int(length) > MAX_FILE_BYTES:
            raise MetadataLimitExceeded("HTTP Content-Length exceeds 512 MiB safety limit")
        hasher = hashlib.new(algorithm)
        count = 0
        while True:
            if monotonic() - start > MAX_SECONDS_PER_FILE:
                raise TimeoutError("Metadata download exceeded 120 seconds")
            block = response.read(min(CHUNK_BYTES, MAX_FILE_BYTES - count + 1))
            if not block:
                break
            count += len(block)
            if count > MAX_FILE_BYTES:
                raise MetadataLimitExceeded("Metadata exceeded 512 MiB safety limit")
            hasher.update(block)
            if progress is not None:
                progress(count, expected_size or 0)
        if expected_size is not None and count != expected_size:
            raise ValueError(f"Metadata size mismatch: expected {expected_size}, got {count}")
        return hasher.hexdigest(), count

def audit_referenced(base: str, country: str, release: str, progress=None) -> AuditResult:
    """Verify three metadata kinds with streaming, without changing DNF."""
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
    for index, (kind, href, algorithm, expected, size) in enumerate(entries, 1):
        if progress is not None:
            progress(kind, index, len(entries), 0, size or 0)
        try:
            def on_bytes(done, total):
                if progress is not None:
                    progress(kind, index, len(entries), done, total)
            actual, count = _hash_stream(urljoin(base, href), algorithm, size, on_bytes)
            if actual != expected:
                return AuditResult("checksum-mismatch", f"{kind}: checksum differs ({href})", base)
            verified.append(f"{kind} ({count} bytes)")
        except HTTPError as exc:
            return AuditResult("missing", f"{kind}: HTTP {exc.code} ({href})", base)
        except MetadataLimitExceeded as exc:
            return AuditResult("too-large", f"{kind}: {exc} ({href})", base)
        except (URLError, TimeoutError, ValueError, RuntimeError, OSError) as exc:
            return AuditResult("error", f"{kind}: {exc} ({href})", base)
    return AuditResult("metadata-match",
                       f"Verified {len(verified)} metadata files: {', '.join(verified)}; "
                       "other metadata and RPM signatures not checked", base)
