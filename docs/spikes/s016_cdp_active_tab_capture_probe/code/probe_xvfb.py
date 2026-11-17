from __future__ import annotations

import asyncio
import base64
import json
import urllib.parse

from playwright.async_api import async_playwright

ENGINE = "/data/engine-cache/chromium-146.0.7680.177.3/chrome"


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


async def main():
    out = {"engine": ENGINE, "headless": False, "display": "container_xvfb", "cases": []}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path=ENGINE,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--window-size=1280,800",
            ],
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
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
                {"title": t.get("title"), "attached": t.get("attached")}
                for t in info["targetInfos"]
                if t["type"] == "page"
            ]

        for label, active in (
            ("after_create", None),
            ("after_bring_p1", 1),
            ("after_bring_p0", 0),
        ):
            if active is not None:
                await pages[active].bring_to_front()
                await asyncio.sleep(0.3)
            out["cases"].append(
                {
                    "label": label,
                    "samples": [await sample(page) for page in pages],
                    "targets": page_targets(await bcdp.send("Target.getTargets")),
                }
            )

        result = await sessions[2].send(
            "Page.captureScreenshot", {"format": "jpeg", "quality": 70}
        )
        raw = base64.b64decode(result["data"])
        out["capture_background_p2"] = {
            "jpeg": raw[:2] == b"\xff\xd8",
            "bytes": len(raw),
            "samples_after": [await sample(page) for page in pages],
            "targets_after": page_targets(await bcdp.send("Target.getTargets")),
        }
        await browser.close()
    print(json.dumps(out, ensure_ascii=False, indent=2))


asyncio.run(main())
