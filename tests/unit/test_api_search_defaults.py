"""Coordinator search-defaults refresh/retry behavior (t022 A55 / AC-016)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from cbrowser.api.runtime_coordinator import (
    RuntimeCoordinator,
    SearchDefaultsConflictError,
    SearchDefaultsUnavailableError,
)


def _runtime(instance: str | None = "inst_1"):
    return SimpleNamespace(
        profile_id="profile_a",
        desired_state="running",
        observed_state="running",
        runtime_instance_id=instance,
        config_version=1,
        failure_count=0,
        restart_blocked=False,
        last_exit_event_id=None,
        last_started_at=None,
        last_stopped_at=None,
        browser_product=None,
        browser_user_agent=None,
        updated_at="2026-11-04T00:00:00+00:00",
    )


class _ProfileService:
    def __init__(self, runtime):
        self._runtime = runtime

    async def get_runtime(self, _profile_id: str):
        return self._runtime


def _coordinator(handler) -> RuntimeCoordinator:
    transport = httpx.MockTransport(handler)
    return RuntimeCoordinator(
        supervisor_url="http://supervisor:9000",
        supervisor_token="unit-" + "test-" + "coordinator-" + "token-value",
        profile_service=_ProfileService(_runtime()),
        transport=transport,
    )


def _status_payload(state: str = "failed") -> dict:
    return {
        "profile_id": "profile_a",
        "runtime_instance_id": "inst_1",
        "search_defaults": {
            "state": state,
            "error_kind": "timeout" if state == "failed" else None,
            "runtime_instance_id": "inst_1",
            "request_id": None,
            "updated_at": "2026-11-04T00:00:00+00:00",
        },
    }


@pytest.mark.asyncio
async def test_refresh_caches_fenced_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/profiles/profile_a/search-defaults")
        return httpx.Response(200, json=_status_payload())

    coordinator = _coordinator(handler)
    status = await coordinator.refresh_search_defaults("profile_a")
    assert status is not None
    assert status.state == "failed"
    assert coordinator.get_search_defaults("profile_a") == status


@pytest.mark.asyncio
async def test_refresh_drops_status_from_another_instance() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        payload = _status_payload()
        payload["search_defaults"]["runtime_instance_id"] = "inst_other"
        return httpx.Response(200, json=payload)

    coordinator = _coordinator(handler)
    assert await coordinator.refresh_search_defaults("profile_a") is None


@pytest.mark.asyncio
async def test_retry_posts_fenced_request_and_refreshes() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search-defaults/retry"):
            import json

            seen.update(json.loads(request.content))
            return httpx.Response(200, json={"status": "ok"})
        payload = _status_payload("applied")
        # The supervisor reports the consumed request's id once the
        # runner has executed it; the coordinator waits for that stamp.
        payload["search_defaults"]["request_id"] = seen.get("request_id")
        return httpx.Response(200, json=payload)

    coordinator = _coordinator(handler)
    status = await coordinator.retry_search_defaults("profile_a")
    assert seen["profile_id"] == "profile_a"
    assert seen["runtime_instance_id"] == "inst_1"
    assert seen["request_id"].startswith("sd-retry-")
    assert status is not None and status.state == "applied"
    assert status.request_id == seen["request_id"]


@pytest.mark.asyncio
async def test_retry_maps_supervisor_conflict_and_unavailable() -> None:
    def conflict_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "conflict"})

    with pytest.raises(SearchDefaultsConflictError):
        await _coordinator(conflict_handler).retry_search_defaults("profile_a")

    def unavailable_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "unavailable"})

    with pytest.raises(SearchDefaultsUnavailableError):
        await _coordinator(unavailable_handler).retry_search_defaults("profile_a")


@pytest.mark.asyncio
async def test_retry_waits_for_the_runners_terminal_status() -> None:
    """f011: while the runner has not consumed the retry yet, the status
    endpoint still shows the pre-retry failure stamped with the old
    request id; the coordinator keeps refreshing until the outcome
    stamped with this request_id appears and returns that."""
    seen: dict = {}
    polls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        if request.url.path.endswith("/search-defaults/retry"):
            seen.update(json.loads(request.content))
            return httpx.Response(200, json={"status": "ok"})
        polls["count"] += 1
        if polls["count"] < 3:
            return httpx.Response(200, json=_status_payload("failed"))
        payload = _status_payload("applied")
        payload["search_defaults"]["request_id"] = seen.get("request_id")
        return httpx.Response(200, json=payload)

    coordinator = _coordinator(handler)
    status = await coordinator.retry_search_defaults("profile_a")
    assert status is not None and status.state == "applied"
    assert status.request_id == seen["request_id"]
    assert polls["count"] >= 3


@pytest.mark.asyncio
async def test_publish_fences_status_from_another_instance() -> None:
    """f010: the live SSE publish drops a cached status whose instance
    does not match the runtime's current instance."""
    from cbrowser.domain.models import SearchDefaultsStatusData

    coordinator = _coordinator(lambda _req: httpx.Response(200, json={}))
    coordinator._search_defaults["profile_a"] = SearchDefaultsStatusData(
        state="failed",
        error_kind="timeout",
        runtime_instance_id="inst_other",
        request_id=None,
        updated_at="2026-11-04T00:00:00+00:00",
    )
    published = []

    async def capture(event):
        published.append(event)

    coordinator.broadcaster.publish = capture  # type: ignore[method-assign]
    await coordinator.publish_profile_change("profile_a")
    assert published and published[0].search_defaults is None
