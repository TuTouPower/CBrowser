"""Real-stack E2E: frontend auth guard and session-expiry handling.

Runs the production Vite build behind Caddy with a real API/Coordinator graph.
Covers the t007 auth lane: unauthenticated redirect with preserved target,
no business/SSE traffic before login, authenticated return to the target,
401-driven session expiry redirect, SSE stop after expiry, and open-redirect
rejection.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from playwright.async_api import Browser, BrowserContext, Page, async_playwright


from frontend_app_probe.harness import FrontendAppTopologyHarness  # noqa: E402

logger = logging.getLogger("cbrowser.frontend_app_auth.e2e")


class AuthTopologyHarness(FrontendAppTopologyHarness):
    prefix_base = "t007-auth"
    test_label = "t007-auth"


@pytest.fixture(scope="module")
def harness(tmp_path_factory: pytest.TempPathFactory):
    h = AuthTopologyHarness(tmp_path_factory.mktemp("fe_auth"))
    asyncio.run(h.start())
    try:
        yield h
    finally:
        asyncio.run(h.cleanup())


async def launch_browser() -> tuple[Any, Browser, BrowserContext]:
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
        locale="zh-CN",
    )
    return pw, browser, context


class ApiRequestRecorder:
    def __init__(self, page: Page) -> None:
        self.paths: list[str] = []
        self.statuses: dict[str, list[int]] = {}
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    def _on_request(self, request: Any) -> None:
        parsed = urlparse(request.url)
        if parsed.path.startswith("/api/"):
            self.paths.append(parsed.path)

    def _on_response(self, response: Any) -> None:
        parsed = urlparse(response.url)
        if parsed.path.startswith("/api/"):
            self.statuses.setdefault(parsed.path, []).append(response.status)

    def count(self, path: str) -> int:
        return sum(1 for item in self.paths if item == path)

    def has_status(self, path: str, status: int) -> bool:
        return status in self.statuses.get(path, [])


async def ui_login(page: Page, harness: AuthTopologyHarness) -> None:
    await page.wait_for_selector('[data-testid="login-page"]', timeout=15000)
    await page.fill('[data-testid="login-password"]', harness.admin_password)
    await page.click('[data-testid="login-submit"]')


async def wait_for_api_request(
    recorder: ApiRequestRecorder, path: str, timeout: float = 15.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if recorder.count(path) > 0:
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(f"No {path} request observed; saw {recorder.paths}")


async def wait_for_api_status(
    recorder: ApiRequestRecorder, path: str, status: int, timeout: float = 15.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if recorder.has_status(path, status):
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(
        f"No {path} response with status {status}; saw {recorder.statuses}"
    )


async def create_profile(harness: AuthTopologyHarness, name: str) -> dict[str, Any]:
    async with await harness.api_client() as client:
        resp = await client.post("/api/v1/profiles", json={"name": name})
        resp.raise_for_status()
        return resp.json()


async def revoke_browser_session(
    context: BrowserContext, harness: AuthTopologyHarness
) -> None:
    cookies = {c["name"]: c["value"] for c in await context.cookies(harness.origin)}
    session = cookies["cbrowser_session"]
    csrf = cookies["cbrowser_csrf"]
    async with httpx.AsyncClient(
        base_url=harness.origin, verify=False, trust_env=False, timeout=30.0
    ) as client:
        resp = await client.post(
            "/api/v1/auth/logout",
            headers={
                "Origin": harness.origin,
                "X-CSRF-Token": csrf,
                "Cookie": f"cbrowser_session={session}; cbrowser_csrf={csrf}",
            },
        )
        assert resp.status_code == 200, resp.text


def login_next(url: str) -> str | None:
    values = parse_qs(urlparse(url).query).get("next")
    return values[0] if values else None


@pytest.mark.asyncio
async def test_frontend_app_auth_guard_e2e(harness: AuthTopologyHarness) -> None:
    profile = await create_profile(harness, "Auth Guard Profile")
    profile_id = profile["id"]

    pw, browser, context = await launch_browser()
    try:
        page = await context.new_page()
        recorder = ApiRequestRecorder(page)

        await page.goto(
            f"{harness.origin}/session/{profile_id}", wait_until="domcontentloaded"
        )
        await page.wait_for_url(re.compile(r"/login\?next="), timeout=20000)
        assert login_next(page.url) == f"/session/{profile_id}"
        assert await page.query_selector('[data-testid="login-page"]') is not None

        # Session check happened, but no business or SSE traffic before login.
        assert recorder.count("/api/v1/auth/session") >= 1, recorder.paths
        assert recorder.count("/api/v1/events") == 0, recorder.paths
        assert recorder.statuses.get("/api/v1/events", []) == [], recorder.statuses
        assert recorder.count("/api/v1/profiles") == 0, recorder.paths
        assert not any(
            path.startswith("/api/v1/profiles/") for path in recorder.paths
        ), recorder.paths

        # Login returns to the original target and selects that profile.
        await ui_login(page, harness)
        await page.wait_for_url(
            re.compile(rf"/session/{profile_id}$"), timeout=20000
        )
        await page.wait_for_selector(
            '[data-testid="session-launch-btn"]', timeout=20000
        )
        assert profile["name"] in await page.content()
        await wait_for_api_request(recorder, "/api/v1/events")
        await wait_for_api_status(recorder, "/api/v1/events", 200)

        # Server-side session revocation: the next API call must 401 and redirect.
        await page.wait_for_selector('[data-testid="session-launch-btn"]', timeout=20000)
        await revoke_browser_session(context, harness)
        events_before = recorder.count("/api/v1/events")
        await page.click('[data-testid="session-launch-btn"]')

        await page.wait_for_url(re.compile(r"/login\?next="), timeout=20000)
        assert login_next(page.url) == f"/session/{profile_id}"
        assert await page.query_selector('[data-testid="login-page"]') is not None

        # SSE must not reconnect after the session expired.
        # Fixed settle window for a negative assertion: absence of new
        # /events requests must hold over an interval after the redirect.
        await asyncio.sleep(3.0)
        assert recorder.count("/api/v1/events") == events_before, recorder.paths

        # Open redirect: a hostile next value keeps the user on this origin.
        hostile_context = await browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 720},
            locale="zh-CN",
        )
        try:
            hostile_page = await hostile_context.new_page()
            await hostile_page.goto(
                f"{harness.origin}/login?next=%2F%2Fevil.example",
                wait_until="domcontentloaded",
            )
            await ui_login(hostile_page, harness)
            await hostile_page.wait_for_selector(
                '[data-testid="sidebar"]', timeout=20000
            )
            landed = urlparse(hostile_page.url)
            origin = urlparse(harness.origin)
            assert landed.netloc == origin.netloc, hostile_page.url
            assert landed.path == "/", hostile_page.url
            assert "evil.example" not in hostile_page.url
        finally:
            await hostile_context.close()
    finally:
        await browser.close()
        await pw.stop()
