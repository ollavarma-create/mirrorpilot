# MirrorPilot — Architecture and Design

**Status:** experimental pre-alpha (`0.1.0a1`). This document describes the implemented read-only GUI and distinguishes it from research-only code. See [README](../README.md) for user instructions and [TESTING](TESTING.md) for verification.

## Design goals and trust boundaries

MirrorPilot exists to make Fedora DNF5 repository failures diagnosable without giving the diagnostic tool authority to repair the system. It distinguishes four questions:

1. **What source is configured?** Local repository files and DNF5's resolved options.
2. **Can the source be reached?** HTTP/network responses from the configured mirror.
3. **Does the mirror agree with Fedora's repository reference?** `repomd.xml` compared with the appropriate Fedora metalink checksum.
4. **Are selected files referenced by the index actually available and consistent?** Streaming checks of their digests.

Only after these checks can the GUI present a *candidate* configuration command. **The user—not MirrorPilot—executes any privileged operation.** Passing checks does not prove that the mirror will remain healthy, that every RPM is valid, or that an operating-system upgrade is safe.

## Component map

| Component | Responsibility | Boundary |
| --- | --- | --- |
| `mirrorpilot/app.py` | PySide6 GUI, asynchronous workers, action selection, results, and dialogs | User interface; no privileged DNF writes |
| `mirrorpilot/repos.py` | Read `.repo` files and override fragments; expand basic release/architecture variables | Conservative parser, not full libdnf5 |
| `mirrorpilot/config_conflicts.py` | Show where selected options are declared and where definitions differ | Does not infer authoritative precedence from file order |
| `mirrorpilot/dnf_effective.py` | Read `dnf5 --dump-repo-config=<repo>` via a bounded subprocess | DNF5-resolved options, not file provenance or mirror health |
| `mirrorpilot/releases.py` | Detect installed Fedora release and probe next release's published metalink | Publication does not imply supported upgrade |
| `mirrorpilot/speed.py` | Discover eligible alternatives using MirrorManager inventory/metalink; bounded benchmark | Indicative speed and registered country only |
| `mirrorpilot/diagnostics.py` | Coordinate current-source checks, alternative benchmarking, index and metadata checks | Explicit verification scope |
| `mirrorpilot/audit.py` | Compare index digest with Fedora metalink; stream and hash referenced metadata | Selected metadata only; no RPM signature verification |
| `mirrorpilot/check.py` | Independent bounded HTTPS base-URL metadata consistency check | Internal consistency, not publisher authenticity |
| `mirrorpilot/summary.py` | Present current/alternative status and uncertainty | Never promote untested sources to verified |
| `mirrorpilot/changes.py` | Validate proposed URL, installed release, Fedora path layout; construct command preview | Pure change planning; no writes |
| `mirrorpilot/manual_edit.py` | Explain user-run DNF5 command and verify effective + stored settings | Read-only verification; no rollback |

## Main diagnostic flows

```text
Local .repo files + override fragments ──> Configured repositories (GUI)
                  │                                   │
                  └──> DNF5 --dump-repo-config ────────┤
                                                      │
                      ┌───────────────────────────────┴─────────────────┐
                      │                                                 │
                Check current                                  Find better mirrors
                      │                                                 │
          Configured direct HTTPS baseurl                   Fedora metalink + registry
                      │                                                 │
          Fedora reference index                         Approved candidate hosts
                      │                                                 │
          Index + selected metadata                      Bounded speed samples
                      │                                                 │
               Current-source result                      Index comparison for candidates
                                                                        │
                                                        Selected metadata for fastest
                                                        index-matching alternative
                                                                        │
                                                        Verified alternative, if any
                                                                        │
                                                        User-run command preview
                                                                        │
                                               User executes command outside GUI
                                                                        │
                                               Read-only effective-settings Verify
```

The current-source check does **not** benchmark speed. Alternative discovery deliberately excludes the configured source. GUI network operations run in Qt worker threads to keep the interface responsive.

### Discovery and speed

The alternative inventory is derived from Fedora's live MirrorManager data. The supported registered country set is **FI, SE, EE, DE, NL, DK**. A hostname must have an unambiguous country entry; unknown or conflicting entries are skipped. Up to **eight** mirrors are benchmarked, with **three** bounded samples per mirror, each transferring at most **2 MiB** of selected metadata. Time-to-first-byte and transfer throughput are reported separately, using median-based comparison.

The registered country is not independent proof of server location. Benchmark numbers are indicative, not sustained package download speeds. MirrorManager can be unavailable, incomplete, or temporarily inconsistent with a release metalink.

### Index and metadata integrity

For the selected Fedora release/repository, `audit.py` obtains Fedora's metalink checksum and compares it to the selected mirror's `repodata/repomd.xml` (SHA-256 or SHA-512). An **index-match** means agreement with that reference at the time of the check.

Referenced verification examines up to three metadata kinds: **primary, filelists, other**. Files are streamed in **256 KiB chunks**, with a **512 MiB per-file cap**, a **12-second network timeout**, and a **120-second elapsed-time check** between reads. Declared sizes are checked when available. Size limits, timeouts and unavailable resources must not be misreported as successful verification. A blocking socket read may extend beyond the elapsed-time threshold until its network timeout.

The `MirrorHealth` classification is **verified** only when the index and selected metadata checks both pass. It can also be **unchecked**, **uncertain**, **problem**, or **error**. In the combined alternatives flow, the default is to verify selected metadata for **only the fastest index-matching alternative**; other mirrors can be checked explicitly.

**Security meaning:** These checks do not verify RPM signatures, every referenced metadata kind, the publisher's identity independently, or future repository freshness. A checksum match and an HTTPS connection do not by themselves authorize privileged changes.

## Repository configuration and variable expansion

`repos.py` reads `/etc/yum.repos.d/*.repo` and `/etc/dnf/repos.override.d/*.repo`. It preserves the **raw stored baseurl** separately from the **expanded diagnostic URL**. The parser expands basic `$releasever`, `$basearch`, and `$arch` forms for display and diagnostics, but is not a complete implementation of DNF5 configuration precedence.

`dnf_effective.py` invokes DNF5 directly for the resolved values. Crucially, DNF5 can expand variables in `--dump-repo-config`, so an effective URL containing `/44/Everything/x86_64/` does not establish whether the stored configuration is hardcoded or uses variables.

For a validated Fedora `fedora` or `updates` mirror, `changes.py` converts only **known Fedora repository path layouts** into a persistent template:

```text
/releases/44/Everything/x86_64/os/
    -> /releases/$releasever/Everything/$basearch/os/

/updates/44/Everything/x86_64/
    -> /updates/$releasever/Everything/$basearch/
```

Unknown URL layouts fail closed; no generic string substitution is attempted. The user-run command is shell-quoted to preserve DNF variables. A template is **not proof** that the host provides future releases.

Verification checks **both** the DNF5 effective `baseurl` (which may be expanded), empty `metalink`/`mirrorlist`, **and** the stored variable-based `raw_baseurl`. If the effective source matches but the stored form cannot be confirmed, verification is inconclusive rather than falsely successful. If the template is already configured, the change planner reports that no change is needed.

## Safety invariants

- **No root GUI:** MirrorPilot runs as a normal user and does not invoke Polkit to modify repository settings.
- **No implicit mutation:** diagnostics, preview, copying, and verification do not write DNF configuration, caches, or packages.
- **Cross-release isolation:** a proposed configuration command is permitted only when installed and target Fedora releases are known numeric values and **identical**. Read-only diagnostics may target a different release.
- **Restricted proposals:** only the `fedora` and `updates` repositories and validated concrete HTTPS mirror directory URLs are supported. The persistent URL must match a known Fedora layout.
- **Manual privilege boundary:** only the user can choose to run the displayed `sudo dnf5 config-manager setopt` command. The GUI provides no automatic rollback or transactional guarantee.
- **Network safeguards:** bounded downloads, timeouts, and refusal of cross-host/insecure redirects for metadata requests reduce exposure but do not eliminate network risk.

## Research-only modules: NOT a production writer

The repository also contains sandbox transaction/recovery experiments, a helper-request protocol, a filesystem identity probe, and an optional Polkit authorization smoke test. These are deliberately **not integrated with the GUI**. They do not provide a production-safe privileged update path.

A future privileged implementation would need independent input and installed-release validation, safe filesystem access, concurrency control, durable backups and rollback, SELinux/ACL/ownership preservation, and independent DNF5 post-write verification. None of those safeguards should be inferred from the existence of sandbox tests.

## Known limitations and next steps

- The repository-file parser is conservative and may differ from libdnf5 in complex configurations.
- Current-source diagnosis requires a supported concrete HTTPS `baseurl`; metalink/mirrorlist-only sources cannot be directly tested as that configured URL.
- Network failures, mirror synchronization windows, and per-file limits can yield inconclusive results.
- Release availability checks are not upgrade-readiness checks.
- Architecture is derived from the host for release discovery and local expansion; review remaining architecture-specific metalink/discovery assumptions before claiming broad non-x86_64 support.
- Extend testing across Fedora releases, architectures, network conditions, and non-KDE desktops before promoting pre-alpha status.

See [TESTING](TESTING.md) for reproducible checks and field-test findings.
