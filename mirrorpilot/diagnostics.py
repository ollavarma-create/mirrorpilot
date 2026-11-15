"""Read-only unified diagnostics with explicit verification scope."""
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
import socket
from mirrorpilot.speed import benchmark, MirrorResult, probe, _base_from_metalink
from mirrorpilot.audit import audit, audit_referenced, AuditResult

BAD = {"different", "missing", "checksum-mismatch"}


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
