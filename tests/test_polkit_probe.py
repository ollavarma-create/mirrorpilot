import json
import pytest

from mirrorpilot.polkit_probe import parse_probe_response


def test_accepts_expected_root_readonly_response():
    payload = {"protocol": "mirrorpilot-auth-probe-v1", "authorized": True,
               "effective_uid": 0, "writes": False}
    assert parse_probe_response(json.dumps(payload)) == payload


@pytest.mark.parametrize("override", [
    {"effective_uid": 1000}, {"effective_uid": False},
    {"authorized": False}, {"writes": True},
    {"protocol": "unexpected"},
])
def test_rejects_unexpected_response(override):
    payload = {"protocol": "mirrorpilot-auth-probe-v1", "authorized": True,
               "effective_uid": 0, "writes": False}
    payload.update(override)
    with pytest.raises(ValueError):
        parse_probe_response(json.dumps(payload))


def test_rejects_malformed_response():
    with pytest.raises(ValueError):
        parse_probe_response("not json")


def test_rejects_extra_fields():
    with pytest.raises(ValueError):
        parse_probe_response('{"protocol":"mirrorpilot-auth-probe-v1","authorized":true,"effective_uid":0,"writes":false,"secret":"x"}')
