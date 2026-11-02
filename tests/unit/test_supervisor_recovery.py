"""Unit test suite for Supervisor Control Server & State Recovery Components.

Tests:
1. Control server authentication (rejects unauthenticated/wrong token,
   accepts valid Bearer token).
2. Start/stop/status/reset-blocked control RPC routes.
3. Offline disk event consumption & status fence.
"""

import json
import secrets
from pathlib import Path

import httpx
import pytest
from cbrowser.domain.models import ProfileConfig
from cbrowser.supervisor.agent_credentials import AgentCredentials
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.gateway_client import GatewayControlClient
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


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
            json={"profile_id": "p_test", "config_version": 1},
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
    assert "p_err" in core._sessions
    assert core._sessions["p_err"].udp_mux_port == 30005
    assert core.ports.is_port_used(30005)


@pytest.mark.asyncio
async def test_supervisor_gateway_fixture_contract(tmp_path: Path):
    import importlib.util
    import sys

    from aiohttp import ClientSession

    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "supervisor_recovery_probe"
        / "gateway_fixture.py"
    )
    spec = importlib.util.spec_from_file_location("gateway_fixture", fixture_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["gateway_fixture"] = module
    spec.loader.exec_module(module)
    SupervisorGatewayFixture = module.SupervisorGatewayFixture

    agent_key_file = tmp_path / "gw_agent_key"
    agent_key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    agent_key_file.chmod(0o600)
    gw_token_file = tmp_path / "gw_token"
    gw_token = secrets.token_urlsafe(32)
    gw_token_file.write_text(gw_token, encoding="utf-8")

    credentials = AgentCredentials(agent_key_file)
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    fixture = SupervisorGatewayFixture(
        port=port, credentials=credentials, token_file=gw_token_file
    )
    await fixture.start()

    profile_id = "test-p1"
    runtime_instance_id = "test-inst-1"
    agent_token = credentials.token_for(profile_id, runtime_instance_id)

    auth_headers = {"Authorization": f"Bearer {gw_token}"}
    client = httpx.AsyncClient(
        base_url=fixture.control_url, headers=auth_headers, trust_env=False
    )

    try:
        # 1. No agent registered yet: internal control returns 503
        r_unavail = await client.get(
            f"/gateway/v1/internal/profiles/{profile_id}/visibility",
            params={"runtime_instance_id": runtime_instance_id},
        )
        assert r_unavail.status_code == 503

        # 2. Register Agent over WebSocket
        async with ClientSession() as session:
            ws_url = f"http://127.0.0.1:{port}/stream/agent/register"
            async with session.ws_connect(
                ws_url, headers={"Authorization": f"Bearer {agent_token}"}
            ) as agent_ws:
                await agent_ws.send_json(
                    {
                        "version": "v2",
                        "action": "register",
                        "profile_id": profile_id,
                        "runtime_instance_id": runtime_instance_id,
                    }
                )
                ack = await agent_ws.receive_json()
                assert ack["status"] == "ok"
                assert ack["profile_id"] == profile_id
                assert ack["runtime_instance_id"] == runtime_instance_id
                agent_session_id = ack["agent_session_id"]
                assert agent_session_id

                # 3. Unauthorized control RPC (wrong Bearer token) -> 401
                bad_auth_client = httpx.AsyncClient(
                    base_url=fixture.control_url,
                    headers={"Authorization": "Bearer bad"},
                    trust_env=False,
                )
                r_unauth = await bad_auth_client.get(
                    f"/gateway/v1/internal/profiles/{profile_id}/visibility",
                    params={"runtime_instance_id": runtime_instance_id},
                )
                assert r_unauth.status_code == 401
                await bad_auth_client.aclose()

                # 4. Instance fence mismatch -> 409
                r_conflict = await client.get(
                    f"/gateway/v1/internal/profiles/{profile_id}/visibility",
                    params={"runtime_instance_id": "wrong-instance-id"},
                )
                assert r_conflict.status_code == 409

                # 5. Visibility check: no viewers -> False
                r_vis1 = await client.get(
                    f"/gateway/v1/internal/profiles/{profile_id}/visibility",
                    params={"runtime_instance_id": runtime_instance_id},
                )
                assert r_vis1.status_code == 200
                assert r_vis1.json()["has_foreground_viewers"] is False

                # 6. Connect viewer with foreground=true
                viewer_url = (
                    f"http://127.0.0.1:{port}/viewer/{profile_id}?foreground=true"
                )
                async with session.ws_connect(viewer_url) as viewer_ws:
                    # Visibility check now returns True
                    r_vis2 = await client.get(
                        f"/gateway/v1/internal/profiles/{profile_id}/visibility",
                        params={"runtime_instance_id": runtime_instance_id},
                    )
                    assert r_vis2.status_code == 200
                    assert r_vis2.json()["has_foreground_viewers"] is True

                    # 7. Quota route: forwards v2 supervisor_quota envelope to Agent WS
                    r_quota = await client.post(
                        f"/gateway/v1/internal/profiles/{profile_id}/quota",
                        json={
                            "runtime_instance_id": runtime_instance_id,
                            "max_fps_cap": 15.0,
                        },
                    )
                    assert r_quota.status_code == 200
                    quota_msg = await agent_ws.receive_json()
                    assert quota_msg["action"] == "supervisor_quota"
                    assert quota_msg["profile_id"] == profile_id
                    assert quota_msg["runtime_instance_id"] == runtime_instance_id
                    assert quota_msg["agent_session_id"] == agent_session_id
                    assert quota_msg["payload"]["max_fps_cap"] == 15.0

                    # 8. Disconnect route: closes viewer WS, leaves agent WS open
                    r_disc = await client.post(
                        f"/gateway/v1/internal/profiles/{profile_id}/disconnect",
                        json={"runtime_instance_id": runtime_instance_id},
                    )
                    assert r_disc.status_code == 200

                    # Viewer receives close frame
                    viewer_close = await viewer_ws.receive()
                    assert viewer_close.type.name in ("CLOSE", "CLOSED")

                # Agent WS is still open and alive
                assert not agent_ws.closed
    finally:
        await client.aclose()
        await fixture.stop()
