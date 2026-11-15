"""Read-only unified diagnostics with explicit verification scope."""
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
import socket
from mirrorpilot.speed import benchmark, MirrorResult, probe, _base_from_metalink
from mirrorpilot.audit import audit, audit_referenced, AuditResult

BAD = {"different", "missing", "checksum-mismatch"}


def explain_source(row):
    """Plain-language result with scope and next action, without overstating integrity."""
    if row is None:
        return "Current repository could not be identified; no current-source check was performed."
    if row.speed.status != "measured":
        detail = row.speed.detail
        if "HTTP Error 404" in detail or "HTTP 404" in detail:
            return ("Current repository unavailable: HTTP 404 while retrieving metadata "
                    f"({urljoin(row.speed.url, 'repodata/repomd.xml')} or a referenced metadata file). "
                    "A working alternative may be needed; no settings changed.")
        if "timed out" in detail.lower():
            return "Current repository did not respond in time; retry before changing settings."
        return f"Current repository check failed: {detail}. No changes made."
    if row.index and row.index.status == "different":
        return "Current repository index differs from Fedora's reference; it may be synchronizing."
    if row.metadata and row.metadata.status == "missing":
        return f"Current repository references missing metadata: {row.metadata.message}"
    if row.health == "verified":
        return "Current repository: checked metadata OK; no integrity-related change indicated."
    return f"Current repository: {row.health}; inspect details before changing settings."



def _index_safely(speed, release, repo):
    try:
        return audit(speed.url, speed.country, release, repo=repo)
    except (TimeoutError, socket.timeout, URLError, OSError) as exc:
        return AuditResult("timeout", f"Index request timed out or failed: {exc}", speed.url)
    except Exception as exc:
        return AuditResult("error", f"Index check failed: {exc}", speed.url)

GOOD = {"index-match", "metadata-match"}

@dataclass(frozen=True)
class MirrorHealth:
    speed: MirrorResult
    index: AuditResult | None = None
    metadata: AuditResult | None = None

    @property
    def health(self):
        if self.speed.status != "measured":
            return "error"
        states = [r.status for r in (self.index, self.metadata) if r is not None]
        if any(s in BAD for s in states):
            return "problem"
        if any(s not in GOOD for s in states):
            return "uncertain"
        if len(states) < 2:
            return "unchecked"
        return "verified"

def fastest_verified(rows):
    eligible = [r for r in rows if r.health == "verified" and r.speed.mbps is not None]
    return max(eligible, key=lambda r: r.speed.mbps) if eligible else None

def run_diagnostics(release: str, metadata_count: int = 1, repo: str = "fedora", configured_base: str | None = None, progress=None):
    """Benchmark eight, compare all indexes, stream metadata for fastest N.

    Default N=1 intentionally avoids downloading up to 12 GiB without
    explicit user approval. No verified recommendation until both checks pass.
    """
    if repo not in ("fedora", "updates"):
        raise ValueError("Unsupported repository")
    if not 0 <= metadata_count <= 8:
        raise ValueError("metadata_count must be between 0 and 8")
    def emit(phase, done, total, detail=""):
        if progress:
            progress(phase, done, total, detail)
    current = None
    if configured_base:
        base = configured_base.strip().rstrip("/") + "/"
        if _base_from_metalink(base + "repodata/repomd.xml") != base:
            raise ValueError("Configured source must be a concrete HTTPS repository URL")
        emit("current", 0, 1, base)
        current = probe(base, "Configured")
        emit("current", 1, 1, base)
    speeds = benchmark(release, repo=repo, progress=lambda done, total: emit("benchmark", done, total))
    if current is not None:
        speeds = [current] + [s for s in speeds if s.url.rstrip("/") != current.url.rstrip("/")]
    rows = []
    for i, speed in enumerate(speeds, 1):
        index = _index_safely(speed, release, repo) if speed.status == "measured" else None
        rows.append(MirrorHealth(speed, index))
        emit("index", i, len(speeds), speed.country)
    # Verify the configured source first, including when its index differs:
    # missing referenced files can explain a failed DNF update.
    if current is not None and rows and rows[0].index is not None:
        if rows[0].index.status in ("index-match", "different"):
            try:
                result = audit_referenced(current.url, "Configured", release,
                                          progress=lambda kind, n, total, done, size:
                                          emit("bytes", n, total, f"Current {kind}: {done}/{size} bytes"))
            except Exception as exc:
                result = AuditResult("error", f"Configured metadata check interrupted: {exc}", current.url)
            rows[0] = MirrorHealth(current, rows[0].index, result)
    # Verify fastest alternative whose index matches. Other rows remain unchecked.
    candidates = [i for i, row in enumerate(rows) if row.speed.country != "Configured" and row.health == "unchecked"
                  and row.index is not None and row.index.status == "index-match"]
    for done, i in enumerate(candidates[:metadata_count], 1):
        row = rows[i]
        emit("metadata", done - 1, min(metadata_count, len(candidates)), row.speed.country)
        try:
            metadata = audit_referenced(row.speed.url, row.speed.country, release,
                                        progress=lambda kind, n, total, bytes_done, size:
                                        emit("bytes", n, total, f"{kind}: {bytes_done}/{size} bytes"))
        except Exception as exc:
            metadata = AuditResult("error", f"Metadata check interrupted: {exc}", row.speed.url)
        rows[i] = MirrorHealth(row.speed, row.index, metadata)
        emit("metadata", done, min(metadata_count, len(candidates)), row.speed.country)
    return rows


def check_current_repository(release: str, repo: str = "fedora",
                             configured_base: str | None = None, progress=None):
    """Check one configured source without speed sampling or mirror discovery.

    Checks the Fedora reference index and the three selected referenced
    metadata files. This may transfer substantial data but does not download
    benchmark samples or access the alternative-mirror registry.
    """
    if repo not in ("fedora", "updates"):
        raise ValueError("Unsupported repository")
    if not configured_base:
        return []
    base = configured_base.strip().rstrip("/") + "/"
    if _base_from_metalink(base + "repodata/repomd.xml") != base:
        raise ValueError("Configured source must be a concrete HTTPS repository URL")
    def emit(phase, done, total, detail=""):
        if progress:
            progress(phase, done, total, detail)
    emit("current", 0, 1, base)
    # No 2 MiB x 3 samples: index retrieval is the availability check.
    index = _index_safely(MirrorResult(base, "Configured", "measured", None, None, 0,
                                      "Availability/index check only; speed not measured"),
                          release, repo)
    metadata = None
    if index.status in ("index-match", "different"):
        try:
            metadata = audit_referenced(
                base, "Configured", release,
                progress=lambda kind, n, total, done, size:
                emit("bytes", n, total, f"Current {kind}: {done}/{size} bytes"))
        except Exception as exc:
            metadata = AuditResult("error", f"Metadata check interrupted: {exc}", base)
    # A missing index is an actual failure, not an unverified speed result.
    status = "error" if index.status in ("missing", "error", "timeout") else "measured"
    detail = index.message if status == "error" else "Availability/index check only; speed not measured"
    speed = MirrorResult(base, "Configured", status, None, None, 0, detail)
    emit("current", 1, 1, base)
    return [MirrorHealth(speed, index, metadata)]
