"""Subprocess client for the t029 automation compatibility probe.

Every mode runs in its own OS process so the probe can observe what a
real external automation process does — and what survives its normal
exit, abrupt death or timeout — without the test process sharing the
connection.  Results are written as one JSON document to ``--out``.

Modes:
  matrix   Full candidate-API exercise through a discovery endpoint.
  hold     Attach at one fingerprint level (L2-L5) and wait for release.
  raw_hold Raw browser-level CDP socket, no domains enabled (L1).
  dialog   Raw-CDP JavaScript Dialog baseline scenarios.
  input    CDP Input exercise whose page-side events are reported.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any


def _write_out(path: str | None, payload: dict[str, Any]) -> None:
    if path:
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


async def _wait_release(release_file: str | None, timeout: float) -> None:
    if not release_file:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if Path(release_file).exists():
            return
        await asyncio.sleep(0.1)
    raise TimeoutError("release file never appeared")


# ---------------------------------------------------------------------------
# matrix
# ---------------------------------------------------------------------------


async def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    result: dict[str, Any] = {"mode": "matrix", "no_defaults": args.no_defaults}
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(
            args.endpoint, no_defaults=args.no_defaults
        )
        result["browser_version"] = browser.version
        result["contexts"] = len(browser.contexts)
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(args.url)
        result["title"] = await page.title()

        async with page.expect_popup(timeout=5000) as popup_info:
            await page.click("#popup-btn")
        popup = await popup_info.value
        await popup.wait_for_load_state("domcontentloaded")
        result["popup"] = {"title": await popup.title(), "url": popup.url}
        await popup.close()
        result["pages_after_popup_close"] = len(context.pages)

        frame = None
        for _ in range(50):
            frame = page.frame(url=re.compile(r"/frame"))
            if frame is not None:
                break
            await page.wait_for_timeout(100)
        result["frame_found"] = frame is not None
        if frame is not None:
            await frame.click("#frame-pad")
            frame_events = await frame.evaluate("() => window.__events")
            result["frame_click_events"] = [
                e["type"] for e in frame_events if e.get("isTrusted")
            ]

        snapshot = await page.aria_snapshot(mode="ai")
        result["snapshot_has_pad"] = "Pointer pad" in snapshot or "pad" in snapshot
        result["snapshot_excerpt"] = snapshot[:300]
        ref_match = re.search(r"\[ref=([a-z]?\d*e\d+)\]", snapshot)
        result["snapshot_ref_found"] = ref_match is not None
        if ref_match:
            locator = page.get_by_ref(ref_match.group(1))
            result["ref_tag"] = await locator.evaluate("el => el.tagName")

        await page.evaluate("() => { window.__events = []; }")
        try:
            async with page.expect_download(timeout=4000) as download_info:
                await page.click("#download-link")
            download = await download_info.value
            entry: dict[str, Any] = {
                "event": "download",
                "suggested_filename": download.suggested_filename,
                "url": download.url,
            }
            try:
                path = await download.path()
                entry["path_available"] = path is not None
            except Exception as exc:  # noqa: BLE001 - outcome is the evidence
                entry["path_error"] = type(exc).__name__
            result["download"] = entry
        except Exception as exc:  # noqa: BLE001 - outcome is the evidence
            # With no_defaults=True Playwright never arms download events
            # on the context, so a click can legitimately produce no
            # client-side download event; where the file lands is then
            # decided by the browser-level behavior (the Agent's, in
            # chain mode) and is asserted by the caller, not here.
            result["download"] = {"event": "timeout", "error": type(exc).__name__}

        box = await page.locator("#pad").bounding_box()
        if box:
            await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await page.click("#text-input")
        await page.keyboard.type("probe")
        events = await page.evaluate("() => window.__events")
        result["input_events"] = [
            {"type": e["type"], "isTrusted": e["isTrusted"]} for e in events[:12]
        ]
        result["text_value"] = await page.input_value("#text-input")

        if args.disconnect == "close":
            await browser.close()
            result["disconnect"] = "browser.close"
            return result
        if args.disconnect == "exit":
            result["disconnect"] = "process_exit"
            _write_out(args.out, result)
            sys.stdout.flush()
            os._exit(0)
        result["disconnect"] = "driver_stop"
        return result


# ---------------------------------------------------------------------------
# hold (L2-L5) / raw_hold (L1)
# ---------------------------------------------------------------------------


async def run_hold(args: argparse.Namespace) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    result: dict[str, Any] = {"mode": "hold", "level": args.level}
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(
            args.endpoint, no_defaults=(args.level != "L3")
        )
        result["browser_version"] = browser.version
        if args.level in {"L4", "L5"}:
            context = browser.contexts[0]
            page = context.pages[0]
            session = await context.new_cdp_session(page)
            await session.send("Runtime.enable")
            await session.send("Page.enable")
            result["domains_enabled"] = ["Runtime", "Page"]
            if args.level == "L5":
                snapshot = await page.aria_snapshot(mode="ai")
                ref_match = re.search(r"\[ref=(e\d+)\]", snapshot)
                result["snapshot_ref_found"] = ref_match is not None
                if ref_match:
                    locator = page.get_by_ref(ref_match.group(1))
                    result["ref_tag"] = await locator.evaluate("el => el.tagName")
        if args.ready_file:
            Path(args.ready_file).write_text(
                json.dumps({"pid": os.getpid(), "level": args.level}),
                encoding="utf-8",
            )
        await _wait_release(args.release_file, args.hold_timeout)
        result["released"] = True
        _write_out(args.out, result)
        sys.stdout.flush()
        os._exit(0)


async def run_raw_hold(args: argparse.Namespace) -> dict[str, Any]:
    import websockets

    async with websockets.connect(args.endpoint, max_size=32 * 1024 * 1024) as ws:
        if args.ready_file:
            Path(args.ready_file).write_text(
                json.dumps({"pid": os.getpid(), "level": "L1"}), encoding="utf-8"
            )
        await _wait_release(args.release_file, args.hold_timeout)
        result = {"mode": "raw_hold", "level": "L1", "released": True}
        _write_out(args.out, result)
        sys.stdout.flush()
        os._exit(0)


# ---------------------------------------------------------------------------
# dialog (raw CDP)
# ---------------------------------------------------------------------------


class RawCdp:
    def __init__(self) -> None:
        self.ws: Any = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self.events: list[dict[str, Any]] = []
        self._reader: asyncio.Task | None = None

    async def connect(self, url: str) -> None:
        import websockets

        self.ws = await websockets.connect(url, max_size=32 * 1024 * 1024)
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        async for raw in self.ws:
            message = json.loads(raw)
            if "id" in message and message["id"] in self._pending:
                future = self._pending.pop(message["id"])
                if not future.done():
                    future.set_result(message)
            elif "method" in message:
                self.events.append(message)

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        self._next_id += 1
        cid = self._next_id
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[cid] = future
        payload: dict[str, Any] = {"id": cid, "method": method, "params": params or {}}
        if session_id:
            payload["sessionId"] = session_id
        await self.ws.send(json.dumps(payload))
        return await asyncio.wait_for(future, timeout=timeout)

    async def wait_event(self, method: str, timeout: float) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for event in self.events:
                if event.get("method") == method:
                    return event
            await asyncio.sleep(0.05)
        return None

    async def attach_page(self, url_marker: str) -> str:
        targets = await self.send("Target.getTargets")
        infos = targets["result"]["targetInfos"]
        chosen = None
        for info in infos:
            if info.get("type") == "page" and url_marker in info.get("url", ""):
                chosen = info
                break
        if chosen is None:
            for info in infos:
                if info.get("type") == "page":
                    chosen = info
                    break
        if chosen is None:
            raise RuntimeError("no page target available")
        attached = await self.send(
            "Target.attachToTarget",
            {"targetId": chosen["targetId"], "flatten": True},
        )
        return str(attached["result"]["sessionId"])

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
        if self.ws:
            await self.ws.close()


async def run_dialog(args: argparse.Namespace) -> dict[str, Any]:
    cdp = RawCdp()
    await cdp.connect(args.endpoint)
    session = await cdp.attach_page(args.url_marker)
    result: dict[str, Any] = {"mode": "dialog", "scenario": args.scenario}
    button = {"alert": "#alert-btn", "confirm": "#confirm-btn", "prompt": "#prompt-btn"}[
        args.dialog_type
    ]
    try:
        if args.scenario in {"pending", "leave"}:
            await cdp.send("Page.enable", session_id=session)
            await cdp.send("Runtime.enable", session_id=session)
            evaluate_task = asyncio.create_task(
                cdp.send(
                    "Runtime.evaluate",
                    {
                        "expression": f"document.querySelector('{button}').click()",
                        "returnByValue": True,
                    },
                    session_id=session,
                    timeout=30,
                )
            )
            opening = await cdp.wait_event("Page.javascriptDialogOpening", 8)
            result["opening"] = opening.get("params") if opening else None
            if args.scenario == "leave":
                result["left_open"] = opening is not None
                _write_out(args.out, result)
                sys.stdout.flush()
                os._exit(3)
            if opening is None:
                result["handled_while_pending"] = False
                evaluate_task.cancel()
                return result
            await cdp.send(
                "Page.handleJavaScriptDialog",
                {"accept": True, "promptText": "agent"},
                session_id=session,
            )
            result["handled_while_pending"] = True
            response = await asyncio.wait_for(evaluate_task, timeout=8)
            result["evaluate_completed"] = "result" in response
            last = await cdp.send(
                "Runtime.evaluate",
                {"expression": "window.__lastDialog", "returnByValue": True},
                session_id=session,
            )
            result["last_dialog"] = last["result"]["result"].get("value")
            return result

        if args.scenario == "handle_new":
            enable_error = None
            try:
                await cdp.send("Page.enable", session_id=session, timeout=4)
            except Exception as exc:  # noqa: BLE001 - blocking is the evidence
                enable_error = type(exc).__name__
            result["page_enable_error"] = enable_error
            opening = await cdp.wait_event("Page.javascriptDialogOpening", 2.5)
            result["opening_replayed"] = opening is not None
            if opening:
                result["opening"] = opening.get("params")
            handle_error = None
            try:
                await cdp.send(
                    "Page.handleJavaScriptDialog",
                    {"accept": True, "promptText": "agent"},
                    session_id=session,
                    timeout=4,
                )
            except Exception as exc:  # noqa: BLE001 - outcome is the evidence
                handle_error = type(exc).__name__
            result["handle_error"] = handle_error
            try:
                last = await cdp.send(
                    "Runtime.evaluate",
                    {"expression": "window.__lastDialog", "returnByValue": True},
                    session_id=session,
                    timeout=4,
                )
                result["last_dialog"] = last["result"]["result"].get("value")
                result["commands_blocked"] = False
            except Exception as exc:  # noqa: BLE001 - outcome is the evidence
                result["last_dialog"] = None
                result["commands_blocked"] = True
                result["evaluate_error"] = type(exc).__name__
            return result

        if args.scenario == "beforeunload":
            await cdp.send("Page.enable", session_id=session)
            await cdp.send("Runtime.enable", session_id=session)
            if args.activation == "input":
                rect = await cdp.send(
                    "Runtime.evaluate",
                    {
                        "expression": (
                            "(() => { const r = document.querySelector('#bu-toggle')"
                            ".getBoundingClientRect();"
                            " return {x: r.x + r.width / 2, y: r.y + r.height / 2}; })()"
                        ),
                        "returnByValue": True,
                    },
                    session_id=session,
                )
                point = rect["result"]["result"]["value"]
                for event_type in ("mousePressed", "mouseReleased"):
                    await cdp.send(
                        "Input.dispatchMouseEvent",
                        {
                            "type": event_type,
                            "x": point["x"],
                            "y": point["y"],
                            "button": "left",
                            "clickCount": 1,
                        },
                        session_id=session,
                    )
            else:
                await cdp.send(
                    "Runtime.evaluate",
                    {
                        "expression": "window.onbeforeunload = (e) => { e.preventDefault(); e.returnValue = ''; }",
                        "returnByValue": True,
                    },
                    session_id=session,
                )
            armed = await cdp.send(
                "Runtime.evaluate",
                {"expression": "typeof window.onbeforeunload", "returnByValue": True},
                session_id=session,
            )
            result["armed_type"] = armed["result"]["result"].get("value")
            navigate_task = asyncio.create_task(
                cdp.send(
                    "Page.navigate", {"url": args.url}, session_id=session, timeout=15
                )
            )
            opening = await cdp.wait_event("Page.javascriptDialogOpening", 4)
            result["opening"] = opening.get("params") if opening else None
            if opening:
                await cdp.send(
                    "Page.handleJavaScriptDialog",
                    {"accept": True},
                    session_id=session,
                )
                result["handled"] = True
            try:
                response = await asyncio.wait_for(navigate_task, timeout=8)
                result["navigate_completed"] = "result" in response
            except Exception as exc:  # noqa: BLE001 - outcome is the evidence
                result["navigate_completed"] = False
                result["navigate_error"] = type(exc).__name__
            current = await cdp.send(
                "Runtime.evaluate",
                {"expression": "location.href", "returnByValue": True},
                session_id=session,
            )
            result["final_url"] = current["result"]["result"].get("value")
            return result
        raise ValueError(f"unknown scenario {args.scenario}")
    finally:
        await cdp.close()


# ---------------------------------------------------------------------------
# input (CDP)
# ---------------------------------------------------------------------------


async def run_input(args: argparse.Namespace) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    result: dict[str, Any] = {"mode": "input"}
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(args.endpoint, no_defaults=True)
        context = browser.contexts[0]
        page = context.pages[0]
        await page.goto(args.url)
        await page.evaluate("() => { window.__events = []; }")

        pad = await page.locator("#pad").bounding_box()
        assert pad is not None
        await page.mouse.click(pad["x"] + 40, pad["y"] + 30)
        await page.click("#text-input")
        await page.keyboard.type("probe")
        box = await page.locator("#scrollbox").bounding_box()
        assert box is not None
        await page.mouse.move(box["x"] + 30, box["y"] + 30)
        await page.mouse.wheel(0, 300)
        await page.wait_for_timeout(150)
        result["scroll_top"] = await page.evaluate(
            "() => document.getElementById('scrollbox').scrollTop"
        )
        frame = page.frame(url=re.compile(r"/frame"))
        result["frame_found"] = frame is not None
        if frame is not None:
            frame_pad = await frame.locator("#frame-pad").bounding_box()
            if frame_pad:
                await page.mouse.click(
                    frame_pad["x"] + 25, frame_pad["y"] + 20
                )
            result["frame_events"] = await frame.evaluate("() => window.__events")
        result["events"] = await page.evaluate("() => window.__events")
        result["text_value"] = await page.input_value("#text-input")
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)

    matrix = sub.add_parser("matrix")
    matrix.add_argument("--endpoint", required=True)
    matrix.add_argument("--url", required=True)
    matrix.add_argument("--out")
    matrix.add_argument("--no-defaults", action="store_true")
    matrix.add_argument("--disconnect", choices=["exit", "close", "stop"], default="exit")

    hold = sub.add_parser("hold")
    hold.add_argument("--endpoint", required=True)
    hold.add_argument("--level", choices=["L2", "L3", "L4", "L5"], required=True)
    hold.add_argument("--ready-file")
    hold.add_argument("--release-file")
    hold.add_argument("--hold-timeout", type=float, default=90)
    hold.add_argument("--out")

    raw_hold = sub.add_parser("raw_hold")
    raw_hold.add_argument("--endpoint", required=True)
    raw_hold.add_argument("--ready-file")
    raw_hold.add_argument("--release-file")
    raw_hold.add_argument("--hold-timeout", type=float, default=90)
    raw_hold.add_argument("--out")

    dialog = sub.add_parser("dialog")
    dialog.add_argument("--endpoint", required=True)
    dialog.add_argument("--url", default="")
    dialog.add_argument("--url-marker", default="127.0.0.1")
    dialog.add_argument(
        "--scenario",
        choices=["pending", "leave", "handle_new", "beforeunload"],
        required=True,
    )
    dialog.add_argument(
        "--dialog-type", choices=["alert", "confirm", "prompt"], default="confirm"
    )
    dialog.add_argument("--activation", choices=["input", "none"], default="input")
    dialog.add_argument("--out")

    input_parser = sub.add_parser("input")
    input_parser.add_argument("--endpoint", required=True)
    input_parser.add_argument("--url", required=True)
    input_parser.add_argument("--out")

    args = parser.parse_args()
    runners = {
        "matrix": run_matrix,
        "hold": run_hold,
        "raw_hold": run_raw_hold,
        "dialog": run_dialog,
        "input": run_input,
    }
    result = asyncio.run(runners[args.mode](args))
    _write_out(args.out, result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
