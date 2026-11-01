"""Integration tests for Runtime Coordinator (AC-009) and SSE (AC-006)
using real uvicorn, real SQLite, and real aiohttp Supervisor mock.
"""

from __future__ import annotations

import asyncio
import importlib.util
import secrets
import socket
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from aiohttp import web
from cbrowser.api.app import create_app

_auth_path = Path(__file__).resolve().parents[1] / "fixtures" / "api_auth.py"
_auth_spec = importlib.util.spec_from_file_location("api_auth", _auth_path)
_auth_mod = importlib.util.module_from_spec(_auth_spec)
sys.modules["api_auth"] = _auth_mod
_auth_spec.loader.exec_module(_auth_mod)
create_auth_context = _auth_mod.create_auth_context


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MockSupervisorServer:
    """Real HTTP aiohttp server implementing the Supervisor protocol."""

    def __init__(self, token: str, api_url_getter: Any):
        self.token = token
        self.api_url_getter = api_url_getter
        self.app = web.Application()
        self.app.router.add_get("/supervisor/v1/health", self.handle_health)
        self.app.router.add_post("/supervisor/v1/profiles/start", self.handle_start)
        self.app.router.add_post("/supervisor/v1/profiles/stop", self.handle_stop)
        self.app.router.add_get(
            "/supervisor/v1/profiles/{profile_id}/status", self.handle_status
        )

        self.start_calls: list[dict[str, Any]] = []
        self.stop_calls: list[dict[str, Any]] = []
        self.should_fail: bool = False
        self.fail_status: int = 503
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self.port: int = 0

    def _check_auth(self, request: web.Request) -> None:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {self.token}":
            raise web.HTTPUnauthorized()

    async def handle_health(self, request: web.Request) -> web.Response:
        self._check_auth(request)
        if self.should_fail:
            raise web.HTTPServiceUnavailable(text="Mock supervisor failure")
        return web.json_response({"status": "ok", "role": "supervisor"})

    async def handle_start(self, request: web.Request) -> web.Response:
        self._check_auth(request)
        if self.should_fail:
            raise web.HTTPServiceUnavailable(text="Mock supervisor failure")
        data = await request.json()
        self.start_calls.append(data)

        profile_id = data["profile_id"]
        config_version = data.get("config_version", 1)
        instance_id = f"inst_mock_{secrets.token_hex(4)}"

        # Simulate Supervisor workflow: bind runtime in API
        api_url = self.api_url_getter()
        auth_headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient(
            base_url=api_url, timeout=5.0, trust_env=False
        ) as client:
            bind_resp = await client.post(
                f"/api/v1/internal/supervisor/runtimes/bind?profile_id={profile_id}",
                json={
                    "runtime_instance_id": instance_id,
                    "config_version": config_version,
                },
                headers=auth_headers,
            )
            bind_resp.raise_for_status()

            obs_resp = await client.post(
                f"/api/v1/internal/supervisor/runtimes/observed?profile_id={profile_id}",
                json={
                    "runtime_instance_id": instance_id,
                    "observed_state": "running",
                    "config_version": config_version,
                },
                headers=auth_headers,
            )
            obs_resp.raise_for_status()

        return web.json_response(
            {
                "profile_id": profile_id,
                "status": "running",
                "runtime_instance_id": instance_id,
                "udp_mux_port": 30005,
                "browser_container": "browser_c",
                "stream_container": "stream_c",
            }
        )

    async def handle_stop(self, request: web.Request) -> web.Response:
        self._check_auth(request)
        if self.should_fail:
            raise web.HTTPServiceUnavailable(text="Mock supervisor failure")
        data = await request.json()
        self.stop_calls.append(data)

        profile_id = data["profile_id"]
        instance_id = data["runtime_instance_id"]

        api_url = self.api_url_getter()
        auth_headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient(
            base_url=api_url, timeout=5.0, trust_env=False
        ) as client:
            obs_resp = await client.post(
                f"/api/v1/internal/supervisor/runtimes/observed?profile_id={profile_id}",
                json={
                    "runtime_instance_id": instance_id,
                    "observed_state": "stopped",
                },
                headers=auth_headers,
            )
            obs_resp.raise_for_status()

        return web.json_response(
            {
                "profile_id": profile_id,
                "runtime_instance_id": instance_id,
                "status": "stopped",
            }
        )

    async def handle_status(self, request: web.Request) -> web.Response:
        self._check_auth(request)
        profile_id = request.match_info["profile_id"]
        return web.json_response(
            {
                "profile_id": profile_id,
                "runtime_instance_id": None,
                "observed_state": "stopped",
                "desired_state": "stopped",
                "udp_mux_port": None,
                "browser_container_id": None,
                "stream_container_id": None,
                "restart_blocked": False,
                "failure_count": 0,
            }
        )

    async def start(self) -> str:
        self.port = find_free_port()
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", self.port)
        await self.site.start()
        return f"http://127.0.0.1:{self.port}"

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None


async def start_api_server(
    *,
    db_path: Path,
    sup_token_file: Path,
    auth_dir: Path,
    sup_url: str,
    attempts: int = 5,
) -> dict[str, Any]:
    """Start a real uvicorn process on a free port, retrying transient bind races."""
    last_error: str = "unknown"
    for attempt in range(attempts):
        port = find_free_port()
        api_url = f"http://127.0.0.1:{port}"
        auth_ctx = create_auth_context(auth_dir / f"auth{attempt}", origin=api_url)
        app = create_app(
            db_path=db_path,
            supervisor_token_file=sup_token_file,
            admin_password_file=auth_ctx.admin_password_file,
            allowed_origins=auth_ctx.allowed_origin,
            supervisor_url=sup_url,
        )
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        task = asyncio.create_task(server.serve())
        for _ in range(100):
            if server.started:
                return {
                    "api_url": api_url,
                    "auth_ctx": auth_ctx,
                    "app": app,
                    "server": server,
                    "task": task,
                }
            if task.done():
                last_error = repr(task.exception())
                break
            await asyncio.sleep(0.05)
        server.should_exit = True
        await task
    raise RuntimeError(f"uvicorn failed to start on a free port: {last_error}")


async def stop_api_server(env: dict[str, Any]) -> None:
    env["server"].should_exit = True
    await env["task"]


@pytest.fixture
async def coord_test_env(tmp_path: Path):
    sup_token = secrets.token_urlsafe(32)
    sup_token_file = tmp_path / "supervisor_token.txt"
    sup_token_file.write_text(sup_token, encoding="utf-8")
    sup_token_file.chmod(0o600)
    sup_token_file.chmod(0o600)

    api_url_holder: dict[str, str] = {"url": ""}
    sup_mock = MockSupervisorServer(
        sup_token, api_url_getter=lambda: api_url_holder["url"]
    )
    sup_url = await sup_mock.start()

    db_path = tmp_path / "test_api_coord.db"
    env = await start_api_server(
        db_path=db_path,
        sup_token_file=sup_token_file,
        auth_dir=tmp_path / "auth",
        sup_url=sup_url,
    )
    api_url_holder["url"] = env["api_url"]

    try:
        yield {
            "api_url": env["api_url"],
            "sup_mock": sup_mock,
            "auth_ctx": env["auth_ctx"],
            "app": env["app"],
            "db_path": db_path,
            "sup_token_file": sup_token_file,
        }
    finally:
        await stop_api_server(env)
        await sup_mock.stop()


@pytest.mark.asyncio
async def test_ac009_api_supervisor_start_and_stop_coordination(coord_test_env):
    """AC-009: API desired-state change coordinates with Supervisor start/stop."""
    api_url = coord_test_env["api_url"]
    sup_mock = coord_test_env["sup_mock"]
    auth_ctx = coord_test_env["auth_ctx"]

    async with httpx.AsyncClient(
        base_url=api_url, timeout=10.0, trust_env=False
    ) as client:
        # 1. Login
        auth_headers = await auth_ctx.login_async(api_url, client=client)

        # 2. Create Profile
        create_resp = await client.post(
            "/api/v1/profiles",
            json={"name": "coord_profile_1"},
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        profile_id = create_resp.json()["id"]

        # 3. Patch desired-state to running
        patch_resp = await client.patch(
            f"/api/v1/profiles/{profile_id}/runtime/desired-state",
            json={"desired_state": "running"},
            headers=auth_headers,
        )
        assert patch_resp.status_code == 200
        # API returns immediately with desired_state=running
        rt_init = patch_resp.json()
        assert rt_init["desired_state"] == "running"

        # 4. Wait for Supervisor start RPC to be invoked and convergence to complete
        for _ in range(50):
            if len(sup_mock.start_calls) >= 1:
                break
            await asyncio.sleep(0.1)

        assert len(sup_mock.start_calls) == 1
        assert sup_mock.start_calls[0]["profile_id"] == profile_id
        assert sup_mock.start_calls[0]["config_version"] == 1

        # Check API runtime state has converged to running
        rt_resp = await client.get(
            f"/api/v1/profiles/{profile_id}/runtime", headers=auth_headers
        )
        assert rt_resp.status_code == 200
        rt_data = rt_resp.json()
        assert rt_data["desired_state"] == "running"
        assert rt_data["observed_state"] == "running"
        assert rt_data["runtime_instance_id"] is not None
        assert rt_data["last_coordinator_error"] is None

        # 5. Stop the profile via POST /profiles/{id}/stop
        stop_resp = await client.post(
            f"/api/v1/profiles/{profile_id}/stop",
            headers=auth_headers,
        )
        assert stop_resp.status_code == 200
        assert stop_resp.json()["desired_state"] == "stopped"

        for _ in range(50):
            if len(sup_mock.stop_calls) >= 1:
                break
            await asyncio.sleep(0.1)

        assert len(sup_mock.stop_calls) == 1
        assert sup_mock.stop_calls[0]["profile_id"] == profile_id

        # Verify converged to stopped
        rt_stopped = (
            await client.get(
                f"/api/v1/profiles/{profile_id}/runtime", headers=auth_headers
            )
        ).json()
        assert rt_stopped["desired_state"] == "stopped"
        assert rt_stopped["observed_state"] == "stopped"


@pytest.mark.asyncio
async def test_ac009_supervisor_unreachable_intent_preserved_and_recovers(
    coord_test_env,
):
    """AC-009: When Supervisor is unreachable, intent is preserved, error is reported,
    and coordinator recovers when Supervisor comes back.
    """
    api_url = coord_test_env["api_url"]
    sup_mock = coord_test_env["sup_mock"]
    auth_ctx = coord_test_env["auth_ctx"]

    async with httpx.AsyncClient(
        base_url=api_url, timeout=10.0, trust_env=False
    ) as client:
        auth_headers = await auth_ctx.login_async(api_url, client=client)

        create_resp = await client.post(
            "/api/v1/profiles",
            json={"name": "coord_err_profile"},
            headers=auth_headers,
        )
        profile_id = create_resp.json()["id"]

        # Make supervisor fail
        sup_mock.should_fail = True

        patch_resp = await client.patch(
            f"/api/v1/profiles/{profile_id}/runtime/desired-state",
            json={"desired_state": "running"},
            headers=auth_headers,
        )
        assert patch_resp.status_code == 200
        # Intent is running
        assert patch_resp.json()["desired_state"] == "running"

        # Wait for coordinator attempt to register failure
        found_err = False
        for _ in range(50):
            rt = (
                await client.get(
                    f"/api/v1/profiles/{profile_id}/runtime", headers=auth_headers
                )
            ).json()
            if rt["last_coordinator_error"]:
                found_err = True
                assert "Supervisor" in rt["last_coordinator_error"]
                break
            await asyncio.sleep(0.1)
        assert found_err, "Expected last_coordinator_error to be set"

        # Desired state is still running!
        assert rt["desired_state"] == "running"
        assert rt["observed_state"] == "stopped"

        # Restore Supervisor
        sup_mock.should_fail = False

        # Wait for backoff retry to converge
        converged = False
        for _ in range(80):
            rt = (
                await client.get(
                    f"/api/v1/profiles/{profile_id}/runtime", headers=auth_headers
                )
            ).json()
            if rt["observed_state"] == "running":
                converged = True
                assert rt["last_coordinator_error"] is None
                break
            await asyncio.sleep(0.2)
        assert converged, "Expected coordinator to converge after Supervisor recovery"


@pytest.mark.asyncio
async def test_ac006_sse_streaming_status_events(coord_test_env):
    """AC-006: SSE GET /api/v1/events delivers status updates in real-time."""
    api_url = coord_test_env["api_url"]
    auth_ctx = coord_test_env["auth_ctx"]

    async with httpx.AsyncClient(
        base_url=api_url, timeout=10.0, trust_env=False
    ) as client:
        auth_headers = await auth_ctx.login_async(api_url, client=client)

        create_resp = await client.post(
            "/api/v1/profiles",
            json={"name": "sse_profile_1"},
            headers=auth_headers,
        )
        profile_id = create_resp.json()["id"]

        # Connect to SSE
        async with client.stream(
            "GET",
            "/api/v1/events",
            headers={"Cookie": auth_headers["Cookie"]},
        ) as sse_stream:
            assert sse_stream.status_code == 200
            assert "text/event-stream" in sse_stream.headers["content-type"]

            # Trigger desired-state change in another client call
            patch_resp = await client.patch(
                f"/api/v1/profiles/{profile_id}/runtime/desired-state",
                json={"desired_state": "running"},
                headers=auth_headers,
            )
            assert patch_resp.status_code == 200

            # Read events from stream and verify status arrives
            received_running = False
            async for line in sse_stream.aiter_lines():
                if "running" in line and profile_id in line:
                    received_running = True
                    break
            assert received_running


@pytest.mark.asyncio
async def test_api_startup_fails_when_supervisor_required_but_unconfigured(tmp_path):
    """Explicit 'require supervisor' mode refuses to start without credentials."""
    admin_pwd_file = tmp_path / "admin_pwd_req.txt"
    admin_pwd_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")

    app = create_app(
        db_path=tmp_path / "require_sup.db",
        admin_password_file=admin_pwd_file,
        allowed_origins=["http://127.0.0.1:3000"],
        require_supervisor=True,
    )
    with pytest.raises(
        RuntimeError, match="Supervisor URL and token must be configured"
    ):
        async with app.router.lifespan_context(app):
            pass


@pytest.mark.asyncio
async def test_api_restart_converges_preserved_running_intent(tmp_path):
    """A preserved running intent is converged after an API restart."""
    sup_token = secrets.token_urlsafe(32)
    sup_token_file = tmp_path / "sup_restart_token.txt"
    sup_token_file.write_text(sup_token, encoding="utf-8")
    sup_token_file.chmod(0o600)

    api_url_holder: dict[str, str] = {"url": ""}
    sup_mock = MockSupervisorServer(
        sup_token, api_url_getter=lambda: api_url_holder["url"]
    )
    sup_url = await sup_mock.start()

    auth_dir = tmp_path / "auth_restart"
    db_path = tmp_path / "restart_coord.db"

    try:
        env_a = await start_api_server(
            db_path=db_path,
            sup_token_file=sup_token_file,
            auth_dir=auth_dir,
            sup_url=sup_url,
        )
        api_url_holder["url"] = env_a["api_url"]
        api_url = env_a["api_url"]
        auth_headers: dict[str, str] = {}
        try:
            async with httpx.AsyncClient(
                base_url=api_url, timeout=10.0, trust_env=False
            ) as client:
                auth_headers = await env_a["auth_ctx"].login_async(
                    api_url, client=client
                )
                create_resp = await client.post(
                    "/api/v1/profiles",
                    json={"name": "restart_profile"},
                    headers=auth_headers,
                )
                assert create_resp.status_code == 201
                profile_id = create_resp.json()["id"]

                # Supervisor down: intent persists without an instance.
                sup_mock.should_fail = True
                patch_resp = await client.patch(
                    f"/api/v1/profiles/{profile_id}/runtime/desired-state",
                    json={"desired_state": "running"},
                    headers=auth_headers,
                )
                assert patch_resp.status_code == 200
                error_seen = False
                for _ in range(100):
                    rt = (
                        await client.get(
                            f"/api/v1/profiles/{profile_id}/runtime",
                            headers=auth_headers,
                        )
                    ).json()
                    if rt["last_coordinator_error"]:
                        error_seen = True
                        break
                    await asyncio.sleep(0.05)
                assert error_seen
                assert rt["desired_state"] == "running"
                assert rt["runtime_instance_id"] is None
        finally:
            await stop_api_server(env_a)

        # Supervisor recovers, then the API restarts on the same database.
        sup_mock.should_fail = False
        env_b = await start_api_server(
            db_path=db_path,
            sup_token_file=sup_token_file,
            auth_dir=auth_dir,
            sup_url=sup_url,
        )
        api_url_holder["url"] = env_b["api_url"]
        api_url = env_b["api_url"]
        try:
            async with httpx.AsyncClient(
                base_url=api_url, timeout=10.0, trust_env=False
            ) as client:
                converged = False
                for _ in range(200):
                    rt = (
                        await client.get(
                            f"/api/v1/profiles/{profile_id}/runtime",
                            headers=auth_headers,
                        )
                    ).json()
                    if (
                        rt["observed_state"] == "running"
                        and rt["runtime_instance_id"] is not None
                        and rt["last_coordinator_error"] is None
                    ):
                        converged = True
                        break
                    await asyncio.sleep(0.05)
                assert converged, f"startup convergence failed: {rt}"
        finally:
            await stop_api_server(env_b)
    finally:
        await sup_mock.stop()
