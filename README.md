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

## Streaming metadata verification

The referenced-metadata check now streams SHA-256/SHA-512 over 256 KiB chunks rather than loading each entire file into RAM. The safety cap is 512 MiB **per file**, with a 12-second network operation timeout and a 120-second elapsed-time check between reads. It compares the compressed file size with the optional `repomd.xml` declared size and shows file number, name and downloaded MiB on the button. The cap prevents excessive transfers; large files are not automatically treated as corrupt. A blocking network read may exceed the elapsed-time limit until its socket timeout fires. This is a read-only check; no DNF files or caches are modified.

## Unified health view (experimental)

**Run diagnostics** measures up to eight country-approved mirrors, checks each measured mirror's Fedora metalink index checksum, then verifies the three selected metadata kinds for **only the fastest index-matching mirror**. This conservative default prevents downloading up to ~12 GiB without explicit consent. Additional mirrors can be verified individually with **Verify selected mirror metadata** (up to 512 MiB per file). The selected row shows full diagnostics. Red indicates a detected issue, amber an inconclusive check, grey unverified, and green a verified subset. A **Recommended** label appears only after both index and referenced-metadata checks pass; it is not a claim of full repository or RPM signature validation. The GUI does not modify DNF configuration or caches. Fedora release 44 `fedora` repositories are tested by default; Fedora 45 `updates` is not yet included in this combined workflow.

## Fedora 45 updates diagnosis

Select **Fedora updates** under **Repository to diagnose**, enter `45` in **Fedora release**, and choose **Run diagnostics**. This uses Fedora MirrorManager's `updates-released-f45` metalink, not the `fedora-45` release metalink. It measures up to eight registered, country-approved mirrors, compares each `repomd.xml` with the matching updates reference, and streams the three selected metadata kinds from the fastest index-matching mirror. The original configured FUNET URL is not automatically among these eight: use **Check selected repository URL (advanced)** on the configured repository to investigate that exact source. Differences in a rapidly changing updates repository may reflect a transient synchronization window; recheck before treating them as persistent failures. All operations are read-only.

A settings gear, adjustable mirror count and CLI are planned for later; the current cap remains eight.

## Installed Fedora, release selection, and configured source (experimental)

The UI detects the installed Fedora version from \`/etc/os-release\`. It checks the next release's official Fedora release metalink asynchronously and offers it in a dropdown when published; this is **not** an assertion that an upgrade is safe or supported. When offline, only the installed version is shown. Choosing a release refreshes the read-only repository preview with \`$releasever\` expanded for that target.

A unified diagnostics run checks the enabled, concrete HTTPS \`baseurl\` of the selected \`fedora\` or \`updates\` repository **first**, even when it is not registered in the approved-country inventory. It is labeled **Configured**, never assigned an invented country. It compares the index to the target release's official metalink and checks referenced metadata even when the index differs. It then benchmarks up to eight country-approved alternative mirrors and verifies the fastest index-matching alternative. This can download significant metadata (up to three 512 MiB files per verified source). A missing/unsupported configured source is clearly reported as not tested, rather than assumed healthy. This is a conservative configuration-file parser, not complete libdnf5 effective-state resolution; metalink/mirrorlist-only configured sources are not yet checked as the current mirror.
