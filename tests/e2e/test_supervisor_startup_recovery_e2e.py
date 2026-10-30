"""Real Process & Real Docker E2E Suite for Supervisor Startup Interruption Recovery.

Validates:
Case 1: Missing runtime recovery
  API is bound to an active runtime_instance_id (via supervisor bind RPC)
  with running intent, but Docker has no container for this profile (simulating
  Supervisor SIGKILL before Browser container creation).
  RecoveryCoordinator.tick() synthesizes a single stable abnormal exit
  missing_runtime:<instance>, converges with API runtime state, increments
  failure count to 1, and schedules backoff retry in 2 seconds. Repeating tick
  does not duplicate or double-count.
Case 2: Profile lock held
  While Core profile lock is held (active operation), tick() must skip scanning
  and exit synthesis for that profile to prevent false positives.
Case 3: Native exit priority with local HTTP proxy
  A native normal exit (code 0) is written to the disk journal. A local HTTP fault
  proxy causes the first POST /runtimes/events to return 503, queuing the event in
  spool while registering the native exit tuple in Core.has_native_exit.
  Subsequent tick() must NOT synthesize an abnormal Docker or missing exit ahead of it.
  Once the proxy allows normal forwarding, spool replay delivers the normal exit,
  converging the profile runtime to stopped with no restart.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import secrets
import shutil
import socket
import sys
import uuid
from pathlib import Path

import aiohttp
import docker
import httpx
import pytest
from aiohttp import web
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from cbrowser.supervisor.recovery_coordinator import RecoveryCoordinator

_core_e2e_path = Path(__file__).with_name("test_supervisor_core_e2e.py")
_core_spec = importlib.util.spec_from_file_location(
    "supervisor_core_e2e_module", _core_e2e_path
)
assert _core_spec is not None and _core_spec.loader is not None
_core_module = importlib.util.module_from_spec(_core_spec)
sys.modules["supervisor_core_e2e_module"] = _core_module
_core_spec.loader.exec_module(_core_module)
real_api_server = _core_module.real_api_server

logger = logging.getLogger(__name__)


def check_e2e_images():
    browser_image = os.environ.get("CBROWSER_RUNTIME_TEST_IMAGE")
    stream_image = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    engine_cache = os.environ.get("CBROWSER_RUNTIME_ENGINE_CACHE")

    missing = []
    if not browser_image:
        missing.append("CBROWSER_RUNTIME_TEST_IMAGE")
    if not stream_image:
        missing.append("CBROWSER_STREAM_TEST_IMAGE")
    if not engine_cache:
        missing.append("CBROWSER_RUNTIME_ENGINE_CACHE")

    if missing:
        pytest.skip(f"Missing required E2E environment variables: {', '.join(missing)}")

    assert browser_image.startswith("sha256:"), (
        f"CBROWSER_RUNTIME_TEST_IMAGE must be sha256 digest, got {browser_image}"
    )
    assert stream_image.startswith("sha256:"), (
        f"CBROWSER_STREAM_TEST_IMAGE must be sha256 digest, got {stream_image}"
    )
    assert Path(engine_cache).is_dir(), (
        f"Engine cache is not a directory: {engine_cache}"
    )
    return browser_image, stream_image, Path(engine_cache)


class HttpFaultProxy:
    """Inject one HTTP 503 before forwarding to the real API."""

    def __init__(self, target_base_url: str):
        self.target_base = target_base_url
        self.first_post_503_done = False
        self.runner: web.AppRunner | None = None
        self.port: int | None = None
        self.session: aiohttp.ClientSession | None = None

    async def start(self) -> str:
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self.session = aiohttp.ClientSession()
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        site = web.TCPSite(self.runner, "127.0.0.1", self.port)
        await site.start()
        return f"http://127.0.0.1:{self.port}"

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        path = request.path
        if request.method == "POST" and path.endswith("/runtimes/events"):
            if not self.first_post_503_done:
                self.first_post_503_done = True
                return web.Response(
                    status=503,
                    text=json.dumps({"detail": "Database busy (injected 503)"}),
                    content_type="application/json",
                )

        target_url = f"{self.target_base}{request.rel_url}"
        body = await request.read()
        headers = dict(request.headers)
        headers.pop("Host", None)
        headers.pop("Content-Length", None)

        async with self.session.request(
            request.method, target_url, headers=headers, data=body
        ) as upstream_resp:
            resp_body = await upstream_resp.read()
            client_resp = web.Response(
                status=upstream_resp.status,
                body=resp_body,
                content_type=upstream_resp.content_type,
            )
            return client_resp

    async def close(self) -> None:
        if self.session:
            await self.session.close()
        if self.runner:
            await self.runner.cleanup()


@pytest.mark.asyncio
async def test_supervisor_missing_runtime_recovery_and_lock_guards_e2e(
    tmp_path: Path, real_api_server
):
    """Reconstruct interrupted startup via bind RPC and verify lock guards."""
    browser_image, stream_image, engine_src = check_e2e_images()
    api_url, auth_token, token_file = real_api_server

    test_run_id = uuid.uuid4().hex[:6]
    prefix = f"t005-startup-{test_run_id}"

    data_root = tmp_path / "data_root"
    data_root.mkdir()
    engine_cache = data_root / "engine_cache"
    shutil.copytree(engine_src, engine_cache)

    agent_key_file = data_root / "agent_key"
    agent_key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    agent_key_file.chmod(0o600)

    d_client = docker.from_env()

    api_client = httpx.AsyncClient(
        base_url=api_url,
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10.0,
        trust_env=False,
    )
    validator = PathValidator(data_root)
    docker_adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=engine_cache,
        docker_client=d_client,
        browser_image=browser_image,
        stream_image=stream_image,
        resource_prefix=prefix,
    )
    port_allocator = PortAllocator(min_port=30000, max_port=30010)
    event_forwarder = EventForwarder(
        api_base_url=api_url,
        events_spool_dir=data_root / "spool",
        token_file=token_file,
        client=api_client,
    )
    core = SupervisorCore(
        docker_adapter=docker_adapter,
        port_allocator=port_allocator,
        event_forwarder=event_forwarder,
        api_client=api_client,
        gateway_url="ws://127.0.0.1:9999",
        token_file=token_file,
        agent_key_file=agent_key_file,
    )
    coordinator = RecoveryCoordinator(core)

    try:
        # Verify Docker scan with this prefix returns empty set (no containers)
        containers = await asyncio.to_thread(docker_adapter.scan_active_containers)
        assert len(containers) == 0

        # Create Profile 1 in real API
        p_resp = await api_client.post(
            "/api/v1/profiles", json={"name": "Startup Test Profile"}
        )
        assert p_resp.status_code == 201
        profile_id = p_resp.json()["id"]

        # Set desired_state = running
        patch_resp = await api_client.patch(
            f"/api/v1/profiles/{profile_id}/runtime/desired-state",
            json={"desired_state": "running"},
        )
        assert patch_resp.status_code == 200

        # Simulate SIGKILL after bind RPC: bind runtime instance via internal
        # supervisor API
        active_inst = f"inst_{uuid.uuid4().hex[:12]}"
        bind_resp = await api_client.post(
            f"/api/v1/internal/supervisor/runtimes/bind?profile_id={profile_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "runtime_instance_id": active_inst,
                "config_version": 1,
            },
        )
        assert bind_resp.status_code == 200

        # Verify API state is bound with running intent, but Docker has no container
        rt_check = await api_client.get(
            f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert rt_check.status_code == 200
        rt_data = rt_check.json()
        assert rt_data["desired_state"] == "running"
        assert rt_data["runtime_instance_id"] == active_inst
        assert rt_data["failure_count"] == 0
        assert rt_data["last_exit_event_id"] is None

        # Case 2 check first: Acquire profile lock and tick -> must NOT synthesize exit
        profile_lock = core._get_profile_lock(profile_id)
        await profile_lock.acquire()
        try:
            await coordinator.tick()
            rt_during_lock = (
                await api_client.get(
                    f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime",
                    headers={"Authorization": f"Bearer {auth_token}"},
                )
            ).json()
            assert rt_during_lock["runtime_instance_id"] == active_inst
            assert rt_during_lock["failure_count"] == 0
            assert rt_during_lock["last_exit_event_id"] is None
        finally:
            profile_lock.release()

        # Case 1: With lock released, run tick()
        await coordinator.tick()

        # Authoritative API state must now reflect missing_runtime exit
        rt_after = (
            await api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        ).json()
        assert rt_after["runtime_instance_id"] is None
        assert rt_after["failure_count"] == 1
        assert rt_after["last_exit_event_id"] == f"missing_runtime:{active_inst}"
        assert rt_after["observed_state"] == "stopped"

        # Verify retry task was scheduled for 2s backoff
        assert profile_id in coordinator._in_flight_tasks

        # Repeat tick immediately: must NOT synthesize duplicate exit or
        # increase failure count
        await coordinator.tick()
        rt_repeat = (
            await api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        ).json()
        assert rt_repeat["failure_count"] == 1
        assert rt_repeat["last_exit_event_id"] == f"missing_runtime:{active_inst}"

    finally:
        await coordinator.close()
        await event_forwarder.close()
        await api_client.aclose()
        d_client.close()


@pytest.mark.asyncio
async def test_supervisor_native_exit_priority_over_synthetic_e2e(
    tmp_path: Path, real_api_server
):
    """Preserve normal exit semantics through a real HTTP 503 and replay."""
    browser_image, stream_image, engine_src = check_e2e_images()
    api_url, auth_token, token_file = real_api_server

    test_run_id = uuid.uuid4().hex[:6]
    prefix = f"t005-startup-{test_run_id}"

    data_root = tmp_path / "data_root"
    data_root.mkdir()
    engine_cache = data_root / "engine_cache"
    shutil.copytree(engine_src, engine_cache)

    agent_key_file = data_root / "agent_key"
    agent_key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    agent_key_file.chmod(0o600)

    # Start local HTTP fault proxy in front of real API
    proxy = HttpFaultProxy(api_url)
    proxy_url = await proxy.start()

    d_client = docker.from_env()

    # Direct client to real API for assertions and setup
    real_api_client = httpx.AsyncClient(
        base_url=api_url,
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10.0,
        trust_env=False,
    )

    # Proxy-routed client for supervisor components
    proxy_api_client = httpx.AsyncClient(
        base_url=proxy_url,
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10.0,
        trust_env=False,
    )

    validator = PathValidator(data_root)
    docker_adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=engine_cache,
        docker_client=d_client,
        browser_image=browser_image,
        stream_image=stream_image,
        resource_prefix=prefix,
    )
    port_allocator = PortAllocator(min_port=30000, max_port=30010)
    event_forwarder = EventForwarder(
        api_base_url=proxy_url,
        events_spool_dir=data_root / "spool",
        token_file=token_file,
        client=proxy_api_client,
    )
    core = SupervisorCore(
        docker_adapter=docker_adapter,
        port_allocator=port_allocator,
        event_forwarder=event_forwarder,
        api_client=proxy_api_client,
        gateway_url="ws://127.0.0.1:9999",
        token_file=token_file,
        agent_key_file=agent_key_file,
    )
    coordinator = RecoveryCoordinator(core)

    try:
        # Create Profile in real API
        p_resp = await real_api_client.post(
            "/api/v1/profiles", json={"name": "Native Priority Profile"}
        )
        assert p_resp.status_code == 201
        profile_id = p_resp.json()["id"]

        # Set desired_state = running
        await real_api_client.patch(
            f"/api/v1/profiles/{profile_id}/runtime/desired-state",
            json={"desired_state": "running"},
        )

        # Bind runtime instance
        native_inst = f"inst_{uuid.uuid4().hex[:12]}"
        bind_resp = await real_api_client.post(
            f"/api/v1/internal/supervisor/runtimes/bind?profile_id={profile_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "runtime_instance_id": native_inst,
                "config_version": 1,
            },
        )
        assert bind_resp.status_code == 200

        # Write a real native normal exit event (code 0) to disk journal
        event_dir = (
            data_root
            / "runtime-events"
            / profile_id
            / "events"
            / "runtime"
            / native_inst
        )
        event_dir.mkdir(parents=True)
        native_event_file = event_dir / "native_exit.json"
        native_event_file.write_text(
            json.dumps(
                {
                    "event_id": f"native_exit:{native_inst}",
                    "profile_id": profile_id,
                    "runtime_instance_id": native_inst,
                    "event_type": "exit",
                    "exit_code": 0,
                    "exit_reason": "normal",
                    "config_version": 1,
                    "payload": {"source": "native_chrome"},
                }
            ),
            encoding="utf-8",
        )

        # Core consumes disk events: proxy returns 503 on first POST /events.
        # Event is queued in spool, and (profile_id, native_inst, 1) is
        # registered in core._native_exit_instances.
        forwarded = await core.consume_disk_events()
        assert forwarded == 0  # not acknowledged because 503 was returned
        assert core.has_native_exit(profile_id, native_inst, 1) is True

        # Verify proxy did inject the 503
        assert proxy.first_post_503_done is True

        # Now tick() runs: Docker has NO container for this profile.
        # Under naive missing logic, it would synthesize
        # missing_runtime:<instance> (abnormal exit=1).
        # But has_native_exit is True: tick() MUST NOT synthesize missing exit!
        await coordinator.tick()

        # Authoritative API check: still in original bound state, failure_count=0
        rt_after_tick = (
            await real_api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        ).json()
        assert rt_after_tick["runtime_instance_id"] == native_inst
        assert rt_after_tick["failure_count"] == 0
        assert rt_after_tick["last_exit_event_id"] is None
        assert native_inst not in coordinator._reported_dead_instances

        # Now replay spooled events (proxy will forward normally now)
        replayed = await event_forwarder.replay_spooled_events()
        assert replayed == 1

        # API state must now converge to stopped with 0 failure count (normal exit)
        rt_final = (
            await real_api_client.get(
                f"/api/v1/internal/supervisor/profiles/{profile_id}/runtime",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        ).json()
        assert rt_final["desired_state"] == "stopped"
        assert rt_final["observed_state"] == "stopped"
        assert rt_final["runtime_instance_id"] is None
        assert rt_final["failure_count"] == 0
        assert rt_final["last_exit_event_id"] == f"native_exit:{native_inst}"

        # Additional tick: desired_state is stopped, no retry should be scheduled
        await coordinator.tick()
        assert profile_id not in coordinator._in_flight_tasks

    finally:
        await coordinator.close()
        await event_forwarder.close()
        await proxy_api_client.aclose()
        await real_api_client.aclose()
        await proxy.close()
        d_client.close()
