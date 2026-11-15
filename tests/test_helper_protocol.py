"""Tests for the unprivileged helper protocol. No DNF5 or pkexec is invoked."""
import json

import pytest

from mirrorpilot.helper_protocol import (
    MAX_REQUEST_BYTES, decode_request, dry_run, encode_request,
)


def test_round_trip_and_exact_argv():
    payload = encode_request("fedora", "https://mirrors.xtom.ee/fedora/releases/44/")
    op = decode_request(payload)
    assert op.argv == (
        "/usr/bin/dnf5", "config-manager", "setopt",
        "fedora.baseurl=https://mirrors.xtom.ee/fedora/releases/44/",
        "fedora.metalink=", "fedora.mirrorlist=",
    )
    result = dry_run(payload)
    assert result["status"] == "preview-only"
    assert result["writes_performed"] is False
    assert result["authorization_attempted"] is False


@pytest.mark.parametrize("changes", [
    {"version": True},
    {"version": 2},
    {"action": "execute"},
    {"repository": "updates-testing"},
    {"baseurl": "file:///etc/passwd"},
    {"command": "rm -rf /"},
    {"path": "/etc/shadow"},
    {"uid": 0},
])
def test_reject_changed_fields(changes):
    doc = json.loads(encode_request("fedora", "https://mirror.example.fi/fedora/"))
    doc.update(changes)
    with pytest.raises(ValueError):
        decode_request(json.dumps(doc).encode())


@pytest.mark.parametrize("payload", [
    b"", b"[]", b"null", b"not json",
    b'{"version":1,"version":1,"action":"set-mirror","repository":"fedora","baseurl":"https://mirror.example.fi/fedora/"}',
    b"\xff", b" " * (MAX_REQUEST_BYTES + 1),
])
def test_reject_malformed_or_oversized(payload):
    with pytest.raises(ValueError):
        decode_request(payload)


def test_no_external_commands(monkeypatch):
    import subprocess
    def forbidden(*args, **kwargs):
        raise AssertionError("External process launched")
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert dry_run(encode_request("updates", "https://mirror.example.fi/updates/"))["writes_performed"] is False
