"""Unit test suite for Supervisor Control Server & State Recovery Components.

Tests:
1. Control server authentication (rejects unauthenticated/wrong token,
   accepts valid Bearer token).
2. Start/stop/status/reset-blocked control RPC routes.
3. Offline disk event consumption & status fence.
"""

import asyncio
import json
import secrets
import socket
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from wait import poll_until
from aiohttp import ClientSession, WSMsgType
from cbrowser.domain.models import ProfileConfig
from cbrowser.shared.agent_credentials import AgentCredentials
from cbrowser.shared.viewer_grants import (
    AUTHORIZED_PROFILE_HEADER,
    VIEWER_GRANT_HEADER,
)
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.gateway_client import GatewayControlClient
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from cbrowser.stream_agent.messaging import (
    build_heartbeat_envelope,
    build_register_envelope,
    build_register_payload,
    iso_now,
)
from cbrowser.stream_agent.protocol import AgentHeartbeatPayload
from supervisor_recovery_probe.gateway_service import (
    FakeGatewayApiClient,
    ProductionGatewayService,
)


@pytest.fixture
def supervisor_setup(tmp_path: Path):
    token = secrets.token_urlsafe(32)
    token_file = tmp_path / "sup_token"
    token_file.write_text(token)
    token_file.chmod(0o600)

    agent_key_file = tmp_path / "agent_key"
    agent_key_file.write_text(secrets.token_urlsafe(32))
    agent_key_file.chmod(0o600)
    agent_key_file.chmod(0o600)

    gw_token_file = tmp_path / "gw_token"
    gw_token_file.write_text(secrets.token_urlsafe(32))
    gw_token_file.chmod(0o600)

    data_root = tmp_path / "data_root"
    data_root.mkdir()

    # Mock API transport for supervisor's outgoing calls
    runtime_state = {
        "profile_id": "p_test",
        "display_number": 1,
        "desired_state": "running",
        "observed_state": "stopped",
        "runtime_instance_id": None,
        "config_version": 1,
        "failure_count": 0,
        "restart_blocked": False,
        "last_exit_event_id": None,
        "updated_at": "2026-10-29T00:00:00Z",
    }

    def api_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if "/versions/" in p:
            return httpx.Response(
                200,
                json={
                    "profile_id": "p_test",
                    "version": 1,
                    "config": ProfileConfig(name="Test").model_dump(),
                },
            )
        if p.endswith("/runtime"):
            return httpx.Response(200, json=runtime_state)
        if "/runtimes/bind" in p:
            runtime_state["runtime_instance_id"] = json.loads(request.content)[
                "runtime_instance_id"
            ]
            return httpx.Response(200, json={"status": "ok"})
        if "/runtimes/observed" in p:
            runtime_state["observed_state"] = json.loads(request.content)[
                "observed_state"
            ]
            return httpx.Response(200, json={"status": "ok"})
        if "/runtimes/events" in p:
            return httpx.Response(200, json={"status": "ok", "outcome": "applied"})
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(api_handler)
    api_client = httpx.AsyncClient(
        transport=transport, base_url="http://api.internal", trust_env=False
    )

    gw_control = GatewayControlClient("http://gateway.internal", gw_token_file)

    def gw_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"status": "ok", "has_foreground_viewers": False}
        )

    gw_control._client = httpx.AsyncClient(
        transport=httpx.MockTransport(gw_handler),
        base_url="http://gateway.internal",
        trust_env=False,
    )

    validator = PathValidator(data_root)

    # Mock docker adapter for unit testing control server without spawning real
    # containers
    class MockDockerAdapter:
        def __init__(self):
            self.validator = validator
            self.resource_prefix = "test-prefix"

        def remember_profile_number(self, pid, number):
            return None

        def get_browser_container_name(self, pid):
            return f"b_{pid}"

        def get_stream_container_name(self, pid):
            return f"s_{pid}"

        def get_network_name(self, pid):
            return f"net_{pid}"

        def prepare_profile_directories(self, pid):
            r_dir = data_root / "runtime" / pid
            r_dir.mkdir(parents=True, exist_ok=True)
            for d in ("profile", "exchange", "x11", "pulse"):
                (data_root / d).mkdir(parents=True, exist_ok=True)
            return {
                "profile": data_root / "profile",
                "runtime": r_dir,
                "events": data_root / "runtime-events" / pid,
                "exchange": data_root / "exchange",
                "x11": data_root / "x11",
                "pulse": data_root / "pulse",
            }

        async def create_profile_network(self, pid):
            pass

        async def start_browser_container(self, **kwargs):
            class C:
                id = "cid_b"
                name = "b_name"

            # create mock sockets matching browser_runtime_ready contract
            pid = kwargs["profile_id"]
            iid = kwargs.get("runtime_instance_id", "inst_1")
            r_dir = data_root / "runtime" / pid
            r_dir.mkdir(parents=True, exist_ok=True)
            for relative in (
                "x11/X99",
                "pulse/pulse.sock",
                "Xauthority",
                "agent.sock",
            ):
                path = r_dir / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            info = {
                "profile_id": pid,
                "runtime_instance_id": iid,
                "config_version": 1,
                "browser_pid": 1234,
            }
            (r_dir / "runner_info.json").write_text(json.dumps(info))
            return C()

        async def start_stream_container(self, **kwargs):
            class C:
                id = "cid_s"
                status = "running"

                def reload(self):
                    pass

            return C()

        def attach_profile_infrastructure(self, *args, **kwargs):
            return {"gateway_ip": "10.0.0.8", "gateway_url": "ws://10.0.0.8:18080"}

        async def teardown_profile(self, pid):
            pass

        def cleanup_container_by_name(self, n):
            pass

        def cleanup_network_by_name(self, n):
            pass

        def scan_active_containers(self):
            return []

    docker_adapter = MockDockerAdapter()
    port_allocator = PortAllocator(min_port=30000, max_port=30005)
    event_forwarder = EventForwarder(
        api_base_url="http://api.internal",
        events_spool_dir=data_root / "spool",
        token_file=token_file,
        client=api_client,
    )

    core = SupervisorCore(
        docker_adapter=docker_adapter,
        port_allocator=port_allocator,
        event_forwarder=event_forwarder,
        api_client=api_client,
        token_file=token_file,
        agent_key_file=agent_key_file,
        gateway_control=gw_control,
    )

    app = create_control_app(core, token_file)
    return app, token, core, data_root


@pytest.mark.asyncio
async def test_control_server_auth_and_routes(supervisor_setup):
    app, token, _core, _data_root = supervisor_setup
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://supervisor.internal", trust_env=False
    ) as client:
        # 1. Reject unauthenticated
        r1 = await client.get("/supervisor/v1/health")
        assert r1.status_code == 401

        # 2. Reject bad token
        r2 = await client.get(
            "/supervisor/v1/health", headers={"Authorization": "Bearer bad"}
        )
        assert r2.status_code == 401

        # 3. Accept valid token
        auth_headers = {"Authorization": f"Bearer {token}"}
        r3 = await client.get("/supervisor/v1/health", headers=auth_headers)
        assert r3.status_code == 200
        assert r3.json() == {"status": "ok", "role": "supervisor"}

        # 4. Status route
        r_stat = await client.get(
            "/supervisor/v1/profiles/p_test/status", headers=auth_headers
        )
        assert r_stat.status_code == 200
        assert r_stat.json()["observed_state"] == "stopped"

        # 5. Start profile
        r_start = await client.post(
            "/supervisor/v1/profiles/start",
            headers=auth_headers,
            json={"profile_id": "p_test", "profile_number": 1, "config_version": 1},
        )
        assert r_start.status_code == 200
        assert r_start.json()["status"] == "running"
        assert r_start.json()["udp_mux_port"] == 30000

        # Status is now running
        r_stat2 = await client.get(
            "/supervisor/v1/profiles/p_test/status", headers=auth_headers
        )
        assert r_stat2.json()["observed_state"] == "running"

        # 6. Stop profile
        r_stop = await client.post(
            "/supervisor/v1/profiles/stop",
            headers=auth_headers,
            json={
                "profile_id": "p_test",
                "runtime_instance_id": r_start.json()["runtime_instance_id"],
                "operation_id": "op_stop_1",
            },
        )
        assert r_stop.status_code == 200
        assert r_stop.json()["status"] == "stopped"

        # 7. Reset blocked
        r_reset = await client.post(
            "/supervisor/v1/profiles/reset-blocked",
            headers=dict(auth_headers, **{"Idempotency-Key": "op_reset_1"}),
            json={"profile_id": "p_test"},
        )
        assert r_reset.status_code == 200


@pytest.mark.asyncio
async def test_offline_reconciliation_preserves_containers_on_api_error(
    supervisor_setup,
):
    _app, _token, core, _data_root = supervisor_setup

    # Mock container in docker_adapter
    class MockC:
        def __init__(self) -> None:
            self.id = "test_c_id"
            self.name = "test_c_name"
            self.labels = {"com.cbrowser.prefix": "test-prefix"}

    core.docker.scan_active_containers = lambda: [
        {
            "id": "b1",
            "status": "running",
            "policy_ready": True,
            "name": "b1_name",
            "profile_id": "p_err",
            "role": "browser",
            "instance_id": "inst_1",
        },
        {
            "id": "s1",
            "status": "running",
            "policy_ready": True,
            "name": "s1_name",
            "profile_id": "p_err",
            "role": "stream",
            "instance_id": "inst_1",
        },
    ]
    core.docker.client = type(
        "MockClient",
        (),
        {
            "api": type(
                "MockAPI",
                (),
                {
                    "inspect_container": lambda *args, **kwargs: {
                        "HostConfig": {
                            "PortBindings": {"30005/udp": [{"HostPort": "30005"}]}
                        }
                    }
                },
            )()
        },
    )()

    # 1. API returns 503 or 500: containers must NOT be torn down
    teardown_called = False

    async def mock_teardown(pid):
        nonlocal teardown_called
        teardown_called = True

    core.docker.teardown_profile = mock_teardown

    # Force API 503
    def err_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "busy"})

    core.api = httpx.AsyncClient(
        transport=httpx.MockTransport(err_handler),
        base_url="http://api.internal",
        trust_env=False,
    )

    await core.scan_and_reconcile_existing()
    assert teardown_called is False, "503 must NOT tear down healthy containers"

    # 2. API returns 200 running: session reconstructed and port 30005 occupied
    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "profile_id": "p_err",
                "desired_state": "running",
                "observed_state": "running",
                "runtime_instance_id": "inst_1",
                "config_version": 1,
                "failure_count": 0,
                "restart_blocked": False,
                "last_exit_event_id": None,
                "updated_at": "2026-10-29T00:00:00Z",
            },
        )

    core.api = httpx.AsyncClient(
        transport=httpx.MockTransport(ok_handler),
        base_url="http://api.internal",
        trust_env=False,
    )

    await core.scan_and_reconcile_existing()
    assert core.get_session("p_err") is not None
    assert core.get_session("p_err").udp_mux_port == 30005
    assert core.ports.is_port_used(30005)


@pytest.mark.asyncio
async def test_production_gateway_contract_used_by_supervisor(tmp_path: Path):
    """Supervisor control and viewer paths run against the production Gateway."""
    agent_key_file = tmp_path / "gw_agent_key"
    agent_key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    agent_key_file.chmod(0o600)
    gw_token_file = tmp_path / "gw_token"
    gw_token = secrets.token_urlsafe(32)
    gw_token_file.write_text(gw_token, encoding="utf-8")
    gw_token_file.chmod(0o600)

    credentials = AgentCredentials(agent_key_file)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    profile_id = "test-p1"
    runtime_instance_id = "test-inst-1"
    fake_api = FakeGatewayApiClient()
    fake_api.set_profile_runtime(profile_id, runtime_instance_id)

    gateway = ProductionGatewayService(
        port=port,
        agent_key_file=agent_key_file,
        gateway_token_file=gw_token_file,
        api_client=fake_api,
    )
    await gateway.start()

    agent_token = credentials.token_for(profile_id, runtime_instance_id)
    control = GatewayControlClient(gateway.control_url, gw_token_file)
    ws_base = f"ws://127.0.0.1:{port}"
    viewer_headers = {
        "Origin": "https://127.0.0.1:56661",
        AUTHORIZED_PROFILE_HEADER: profile_id,
        VIEWER_GRANT_HEADER: gateway.grant_authority.mint(profile_id),
    }
    agent_config = SimpleNamespace(
        profile_id=profile_id,
        runtime_instance_id=runtime_instance_id,
        udp_mux_port=30000,
        selkies_version="2.1.0",
        config_version=1,
        video_streaming_mode=False,
        width=1920,
        height=1080,
    )

    try:
        # 1. No agent registered yet: production control returns 503.
        with pytest.raises(httpx.HTTPStatusError) as unavailable:
            await control.has_foreground_viewers(
                profile_id, runtime_instance_id
            )
        assert unavailable.value.response.status_code == 503

        # 2. Register the Agent through the production WebSocket route.
        async with ClientSession() as session:
            register_url = (
                f"{ws_base}/stream/agent/register"
                f"?profile_id={profile_id}"
                f"&runtime_instance_id={runtime_instance_id}"
            )
            async with session.ws_connect(
                register_url,
                headers={"Authorization": f"Bearer {agent_token}"},
            ) as agent_ws:
                register = build_register_envelope(
                    agent_config,
                    build_register_payload(agent_config, "test-host", "2.1.0"),
                    iso_now(),
                )
                await agent_ws.send_str(register.model_dump_json())
                ack = await agent_ws.receive_json()
                assert ack["status"] == "ok"
                assert ack["profile_id"] == profile_id
                assert ack["runtime_instance_id"] == runtime_instance_id
                agent_session_id = ack["agent_session_id"]
                assert agent_session_id

                # 3. Instance fence mismatch -> 409.
                with pytest.raises(httpx.HTTPStatusError) as fenced:
                    await control.has_foreground_viewers(
                        profile_id, "wrong-instance-id"
                    )
                assert fenced.value.response.status_code == 409

                # 4. Visibility comes from the Agent heartbeat report.
                heartbeat = build_heartbeat_envelope(
                    agent_config,
                    agent_session_id,
                    AgentHeartbeatPayload(
                        runtime_state="ready",
                        viewer_count=1,
                        unpaused_video_consumers=1,
                        capture_running=True,
                    ),
                    iso_now(),
                )
                await agent_ws.send_str(heartbeat.model_dump_json())

                async def read_visible() -> bool | None:
                    try:
                        return await control.has_foreground_viewers(
                            profile_id, runtime_instance_id
                        )
                    except httpx.HTTPStatusError:
                        return None

                visible = await poll_until(
                    read_visible,
                    lambda value: value is not None,
                    timeout=5.0,
                    interval=0.05,
                    description="Agent heartbeat observable through Gateway",
                )
                assert visible is True

                # 5. Real viewer signaling: connect, tunnel both directions.
                viewer_url = f"{ws_base}/stream/{profile_id}/signal"
                async with session.ws_connect(
                    viewer_url, headers=viewer_headers
                ) as viewer_ws:
                    opened = await agent_ws.receive_json()
                    assert opened["type"] == "open"
                    assert opened["profile_id"] == profile_id
                    assert opened["runtime_instance_id"] == runtime_instance_id
                    conn_id = opened["conn_id"]

                    await viewer_ws.send_str("client-frame")
                    forwarded = await agent_ws.receive_json()
                    assert forwarded["type"] == "msg"
                    assert forwarded["conn_id"] == conn_id
                    assert forwarded["data"] == "client-frame"

                    await agent_ws.send_str(
                        json.dumps(
                            {
                                "version": "v2",
                                "type": "msg",
                                "profile_id": profile_id,
                                "runtime_instance_id": runtime_instance_id,
                                "agent_session_id": agent_session_id,
                                "conn_id": conn_id,
                                "data": "agent-frame",
                            }
                        )
                    )
                    reply = await viewer_ws.receive()
                    assert reply.type is WSMsgType.TEXT
                    assert reply.data == "agent-frame"

                    # 6. Quota route forwards a v2 supervisor_quota envelope.
                    await control.set_quota(profile_id, runtime_instance_id, 15.0)
                    quota_msg = await agent_ws.receive_json()
                    assert quota_msg["action"] == "supervisor_quota"
                    assert quota_msg["profile_id"] == profile_id
                    assert quota_msg["runtime_instance_id"] == runtime_instance_id
                    assert quota_msg["agent_session_id"] == agent_session_id
                    assert quota_msg["payload"]["max_fps_cap"] == 15.0

                    # 7. Disconnect closes the viewer, not the Agent session.
                    await control.disconnect_viewers(
                        profile_id, runtime_instance_id
                    )
                    viewer_close = await viewer_ws.receive()
                    assert viewer_close.type == WSMsgType.CLOSE
                    close_env = await agent_ws.receive_json()
                    assert close_env["type"] == "close"
                    assert close_env["conn_id"] == conn_id

                assert not agent_ws.closed
    finally:
        await control.close()
        await gateway.stop()
