# MirrorPilot

**Read-only Fedora DNF5 mirror diagnostics, with a graphical interface.**

MirrorPilot helps you investigate slow or broken Fedora repository mirrors, compare alternatives, and review a DNF5 configuration command **before deciding whether to run it yourself**. It does not install packages, change repositories, modify DNF caches, or request administrator privileges.

> **Status:** experimental pre-alpha (`0.1.0a1`). Tested on Fedora 44 KDE; other releases and environments need further validation. The project is not affiliated with the Fedora Project.

![MirrorPilot main window showing Fedora repositories, tested mirrors, and diagnostics](docs/images/mirrorpilot-main.png)

*Mirror comparison and diagnostic results.*

## Why MirrorPilot?

A mirror can respond quickly yet serve missing or inconsistent repository metadata. A configured mirror can also fail while another mirror works. MirrorPilot separates **availability**, **indicative transfer speed**, **repository index consistency**, and **referenced metadata checks**, instead of treating a fast response as proof of a healthy repository.

In a Fedora 44 field test, a configured updates mirror returned HTTP 404 for referenced metadata. A separately checked alternative provided consistent metadata, and DNF5 subsequently loaded the repositories and listed available updates. This is an example, not a guarantee that the same mirror will work for everyone.

## What it does

- **Inspect repositories:** show configured Fedora repositories and their effective DNF5 sources; inspect configuration origins and potential overrides.
- **Check current:** diagnose a configured, direct HTTPS `baseurl` without searching for alternatives.
- **Find better mirrors:** discover eligible mirrors through Fedora MirrorManager, measure bounded transfers, and compare repository indexes with the relevant Fedora metalink.
- **Verify selected metadata:** check selected referenced metadata files against digests in `repomd.xml`. A recommended alternative has passed the application's index and selected metadata checks.
- **Preview a DNF5 command:** generate a copyable, **user-run** command for a verified Fedora `fedora` or `updates` mirror, using `$releasever` and `$basearch` rather than locking the URL to one Fedora release.
- **Verify settings:** compare DNF5's effective values with the intended mirror and check that the saved URL remains variable-based.

The **Installed** Fedora version comes from the system; **Diagnose release** selects which release to inspect. Testing another release is allowed, but generating a configuration change for a release other than the installed one is blocked.

## Install and run

Requires Linux with DNF5, Python 3.11+, and Qt/PySide6. The primary development and field-test environment is Fedora KDE.

From a clone of this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
mirrorpilot
```

No `sudo` is needed to run MirrorPilot. If you already have a local checkout, update it with `git pull` before installing or running.

## Quick start

1. Select **Diagnose release** (normally the installed Fedora version) and **Repository** (`Fedora` / `Fedora updates`).
2. Click **Check current** to investigate your configured direct HTTPS source, or **Find better mirrors** to discover and compare alternatives.
3. Inspect the results and details. A fast mirror is not necessarily a verified mirror; only a checked alternative can be marked **Recommended**.
4. Select a verified alternative and click **Copy DNF5 configuration command…**. Read the command and inspect **Configuration origins…** before applying it.
5. If you choose to change the configuration, run the copied command **yourself** in a terminal, then use **Verify effective settings**.

![MirrorPilot dialog showing the copyable DNF5 configuration command](docs/images/mirrorpilot-command.png)

*Review and copy the DNF5 command before making changes yourself.*

### Example: a manual DNF5 command

The following is **illustrative**, not a universal mirror recommendation. Use the URL from your own verified diagnostic result.

```bash
sudo dnf5 config-manager setopt \
  'updates.baseurl=https://mirror.example.org/fedora/linux/updates/$releasever/Everything/$basearch/' \
  updates.metalink= \
  updates.mirrorlist=
```

The single quotes preserve the DNF variables. DNF5's config-manager manages its override; do **not** manually edit the generated `99-config_manager.repo` as the normal workflow. MirrorPilot only displays and copies the command—it never executes it.

After a user-run change, you can check repository loading with:

```bash
dnf5 --refresh check-update
echo "DNF5 exit code: $?"
```

For `dnf5 check-update`, exit code **100** means updates are available, **0** means no updates are available, and **1** indicates an error. A working Fedora 44 mirror does not prove that the same server carries Fedora 45.

![MirrorPilot successful DNF5 effective-settings verification dialog](docs/images/mirrorpilot-verification.png)

*Check effective DNF5 settings after running the command.*

## What the results mean

| Result | Interpretation |
| --- | --- |
| **Measured speed** | Indicative performance of bounded sample transfers, not sustained package-download speed |
| **index-match** | The mirror's `repomd.xml` digest matched the Fedora metalink reference during the check |
| **metadata-match** | Selected referenced metadata files passed the digest checks |
| **Recommended** | An alternative passed the index and selected metadata checks; not a full security certification |
| **Current source: not tested** | The current source was not checked in this run, or no supported concrete HTTPS `baseurl` could be identified |
| **Different / unavailable / inconclusive** | Inspect the details; a changing repository, timeout, size cap, or synchronization delay can affect results |

**Important limitations:** The tool does not verify RPM signatures, establish publisher authenticity independently, check every metadata type, guarantee repository freshness, or certify future mirror availability. The mirror country is based on MirrorManager registry data, **not independent physical geolocation**. Discovery and network operations can time out. The current-source parser does not implement every libdnf5 precedence rule, and metalink-only sources are not directly tested as a configured base URL.

## Safety and scope

MirrorPilot is **read-only** with respect to the host's DNF configuration, installed packages, and caches. It uses network access for diagnostics and can download substantial metadata during explicit verification. By default, it verifies selected metadata for only the fastest index-matching alternative; additional checks require user action.

A diagnostic run for Fedora 45 on a Fedora 44 installation **does not** authorize pointing the Fedora 44 repositories at Fedora 45. Use Fedora's official release-upgrade procedure for distribution upgrades.

The repository includes **research-only** prototypes for privileged helpers, Polkit authentication, filesystem identity checks, and sandbox transactions. These are **not wired into the GUI**, are not production-safe writers, and must not be used to modify real `/etc` repository configuration.

## Tests and contributions

```bash
python -m pip install -e '.[test]'
python -m pytest -q
```

In the Fedora 44 development environment, the latest reported run completed with **242 passed, 1 skipped** (November 2026). This is a local test result, not a claim of exhaustive coverage or CI certification.

Bug reports are especially welcome for DNF5 configuration differences, mirror discovery timeouts, Fedora release changes, and confusing diagnostic messages. Please include the Fedora release, steps to reproduce, and relevant non-sensitive logs.

## Roadmap

Near-term priorities are documentation, reproducible field testing, clear diagnostic messages, and validation across Fedora releases. A production privileged writer is **not** planned as part of the current read-only workflow.

## License

GPL-3.0-only. See [LICENSE](LICENSE).
