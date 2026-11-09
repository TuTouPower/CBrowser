"""Deployment readiness probe, executed INSIDE the Supervisor container.

scripts/deploy.sh pipes this file to
``docker compose exec -T supervisor python3 - verify <deadline_sec>`` so the
host needs no supervisor secret and no new published port (t026 spec:
"宿主机经容器内命令调用").  In ``verify`` mode the probe triggers the
single convergence entry (POST /supervisor/v1/reconcile) once, then polls
GET /supervisor/v1/readiness; one deadline bounds the whole verification
(the reconcile call consumes from the same budget, it does not add a
second one).  In ``report`` mode it takes one read-only readiness
snapshot (no reconcile) for failure diagnostics.

Output is exactly one JSON object on stdout:

    {"ready": bool, "reason": str | null,
     "profiles": [{"profile_id": str, "ready": bool,
                   "diagnostics": [str, ...]}, ...]}

Only profile ids, ready flags and diagnostic codes are emitted — never
tokens or other secret material.  Exit code is 0 iff ready is true.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:8005"
POLL_INTERVAL_SEC = 2.0


def _base_url() -> str:
    return os.environ.get("CBROWSER_SUPERVISOR_URL", DEFAULT_BASE_URL).rstrip("/")


def _token() -> str:
    token_file = os.environ.get("CBROWSER_SUPERVISOR_TOKEN_FILE", "")
    if token_file:
        with open(token_file, encoding="utf-8") as handle:
            return handle.read().strip()
    return os.environ.get("CBROWSER_SUPERVISOR_TOKEN", "")


# The control plane is always local (same container / loopback): never
# route through proxy environment variables inherited from the host.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _request(method: str, path: str, token: str, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(
        f"{_base_url()}{path}",
        method=method,
        headers={"Authorization": f"Bearer {token}"},
    )
    with _OPENER.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _summary(payload: dict) -> dict:
    profiles = []
    for profile in payload.get("profiles", []):
        profiles.append(
            {
                "profile_id": profile.get("profile_id", "?"),
                "ready": bool(profile.get("ready", False)),
                "diagnostics": [
                    str(item)[:200] for item in profile.get("diagnostics", [])
                ],
            }
        )
    return {
        "ready": bool(payload.get("ready", False)),
        "reason": payload.get("reason"),
        "profiles": profiles,
    }


def run(deadline_sec: float) -> dict:
    token = _token()
    if not token:
        return {
            "ready": False,
            "reason": "probe_missing_supervisor_token",
            "profiles": [],
        }
    # A single deadline bounds the whole verification: reconcile_all is
    # a full convergence pass over every Profile and may legitimately
    # take far longer than one readiness poll, so it gets whatever
    # remains of the deadline (not a separate budget on top of it).
    deadline = time.monotonic() + max(0.0, deadline_sec)
    try:
        _request(
            "POST",
            "/supervisor/v1/reconcile",
            token,
            timeout=max(1.0, deadline - time.monotonic()),
        )
    except Exception as exc:  # noqa: BLE001 - any reconcile failure is a not-ready verdict
        return {
            "ready": False,
            "reason": f"reconcile_request_failed:{type(exc).__name__}",
            "profiles": [],
        }
    last: dict = {
        "ready": False,
        "reason": "readiness_not_yet_reported",
        "profiles": [],
    }
    while True:
        try:
            last = _summary(
                _request(
                    "GET",
                    "/supervisor/v1/readiness",
                    token,
                    timeout=max(1.0, min(10.0, deadline - time.monotonic())),
                )
            )
            if last["ready"]:
                return last
        except Exception as exc:  # noqa: BLE001 - transient errors retry until the deadline
            last = {
                "ready": False,
                "reason": f"readiness_request_failed:{type(exc).__name__}",
                "profiles": [],
            }
        if time.monotonic() >= deadline:
            if not last["ready"] and last.get("reason") in (
                None,
                "readiness_not_yet_reported",
            ):
                last["reason"] = "readiness_deadline_exceeded"
            return last
        time.sleep(min(POLL_INTERVAL_SEC, max(0.0, deadline - time.monotonic())))


def report() -> dict:
    """Read-only single readiness snapshot: never triggers reconcile.

    Used for failure diagnostics after `compose up --wait` has already
    failed, where re-running a full convergence pass would be slow and
    outside the diagnostic scope.
    """
    token = _token()
    if not token:
        return {
            "ready": False,
            "reason": "probe_missing_supervisor_token",
            "profiles": [],
        }
    try:
        return _summary(_request("GET", "/supervisor/v1/readiness", token))
    except Exception as exc:  # noqa: BLE001 - diagnostics must degrade, never crash
        return {
            "ready": False,
            "reason": f"readiness_request_failed:{type(exc).__name__}",
            "profiles": [],
        }


def main(argv: list[str]) -> int:
    deadline_sec = 300.0
    if len(argv) > 1 and argv[1] == "verify":
        if len(argv) > 2:
            deadline_sec = float(argv[2])
        result = run(deadline_sec)
    elif len(argv) > 1 and argv[1] == "report":
        result = report()
    elif len(argv) > 1:
        print(
            json.dumps(
                {
                    "ready": False,
                    "reason": "usage: verify [deadline_sec] | report",
                    "profiles": [],
                }
            )
        )
        return 2
    else:
        result = run(deadline_sec)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
