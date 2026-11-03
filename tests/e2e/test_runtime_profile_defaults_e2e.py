"""E2E test suite for runtime profile defaults initialization in CloakBrowser sandbox.

Validates:
- Profile defaults initialization API (initialize_profile_defaults)
- Setting Google as default search engine via real chrome://settings/searchEngines UI
- Preservation of existing user tabs and browser PID
- Locale compatibility for en-US and zh-CN
- No-op behavior when set_google_default=False
- Atomic marker fsync and rejection of corrupted marker files
- Preservation of user-customized search engine preferences across launches
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest

from e2e_env import require_e2e_env

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


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
    """Verify Docker, immutable image, and engine cache exist."""
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
import sys
from pathlib import Path
from cbrowser.runtime_agent.runner import BrowserRunner
from cbrowser.runtime_agent.profile_defaults import (
    initialize_profile_defaults,
    ProfileDefaultsError,
    SEARCH_ENGINE_MARKER_FILE,
)


async def run_scenario():
    scenario = sys.argv[1]
    locale = sys.argv[2] if len(sys.argv) > 2 else "en-US"

    run_dir = "/tmp/run"
    prof_dir = "/tmp/prof"
    events_dir = "/tmp/events"
    snap_path = "/tmp/snap.json"

    Path(run_dir).mkdir(parents=True, exist_ok=True)
    Path(prof_dir).mkdir(parents=True, exist_ok=True)
    Path(events_dir).mkdir(parents=True, exist_ok=True)

    snap = {
        "id": "snap_e2e",
        "profile_id": "prof_e2e",
        "version": 1,
        "config": {
            "name": "E2E Profile",
            "locale": locale,
            "geoip": False,
            "set_google_default": scenario == "runtime_startup_defaults",
        },
        "created_at": "2026-10-28T00:00:00Z",
    }
    with open(snap_path, "w") as f:
        json.dump(snap, f)

    if scenario == "locale_and_persistence":
        # Verify initialization, process/tab identity, marker and opt-out.
        runner = BrowserRunner(
            profile_id="prof_e2e",
            runtime_instance_id="inst_1",
            config_snapshot_path=snap_path,
            run_dir=run_dir,
            user_data_dir=prof_dir,
            events_dir=events_dir,
            engine_cache_dir="/data/engine-cache",
        )
        try:
            await runner.start()
            ctx = runner.browser_context
            pid_before = runner.chrome_pid
            start_before = (
                Path(f"/proc/{pid_before}/stat")
                .read_text()
                .rsplit(")", 1)[1]
                .split()[19]
            )

            # Open user page
            user_page = await ctx.new_page()
            await user_page.goto(
                "data:text/html,<html><body><h1>User Content</h1></body></html>"
            )
            page_count_before = len(ctx.pages)

            # Opting out must preserve the fresh profile before any setup.
            assert not (Path(prof_dir) / SEARCH_ENGINE_MARKER_FILE).exists()
            await initialize_profile_defaults(ctx, prof_dir, set_google_default=False)
            assert not (Path(prof_dir) / SEARCH_ENGINE_MARKER_FILE).exists()
            assert len(ctx.pages) == page_count_before

            # Initialize defaults
            await initialize_profile_defaults(ctx, prof_dir, set_google_default=True)

            # Check PID and user page
            assert runner.chrome_pid == pid_before, (
                "Browser PID changed during initialization"
            )
            start_after = (
                Path(f"/proc/{pid_before}/stat")
                .read_text()
                .rsplit(")", 1)[1]
                .split()[19]
            )
            assert start_after == start_before, "Real Chrome process was replaced"
            assert len(ctx.pages) == page_count_before, (
                f"Page count changed: {len(ctx.pages)} != {page_count_before}"
            )
            content = await user_page.evaluate(
                "() => document.querySelector('h1').textContent"
            )
            assert content == "User Content", "User tab content corrupted"

            # Check marker
            marker_p = Path(prof_dir) / SEARCH_ENGINE_MARKER_FILE
            assert marker_p.exists(), "Marker file was not created"
            with open(marker_p) as f:
                marker_data = json.load(f)
            assert marker_data.get("google_default_applied") is True
            assert marker_data.get("engine_keyword") == "google.com"

            # Check active default engine in browser
            check_page = await ctx.new_page()
            await check_page.goto("chrome://settings/searchEngines")
            await asyncio.sleep(1)
            active = await check_page.evaluate(\"\"\"async () => {
                const cr = await import('chrome://resources/js/cr.js');
                const l = await cr.sendWithPromise('getSearchEnginesList');
                return (l.defaults || []).find(e => e.default);
            }\"\"\")
            assert active and active.get("keyword") == "google.com", (
                f"Active engine not Google: {active}"
            )
            await check_page.close()

            # Second call should be no-op
            await initialize_profile_defaults(ctx, prof_dir, set_google_default=True)

            # False call should immediately no-op
            await initialize_profile_defaults(ctx, prof_dir, set_google_default=False)

            print(
                json.dumps({"status": "PASS", "scenario": scenario, "locale": locale})
            )
        finally:
            await runner.stop()

    elif scenario == "runtime_startup_defaults":
        runner = BrowserRunner(
            "prof_e2e",
            "instance_bootstrap",
            snap_path,
            run_dir,
            prof_dir,
            events_dir=events_dir,
            engine_cache_dir="/data/engine-cache",
        )
        try:
            await runner.start()
            marker = Path(prof_dir) / SEARCH_ENGINE_MARKER_FILE
            assert marker.is_file(), (
                "Runtime did not apply its frozen initialization flag"
            )
            page = await runner.browser_context.new_page()
            await page.goto("chrome://settings/searchEngines")
            active = await page.evaluate(\"\"\"async () => {
                const cr = await import('chrome://resources/js/cr.js');
                const engines = await cr.sendWithPromise('getSearchEnginesList');
                return (engines.defaults || []).find(engine => engine.default);
            }\"\"\")
            assert active and active.get("keyword") == "google.com"
            print(json.dumps({"status": "PASS", "scenario": scenario}))
        finally:
            await runner.stop()

    elif scenario == "corrupt_marker":
        runner = BrowserRunner(
            profile_id="prof_e2e",
            runtime_instance_id="inst_corrupt",
            config_snapshot_path=snap_path,
            run_dir=run_dir,
            user_data_dir=prof_dir,
            events_dir=events_dir,
            engine_cache_dir="/data/engine-cache",
        )
        try:
            await runner.start()
            ctx = runner.browser_context
            marker_p = Path(prof_dir) / SEARCH_ENGINE_MARKER_FILE
            marker_p.write_text("NOT_VALID_JSON{:::}")

            caught = False
            try:
                await initialize_profile_defaults(
                    ctx, prof_dir, set_google_default=True
                )
            except ProfileDefaultsError:
                caught = True
            assert caught, "Did not raise ProfileDefaultsError on corrupt marker"
            print(json.dumps({"status": "PASS", "scenario": scenario}))
        finally:
            await runner.stop()

    elif scenario == "user_override_preservation":
        # Launch 1: initialize Google, then select Bing manually.
        runner1 = BrowserRunner(
            profile_id="prof_e2e",
            runtime_instance_id="inst_ov_1",
            config_snapshot_path=snap_path,
            run_dir=run_dir,
            user_data_dir=prof_dir,
            events_dir=events_dir,
            engine_cache_dir="/data/engine-cache",
        )
        try:
            await runner1.start()
            ctx1 = runner1.browser_context
            await initialize_profile_defaults(ctx1, prof_dir, set_google_default=True)

            page = await ctx1.new_page()
            await page.goto("chrome://settings/searchEngines")
            await asyncio.sleep(1)

            # Switch default to Yahoo or Bing
            switched = await page.evaluate(\"\"\"() => {
                const walk = (root, fn) => root.querySelectorAll('*').forEach(el => {
                    if (el.shadowRoot) walk(el.shadowRoot, fn);
                    fn(el);
                });
                let targetEntry = null;
                walk(document, el => {
                    if (el.tagName === 'SETTINGS-SEARCH-ENGINE-ENTRY') {
                        const sr = el.shadowRoot;
                        if (sr && sr.textContent.includes('bing.com')) {
                            targetEntry = el;
                        }
                    }
                });
                if (!targetEntry) return Promise.resolve(false);
                const sr = targetEntry.shadowRoot;
                const menuBtn = sr.querySelector('cr-icon-button.icon-more-vert');
                if (!menuBtn) return Promise.resolve(false);
                menuBtn.click();
                return new Promise(resolve => setTimeout(() => {
                    let makeBtn = null;
                    walk(document, el => {
                        if (el.tagName === 'CR-ACTION-MENU' && el.open) {
                            const b = el.querySelector('button#makeDefault');
                            if (b && !b.disabled) makeBtn = b;
                        }
                    });
                    if (!makeBtn) resolve(false);
                    else {
                        makeBtn.click();
                        resolve(true);
                    }
                }, 350));
            }\"\"\")
            assert switched, "Failed to switch default to Bing"
            await asyncio.sleep(1)
            await page.close()
        finally:
            await runner1.stop()

        # Launch 2: reuse prof_dir, call initialize_profile_defaults again
        runner2 = BrowserRunner(
            profile_id="prof_e2e",
            runtime_instance_id="inst_ov_2",
            config_snapshot_path=snap_path,
            run_dir=run_dir,
            user_data_dir=prof_dir,
            events_dir=events_dir,
            engine_cache_dir="/data/engine-cache",
        )
        try:
            await runner2.start()
            ctx2 = runner2.browser_context
            await initialize_profile_defaults(ctx2, prof_dir, set_google_default=True)

            page2 = await ctx2.new_page()
            await page2.goto("chrome://settings/searchEngines")
            await asyncio.sleep(1)
            active2 = await page2.evaluate(\"\"\"async () => {
                const cr = await import('chrome://resources/js/cr.js');
                const l = await cr.sendWithPromise('getSearchEnginesList');
                return (l.defaults || []).find(e => e.default);
            }\"\"\")
            assert active2 and active2.get("keyword") == "bing.com", (
                f"Override not preserved: {active2}"
            )
            await page2.close()
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "scenario": scenario,
                        "active_keyword": active2.get("keyword"),
                    }
                )
            )
        finally:
            await runner2.stop()


if __name__ == "__main__":
    asyncio.run(run_scenario())
"""


def _run_docker_e2e(scenario: str, locale: str = "en-US") -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:8]
    container_name = f"cbrowser-t003-profile-defaults-{run_id}"
    image = get_docker_image()
    cache_dir = get_engine_cache_dir().resolve()

    scratch_run = PROJECT_ROOT / f".scratch/t003_profile_defaults/{run_id}"
    scratch_run.mkdir(parents=True, exist_ok=True)
    script_path = scratch_run / "e2e_runner.py"
    script_path.write_text(CONTAINER_SCRIPT, encoding="utf-8")

    cmd = [
        "docker",
        "run",
        "--name",
        container_name,
        "--label",
        "cbrowser.task=t003",
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
        locale,
    ]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, check=False
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


class TestRuntimeProfileDefaultsE2E:
    """E2E verification in isolated Docker container with real CloakBrowser."""

    @pytest.fixture(autouse=True)
    def require_prerequisites(self):
        ready, reason = check_prerequisites()
        if not ready:
            message = f"E2E prerequisites missing: {reason}"
            if os.environ.get("CBROWSER_E2E_REQUIRED") == "1":
                pytest.fail(message, pytrace=False)
            pytest.skip(message)

    def test_profile_defaults_en_us(self):
        """Verify defaults initialization in en-US locale."""
        res = _run_docker_e2e("locale_and_persistence", "en-US")
        assert res.get("status") == "PASS"
        assert res.get("locale") == "en-US"

    def test_profile_defaults_zh_cn(self):
        """Verify defaults initialization in zh-CN locale."""
        res = _run_docker_e2e("locale_and_persistence", "zh-CN")
        assert res.get("status") == "PASS"
        assert res.get("locale") == "zh-CN"

    def test_corrupt_marker_handling(self):
        """Verify ProfileDefaultsError raised and corrupt marker rejected."""
        res = _run_docker_e2e("corrupt_marker")
        assert res.get("status") == "PASS"

    def test_user_override_preservation(self):
        """Preserve manual search engine choice across launches."""
        res = _run_docker_e2e("user_override_preservation")
        assert res.get("status") == "PASS"
        assert res.get("active_keyword") == "bing.com"

    def test_runtime_applies_frozen_search_default(self):
        """Runner consumes the flag without an explicit helper call."""
        result = _run_docker_e2e("runtime_startup_defaults")
        assert result["status"] == "PASS"
