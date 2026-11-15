# MirrorPilot — Testing and Field Validation

**Scope:** MirrorPilot pre-alpha `0.1.0a1`. This document separates **automated regression tests**, **reported hands-on Fedora testing**, and **untested assumptions**. See [DESIGN](DESIGN.md) for component boundaries.

## Test environments and evidence

- **Automated suite:** pytest tests in the repository, using mocks, synthetic repository metadata and temporary directories where appropriate.
- **Hands-on environment:** Fedora 44 KDE with DNF5, including actual `fedora` and `updates` repositories, DNF5 configuration overrides and PackageKit queries.
- **Latest reported local result (15 November 2026):** **242 passed, 1 skipped in 0.66 s**.
- This result was reported from the development workstation; it is **not** evidence of a clean CI run, cross-distribution compatibility, or independent reproduction.

## Running the tests

From the repository root in a Python 3.11+ environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -q
```

For focused tests, run a file or test name:

```bash
python -m pytest -q tests/test_manual_edit.py
python -m pytest -q tests/test_version_independent_urls.py
python -m pytest -q tests/test_dnf_effective.py
python -m pytest -q tests/test_config_conflicts.py
```

**Note:** check that these test paths exist in your checkout before copying them into automation; test modules may change during development.

Most automated tests should not require root privileges or real network access. Do not run the entire GUI or sandbox scripts under `sudo`. An optional Polkit smoke test has separate, explicitly documented installation steps in the project history and is not part of routine GUI operation.

## Regression areas

| Area | Expected invariant / failure case |
| --- | --- |
| Repository discovery | Reads .repo and DNF5 overrides; preserves raw `baseurl`; expands basic variables only for diagnostics |
| DNF5 effective values | Parses bounded `--dump-repo-config` output; handles empty values and malformed responses |
| Config origins | Reports multiple definitions without inventing a precedence order |
| Mirror discovery | Uses country-registered candidates; rejects missing/conflicting entries and unsafe URLs |
| Benchmark | Bounds candidate count, repetitions, and transferred bytes; handles timeouts |
| Index audit | Compares `repomd.xml` digest with the matching Fedora metalink |
| Referenced metadata | Verifies selected file hashes and sizes; handles missing files, corrupt digests, and download caps |
| Summary/GUI logic | Keeps configured-but-untested distinct from checked and verified |
| Change planning | Only supported Fedora repos/layouts; same installed/target release; no writes |
| Persistent URL | Converts known concrete Fedora layouts to `$releasever`/`$basearch` templates; rejects unknown layouts |
| Verify | Requires correct DNF5 effective source **and** stored variable-based URL; does not mistake expansion for hardcoding |
| Research-only recovery | Uses disposable fixtures; does not touch real `/etc` |

## Fedora 44 field-test case study

The following findings came from a real Fedora 44 KDE troubleshooting and development session. They illustrate why unit tests alone cannot establish correct behavior against live DNF5 and repository infrastructure.

### 1. Broken configured updates mirror

**Observed:** A configured FUNET updates mirror returned **HTTP 404** for referenced `primary.xml.zck` metadata and zchunk checksum-related errors occurred during DNF5 refresh.

**Diagnosis:** MirrorPilot checked repository metadata and identified an alternative that matched Fedora's index and referenced metadata checks.

**Manual validation:** A tested alternative was `https://mirror.23m.com/fedora/linux/updates/44/Everything/x86_64/`. After the user manually changed the DNF5 settings, `dnf5 --refresh check-update` returned **100**, with three updates listed. PackageKit's `pkcon get-updates` showed corresponding updates.

**Interpretation:** Exit code 100 means updates are available, not failure. This validates repository loading in that session, not the permanent health of the mirror.

### 2. Hardcoded Fedora release and architecture in a proposed command

**Observed:** An early configuration preview used a concrete `/44/Everything/x86_64/` URL. Persisting it would lock the setting to one release and architecture.

**Correction:** For supported Fedora `fedora` and `updates` URL layouts, the planner now emits `$releasever` and `$basearch` in the copied command. Unknown layouts are rejected.

**Regression expectation:** A hardcoded current URL can be upgraded to the equivalent template; an already configured template produces **“Proposed version-independent mirror is already configured.”**

**Boundary:** Variables do not guarantee that a particular mirror hosts a future Fedora release.

### 3. DNF5 variable expansion caused false Verify failures

**Observed:** The stored DNF5 override contained the correct literal `$releasever` and `$basearch`, but `dnf5 --dump-repo-config` displayed the expanded concrete URL. Comparing the two text forms made **Verify effective settings** incorrectly report a mismatch.

**Correction:** Verification now distinguishes the DNF5-resolved value from the raw stored `baseurl` and requires both to agree with the intended configuration.

**Regression expectation:** Expanded effective URL + stored template = success; expanded effective URL + stored hardcoded URL = not confirmed as version-independent; missing raw value = not confirmed.

### 4. Stale GUI repository state after manual changes

**Observed:** A user can change DNF5 settings outside MirrorPilot while the GUI remains open. A cached repository list can then produce misleading previews.

**Correction:** Refresh repository configuration before creating a change preview and when verification needs the stored URL.

**Regression expectation:** Re-read current configuration instead of relying on the application's startup snapshot.

### 5. Configured HTTPS source was not the same as a tested source

**Observed:** A source may be configured but not yet checked by **Check current**. Treating it as absent or healthy misleads users.

**Correction:** The summary distinguishes **configured HTTPS URL detected; not tested** from **no supported configured HTTPS base URL** and from a successfully checked current source.

### 6. Fedora release availability and architecture

**Observed risk:** A next-release availability probe that assumes `x86_64` may be wrong on another architecture.

**Correction:** Release discovery uses the host architecture rather than hardcoding it. Broader architecture support is **not yet demonstrated**, because other discovery paths and mirror layouts still require review.

## Manual acceptance checklist

Use a disposable or backed-up test environment for any manual DNF5 configuration changes. MirrorPilot itself should run without privileges.

- [ ] Start the GUI as a normal user; verify installed release and repository selector.
- [ ] Run **Check current** on a concrete HTTPS configured source; distinguish success, missing metadata, and timeout.
- [ ] Run **Find better mirrors**; check that measured speed is not presented as proof of metadata integrity.
- [ ] Inspect **Recommended** and verify it appears only after index and selected metadata checks pass.
- [ ] Inspect **Configuration origins…** and compare with DNF5 effective values; understand intentional overrides.
- [ ] Preview a verified same-release Fedora mirror command; check quoting and variable-based URL.
- [ ] Confirm that a cross-release configuration preview is blocked while cross-release diagnostics remain possible.
- [ ] Optionally run the command yourself and then use **Verify effective settings**.
- [ ] Confirm that an already configured template yields a no-change message.
- [ ] Confirm that no MirrorPilot action directly edits DNF configuration, cache, or installed packages.
- [ ] Test an offline or timed-out discovery; ensure errors remain explicit and no recommendation is invented.

## Interpretation and limitations

- **Passing pytest does not validate live MirrorManager responses**, actual network geography, mirror synchronization, or compatibility with every DNF5 version.
- **Index agreement** with a Fedora metalink is not proof that every referenced metadata file is available.
- **Referenced metadata checks** do not validate RPM signatures, every metadata kind, or future freshness.
- **DNF5 effective settings** can expand variables; stored configuration must be inspected separately when persistence matters.
- **Manual changes are outside MirrorPilot's transaction boundary.** Verification is not an automatic rollback.
- **Pre-alpha status remains appropriate** until reproducible testing across more Fedora releases, architectures and independent environments.

## Reporting regressions

Please include the MirrorPilot commit/version, Fedora release and architecture, DNF5 version, selected repository, action taken, sanitized output/errors, and whether the issue reproduces without changing system settings. Remove credentials, private URLs, and personally identifying paths from logs.

When recording a real-world case, separate **observed behavior**, **hypothesis**, **confirmed cause**, **code change**, and **post-fix test**. This prevents a plausible explanation from becoming an unsupported root-cause claim.
