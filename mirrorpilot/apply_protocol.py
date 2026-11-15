"""Strict validation of a proposed DNF5 change request.

This is an unprivileged protocol prototype. It does not grant authorization
or write any configuration. A future privileged helper must independently
verify the installed release, effective DNF5 settings and verified mirror.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re

from mirrorpilot.changes import ALLOWED_REPOS, release_change_allowed, validate_mirror_url

MAX_REQUEST_BYTES = 4096
_PROTOCOL = "mirrorpilot-change-v1"


@dataclass(frozen=True)
class ChangeRequest:
    repo_id: str
    release: str
    proposed_url: str


def decode_request(raw: bytes) -> ChangeRequest:
    """Reject unknown fields, invalid encodings and unsupported operations."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_REQUEST_BYTES:
        raise ValueError("Invalid request size")
    try:
        request = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Invalid request JSON") from exc
    if not isinstance(request, dict) or set(request) != {
        "protocol", "operation", "repo_id", "release", "proposed_url"
    }:
        raise ValueError("Unexpected request fields")
    if request["protocol"] != _PROTOCOL or request["operation"] != "preview":
        raise ValueError("Unsupported protocol or operation")
    repo = request["repo_id"]
    release = request["release"]
    if type(repo) is not str or repo not in ALLOWED_REPOS:
        raise ValueError("Unsupported repository")
    if type(release) is not str or re.fullmatch(r"[0-9]{1,3}", release) is None:
        raise ValueError("Invalid release")
    url = validate_mirror_url(request["proposed_url"])
    return ChangeRequest(repo, release, url)


def validate_installed_release(request: ChangeRequest, installed: str) -> None:
    if not release_change_allowed(installed, request.release):
        raise ValueError("Release mismatch: refusing cross-release change")


def encode_preview_request(repo_id: str, release: str, url: str) -> bytes:
    raw = json.dumps({
        "protocol": _PROTOCOL, "operation": "preview",
        "repo_id": repo_id, "release": release, "proposed_url": url,
    }, separators=(",", ":")).encode("utf-8")
    decode_request(raw)
    return raw
