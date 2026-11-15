"""Unprivileged, fail-closed prototype of the future helper protocol.

This module NEVER executes DNF5, pkexec or filesystem writes. The privileged
helper must independently revalidate requests and implement recovery.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from mirrorpilot.write_policy import validate_request, preview_options

MAX_REQUEST_BYTES = 4096
VERSION = 1
ACTION = "set-mirror"


@dataclass(frozen=True)
class PreparedOperation:
    repository: str
    baseurl: str
    argv: tuple[str, ...]


def decode_request(payload: bytes) -> PreparedOperation:
    """Accept exactly one small, versioned JSON request with no extra keys."""
    if type(payload) is not bytes or not payload or len(payload) > MAX_REQUEST_BYTES:
        raise ValueError("Invalid request size")
    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed request JSON") from exc
    if type(document) is not dict or set(document) != {"version", "action", "repository", "baseurl"}:
        raise ValueError("Unexpected request fields")
    if type(document["version"]) is not int or document["version"] != VERSION:
        raise ValueError("Unsupported protocol version")
    if document["action"] != ACTION:
        raise ValueError("Unsupported action")
    request = validate_request(document["repository"], document["baseurl"])
    return PreparedOperation(
        request.repository, request.baseurl,
        ("/usr/bin/dnf5", "config-manager", "setopt", *preview_options(request)),
    )


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON field")
        obj[key] = value
    return obj


def encode_request(repository: str, baseurl: str) -> bytes:
    """GUI-side encoder. Never treat this as authorization."""
    request = validate_request(repository, baseurl)
    return json.dumps({
        "version": VERSION, "action": ACTION,
        "repository": request.repository, "baseurl": request.baseurl,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def dry_run(payload: bytes) -> dict:
    """Describe a validated request, without running the proposed argv."""
    operation = decode_request(payload)
    return {
        "status": "preview-only",
        "repository": operation.repository,
        "baseurl": operation.baseurl,
        "argv": list(operation.argv),
        "writes_performed": False,
        "authorization_attempted": False,
    }
