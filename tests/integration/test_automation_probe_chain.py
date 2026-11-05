"""t029 probe: real Playwright process through the production tunnel.

Chain under test, all real components in-process or subprocess:
external Playwright process -> CdpBridge (discovery + recorder) ->
API automation WS (cbat_ token) -> Supervisor control WS -> Agent UDS
(run_uds_agent + CdpProxyManager) -> real browser loopback CDP.

Browsers: the target engine via the production BrowserRunner launch
path (host Xvfb substitutions only) and ordinary Chromium via a vanilla
Playwright persistent context.  Tests skip when a prerequisite is not
installed; they never substitute one engine's result for the other's.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import httpx
import pytest
import uvicorn
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))

from automation_probe.harness import (  # noqa: E402
    CdpBridge,
    ObservationServer,
    build_report,
    chromium_executable,
    devtools_ws_url,
    engine_cache_dir,
    find_browser_pid,
    free_port,
    host_runner_class,
    start_xvfb,
    write_profile_snapshot,
)
from cbrowser.adapters.database.migrations import run_database_migrations  # noqa: E402
from cbrowser.adapters.database.repository import ProfileRepository  # noqa: E402
from cbrowser.adapters.database.session import create_engine_and_maker  # noqa: E402
from cbrowser.api.app import create_app  # noqa: E402
from cbrowser.domain.models import ProfileConfig  # noqa: E402
from cbrowser.runtime_agent.agent import run_uds_agent  # noqa: E402
from cbrowser.supervisor.control_server import create_control_app  # noqa: E402
from cbrowser.supervisor.path_validator import PathValidator  # noqa: E402

CLIENT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "automation_probe"
    / "probe_client.py"
)
SEED = 290029


class _UvicornThread:
    def __init__(self, app, port: int):
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> int:
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                return int(self.server.config.port)
            time.sleep(0.05)
        raise RuntimeError("uvicorn did not start")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


def _report_dir(root: Path) -> Path:
    override = os.environ.get("CBROWSER_T029_REPORT_DIR")
    return Path(override) if override else root


async def _run_client(
    *argv: str, timeout: float = 180
) -> tuple[int, dict | None, str]:
    """Run the probe client without blocking this process's event loop.

    The Agent UDS server lives in the test's own loop; a blocking
    subprocess.run here froze it, the tunnel's 10 s ping timed out and
    the chain collapsed (measured during t029 development).
    """
    env = dict(os.environ)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    proc = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, str(CLIENT), *argv],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    out_file = None
    if "--out" in argv:
        out_file = Path(argv[argv.index("--out") + 1])
    payload = None
    if out_file is not None and out_file.exists():
        payload = json.loads(out_file.read_text(encoding="utf-8"))
    return proc.returncode, payload, proc.stderr


class _Chain:
    """Real API + Supervisor control + Agent UDS around a live browser."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="cbrowser-t029-", dir="/tmp"))
        self.api_port = 0
        self.token = ""
        self.downloads = self.root / "data" / "downloads"
        self._api: _UvicornThread | None = None
        self._supervisor: _UvicornThread | None = None
        self._agent_task: asyncio.Task | None = None

    async def start(self, *, browser_ws_url: str, profile_id: str = "p1") -> None:
        root = self.root
        data_root = root / "data"
        runtime_dir = data_root / "runtime" / profile_id
        events_dir = data_root / "runtime-events" / profile_id
        runtime_dir.mkdir(parents=True)
        events_dir.mkdir(parents=True)
        cdp_port = urlparse(browser_ws_url).port
        runner_info = {
            "profile_id": profile_id,
            "runtime_instance_id": "i1",
            "config_version": 1,
            "cdp_port": cdp_port,
            "browser_ws_url": browser_ws_url,
            "browser_pid": 1,
            "runner_pid": 1,
        }
        (runtime_dir / "runner_info.json").write_text(
            json.dumps(runner_info), encoding="utf-8"
        )
        self._agent_task = asyncio.create_task(
            run_uds_agent(
                run_dir=runtime_dir,
                default_download_dir=self.downloads,
                events_dir=events_dir,
            )
        )
        sock = runtime_dir / "agent.sock"
        for _ in range(100):
            if sock.is_socket():
                break
            if self._agent_task.done():
                await self._agent_task  # raise the startup failure
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Agent UDS did not start")

        supervisor_token = secrets.token_urlsafe(32)
        token_file = root / "supervisor_token"
        token_file.write_text(supervisor_token, encoding="utf-8")
        token_file.chmod(0o600)
        core = SimpleNamespace(
            _token_file=token_file,
            _sessions={
                profile_id: SimpleNamespace(
                    runtime_instance_id="i1", observed_state="running"
                )
            },
            docker=SimpleNamespace(validator=PathValidator(data_root)),
        )
        supervisor_port = free_port()
        self._supervisor = _UvicornThread(
            create_control_app(core, token_file), supervisor_port
        )
        self._supervisor.start()

        db_file = root / "api.db"
        run_database_migrations(db_file)
        engine, session_maker = create_engine_and_maker(db_file)
        repository = ProfileRepository(session_maker)
        await repository.create_profile(
            ProfileConfig(name="p1", fingerprint_seed=SEED), profile_id="p1"
        )
        await repository.create_profile(
            ProfileConfig(name="p2", fingerprint_seed=SEED), profile_id="p2"
        )
        await engine.dispose()

        admin_password = secrets.token_urlsafe(32)
        admin_file = root / "admin"
        admin_file.write_text(admin_password, encoding="utf-8")
        admin_file.chmod(0o600)
        origin = "http://127.0.0.1"
        api = create_app(
            db_path=db_file,
            admin_password_file=admin_file,
            allowed_origins=[origin],
            artifacts_root=root / "artifacts",
            supervisor_url=f"http://127.0.0.1:{supervisor_port}",
            supervisor_token_file=token_file,
        )
        self._api = _UvicornThread(api, free_port())
        self.api_port = self._api.start()

        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{self.api_port}",
            timeout=10.0,
            trust_env=False,
        ) as client:
            login = await client.post(
                "/api/v1/auth/login", json={"password": admin_password}
            )
            login.raise_for_status()
            csrf = login.json()["csrf_token"]
            session = login.cookies.get("cbrowser_session")
            headers = {
                "X-CSRF-Token": csrf,
                "Origin": origin,
                "Cookie": f"cbrowser_session={session}",
            }
            created = await client.post(
                "/api/v1/automation/tokens",
                json={"name": "probe", "profile_ids": ["p1"]},
                headers=headers,
            )
            created.raise_for_status()
            self.token = created.json()["token"]

    def downloads_snapshot(self) -> set[str]:
        if not self.downloads.exists():
            return set()
        return {p.name for p in self.downloads.iterdir() if p.is_file()}

    async def wait_new_downloads(
        self, before: set[str], timeout: float = 15
    ) -> list[str]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            new = sorted(self.downloads_snapshot() - before)
            if new:
                return new
            await asyncio.sleep(0.2)
        return sorted(self.downloads_snapshot() - before)

    async def stop(self) -> None:
        if self._api is not None:
            self._api.stop()
        if self._supervisor is not None:
            self._supervisor.stop()
        if self._agent_task is not None:
            self._agent_task.cancel()
            try:
                await self._agent_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        shutil.rmtree(self.root, ignore_errors=True)


async def _ws_rejection(port: int, profile_id: str, token: str | None) -> str:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    url = f"ws://127.0.0.1:{port}/api/v1/automation/profiles/{profile_id}/cdp"
    try:
        ws = await websockets.connect(
            url, additional_headers=headers, proxy=None, open_timeout=5
        )
    except Exception as exc:  # noqa: BLE001 - rejection shape is the evidence
        return f"handshake:{type(exc).__name__}"
    try:
        await ws.send('{"id":1,"method":"Browser.getVersion"}')
        await asyncio.wait_for(ws.recv(), timeout=5)
        return "accepted"
    except websockets.ConnectionClosed as closed:
        return f"close:{closed.code}"
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}"
    finally:
        await ws.close()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _assert_matrix_output(payload: dict) -> None:
    assert payload["contexts"] == 1
    assert payload["popup"]["title"] == "CBrowser Probe Popup"
    assert payload["pages_after_popup_close"] >= 1
    assert payload["frame_found"] is True
    assert "pointerdown" in payload["frame_click_events"]
    assert payload["snapshot_ref_found"] is True
    download = payload["download"]
    assert download["event"] in {"download", "timeout"}
    if download["event"] == "download":
        assert download["suggested_filename"] == "probe-download.txt"
    assert payload["text_value"] == "probe"
    assert any(event["isTrusted"] for event in payload["input_events"])


@pytest.mark.asyncio
async def test_probe_chain_target_engine_matrix_and_disconnect() -> None:
    cache = engine_cache_dir()
    if cache is None:
        pytest.skip(
            "CloakBrowser target engine cache not installed; set "
            "CBROWSER_T029_ENGINE_CACHE to the cache dir to run this test"
        )
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t029-target-", dir="/tmp"))
    runner_cls = host_runner_class()
    runner = runner_cls(
        profile_id="p1",
        runtime_instance_id="i1",
        config_snapshot_path=write_profile_snapshot(root, profile_id="p1", seed=SEED),
        run_dir=root / "run",
        user_data_dir=root / "profile",
        events_dir=root / "events",
        engine_cache_dir=cache,
        display=":126",
    )
    chain = _Chain()
    bridge: CdpBridge | None = None
    with ObservationServer() as observation:
        try:
            await runner.start()
            page = runner.browser_context.pages[0]
            await page.goto(observation.url + "/")
            await chain.start(browser_ws_url=str(runner.browser_ws_url))
            bridge = CdpBridge(
                f"ws://127.0.0.1:{chain.api_port}/api/v1/automation/profiles/p1/cdp",
                headers={"Authorization": f"Bearer {chain.token}"},
            ).start()

            # POLICY CHANGE (t030, replaces the t029 no_defaults=False
            # expectation): the mediated tunnel rejects
            # Browser.setDownloadBehavior, so Playwright's
            # connect_over_cdp with no_defaults=False now fails fast at
            # connect time with the stable tunnel error instead of
            # taking over download capture.  External clients must use
            # no_defaults=True (or raw CDP without download overrides).
            # The browser and the user page must survive the refusal.
            outcomes: dict[str, dict] = {}
            for no_defaults in (True, False):
                out_path = root / f"matrix-{no_defaults}.json"
                downloads_before = chain.downloads_snapshot()
                rc, payload, stderr = await _run_client(
                    "matrix",
                    "--endpoint",
                    bridge.endpoint_url,
                    "--url",
                    observation.url + "/",
                    "--out",
                    str(out_path),
                    "--disconnect",
                    "exit",
                    *(["--no-defaults"] if no_defaults else []),
                )
                if not no_defaults:
                    assert rc != 0, "no_defaults=False connect must be refused"
                    assert "CBrowser tunnel" in stderr
                    assert "Browser.setDownloadBehavior" in stderr
                    # Nothing was clicked (connect failed first), so no
                    # download may have been captured.
                    assert chain.downloads_snapshot() == downloads_before
                    outcomes[str(no_defaults)] = {
                        "connect_rejected": True,
                        "reason": "tunnel rejects Browser.setDownloadBehavior",
                    }
                    assert _pid_alive(int(runner.chrome_pid))
                    assert await page.evaluate("() => document.title") == (
                        "CBrowser Probe Main"
                    )
                    continue
                assert rc == 0, stderr
                assert payload is not None
                _assert_matrix_output(payload)
                captured = await chain.wait_new_downloads(downloads_before)
                payload["agent_capture_during_connection"] = captured
                # Playwright applied no download behavior of its own,
                # so the Agent's browser-level capture must have taken
                # the file clicked during the connection (AC-002).
                assert captured, (
                    "Agent did not capture the download clicked during "
                    "a no-defaults external connection"
                )
                outcomes[str(no_defaults)] = payload
                assert _pid_alive(int(runner.chrome_pid))
                assert await page.evaluate("() => document.title") == (
                    "CBrowser Probe Main"
                )

            methods = bridge.client_methods()
            assert "Browser.close" not in methods
            report = build_report(
                chain={
                    "engine": f"cloakbrowser-linux-{platform.machine()}",
                    "matrix": outcomes,
                    "state_changing_methods": bridge.state_changing_methods(),
                    "browser_close_sent_by_safe_disconnect": "Browser.close"
                    in methods,
                }
            )
            (_report_dir(root) / "chain-target.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )

            no_token = await _ws_rejection(chain.api_port, "p1", None)
            wrong_token = await _ws_rejection(chain.api_port, "p1", "cbat_wrong")
            cross_profile = await _ws_rejection(chain.api_port, "p2", chain.token)
            # Rejection shapes are pinned to the measured contract (not
            # merely "not accepted", which unrelated failures would also
            # satisfy): each probe must end in exactly one of the two
            # legitimate refusal shapes — handshake refusal with
            # InvalidStatus (HTTP 403) or an accept followed by close
            # 4401 — never in acceptance, a timeout or a generic error.
            for outcome in (no_token, wrong_token, cross_profile):
                assert outcome in {"close:4401", "handshake:InvalidStatus"}, (
                    outcome
                )
            # No bare CDP exposure: every endpoint the probe used is
            # loopback-only (browser WS, bridge, API).
            for endpoint in (
                str(runner.browser_ws_url),
                bridge.endpoint_url,
                f"http://127.0.0.1:{chain.api_port}",
            ):
                assert urlparse(endpoint).hostname in {"127.0.0.1", "localhost"}

            # After every external client is gone, the Agent rearm must
            # restore browser-level download capture: a download started
            # from the surviving user page lands in the Agent directory.
            bridge.close()
            bridge = None
            await asyncio.sleep(2)
            await page.click("#download-link")
            captured = False
            for _ in range(100):
                if chain.downloads.exists() and any(chain.downloads.iterdir()):
                    captured = True
                    break
                await asyncio.sleep(0.1)
            assert captured, "download after disconnect not captured by Agent"
        finally:
            if bridge is not None:
                bridge.close()
            await chain.stop()
            await runner.stop()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_probe_chain_ordinary_chromium_matrix() -> None:
    executable = chromium_executable()
    if executable is None:
        pytest.skip("Playwright full Chromium not installed")
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    from playwright.async_api import async_playwright

    root = Path(tempfile.mkdtemp(prefix="cbrowser-t029-chromium-", dir="/tmp"))
    xvfb = start_xvfb(":127")
    chain = _Chain()
    bridge: CdpBridge | None = None
    pw = await async_playwright().start()
    context = None
    with ObservationServer() as observation:
        try:
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=root / "profile",
                executable_path=executable,
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--window-position=0,0",
                    "--window-size=1280,800",
                    "--force-device-scale-factor=1",
                    "--remote-debugging-port=0",
                    "--remote-debugging-address=127.0.0.1",
                ],
                no_viewport=True,
                env=dict(os.environ, DISPLAY=":127"),
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(observation.url + "/")
            ws_url = devtools_ws_url(root / "profile")
            pid = find_browser_pid(root / "profile")
            assert pid is not None
            await chain.start(browser_ws_url=ws_url)
            bridge = CdpBridge(
                f"ws://127.0.0.1:{chain.api_port}/api/v1/automation/profiles/p1/cdp",
                headers={"Authorization": f"Bearer {chain.token}"},
            ).start()
            out_path = root / "matrix-chromium.json"
            downloads_before = chain.downloads_snapshot()
            rc, payload, stderr = await _run_client(
                "matrix",
                "--endpoint",
                bridge.endpoint_url,
                "--url",
                observation.url + "/",
                "--out",
                str(out_path),
                "--disconnect",
                "exit",
                "--no-defaults",
            )
            assert rc == 0, stderr
            assert payload is not None
            _assert_matrix_output(payload)
            payload["agent_capture_during_connection"] = (
                await chain.wait_new_downloads(downloads_before)
            )
            assert _pid_alive(pid)
            report = build_report(
                chain={
                    "engine": "chromium-for-testing",
                    "matrix": payload,
                    "state_changing_methods": bridge.state_changing_methods(),
                }
            )
            (_report_dir(root) / "chain-chromium.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
        finally:
            if bridge is not None:
                bridge.close()
            await chain.stop()
            if context is not None:
                await context.close()
            await pw.stop()
            xvfb.terminate()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_probe_chain_dialog_contract() -> None:
    """AC-003 dialog baseline through the full tunnel (ordinary Chromium).

    The dialog semantics under test are chain properties, so one engine
    suffices here; the target engine runs the same scenarios in the
    t032 local entry.  Baseline questions (from the ego-lite native
    dialog requirement): opening events reach the external session,
    a dialog can be handled while another command is pending, and a
    dialog left open by a vanished session is observable/handled by a
    new session rather than wedging the Profile.
    """
    executable = chromium_executable()
    if executable is None:
        pytest.skip("Playwright full Chromium not installed")
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    from playwright.async_api import async_playwright

    root = Path(tempfile.mkdtemp(prefix="cbrowser-t029-dialog-", dir="/tmp"))
    xvfb = start_xvfb(":129")
    chain = _Chain()
    bridge: CdpBridge | None = None
    pw = await async_playwright().start()
    context = None
    with ObservationServer() as observation:
        try:
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=root / "profile",
                executable_path=executable,
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--window-size=1280,800",
                    "--remote-debugging-port=0",
                    "--remote-debugging-address=127.0.0.1",
                ],
                no_viewport=True,
                env=dict(os.environ, DISPLAY=":129"),
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(observation.url + "/")
            await chain.start(browser_ws_url=devtools_ws_url(root / "profile"))
            bridge = CdpBridge(
                f"ws://127.0.0.1:{chain.api_port}/api/v1/automation/profiles/p1/cdp",
                headers={"Authorization": f"Bearer {chain.token}"},
            ).start()

            async def dialog(scenario: str, out_name: str, *extra: str):
                argv = [
                    "dialog",
                    "--endpoint",
                    bridge.ws_url,
                    "--url",
                    observation.url + "/other",
                    "--url-marker",
                    urlparse(observation.url).netloc,
                    "--scenario",
                    scenario,
                    "--out",
                    str(root / out_name),
                    *extra,
                ]
                return await _run_client(*argv)

            evidence: dict[str, dict] = {}

            rc, pending, stderr = await dialog(
                "pending", "dialog-pending.json", "--dialog-type", "prompt"
            )
            assert rc == 0, stderr
            assert pending is not None
            assert pending["opening"] is not None
            assert pending["opening"]["type"] == "prompt"
            assert pending["handled_while_pending"] is True
            assert pending["evaluate_completed"] is True
            # Measured engine behavior: promptText is not delivered
            # back to the page (accept answers the dialog, prompt()
            # returns null) — pinned so a change is noticed.
            assert pending["last_dialog"] == {"type": "prompt", "result": None}
            evidence["pending"] = pending

            rc, alert, stderr = await dialog(
                "pending", "dialog-alert.json", "--dialog-type", "alert"
            )
            assert rc == 0, stderr
            assert alert is not None
            assert alert["opening"] is not None
            assert alert["opening"]["type"] == "alert"
            assert alert["handled_while_pending"] is True
            assert alert["evaluate_completed"] is True
            evidence["pending_alert"] = alert

            rc, left, stderr = await dialog(
                "leave", "dialog-leave.json", "--dialog-type", "confirm"
            )
            assert rc == 3, stderr  # leave exits abruptly by design
            assert left is not None and left["left_open"] is True
            evidence["leave"] = left

            rc, new_session, stderr = await dialog(
                "handle_new", "dialog-new.json", "--dialog-type", "confirm"
            )
            assert rc == 0, stderr
            assert new_session is not None
            # Measured contract: the leftover dialog is NOT replayed to
            # the new session, does not block its commands, and has
            # already been dismissed (confirm resolves false).
            assert new_session["opening_replayed"] is False
            assert new_session["commands_blocked"] is False
            assert new_session["page_enable_error"] is None
            assert new_session["last_dialog"] == {
                "type": "confirm",
                "result": False,
            }
            evidence["after_vanished_session"] = new_session
            # The Profile must not be wedged for the user either way.
            assert await page.evaluate("() => document.title") == (
                "CBrowser Probe Main"
            )

            rc, beforeunload, stderr = await dialog(
                "beforeunload",
                "dialog-beforeunload.json",
                "--activation",
                "input",
            )
            assert rc == 0, stderr
            assert beforeunload is not None
            assert beforeunload["opening"] is not None
            assert beforeunload["opening"]["type"] == "beforeunload"
            assert beforeunload["handled"] is True
            assert beforeunload["navigate_completed"] is True
            assert beforeunload["final_url"].endswith("/other")
            evidence["beforeunload_input_activation"] = beforeunload

            rc, beforeunload_script, stderr = await dialog(
                "beforeunload",
                "dialog-beforeunload-script.json",
                "--activation",
                "none",
            )
            assert rc == 0, stderr
            assert beforeunload_script is not None
            # Without a real user activation the armed beforeunload is
            # ignored entirely: no opening event, navigation completes.
            assert beforeunload_script["opening"] is None
            assert beforeunload_script["navigate_completed"] is True
            assert beforeunload_script["final_url"].endswith("/other")
            evidence["beforeunload_script_activation"] = beforeunload_script

            report = build_report(chain={"dialog": evidence})
            (_report_dir(root) / "chain-dialog.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
        finally:
            if bridge is not None:
                bridge.close()
            await chain.stop()
            if context is not None:
                await context.close()
            await pw.stop()
            xvfb.terminate()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_probe_target_engine_dialog_contract() -> None:
    """AC-006 dialog baseline on the target engine (bridge-direct).

    The full cbat_ chain dialog semantics are covered by
    test_probe_chain_dialog_contract on ordinary Chromium; this run
    repeats the same four scenarios against the CloakBrowser binary so
    engine-level dialog differences are measured, not assumed.
    """
    cache = engine_cache_dir()
    if cache is None:
        pytest.skip(
            "CloakBrowser target engine cache not installed; set "
            "CBROWSER_T029_ENGINE_CACHE to the cache dir to run this test"
        )
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t029-dlg-target-", dir="/tmp"))
    runner_cls = host_runner_class()
    runner = runner_cls(
        profile_id="p1",
        runtime_instance_id="i1",
        config_snapshot_path=write_profile_snapshot(root, profile_id="p1", seed=SEED),
        run_dir=root / "run",
        user_data_dir=root / "profile",
        events_dir=root / "events",
        engine_cache_dir=cache,
        display=":130",
    )
    bridge: CdpBridge | None = None
    with ObservationServer() as observation:
        try:
            await runner.start()
            page = runner.browser_context.pages[0]
            await page.goto(observation.url + "/")
            bridge = CdpBridge(str(runner.browser_ws_url)).start()

            async def dialog(scenario: str, out_name: str, *extra: str):
                return await _run_client(
                    "dialog",
                    "--endpoint",
                    bridge.ws_url,
                    "--url",
                    observation.url + "/other",
                    "--url-marker",
                    urlparse(observation.url).netloc,
                    "--scenario",
                    scenario,
                    "--out",
                    str(root / out_name),
                    *extra,
                )

            evidence: dict[str, dict] = {}
            rc, pending, stderr = await dialog(
                "pending", "t-pending.json", "--dialog-type", "prompt"
            )
            assert rc == 0, stderr
            assert pending is not None
            assert pending["opening"] is not None
            assert pending["opening"]["type"] == "prompt"
            assert pending["handled_while_pending"] is True
            assert pending["evaluate_completed"] is True
            assert pending["last_dialog"] == {"type": "prompt", "result": None}
            evidence["pending"] = pending

            rc, alert, stderr = await dialog(
                "pending", "t-alert.json", "--dialog-type", "alert"
            )
            assert rc == 0, stderr
            assert alert is not None
            assert alert["opening"] is not None
            assert alert["opening"]["type"] == "alert"
            assert alert["handled_while_pending"] is True
            assert alert["evaluate_completed"] is True
            evidence["pending_alert"] = alert

            rc, left, stderr = await dialog(
                "leave", "t-leave.json", "--dialog-type", "confirm"
            )
            assert rc == 3, stderr
            assert left is not None and left["left_open"] is True
            evidence["leave"] = left

            rc, new_session, stderr = await dialog(
                "handle_new", "t-new.json", "--dialog-type", "confirm"
            )
            assert rc == 0, stderr
            assert new_session is not None
            assert new_session["opening_replayed"] is False
            assert new_session["commands_blocked"] is False
            assert new_session["page_enable_error"] is None
            assert new_session["last_dialog"] == {
                "type": "confirm",
                "result": False,
            }
            evidence["after_vanished_session"] = new_session
            assert await page.evaluate("() => document.title") == (
                "CBrowser Probe Main"
            )

            rc, beforeunload, stderr = await dialog(
                "beforeunload", "t-bu.json", "--activation", "input"
            )
            assert rc == 0, stderr
            assert beforeunload is not None
            assert beforeunload["opening"] is not None
            assert beforeunload["opening"]["type"] == "beforeunload"
            assert beforeunload["handled"] is True
            assert beforeunload["navigate_completed"] is True
            assert beforeunload["final_url"].endswith("/other")
            evidence["beforeunload_input_activation"] = beforeunload

            rc, beforeunload_script, stderr = await dialog(
                "beforeunload", "t-bu-script.json", "--activation", "none"
            )
            assert rc == 0, stderr
            assert beforeunload_script is not None
            assert beforeunload_script["opening"] is None
            assert beforeunload_script["navigate_completed"] is True
            assert beforeunload_script["final_url"].endswith("/other")
            evidence["beforeunload_script_activation"] = beforeunload_script

            report = build_report(
                chain={"engine": f"cloakbrowser-linux-{platform.machine()}", "dialog": evidence}
            )
            (_report_dir(root) / "dialog-target.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
        finally:
            if bridge is not None:
                bridge.close()
            await runner.stop()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_probe_chain_client_killed_mid_connection_survival() -> None:
    """AC-002: an attached client that is killed (timeout/abort path)
    leaves the browser and the user's pages alive and usable."""
    executable = chromium_executable()
    if executable is None:
        pytest.skip("Playwright full Chromium not installed")
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    from playwright.async_api import async_playwright

    root = Path(tempfile.mkdtemp(prefix="cbrowser-t029-kill-", dir="/tmp"))
    xvfb = start_xvfb(":131")
    chain = _Chain()
    bridge: CdpBridge | None = None
    pw = await async_playwright().start()
    context = None
    proc: subprocess.Popen | None = None
    with ObservationServer() as observation:
        try:
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=root / "profile",
                executable_path=executable,
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--window-size=1280,800",
                    "--remote-debugging-port=0",
                    "--remote-debugging-address=127.0.0.1",
                ],
                no_viewport=True,
                env=dict(os.environ, DISPLAY=":131"),
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(observation.url + "/")
            pid = find_browser_pid(root / "profile")
            assert pid is not None
            await chain.start(browser_ws_url=devtools_ws_url(root / "profile"))
            bridge = CdpBridge(
                f"ws://127.0.0.1:{chain.api_port}/api/v1/automation/profiles/p1/cdp",
                headers={"Authorization": f"Bearer {chain.token}"},
            ).start()
            ready = root / "ready.json"
            env = dict(os.environ)
            env["NO_PROXY"] = "127.0.0.1,localhost"
            env["no_proxy"] = "127.0.0.1,localhost"
            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(CLIENT),
                    "hold",
                    "--endpoint",
                    bridge.endpoint_url,
                    "--level",
                    "L4",
                    "--ready-file",
                    str(ready),
                    "--release-file",
                    str(root / "release"),
                    "--out",
                    str(root / "hold.json"),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            for _ in range(200):
                if ready.exists():
                    break
                await asyncio.sleep(0.1)
            assert ready.exists(), "hold client never became ready"
            proc.kill()
            proc.wait(timeout=10)
            await asyncio.sleep(1)
            assert _pid_alive(pid), "browser died with the killed client"
            assert await page.evaluate("() => document.title") == (
                "CBrowser Probe Main"
            )
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
            if bridge is not None:
                bridge.close()
            await chain.stop()
            if context is not None:
                await context.close()
            await pw.stop()
            xvfb.terminate()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_probe_chain_external_browser_close_rejected() -> None:
    """POLICY CHANGE (t030, replaces the t029 close-stops-profile test).

    The mediated tunnel rejects external Browser.close with a stable
    error: no external client may stop the Profile through the tunnel.
    The browser, the user page and the runner state must all survive the
    refusal; lifecycle close stays on the Agent's own /control path.
    """
    cache = engine_cache_dir()
    if cache is None:
        pytest.skip(
            "CloakBrowser target engine cache not installed; set "
            "CBROWSER_T029_ENGINE_CACHE to the cache dir to run this test"
        )
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t030-close-", dir="/tmp"))
    runner_cls = host_runner_class()
    runner = runner_cls(
        profile_id="p1",
        runtime_instance_id="i1",
        config_snapshot_path=write_profile_snapshot(root, profile_id="p1", seed=SEED),
        run_dir=root / "run",
        user_data_dir=root / "profile",
        events_dir=root / "events",
        engine_cache_dir=cache,
        display=":128",
    )
    chain = _Chain()
    with ObservationServer() as observation:
        try:
            await runner.start()
            page = runner.browser_context.pages[0]
            await page.goto(observation.url + "/")
            await chain.start(browser_ws_url=str(runner.browser_ws_url))
            async with websockets.connect(
                f"ws://127.0.0.1:{chain.api_port}"
                "/api/v1/automation/profiles/p1/cdp",
                additional_headers={"Authorization": f"Bearer {chain.token}"},
                proxy=None,
            ) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Browser.getVersion"}))
                version = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                assert "result" in version
                await ws.send(json.dumps({"id": 2, "method": "Browser.close"}))
                rejected = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                assert rejected["id"] == 2
                assert rejected["error"]["code"] == -32000
                assert "CBrowser tunnel" in rejected["error"]["message"]
            pid = int(runner.chrome_pid)
            # Poll liveness instead of a fixed sleep: a rejected close
            # either takes effect immediately or not at all, so repeated
            # alive checks over a second are the stronger assertion (and
            # cannot flake on a slow machine).  Long-term survival is
            # covered by the title assertion and the chain tests below.
            for _ in range(10):
                assert _pid_alive(pid), (
                    "rejected Browser.close must not stop the browser"
                )
                await asyncio.sleep(0.1)
            assert await page.evaluate("() => document.title") == (
                "CBrowser Probe Main"
            )
            stopped = [
                candidate
                for candidate in (root / "events").rglob("*.json")
                if '"stopped"' in candidate.read_text(encoding="utf-8", errors="ignore")
            ]
            assert not stopped, "runner must not persist a stopped state"
        finally:
            await chain.stop()
            await runner.stop()
            shutil.rmtree(root, ignore_errors=True)
