# MirrorPilot

Graphical repository and mirror diagnostics for DNF5-based Linux distributions.

> Experimental pre-alpha (0.1.0a1). **Read-only:** no repository configuration or installed packages are modified.

## Goal

Make DNF5 software sources understandable from a Qt graphical interface. MirrorPilot aims to identify unreachable, incomplete, inconsistent and stale mirrors before attempting distribution upgrades.

## Current proof of concept

- List repositories offline from `.repo` files and DNF5 override fragments.
- Inspect effective repository source URLs as reported by DNF5.
- Optionally query the configuration for another Fedora release using `--releasever`.
- Check one direct, concrete HTTPS base URL by retrieving `repodata/repomd.xml`, checking referenced metadata files and validating SHA-256/SHA-512 checksums.
- On demand, benchmark up to 8 Fedora base mirrors returned by country-filtered MirrorManager (FI, SE, EE, DE, NL, DK), using up to 2 MiB of primary/filelists metadata per mirror, with a separate time-to-first-byte measurement.\n- Perform potentially slow operations in background Qt threads.

**Limitations:** DNF5's human-readable CLI output is not a stable API, and must be checked on actual Fedora installations. This alpha only expands basic DNF variables, does not reproduce every DNF5 precedence rule, and does not compare freshness against upstream or edit settings. The speed test uses a small bounded transfer, so results include connection latency and are not sustained bulk throughput. MirrorManager's country filter does not guarantee the physical location of a server. Speed results do not prove metadata integrity. Hash verification demonstrates internal consistency, not freshness or publisher authenticity. Downloads have per-file limits.

## Run on Fedora KDE

Requires Python 3.11+, DNF5, and Qt/PySide6.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
mirrorpilot
```

For tests:

```bash
python -m pip install -e '.[test]'
pytest -q
```

## Roadmap

1. Read-only DNF5 discovery and metadata diagnostics
2. Robust effective DNF5 configuration and variable expansion
3. Mirror discovery, validation, freshness and speed comparison
4. Explicitly authorized settings changes with previews and rollback
5. Release-upgrade preflight and distribution-specific adapters

## Safety

MirrorPilot must not silently change DNF configuration or update installed software. Future writes must use documented DNF5 configuration interfaces, explicit authorization, validation and rollback. Geographic origin cannot be guaranteed by IP geolocation alone.

## License

GPL-3.0. See LICENSE.

## Mirror benchmark safety (experimental)

The MirrorManager country filter is not a security boundary: a previous test returned a Russian Yandex mirror despite selecting FI, SE, EE, DE, NL and DK. For now the benchmark **only contacts three explicitly curated HTTPS hostnames**: `www.nic.funet.fi` (FI), `mirrors.xtom.ee` (EE) and `mirror.dogado.de` (DE). Other candidates are rejected before network access. The host-to-country labels are operator/domain assumptions, **not independently verified physical locations**. A future release should obtain trustworthy mirror-location metadata and allow user review of the candidate list. No arbitrary host is probed.

The test downloads the small `repomd.xml` index to locate larger metadata, then streams at most 2 MiB of a metadata file, measuring time-to-first-byte and transfer throughput separately. A range request is sent but a server may ignore it; the client still stops after the byte cap. This is an indicative single-stream measurement, not a package-download simulation, and **does not verify metadata integrity or freshness**. The separate metadata-check feature is intended for that purpose.

## Dynamic MirrorManager inventory (experimental)

The benchmark now fetches the live Fedora MirrorManager public inventory (country and mirror hostname) and separately obtains release-specific metalink URLs. Only exact hostname matches with registered countries FI, SE, EE, DE, NL or DK are tested; missing, conflicting or unexpected entries are skipped. No mirror hostnames are hardcoded. This is registered country, not independent physical geolocation. MirrorManager's public inventory may be incomplete or inconsistent with the metalink, so an empty list is possible and fails closed. Up to eight matching mirrors are measured three times each, using median transfer throughput and time to first byte. The GUI displays a comparison table. This is not yet a complete verification of repository metadata integrity or freshness.

## Experimental index consistency audit

After a benchmark, select one mirror row and choose **Audit selected mirror index against Fedora metalink**. The audit downloads the current Fedora metalink and the selected mirror's `repodata/repomd.xml` and compares the manifest's SHA-256 or SHA-512 digest against the metalink's reference. `index-match` means the repository index matches this reference at the time of the check. `different` can mean lag, a changing repository or other inconsistency; it is not proof of malicious content. This is **not** a full metadata/package checksum or signature verification, and does not prove freshness of all referenced files. The audit is opt-in, read-only and limited to the selected benchmark mirror. DNF settings and caches are untouched.

## Referenced metadata verification (experimental)

After benchmarking, select a mirror and click **Verify referenced metadata**. This separate opt-in read-only check fetches the selected mirror's `repomd.xml` and up to three referenced `primary`, `filelists` and `other` metadata files, each limited to 32 MiB. It validates SHA-256/SHA-512 digests and distinguishes missing HTTP resources, checksum mismatch and size limits. Large metadata files are reported as `too-large` (inconclusive), not corrupt. The audit does not check every metadata type, signatures or repository freshness, and does not modify DNF caches or configuration. Use the index audit separately to compare with Fedora's current metalink reference.
