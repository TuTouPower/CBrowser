"""Service readiness probe, executed INSIDE the Supervisor container.

scripts/deploy.sh pipes this file to
``docker compose exec -T supervisor python3 - wait <deadline_sec>``
after ``compose up`` (t083: Compose no longer runs Docker healthchecks,
so deploy itself confirms real readiness).  One deadline bounds the
whole wait.  Three services are observed through their existing
control components:

- API:        GET {CBROWSER_API_URL}/api/v1/health
- Gateway:    GET {CBROWSER_GATEWAY_CONTROL_URL}/gateway/v1/health
- Supervisor: GET /supervisor/v1/readiness (control token; readiness
  is computed from maintained observations, and unknown state is
  explicitly not ready)

A service counts ready only on an affirmative response; unreachable,
hung or unknown all stay not-ready until the deadline expires — a
started process is never treated as a ready one.

Output is exactly one JSON object on stdout:

    {"ready": bool, "reason": str | null,
     "services": {"api": bool, "gateway": bool, "supervisor": bool}}

Exit code is 0 iff ready is true.  Only service names and booleans are
emitted — never tokens or other secret material.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

POLL_INTERVAL_SEC = 2.0
SUPERVISOR_BASE_URL = "http://127.0.0.1:8005"

# The control plane is always local or on the compose network: never
# route through proxy environment variables inherited from the host.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _token() -> str:
    token_file = os.environ.get("CBROWSER_SUPERVISOR_TOKEN_FILE", "")
    if token_file:
        with open(token_file, encoding="utf-8") as handle:
            return handle.read().strip()
    return os.environ.get("CBROWSER_SUPERVISOR_TOKEN", "")


def _get(url: str, token: str | None, timeout: float) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with _OPENER.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _check_all(deadline: float) -> dict[str, bool]:
    timeout = max(1.0, min(5.0, deadline - time.monotonic()))
    api_url = os.environ.get("CBROWSER_API_URL", "").rstrip("/")
    gateway_url = os.environ.get(
        "CBROWSER_GATEWAY_CONTROL_URL", ""
    ).rstrip("/")
    results: dict[str, bool] = {}
    try:
        payload = _get(f"{api_url}/api/v1/health", None, timeout)
        results["api"] = payload.get("status") == "ok"
    except Exception:  # noqa: BLE001 - any failure is a not-ready verdict
        results["api"] = False
    try:
        payload = _get(f"{gateway_url}/gateway/v1/health", None, timeout)
        results["gateway"] = payload.get("status") == "ok"
    except Exception:  # noqa: BLE001 - any failure is a not-ready verdict
        results["gateway"] = False
    try:
        payload = _get(
            f"{SUPERVISOR_BASE_URL}/supervisor/v1/readiness",
            _token(),
            timeout,
        )
        results["supervisor"] = payload.get("ready") is True
    except Exception:  # noqa: BLE001 - any failure is a not-ready verdict
        results["supervisor"] = False
    return results


def run(deadline_sec: float) -> dict:
    deadline = time.monotonic() + max(0.0, deadline_sec)
    services = {"api": False, "gateway": False, "supervisor": False}
    while True:
        services = _check_all(deadline)
        if all(services.values()):
            return {"ready": True, "reason": None, "services": services}
        if time.monotonic() >= deadline:
            pending = sorted(
                name for name, ok in services.items() if not ok
            )
            return {
                "ready": False,
                "reason": f"services_not_ready:{','.join(pending)}",
                "services": services,
            }
        time.sleep(
            min(POLL_INTERVAL_SEC, max(0.0, deadline - time.monotonic()))
        )


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "wait":
        print(
            json.dumps(
                {
                    "ready": False,
                    "reason": "usage: service_readiness_probe.py wait <deadline_sec>",
                    "services": {},
                }
            )
        )
        return 2
    try:
        deadline_sec = float(argv[2])
    except ValueError:
        print(
            json.dumps(
                {
                    "ready": False,
                    "reason": "invalid_deadline",
                    "services": {},
                }
            )
        )
        return 2
    result = run(deadline_sec)
    print(json.dumps(result))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
