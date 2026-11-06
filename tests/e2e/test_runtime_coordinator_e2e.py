"""Real Docker E2E test for AC-009 Runtime Coordinator.

Tests:
1. API process + Supervisor container + Gateway.
2. Setting running intent via API causes Browser & Stream to appear.
3. Setting stopped intent via API causes Browser & Stream to disappear.
4. Outage of Supervisor preserves intent, which converges upon recovery.
5. All Docker resources use prefix 't007-be-coord' and are cleaned up in finally.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import shutil
import socket
import uuid
from pathlib import Path

import docker
import httpx
import pytest

from e2e_env import require_e2e_env
from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT
from wait import poll_until, wait_until

from api_auth import create_auth_context

pytestmark = pytest.mark.serial

logger = logging.getLogger("cbrowser.test_runtime_coordinator_e2e")


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def wait_until_ready(
    url: str,
    path: str,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    expected_status: int = 200,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    async with httpx.AsyncClient(base_url=url, trust_env=False) as client:
        while asyncio.get_running_loop().time() < deadline:
            try:
                resp = await client.get(path, headers=headers)
                if resp.status_code == expected_status:
                    return
            except (httpx.TransportError, httpx.HTTPError):
                pass
            await asyncio.sleep(0.3)
    raise TimeoutError(f"Service at {url}{path} did not become ready within {timeout}s")


@pytest.mark.asyncio
async def test_runtime_coordinator_docker_e2e(tmp_path: Path):
    client = docker.from_env()
    prefix = f"t007-be-coord-{uuid.uuid4().hex[:6]}"
    containers: list[docker.models.containers.Container] = []
    networks: list[docker.models.networks.Network] = []

    data = tmp_path / "data"
    control = data / "control"
    control.mkdir(parents=True)
    control.chmod(0o700)
    for name in ("profiles", "runtime", "runtime-events", "artifacts", "spool"):
        d = data / name
        d.mkdir()
        d.chmod(0o777)

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
    cache = data / "engine_cache"
    shutil.copytree(os.environ["CBROWSER_RUNTIME_ENGINE_CACHE"], cache)
    shutil.copytree(
        os.environ["CBROWSER_RUNTIME_GEOIP_CACHE"],
        cache / "geoip",
        dirs_exist_ok=True,
    )

    keys = {}
    for name in ("supervisor", "agent", "gateway", "gateway_api"):
        k = control / f"{name}_key"
        k.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        k.chmod(0o600)
        keys[name] = k

    sup_headers = {"Authorization": f"Bearer {keys['supervisor'].read_text().strip()}"}

    def image(name: str) -> str:
        val = os.environ[name]
        assert val.startswith("sha256:")
        return val

    supervisor_host_port = find_free_port()
    api_host_port = find_free_port()

    edge_network = None
    server_task = None

    try:
        # 1. Edge network
        edge_network = client.networks.create(
            f"{prefix}-edge",
            labels={"com.cbrowser.prefix": prefix},
        )
        networks.append(edge_network)

        # 3. Gateway container
        gateway = client.containers.run(
            image("CBROWSER_GATEWAY_IMAGE"),
            name=f"{prefix}-gateway",
            detach=True,
            read_only=True,
            network=edge_network.name,
            tmpfs={"/tmp": "rw,size=256m"},
            environment={
                "CBROWSER_AGENT_KEY_FILE": "/run/secrets/agent",
                "CBROWSER_GATEWAY_TOKEN_FILE": "/run/secrets/gateway",
                "CBROWSER_GATEWAY_API_URL": (
                    f"http://host.docker.internal:{api_host_port}"
                ),
                "CBROWSER_GATEWAY_API_TOKEN_FILE": "/run/secrets/gateway_api",
                "CBROWSER_ALLOWED_ORIGINS": f"http://127.0.0.1:{api_host_port}",
            },
            volumes={
                str(keys["agent"]): {"bind": "/run/secrets/agent", "mode": "ro"},
                str(keys["gateway"]): {
                    "bind": "/run/secrets/gateway",
                    "mode": "ro",
                },
                str(keys["gateway_api"]): {
                    "bind": "/run/secrets/gateway_api",
                    "mode": "ro",
                },
            },
            ports={f"{DEFAULT_GATEWAY_PORT}/tcp": ("127.0.0.1", None)},
            labels={
                "com.cbrowser.prefix": prefix,
                "com.cbrowser.managed-by": "supervisor",
                "com.cbrowser.role": "gateway",
            },
        )
        containers.append(gateway)
        gateway.reload()
        gw_ports = gateway.attrs["NetworkSettings"]["Ports"]
        gw_port = gw_ports[f"{DEFAULT_GATEWAY_PORT}/tcp"][0]["HostPort"]
        await wait_until_ready(
            f"http://127.0.0.1:{gw_port}",
            "/stream/agent/register",
            timeout=30.0,
            expected_status=401,
        )
        gateway_ip = gateway.attrs["NetworkSettings"]["Networks"][edge_network.name][
            "IPAddress"
        ]

        # 4. API uvicorn process
        origin = f"http://127.0.0.1:{api_host_port}"
        auth_ctx = create_auth_context(control, origin=origin)
        api_db_path = data / "api_control.db"

        import uvicorn
        from cbrowser.api.app import create_app

        api_app = create_app(
            db_path=api_db_path,
            supervisor_token_file=keys["supervisor"],
            gateway_token_file=keys["gateway_api"],
            admin_password_file=auth_ctx.admin_password_file,
            allowed_origins=auth_ctx.allowed_origin,
            supervisor_url=f"http://127.0.0.1:{supervisor_host_port}",
        )

        uv_config = uvicorn.Config(
            api_app,
            host="127.0.0.1",
            port=api_host_port,
            log_level="warning",
            timeout_graceful_shutdown=5,
        )
        uv_server = uvicorn.Server(uv_config)
        server_task = asyncio.create_task(uv_server.serve())

        api_base_url = f"http://127.0.0.1:{api_host_port}"
        await wait_until_ready(api_base_url, "/api/v1/health", timeout=30.0)

        # 5. Supervisor container
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
        mounts["/var/run/docker.sock"] = {
            "bind": "/var/run/docker.sock",
            "mode": "ro",
        }

        supervisor = client.containers.run(
            image("CBROWSER_SUPERVISOR_TEST_IMAGE"),
            name=f"{prefix}-supervisor",
            detach=True,
            network=edge_network.name,
            cap_add=["FOWNER", "DAC_OVERRIDE"],
            tmpfs={"/tmp": "rw,size=256m"},
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
            ports={"8005/tcp": ("127.0.0.1", supervisor_host_port)},
            command=[
                "--api-url",
                f"http://host.docker.internal:{api_host_port}",
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
            labels={
                "com.cbrowser.prefix": prefix,
                "com.cbrowser.managed-by": "supervisor",
                "com.cbrowser.role": "supervisor",
            },
        )
        containers.append(supervisor)
        await wait_until_ready(
            f"http://127.0.0.1:{supervisor_host_port}",
            "/supervisor/v1/health",
            headers=sup_headers,
            timeout=30.0,
        )

        # 6. Execute E2E Coordination via API
        async with httpx.AsyncClient(
            base_url=api_base_url, timeout=30.0, trust_env=False
        ) as api_client:
            # Login
            auth_headers = await auth_ctx.login_async(api_base_url, client=api_client)

            # Create profile
            create_resp = await api_client.post(
                "/api/v1/profiles",
                json={"name": "e2e_coord_prof"},
                headers=auth_headers,
            )
            assert create_resp.status_code == 201
            profile_id = create_resp.json()["id"]

            # A. Set running intent via API
            patch_resp = await api_client.patch(
                f"/api/v1/profiles/{profile_id}/runtime/desired-state",
                json={"desired_state": "running"},
                headers=auth_headers,
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["desired_state"] == "running"

            # Wait for Browser and Stream containers to actually appear in Docker
            browser_c_name = f"{prefix}-browser-{profile_id}"
            stream_c_name = f"{prefix}-stream-{profile_id}"

            def active_names() -> list[str]:
                return [c.name for c in client.containers.list()]

            try:
                await wait_until(
                    lambda: browser_c_name in active_names()
                    and stream_c_name in active_names(),
                    timeout=180.0,
                    interval=0.5,
                    description=f"containers {browser_c_name} and {stream_c_name}",
                )
            except TimeoutError:
                for c in client.containers.list(all=True, filters={"name": prefix}):
                    logger.error(
                        "Container %s (%s) logs:\n%s",
                        c.name,
                        c.status,
                        c.logs().decode(errors="replace")[-2000:],
                    )
                raise

            # Verify API runtime status reports running
            async def get_runtime() -> dict:
                response = await api_client.get(
                    f"/api/v1/profiles/{profile_id}/runtime",
                    headers=auth_headers,
                )
                return response.json()

            rt = await poll_until(
                get_runtime,
                lambda value: value["observed_state"] == "running"
                and value["runtime_instance_id"] is not None,
                timeout=15.0,
                interval=0.3,
                description="API observed_state=running",
            )
            assert rt["desired_state"] == "running"
            assert rt["last_coordinator_error"] is None

            # B. Stop the profile via API
            stop_resp = await api_client.post(
                f"/api/v1/profiles/{profile_id}/stop",
                headers=auth_headers,
            )
            assert stop_resp.status_code == 200
            assert stop_resp.json()["desired_state"] == "stopped"

            # Wait for Browser and Stream containers to disappear
            await wait_until(
                lambda: browser_c_name not in active_names()
                and stream_c_name not in active_names(),
                timeout=60.0,
                interval=0.5,
                description="runtime containers terminated after stop",
            )

            # Verify API reports stopped
            rt_stopped = await poll_until(
                get_runtime,
                lambda value: value["observed_state"] == "stopped",
                timeout=15.0,
                interval=0.3,
                description="API observed_state=stopped",
            )
            assert rt_stopped["desired_state"] == "stopped"

            # C. Simulate Supervisor outage: stop supervisor container
            supervisor.stop(timeout=5)

            # Set running intent while Supervisor is down
            patch_down = await api_client.patch(
                f"/api/v1/profiles/{profile_id}/runtime/desired-state",
                json={"desired_state": "running"},
                headers=auth_headers,
            )
            assert patch_down.status_code == 200
            assert patch_down.json()["desired_state"] == "running"

            # Coordinator sets last_coordinator_error
            rt_err = await poll_until(
                get_runtime,
                lambda value: bool(value["last_coordinator_error"]),
                timeout=8.0,
                interval=0.2,
                description="coordinator error during supervisor outage",
            )
            assert rt_err["desired_state"] == "running"

            # D. Restore Supervisor container
            supervisor.start()
            await wait_until_ready(
                f"http://127.0.0.1:{supervisor_host_port}",
                "/supervisor/v1/health",
                headers=sup_headers,
                timeout=30.0,
            )

            # Wait for coordinator to converge automatically upon recovery
            await poll_until(
                get_runtime,
                lambda value: value["observed_state"] == "running"
                and value["last_coordinator_error"] is None,
                timeout=120.0,
                interval=0.5,
                description="coordinator convergence after supervisor restart",
            )

            # Cleanup: stop the running profile and wait for the Supervisor
            # to finish removing its containers before the harness removes
            # them too (a concurrent removal returns Docker 409).
            await api_client.post(
                f"/api/v1/profiles/{profile_id}/stop", headers=auth_headers
            )
            await wait_until(
                lambda: browser_c_name not in active_names()
                and stream_c_name not in active_names(),
                timeout=60.0,
                interval=0.5,
                description="runtime containers removed after final stop",
            )

    finally:
        if server_task:
            uv_server.should_exit = True
            # The Supervisor can hold a long-lived SSE/control connection
            # across its restart; uvicorn's graceful wait would never
            # return. Force the configured shutdown bound, then cancel.
            try:
                await asyncio.wait_for(server_task, timeout=10.0)
            except (TimeoutError, asyncio.TimeoutError):
                server_task.cancel()
                await asyncio.gather(server_task, return_exceptions=True)

        cleanup_errors: list[str] = []
        # Cleanup all containers strictly labeled with this prefix
        try:
            owned_containers = client.containers.list(
                all=True, filters={"label": f"com.cbrowser.prefix={prefix}"}
            )
        except Exception as exc:  # noqa: BLE001 - robust container query cleanup
            owned_containers = []
            cleanup_errors.append(f"containers_list: {type(exc).__name__}")

        def _cleanup_order(box) -> int:
            labels = getattr(box, "labels", None)
            if labels is None and hasattr(box, "attrs"):
                labels = box.attrs.get("Config", {}).get("Labels", {}) or {}
            role = (labels or {}).get("com.cbrowser.role")
            return 0 if role in ("supervisor", "api", "gateway") else 1

        for c in sorted(owned_containers, key=_cleanup_order):
            lbls = getattr(c, "labels", None)
            if lbls is None and hasattr(c, "attrs"):
                lbls = c.attrs.get("Config", {}).get("Labels", {}) or {}
            lbls = lbls or {}
            if lbls.get("com.cbrowser.prefix") != prefix:
                continue

            c_name = getattr(c, "name", "unnamed")
            try:
                c.stop(timeout=1)
            except docker.errors.NotFound:
                pass
            except Exception as exc:  # noqa: BLE001 - robust container stop cleanup
                logger.warning(
                    "Container stop error for %s: %s", c_name, type(exc).__name__
                )

            for attempt in range(40):
                try:
                    c.remove(force=True, v=True)
                    break
                except docker.errors.NotFound:
                    break
                except Exception as exc:  # noqa: BLE001 - robust container remove cleanup
                    if "already in progress" in str(exc) and attempt < 39:
                        await asyncio.sleep(0.25)
                        continue
                    err_t = type(exc).__name__
                    logger.error("Container remove error for %s: %s", c_name, err_t)
                    cleanup_errors.append(f"container_remove({c_name}): {err_t}")
                    break

        # Cleanup networks strictly labeled with this prefix
        try:
            owned_networks = client.networks.list(
                filters={"label": f"com.cbrowser.prefix={prefix}"}
            )
        except Exception as exc:  # noqa: BLE001 - robust network query cleanup
            owned_networks = []
            cleanup_errors.append(f"networks_list: {type(exc).__name__}")

        for net in owned_networks:
            n_lbls = getattr(net, "attrs", {}).get("Labels") or {}
            if n_lbls.get("com.cbrowser.prefix") != prefix:
                continue

            n_name = getattr(net, "name", "unnamed")
            try:
                if hasattr(net, "reload"):
                    net.reload()
            except docker.errors.NotFound:
                continue
            except Exception as exc:  # noqa: BLE001 - robust network reload cleanup
                cleanup_errors.append(
                    f"network_reload({n_name}): {type(exc).__name__}"
                )
                continue

            for attempt in range(40):
                containers_attached = (
                    getattr(net, "attrs", {}).get("Containers") or {}
                )
                if not containers_attached:
                    try:
                        net.remove()
                    except docker.errors.NotFound:
                        pass
                    except Exception as exc:  # noqa: BLE001 - robust network cleanup
                        err_t = type(exc).__name__
                        logger.error("Network remove error for %s: %s", n_name, err_t)
                        cleanup_errors.append(f"network_remove({n_name}): {err_t}")
                    break
                if attempt < 39:
                    await asyncio.sleep(0.25)
                    try:
                        net.reload()
                    except docker.errors.NotFound:
                        break
                    except Exception as exc:  # noqa: BLE001 - robust network reload
                        cleanup_errors.append(
                            f"network_reload({n_name}): {type(exc).__name__}"
                        )
                        break
                    continue
                cleanup_errors.append(f"network_not_empty({n_name})")


    if cleanup_errors:
        msg = ", ".join(cleanup_errors)
        raise RuntimeError(f"Cleanup encountered failures: {msg}")
