"""Read-only TLS diagnostics for the frozen AppImage and local Python."""
from __future__ import annotations

import os
from pathlib import Path
import ssl
import sys
from urllib.request import urlopen

PROBE_URL = "https://mirrors.fedoraproject.org/"


def diagnostic_lines() -> list[str]:
    paths = ssl.get_default_verify_paths()
    lines = [
        f"Python: {sys.version.split()[0]}",
        f"Frozen: {bool(getattr(sys, 'frozen', False))}",
        f"OpenSSL: {ssl.OPENSSL_VERSION}",
        f"Default CA file: {paths.cafile or '(none found)'}",
        f"Default CA directory: {paths.capath or '(none found)'}",
        f"OpenSSL compiled CA file: {paths.openssl_cafile}",
        f"OpenSSL compiled CA directory: {paths.openssl_capath}",
    ]
    for name in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
        value = os.environ.get(name)
        lines.append(f"{name}: {value if value is not None else '(unset)'}")
    for path in (
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
        "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
    ):
        p = Path(path)
        lines.append(f"CA candidate {path}: exists={p.is_file()} readable={os.access(path, os.R_OK)}")
    return lines


def main() -> int:
    for line in diagnostic_lines():
        print(line, flush=True)
    print(f"HTTPS probe: {PROBE_URL}", flush=True)
    try:
        # urllib uses the default verified TLS context. Never disable verification.
        with urlopen(PROBE_URL, timeout=10) as response:
            print(f"HTTPS result: HTTP {response.status}", flush=True)
            return 0
    except Exception as exc:
        print(f"HTTPS result: {type(exc).__name__}: {exc}", flush=True)
        return 1
