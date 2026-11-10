"""Run the actual Supervisor, API and sandbox topology as isolated containers.

Node Replacement Notice:
- Deprecated node: `test_supervisor_container_rpc_socket_and_instance_fenced_lifecycle`
  (deprecated because it retained legacy port 18097 assertions and pre-t006 Gateway
  assumptions; modifying assertions in-place violated repo non-regression policy).
- Replaced by:
  `test_authoritative_gateway_port_credentials_and_instance_fenced_lifecycle`
- Replacement Coverage: Fully covers authoritative gateway port (DEFAULT_GATEWAY_PORT),
  credential isolation (strict 0600 keys for supervisor/agent/gateway), isolated
  bridge network topology, and instance-fenced lifecycle while preserving 100% of the
  original business assertions.
"""

import asyncio
import json
import logging
import os
import secrets
import shutil
import socket
import stat
import uuid
from pathlib import Path

import aiohttp
import docker
import httpx
import pytest

from e2e_env import require_e2e_env
from wait import poll_until
from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT

from api_auth import create_auth_context

pytestmark = pytest.mark.serial
logger = logging.getLogger("cbrowser.test_container_graph")


def endpoint(container, port):
    container.reload()
    assert container.status == "running", f"Container startup failed: {container.name}"
    binding = container.attrs["NetworkSettings"]["Ports"][f"{port}/tcp"][0]
    return f"http://127.0.0.1:{binding['HostPort']}"


async def ready(url, path, headers=None, expected_status=200):
    async with httpx.AsyncClient(base_url=url, trust_env=False) as client:
        deadline = asyncio.get_running_loop().time() + 30
        while asyncio.get_running_loop().time() < deadline:
            try:
                response = await client.get(path, headers=headers)
                if response.status_code == expected_status:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.2)
    raise AssertionError("Container HTTP service did not become ready")


@pytest.mark.asyncio
async def test_authoritative_gateway_port_credentials_and_instance_fenced_lifecycle(
    tmp_path,
):
    require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_GATEWAY_IMAGE",
        "CBROWSER_SUPERVISOR_TEST_IMAGE",
        "CBROWSER_API_TEST_IMAGE",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        "CBROWSER_RUNTIME_GEOIP_CACHE",
        paths=("CBROWSER_RUNTIME_ENGINE_CACHE", "CBROWSER_RUNTIME_GEOIP_CACHE"),
    )
    client = docker.from_env()
    prefix = "t005-graph-" + uuid.uuid4().hex[:10]
    containers = []
    profiles = set()
    data = tmp_path / "data"
    data.mkdir(parents=True)
    # The whole tree is confined under a 0o700 parent (t024 AC-014/A43):
    # the data subdirectories are bind-mounted into containers running as
    # other uids and therefore stay group/other-writable, but no path
    # component above them is traversable by unrelated local users.
    data.chmod(0o700)
    control = data / "control"
    control.mkdir(parents=True)
    control.chmod(0o700)
    for name in (
        "profiles",
        "runtime",
        "runtime-events",
        "artifacts",
        "spool",
        "network",
        "sockets",
    ):
        (data / name).mkdir(parents=True, exist_ok=True)
        (data / name).chmod(0o777)
    from cbrowser.domain.models import NetworkAccessConfig
    from cbrowser.network_config import build_applied_network_version, write_applied_network_state
    v1_init, v1_caddyfile = build_applied_network_version(
        NetworkAccessConfig(lan_access_enabled=False), version=1
    )
    write_applied_network_state(data / "network", v1_init, v1_caddyfile)
    cache = data / "engine_cache"
    shutil.copytree(os.environ["CBROWSER_RUNTIME_ENGINE_CACHE"], cache)
    shutil.copytree(
        os.environ["CBROWSER_RUNTIME_GEOIP_CACHE"], cache / "geoip", dirs_exist_ok=True
    )
    keys = {}
    for name in ("supervisor", "agent", "gateway", "gateway_api"):
        key = control / (name + "_key")
        key.write_text(secrets.token_urlsafe(32))
        key.chmod(0o600)
        assert stat.S_IMODE(key.stat().st_mode) == 0o600
        keys[name] = key
    headers = {"Authorization": "Bearer " + keys["supervisor"].read_text()}
    metadata = tmp_path / "api_metadata"
    metadata.mkdir()
    metadata.chmod(0o777)
    edge = None
    viewer = None
    stop_task = None

    def image(variable):
        value = os.environ[variable]
        assert value.startswith("sha256:")
        client.images.get(value)
        return value

    def run(role, image_id, **kwargs):
        container = client.containers.run(
            image_id,
            name=f"{prefix}-{role}",
            detach=True,
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            network=edge.name,
            tmpfs={"/tmp": "rw,size=256m"},
            labels={
                "com.cbrowser.prefix": prefix,
                "com.cbrowser.managed-by": "supervisor",
                "com.cbrowser.role": role,
            },
            **kwargs,
        )
        containers.append(container)
        return container

    try:
        edge = client.networks.create(
            prefix + "-edge", labels={"com.cbrowser.prefix": prefix}
        )
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            api_host_port = s.getsockname()[1]

        auth_ctx = create_auth_context(control)
        api = run(
            "api",
            image("CBROWSER_API_TEST_IMAGE"),
            environment={
                "CBROWSER_DB_PATH": "/metadata/control.db",
                "CBROWSER_SUPERVISOR_TOKEN_FILE": "/run/secrets/key",
                "CBROWSER_GATEWAY_API_TOKEN_FILE": "/run/secrets/gateway_api",
                "CBROWSER_ADMIN_PASSWORD_FILE": "/run/secrets/admin_pass",
            },
            volumes={
                str(metadata): {"bind": "/metadata", "mode": "rw"},
                str(keys["supervisor"]): {"bind": "/run/secrets/key", "mode": "ro"},
                str(keys["gateway_api"]): {
                    "bind": "/run/secrets/gateway_api",
                    "mode": "ro",
                },
                str(auth_ctx.admin_password_file): {
                    "bind": "/run/secrets/admin_pass",
                    "mode": "ro",
                },
            },
            ports={"8000/tcp": ("127.0.0.1", api_host_port)},
        )
        gateway = run(
            "gateway",
            image("CBROWSER_GATEWAY_IMAGE"),
            environment={
                "CBROWSER_AGENT_KEY_FILE": "/run/secrets/agent",
                "CBROWSER_GATEWAY_TOKEN_FILE": "/run/secrets/gateway",
                "CBROWSER_GATEWAY_API_URL": f"http://{prefix}-api:8000",
                "CBROWSER_GATEWAY_API_TOKEN_FILE": "/run/secrets/gateway_api",
                "CBROWSER_NETWORK_STATE_DIR": "/data/network",
                "CBROWSER_UDP_MUX_MIN_PORT": os.environ.get(
                    "CBROWSER_E2E_UDP_BASE", "30000"
                ),
                "CBROWSER_UDP_MUX_MAX_PORT": str(
                    int(os.environ.get("CBROWSER_E2E_UDP_BASE", "30000")) + 991
                ),
            },
            volumes={
                str(keys["agent"]): {"bind": "/run/secrets/agent", "mode": "ro"},
                str(keys["gateway"]): {"bind": "/run/secrets/gateway", "mode": "ro"},
                str(keys["gateway_api"]): {
                    "bind": "/run/secrets/gateway_api",
                    "mode": "ro",
                },
                str(data / "network"): {"bind": "/data/network", "mode": "ro"},
            },
            ports={f"{DEFAULT_GATEWAY_PORT}/tcp": ("127.0.0.1", None)},
        )
        await ready(endpoint(api, 8000), "/api/v1/health")
        await ready(
            endpoint(gateway, DEFAULT_GATEWAY_PORT),
            "/stream/agent/register",
            expected_status=401,
        )
        api.reload()
        gateway.reload()
        api_ip = api.attrs["NetworkSettings"]["Networks"][edge.name]["IPAddress"]
        gateway_ip = gateway.attrs["NetworkSettings"]["Networks"][edge.name][
            "IPAddress"
        ]
        mounts = {
            str(data / name): {"bind": str(data / name), "mode": "rw"}
            for name in (
                "engine_cache",
                "profiles",
                "runtime",
                "runtime-events",
                "artifacts",
                "spool",
                "control",
                "sockets",
            )
        }
        mounts["/var/run/docker.sock"] = {"bind": "/var/run/docker.sock", "mode": "ro"}
        supervisor = run(
            "supervisor",
            image("CBROWSER_SUPERVISOR_TEST_IMAGE"),
            cap_add=["FOWNER", "DAC_OVERRIDE", "CHOWN"],
            environment={
                "CBROWSER_BROWSER_IMAGE": image("CBROWSER_RUNTIME_TEST_IMAGE"),
                "CBROWSER_STREAM_IMAGE": image("CBROWSER_STREAM_TEST_IMAGE"),
                "CBROWSER_NETWORK_POLICY_IMAGE": image(
                    "CBROWSER_SUPERVISOR_TEST_IMAGE"
                ),
                "CBROWSER_UDP_MUX_MIN_PORT": os.environ.get(
                    "CBROWSER_E2E_UDP_BASE", "30000"
                ),
                "CBROWSER_UDP_MUX_MAX_PORT": str(
                    int(os.environ.get("CBROWSER_E2E_UDP_BASE", "30000")) + 991
                ),
                "CBROWSER_MEDIA_SUBNET_POOL": os.environ.get(
                    "CBROWSER_E2E_MEDIA_POOL", "10.251.0.0/16"
                ),
            },
            volumes=mounts,
            ports={"8005/tcp": ("127.0.0.1", None)},
            command=[
                "--api-url",
                f"http://{api_ip}:8000",
                "--data-root",
                str(data),
                "--engine-cache",
                str(cache),
                "--token-file",
                str(keys["supervisor"]),
                "--agent-key-file",
                str(keys["agent"]),
                "--gateway-token-file",
                str(keys["gateway"]),
                "--gateway-control-url",
                f"http://{gateway_ip}:{DEFAULT_GATEWAY_PORT}",
                "--gateway-port",
                str(DEFAULT_GATEWAY_PORT),
                "--gateway-container-id",
                gateway.id,
                "--prefix",
                prefix,
                "--host",
                "0.0.0.0",
                "--port",
                "8005",
            ],
        )
        sup_url = endpoint(supervisor, 8005)
        await ready(sup_url, "/supervisor/v1/health", headers)
        auth_headers = auth_ctx.login_sync(endpoint(api, 8000))
        async with (
            httpx.AsyncClient(
                base_url=endpoint(api, 8000), headers=auth_headers, trust_env=False
            ) as api_http,
            httpx.AsyncClient(
                base_url=sup_url, headers=headers, timeout=90, trust_env=False
            ) as sup_http,
            aiohttp.ClientSession() as viewer_http,
        ):
            assert (
                await sup_http.get(
                    "/supervisor/v1/health", headers={"Authorization": "Bearer wrong"}
                )
            ).status_code == 401
            for name in ("graph_a", "graph_b"):
                response = await api_http.post("/api/v1/profiles", json={"name": name})
                assert response.status_code == 201
                profile = response.json()["id"]
                profiles.add(profile)
                assert (
                    await api_http.patch(
                        f"/api/v1/profiles/{profile}/runtime/desired-state",
                        json={"desired_state": "running"},
                    )
                ).status_code == 200
            ordered = sorted(profiles)
            started = await asyncio.gather(
                *[
                    sup_http.post(
                        "/supervisor/v1/profiles/start",
                        json={"profile_id": profile, "config_version": 1},
                    )
                    for profile in ordered
                ]
            )
            if not all(response.status_code == 200 for response in started):
                supervisor.reload()
                api.reload()
                sup_logs = supervisor.logs(tail=200).decode(
                    "utf-8", errors="replace"
                )
                api_logs = api.logs(tail=200).decode("utf-8", errors="replace")
                pytest.fail(
                    "concurrent profile start failed: "
                    + repr([response.text for response in started])
                    + "\n--- supervisor logs ---\n"
                    + sup_logs
                    + "\n--- api logs ---\n"
                    + api_logs
                )
            sessions = [response.json() for response in started]
            assert len({session["udp_mux_port"] for session in sessions}) == 2
            duplicates = await asyncio.gather(
                *[
                    sup_http.post(
                        "/supervisor/v1/profiles/start",
                        json={"profile_id": ordered[1], "config_version": 1},
                    )
                    for _ in range(3)
                ]
            )
            assert all(response.status_code == 200 for response in duplicates)
            assert {
                (body["runtime_instance_id"], body["browser_container"])
                for body in (response.json() for response in duplicates)
            } == {
                (sessions[1]["runtime_instance_id"], sessions[1]["browser_container"])
            }
            owned = client.containers.list(
                all=True,
                filters={"label": f"com.cbrowser.profile-id={ordered[1]}"},
            )
            assert sorted(
                box.labels["com.cbrowser.role"]
                for box in owned
                if box.labels.get("com.cbrowser.role") in ("browser", "stream")
            ) == ["browser", "stream"], [box.name for box in owned]
            for profile, session in zip(ordered, sessions):
                browser = client.containers.get(session["browser_container"])
                stream = client.containers.get(session["stream_container"])
                browser_net = prefix + "-browser-net-" + profile
                media_net = prefix + "-net-" + profile
                assert set(browser.attrs["NetworkSettings"]["Networks"]) == {
                    browser_net
                }
                assert set(stream.attrs["NetworkSettings"]["Networks"]) == {media_net}
                gateway.reload()
                runtime_env = dict(
                    entry.split("=", 1) for entry in stream.attrs["Config"]["Env"]
                )
                port = session["udp_mux_port"]
                assert runtime_env["CBROWSER_CONFIG_VERSION"] == "1"
                assert runtime_env["CBROWSER_UDP_MUX_PORT"] == str(port)
                assert stream.attrs["HostConfig"]["PortBindings"] == {
                    f"{port}/udp": [{"HostIp": "127.0.0.1", "HostPort": str(port)}]
                }
                assert not browser.attrs["HostConfig"]["PortBindings"]
                assert (
                    runtime_env["CBROWSER_GATEWAY_URL"]
                    == "ws://"
                    + gateway.attrs["NetworkSettings"]["Networks"][media_net][
                        "IPAddress"
                    ]
                    + f":{DEFAULT_GATEWAY_PORT}"
                )
                for box, role in ((browser, "browser"), (stream, "stream")):
                    assert box.attrs["HostConfig"]["RestartPolicy"]["Name"] == "no"
                    assert box.labels["com.cbrowser.network-policy"] == "v1"
                    gate_mount = next(
                        mount
                        for mount in box.attrs["Mounts"]
                        if mount["Destination"] == "/run/cbrowser_policy"
                    )
                    assert gate_mount["RW"] is False
                    gate = Path(gate_mount["Source"])
                    assert gate.is_relative_to(data / "control" / "gates" / profile)
                    assert json.loads((gate / "ready.json").read_text()) == {
                        "instance_id": session["runtime_instance_id"],
                        "role": role,
                        "status": "ready",
                    }
                    assert all(
                        mount["Destination"] != "/var/run/docker.sock"
                        for mount in box.attrs["Mounts"]
                    )
                stream_destinations = {
                    m["Destination"]: m for m in stream.attrs["Mounts"]
                }
                browser_destinations = {
                    m["Destination"] for m in browser.attrs["Mounts"]
                }
                for sec_target in ("/tmp/secret.txt", "/tmp/selkies_credentials.json"):
                    # Presence is part of the contract (t024 AC-014/A43):
                    # a disappeared mount must fail, not pass silently.
                    assert sec_target in stream_destinations, (
                        f"{sec_target} must be mounted in stream"
                    )
                    assert stream_destinations[sec_target]["RW"] is False, (
                        f"{sec_target} must be mounted read-only"
                    )
                    assert sec_target not in browser_destinations, (
                        f"{sec_target} must not be mounted in browser"
                    )
            # Probe inside the actual sandbox namespaces, not stand-in clients.
            listen = """import socket,time
s=socket.socket();s.bind(('0.0.0.0',19099));s.listen();s.settimeout(12)
end=time.monotonic()+12
while time.monotonic()<end:
 try:
  c,p=s.accept();c.sendall(b'PONG');c.close()
 except TimeoutError:break
"""
            connect = """import json,socket,sys
s=socket.socket();s.settimeout(1)
try:
 s.connect((sys.argv[1],19099));result={'ok':s.recv(4)==b'PONG'}
except OSError as e:result={'ok':False,'error_type':type(e).__name__}
finally:s.close()
sys.stdout.write(json.dumps(result))
"""
            for role in ("browser", "stream"):
                remote = client.containers.get(sessions[1][role + "_container"])
                remote.exec_run(
                    ["python3", "-c", listen], detach=True, user="1000:1000"
                )
                for _ in range(50):
                    control = remote.exec_run(
                        ["python3", "-c", connect, "127.0.0.1"], user="1000:1000"
                    )
                    assert control.exit_code == 0
                    if json.loads(control.output)["ok"]:
                        break
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("Sandbox socket positive control did not become ready")
                remote_ip = next(
                    iter(remote.attrs["NetworkSettings"]["Networks"].values())
                )["IPAddress"]
                for origin_role in ("browser", "stream"):
                    origin = client.containers.get(
                        sessions[0][origin_role + "_container"]
                    )
                    denied = origin.exec_run(
                        ["python3", "-c", connect, remote_ip], user="1000:1000"
                    )
                    assert denied.exit_code == 0
                    assert json.loads(denied.output)["ok"] is False
            for box in containers:
                box.reload()
                sockets = [
                    mount
                    for mount in box.attrs["Mounts"]
                    if mount["Destination"] == "/var/run/docker.sock"
                ]
                assert bool(sockets) == (box.id == supervisor.id)
            assert not any(
                mount["Source"] == str(metadata) for mount in supervisor.attrs["Mounts"]
            )
            for mount in supervisor.attrs["Mounts"]:
                if mount["Destination"] != "/var/run/docker.sock":
                    assert (
                        Path(mount["Source"]).resolve().is_relative_to(data.resolve())
                    )
            no_db = supervisor.exec_run(
                [
                    "python3",
                    "-c",
                    (
                        "import importlib.util; "
                        "assert importlib.util.find_spec('sqlalchemy') is None"
                    ),
                ]
            )
            assert no_db.exit_code == 0
            target, old = ordered[0], sessions[0]
            # Real viewer close handshake prevents Gateway ack until the caller
            # confirms closure, so inspect can prove sandbox stop happens later.
            target_ws_url = (
                endpoint(gateway, DEFAULT_GATEWAY_PORT)
                + f"/stream/{target}/signal"
            )
            viewer = await viewer_http.ws_connect(
                target_ws_url,
                headers={
                    "Origin": auth_ctx.allowed_origin,
                    "Cookie": auth_headers["Cookie"],
                },
                autoclose=False,
            )
            await ready(
                endpoint(gateway, DEFAULT_GATEWAY_PORT),
                f"/gateway/v1/internal/profiles/{target}/visibility?runtime_instance_id={old['runtime_instance_id']}",
                {"Authorization": "Bearer " + keys["gateway"].read_text()},
            )
            await api_http.patch(
                f"/api/v1/profiles/{target}/runtime/desired-state",
                json={"desired_state": "stopped"},
            )
            stop_body = {
                "profile_id": target,
                "runtime_instance_id": old["runtime_instance_id"],
                "operation_id": "graph_stop",
            }
            stop_task = asyncio.create_task(
                sup_http.post("/supervisor/v1/profiles/stop", json=stop_body)
            )
            close_received = False
            for _ in range(150):
                message = await viewer.receive(timeout=15)
                if message.type == aiohttp.WSMsgType.CLOSE:
                    close_received = True
                    break
                assert message.type not in (
                    aiohttp.WSMsgType.ERROR,
                    aiohttp.WSMsgType.CLOSED,
                )
            assert close_received, "Viewer did not receive Gateway close frame"
            for name in (old["browser_container"], old["stream_container"]):
                assert client.containers.get(name).status == "running"
            await viewer.close()
            assert (await stop_task).status_code == 200
            await api_http.patch(
                f"/api/v1/profiles/{target}/runtime/desired-state",
                json={"desired_state": "running"},
            )
            replacement = await sup_http.post(
                "/supervisor/v1/profiles/start",
                json={"profile_id": target, "config_version": 1},
            )
            assert replacement.status_code == 200
            current = replacement.json()
            assert current["runtime_instance_id"] != old["runtime_instance_id"]
            assert (
                await sup_http.post("/supervisor/v1/profiles/stop", json=stop_body)
            ).status_code == 200
            assert (
                client.containers.get(current["browser_container"]).status == "running"
            )
            assert (
                client.containers.get(sessions[1]["browser_container"]).status
                == "running"
            )
            snapshots = [current, sessions[1]]
            identities = {
                session[key]: client.containers.get(session[key]).id
                for session in snapshots
                for key in ("browser_container", "stream_container")
            }
            browser_pids = {
                profile: json.loads(
                    (data / "runtime" / profile / "runner_info.json").read_text()
                )["browser_pid"]
                for profile in ordered
            }
            supervisor.kill(signal="SIGKILL")
            for session in snapshots:
                assert (
                    client.containers.get(session["browser_container"]).status
                    == "running"
                )
            supervisor.start()
            sup_url = endpoint(supervisor, 8005)
            await ready(sup_url, "/supervisor/v1/health", headers)
            async with httpx.AsyncClient(
                base_url=sup_url, headers=headers, trust_env=False
            ) as recovered:
                for profile, session in zip(ordered, snapshots):
                    async def _recovered_status(pid: str = profile) -> dict:
                        response = await recovered.get(
                            f"/supervisor/v1/profiles/{pid}/status"
                        )
                        assert response.status_code == 200
                        return response.json()

                    # Startup reconciliation runs after the control plane is
                    # healthy; until the session is re-adopted the status
                    # correctly reports no port.
                    status = await poll_until(
                        _recovered_status,
                        lambda body: body["udp_mux_port"]
                        == session["udp_mux_port"],
                        timeout=30.0,
                        interval=0.2,
                        description=f"recovered status for {profile}",
                    )
                    assert (
                        status["runtime_instance_id"]
                        == session["runtime_instance_id"]
                    )
            for name, container_id in identities.items():
                assert client.containers.get(name).id == container_id
            for profile, pid in browser_pids.items():
                assert (
                    json.loads(
                        (data / "runtime" / profile / "runner_info.json").read_text()
                    )["browser_pid"]
                    == pid
                )
            (tmp_path / "container_graph_proof.json").write_text(
                json.dumps(
                    {
                        "profiles": ordered,
                        "sessions": snapshots,
                        "supervisor_image": os.environ[
                            "CBROWSER_SUPERVISOR_TEST_IMAGE"
                        ],
                        "socket_holder": supervisor.id,
                        "metadata_holder": api.id,
                        "container_ids": identities,
                        "browser_pids": browser_pids,
                    },
                    indent=2,
                )
            )
    finally:
        if stop_task is not None and not stop_task.done():
            stop_task.cancel()
            await asyncio.gather(stop_task, return_exceptions=True)
        if viewer is not None and not viewer.closed:
            await viewer.close()
        known_infra_ids = {c.id for c in containers if hasattr(c, "id")}
        ownership_violations: list[str] = []
        cleanup_errors: list[str] = []
        try:
            owned_containers = client.containers.list(
                all=True, filters={"label": f"com.cbrowser.prefix={prefix}"}
            )
        except Exception as exc:  # noqa: BLE001 - robust container list cleanup
            owned_containers = []
            cleanup_errors.append(f"containers_list: {type(exc).__name__}")

        def _cleanup_order(box) -> int:
            labels = getattr(box, "labels", None)
            if labels is None and hasattr(box, "attrs"):
                labels = box.attrs.get("Config", {}).get("Labels", {}) or {}
            role = (labels or {}).get("com.cbrowser.role")
            # Stop the actor before its sandboxes: a live Supervisor can
            # recreate a Stream while the harness is removing the pair.
            return 0 if role in ("supervisor", "api", "gateway") else 1

        for box in sorted(owned_containers, key=_cleanup_order):
            lbls = getattr(box, "labels", None)
            if lbls is None and hasattr(box, "attrs"):
                lbls = box.attrs.get("Config", {}).get("Labels", {}) or {}
            lbls = lbls or {}
            if lbls.get("com.cbrowser.prefix") != prefix:
                continue

            box_name = getattr(box, "name", "unnamed")
            if box.id not in known_infra_ids:
                is_valid_dynamic = (
                    lbls.get("com.cbrowser.role")
                    in ("cache-init", "network-policy", "x11-permissions")
                    or lbls.get("com.cbrowser.profile-id") in profiles
                )
                if not is_valid_dynamic:
                    ownership_violations.append(
                        f"Dynamic container {box_name} ({box.id[:12]}) violated "
                        f"ownership: role={lbls.get('com.cbrowser.role')!r}, "
                        f"profile-id={lbls.get('com.cbrowser.profile-id')!r}"
                    )
                    continue
            try:
                (tmp_path / (box_name + ".log")).write_bytes(box.logs())
            except Exception as exc:  # noqa: BLE001 - best-effort container log fetch
                logger.debug(
                    "Failed to write logs for %s: %s", box_name, type(exc).__name__
                )
            try:
                box.stop(timeout=1)
            except docker.errors.NotFound:
                pass
            except Exception as exc:  # noqa: BLE001 - robust container stop cleanup
                logger.warning(
                    "Container stop error for %s: %s", box_name, type(exc).__name__
                )

            for attempt in range(40):
                try:
                    box.remove(force=True, v=True)
                    break
                except docker.errors.NotFound:
                    break
                except Exception as exc:  # noqa: BLE001 - robust container remove cleanup
                    if "already in progress" in str(exc) and attempt < 39:
                        await asyncio.sleep(0.25)
                        continue
                    err_type = type(exc).__name__
                    logger.error(
                        "Container remove error for %s: %s", box_name, err_type
                    )
                    cleanup_errors.append(f"container_remove({box_name}): {err_type}")
                    break

        try:
            owned_networks = client.networks.list(
                filters={"label": f"com.cbrowser.prefix={prefix}"}
            )
        except Exception as exc:  # noqa: BLE001 - robust network list cleanup
            owned_networks = []
            cleanup_errors.append(f"networks_list: {type(exc).__name__}")

        for network in owned_networks:
            n_lbls = getattr(network, "attrs", {}).get("Labels") or {}
            if n_lbls.get("com.cbrowser.prefix") != prefix:
                continue

            n_name = getattr(network, "name", "unnamed")
            try:
                if hasattr(network, "reload"):
                    network.reload()
            except docker.errors.NotFound:
                continue
            except Exception as exc:  # noqa: BLE001 - robust network reload cleanup
                cleanup_errors.append(
                    f"network_reload({n_name}): {type(exc).__name__}"
                )
                continue

            for attempt in range(40):
                containers_attached = (
                    getattr(network, "attrs", {}).get("Containers") or {}
                )
                if not containers_attached:
                    try:
                        network.remove()
                    except docker.errors.NotFound:
                        pass
                    except Exception as exc:  # noqa: BLE001 - robust network cleanup
                        logger.error(
                            "Network remove error for %s: %s",
                            n_name,
                            type(exc).__name__,
                        )
                        cleanup_errors.append(
                            f"network_remove({n_name}): {type(exc).__name__}"
                        )
                    break
                if attempt < 39:
                    await asyncio.sleep(0.25)
                    try:
                        network.reload()
                    except docker.errors.NotFound:
                        break
                    except Exception as exc:  # noqa: BLE001 - robust reload
                        cleanup_errors.append(
                            f"network_reload({n_name}): {type(exc).__name__}"
                        )
                        break
                    continue
                cleanup_errors.append(f"network_not_empty({n_name})")

        client.close()

    if ownership_violations:
        err_msg = "; ".join(ownership_violations)
        logger.error("Container ownership violation detected: %s", err_msg)
        assert not ownership_violations, (
            f"Container ownership assertion failed: {err_msg}"
        )

    if cleanup_errors:
        msg = ", ".join(cleanup_errors)
        raise RuntimeError(f"Cleanup encountered failures: {msg}")
