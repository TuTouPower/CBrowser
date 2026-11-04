"""E2E verification for t020 per-profile CJK font bundles.

Scenarios run inside the real Browser Runtime image:

- ``image_layout`` (AC-001): the built image stages both WenQuanYi bundles
  under /opt/cbrowser-fonts (outside fontconfig's default scan paths) and a
  default container resolves no CJK font for sans-serif.
- ``render`` (AC-003/AC-004): a profile started with each bundle value
  renders Chinese in real Chrome accordingly, proven by canvas text metrics,
  a CDP platform-font query for the explicit bundle family, fc-list/fc-match
  under the profile fontconfig, and the FONTCONFIG_FILE actually present in
  the Chrome process environment.
- ``isolation`` (AC-005): two profiles with different bundles run at the
  same time in one container and each sees only its own bundle.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest

from e2e_env import require_e2e_env


def get_docker_image() -> str:
    return require_e2e_env("CBROWSER_RUNTIME_TEST_IMAGE")[
        "CBROWSER_RUNTIME_TEST_IMAGE"
    ]


def get_engine_cache_dir() -> Path:
    return Path(
        require_e2e_env("CBROWSER_RUNTIME_ENGINE_CACHE")[
            "CBROWSER_RUNTIME_ENGINE_CACHE"
        ]
    )


def check_prerequisites() -> tuple[bool, str]:
    res = subprocess.run(
        ["which", "docker"], capture_output=True, text=True, check=False
    )
    if res.returncode != 0:
        return False, "Docker CLI not found on host"
    cache = get_engine_cache_dir()
    if not cache.exists() or not any(cache.iterdir()):
        return False, f"Engine cache directory missing or empty at {cache}"
    image = get_docker_image()
    insp = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if insp.returncode != 0:
        return False, f"Docker image {image} not present locally"
    return True, "Ready"


CONTAINER_SCRIPT = """import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from cbrowser.runtime_agent.runner import BrowserRunner

ZH_TEXT = "中文测试汉字"
PUA_TEXT = "\\ue000\\ue001\\ue002\\ue003\\ue004\\ue005"
PAGE_HTML = (
    "<html><body>"
    "<div id='zhprobe' style='font-family: sans-serif; font-size: 48px;'>"
    + ZH_TEXT
    + "</div>"
    "<div id='zhprobe-explicit' "
    "style='font-family: __FONT_FAMILY__; font-size: 48px;'>"
    + ZH_TEXT
    + "</div></body></html>"
)

MEASURE_JS = \"\"\"() => {
  const g = document.createElement('canvas').getContext('2d');
  const zh = '中文测试汉字';
  const pua = '\\ue000\\ue001\\ue002\\ue003\\ue004\\ue005';
  const w = (text, font) => { g.font = font; return g.measureText(text).width; };
  return {
    sansZh: w(zh, '64px sans-serif'),
    sansPua: w(pua, '64px sans-serif'),
  };
}\"\"\"


def write_snapshot(profile_id: str, bundle: str, path: Path) -> None:
    snap = {
        "id": f"snap_{profile_id}",
        "profile_id": profile_id,
        "version": 1,
        "config": {
            "name": f"E2E {profile_id}",
            "geoip": False,
            "set_google_default": False,
            "font_bundle": bundle,
        },
        "created_at": "2026-11-04T00:00:00Z",
    }
    path.write_text(json.dumps(snap), encoding="utf-8")


def chrome_fontconfig_env(pid: int) -> str | None:
    raw = Path(f"/proc/{pid}/environ").read_bytes().decode("utf-8", "replace")
    for entry in raw.split("\\0"):
        if entry.startswith("FONTCONFIG_FILE="):
            return entry.split("=", 1)[1]
    return None


def fontconfig_env(fontconfig_file: str | None) -> dict[str, str]:
    env = dict(os.environ)
    if fontconfig_file is None:
        env.pop("FONTCONFIG_FILE", None)
    else:
        env["FONTCONFIG_FILE"] = fontconfig_file
    return env


def fc_listing(fontconfig_file: str | None) -> str:
    return subprocess.run(
        ["fc-list"],
        env=fontconfig_env(fontconfig_file),
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def fc_match(fontconfig_file: str | None, pattern: str) -> str:
    return subprocess.run(
        ["fc-match", "-f", "%{family}", pattern],
        env=fontconfig_env(fontconfig_file),
        capture_output=True,
        text=True,
        check=True,
    ).stdout


async def platform_font_families(page, selector: str) -> list[str]:
    session = await page.context.new_cdp_session(page)
    await session.send("DOM.enable")
    await session.send("CSS.enable")
    doc = await session.send("DOM.getDocument", {"depth": 1})
    probe = await session.send(
        "DOM.querySelector",
        {"nodeId": doc["root"]["nodeId"], "selector": selector},
    )
    result = await session.send(
        "CSS.getPlatformFontsForNode", {"nodeId": probe["nodeId"]}
    )
    return [f["familyName"] for f in result["fonts"]]


async def start_runner(profile_id: str, bundle: str, display: str):
    base = Path(f"/tmp/{profile_id}")
    run_dir = base / "run"
    prof_dir = base / "prof"
    events_dir = base / "events"
    for directory in (run_dir, prof_dir, events_dir):
        directory.mkdir(parents=True, exist_ok=True)
    # The image sets one PulseAudio runtime dir; two concurrent runners in a
    # single test container need their own daemon pid/socket directory.
    os.environ["PULSE_RUNTIME_PATH"] = f"/tmp/pulse-runtime-{profile_id}"
    snap_path = base / "snap.json"
    write_snapshot(profile_id, bundle, snap_path)
    runner = BrowserRunner(
        profile_id=profile_id,
        runtime_instance_id=f"inst_{profile_id}",
        config_snapshot_path=snap_path,
        run_dir=run_dir,
        user_data_dir=prof_dir,
        events_dir=events_dir,
        engine_cache_dir="/data/engine-cache",
        display=display,
    )
    await runner.start()
    return runner


def bundle_family(bundle: str) -> str:
    return (
        "WenQuanYi Micro Hei"
        if bundle == "wqy-microhei"
        else "WenQuanYi Zen Hei"
    )


async def measure_profile(runner, bundle: str) -> dict:
    page = await runner.browser_context.new_page()
    try:
        if bundle == "none":
            html = PAGE_HTML.replace("__FONT_FAMILY__", "sans-serif")
            selector = "#zhprobe"
        else:
            expected = bundle_family(bundle)
            html = PAGE_HTML.replace("__FONT_FAMILY__", expected)
            selector = "#zhprobe-explicit"
        await page.goto("data:text/html," + html)
        metrics = await page.evaluate(MEASURE_JS)
        families = await platform_font_families(page, selector)
    finally:
        await page.close()
    return {
        "metrics": metrics,
        "families": families,
        "fontconfig_file": chrome_fontconfig_env(runner.chrome_pid),
    }


def scenario_image_layout() -> dict:
    micro = Path("/opt/cbrowser-fonts/wqy-microhei/wqy-microhei.ttc")
    zen = Path("/opt/cbrowser-fonts/wqy-zenhei/wqy-zenhei.ttc")
    assert micro.is_file(), "microhei bundle missing from /opt/cbrowser-fonts"
    assert zen.is_file(), "zenhei bundle missing from /opt/cbrowser-fonts"
    in_default_tree = [
        str(p)
        for p in Path("/usr/share/fonts").rglob("*")
        if "wqy" in p.name.lower()
    ]
    assert not in_default_tree, f"bundles leaked into default tree: {in_default_tree}"
    fc_list = subprocess.run(
        ["fc-list"], capture_output=True, text=True, check=True
    ).stdout
    assert "WenQuanYi" not in fc_list, "default fc-list exposes a bundle"
    fc_match = subprocess.run(
        ["fc-match", "sans-serif:lang=zh"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "WenQuanYi" not in fc_match, f"default zh match hit a bundle: {fc_match}"
    return {"status": "PASS", "scenario": "image_layout"}


async def scenario_render(bundle: str) -> dict:
    runner = await start_runner(f"prof_{bundle}", bundle, ":99")
    try:
        result = await measure_profile(runner, bundle)
    finally:
        await runner.stop()
    metrics, families = result["metrics"], result["families"]
    fontconfig_file = result["fontconfig_file"]
    if bundle == "none":
        assert fontconfig_file is None, result
        assert abs(metrics["sansZh"] - metrics["sansPua"]) < 0.01, metrics
        assert not any("WenQuanYi" in f for f in families), families
        assert "WenQuanYi" not in fc_listing(None), result
    else:
        expected = bundle_family(bundle)
        other = (
            "WenQuanYi Zen Hei" if bundle == "wqy-microhei"
            else "WenQuanYi Micro Hei"
        )
        assert fontconfig_file is not None, result
        assert fontconfig_file.endswith("profile-fonts.conf"), result
        assert expected in families, families
        assert other not in families, families
        assert abs(metrics["sansZh"] - metrics["sansPua"]) > 0.01, metrics
        listing = fc_listing(fontconfig_file)
        assert expected in listing, listing
        assert other not in listing, listing
        assert expected in fc_match(fontconfig_file, expected), result
        assert other not in fc_match(fontconfig_file, other), result
    return {"status": "PASS", "scenario": f"render:{bundle}", **result}


async def scenario_isolation() -> dict:
    runner_a = await start_runner("prof_iso_micro", "wqy-microhei", ":99")
    runner_b = await start_runner("prof_iso_none", "none", ":100")
    try:
        result_a = await measure_profile(runner_a, "wqy-microhei")
        result_b = await measure_profile(runner_b, "none")
    finally:
        await runner_a.stop()
        await runner_b.stop()
    assert "WenQuanYi Micro Hei" in result_a["families"], result_a
    assert not any(
        "WenQuanYi" in f for f in result_b["families"]
    ), result_b
    assert result_a["fontconfig_file"] is not None, result_a
    assert result_b["fontconfig_file"] is None, result_b
    assert result_a["fontconfig_file"] != result_b["fontconfig_file"]
    metrics_a = result_a["metrics"]
    metrics_b = result_b["metrics"]
    assert abs(metrics_a["sansZh"] - metrics_a["sansPua"]) > 0.01, metrics_a
    assert abs(metrics_b["sansZh"] - metrics_b["sansPua"]) < 0.01, metrics_b
    listing_a = fc_listing(result_a["fontconfig_file"])
    assert "WenQuanYi Micro Hei" in listing_a, listing_a
    assert "WenQuanYi Zen Hei" not in listing_a, listing_a
    assert "WenQuanYi" not in fc_listing(None), result_b
    return {
        "status": "PASS",
        "scenario": "isolation",
        "micro": result_a,
        "none": result_b,
    }


async def run_scenario() -> None:
    scenario = sys.argv[1]
    if scenario == "image_layout":
        print(json.dumps(scenario_image_layout()))
    elif scenario.startswith("render:"):
        print(json.dumps(await scenario_render(scenario.split(":", 1)[1])))
    elif scenario == "isolation":
        print(json.dumps(await scenario_isolation()))
    else:
        raise SystemExit(f"unknown scenario {scenario}")


if __name__ == "__main__":
    asyncio.run(run_scenario())
"""


def _run_docker_e2e(scenario: str, timeout: int = 300) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:8]
    container_name = f"cbrowser-t020-fonts-{run_id}"
    image = get_docker_image()
    cache_dir = get_engine_cache_dir().resolve()

    scratch_run = Path(tempfile.mkdtemp(prefix="cbrowser-t020-fonts-", dir="/tmp"))
    script_path = scratch_run / "e2e_runner.py"
    script_path.write_text(CONTAINER_SCRIPT, encoding="utf-8")

    cmd = [
        "docker",
        "run",
        "--name",
        container_name,
        "--label",
        "cbrowser.task=t020",
        "--label",
        f"cbrowser.run_id={run_id}",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--shm-size",
        "1g",
        "--tmpfs",
        "/tmp:rw,exec,mode=1777",
        "--tmpfs",
        "/home/cbrowser:rw,mode=0755",
        "--entrypoint",
        "python3",
        "-v",
        f"{cache_dir}:/data/engine-cache:ro",
        "-v",
        f"{script_path}:/e2e_runner.py:ro",
        image,
        "/e2e_runner.py",
        scenario,
    ]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        output = proc.stdout + "\n" + proc.stderr
        (scratch_run / "container.log").write_text(output, encoding="utf-8")
        last_json = None
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                    if "status" in data:
                        last_json = data
                except json.JSONDecodeError:
                    pass
        if proc.returncode != 0 or not last_json or last_json.get("status") != "PASS":
            raise AssertionError(
                f"Container test failed (exit {proc.returncode}):\n{output}"
            )
        return last_json
    finally:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            check=False,
        )


class TestBrowserFontBundlesE2E:
    """E2E verification in the real Browser image with real Chrome."""

    @pytest.fixture(autouse=True)
    def require_prerequisites(self):
        ready, reason = check_prerequisites()
        if not ready:
            message = f"E2E prerequisites missing: {reason}"
            if os.environ.get("CBROWSER_E2E_REQUIRED") == "1":
                pytest.fail(message, pytrace=False)
            pytest.skip(message)

    def test_image_layout_keeps_bundles_out_of_default_scan(self):
        result = _run_docker_e2e("image_layout", timeout=120)
        assert result["status"] == "PASS"

    @pytest.mark.parametrize(
        "bundle", ["none", "wqy-microhei", "wqy-zenhei"]
    )
    def test_profile_renders_chinese_per_font_bundle(self, bundle: str):
        result = _run_docker_e2e(f"render:{bundle}")
        assert result["status"] == "PASS"

    def test_simultaneous_profiles_do_not_share_font_bundles(self):
        result = _run_docker_e2e("isolation", timeout=420)
        assert result["status"] == "PASS"
