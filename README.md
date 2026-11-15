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


## Two-step read-only workflow

**Check current repository** checks only the selected configured HTTPS base URL. It does not fetch the MirrorManager inventory or benchmark alternatives. It checks the Fedora reference index and, when the index is available, streams the selected referenced metadata (up to three files, 512 MiB per file); it can therefore take time even without speed samples. No speed is reported for this mode.

**Find better mirrors** is the explicit, more network-intensive comparison: up to eight country-approved alternatives (the configured source is excluded), with bounded speed samples, index comparisons, and metadata verification on the fastest matching alternative. The most recent configured-source check is retained in the summary when the release, repository and URL still match. Neither action changes DNF configuration, cache, or packages. For metalink/mirrorlist-only configured repositories, the current-only check reports no supported concrete base URL rather than inventing one.

## Compact GUI and future configuration changes

The installed release, target release and repository selector share the top toolbar. Repositories are loaded automatically on startup and when the target release changes; a small refresh control remains for rereading files after external changes. The top row offers **Check current**, **Find better mirrors** and **Check selected (advanced)**, with explanatory tooltips. Optional **Verify selected metadata** is beside the Details area. All these controls remain read-only.

**Planned, not implemented:** a separate, clearly labeled **Apply changes…** workflow. It must first present the exact current configuration and proposed diff, back up affected original files with their paths and permissions, require explicit confirmation and appropriate authorization (Polkit), apply changes atomically, validate the resulting DNF configuration and provide a tested rollback/restore path. No automatic replacement of a failing configured source or silent writes are permitted. The UI must distinguish diagnostic recommendations from actions that modify the system.

### Read-only change preview (first implementation stage)

Select a **verified** alternative in the mirror results and choose **Preview configuration change…**. MirrorPilot builds a constrained proposal for the Fedora `fedora` or `updates` repository, showing the current URL, proposed URL, and intended override section. The preview is pure and performs **no write, backup, authorization or DNF operation**. Unverified mirrors cannot be proposed through this button.

The proposed `/etc/dnf/repos.override.d/99_mirrorpilot.repo` is a *design target*, not an installed file. Existing overrides, DNF5 precedence, repository consistency and the security of an eventual privileged helper must be independently verified before implementing the actual write path. In particular, a helper must never trust GUI-provided paths, must revalidate the target, must back up the real pre-change state, and must support atomic rollback. No `pkexec` helper is installed or invoked yet.

### Cross-release safety boundary

The selected **Diagnose release** is for read-only investigation, not permission to change the installed Fedora release. A configuration change plan is allowed only when the diagnostic release is a known numeric release **equal to the installed Fedora release**. Otherwise the GUI displays a diagnostic-only warning instead of a DNF override proposal. This rule is also enforced in `changes.build_change_plan()`, with automated mismatch/unknown-version tests.

For example, Fedora 44 users may benchmark Fedora 45 mirrors, but cannot use MirrorPilot to configure those Fedora 45 mirrors as active Fedora 44 repositories. System upgrades must use Fedora's official upgrade procedure. The future privileged helper must **independently re-read the installed release and validate the repository target**, and must not rely on the GUI or this unprivileged preview for authorization.

### Experimental transaction tests (sandbox only)

`mirrorpilot/sandbox_transaction.py` is a **non-privileged, test-only prototype**. It models a before-image snapshot, temporary-file replacement, verification and rollback, including restoring the absence of a file. Tests use pytest's temporary directories; **the GUI does not call this code**, and it cannot be pointed at `/etc`.

Run `python -m pytest -q tests/test_sandbox_transaction.py` to check rollback scenarios. This prototype is **not suitable for privileged execution**: it has filesystem race windows, holds backups in memory, and does not preserve ownership, ACLs, SELinux labels or durable backup history. The eventual Polkit helper will need root-owned durable snapshots, fd-relative/no-follow path handling, secure atomic commits with directory fsync, independent release checks, DNF5 precedence validation and recovery tests before any real system write is enabled.

### Durable journal and crash-recovery sandbox tests

`mirrorpilot/durable_sandbox.py` adds a **test-only** persistent before-image journal with states `PREPARED`, `APPLIED`, and `VERIFIED`. Before replacing the sandbox target, the journal is atomically persisted and fsynced. A new process can call `recover()` to restore the original file (or its previous absence) if the journal remains unfinished. A verified transaction remains in place until explicit journal cleanup. The module intentionally models crashes between target replacement and journal advancement.

Run `python -m pytest -v tests/test_durable_sandbox.py`. All tests operate under pytest temporary directories. This is **not a production crash-safe root writer**: there is no process lock, no protection from adversarial filesystem races, no root-owned backup store, no SELinux/ACL/ownership restoration, and no DNF5 post-write verification. In particular, it is not wired into the GUI or Polkit and must not be used to edit real repositories.

### Optional Polkit authorization smoke test (Fedora KDE)

This stage tests **authentication only**. It does not modify DNF, repository files or system configuration beyond explicitly installing the test helper and its Polkit policy. The GUI remains unprivileged; there is **no Apply button** yet.

After reviewing the two files under `packaging/polkit/`, install them using these commands from the repository root:

```bash
sudo install -o root -g root -m 0755 packaging/polkit/mirrorpilot-auth-probe /usr/libexec/mirrorpilot-auth-probe
sudo install -o root -g root -m 0644 packaging/polkit/org.mirrorpilot.auth-probe.policy /usr/share/polkit-1/actions/org.mirrorpilot.auth-probe.policy
```

Run `pkexec /usr/libexec/mirrorpilot-auth-probe` as the **normal desktop user**, without sudo. KDE should request administrator authentication. After successful authentication the helper prints:

```json
{"protocol": "mirrorpilot-auth-probe-v1", "authorized": true, "effective_uid": 0, "writes": false}
```

The exact JSON whitespace is unimportant. Canceling the dialog should fail without printing a success response. The test helper accepts no command-line arguments and performs no writes.

To uninstall **only this probe**:

```bash
sudo rm -f /usr/libexec/mirrorpilot-auth-probe /usr/share/polkit-1/actions/org.mirrorpilot.auth-probe.policy
```

Run `python -m pytest -q tests/test_polkit_probe.py` for parser tests. This is an optional local integration test, not an automatic installation. Do not invoke the entire MirrorPilot GUI through `pkexec` or `sudo`. The eventual production helper will be separate and require independent authorization and input validation.

### DNF change request protocol (validation-only)

`mirrorpilot/apply_protocol.py` defines a size-limited JSON request with an exact field allowlist: protocol, operation (`preview` only), repository (`fedora` or `updates`), release and concrete HTTPS mirror URL. Arbitrary target paths, unknown fields and `apply` operations are rejected. A separate release check requires equality with the installed Fedora release. This is **not** a privileged writer, and no new authorization or GUI Apply path has been enabled.

Run `python -m pytest -q tests/test_apply_protocol.py`. Before a production helper can write anything, it must recheck all inputs and DNF5's effective configuration under root, securely bind the verified mirror to the requested repository, and implement root-owned backup/rollback and crash recovery.

### Configuration origins (read-only)

Use **Configuration origins…** in the main window to inspect where the selected repository's `enabled`, `baseurl`, `metalink`, `mirrorlist`, and `proxy` values appear in `/etc/yum.repos.d/*.repo` and `/etc/dnf/repos.override.d/*.repo`. Select a configured repository row first; otherwise the repository dropdown is used. Click **Show Details** in the resulting dialog to view paths, values, and notes.

Repeated identical values are distinguished from differing definitions. A differing definition is **not automatically an error**: it can be an intentional override. This conservative file-level inspection does **not** establish DNF5's actual effective precedence, handle every DNF5 configuration source, or authorize writes. Malformed files and uncertain source combinations are reported rather than silently repaired.

Run `python -m pytest -q tests/test_config_conflicts.py`. Next: compare these observations with libdnf5's authoritative effective configuration and add explicit uncertainty reporting before enabling any Apply operation.

### Effective DNF5 values (read-only)

The **Configuration origins…** dialog also queries `dnf5 --dump-repo-config=<repo-id>` and shows the effective settings beside file-level definitions. This avoids requiring usable repository metadata or network access. The query uses a validated repository ID, a shell-free subprocess, and an 8-second timeout. If DNF5 cannot provide values, the dialog still shows the file evidence and an explicit error.

Effective values confirm what DNF5 resolves, **not** which particular file supplied each value. Do not interpret differing file definitions as proven errors or use this display to authorize privileged changes. Run `python -m pytest -q tests/test_dnf_effective.py`.

## Future privileged writer boundary (not enabled)

The GUI now previews a strictly limited request for either `fedora` or
`updates`: a single HTTPS base URL and clearing the corresponding metalink.
`mirrorpilot/write_policy.py` validates request shape and rejects arbitrary
DNF options, shell commands, paths, non-HTTPS URLs, credentials, and unsafe
characters. This is **request-shape validation**, not a guarantee that the
mirror is trusted: the existing metadata checks and release checks remain
mandatory. Country-domain suffix checks are not a security trust anchor.

**There is no privileged writer in this change.** The GUI stays read-only,
and the existing Polkit authorization probe remains read-only. Before adding
a privileged helper we must design a fixed-operation IPC protocol, validate
requests again on the privileged side, use trusted executable paths, prevent
symlink/path races, serialize writes against other DNF configuration changes,
preserve file metadata, and prove durable recovery. Never pass GUI-generated
shell commands or filesystem paths to a root helper.

## Minimal helper protocol prototype (unprivileged, no writes)

`mirrorpilot/helper_protocol.py` defines a versioned JSON request with
**exactly** four fields: `version: 1`, `action: "set-mirror"`,
`repository: "fedora" | "updates"`, and a validated `baseurl`.
Unknown fields, duplicate keys, unsupported actions and oversized requests
are rejected. The parser constructs a fixed DNF5 argument vector for
inspection, but **does not execute it**.

Try the unprivileged dry-run entry point:

```bash
printf '%s' '{"version":1,"action":"set-mirror","repository":"fedora","baseurl":"https://mirrors.xtom.ee/fedora/releases/44/Everything/x86_64/os/"}' | python -m mirrorpilot.helper_dry_run
python -m pytest tests/test_helper_protocol.py -v
```

The dry-run explicitly refuses execution as root. It does not invoke Polkit,
DNF5, or change any configuration. A production privileged helper must
revalidate all fields, constrain process environment and execution, ensure
trusted inputs and filesystem boundaries, implement durable pre-write recovery,
and verify effective DNF5 values before any writes are enabled. The
argument vector is **not** a shell command and must never be executed through
a shell. The existing sandbox recovery experiment is not a production writer.

## Restart-recovery regression suite (sandbox only)

```bash
python -m pytest tests/test_dnf_restart_recovery.py -v
python -m pytest -q
```

The sandbox transaction now optionally stores an independently predicted
SHA-256 in the durable `PREPARED` journal **before** launching its confined
writer. A fresh Python interpreter can recover the original bytes if the
interrupted output exactly matches the prediction. Unknown, partially written,
or third-party-modified contents are left untouched for manual review.
Legacy journals without a prediction remain conservative.

**Not a production recovery guarantee:** predicting the DNF5 output requires
an isolated fixture and independent verification; file permissions, ownership,
ACLs, SELinux labels, symlink-safe paths, locking, journal integrity, power-loss
durability, and privileged execution remain separate work. No host settings
are changed by this suite.

## Filesystem identity threat-model tests (read-only)

```bash
python -m pytest tests/test_fs_identity_probe.py -v
python -m pytest -q
```

The probe uses Linux `open` with `O_NOFOLLOW`, `O_DIRECTORY`,
directory-relative `dir_fd`, and `fstat` to detect inode or directory
replacement between observations. Tests cover same-content atomic replacement,
directory swaps, symlinks, hardlinks, FIFO and invalid basenames.

**Important limitations:** These are observational tests, not an atomic
filesystem guard. The probe does not pin or validate every parent directory,
verify trusted ownership, prevent post-check replacement, or constrain the
external DNF5 writer. In particular, no preflight inode check alone closes
the TOCTOU window when DNF5 subsequently opens a pathname. Do not use the
probe to authorize a production write. The production helper remains blocked.

## DNF5 hybrid atomic-install experiment (sandbox only)

Run as an ordinary user (never sudo):

```bash
python scripts/test_hybrid_dnf_sandbox.py
```

DNF5 config-manager renders an override in a disposable Bubblewrap fixture.
The generated bytes are then installed into a **different** temporary directory
using the existing durable sandbox transaction. Simulated termination at
PREPARED, TARGET_REPLACED and APPLIED is followed by recovery from a newly
constructed transaction object. Successful verification and rejected
verification are also tested. The original bytes and mode are checked.

This experiment does **not** prove power-loss safety or production security:
no privileged writes, actual SIGKILL, SELinux/ACL/xattr handling, concurrent
external writers, hostile filesystem race or libdnf5 version portability is
tested. The existing durable sandbox transaction can overwrite third-party
changes during recovery and must **never** be used on real /etc. The GUI
remains read-only and the privileged helper remains unimplemented.
