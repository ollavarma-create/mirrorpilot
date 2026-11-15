"""Safe release discovery from local OS and official Fedora metalink.

A published repository is not proof that a system upgrade is supported.
"""
from urllib.parse import urlencode
from mirrorpilot.repos import _version, ARCH
from mirrorpilot.speed import _download, MAX_LIST
from mirrorpilot.audit import reference_hash

def installed_release():
    value = _version()
    return value if value.isdecimal() else "unknown"

def available_targets():
    """Installed version always present; probe only the next numeric release."""
    installed = installed_release()
    if not installed.isdecimal():
        return [(installed, "Installed Fedora (version unknown)")]
    options = [(installed, f"Fedora {installed} — installed")]
    next_release = str(int(installed) + 1)
    url = "https://mirrors.fedoraproject.org/metalink?" + urlencode({
        "repo": f"fedora-{next_release}", "arch": ARCH})
    try:
        if reference_hash(_download(url, MAX_LIST)):
            options.append((next_release, f"Fedora {next_release} — repository published (upgrade not verified)"))
    except Exception:
        pass  # A network failure must not misreport the next release as unavailable.
    return options
