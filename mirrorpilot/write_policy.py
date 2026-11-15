"""Fail-closed request boundary for a future privileged DNF5 helper.

This module performs validation only. It does not execute commands, invoke
Polkit, or modify system files. Privileged code must independently validate
requests and must not trust GUI-side checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
import ipaddress
import re

_ALLOWED_REPOS = frozenset({"fedora", "updates"})
_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")


@dataclass(frozen=True)
class MirrorChangeRequest:
    repository: str
    baseurl: str


def validate_request(repository: str, baseurl: str) -> MirrorChangeRequest:
    """Validate the only planned operation: set one Fedora repo HTTPS baseurl.

    No command strings, paths, shell expansion, arbitrary DNF5 options, or
    custom repository IDs are accepted.
    """
    if type(repository) is not str or repository not in _ALLOWED_REPOS:
        raise ValueError("Repository must be fedora or updates")
    if type(baseurl) is not str or len(baseurl) > 2048 or not baseurl.isascii():
        raise ValueError("Invalid URL length or encoding")
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in baseurl):
        raise ValueError("Whitespace and control characters forbidden")
    parts = urlsplit(baseurl)
    if (parts.scheme != "https" or not parts.netloc or parts.username is not None
            or parts.password is not None or parts.query or parts.fragment
            or parts.port not in (None, 443)):
        raise ValueError("Only ordinary HTTPS mirror URLs are allowed")
    host = parts.hostname
    if not host or not _HOST.fullmatch(host) or ".." in host:
        raise ValueError("Invalid DNS hostname")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP literals are not accepted")
    if not host.endswith((".fi", ".se", ".ee", ".de", ".nl", ".dk")):
        raise ValueError("Mirror hostname outside approved country domains")
    if not parts.path.startswith("/") or not parts.path.endswith("/"):
        raise ValueError("Mirror URL must contain a slash-terminated path")
    if any(x in parts.path for x in ("..", "%", "\\", ";", "=")):
        raise ValueError("Unsafe URL path")
    return MirrorChangeRequest(repository, baseurl)


def preview_options(request: MirrorChangeRequest) -> tuple[str, str]:
    """Show exact intended DNF5 option arguments; never execute them here."""
    request = validate_request(request.repository, request.baseurl)
    return (f"{request.repository}.baseurl={request.baseurl}",
            f"{request.repository}.metalink=")
