"""Host-side client for the Supervisor control plane (t026 AC-009).

Invoked inside the Supervisor container, e.g.::

    docker compose exec supervisor python -m cbrowser.supervisor.control_client readiness
    docker compose exec supervisor python -m cbrowser.supervisor.control_client reconcile

No new host port or reverse-proxy route is introduced: the caller reaches
the control API over the container's own loopback through ``exec``.
Configuration comes from the environment:

- ``CBROWSER_SUPERVISOR_URL`` — base URL (default: the shared
  ``DEFAULT_SUPERVISOR_URL``, derived from ``DEFAULT_SUPERVISOR_PORT``)
- ``CBROWSER_SUPERVISOR_TOKEN_FILE`` — control token file path

Exit codes: ``readiness`` exits 0 when ready, 1 when not ready or the
control plane is unreachable; ``reconcile`` exits 0 on success, 2 on
failure. JSON results are printed to stdout for scripting.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

from cbrowser.secret_files import read_secret_file
from cbrowser.shared.endpoints import DEFAULT_SUPERVISOR_URL

__all__ = ["DEFAULT_SUPERVISOR_URL"]


def _client() -> httpx.Client:
    base_url = os.environ.get("CBROWSER_SUPERVISOR_URL", DEFAULT_SUPERVISOR_URL)
    token_file = os.environ.get("CBROWSER_SUPERVISOR_TOKEN_FILE", "")
    if not token_file:
        raise SystemExit("CBROWSER_SUPERVISOR_TOKEN_FILE is not set")
    token = read_secret_file(
        Path(token_file), label="Supervisor control token", minimum_bytes=32
    )
    return httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx.Timeout(120.0),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="control_client")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("readiness", help="Print readiness JSON; exit 0 iff ready")
    sub.add_parser("reconcile", help="Trigger one full convergence pass")
    args = parser.parse_args(argv)

    try:
        with _client() as client:
            if args.command == "readiness":
                response = client.get("/supervisor/v1/readiness")
            else:
                response = client.post("/supervisor/v1/reconcile")
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {"ready": False, "error": f"control_unreachable:{type(exc).__name__}"}
            )
        )
        return 1 if args.command == "readiness" else 2
    print(json.dumps(payload))
    if args.command == "readiness":
        return 0 if payload.get("ready") is True else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
