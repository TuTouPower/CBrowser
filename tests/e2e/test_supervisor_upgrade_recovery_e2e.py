"""t049 AC-007: a deployment upgrade self-heals a running Profile.

Starts the full production topology through the shared frontend harness,
brings a Profile up (frames verified in a headless Chrome viewer), then
force-recreates Gateway and Supervisor together — the same shape as
``docker compose up -d`` replacing both containers. The Supervisor must
restore the orphaned sandbox and re-attach the new Gateway on its own,
readiness must recover inside the 300 s deployment budget without the
deadlock diagnostics, and a new viewer must get frames again.

The suite uses the unified topology harness and its label-scoped cleanup;
it builds no Docker objects of its own (t046).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest
from playwright.async_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    async_playwright,
)

from frontend_app_probe.harness import FrontendAppTopologyHarness  # noqa: E402

pytestmark = pytest.mark.serial

IFRAME_SELECTOR = 'iframe[data-testid="sess-iframe"]'
READINESS_TIMEOUT_SEC = 300.0
FORBIDDEN_DIAGNOSTICS = frozenset(
    {
        "session_instance_mismatch",
        "gateway_not_attached_at_fixed_endpoint",
        "agent_not_registered",
    }
)


class UpgradeTopologyHarness(FrontendAppTopologyHarness):
    """Lane-scoped prefix; only t049-upgrade objects are created."""

    prefix_base = "t049-upgrade"
    test_label = "t049-upgrade"


async def _launch_viewer() -> tuple[Any, Browser, BrowserContext]:
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        channel="chrome",
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--ignore-certificate-errors",
        ],
    )
    context = await browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1280, "height": 720},
    )
    return pw, browser, context


async def _open_session_page(
    context: BrowserContext,
    harness: UpgradeTopologyHarness,
    profile_id: str,
) -> Page:
    page = await context.new_page()
    await page.goto(
        f"{harness.origin}/session/{profile_id}", wait_until="domcontentloaded"
    )
    await page.wait_for_selector(IFRAME_SELECTOR, timeout=30000)
    return page


async def _decoded_frames(page: Page) -> dict[str, Any] | None:
    return await page.evaluate(
        """async () => {
            const f = document.querySelector(
                'iframe[data-testid="sess-iframe"]');
            if (!f || !f.contentWindow) return null;
            if (typeof f.contentWindow.__getWebRTCStats !== 'function') return null;
            return await f.contentWindow.__getWebRTCStats();
        }"""
    )


async def _wait_for_frames(
    page: Page, *, timeout: float, name: str
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = await _decoded_frames(page)
        except (PlaywrightError, RuntimeError) as exc:
            last = {"error": str(exc)}
        if (
            last
            and last.get("connected")
            and (last.get("video") or {}).get("framesDecoded", 0) > 0
        ):
            return last
        await asyncio.sleep(0.3)
    raise TimeoutError(f"{name} did not decode frames: {json.dumps(last)[:800]}")


async def _readiness(
    harness: UpgradeTopologyHarness,
) -> dict[str, Any]:
    async with httpx.AsyncClient(
        base_url=harness.supervisor_url,
        headers={"Authorization": f"Bearer {harness.keys['supervisor']}"},
        trust_env=False,
        timeout=10.0,
    ) as client:
        resp = await client.get("/supervisor/v1/readiness")
        resp.raise_for_status()
        return resp.json()


async def _wait_profile_ready(
    harness: UpgradeTopologyHarness, profile_id: str
) -> dict[str, Any]:
    deadline = time.monotonic() + READINESS_TIMEOUT_SEC
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = await _readiness(harness)
        except (httpx.HTTPError, OSError) as exc:
            last = {"error": type(exc).__name__}
        if isinstance(last, dict) and last.get("ready") is True:
            for entry in last.get("profiles", []):
                if entry.get("profile_id") == profile_id and entry.get("ready"):
                    return entry
        await asyncio.sleep(1.0)
    raise TimeoutError(
        f"Profile {profile_id} not ready within {READINESS_TIMEOUT_SEC}s: "
        f"{json.dumps(last, default=str)[:1200]}"
    )


@pytest.fixture(scope="module")
def harness(tmp_path_factory: pytest.TempPathFactory):
    h = UpgradeTopologyHarness(tmp_path_factory.mktemp("t049_upgrade"))
    asyncio.run(h.start())
    try:
        yield h
    finally:
        asyncio.run(h.cleanup())


@pytest.mark.asyncio
async def test_upgrade_of_running_profile_self_heals(harness: UpgradeTopologyHarness):
    profile = await harness.create_and_start_profile("t049_running")
    profile_id = profile["profile_id"]

    pw, browser, context = await _launch_viewer()
    try:
        headers = await harness.login_api()
        cookie = headers["Cookie"].split("cbrowser_session=", 1)[1]
        await context.add_cookies(
            [
                {
                    "name": "cbrowser_session",
                    "value": cookie,
                    "url": harness.origin,
                }
            ]
        )

        before = await _open_session_page(context, harness, profile_id)
        await _wait_for_frames(before, timeout=90.0, name="pre-upgrade viewer")
        await before.close()

        # Recreate Gateway and Supervisor together while the sandbox runs.
        await harness.rebuild_gateway_and_supervisor()

        ready = await _wait_profile_ready(harness, profile_id)
        diagnostics = set(ready.get("diagnostics") or [])
        assert not (diagnostics & FORBIDDEN_DIAGNOSTICS), diagnostics

        after = await _open_session_page(context, harness, profile_id)
        stats = await _wait_for_frames(after, timeout=180.0, name="post-upgrade viewer")
        assert stats["video"]["framesDecoded"] > 0
    finally:
        await browser.close()
        await pw.stop()
