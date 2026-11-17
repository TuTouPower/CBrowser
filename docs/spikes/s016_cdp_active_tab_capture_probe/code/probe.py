from __future__ import annotations

import asyncio
import base64
import json
import urllib.parse

from playwright.async_api import async_playwright

ENGINE = "/data/engine-cache/chromium-146.0.7680.177.3/chrome"
VIEWPORT = {"width": 1280, "height": 800}


async def sample(page):
    return await page.evaluate(
        """() => ({
            visibilityState: document.visibilityState,
            hidden: document.hidden,
            hasFocus: document.hasFocus(),
            marker: document.getElementById('marker')?.textContent ?? null,
            events: window.__events ? [...window.__events] : [],
        })"""
    )


def jpeg_meta(data):
    raw = base64.b64decode(data)
    return {"bytes": len(raw), "jpeg": raw[:2] == b"\xff\xd8"}


async def main():
    out = {"engine": ENGINE, "headless": True, "cases": []}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path=ENGINE,
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(viewport=VIEWPORT)
        pages = []
        for i in range(3):
            page = await context.new_page()
            html = (
                f"<html><head><title>tab-{i}</title></head>"
                "<body style='margin:0;background:#ffffff'>"
                f"<h1 id='marker' style='font:700 80px sans-serif;color:#003300'>TAB-{i}</h1>"
                "</body></html>"
            )
            await page.goto(
                "data:text/html;charset=utf-8," + urllib.parse.quote(html),
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await page.evaluate(
                """() => {
                    window.__events = [];
                    for (const name of ['focus', 'blur']) {
                        window.addEventListener(name, () => window.__events.push(name));
                    }
                    document.addEventListener('visibilitychange',
                        () => window.__events.push('visibilitychange'));
                }"""
            )
            pages.append(page)
        bcdp = await browser.new_browser_cdp_session()
        sessions = [await context.new_cdp_session(page) for page in pages]

        def page_targets(info):
            return [
                {
                    "url": t["url"],
                    "title": t.get("title"),
                    "attached": t.get("attached"),
                    "targetId": t["targetId"],
                }
                for t in info["targetInfos"]
                if t["type"] == "page"
            ]

        await pages[1].bring_to_front()
        out["baseline"] = {
            "samples": [await sample(page) for page in pages],
            "targets": page_targets(await bcdp.send("Target.getTargets")),
        }

        cases = [
            ("background_page0_default", 0, {}),
            ("foreground_page1_default", 1, {}),
            ("background_page0_beyond_viewport", 0, {"captureBeyondViewport": True}),
            ("background_page0_no_surface", 0, {"fromSurface": False}),
        ]
        for name, index, extra in cases:
            params = {"format": "jpeg", "quality": 70}
            params.update(extra)
            try:
                result = await sessions[index].send("Page.captureScreenshot", params)
                shot = jpeg_meta(result["data"])
            except Exception as exc:
                shot = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            out["cases"].append(
                {
                    "name": name,
                    "target_index": index,
                    "params": params,
                    "shot": shot,
                    "samples": [await sample(page) for page in pages],
                    "targets": page_targets(await bcdp.send("Target.getTargets")),
                }
            )
        await browser.close()
    print(json.dumps(out, ensure_ascii=False, indent=2))


asyncio.run(main())
