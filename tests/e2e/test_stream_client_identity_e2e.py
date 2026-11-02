"""Chrome Web Locks identity arbitration; media acceptance runs separately."""

import asyncio
import json
from pathlib import Path

import pytest
from aiohttp import WSMsgType, web
from playwright.async_api import async_playwright

WEB_LOCK_SHIM_JS = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "stream_probe"
    / "web_lock_shim.js"
).read_text(encoding="utf-8")

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


@pytest.mark.asyncio
async def test_same_document_concurrent_hello_and_duplicate_document() -> None:
    assert CHROME.is_file(), "Google Chrome Stable is required"
    received = []
    sockets = []

    async def signal(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        sockets.append(ws)
        async for message in ws:
            if message.type == WSMsgType.TEXT:
                received.append(message.data)
                await ws.send_str("HELLO")
        return ws

    app = web.Application()
    app.router.add_get(
        "/",
        lambda request: web.Response(
            text="<title>Identity probe</title>", content_type="text/html"
        ),
    )
    app.router.add_get("/stream/profile/signal", signal)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                executable_path=str(CHROME), headless=True
            )
            try:
                context = await browser.new_context()
                await context.add_init_script(WEB_LOCK_SHIM_JS)
                await context.add_init_script(
                    "window.signalUrl=location.origin.replace('http','ws')"
                    "+'/stream/profile/signal';"
                )
                page = await context.new_page()
                await page.goto(origin)
                await page.evaluate("""async () => {
                    sessionStorage.setItem('selkies_tab_id', 'original_tab');
                    window.testSockets = [0,1].map(() => {
                        const ws = new WebSocket(window.signalUrl);
                        return ws;
                    });
                    await Promise.all(testSockets.map(ws =>
                        new Promise(resolve => ws.onopen = resolve)));
                    for (const ws of testSockets) {
                        ws.send('HELLO client {"client_tab_id":"original_tab",'
                            + '"resume_key":"ephemeral"}');
                    }
                }""")
                async with asyncio.timeout(5):
                    while len(received) < 2:
                        await asyncio.sleep(0.02)
                assert (
                    received
                    == [
                        (
                            'HELLO client {"client_tab_id":"original_tab",'
                            '"resume_key":"ephemeral"}'
                        )
                    ]
                    * 2
                )
                assert (
                    await page.evaluate("sessionStorage.getItem('selkies_tab_id')")
                    == "original_tab"
                )
                duplicate = await context.new_page()
                await duplicate.goto(origin)
                await duplicate.evaluate("""() => {
                    sessionStorage.setItem('selkies_tab_id', 'original_tab');
                    window.duplicateSocket = new WebSocket(window.signalUrl);
                    duplicateSocket.onopen = () => duplicateSocket.send(
                        'HELLO client {"client_tab_id":"original_tab"}');
                }""")
                await duplicate.wait_for_function(
                    "sessionStorage.getItem('selkies_tab_id') !== 'original_tab'"
                )
                assert len(received) == 2, "Colliding document forwarded the old HELLO"
                assert await page.evaluate(
                    "testSockets.every(ws => ws.readyState === WebSocket.OPEN)"
                )
                original = await duplicate.evaluate(
                    "sessionStorage.getItem('selkies_tab_id')"
                )
                assert original
                await duplicate.evaluate("""() => {
                    window.retry = new WebSocket(window.signalUrl);
                    retry.onopen = () => retry.send('HELLO client '
                        + JSON.stringify({client_tab_id:
                            sessionStorage.getItem('selkies_tab_id')}));
                }""")
                async with asyncio.timeout(5):
                    while len(received) < 3:
                        await asyncio.sleep(0.02)
                assert (
                    json.loads(received[-1].removeprefix("HELLO client "))[
                        "client_tab_id"
                    ]
                    == original
                )
                await duplicate.reload()
                assert (
                    await duplicate.evaluate("sessionStorage.getItem('selkies_tab_id')")
                    == original
                )
            finally:
                await browser.close()
    finally:
        for ws in sockets:
            await ws.close()
        await runner.cleanup()
