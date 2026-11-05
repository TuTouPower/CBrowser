"""t030 executor: real CLI subprocess through the production tunnel.

Chain under test, all real components in-process or subprocess:
cbrowser-agent (stdin JSON program) -> API automation WS (cbat_ token)
-> Supervisor control WS -> Agent UDS (run_uds_agent + mediated /cdp
tunnel) -> real browser loopback CDP.

Browsers: ordinary Chromium (Chrome for Testing) always; the CloakBrowser
target engine runs the same scenarios when its cache is installed (the
package default ~/.cloakbrowser is accepted as well as the t029 cache
override).  Tests skip when a prerequisite is not installed; they never
substitute one engine's result for the other's.
"""

from __future__ import annotations

import asyncio
import json
import os
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
    TARGET_ENGINE_VERSION,
    ObservationServer,
    chromium_executable,
    devtools_ws_url,
    engine_cache_dir,
    find_browser_pid,
    free_port,
    start_xvfb,
)
from cbrowser.adapters.database.migrations import run_database_migrations  # noqa: E402
from cbrowser.adapters.database.repository import ProfileRepository  # noqa: E402
from cbrowser.adapters.database.session import create_engine_and_maker  # noqa: E402
from cbrowser.api.app import create_app  # noqa: E402
from cbrowser.domain.models import ProfileConfig  # noqa: E402
from cbrowser.runtime_agent.agent import run_uds_agent  # noqa: E402
from cbrowser.supervisor.control_server import create_control_app  # noqa: E402
from cbrowser.supervisor.path_validator import PathValidator  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = 290029


class _UvicornThread:
    def __init__(self, app, port: int) -> None:
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


class _Chain:
    """Real API + Supervisor control + Agent UDS around a live browser."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="cbrowser-t030-", dir="/tmp"))
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
                await self._agent_task
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
                json={"name": "executor", "profile_ids": ["p1"]},
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


async def _run_cli(
    chain: _Chain, root: Path, program: dict, timeout: float = 120
) -> tuple[int, dict, str]:
    """Run cbrowser-agent as a subprocess (threaded: never block the loop)."""
    token_file = root / "cbat_token"
    token_file.write_text(chain.token, encoding="utf-8")
    token_file.chmod(0o600)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src" / "backend")
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    env.pop("CBROWSER_AGENT_TOKEN", None)
    proc = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-m",
            "cbrowser.agent_executor.cli",
            "--endpoint",
            f"ws://127.0.0.1:{chain.api_port}/api/v1/automation/profiles/p1/cdp",
            "--profile",
            "p1",
            "--runtime-instance",
            "i1",
            "--token-file",
            str(token_file),
            "--state-file",
            str(root / "agent-state.json"),
        ],
        input=json.dumps(program),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    output = json.loads(proc.stdout) if proc.stdout.strip() else {}
    assert chain.token not in proc.stdout, "token leaked to CLI stdout"
    assert chain.token not in proc.stderr, "token leaked to CLI stderr"
    return proc.returncode, output, proc.stderr


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _target_engine_cache() -> Path | None:
    cache = engine_cache_dir()
    if cache is not None:
        return cache
    default = Path.home() / ".cloakbrowser"
    binary = default / f"chromium-{TARGET_ENGINE_VERSION}" / "chrome"
    if binary.is_file() and os.access(binary, os.X_OK):
        return default
    return None


async def _chromium_context(root: Path, display: str):
    """Launch ordinary Chromium persistent context; returns (pw, context)."""
    from playwright.async_api import async_playwright

    executable = chromium_executable()
    assert executable is not None
    pw = await async_playwright().start()
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
        env=dict(os.environ, DISPLAY=display),
    )
    return pw, context


async def _target_engine_context(root: Path, display: str):
    """Launch the CloakBrowser target engine binary; returns (pw, context)."""
    from playwright.async_api import async_playwright

    cache = _target_engine_cache()
    if cache is None:
        return None, None
    binary = cache / f"chromium-{TARGET_ENGINE_VERSION}" / "chrome"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        return None, None
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=root / "profile",
        executable_path=str(binary),
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1280,800",
            "--remote-debugging-port=0",
            "--remote-debugging-address=127.0.0.1",
        ],
        no_viewport=True,
        env=dict(os.environ, DISPLAY=display),
    )
    return pw, context


@pytest.mark.asyncio
async def test_executor_cli_chromium_end_to_end() -> None:
    executable = chromium_executable()
    if executable is None:
        pytest.skip("Playwright full Chromium not installed")
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t030-e2e-", dir="/tmp"))
    xvfb = start_xvfb(":140")
    chain = _Chain()
    pw = None
    context = None
    with ObservationServer() as observation:
        try:
            pw, context = await _chromium_context(root, ":140")
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(observation.url + "/")
            pid = find_browser_pid(root / "profile")
            assert pid is not None
            await chain.start(browser_ws_url=devtools_ws_url(root / "profile"))
            base = observation.url + "/"

            rc, listed, stderr = await _run_cli(
                chain,
                root,
                {"version": 1, "steps": [{"action": "targets"}]},
            )
            assert rc == 0, stderr
            user_targets = [
                t for t in listed["results"][0]["result"]["targets"]
                if t["origin"] == "user"
            ]
            assert len(user_targets) == 1
            user_id = user_targets[0]["target_id"]

            rc, snap, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
                        {"action": "snapshot", "targetId": user_id},
                    ],
                },
            )
            assert rc == 0, stderr
            nodes = snap["results"][1]["result"]["nodes"]
            assert any(n["role"] == "button" for n in nodes)
            # The iframe subtree is snapshotted under its own frame refs.
            assert len({n["frame_id"] for n in nodes}) >= 2

            # Agent page: snapshot, then click the popup button and verify
            # attribution inside the same session that performed the click.
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "new_page", "url": base},
                        {"action": "wait_for_target_count", "count": 2},
                    ],
                },
            )
            assert rc == 0, stderr
            agent_id = run["results"][0]["result"]["target_id"]

            rc, snap2, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_id},
                        {"action": "snapshot", "targetId": agent_id},
                    ],
                },
            )
            assert rc == 0, stderr
            nodes = snap2["results"][1]["result"]["nodes"]
            popup_btn = next(n for n in nodes if n["name"] == "Open popup")
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_id},
                        {
                            "action": "click",
                            "targetId": agent_id,
                            "ref": popup_btn["ref"],
                        },
                        {"action": "wait_for_target_count", "count": 3},
                        {"action": "targets"},
                    ],
                },
            )
            assert rc == 0, stderr
            targets = run["results"][3]["result"]["targets"]
            popup = [
                t
                for t in targets
                if t["target_id"] not in (user_id, agent_id)
            ]
            assert len(popup) == 1
            assert popup[0]["origin"] == "agent"
            assert popup[0]["cleanable"] is True
            popup_id = popup[0]["target_id"]

            # Input + extract on the agent page, then cleanup.
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_id},
                        {"action": "snapshot", "targetId": agent_id},
                    ],
                },
            )
            assert rc == 0, stderr
            nodes = run["results"][1]["result"]["nodes"]
            textbox = next(
                n for n in nodes if n["role"] == "textbox" and n["frame_id"]
            )
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_id},
                        {
                            "action": "input",
                            "targetId": agent_id,
                            "ref": textbox["ref"],
                            "text": "probe",
                        },
                        {
                            "action": "extract",
                            "targetId": agent_id,
                            "expression": "document.getElementById('text-input').value",
                        },
                        {"action": "cleanup"},
                    ],
                },
            )
            assert rc == 0, stderr
            assert run["results"][2]["result"]["value"] == "probe"
            closed = run["results"][3]["result"]["closed"]
            assert agent_id in closed
            assert popup_id in closed
            assert user_id not in closed

            # The user page and browser survive the whole session.
            assert _pid_alive(pid)
            assert await page.evaluate("() => document.title") == (
                "CBrowser Probe Main"
            )
        finally:
            await chain.stop()
            if context is not None:
                await context.close()
            if pw is not None:
                await pw.stop()
            xvfb.terminate()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_executor_dialog_pending_and_legacy() -> None:
    executable = chromium_executable()
    if executable is None:
        pytest.skip("Playwright full Chromium not installed")
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t030-dialog-", dir="/tmp"))
    xvfb = start_xvfb(":141")
    chain = _Chain()
    pw = None
    context = None
    with ObservationServer() as observation:
        try:
            pw, context = await _chromium_context(root, ":141")
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(observation.url + "/")
            # Playwright auto-dismisses dialogs when no listener is
            # registered; that would close the confirm before the
            # executor's dialog_wait ever sees it.  A no-op listener
            # disables auto-dismiss and leaves the dialog open for the
            # executor to answer over CDP.
            page.on("dialog", lambda dialog: None)
            await chain.start(browser_ws_url=devtools_ws_url(root / "profile"))
            rc, listed, stderr = await _run_cli(
                chain,
                root,
                {"version": 1, "steps": [{"action": "targets"}]},
            )
            assert rc == 0, stderr
            user_id = listed["results"][0]["result"]["targets"][0]["target_id"]

            # Pending: click opens confirm, dialog_wait observes it, answer
            # dismiss, page records false.
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
                        {"action": "snapshot", "targetId": user_id},
                    ],
                },
            )
            assert rc == 0, stderr
            nodes = run["results"][1]["result"]["nodes"]
            confirm_btn = next(n for n in nodes if n["name"] == "Confirm")
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
                        {
                            "action": "click",
                            "targetId": user_id,
                            "ref": confirm_btn["ref"],
                        },
                        {"action": "dialog_wait", "targetId": user_id},
                        {
                            "action": "dialog_answer",
                            "targetId": user_id,
                            "answer": "dismiss",
                        },
                        {
                            "action": "extract",
                            "targetId": user_id,
                            "expression": "window.__lastDialog",
                        },
                    ],
                },
            )
            assert rc == 0, stderr
            assert run["results"][2]["result"]["type"] == "confirm"
            assert run["results"][3]["result"] == {"action": "dismiss"}
            assert run["results"][4]["result"]["value"] == {
                "type": "confirm",
                "result": False,
            }

            # Legacy: a session opens a confirm and exits without answering.
            # The next session finds it dissolved (false) and unblocked.
            # This must run on an executor-created page, and it must NOT
            # dialog_wait: when no session claims dialog handling, Chrome
            # auto-dismisses the dialog at open (verified live: Opening
            # immediately followed by Closed, result false), so there is
            # no dialog left to wait on.  The legacy property verified
            # here is the AC-006 outcome: the next call is unblocked and
            # sees the dissolved result.  (A dialog left open by a
            # lingering handler session, e.g. Playwright's listener, is
            # a Chrome-level limitation: new sessions cannot enable Page
            # while it is modal, nor answer it -- verified live -- so it
            # is documented, not tested.)
            base = observation.url + "/"
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "new_page", "url": base},
                        {"action": "wait_for_target_count", "count": 2},
                    ],
                },
            )
            assert rc == 0, stderr
            agent_id = run["results"][0]["result"]["target_id"]
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_id},
                        {
                            "action": "wait_for",
                            "targetId": agent_id,
                            "expression": "document.readyState === 'complete'",
                            "timeoutMs": 10000,
                        },
                        {"action": "snapshot", "targetId": agent_id},
                    ],
                },
            )
            assert rc == 0, stderr
            nodes = run["results"][2]["result"]["nodes"]
            confirm_btn = next(n for n in nodes if n["name"] == "Confirm")
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_id},
                        {
                            "action": "click",
                            "targetId": agent_id,
                            "ref": confirm_btn["ref"],
                        },
                    ],
                },
            )
            assert rc == 0, stderr  # exits without answering, deliberately
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_id},
                        {
                            "action": "extract",
                            "targetId": agent_id,
                            "expression": "window.__lastDialog",
                        },
                        {"action": "snapshot", "targetId": agent_id},
                    ],
                },
            )
            assert rc == 0, stderr
            assert run["results"][1]["result"]["value"] == {
                "type": "confirm",
                "result": False,
            }
            assert run["results"][2]["result"]["nodes"]
            assert await page.evaluate("() => document.title") == (
                "CBrowser Probe Main"
            )
        finally:
            await chain.stop()
            if context is not None:
                await context.close()
            if pw is not None:
                await pw.stop()
            xvfb.terminate()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_executor_ref_stale_after_navigation_and_replace() -> None:
    executable = chromium_executable()
    if executable is None:
        pytest.skip("Playwright full Chromium not installed")
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t030-refs-", dir="/tmp"))
    xvfb = start_xvfb(":142")
    chain = _Chain()
    pw = None
    context = None
    with ObservationServer() as observation:
        try:
            pw, context = await _chromium_context(root, ":142")
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(observation.url + "/")
            await chain.start(browser_ws_url=devtools_ws_url(root / "profile"))
            rc, listed, stderr = await _run_cli(
                chain,
                root,
                {"version": 1, "steps": [{"action": "targets"}]},
            )
            assert rc == 0, stderr
            user_id = listed["results"][0]["result"]["targets"][0]["target_id"]
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
                        {"action": "snapshot", "targetId": user_id},
                    ],
                },
            )
            assert rc == 0, stderr
            nodes = run["results"][1]["result"]["nodes"]
            confirm_btn = next(n for n in nodes if n["name"] == "Confirm")

            # Navigation changes loaderId: the old ref must go stale.
            # No re-snapshot in this call on purpose: the click validates
            # the persisted ref from the previous call, so the failure is
            # genuinely the loaderId change (a fresh snapshot would replace
            # the registry and fail for "not in snapshot" instead).
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
                        {
                            "action": "navigate",
                            "targetId": user_id,
                            "url": observation.url + "/other",
                        },
                        {
                            "action": "wait_for",
                            "targetId": user_id,
                            "expression": "window.location.pathname === '/other'",
                            "timeoutMs": 10000,
                        },
                        {
                            "action": "click",
                            "targetId": user_id,
                            "ref": confirm_btn["ref"],
                        },
                    ],
                },
            )
            assert rc == 1, stderr
            assert run["error"]["code"] == "ref_stale"
            assert run["error"]["step"] == 3

            # Back on main: replacing the node invalidates its ref.
            # Fresh snapshot first, then replace + click the fresh ref, so
            # the failure is genuinely the signature change.
            await page.goto(observation.url + "/")
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
                        {"action": "snapshot", "targetId": user_id},
                    ],
                },
            )
            assert rc == 0, stderr
            nodes = run["results"][1]["result"]["nodes"]
            confirm_btn = next(n for n in nodes if n["name"] == "Confirm")
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
                        {
                            "action": "extract",
                            "targetId": user_id,
                            "expression": (
                                "(() => { const b = document.getElementById"
                                "('confirm-btn'); const n = b.cloneNode(true);"
                                " b.replaceWith(n); return true; })()"
                            ),
                        },
                        {
                            "action": "click",
                            "targetId": user_id,
                            "ref": confirm_btn["ref"],
                        },
                    ],
                },
            )
            assert rc == 1, stderr
            assert run["error"]["code"] == "ref_stale"
        finally:
            await chain.stop()
            if context is not None:
                await context.close()
            if pw is not None:
                await pw.stop()
            xvfb.terminate()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_tunnel_rejections_and_session_download_capture() -> None:
    executable = chromium_executable()
    if executable is None:
        pytest.skip("Playwright full Chromium not installed")
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t030-tunnel-", dir="/tmp"))
    xvfb = start_xvfb(":143")
    chain = _Chain()
    pw = None
    context = None
    with ObservationServer() as observation:
        try:
            pw, context = await _chromium_context(root, ":143")
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(observation.url + "/")
            pid = find_browser_pid(root / "profile")
            assert pid is not None
            await chain.start(browser_ws_url=devtools_ws_url(root / "profile"))

            # Raw client: every destructive command class gets a stable
            # CBrowser error and the browser survives.
            async with websockets.connect(
                f"ws://127.0.0.1:{chain.api_port}"
                "/api/v1/automation/profiles/p1/cdp",
                additional_headers={"Authorization": f"Bearer {chain.token}"},
                proxy=None,
            ) as ws:
                for msg_id, method in (
                    (1, "Browser.close"),
                    (2, "Browser.setDownloadBehavior"),
                    (3, "Emulation.setDeviceMetricsOverride"),
                    (4, "Network.emulateNetworkConditions"),
                ):
                    await ws.send(
                        json.dumps({"id": msg_id, "method": method, "params": {}})
                    )
                    resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                    assert resp["id"] == msg_id
                    assert resp["error"]["code"] == -32000
                    assert "CBrowser tunnel" in resp["error"]["message"]
            assert _pid_alive(pid)
            assert await page.evaluate("() => document.title") == (
                "CBrowser Probe Main"
            )

            # Executor session download still lands in Agent capture.
            rc, listed, stderr = await _run_cli(
                chain,
                root,
                {"version": 1, "steps": [{"action": "targets"}]},
            )
            assert rc == 0, stderr
            user_id = listed["results"][0]["result"]["targets"][0]["target_id"]
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
                        {"action": "snapshot", "targetId": user_id},
                    ],
                },
            )
            assert rc == 0, stderr
            nodes = run["results"][1]["result"]["nodes"]
            download_link = next(n for n in nodes if n["name"] == "Download probe file")
            before = chain.downloads_snapshot()
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
                        {
                            "action": "click",
                            "targetId": user_id,
                            "ref": download_link["ref"],
                        },
                    ],
                },
            )
            assert rc == 0, stderr
            captured = await chain.wait_new_downloads(before)
            assert captured, "session download did not enter Agent capture"
        finally:
            await chain.stop()
            if context is not None:
                await context.close()
            if pw is not None:
                await pw.stop()
            xvfb.terminate()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_tunnel_script_registration_cleaned_on_disconnect() -> None:
    executable = chromium_executable()
    if executable is None:
        pytest.skip("Playwright full Chromium not installed")
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t030-script-", dir="/tmp"))
    xvfb = start_xvfb(":144")
    chain = _Chain()
    pw = None
    context = None
    with ObservationServer() as observation:
        try:
            pw, context = await _chromium_context(root, ":144")
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(observation.url + "/")
            await chain.start(browser_ws_url=devtools_ws_url(root / "profile"))
            ws_url = (
                f"ws://127.0.0.1:{chain.api_port}"
                "/api/v1/automation/profiles/p1/cdp"
            )
            headers = {"Authorization": f"Bearer {chain.token}"}

            async def recv_for(ws, msg_id: int) -> dict:
                """Read until the response with this id (events may interleave)."""
                while True:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                    if msg.get("id") == msg_id:
                        return msg

            async def raw_cdp(commands):
                """Run raw CDP commands over the tunnel; returns responses."""
                out = []
                async with websockets.connect(
                    ws_url, additional_headers=headers, proxy=None
                ) as ws:
                    await ws.send(
                        json.dumps({"id": 1, "method": "Target.getTargets"})
                    )
                    targets = await recv_for(ws, 1)
                    target_id = next(
                        t["targetId"]
                        for t in targets["result"]["targetInfos"]
                        if t["type"] == "page"
                    )
                    await ws.send(
                        json.dumps(
                            {
                                "id": 2,
                                "method": "Target.attachToTarget",
                                "params": {"targetId": target_id, "flatten": True},
                            }
                        )
                    )
                    attached = await recv_for(ws, 2)
                    session_id = attached["result"]["sessionId"]
                    for index, (method, params) in enumerate(commands, start=10):
                        await ws.send(
                            json.dumps(
                                {
                                    "id": index,
                                    "method": method,
                                    "params": params,
                                    "sessionId": session_id,
                                }
                            )
                        )
                        out.append(await recv_for(ws, index))
                return out

            # Register a marker script, navigate, confirm it ran.
            # Page.enable is required before addScriptToEvaluateOnNewDocument:
            # without it Chrome accepts the registration but never runs the
            # script on new documents (verified against live Chromium).
            resps = await raw_cdp(
                [
                    ("Page.enable", {}),
                    ("Runtime.enable", {}),
                    (
                        "Page.addScriptToEvaluateOnNewDocument",
                        {"source": "window.__t030marker = 1;"},
                    ),
                    ("Page.navigate", {"url": observation.url + "/other"}),
                ]
            )
            assert "result" in resps[2]
            # Poll, don't fixed-sleep: on a slow machine the script may
            # not have run yet when a 1s sleep expires, and a fixed sleep
            # can only flake in that direction.  Evaluating mid-navigation
            # raises "execution context destroyed": that is "not ready",
            # never a value -- the sentinel keeps the loop waiting
            # instead of being mistaken for the marker (or its absence).
            _navigating = object()

            async def _marker_value():
                try:
                    return await page.evaluate("() => window.__t030marker")
                except Exception:
                    return _navigating

            deadline = time.monotonic() + 10
            while await _marker_value() != 1:
                assert time.monotonic() < deadline, "marker script never ran"
                await asyncio.sleep(0.1)
            # After that client disconnected, a fresh navigation must not
            # see the marker: no script survives the session.
            resps = await raw_cdp(
                [("Page.navigate", {"url": observation.url + "/"})]
            )
            deadline = time.monotonic() + 10
            while await _marker_value() is not None:
                # A mid-navigation error is the sentinel, not None, so
                # the loop cannot exit early on a half-loaded page.
                assert time.monotonic() < deadline, "marker never cleared"
                await asyncio.sleep(0.1)
        finally:
            await chain.stop()
            if context is not None:
                await context.close()
            if pw is not None:
                await pw.stop()
            xvfb.terminate()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_executor_dialog_prompt_accepts_text() -> None:
    """Prompt dialogs accept promptText end to end (AC-005).

    The confirm-only coverage left promptText unproven on a real
    browser: click opens the prompt, dialog_answer accepts with text,
    and the page must record exactly the submitted text.
    """
    executable = chromium_executable()
    if executable is None:
        pytest.skip("Playwright full Chromium not installed")
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t030-prompt-", dir="/tmp"))
    xvfb = start_xvfb(":168")
    chain = _Chain()
    pw = None
    context = None
    with ObservationServer() as observation:
        try:
            pw, context = await _chromium_context(root, ":168")
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(observation.url + "/")
            # Same no-op listener rationale as the pending confirm case:
            # without it Playwright auto-dismisses the prompt before the
            # executor can answer it.
            page.on("dialog", lambda dialog: None)
            await chain.start(browser_ws_url=devtools_ws_url(root / "profile"))
            rc, listed, stderr = await _run_cli(
                chain,
                root,
                {"version": 1, "steps": [{"action": "targets"}]},
            )
            assert rc == 0, stderr
            user_id = listed["results"][0]["result"]["targets"][0]["target_id"]
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
                        {"action": "snapshot", "targetId": user_id},
                    ],
                },
            )
            assert rc == 0, stderr
            nodes = run["results"][1]["result"]["nodes"]
            prompt_btn = next(n for n in nodes if n["name"] == "Prompt")
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
                        {
                            "action": "click",
                            "targetId": user_id,
                            "ref": prompt_btn["ref"],
                        },
                        {
                            "action": "dialog_answer",
                            "targetId": user_id,
                            "answer": "accept",
                            "promptText": "hello-prompt",
                        },
                        {
                            "action": "extract",
                            "targetId": user_id,
                            "expression": "window.__lastDialog",
                        },
                    ],
                },
            )
            assert rc == 0, stderr
            assert run["results"][1]["result"]["dialog"]["type"] == "prompt"
            assert run["results"][2]["result"] == {"action": "accept"}
            assert run["results"][3]["result"]["value"] == {
                "type": "prompt",
                "result": "hello-prompt",
            }
        finally:
            await chain.stop()
            if context is not None:
                await context.close()
            if pw is not None:
                await pw.stop()
            xvfb.terminate()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_executor_set_input_files() -> None:
    """File selection is a separate step from permission prompts (AC-007).

    The agent page selects a file into the fixture's file input; the
    page must then report exactly one file with the uploaded name.
    """
    executable = chromium_executable()
    if executable is None:
        pytest.skip("Playwright full Chromium not installed")
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t030-files-", dir="/tmp"))
    upload = root / "upload.txt"
    upload.write_text("probe-upload", encoding="utf-8")
    xvfb = start_xvfb(":169")
    chain = _Chain()
    pw = None
    context = None
    with ObservationServer() as observation:
        try:
            pw, context = await _chromium_context(root, ":169")
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(observation.url + "/")
            await chain.start(browser_ws_url=devtools_ws_url(root / "profile"))
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "new_page", "url": observation.url + "/"},
                        {"action": "wait_for_target_count", "count": 2},
                    ],
                },
            )
            assert rc == 0, stderr
            agent_id = run["results"][0]["result"]["target_id"]
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_id},
                        {"action": "snapshot", "targetId": agent_id},
                    ],
                },
            )
            assert rc == 0, stderr
            nodes = run["results"][1]["result"]["nodes"]
            file_input = next(
                n
                for n in nodes
                if n["tag"] == "INPUT" and n["attrs"].get("id") == "file-input"
            )
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_id},
                        {
                            "action": "set_input_files",
                            "targetId": agent_id,
                            "ref": file_input["ref"],
                            "files": [str(upload)],
                        },
                        {
                            "action": "extract",
                            "targetId": agent_id,
                            "expression": "document.getElementById('file-input').files.length",
                        },
                        {
                            "action": "extract",
                            "targetId": agent_id,
                            "expression": "document.getElementById('file-input').files[0].name",
                        },
                        {"action": "cleanup"},
                    ],
                },
            )
            assert rc == 0, (stderr, run)
            assert run["results"][2]["result"]["value"] == 1
            assert run["results"][3]["result"]["value"] == "upload.txt"
            assert agent_id in run["results"][4]["result"]["closed"]
        finally:
            await chain.stop()
            if context is not None:
                await context.close()
            if pw is not None:
                await pw.stop()
            xvfb.terminate()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_executor_target_engine_core_flow() -> None:
    """Core executor flow against the CloakBrowser target engine (AC-011).

    Same production path as the Chromium e2e (targets, adopt, snapshot,
    popup click with attribution, input, extract, cleanup) but with the
    target engine binary as the browser.  Real-image behaviour is still
    t032's call; this proves the executor works on the engine binary.
    """
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t030-engine-", dir="/tmp"))
    xvfb = start_xvfb(":167")
    chain = _Chain()
    pw = None
    context = None
    with ObservationServer() as observation:
        try:
            pw, context = await _target_engine_context(root, ":167")
            if pw is None:
                pytest.skip("CloakBrowser target engine cache not installed")
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(observation.url + "/")
            pid = find_browser_pid(root / "profile")
            assert pid is not None
            await chain.start(browser_ws_url=devtools_ws_url(root / "profile"))
            base = observation.url + "/"
            rc, listed, stderr = await _run_cli(
                chain,
                root,
                {"version": 1, "steps": [{"action": "targets"}]},
            )
            assert rc == 0, stderr
            user_targets = [
                t for t in listed["results"][0]["result"]["targets"]
                if t["origin"] == "user"
            ]
            assert len(user_targets) == 1
            user_id = user_targets[0]["target_id"]
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "new_page", "url": base},
                        {"action": "wait_for_target_count", "count": 2},
                    ],
                },
            )
            assert rc == 0, stderr
            agent_id = run["results"][0]["result"]["target_id"]
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_id},
                        {"action": "snapshot", "targetId": agent_id},
                    ],
                },
            )
            assert rc == 0, stderr
            nodes = run["results"][1]["result"]["nodes"]
            popup_btn = next(n for n in nodes if n["name"] == "Open popup")
            textbox = next(n for n in nodes if n["role"] == "textbox")
            # The popup click must come from the agent page: attribution
            # requires the opener to be an agent page (a popup from the
            # user page is correctly unknown, not agent-owned).
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_id},
                        {
                            "action": "click",
                            "targetId": agent_id,
                            "ref": popup_btn["ref"],
                        },
                        {"action": "wait_for_target_count", "count": 3},
                        {"action": "targets"},
                    ],
                },
            )
            assert rc == 0, stderr
            targets = run["results"][3]["result"]["targets"]
            popup = [
                t
                for t in targets
                if t["target_id"] not in (user_id, agent_id)
            ]
            assert len(popup) == 1
            assert popup[0]["origin"] == "agent"
            assert popup[0]["cleanable"] is True
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_id},
                        {
                            "action": "input",
                            "targetId": agent_id,
                            "ref": textbox["ref"],
                            "text": "engine-probe",
                        },
                        {
                            "action": "extract",
                            "targetId": agent_id,
                            "expression": "document.getElementById('text-input').value",
                        },
                        {"action": "cleanup"},
                    ],
                },
            )
            assert rc == 0, stderr
            assert run["results"][2]["result"]["value"] == "engine-probe"
            closed = run["results"][3]["result"]["closed"]
            assert agent_id in closed
            assert popup[0]["target_id"] in closed
            assert user_id not in closed
            assert _pid_alive(pid)
        finally:
            await chain.stop()
            if context is not None:
                await context.close()
            if pw is not None:
                await pw.stop()
            xvfb.terminate()
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["timeout", "cancel"])
async def test_executor_target_timeout_cancel_preserves_user_page(mode: str) -> None:
    """Real target engine and tunnel: failed programs clean only agent pages."""
    from cbrowser.agent_executor.cli import run_program
    from cbrowser.agent_executor.session import ExecutorSession

    if shutil.which("Xvfb") is None or _target_engine_cache() is None:
        pytest.skip("Target engine and Xvfb required")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t032-cancel-", dir="/tmp"))
    display = ":170" if mode == "timeout" else ":171"
    xvfb = start_xvfb(display)
    chain = _Chain()
    pw = context = session = task = None
    try:
        pw, context = await _target_engine_context(root, display)
        assert context is not None
        user_page = context.pages[0]
        await user_page.goto("data:text/html,<title>User page</title>")
        await chain.start(browser_ws_url=devtools_ws_url(root / "profile"))
        session = ExecutorSession(
            endpoint=f"ws://127.0.0.1:{chain.api_port}/api/v1/automation/profiles/p1/cdp",
            token=chain.token, profile_id="p1", runtime_instance_id="i1",
        )
        await session.start()
        agent = await session.new_page("about:blank")
        program = {"version": 1, "steps": [{
            "action": "wait_for", "targetId": agent["target_id"],
            "expression": "(window.__t032_wait_started = true, false)",
            "timeoutMs": 30000,
        }]}
        task = asyncio.create_task(run_program(
            session, program, program_timeout=1 if mode == "timeout" else 30,
            token=chain.token,
        ))
        if mode == "cancel":
            async def wait_started():
                while True:
                    for candidate in context.pages:
                        if not candidate.is_closed() and await candidate.evaluate(
                            "() => window.__t032_wait_started === true"
                        ):
                            return
                    await asyncio.sleep(0.05)
            await asyncio.wait_for(wait_started(), 10)
            task.cancel()
        output, code = await asyncio.wait_for(task, 15)
        assert code != 0
        assert output["error"]["code"] == (
            "step_timeout" if mode == "timeout" else "cancelled"
        )
        assert agent["target_id"] in output["cleanup"]["closed"]
        assert not user_page.is_closed()
        assert await user_page.title() == "User page"
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if session is not None:
            await session.close()
        await chain.stop()
        if context is not None:
            await context.close()
        if pw is not None:
            await pw.stop()
        xvfb.terminate()
        xvfb.wait(timeout=5)
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_target_unknown_oopif_and_last_tab_protection() -> None:
    """Probe cross-site frame isolation and page ownership on the real engine."""
    from cbrowser.agent_executor.session import ExecutorSession

    if shutil.which("Xvfb") is None or _target_engine_cache() is None:
        pytest.skip("Target engine and Xvfb required")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t032-pages-", dir="/tmp"))
    xvfb = start_xvfb(":172")
    chain = _Chain()
    pw = context = session = None
    try:
        with ObservationServer() as observation:
            pw, context = await _target_engine_context(root, ":172")
            assert context is not None
            user_page = context.pages[0]
            await user_page.goto(observation.url)
            await chain.start(browser_ws_url=devtools_ws_url(root / "profile"))
            session = ExecutorSession(
                endpoint=f"ws://127.0.0.1:{chain.api_port}/api/v1/automation/profiles/p1/cdp",
                token=chain.token, profile_id="p1", runtime_instance_id="i1",
            )
            await session.start()
            # localhost and 127.0.0.1 are distinct sites, unlike two ports
            # on the same host. The iframe target proves OOPIF isolation.
            frame_url = observation.url.replace("127.0.0.1", "localhost") + "/frame"
            await user_page.locator("#frame").evaluate("(el, url) => el.src = url", frame_url)
            await user_page.frame_locator("#frame").locator("#frame-pad").wait_for()
            targets = await session._client.send("Target.getTargets")
            assert any(
                target.get("type") == "iframe" and target.get("url") == frame_url
                for target in targets["targetInfos"]
            ), "Cross-site frame did not become an OOPIF"
            baseline = await session.list_targets()
            user_id = next(t["target_id"] for t in baseline if t["origin"] == "user")
            await session.adopt(user_id)
            snapshot = await session.snapshot(user_id)
            assert snapshot["nodes"], "OOPIF must not break the page snapshot"
            box = await user_page.frame_locator("#frame").locator("#frame-pad").bounding_box()
            assert box is not None
            sid = await session.attach(user_id)
            for event in ("mousePressed", "mouseReleased"):
                await session._client.send(
                    "Input.dispatchMouseEvent",
                    {"type": event, "x": box["x"] + 20, "y": box["y"] + 20,
                     "button": "left", "clickCount": 1}, session_id=sid,
                )
            frame = user_page.frame(url=frame_url)
            assert frame is not None
            await frame.wait_for_function(
                "window.__events.some(e => e.type === 'click' && e.target === 'frame-pad')"
            )

            unknown_page = await context.new_page()
            await session.wait_for_target_count(2, 10000)
            unknown = next(t for t in await session.list_targets() if t["origin"] == "unknown")
            assert unknown["manageable"] is False and unknown["cleanable"] is False
            await session.adopt(unknown["target_id"])
            adopted = next(t for t in await session.list_targets() if t["target_id"] == unknown["target_id"])
            assert adopted["manageable"] is True and adopted["cleanable"] is False
            assert adopted["origin"] == "unknown"
            agent = await session.new_page("about:blank")
            await unknown_page.close()
            await user_page.close()
            await session.wait_for_target_count(1, 10000)
            result = await session.cleanup()
            assert result["closed"] == []
            assert result["refused"] == [{"target_id": agent["target_id"], "reason": "last_tab_protected"}]
            live = await session._client.send("Target.getTargets")
            assert any(t["targetId"] == agent["target_id"] for t in live["targetInfos"])
    finally:
        if session is not None:
            await session.close()
        await chain.stop()
        if context is not None:
            await context.close()
        if pw is not None:
            await pw.stop()
        xvfb.terminate()
        xvfb.wait(timeout=5)
        shutil.rmtree(root, ignore_errors=True)
