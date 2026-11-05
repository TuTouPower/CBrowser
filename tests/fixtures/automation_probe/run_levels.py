"""t029 AC-004/AC-005 sampling driver (t032 recheck entry).

Per sample: fresh target-engine process via the production BrowserRunner
launch path (host substitutions only), fixed seed/viewport, self-hosted
observation page.  External clients attach through a CdpBridge relay
directly to the browser WS (path equivalence with the cbat_ tunnel is
proven separately by the chain integration tests).  Signals are read
through the runner's own SDK page handle, which is part of the
production runtime in every level including L0.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "src" / "backend"))
sys.path.insert(0, str(_REPO_ROOT / "tests" / "fixtures"))

from automation_probe.harness import (  # noqa: E402
    READ_EVENTS_SCRIPT,
    SIGNAL_SCRIPT,
    CdpBridge,
    ObservationServer,
    XTestInput,
    build_report,
    engine_cache_dir,
    host_runner_class,
    restore_pulse_runtime_path,
    stop_sample_pulse_daemon,
    summarize_levels,
    write_profile_snapshot,
)

CLIENT = str(Path(__file__).resolve().parent / "probe_client.py")
SEED = 290029
SAMPLES = int(os.environ.get("T029_SAMPLES", "5"))
DISPLAY = os.environ.get("T029_DISPLAY", ":141")
XTE = os.environ.get("T029_XTE") or None


def spawn_client(argv: list[str]) -> subprocess.Popen:
    env = dict(os.environ)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    return subprocess.Popen(
        [sys.executable, CLIENT, *argv],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )


async def wait_file(path: Path, timeout: float = 60) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        await asyncio.sleep(0.1)
    return False


class Sample:
    def __init__(self, obs: ObservationServer, tag: str):
        self.obs = obs
        self.root = Path(tempfile.mkdtemp(prefix=f"t029-lvl-{tag}-", dir="/tmp"))
        self.runner = None
        self.bridge: CdpBridge | None = None
        self._previous_pulse_runtime_path = None

    async def __aenter__(self):
        self._previous_pulse_runtime_path = os.environ.get("PULSE_RUNTIME_PATH")
        runner_cls = host_runner_class()
        cache = engine_cache_dir()
        assert cache is not None
        self.runner = runner_cls(
            profile_id="p1",
            runtime_instance_id="i1",
            config_snapshot_path=write_profile_snapshot(
                self.root, profile_id="p1", seed=SEED
            ),
            run_dir=self.root / "run",
            user_data_dir=self.root / "profile",
            events_dir=self.root / "events",
            engine_cache_dir=cache,
            display=DISPLAY,
        )
        await self.runner.start()
        page = self.runner.browser_context.pages[0]
        await page.goto(self.obs.url + "/")
        self.bridge = CdpBridge(str(self.runner.browser_ws_url)).start()
        return self

    async def __aexit__(self, *exc):
        try:
            if self.bridge is not None:
                self.bridge.close()
            if self.runner is not None:
                await self.runner.stop()
        finally:
            # Production runners do not stop their own daemon. Stop only this
            # sample's container daemon, then restore the process-global
            # environment before removing the sample directory.
            stop_sample_pulse_daemon(self.runner)
            restore_pulse_runtime_path(self._previous_pulse_runtime_path)
            # Each sample's profile directory is several MB; on small
            # tmpfs mounts (the cloud VM has 512 MB) keeping them all
            # exhausts the disk mid-run, so samples clean up after
            # themselves.  Samples live in the report, not on disk.
            import shutil

            shutil.rmtree(self.root, ignore_errors=True)

    @property
    def page(self):
        return self.runner.browser_context.pages[0]

    async def signal(self) -> dict:
        return await self.page.evaluate(SIGNAL_SCRIPT)

    async def hold_sample(self, mode: str, level: str | None) -> dict:
        ready = self.root / "ready.json"
        release = self.root / "release"
        argv = [mode, "--endpoint", "", "--ready-file", str(ready),
                "--release-file", str(release), "--out", str(self.root / "client.json")]
        if mode == "raw_hold":
            argv[2] = self.bridge.ws_url
        else:
            argv[2] = self.bridge.endpoint_url
            argv += ["--level", level]
        proc = spawn_client(argv)
        try:
            assert await wait_file(ready), f"{mode} {level} never became ready"
            signal = await self.signal()
            release.write_text("go", encoding="utf-8")
            rc = await asyncio.to_thread(proc.wait, 30)
            # The client exit code is run metadata, not a page signal:
            # it must never enter the compared sample (doing so once
            # produced a spurious "new change" on every level).
            signal = dict(signal)
            self.client_exit_code = rc
            return signal
        finally:
            if proc.poll() is None:
                proc.kill()


async def main() -> None:
    obs = ObservationServer()
    obs.__enter__()
    levels: dict[str, list[dict]] = {}
    try:
        for level in ("L0", "L1", "L2", "L3", "L4", "L5"):
            samples = []
            for i in range(SAMPLES):
                async with Sample(obs, f"{level}-{i}") as s:
                    if level == "L0":
                        samples.append(await s.signal())
                    elif level == "L1":
                        samples.append(await s.hold_sample("raw_hold", None))
                    else:
                        samples.append(await s.hold_sample("hold", level))
                print(f"{level} sample {i} done", flush=True)
            levels[level] = samples

        # L6 CDP input
        l6_cdp = []
        input_details: dict[str, list[dict]] = {
            "cdp": [],
            "xtest": [],
            "zoom": [],
            "focus_contention": [],
        }
        for i in range(SAMPLES):
            async with Sample(obs, f"L6cdp-{i}") as s:
                pad = await s.page.locator("#pad").bounding_box()
                assert pad is not None
                target_client = [pad["x"] + 40, pad["y"] + 30]
                out = s.root / "input.json"
                proc = spawn_client([
                    "input", "--endpoint", s.bridge.endpoint_url,
                    "--url", obs.url + "/", "--out", str(out),
                ])
                rc = await asyncio.to_thread(proc.wait, 120)
                payload = json.loads(out.read_text()) if out.exists() else {}
                payload["client_exit_code"] = rc
                l6_cdp.append(await s.signal())
                clicks = [
                    e for e in payload.get("events", []) if e["type"] == "click"
                ]
                click = clicks[0] if clicks else None
                input_details["cdp"].append({
                    "click": click,
                    "target_client": target_client,
                    "client_error": [
                        round(click.get("clientX", -999) - target_client[0], 2),
                        round(click.get("clientY", -999) - target_client[1], 2),
                    ] if click else None,
                    "scroll_top": payload.get("scroll_top"),
                    "text_value": payload.get("text_value"),
                    "frame_found": payload.get("frame_found"),
                    "frame_events": payload.get("frame_events"),
                })
            print(f"L6-CDP sample {i} done", flush=True)
        levels["L6_cdp_input"] = l6_cdp

        # L6 XTEST input
        l6_xtest = []
        for i in range(SAMPLES):
            async with Sample(obs, f"L6x-{i}") as s:
                page = s.page
                await page.evaluate("() => { window.__events = []; }")
                xtest = XTestInput(DISPLAY, xte_path=XTE, xauthority=s.runner.xauth_path)
                meta = await page.evaluate(
                    """() => ({sx: window.screenX, sy: window.screenY,
                               ow: window.outerWidth, oh: window.outerHeight,
                               iw: window.innerWidth, ih: window.innerHeight,
                               dpr: window.devicePixelRatio})"""
                )
                border_x = (meta["ow"] - meta["iw"]) / 2
                top_ui = (meta["oh"] - meta["ih"]) - border_x
                pad = await page.locator("#pad").bounding_box()
                assert pad is not None
                tx = meta["sx"] + border_x + pad["x"] + 40
                ty = meta["sy"] + top_ui + pad["y"] + 30
                await asyncio.to_thread(xtest.click, int(tx), int(ty))
                await page.wait_for_timeout(300)
                events = await page.evaluate(READ_EVENTS_SCRIPT)
                click = next(
                    (e for e in events if e["type"] == "click"), {}
                )
                text_box = await page.locator("#text-input").bounding_box()
                assert text_box is not None
                await asyncio.to_thread(
                    xtest.click,
                    int(meta["sx"] + border_x + text_box["x"] + 10),
                    int(meta["sy"] + top_ui + text_box["y"] + 10),
                )
                await asyncio.to_thread(xtest.type_text, "probe")
                await page.wait_for_timeout(200)
                box = await page.locator("#scrollbox").bounding_box()
                assert box is not None
                await asyncio.to_thread(
                    xtest.scroll,
                    int(meta["sx"] + border_x + box["x"] + 30),
                    int(meta["sy"] + top_ui + box["y"] + 30),
                    -5,
                )
                await page.wait_for_timeout(300)
                # iframe target through the same XTEST mapping: the
                # frame pad's bounding box is in main-viewport CSS px.
                frame = page.frame(url=re.compile(r"/frame"))
                frame_click = None
                frame_error = None
                if frame is not None:
                    await frame.evaluate(
                        "() => { window.__events = []; }"
                    )
                    fpad = await frame.locator("#frame-pad").bounding_box()
                    frame_box = await page.locator("#frame").bounding_box()
                    if fpad is not None and frame_box is not None:
                        await asyncio.to_thread(
                            xtest.click,
                            int(meta["sx"] + border_x + fpad["x"] + 25),
                            int(meta["sy"] + top_ui + fpad["y"] + 20),
                        )
                        await page.wait_for_timeout(300)
                        fevents = await frame.evaluate(READ_EVENTS_SCRIPT)
                        frame_click = next(
                            (e for e in fevents if e["type"] == "click"), None
                        )
                        if frame_click is not None:
                            # Events inside the frame report client
                            # coordinates in the frame's own viewport
                            # space; the target must be expressed in
                            # that space too (pad box minus the frame
                            # element's box), not the main page's.
                            frame_error = [
                                round(
                                    frame_click.get("clientX", -999)
                                    - (fpad["x"] - frame_box["x"] + 25),
                                    2,
                                ),
                                round(
                                    frame_click.get("clientY", -999)
                                    - (fpad["y"] - frame_box["y"] + 20),
                                    2,
                                ),
                            ]
                l6_xtest.append(await s.signal())
                input_details["xtest"].append({
                    "window_meta": meta,
                    "mapping": {"border_x": border_x, "top_ui": top_ui,
                                "target_screen": [tx, ty],
                                "target_client": [pad["x"] + 40, pad["y"] + 30]},
                    "click_event": click,
                    "client_error": [
                        round(click.get("clientX", -999) - (pad["x"] + 40), 2),
                        round(click.get("clientY", -999) - (pad["y"] + 30), 2),
                    ] if click else None,
                    "frame_click_event": frame_click,
                    "frame_client_error": frame_error,
                    "text_value": await page.input_value("#text-input"),
                    "scroll_top": await page.evaluate(
                        "() => document.getElementById('scrollbox').scrollTop"
                    ),
                })
            print(f"L6-XTEST sample {i} done", flush=True)
        levels["L6_xtest_input"] = l6_xtest

        # AC-005 sub-scenarios: page zoom (DPR) and focus contention.
        async def window_meta(page) -> dict:
            return await page.evaluate(
                """() => ({sx: window.screenX, sy: window.screenY,
                           ow: window.outerWidth, oh: window.outerHeight,
                           iw: window.innerWidth, ih: window.innerHeight,
                           dpr: window.devicePixelRatio})"""
            )

        async def xtest_pad_click(page, xtest) -> dict:
            meta = await window_meta(page)
            bx = (meta["ow"] - meta["iw"]) / 2
            tu = (meta["oh"] - meta["ih"]) - bx
            pad = await page.locator("#pad").bounding_box()
            assert pad is not None
            await page.evaluate("() => { window.__events = []; }")
            await asyncio.to_thread(
                xtest.click,
                int(meta["sx"] + (bx + pad["x"] + 40) * meta["dpr"]),
                int(meta["sy"] + (tu + pad["y"] + 30) * meta["dpr"]),
            )
            await page.wait_for_timeout(300)
            events = await page.evaluate(READ_EVENTS_SCRIPT)
            click = next((e for e in events if e["type"] == "click"), {})
            return {
                "dpr": meta["dpr"],
                "target_client": [pad["x"] + 40, pad["y"] + 30],
                "click_client": [click.get("clientX"), click.get("clientY")],
                "client_error": [
                    round(click.get("clientX", -999) - (pad["x"] + 40), 2),
                    round(click.get("clientY", -999) - (pad["y"] + 30), 2),
                ] if click else None,
            }

        for i in range(2):
            async with Sample(obs, f"zoom-{i}") as s:
                page = s.page
                xtest = XTestInput(DISPLAY, xte_path=XTE, xauthority=s.runner.xauth_path)
                meta = await window_meta(page)
                bx = (meta["ow"] - meta["iw"]) / 2
                tu = (meta["oh"] - meta["ih"]) - bx
                await asyncio.to_thread(
                    xtest.click, meta["sx"] + 60, meta["sy"] + int(tu) + 60
                )
                zoom_keysyms = ("ctrl+plus", "ctrl+equal")
                for keys in zoom_keysyms:
                    await asyncio.to_thread(xtest.key, keys)
                await page.wait_for_timeout(500)
                after = await xtest_pad_click(page, xtest)
                pad = await page.locator("#pad").bounding_box()
                assert pad is not None
                await page.evaluate("() => { window.__events = []; }")
                await page.mouse.click(pad["x"] + 40, pad["y"] + 30)
                await page.wait_for_timeout(200)
                events = await page.evaluate(READ_EVENTS_SCRIPT)
                click = next((e for e in events if e["type"] == "click"), {})
                input_details["zoom"].append({
                    "keysym_attempted": list(zoom_keysyms),
                    "dpr_after_zoom_keys": after["dpr"],
                    "zoom_effective": after["dpr"] != 1,
                    "verdict": (
                        "measured"
                        if after["dpr"] != 1
                        else "inconclusive_shortcut_ineffective"
                    ),
                    "xtest_click": after,
                    "cdp_click": {
                        "click_client": [
                            click.get("clientX"), click.get("clientY")
                        ],
                        "client_error": [
                            round(
                                click.get("clientX", -999) - (pad["x"] + 40), 2
                            ),
                            round(
                                click.get("clientY", -999) - (pad["y"] + 30), 2
                            ),
                        ] if click else None,
                    },
                })
            print(f"zoom sample {i} done", flush=True)

        for i in range(2):
            async with Sample(obs, f"focus-{i}") as s:
                page = s.page
                ready = s.root / "ready.json"
                release = s.root / "release"
                proc = spawn_client([
                    "hold", "--endpoint", s.bridge.endpoint_url,
                    "--level", "L3", "--ready-file", str(ready),
                    "--release-file", str(release),
                    "--out", str(s.root / "hold.json"),
                ])
                try:
                    assert await wait_file(ready), "L3 hold never ready"
                    xtest = XTestInput(DISPLAY, xte_path=XTE, xauthority=s.runner.xauth_path)
                    input_details["focus_contention"].append({
                        "has_focus_during_L3": await page.evaluate(
                            "() => document.hasFocus()"
                        ),
                        "xtest_click": await xtest_pad_click(page, xtest),
                        "signal": await s.signal(),
                    })
                    release.write_text("go", encoding="utf-8")
                    await asyncio.to_thread(proc.wait, 30)
                finally:
                    if proc.poll() is None:
                        proc.kill()
            print(f"focus sample {i} done", flush=True)
    finally:
        obs.__exit__()

    summary = summarize_levels(levels)
    report = build_report(
        levels=levels, summary=summary, input_comparison=input_details
    )
    report_dir = Path(
        os.environ.get("CBROWSER_T029_REPORT_DIR", ".")
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "levels.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


asyncio.run(main())
