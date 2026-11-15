"""Run the future helper protocol parser as an unprivileged dry run.

Usage: python -m mirrorpilot.helper_dry_run < request.json
No pkexec, DNF5 execution, or system writes.
"""
from __future__ import annotations

import json
import os
import sys

from mirrorpilot.helper_protocol import MAX_REQUEST_BYTES, dry_run


def main() -> int:
    if os.geteuid() == 0:
        print("Refusing root execution", file=sys.stderr)
        return 2
    try:
        payload = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        result = dry_run(payload)
    except (ValueError, TypeError) as exc:
        print(f"Request rejected: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
