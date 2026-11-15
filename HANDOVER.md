# MirrorPilot — HANDOVER for the next ChatGPT conversation

**Date:** 2026-11-15  
**Next objective:** create and validate a reproducible Fedora-focused **AppImage**, then invite external beta testers.

## Project and status

- GitHub: https://github.com/ollavarma-create/mirrorpilot
- Current branch: `main`; use a separate feature branch for packaging.
- Current declared version: **0.1.0a1** (experimental pre-alpha).
- Python **3.11+**, **PySide6 >= 6.6**, Hatchling build backend.
- CLI entry point in `pyproject.toml`: `mirrorpilot = "mirrorpilot.app:main"`.
- Primary field-test environment: Fedora 44 KDE Plasma, x86_64.
- Most recent reported test result: **242 passed, 1 skipped** (local report; not a fresh CI run).
- Documentation in `README.md`, `docs/DESIGN.md`, `docs/TESTING.md`; README includes actual screenshots under `docs/images/`.
- README/screenshots PR #3 and architecture/testing PR #4 are merged into `main`.

**User's plan:** once a working AppImage is available, announce MirrorPilot on a Fedora/Linux forum and request beta testers. Do not announce a binary before validating it on the user's Fedora machine.

## What the application does

MirrorPilot is a **read-only Fedora DNF5 mirror diagnostic GUI**. It reads repository definitions and overrides, queries DNF5 effective values, checks the configured HTTPS source, discovers/benchmarks alternative Fedora mirrors, compares repository indexes with Fedora metalink checksums, and validates selected referenced metadata. A **Recommended** alternative has passed the applicable index and selected metadata checks, not RPM signature verification.

It can display and copy a **user-run** `sudo dnf5 config-manager setopt` command for a verified same-release `fedora` or `updates` mirror. For recognized Fedora URL layouts, this preserves literal `$releasever` and `$basearch` variables. After the user executes the command separately, MirrorPilot can verify both DNF5 effective settings and the stored variable-based URL.

**Safety boundary:** the GUI does **not** write DNF configuration, DNF caches, or packages; does not run as root or invoke a privileged writer; does not automatically apply repairs. Experimental Polkit/helper, sandbox transaction and crash-recovery code in the repository is **research only** and must not be presented as production functionality. Cross-release diagnosis is allowed, but generating a configuration change for a release other than the installed Fedora release is blocked.

## Relevant source modules

- `mirrorpilot/app.py`: PySide6 GUI, worker threads, user actions.
- `mirrorpilot/repos.py`: repository-file discovery, expanded vs raw baseurl.
- `mirrorpilot/dnf_effective.py`: `dnf5 --dump-repo-config=<repo>`.
- `mirrorpilot/config_conflicts.py`: file-level configuration origins.
- `mirrorpilot/releases.py`: installed release and next-release probe.
- `mirrorpilot/speed.py`: MirrorManager discovery and bounded benchmark.
- `mirrorpilot/audit.py`: metalink index and referenced metadata checks.
- `mirrorpilot/diagnostics.py`: orchestration and health classification.
- `mirrorpilot/changes.py`: restricted same-release change planning, persistent URL templates.
- `mirrorpilot/manual_edit.py`: copyable user-run command and verification.
- `mirrorpilot/summary.py`: accurate user-facing results.

Consult the current repository rather than assuming this list is exhaustive.

## Important lessons from Fedora field testing

1. A configured FUNET Fedora 44 updates mirror returned HTTP 404 for referenced `primary.xml.zck` metadata. A separately verified alternative worked when configured manually.
2. Early generated commands hardcoded Fedora 44 and x86_64. Known Fedora layouts now become `$releasever` and `$basearch` templates.
3. DNF5 expands variables in `--dump-repo-config`, causing an early false Verify mismatch. Verification now checks **expanded effective** and **raw stored** URLs separately.
4. The GUI must refresh repository settings after external DNF5 changes.
5. Configured-but-untested is distinct from missing or verified.
6. Release discovery uses host architecture; do not assume all other paths are architecture-neutral.

See `docs/TESTING.md` for details and limitations.

## AppImage task: recommended workflow

**First inspect current `main`** using the GitHub connector or a checked-out repository: `pyproject.toml`, application entry point, any `packaging/` assets, icon and desktop file, scripts, `.github/workflows/`, and tests. **No AppImage toolchain has yet been chosen or validated.** Do not invent existing packaging assets.

1. Choose an initial support target: **Linux x86_64, first tested on Fedora 44 KDE**. Additional Fedora versions are potential test targets, not promises.
2. Select a reproducible bundling approach for Python + PySide6 + Qt (for example, assess PyInstaller/AppDir/appimagetool or another appropriate maintained workflow). Keep build scripts/configuration in Git.
3. Prepare the AppDir with executable `AppRun`, a valid `.desktop` file, icon, and bundled application runtime. Reuse any existing artwork where possible.
4. **DNF5 stays a host dependency.** MirrorPilot must invoke the host's `dnf5` and read the host's `/etc/yum.repos.d/`, `/etc/dnf/repos.override.d/`, and `/etc/os-release`. AppImage does not make non-DNF5 distributions compatible.
5. Verify that AppImage's bundled library paths and Qt environment variables do not break the host `dnf5` subprocess. Investigate `LD_LIBRARY_PATH`, `QT_PLUGIN_PATH`, Wayland/X11 platform plugins, TLS certificates and graphics compatibility.
6. Consider glibc baseline and the build environment; a binary built on a newer distribution may fail on older ones.
7. Keep the AppImage **unprivileged**. Do not enable research-only privileged helpers or include root execution in normal installation instructions.
8. Test the actual generated AppImage on the user's Fedora system, not merely whether the build succeeds.
9. Record artifact name/version/architecture, SHA-256 checksum, build provenance, and limitations. Update README with download/run instructions once verified.
10. Open a PR and merge only after user testing and approval. Consider a GitHub pre-release and a forum beta invitation afterward.

## Minimum AppImage acceptance checklist

- [ ] Builds reproducibly from a documented script or workflow.
- [ ] Runs on Fedora 44 KDE without a local Python venv or pip-installed dependencies.
- [ ] Starts from a terminal and file manager after `chmod +x`.
- [ ] Main window renders correctly on the actual desktop (X11/Wayland as available).
- [ ] Reads installed release and configured repositories.
- [ ] `Configuration origins…` and DNF5 effective-value inspection work.
- [ ] `Check current` and `Find better mirrors` work, including explicit error states.
- [ ] Command preview preserves literal `$releasever` and `$basearch`.
- [ ] Effective-settings Verify handles expanded and raw URLs.
- [ ] No host DNF configuration/cache/package changes occur from application actions.
- [ ] Existing pytest suite passes; packaging smoke test and SHA-256 are recorded.
- [ ] README explains Fedora/DNF5 requirement, executable permission, run method, experimental status, and bug-report instructions.

Potential AppImage runtime/FUSE limitations and `--appimage-extract` fallback should be documented after checking the chosen runtime.

## Suggested collaboration workflow

The user is comfortable testing on Fedora and reviewing GitHub PRs. The assistant should inspect real GitHub sources, create a dedicated branch such as `packaging/appimage`, commit the packaging changes, open a PR, and have the user test the actual build. Merge only with user approval. Avoid unrelated diagnostics refactors.

Local baseline:

```bash
git switch main
git pull --ff-only origin main
python -m pytest -q
```

## Prompt for the new conversation

> Continue the MirrorPilot project from this HANDOVER.md. Our next goal is a reproducible Fedora x86_64 AppImage that I can test on Fedora KDE, then a small external beta test. Inspect the latest `ollavarma-create/mirrorpilot` GitHub `main`, including `pyproject.toml`, entry points and any existing packaging assets. Preserve the read-only safety model. Propose a practical build strategy, implement it in a feature branch/PR, and let me test the AppImage before merging or publishing.

**Not yet done:** no AppImage has been built or tested, no build toolchain or minimum Fedora compatibility baseline has been confirmed, and no public beta announcement has been made.
