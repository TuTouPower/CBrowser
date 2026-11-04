"""Search-defaults retry on the live context E2E (t028 AC-004).

The route contract (CSRF, outcome mapping, idempotency key plumbing)
is covered with a stub coordinator in
``tests/integration/test_api_search_defaults_routes.py``.  This entry
runs the retry against the live topology: API -> Supervisor -> Agent
UDS -> Runner inside the real Stream/Browser runtime, and asserts the
terminal outcome the live context reports back.  Target-environment
execution is t032's.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import httpx
import pytest
from gateway_probe.evidence import save_evidence
from gateway_probe.topology import GatewayTopologyHarness
from wait import poll_until


@pytest.mark.asyncio
async def test_search_defaults_retry_on_live_context(tmp_path: Path) -> None:
    harness = GatewayTopologyHarness(tmp_path)
    try:
        await harness.start()
        profile = await harness.create_and_start_profile(
            "search_defaults_profile"
        )
        profile_id = profile["profile_id"]
        instance_id = profile["runtime_instance_id"]
        auth_headers = await harness.login_api()
        url = f"/api/v1/profiles/{profile_id}/runtime/search-defaults/retry"
        request_key = f"t028-live-{secrets.token_hex(6)}"

        async with httpx.AsyncClient(
            base_url=harness.origin,
            headers=auth_headers,
            verify=False,
            trust_env=False,
            timeout=30.0,
        ) as api:
            # CSRF is enforced on the live route exactly as in the stub
            # contract tests.
            no_csrf = {
                k: v for k, v in auth_headers.items() if k != "X-CSRF-Token"
            }
            resp = await api.post(url, headers=no_csrf)
            assert resp.status_code == 403

            async def do_retry() -> httpx.Response:
                return await api.post(
                    url, headers={"Idempotency-Key": request_key}
                )

            resp = await do_retry()
            assert resp.status_code == 200, resp.text
            body = resp.json()
            status = body["search_defaults"]
            assert status is not None
            assert status["runtime_instance_id"] == instance_id

            # The coordinator polls briefly; the status endpoint must
            # converge to THIS request's terminal outcome on the live
            # instance (fenced: another instance's status never shows).
            async def current_status() -> dict | None:
                resp = await api.get(f"/api/v1/profiles/{profile_id}/runtime")
                assert resp.status_code == 200
                return resp.json().get("search_defaults")

            status = await poll_until(
                current_status,
                lambda s: bool(s)
                and s.get("request_id") == request_key
                and s.get("state") in ("applied", "failed", "disabled"),
                timeout=60.0,
                interval=1.0,
                description="live search-defaults outcome for this request",
            )
            assert status["runtime_instance_id"] == instance_id
            assert status["state"] == "applied", (
                f"live retry did not apply search defaults: {status}"
            )

            # Idempotent replay: the same key is deduplicated end to end
            # and reports the same request, not a second execution.
            resp = await do_retry()
            assert resp.status_code == 200, resp.text
            replayed = resp.json()["search_defaults"]
            assert replayed["request_id"] == request_key
            assert replayed["state"] == "applied"

        save_evidence(
            "search_defaults_retry_live",
            {
                "profile_id": profile_id,
                "runtime_instance_id": instance_id,
                "request_id": request_key,
                "state": status["state"],
            },
            tmp_path,
        )
    finally:
        await harness.cleanup()
