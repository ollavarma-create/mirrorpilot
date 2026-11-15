"""Read-only unified diagnostics with explicit verification scope."""
from dataclasses import dataclass
from mirrorpilot.speed import benchmark, MirrorResult
from mirrorpilot.audit import audit, audit_referenced, AuditResult

BAD = {"different", "missing", "checksum-mismatch"}
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

def run_diagnostics(release: str, progress=None, metadata_count: int = 1, repo: str = "fedora"):
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
    speeds = benchmark(release, repo=repo, progress=lambda done, total: emit("benchmark", done, total))
    rows = []
    for i, speed in enumerate(speeds, 1):
        index = audit(speed.url, speed.country, release, repo=repo) if speed.status == "measured" else None
        rows.append(MirrorHealth(speed, index))
        emit("index", i, len(speeds), speed.country)
    # Verify fastest mirrors whose indexes match. Other rows remain unchecked.
    candidates = [i for i, row in enumerate(rows) if row.health == "unchecked"
                  and row.index is not None and row.index.status == "index-match"]
    for done, i in enumerate(candidates[:metadata_count], 1):
        row = rows[i]
        emit("metadata", done - 1, min(metadata_count, len(candidates)), row.speed.country)
        metadata = audit_referenced(row.speed.url, row.speed.country, release,
                                    progress=lambda kind, n, total, bytes_done, size:
                                    emit("bytes", n, total, f"{kind}: {bytes_done}/{size} bytes"))
        rows[i] = MirrorHealth(row.speed, row.index, metadata)
        emit("metadata", done, min(metadata_count, len(candidates)), row.speed.country)
    return rows
