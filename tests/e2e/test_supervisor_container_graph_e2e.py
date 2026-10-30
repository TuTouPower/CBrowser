"""Run the actual Supervisor, API and sandbox topology as isolated containers."""

import asyncio
import json
import os
import secrets
import shutil
import uuid
from pathlib import Path

import aiohttp
import docker
import httpx
import pytest


def endpoint(container, port):
    container.reload()
    assert container.status == "running", f"Container startup failed: {container.name}"
    binding = container.attrs["NetworkSettings"]["Ports"][f"{port}/tcp"][0]
    return f"http://127.0.0.1:{binding['HostPort']}"


async def ready(url, path, headers=None):
    async with httpx.AsyncClient(base_url=url, trust_env=False) as client:
        deadline = asyncio.get_running_loop().time() + 30
        while asyncio.get_running_loop().time() < deadline:
            try:
                response = await client.get(path, headers=headers)
                if response.status_code == 200:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.2)
    raise AssertionError("Container HTTP service did not become ready")


@pytest.mark.asyncio
async def test_supervisor_container_rpc_socket_and_instance_fenced_lifecycle(tmp_path):
    client = docker.from_env()
    prefix = "t005-graph-" + uuid.uuid4().hex[:10]
    containers = []
    profiles = set()
    data = tmp_path / "data"
    control = data / "control"
    control.mkdir(parents=True)
    control.chmod(0o777)
    for name in ("profiles", "runtime", "runtime-events", "artifacts", "spool"):
        (data / name).mkdir()
        (data / name).chmod(0o777)
    cache = data / "engine_cache"
    shutil.copytree(os.environ["CBROWSER_RUNTIME_ENGINE_CACHE"], cache)
    shutil.copytree(
        os.environ["CBROWSER_RUNTIME_GEOIP_CACHE"], cache / "geoip", dirs_exist_ok=True
    )
    keys = {}
    for name in ("supervisor", "agent", "gateway"):
        key = control / (name + "_key")
        key.write_text(secrets.token_urlsafe(32))
        key.chmod(0o644)
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
        api = run(
            "api",
            image("CBROWSER_API_TEST_IMAGE"),
            environment={
                "CBROWSER_DB_PATH": "/metadata/control.db",
                "CBROWSER_SUPERVISOR_TOKEN_FILE": "/run/secrets/key",
            },
            volumes={
                str(metadata): {"bind": "/metadata", "mode": "rw"},
                str(keys["supervisor"]): {"bind": "/run/secrets/key", "mode": "ro"},
            },
            ports={"8000/tcp": ("127.0.0.1", None)},
        )
        gateway = run(
            "gateway",
            image("CBROWSER_GATEWAY_TEST_IMAGE"),
            environment={
                "PROBE_AGENT_KEY_FILE": "/run/secrets/agent",
                "PROBE_GATEWAY_KEY_FILE": "/run/secrets/gateway",
            },
            volumes={
                str(keys["agent"]): {"bind": "/run/secrets/agent", "mode": "ro"},
                str(keys["gateway"]): {"bind": "/run/secrets/gateway", "mode": "ro"},
            },
            ports={"18097/tcp": ("127.0.0.1", None)},
        )
        turn_config = control / "turn.conf"
        turn_config.write_text(
            "listening-port=3478\nrealm=cbrowser.local\nuse-auth-secret\n"
            "no-cli\nno-tls\nno-dtls\n"
            "static-auth-secret=" + secrets.token_hex(32) + "\n"
        )
        turn_config.chmod(0o644)
        coturn = run(
            "coturn",
            image("CBROWSER_TURN_TEST_IMAGE"),
            cap_add=["NET_BIND_SERVICE"],
            entrypoint="/usr/bin/turnserver",
            command=[
                "-c",
                "/etc/turnserver.conf",
                "--relay-threads=1",
                "--log-file=stdout",
            ],
            volumes={str(turn_config): {"bind": "/etc/turnserver.conf", "mode": "ro"}},
        )
        await ready(endpoint(api, 8000), "/api/v1/health")
        await ready(endpoint(gateway, 18097), "/healthz")
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
            )
        }
        mounts["/var/run/docker.sock"] = {"bind": "/var/run/docker.sock", "mode": "ro"}
        supervisor = run(
            "supervisor",
            image("CBROWSER_SUPERVISOR_TEST_IMAGE"),
            cap_add=["FOWNER", "DAC_OVERRIDE"],
            environment={
                "CBROWSER_BROWSER_IMAGE": image("CBROWSER_RUNTIME_TEST_IMAGE"),
                "CBROWSER_STREAM_IMAGE": image("CBROWSER_STREAM_TEST_IMAGE"),
                "CBROWSER_NETWORK_POLICY_IMAGE": image(
                    "CBROWSER_SUPERVISOR_TEST_IMAGE"
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
                f"http://{gateway_ip}:18097",
                "--gateway-container-id",
                gateway.id,
                "--coturn-container-id",
                coturn.id,
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
        async with (
            httpx.AsyncClient(
                base_url=endpoint(api, 8000), trust_env=False
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
            assert all(response.status_code == 200 for response in started), [
                response.text for response in started
            ]
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
                coturn.reload()
                runtime_env = dict(
                    entry.split("=", 1) for entry in stream.attrs["Config"]["Env"]
                )
                port = session["udp_mux_port"]
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
                    + ":18097"
                )
                assert (
                    runtime_env["SELKIES_STUN_HOST"]
                    == coturn.attrs["NetworkSettings"]["Networks"][media_net][
                        "IPAddress"
                    ]
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
            viewer = await viewer_http.ws_connect(
                endpoint(gateway, 18097) + f"/viewer/{target}?foreground=true",
                autoclose=False,
            )
            await ready(
                endpoint(gateway, 18097),
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
            assert (await viewer.receive(timeout=15)).type == aiohttp.WSMsgType.CLOSE
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
                    response = await recovered.get(
                        f"/supervisor/v1/profiles/{profile}/status"
                    )
                    assert response.status_code == 200
                    assert (
                        response.json()["runtime_instance_id"]
                        == session["runtime_instance_id"]
                    )
                    assert response.json()["udp_mux_port"] == session["udp_mux_port"]
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
        for box in reversed(containers):
            try:
                (tmp_path / (box.name + ".log")).write_bytes(box.logs())
                box.remove(force=True)
            except docker.errors.NotFound:
                pass
        for box in client.containers.list(
            all=True, filters={"label": f"com.cbrowser.prefix={prefix}"}
        ):
            labels = box.labels
            assert (
                labels.get("com.cbrowser.role") == "cache-init"
                or labels.get("com.cbrowser.profile-id") in profiles
            )
            (tmp_path / (box.name + ".log")).write_bytes(box.logs())
            box.remove(force=True)
        for network in client.networks.list(
            filters={"label": f"com.cbrowser.prefix={prefix}"}
        ):
            network.remove()
        client.close()
