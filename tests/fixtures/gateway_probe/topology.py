"""Real Docker container graph topology for Gateway, API, Supervisor and Caddy."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import shutil
import socket
import uuid
from pathlib import Path
from typing import Any

import docker
import httpx
from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT

from .caddyfile import generate_caddyfile
from .selkies_assets import prepare_selkies_web_assets

logger = logging.getLogger("cbrowser.gateway_probe.topology")


def find_free_port(start: int = 34800, end: int = 35999) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def wait_until_ready(
    url: str,
    path: str,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    verify: bool = True,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    async with httpx.AsyncClient(
        base_url=url, verify=verify, trust_env=False
    ) as client:
        while asyncio.get_running_loop().time() < deadline:
            try:
                resp = await client.get(path, headers=headers)
                if resp.status_code == 200:
                    return
            except (httpx.TransportError, httpx.HTTPError):
                pass
            await asyncio.sleep(0.2)
    raise TimeoutError(f"Service at {url}{path} not ready within {timeout}s")


class GatewayTopologyHarness:
    """Manages the real Docker container topology for Gateway E2E tests."""

    def __init__(
        self,
        work_dir: Path,
        agent_heartbeat_timeout_sec: float = 30.0,
    ) -> None:
        self.work_dir = work_dir
        self.agent_heartbeat_timeout_sec = agent_heartbeat_timeout_sec

        self.docker_client = docker.from_env()
        self.prefix = f"t006-relay-{uuid.uuid4().hex[:8]}"

        self.containers: list[docker.models.containers.Container] = []
        self.networks: list[docker.models.networks.Network] = []

        self.browser_image = self._get_image("CBROWSER_RUNTIME_TEST_IMAGE")
        self.stream_image = self._get_image("CBROWSER_STREAM_TEST_IMAGE")
        self.gateway_image = self._get_image("CBROWSER_GATEWAY_IMAGE")
        self.supervisor_image = self._get_image("CBROWSER_SUPERVISOR_TEST_IMAGE")
        self.api_image = self._get_image("CBROWSER_API_TEST_IMAGE")
        self.caddy_image = os.environ.get(
            "CBROWSER_CADDY_TEST_IMAGE",
            "sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b",
        )
        assert self.caddy_image.startswith("sha256:")

        self.engine_cache_src = Path(os.environ["CBROWSER_RUNTIME_ENGINE_CACHE"])
        self.geoip_cache_src = Path(os.environ["CBROWSER_RUNTIME_GEOIP_CACHE"])

        self.caddy_host_port = find_free_port(35000, 35999)
        self.origin = f"https://127.0.0.1:{self.caddy_host_port}"

        self.data_dir = self.work_dir / "data"
        self.control_dir = self.data_dir / "control"
        self.metadata_dir = self.work_dir / "api_metadata"
        self.static_dir = self.work_dir / "static"

        self.keys: dict[str, str] = {}
        self.key_files: dict[str, Path] = {}
        self.admin_password = secrets.token_urlsafe(32)

        self.edge_network: docker.models.networks.Network | None = None
        self.api_container: docker.models.containers.Container | None = None
        self.gateway_container: docker.models.containers.Container | None = None
        self.supervisor_container: docker.models.containers.Container | None = None
        self.caddy_container: docker.models.containers.Container | None = None

        self.api_ip: str = ""
        self.gateway_ip: str = ""
        self.supervisor_url: str = ""
        self.api_internal_url: str = ""

    def _get_image(self, var_name: str) -> str:
        val = os.environ.get(var_name)
        assert val and val.startswith("sha256:"), (
            f"Missing or invalid immutable image ID in {var_name}"
        )
        return val

    def prepare_static(self) -> None:
        """Prepares the Caddy static root; subclasses may replace this."""
        prepare_selkies_web_assets(self.stream_image, self.static_dir)

    def api_environment_extra(self) -> dict[str, str]:
        """Extra environment variables for the API container."""
        return {}

    def _init_dirs_and_secrets(self) -> None:
        self.control_dir.mkdir(parents=True, exist_ok=True)
        self.control_dir.chmod(0o777)
        for name in ("profiles", "runtime", "runtime-events", "artifacts", "spool"):
            d = self.data_dir / name
            d.mkdir(parents=True, exist_ok=True)
            d.chmod(0o777)

        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.chmod(0o777)

        cache = self.data_dir / "engine_cache"
        if not cache.exists():
            shutil.copytree(self.engine_cache_src, cache)
            shutil.copytree(self.geoip_cache_src, cache / "geoip", dirs_exist_ok=True)

        for name in ("supervisor", "agent", "gateway", "gateway_api"):
            val = secrets.token_urlsafe(32)
            f = self.control_dir / f"{name}_key"
            f.write_text(val, encoding="utf-8")
            f.chmod(0o600)
            self.keys[name] = val
            self.key_files[name] = f

        pwd_file = self.control_dir / "admin_password"
        pwd_file.write_text(self.admin_password, encoding="utf-8")
        pwd_file.chmod(0o600)
        self.key_files["admin_password"] = pwd_file

    def _run_container(
        self, role: str, image_id: str, **kwargs
    ) -> docker.models.containers.Container:
        labels = kwargs.pop("labels", {})
        labels.update(
            {
                "com.cbrowser.prefix": self.prefix,
                "com.cbrowser.test": "t006-relay",
                "com.cbrowser.role": role,
            }
        )
        # Gateway requires managed-by=supervisor for infra validation
        if role == "gateway":
            labels["com.cbrowser.managed-by"] = "supervisor"
        container = self.docker_client.containers.run(
            image_id,
            name=f"{self.prefix}-{role}",
            detach=True,
            network=self.edge_network.name,
            labels=labels,
            **kwargs,
        )
        self.containers.append(container)
        return container

    async def start(self) -> None:
        try:
            await self._do_start()
        except BaseException as start_exc:
            logger.error(
                "GatewayTopologyHarness.start failed: %s; cleaning up topology",
                type(start_exc).__name__,
            )
            try:
                await self.cleanup()
            except BaseException as cleanup_exc:
                logger.error(
                    "GatewayTopologyHarness.cleanup also failed during start: %s",
                    type(cleanup_exc).__name__,
                )
                raise cleanup_exc from start_exc
            raise

    async def _do_start(self) -> None:
        self._init_dirs_and_secrets()
        self.prepare_static()

        self.edge_network = self.docker_client.networks.create(
            f"{self.prefix}-edge",
            labels={"com.cbrowser.prefix": self.prefix},
        )
        self.networks.append(self.edge_network)

        # 1. API container
        self.api_container = self._run_container(
            "api",
            self.api_image,
            read_only=True,
            tmpfs={"/tmp": "rw,size=256m"},
            environment={
                "CBROWSER_DB_PATH": "/metadata/control.db",
                "CBROWSER_SUPERVISOR_TOKEN_FILE": "/run/secrets/supervisor_key",
                "CBROWSER_GATEWAY_API_TOKEN_FILE": "/run/secrets/gateway_api_key",
                "CBROWSER_ADMIN_PASSWORD_FILE": "/run/secrets/admin_password",
                "CBROWSER_ALLOWED_ORIGINS": self.origin,
                **self.api_environment_extra(),
            },
            volumes={
                str(self.metadata_dir): {"bind": "/metadata", "mode": "rw"},
                str(self.control_dir): {"bind": "/run/secrets", "mode": "ro"},
            },
            ports={"8000/tcp": ("127.0.0.1", None)},
        )

        self.api_container.reload()
        self.api_ip = self.api_container.attrs["NetworkSettings"]["Networks"][
            self.edge_network.name
        ]["IPAddress"]

        # 3. Gateway container
        self.gateway_container = self._run_container(
            "gateway",
            self.gateway_image,
            read_only=True,
            tmpfs={"/tmp": "rw,size=256m"},
            environment={
                "CBROWSER_GATEWAY_HOST": "0.0.0.0",
                "CBROWSER_GATEWAY_PORT": str(DEFAULT_GATEWAY_PORT),
                "CBROWSER_AGENT_KEY_FILE": "/run/secrets/agent_key",
                "CBROWSER_GATEWAY_TOKEN_FILE": "/run/secrets/gateway_key",
                "CBROWSER_GATEWAY_API_URL": f"http://{self.api_ip}:8000",
                "CBROWSER_GATEWAY_API_TOKEN_FILE": "/run/secrets/gateway_api_key",
                "CBROWSER_ALLOWED_ORIGINS": self.origin,
                "CBROWSER_AGENT_HEARTBEAT_TIMEOUT_SEC": str(
                    self.agent_heartbeat_timeout_sec
                ),
            },
            volumes={
                str(self.control_dir): {"bind": "/run/secrets", "mode": "ro"},
            },
            ports={f"{DEFAULT_GATEWAY_PORT}/tcp": ("127.0.0.1", None)},
        )
        self.gateway_container.reload()
        self.gateway_ip = self.gateway_container.attrs["NetworkSettings"]["Networks"][
            self.edge_network.name
        ]["IPAddress"]

        # 4. Supervisor container
        mounts = {
            str(self.data_dir / name): {"bind": str(self.data_dir / name), "mode": "rw"}
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

        self.supervisor_container = self._run_container(
            "supervisor",
            self.supervisor_image,
            read_only=True,
            cap_add=["FOWNER", "DAC_OVERRIDE"],
            tmpfs={"/tmp": "rw,size=256m"},
            environment={
                "CBROWSER_BROWSER_IMAGE": self.browser_image,
                "CBROWSER_STREAM_IMAGE": self.stream_image,
                "CBROWSER_NETWORK_POLICY_IMAGE": self.supervisor_image,
            },
            volumes=mounts,
            ports={"8005/tcp": ("127.0.0.1", None)},
            command=[
                "--api-url",
                f"http://{self.api_ip}:8000",
                "--gateway-control-url",
                f"http://{self.gateway_ip}:{DEFAULT_GATEWAY_PORT}",
                "--gateway-port",
                str(DEFAULT_GATEWAY_PORT),
                "--gateway-container-id",
                self.gateway_container.id,
                "--prefix",
                self.prefix,
                "--data-root",
                str(self.data_dir),
                "--engine-cache",
                str(self.data_dir / "engine_cache"),
                "--token-file",
                str(self.key_files["supervisor"]),
                "--agent-key-file",
                str(self.key_files["agent"]),
                "--gateway-token-file",
                str(self.key_files["gateway"]),
                "--host",
                "0.0.0.0",
                "--port",
                "8005",
            ],
        )

        # 5. Caddy container
        caddyfile_content = generate_caddyfile(
            self.api_ip, self.gateway_ip, DEFAULT_GATEWAY_PORT
        )
        caddyfile_path = self.work_dir / "Caddyfile"
        caddyfile_path.write_text(caddyfile_content, encoding="utf-8")

        self.caddy_container = self._run_container(
            "caddy",
            self.caddy_image,
            read_only=True,
            tmpfs={
                "/tmp": "rw,size=64m",
                "/config": "rw,size=32m",
                "/data": "rw,size=64m",
            },
            volumes={
                str(caddyfile_path): {"bind": "/etc/caddy/Caddyfile", "mode": "ro"},
                str(self.static_dir): {"bind": "/var/www/html", "mode": "ro"},
            },
            ports={"443/tcp": ("127.0.0.1", self.caddy_host_port)},
            command=[
                "caddy",
                "run",
                "--config",
                "/etc/caddy/Caddyfile",
                "--adapter",
                "caddyfile",
            ],
        )

        self.supervisor_container.reload()
        sup_ports = self.supervisor_container.attrs["NetworkSettings"]["Ports"]
        if "8005/tcp" not in sup_ports or not sup_ports["8005/tcp"]:
            st = self.supervisor_container.status
            raise RuntimeError(f"Supervisor container did not expose 8005/tcp ({st})")
        sup_port = sup_ports["8005/tcp"][0]["HostPort"]
        self.supervisor_url = f"http://127.0.0.1:{sup_port}"

        self.api_container.reload()
        api_ports = self.api_container.attrs["NetworkSettings"]["Ports"]
        if "8000/tcp" not in api_ports or not api_ports["8000/tcp"]:
            st = self.api_container.status
            raise RuntimeError(f"API container did not expose 8000/tcp ({st})")
        api_port = api_ports["8000/tcp"][0]["HostPort"]
        self.api_internal_url = f"http://127.0.0.1:{api_port}"

        await wait_until_ready(self.api_internal_url, "/api/v1/health")
        await wait_until_ready(
            self.supervisor_url,
            "/supervisor/v1/health",
            headers={"Authorization": f"Bearer {self.keys['supervisor']}"},
        )
        await wait_until_ready(self.origin, "/api/v1/health", verify=False)

    async def login_api(
        self, client: httpx.AsyncClient | None = None
    ) -> dict[str, str]:
        """Performs login through HTTPS Caddy entrypoint and returns auth headers."""
        should_close = False
        if client is None:
            client = httpx.AsyncClient(
                base_url=self.origin, verify=False, trust_env=False
            )
            should_close = True
        try:
            resp = await client.post(
                "/api/v1/auth/login",
                json={"password": self.admin_password},
                headers={"Origin": self.origin},
            )
            resp.raise_for_status()
            data = resp.json()
            csrf_token = data["csrf_token"]
            session_cookie = resp.cookies.get("cbrowser_session")
            if not session_cookie:
                for val in resp.headers.get_list("set-cookie"):
                    if "cbrowser_session=" in val:
                        part = val.split("cbrowser_session=", 1)[1]
                        session_cookie = part.split(";", 1)[0]
                        break
            return {
                "Cookie": f"cbrowser_session={session_cookie}",
                "X-CSRF-Token": csrf_token,
                "Origin": self.origin,
            }
        finally:
            if should_close:
                await client.aclose()

    async def create_and_start_profile(
        self, name: str = "e2e_profile"
    ) -> dict[str, Any]:
        """Creates profile, sets desired state, starts via Supervisor."""
        auth_headers = await self.login_api()
        async with httpx.AsyncClient(
            base_url=self.origin,
            headers=auth_headers,
            verify=False,
            trust_env=False,
        ) as api_http:
            resp = await api_http.post("/api/v1/profiles", json={"name": name})
            assert resp.status_code == 201, f"Failed to create profile: {resp.text}"
            profile_id = resp.json()["id"]

            resp = await api_http.patch(
                f"/api/v1/profiles/{profile_id}/runtime/desired-state",
                json={"desired_state": "running"},
            )
            assert resp.status_code == 200, f"Failed to set desired state: {resp.text}"

        sup_headers = {"Authorization": f"Bearer {self.keys['supervisor']}"}
        async with httpx.AsyncClient(
            base_url=self.supervisor_url,
            headers=sup_headers,
            timeout=90.0,
            trust_env=False,
        ) as sup_http:
            resp = await sup_http.post(
                "/supervisor/v1/profiles/start",
                json={"profile_id": profile_id, "config_version": 1},
            )
            if resp.status_code != 200:
                sup_logs = self.supervisor_container.logs().decode("utf-8")
                raise AssertionError(
                    f"Failed to start profile in supervisor: {resp.text}\n"
                    f"Supervisor logs:\n{sup_logs}"
                )
            start_data = resp.json()

        # Wait for Gateway visibility 200 AND API runtime observed_state running
        gw_headers = {"Authorization": f"Bearer {self.keys['gateway']}"}
        gw_api_headers = {"Authorization": f"Bearer {self.keys['gateway_api']}"}
        runtime_instance_id = start_data["runtime_instance_id"]
        gw_ports = self.gateway_container.attrs["NetworkSettings"]["Ports"]
        gw_port = gw_ports[f"{DEFAULT_GATEWAY_PORT}/tcp"][0]["HostPort"]
        gateway_internal_url = f"http://127.0.0.1:{gw_port}"
        deadline = asyncio.get_running_loop().time() + 30.0
        async with (
            httpx.AsyncClient(
                base_url=gateway_internal_url,
                headers=gw_headers,
                trust_env=False,
            ) as gw_http,
            httpx.AsyncClient(
                base_url=self.api_internal_url,
                headers=gw_api_headers,
                trust_env=False,
            ) as api_http,
        ):
            while asyncio.get_running_loop().time() < deadline:
                try:
                    vis_resp = await gw_http.get(
                        f"/gateway/v1/internal/profiles/{profile_id}/visibility",
                        params={"runtime_instance_id": runtime_instance_id},
                    )
                    rt_resp = await api_http.get(
                        f"/api/v1/internal/gateway/profiles/{profile_id}/runtime"
                    )
                    if (
                        vis_resp.status_code == 200
                        and rt_resp.status_code == 200
                        and rt_resp.json().get("observed_state") in ("running", "ready")
                    ):
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.3)
            else:
                raise TimeoutError("Stream Agent did not register in 30s")

        return {
            "profile_id": profile_id,
            "runtime_instance_id": runtime_instance_id,
            "browser_container": start_data["browser_container"],
            "stream_container": start_data["stream_container"],
            "udp_mux_port": start_data["udp_mux_port"],
        }

    async def cleanup(self) -> None:
        """Tears down all Docker resources strictly labeled with self.prefix."""
        cleanup_prefixed_resources(self.docker_client, self.prefix)


def cleanup_prefixed_resources(docker_client: Any, prefix: str) -> None:
    """Core cleanup helper: removes resources strictly labeled with prefix."""
    errors: list[str] = []

    # 1. Containers: verify com.cbrowser.prefix label, remove owned containers
    try:
        owned_containers = docker_client.containers.list(
            all=True,
            filters={"label": f"com.cbrowser.prefix={prefix}"},
        )
    except Exception as exc:  # noqa: BLE001
        owned_containers = []
        errors.append(f"containers_list: {type(exc).__name__}")

    for c in owned_containers:
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
        except Exception as exc:  # noqa: BLE001
            err_t = type(exc).__name__
            logger.warning("Container stop error for %s: %s", c_name, err_t)

        try:
            c.remove(force=True, v=True)
        except docker.errors.NotFound:
            pass
        except Exception as exc:  # noqa: BLE001
            err_t = type(exc).__name__
            logger.error("Container remove error for %s: %s", c_name, err_t)
            errors.append(f"container_remove({c_name}): {err_t}")

    # 2. Networks: verify com.cbrowser.prefix label, delete empty owned networks
    try:
        owned_networks = docker_client.networks.list(
            filters={"label": f"com.cbrowser.prefix={prefix}"},
        )
    except Exception as exc:  # noqa: BLE001
        owned_networks = []
        errors.append(f"networks_list: {type(exc).__name__}")

    for n in owned_networks:
        n_lbls = getattr(n, "attrs", {}).get("Labels") or {}
        if n_lbls.get("com.cbrowser.prefix") != prefix:
            continue

        n_name = getattr(n, "name", "unnamed")
        try:
            if hasattr(n, "reload"):
                n.reload()
        except docker.errors.NotFound:
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"network_reload({n_name}): {type(exc).__name__}")
            continue

        containers_attached = getattr(n, "attrs", {}).get("Containers") or {}
        if containers_attached:
            errors.append(f"network_not_empty({n_name})")
            continue

        try:
            n.remove()
        except docker.errors.NotFound:
            pass
        except Exception as exc:  # noqa: BLE001
            err_t = type(exc).__name__
            logger.error("Network remove error for %s: %s", n_name, err_t)
            errors.append(f"network_remove({n_name}): {err_t}")

    if errors:
        raise RuntimeError(f"Cleanup encountered failures: {', '.join(errors)}")
