"""t031 attendant chain: real browser + API + Supervisor + Agent UDS.

Proves, against a live Chromium, the two behaviors the ADR leaves to
the chain test (never presumed):

1. A dialog opened while the resident attendant is armed stays held
   across CLI sessions: a new session observes it through the
   attendant peek and answers it on the attendant's pre-existing
   session (chain evidence: a later session's own CDP session can
   neither observe nor answer it -- Page.enable hangs behind the
   modal dialog and Chrome reports "No dialog is showing").
2. After the takeover release (Supervisor close-tunnels), a dialog
   that opens with no agent session and no attendant follows Chrome's
   default handling (auto-dismiss, false) instead of staying held.

The ObservationServer page carries the Confirm button; the Playwright
no-op dialog listener only stops Playwright's own auto-dismiss on the
adopted page, it never answers a dialog.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))

from automation_probe.harness import (  # noqa: E402
    ObservationServer,
    chromium_executable,
    devtools_ws_url,
    free_port,
    start_xvfb,
)
from cbrowser.adapters.database.migrations import run_database_migrations  # noqa: E402
from cbrowser.adapters.database.repository import ProfileRepository  # noqa: E402
from cbrowser.adapters.database.session import create_engine_and_maker  # noqa: E402
from cbrowser.api.app import create_app  # noqa: E402
from cbrowser.domain.models import ProfileConfig  # noqa: E402
from cbrowser.runtime_agent.agent import run_uds_agent  # noqa: E402
from cbrowser.runtime_agent.socket_root import agent_socket_path, prepare_socket_dir  # noqa: E402
from cbrowser.supervisor.control_server import create_control_app  # noqa: E402
from cbrowser.supervisor.path_validator import PathValidator  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = 290031


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
        self.root = Path(tempfile.mkdtemp(prefix="cbrowser-t031-", dir="/tmp"))
        self.api_port = 0
        self.supervisor_port = 0
        self.supervisor_token = ""
        self.admin_password = ""
        self.token = ""
        self._api: _UvicornThread | None = None
        self._supervisor: _UvicornThread | None = None
        self._agent_task: asyncio.Task | None = None

    async def start(self, *, browser_ws_url: str, display: str, xauth_path: Path | None = None, profile_id: str = "p1") -> None:
        root = self.root
        data_root = root / "data"
        runtime_dir = data_root / "runtime" / profile_id
        events_dir = data_root / "runtime-events" / profile_id
        runtime_dir.mkdir(parents=True)
        events_dir.mkdir(parents=True)
        cdp_port = urlparse(browser_ws_url).port
        # Bare-Xvfb cases have no authentication; Runner cases pass its real
        # private cookie. Neither fixture enables preview collection.
        authority = xauth_path or runtime_dir / "Xauthority"
        if xauth_path is None:
            authority.touch(mode=0o600)
        runner_info = {
            "profile_id": profile_id,
            "runtime_instance_id": "i1",
            "config_version": 1,
            "cdp_port": cdp_port,
            "browser_ws_url": browser_ws_url,
            "display": display,
            "xauth_path": str(authority),
            "browser_pid": 1,
            "runner_pid": 1,
        }
        (runtime_dir / "runner_info.json").write_text(
            json.dumps(runner_info), encoding="utf-8"
        )
        socket_root = PathValidator(data_root).socket_root
        prepare_socket_dir(socket_root, profile_id, "i1")
        sock = agent_socket_path(socket_root, profile_id, "i1")
        self._agent_task = asyncio.create_task(
            run_uds_agent(
                run_dir=runtime_dir,
                default_download_dir=root / "data" / "downloads",
                events_dir=events_dir,
                uds_path=sock,
            )
        )
        for _ in range(100):
            if sock.is_socket():
                break
            if self._agent_task.done():
                await self._agent_task
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Agent UDS did not start")

        async def release_attendant(pid: str) -> bool:
            resp = await _uds_control(
                "release_attendant", {"profile_id": pid}
            )
            return resp is not None and resp.status_code == 200

        async def list_attendant_dialogs(pid: str) -> list[dict] | None:
            resp = await _uds_control(
                "list_attendant_dialogs", {"profile_id": pid}
            )
            if resp is None or resp.status_code != 200:
                return None
            try:
                data = resp.json().get("data") or {}
            except ValueError:
                return None
            dialogs = data.get("dialogs")
            return dialogs if isinstance(dialogs, list) else None

        async def answer_attendant_dialog(
            pid: str,
            target_id: str,
            accept: bool,
            prompt_text: str | None = None,
        ) -> dict | None:
            params: dict = {
                "profile_id": pid,
                "target_id": target_id,
                "accept": accept,
            }
            if prompt_text is not None:
                params["prompt_text"] = prompt_text
            resp = await _uds_control("answer_attendant_dialog", params)
            if resp is None or resp.status_code != 200:
                return None
            try:
                data = resp.json().get("data") or {}
            except ValueError:
                return None
            dialog = data.get("dialog")
            return dialog if isinstance(dialog, dict) else None

        async def _uds_control(action: str, params: dict):
            transport = httpx.AsyncHTTPTransport(uds=str(sock))
            try:
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://agent",
                    timeout=10.0,
                ) as client:
                    return await client.post(
                        "/control",
                        json={"action": action, "params": params},
                    )
            except Exception:  # noqa: BLE001 - best-effort control
                return None

        token = secrets.token_urlsafe(32)
        token_file = root / "supervisor_token"
        token_file.write_text(token, encoding="utf-8")
        token_file.chmod(0o600)
        self.supervisor_token = token
        core = SimpleNamespace(
            _token_file=token_file,
            _sessions={
                profile_id: SimpleNamespace(
                    runtime_instance_id="i1", observed_state="running"
                )
            },
            docker=SimpleNamespace(validator=PathValidator(data_root)),
            release_dialog_attendant=release_attendant,
            list_attendant_dialogs=list_attendant_dialogs,
            answer_attendant_dialog=answer_attendant_dialog,
        )
        self.supervisor_port = free_port()
        self._supervisor = _UvicornThread(
            create_control_app(core, token_file), self.supervisor_port
        )
        self._supervisor.start()

        db_file = root / "api.db"
        run_database_migrations(db_file)
        engine, session_maker = create_engine_and_maker(db_file)
        repository = ProfileRepository(session_maker)
        await repository.create_profile(
            ProfileConfig(name="p1", fingerprint_seed=SEED), profile_id="p1"
        )
        # The in-process Supervisor session wraps this live browser; seed
        # the API with the same authoritative instance before it starts.
        await repository.set_desired_state(profile_id, "running")
        await repository.bind_runtime_instance(profile_id, "i1", config_version=1)
        await repository.report_observed_state(profile_id, "i1", "running", config_version=1)
        await engine.dispose()

        admin_password = secrets.token_urlsafe(32)
        self.admin_password = admin_password
        admin_file = root / "admin"
        admin_file.write_text(admin_password, encoding="utf-8")
        admin_file.chmod(0o600)
        origin = "https://127.0.0.1:56661"
        api = create_app(
            db_path=db_file,
            admin_password_file=admin_file,
                        artifacts_root=root / "artifacts",
            supervisor_url=f"http://127.0.0.1:{self.supervisor_port}",
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


async def _chromium_context(root: Path, display: str):
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


async def _control_state(chain: _Chain) -> dict:
    """Read the profile control state as the admin session user."""
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{chain.api_port}",
        timeout=10.0,
        trust_env=False,
    ) as client:
        login = await client.post(
            "/api/v1/auth/login", json={"password": chain.admin_password}
        )
        login.raise_for_status()
        headers = {
            "X-CSRF-Token": login.json()["csrf_token"],
            "Origin": "https://127.0.0.1:56661",
            "Cookie": f"cbrowser_session={login.cookies.get('cbrowser_session')}",
        }
        state = await client.get(
            "/api/v1/profiles/p1/control", headers=headers
        )
        state.raise_for_status()
        return state.json()


@pytest.mark.asyncio
async def test_attendant_holds_dialog_and_release_restores_default() -> None:
    executable = chromium_executable()
    if executable is None:
        pytest.skip("Playwright full Chromium not installed")
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb not available")
    root = Path(tempfile.mkdtemp(prefix="cbrowser-t031-dialog-", dir="/tmp"))
    xvfb = start_xvfb(":142")
    chain = _Chain()
    pw = None
    context = None
    with ObservationServer() as observation:
        try:
            pw, context = await _chromium_context(root, ":142")
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(observation.url + "/")
            # No-op listener only stops Playwright's own auto-dismiss;
            # it never answers a dialog.
            page.on("dialog", lambda dialog: None)
            await chain.start(browser_ws_url=devtools_ws_url(root / "profile"), display=":142")
            rc, listed, stderr = await _run_cli(
                chain, root, {"version": 1, "steps": [{"action": "targets"}]}
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

            # CLI-1 opens the confirm and exits WITHOUT answering. The
            # resident attendant (armed on tunnel connect) holds it.
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
                    ],
                },
            )
            assert rc == 0, stderr

            # Review t031_test_f005: opening and holding a dialog must
            # not switch control on its own: the agent still owns it
            # and the generation is unchanged while the dialog is held.
            control_before = await _control_state(chain)
            assert control_before["owner"] == "agent"
            gen_before = control_before["generation"]

            # New session: dialog_wait observes the held dialog through
            # the attendant peek (a later session's own CDP session
            # cannot observe it: Page.enable hangs behind the modal
            # dialog and Chrome reports no dialog for the new session).
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
                        {
                            "action": "dialog_wait",
                            "targetId": user_id,
                            "timeoutMs": 3000,
                        },
                    ],
                },
            )
            assert rc == 0, stderr
            assert run["results"][1]["result"]["type"] == "confirm"
            assert run["results"][1]["result"]["message"] == "probe-confirm"

            # Still held, still agent-owned with the same generation.
            control_held = await _control_state(chain)
            assert control_held["owner"] == "agent"
            assert control_held["generation"] == gen_before

            # And the same new session answers the held dialog through
            # the attendant's pre-existing session.
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": user_id},
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
            assert run["results"][1]["result"] == {"action": "dismiss"}
            assert run["results"][2]["result"]["value"] == {
                "type": "confirm",
                "result": False,
            }

            # Release path, ordered so the timer unambiguously fires
            # after the attendant is released: schedule a delayed
            # confirm FIRST (15s gives the handoff ample time), then
            # drive the real API control path (handoff + explicit
            # restore) and poll until the Supervisor close is confirmed
            # well before the timer fires. No agent session connects
            # between release and firing, so the dialog opens with no
            # listener at all. A direct Supervisor close-tunnels POST
            # with an invented generation would fence later handshakes
            # as stale; the API path keeps generations consistent.
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [{"action": "new_page", "url": "about:blank"}],
                },
            )
            assert rc == 0, stderr
            agent_page = run["results"][0]["result"]["target_id"]
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_page},
                        {
                            "action": "extract",
                            "targetId": agent_page,
                            "expression": (
                                "setTimeout(() => {"
                                " window.__released = confirm('again?');"
                                " }, 15000); 'scheduled'"
                            ),
                        },
                    ],
                },
            )
            assert rc == 0, stderr
            assert run["results"][1]["result"]["value"] == "scheduled"
            scheduled_at = time.monotonic()
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{chain.api_port}",
                timeout=10.0,
                trust_env=False,
            ) as client:
                handoff = await client.post(
                    "/api/v1/profiles/p1/control/handoff",
                    json={"reason": "cli_handoff"},
                    headers={"Authorization": f"Bearer {chain.token}"},
                )
                assert handoff.status_code == 200
                assert handoff.json()["owner"] == "user"
                login = await client.post(
                    "/api/v1/auth/login",
                    json={"password": chain.admin_password},
                )
                assert login.status_code == 200
                csrf = login.json()["csrf_token"]
                session_cookie = login.cookies.get("cbrowser_session")
                session_headers = {
                    "X-CSRF-Token": csrf,
                    "Origin": "https://127.0.0.1:56661",
                    "Cookie": f"cbrowser_session={session_cookie}",
                }
                restore = await client.post(
                    "/api/v1/profiles/p1/control/restore",
                    headers=session_headers,
                )
                assert restore.status_code == 200
                assert restore.json()["owner"] == "agent"
                # Poll until the Supervisor close is confirmed, with
                # a deadline well before the timer fires; if it never
                # confirms, fail fast instead of letting the timer fire
                # while the attendant is still armed.
                deadline = scheduled_at + 10
                while True:
                    state = await client.get(
                        "/api/v1/profiles/p1/runtime",
                        headers=session_headers,
                    )
                    assert state.status_code == 200
                    control = state.json().get("control") or {}
                    if control.get("pending_supervisor_close") is False:
                        break
                    if time.monotonic() >= deadline:
                        raise AssertionError(
                            "Supervisor close never confirmed"
                        )
                    await asyncio.sleep(0.1)

            # Wait past the timer firing (15s after schedule) with
            # margin; the dialog opens with no listener and Chrome's
            # default handling auto-dismisses (false).
            remaining = scheduled_at + 20 - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(remaining)
            rc, run, stderr = await _run_cli(
                chain,
                root,
                {
                    "version": 1,
                    "steps": [
                        {"action": "adopt", "targetId": agent_page},
                        {
                            "action": "extract",
                            "targetId": agent_page,
                            "expression": "window.__released",
                        },
                    ],
                },
                timeout=30,
            )
            assert rc == 0, stderr
            assert run["results"][1]["result"]["value"] is False
        finally:
            if context is not None:
                await context.close()
            if pw is not None:
                await pw.stop()
            await chain.stop()
            xvfb.terminate()
            shutil.rmtree(root, ignore_errors=True)
