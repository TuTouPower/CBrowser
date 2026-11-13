"""t038 AC-008 real-stack E2E: create a proxy through the /proxies UI,
reference it from a newly created environment, launch that environment, and
prove browser egress traverses the proxy via a local recording proxy's
``PROXY_GET <path>`` log line driven by a CDP ``Page.navigate``.

Topology: FrontendAppTopologyHarness (production Vite build + Caddy + API
Runtime Coordinator -> Supervisor -> Browser/Stream containers), driven by
headless official Mac Google Chrome.  The recording proxy is a host thread
listening on an OS-assigned port; the Browser container reaches it through
``host.docker.internal`` (Docker Desktop / OrbStack host gateway), so no public
network and no extra container/network attachment is required.  Supervisor
writes the proxy host verbatim into ``proxy_credentials.json`` and derives the
Chrome ``--proxy-server`` endpoint plus its fail-closed allow rule from it.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from wait import poll_until, wait_for_log

pytestmark = [pytest.mark.serial, pytest.mark.e2e_images('CBROWSER_API_TEST_IMAGE', 'CBROWSER_CADDY_TEST_IMAGE', 'CBROWSER_GATEWAY_IMAGE', 'CBROWSER_RUNTIME_TEST_IMAGE', 'CBROWSER_STREAM_TEST_IMAGE', 'CBROWSER_SUPERVISOR_TEST_IMAGE')]

PROXY_HOST = "host.docker.internal"
TARGET_HOST = "cbrowser-ac008.invalid"


class _ProxyLog:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.lines: list[str] = []

    def add(self, line: str) -> None:
        with self.lock:
            self.lines.append(line)

    def text(self) -> str:
        with self.lock:
            return "\n".join(self.lines)


def _handler_factory(log: _ProxyLog):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            line = f"PROXY_GET {self.path}"
            print(line, flush=True)
            log.add(line)
            body = b"cbrowser ac008 proxy ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_CONNECT(self) -> None:
            self.send_response(405)
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            return

    return Handler


@pytest.fixture
def recording_proxy():
    log = _ProxyLog()
    server = ThreadingHTTPServer(("0.0.0.0", 0), _handler_factory(log))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield PROXY_HOST, port, log
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


@pytest.fixture(scope="module")
def harness(tmp_path_factory: Any):
    from frontend_app_probe.harness import FrontendAppTopologyHarness

    h = FrontendAppTopologyHarness(tmp_path_factory.mktemp("ac008"))
    asyncio.run(h.start())
    try:
        yield h
    finally:
        asyncio.run(h.cleanup())


async def _launch_browser():
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        channel="chrome",
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--ignore-certificate-errors",
            "--autoplay-policy=no-user-gesture-required",
        ],
    )
    context = await browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1280, "height": 720},
        locale="zh-CN",
    )
    return pw, browser, context


async def ui_login(page: Any, harness: Any) -> None:
    await page.goto(f"{harness.origin}/login", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="login-page"]', timeout=15000)
    await page.fill('[data-testid="login-password"]', harness.admin_password)
    await page.click('[data-testid="login-submit"]')
    await page.wait_for_url(re.compile(r"/$"), timeout=20000)


async def open_session(page: Any, harness: Any, profile_id: str) -> None:
    await page.goto(
        f"{harness.origin}/session/{profile_id}", wait_until="domcontentloaded"
    )


async def launch_profile_via_ui(page: Any, timeout: float = 120.0) -> None:
    await page.click('[data-testid="sess-stage-action-launch"]', timeout=15000)
    await page.wait_for_selector(
        '[data-testid="sess-page"]', timeout=timeout * 1000
    )


async def _stop_profile(harness: Any, profile_id: str) -> None:
    client = await harness.api_client()
    async with client:
        resp = await client.post(f"/api/v1/profiles/{profile_id}/stop")
        resp.raise_for_status()


async def _create_proxy_via_ui(
    page: Any, harness: Any, name: str, host: str, port: int
) -> str:
    await page.goto(f"{harness.origin}/proxies", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="proxy-list-page"]', timeout=15000)
    await page.click('[data-testid="proxy-add"]')
    await page.wait_for_selector('[data-testid="proxy-form-dialog"]', timeout=15000)
    # t052: the link is the only entry; the name lives in the (collapsed)
    # advanced section and defaults to host:port when left untouched.
    await page.fill('[data-testid="proxy-form-url"]', f"http://{host}:{port}")
    await page.click('[data-testid="proxy-form-advanced-toggle"]')
    await page.fill('[data-testid="proxy-form-name"]', name)
    await page.click('[data-testid="proxy-form-submit"]')
    await page.wait_for_selector(
        '[data-testid="proxy-form-dialog"]', state="detached", timeout=15000
    )
    row = page.locator('[data-testid^="proxy-row-"]').filter(has_text=name)
    await row.wait_for(state="visible", timeout=15000)
    testid = await row.get_attribute("data-testid")
    assert testid is not None
    return testid.removeprefix("proxy-row-")


async def _create_profile_with_proxy_via_ui(
    page: Any, harness: Any, profile_name: str, proxy_name: str
) -> str:
    await page.goto(f"{harness.origin}/", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="env-list-page"]', timeout=15000)
    await page.click('[data-testid="env-new"]')
    await page.wait_for_selector('[data-testid="env-new-dialog"]', timeout=15000)
    await page.fill('[data-testid="profile-form-name"]', profile_name)
    await page.locator('[data-testid="profile-form-proxy"] button').click()
    await page.get_by_role("option", name=proxy_name, exact=True).click()
    await page.click('[data-testid="profile-form-submit"]')
    await page.wait_for_selector(
        '[data-testid="env-new-dialog"]', state="detached", timeout=15000
    )
    row = page.locator('[data-testid^="env-row-"]').filter(has_text=profile_name)
    await row.wait_for(state="visible", timeout=15000)
    testid = await row.get_attribute("data-testid")
    assert testid is not None
    return testid.removeprefix("env-row-")


async def _assert_profile_proxy(
    harness: Any, profile_id: str, proxy_id: str
) -> None:
    async def _read() -> dict[str, Any]:
        async with await harness.api_client() as client:
            resp = await client.get(f"/api/v1/profiles/{profile_id}")
            resp.raise_for_status()
            return resp.json()

    profile = await poll_until(
        _read,
        lambda data: data.get("proxy_id") == proxy_id,
        timeout=15.0,
        interval=0.3,
        description="profile.proxy_id persisted",
    )
    assert profile["proxy_id"] == proxy_id


def _cdp_navigate(container: str, url: str) -> None:
    script = """import asyncio, json, websockets

parameters = __PARAMS__

async def cmd(ws, cid, method, params=None, session=None):
    req = {"id": cid, "method": method, "params": params or {}}
    if session:
        req["sessionId"] = session
    await ws.send(json.dumps(req))
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), 15))
        if msg.get("id") == cid:
            if "error" in msg:
                raise RuntimeError("CDP %s: %s" % (cid, msg["error"]))
            return msg.get("result", {})

async def run():
    from cbrowser.runtime_agent.socket_root import container_agent_socket_path
    async with websockets.unix_connect(
        container_agent_socket_path(), "ws://localhost/cdp"
    ) as ws:
        targets = await cmd(ws, 1, "Target.getTargets")
        pages = [t for t in targets["targetInfos"] if t["type"] == "page"]
        if not pages:
            raise RuntimeError("no page target")
        attach = await cmd(
            ws, 2, "Target.attachToTarget",
            {"targetId": pages[0]["targetId"], "flatten": True},
        )
        s = attach["sessionId"]
        await cmd(ws, 3, "Page.enable", session=s)
        await cmd(ws, 4, "Page.navigate", {"url": parameters["url"]}, session=s)
        print("NAVIGATED", flush=True)

asyncio.run(run())
""".replace("__PARAMS__", repr({"url": url}))
    result = subprocess.run(
        ["docker", "exec", container, "python3", "-c", script],
        capture_output=True,
        text=True,
        timeout=25.0,
        check=True,
    )
    assert "NAVIGATED" in result.stdout, result.stdout + result.stderr


@pytest.mark.asyncio
async def test_ac008_proxy_library_outbound_via_ui(
    harness: Any, recording_proxy: Any, tmp_path: Path
) -> None:
    proxy_host, proxy_port, proxy_log = recording_proxy
    run_id = uuid.uuid4().hex[:8]
    proxy_name = f"ac008-proxy-{run_id}"
    profile_name = f"ac008-env-{run_id}"
    target_url = f"http://{TARGET_HOST}/ac008?run={run_id}"
    needle = f"PROXY_GET http://{TARGET_HOST}/ac008"

    pw, browser, context = await _launch_browser()
    profile_id: str | None = None
    try:
        page = await context.new_page()
        await ui_login(page, harness)

        proxy_id = await _create_proxy_via_ui(
            page, harness, proxy_name, proxy_host, proxy_port
        )
        profile_id = await _create_profile_with_proxy_via_ui(
            page, harness, profile_name, proxy_name
        )
        await _assert_profile_proxy(harness, profile_id, proxy_id)

        await open_session(page, harness, profile_id)
        await launch_profile_via_ui(page)
        await harness.wait_runtime(
            profile_id, desired="running", observed="running"
        )

        names = await poll_until(
            lambda: asyncio.to_thread(harness.container_names, profile_id),
            lambda value: value is not None,
            timeout=30.0,
            interval=0.5,
            description="browser/stream container binding",
        )
        browser_container = names[0]

        async def _navigate_once() -> bool:
            try:
                await asyncio.to_thread(
                    _cdp_navigate, browser_container, target_url
                )
                return True
            except Exception:  # noqa: BLE001 - CDP may not be ready yet
                return False

        await poll_until(
            _navigate_once,
            lambda ok: bool(ok),
            timeout=30.0,
            interval=1.0,
            description="remote CDP Page.navigate readiness",
        )

        async def _read_log() -> str:
            return proxy_log.text()

        text = await wait_for_log(
            _read_log, needle, timeout=15.0, interval=0.5
        )
        assert needle in text, f"browser egress did not traverse the proxy: {text!r}"
        (tmp_path / "ac008_proxy_log.txt").write_text(text, encoding="utf-8")
    finally:
        if profile_id:
            try:
                await _stop_profile(harness, profile_id)
            except Exception:  # noqa: BLE001 - best-effort runtime cleanup
                pass
        await browser.close()
        await pw.stop()
