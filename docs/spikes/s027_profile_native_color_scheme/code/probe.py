"""Run isolated native Chromium theme trials through the real BrowserRunner."""

import asyncio
import ctypes as c
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from cbrowser.runtime_agent.event_storage import atomic_write_json
from cbrowser.runtime_agent.runner import BrowserRunner


BUILD = "146.0.7680.177.3"
WIDTH, HEIGHT = 1120, 720
ROOT = Path("/tmp/theme_probe")
EVIDENCE = Path("/evidence")
THEME_MODES = {"light": 1, "dark": 2}
ADAPTIVE = """
<title>Theme probe</title>
<style>
  body { background: #f4f5f6; color: #252525; font: 24px sans-serif; }
  @media (prefers-color-scheme: dark) {
    body { background: #202124; color: #f4f5f6; }
  }
</style>
<p>Website with dark palette</p>
"""
FIXED = """<title>Fixed page</title><body style="background:#ffffff;color:#111111">
<p>Website with a fixed white background</p></body>"""
READ_WEB = """() => ({
  scheme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
  background: getComputedStyle(document.body).backgroundColor
})"""


def bind(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


def capture(runner, destination, expected_body_rgb=None):
    x11 = c.CDLL("libX11.so.6")
    cairo = c.CDLL("libcairo.so.2")
    pointer = c.c_void_p
    open_display = bind(x11, "XOpenDisplay", pointer, c.c_char_p)
    root_window = bind(x11, "XDefaultRootWindow", c.c_ulong, pointer)
    visual = bind(x11, "XDefaultVisual", pointer, pointer, c.c_int)
    screen = bind(x11, "XDefaultScreen", c.c_int, pointer)
    close_display = bind(x11, "XCloseDisplay", c.c_int, pointer)
    make_surface = bind(
        cairo, "cairo_xlib_surface_create", pointer,
        pointer, c.c_ulong, pointer, c.c_int, c.c_int,
    )
    write_png = bind(cairo, "cairo_surface_write_to_png", c.c_int, pointer, c.c_char_p)
    destroy_surface = bind(cairo, "cairo_surface_destroy", None, pointer)
    get_image = bind(
        x11, "XGetImage", pointer,
        pointer, c.c_ulong, c.c_int, c.c_int, c.c_uint, c.c_uint, c.c_ulong, c.c_int,
    )
    get_pixel = bind(x11, "XGetPixel", c.c_ulong, pointer, c.c_int, c.c_int)
    destroy_image = bind(x11, "XDestroyImage", c.c_int, pointer)
    previous_xauth = os.environ.get("XAUTHORITY")
    os.environ["XAUTHORITY"] = str(runner.xauth_path)
    try:
        display = open_display(runner.display.encode())
    finally:
        if previous_xauth is None:
            del os.environ["XAUTHORITY"]
        else:
            os.environ["XAUTHORITY"] = previous_xauth
    if not display:
        raise RuntimeError(f"Could not open {runner.display}")
    try:
        root = root_window(display)
        if expected_body_rgb is not None:
            sample = get_image(display, root, 600, 500, 1, 1, 0xFFFFFF, 2)
            if not sample:
                raise RuntimeError("X11 pixel sample failed")
            try:
                if get_pixel(sample, 0, 0) != expected_body_rgb:
                    return False
            finally:
                destroy_image(sample)
        surface = make_surface(
            display, root, visual(display, screen(display)), WIDTH, HEIGHT
        )
        try:
            status = write_png(surface, os.fsencode(destination))
            if status:
                raise RuntimeError(f"Cairo screenshot failed with status {status}")
        finally:
            destroy_surface(surface)
    finally:
        close_display(display)
    return True


def preferences_path(profile):
    return ROOT / profile / "data" / "Default" / "Preferences"


def read_preferences(profile):
    path = preferences_path(profile)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def apply_native_mode(profile, theme, system_theme):
    path = preferences_path(profile)
    preferences = read_preferences(profile)
    preferences.setdefault("browser", {}).setdefault("theme", {})["color_scheme2"] = (
        THEME_MODES[theme]
    )
    preferences.setdefault("extensions", {}).setdefault("theme", {})["system_theme"] = (
        system_theme
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, preferences)


def observed_preferences(profile):
    values = read_preferences(profile)
    return {
        "native": values.get("browser", {}).get("theme", {}).get("color_scheme2"),
        "system": values.get("extensions", {}).get("theme", {}).get("system_theme"),
    }


def press_key(runner, key):
    environment = dict(os.environ, DISPLAY=runner.display, XAUTHORITY=str(runner.xauth_path))
    subprocess.run(["xdotool", "key", "--clearmodifiers", key], env=environment, check=True)


async def capture_when_painted(runner, destination, expected_body_rgb):
    for attempt in range(32):
        if capture(runner, destination, expected_body_rgb):
            return
        if attempt == 3:
            press_key(runner, "alt+f")
            await asyncio.sleep(0.2)
            press_key(runner, "Escape")
        await asyncio.sleep(0.15)
    raise RuntimeError(f"The X11 page did not paint the expected color for {destination.name}")


async def start_case(label, profile, theme, display=":91", system_theme=0):
    run = ROOT / profile / label
    run.mkdir(parents=True)
    os.environ["PULSE_RUNTIME_PATH"] = str(run / "pulse_server")
    case_config = {
        "id": "theme_snapshot",
        "profile_id": profile,
        "version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "config": {
            "name": "Theme probe",
            "locale": "en-US",
            "color_scheme": theme,
            "font_set_id": os.environ["THEME_PROBE_FONT_SET_ID"],
            "include_cjk_fonts": True,
            "fingerprint_seed": 19419,
            "screen_width": WIDTH,
            "screen_height": HEIGHT,
            "geoip": False,
            "humanize": False,
            "set_google_default": False,
            "restore_session": False,
        },
    }
    snapshot = run / "snapshot.json"
    atomic_write_json(snapshot, case_config)
    if system_theme is not None:
        apply_native_mode(profile, theme, system_theme)
    runner = BrowserRunner(
        profile_id=profile, runtime_instance_id=label, config_snapshot_path=snapshot,
        run_dir=run, user_data_dir=ROOT / profile / "data", display=display,
        engine_build=BUILD,
    )
    try:
        await runner.start()
        return runner
    except BaseException:
        await runner.stop()
        raise


async def record(label, runner):
    context = runner.browser_context
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto("data:text/html," + quote(FIXED))
    fixed = await page.evaluate(READ_WEB)
    await page.goto("data:text/html," + quote(ADAPTIVE))
    adaptive = await page.evaluate(READ_WEB)
    await page.bring_to_front()
    dark = adaptive["scheme"] == "dark"
    expected_body_rgb = 0x202124 if dark else 0xF4F5F6
    await capture_when_painted(runner, EVIDENCE / f"{label}_window.png", expected_body_rgb)
    press_key(runner, "alt+f")
    await asyncio.sleep(0.25)
    capture(runner, EVIDENCE / f"{label}_menu.png")
    press_key(runner, "Escape")
    if label == "then_dark":
        await page.goto("data:text/html," + quote(FIXED))
        await capture_when_painted(runner, EVIDENCE / "dark_fixed_white.png", 0xFFFFFF)
    assert adaptive["scheme"] == runner.profile_config.color_scheme
    assert fixed == {"scheme": adaptive["scheme"], "background": "rgb(255, 255, 255)"}
    assert adaptive["background"] == (
        "rgb(32, 33, 36)" if adaptive["scheme"] == "dark" else "rgb(244, 245, 246)"
    )
    return {
        "profile": runner.profile_id, "display": runner.display,
        "adaptive": adaptive, "fixed": fixed,
        "engine": runner.engine_artifact_info["engine_build"],
    }


async def main():
    output = {}
    for label, theme, system_theme in (
        ("baseline_dark", "dark", None),
        ("first_light", "light", 0),
        ("then_dark", "dark", 0),
        ("back_light", "light", 0),
        ("gtk_dark_requested", "dark", 1),
        ("gtk_override_dark", "dark", 0),
    ):
        runner = await start_case(label, "theme_a", theme, system_theme=system_theme)
        try:
            output[label] = await record(label, runner)
            if label == "back_light":
                other = await start_case("parallel_dark", "theme_b", "dark", display=":92")
                try:
                    output["parallel_light"] = await record("parallel_light", runner)
                    output["parallel_dark"] = await record("parallel_dark", other)
                finally:
                    await other.stop()
                output["parallel_dark"]["persisted"] = observed_preferences("theme_b")
        finally:
            await runner.stop()
        output[label]["persisted"] = observed_preferences("theme_a")
        atomic_write_json(EVIDENCE / "runtime_results.json", output)


if __name__ == "__main__":
    asyncio.run(main())
