import json
import pytest

from mirrorpilot.apply_protocol import (
    decode_request, encode_preview_request, validate_installed_release,
)


def valid():
    return {"protocol": "mirrorpilot-change-v1", "operation": "preview",
            "repo_id": "updates", "release": "44",
            "proposed_url": "https://example.org/fedora/updates/44/"}


def test_roundtrip():
    req = decode_request(encode_preview_request("updates", "44", valid()["proposed_url"]))
    assert req.repo_id == "updates"
    validate_installed_release(req, "44")


@pytest.mark.parametrize("field,value", [
    ("operation", "apply"), ("repo_id", "vscode"), ("release", "45x"),
    ("proposed_url", "http://example.org/fedora/"),
    ("proposed_url", "https://localhost/fedora/"),
])
def test_rejects_invalid_fields(field, value):
    data = valid()
    data[field] = value
    with pytest.raises(ValueError):
        decode_request(json.dumps(data).encode())


def test_rejects_extra_field():
    data = valid()
    data["target_path"] = "/etc/passwd"
    with pytest.raises(ValueError):
        decode_request(json.dumps(data).encode())


def test_rejects_cross_release():
    req = decode_request(json.dumps(valid()).encode())
    with pytest.raises(ValueError, match="Release mismatch"):
        validate_installed_release(req, "45")


def test_rejects_invalid_payload():
    for raw in (b"", b"{", b"x" * 4097, b"[]", b"null"):
        with pytest.raises(ValueError):
            decode_request(raw)


def test_rejects_unrecognized_protocol():
    data = valid()
    data["protocol"] = "other"
    with pytest.raises(ValueError):
        decode_request(json.dumps(data).encode())
