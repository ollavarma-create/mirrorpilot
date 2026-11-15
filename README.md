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
- On demand, benchmark up to 8 Fedora base mirrors returned by country-filtered MirrorManager (FI, SE, EE, DE, NL, DK), using at most 512 KiB of `repomd.xml` per mirror.\n- Perform potentially slow operations in background Qt threads.

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
