"""Parse the result of the optional Polkit authorization probe.

No privilege escalation happens in this module.
"""
from __future__ import annotations

import json

EXPECTED_PROTOCOL = "mirrorpilot-auth-probe-v1"


def parse_probe_response(output: str) -> dict:
    if len(output) > 4096:
        raise ValueError("Probe response too large")
    try:
        response = json.loads(output)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid probe response") from exc
    if (not isinstance(response, dict)
            or set(response) != {"protocol", "authorized", "effective_uid", "writes"}
            or response["protocol"] != EXPECTED_PROTOCOL
            or response["authorized"] is not True
            or type(response["effective_uid"]) is not int
            or response["effective_uid"] != 0
            or response["writes"] is not False):
        raise ValueError("Unexpected or unauthorized probe response")
    return response
