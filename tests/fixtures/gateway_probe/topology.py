"""Real Docker container graph topology for Gateway, API, Supervisor, coturn, Caddy."""

from __future__ import annotations

import asyncio
import ipaddress
import json
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
        webrtc_mode: str = "lan",
        credential_lifetime_sec: float = 86400.0,
        generation_interval_sec: float = 43200.0,
        ice_restart_lead_time_sec: float = 21600.0,
        agent_heartbeat_timeout_sec: float = 30.0,
        coturn_total_quota: int | None = None,
    ) -> None:
        self.work_dir = work_dir
        self.webrtc_mode = webrtc_mode
        self.credential_lifetime_sec = credential_lifetime_sec
        self.generation_interval_sec = generation_interval_sec
        self.ice_restart_lead_time_sec = ice_restart_lead_time_sec
        self.agent_heartbeat_timeout_sec = agent_heartbeat_timeout_sec
        self.coturn_total_quota = coturn_total_quota

        self.docker_client = docker.from_env()
        self.prefix = f"t006-relay-{uuid.uuid4().hex[:8]}"

        self.containers: list[docker.models.containers.Container] = []
        self.networks: list[docker.models.networks.Network] = []

        self.browser_image = self._get_image("CBROWSER_RUNTIME_TEST_IMAGE")
        self.stream_image = self._get_image("CBROWSER_STREAM_TEST_IMAGE")
        self.gateway_image = self._get_image("CBROWSER_GATEWAY_IMAGE")
        self.supervisor_image = self._get_image("CBROWSER_SUPERVISOR_TEST_IMAGE")
        self.api_image = self._get_image("CBROWSER_API_TEST_IMAGE")
        self.turn_image = os.environ.get(
            "CBROWSER_TURN_TEST_IMAGE",
            "sha256:e2bca2f79a4269d7240de5872ab60a9305013ad37296d2acf14f9510874346be",
        )
        assert self.turn_image.startswith("sha256:")
        self.caddy_image = os.environ.get(
            "CBROWSER_CADDY_TEST_IMAGE",
            "sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b",
        )
        assert self.caddy_image.startswith("sha256:")

        self.engine_cache_src = Path(os.environ["CBROWSER_RUNTIME_ENGINE_CACHE"])
        self.geoip_cache_src = Path(os.environ["CBROWSER_RUNTIME_GEOIP_CACHE"])

        self.caddy_host_port = find_free_port(35000, 35999)
        self.coturn_host_port = find_free_port(34800, 34999)
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
        self.coturn_container: docker.models.containers.Container | None = None
        self.gateway_container: docker.models.containers.Container | None = None
        self.supervisor_container: docker.models.containers.Container | None = None
        self.caddy_container: docker.models.containers.Container | None = None

        self.api_ip: str = ""
        self.coturn_ip: str = ""
        self.gateway_ip: str = ""
        self.supervisor_url: str = ""
        self.api_internal_url: str = ""

    def _get_image(self, var_name: str) -> str:
        val = os.environ.get(var_name)
        assert val and val.startswith("sha256:"), (
            f"Missing or invalid immutable image ID in {var_name}"
        )
        return val

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

        for name in ("supervisor", "agent", "gateway", "gateway_api", "turn"):
            val = secrets.token_urlsafe(32)
            f = self.control_dir / f"{name}_key"
            f.write_text(val, encoding="utf-8")
            f.chmod(0o644)
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
        # Gateway and coturn require managed-by=supervisor for infra validation
        if role in ("gateway", "coturn"):
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
        self._init_dirs_and_secrets()
        prepare_selkies_web_assets(self.stream_image, self.static_dir)

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
            },
            volumes={
                str(self.metadata_dir): {"bind": "/metadata", "mode": "rw"},
                str(self.control_dir): {"bind": "/run/secrets", "mode": "ro"},
            },
            ports={"8000/tcp": ("127.0.0.1", None)},
        )

        # 2. Coturn container
        net_info = self.docker_client.api.inspect_network(self.edge_network.name)
        if isinstance(net_info, (str, bytes)):
            net_info = json.loads(net_info)
        subnet = ipaddress.ip_network(net_info["IPAM"]["Config"][0]["Subnet"])
        self.coturn_ip = str(subnet[10])

        turn_conf_content = (
            "listening-port=3478\n"
            "listening-ip=0.0.0.0\n"
            "realm=cbrowser.local\n"
            "use-auth-secret\n"
            "no-cli\n"
            "no-tls\n"
            "no-dtls\n"
            "verbose\n"
            f"static-auth-secret={self.keys['turn']}\n"
            f"external-ip=127.0.0.1/{self.coturn_ip}\n"
            "allow-loopback-peers\n"
            "min-port=50000\n"
            "max-port=50040\n"
        )
        if self.coturn_total_quota is not None:
            turn_conf_content += f"total-quota={self.coturn_total_quota}\n"

        turn_conf_path = self.control_dir / "turnserver.conf"
        turn_conf_path.write_text(turn_conf_content, encoding="utf-8")
        turn_conf_path.chmod(0o644)

        endpoint_config = self.docker_client.api.create_endpoint_config(
            ipv4_address=self.coturn_ip
        )
        networking_config = {self.edge_network.name: endpoint_config}

        turn_ports = {
            "3478/udp": ("127.0.0.1", self.coturn_host_port),
            "3478/tcp": ("127.0.0.1", self.coturn_host_port),
        }
        for port_num in range(50000, 50041):
            turn_ports[f"{port_num}/udp"] = ("127.0.0.1", port_num)

        self.coturn_container = self._run_container(
            "coturn",
            self.turn_image,
            read_only=True,
            cap_drop=["ALL"],
            cap_add=["NET_BIND_SERVICE"],
            security_opt=["no-new-privileges:true"],
            tmpfs={"/tmp": "rw,mode=1777"},
            networking_config=networking_config,
            volumes={
                str(turn_conf_path): {"bind": "/etc/turnserver.conf", "mode": "ro"},
            },
            ports=turn_ports,
            entrypoint="/usr/bin/turnserver",
            command=[
                "-c",
                "/etc/turnserver.conf",
                "--relay-threads=1",
                "--log-file=stdout",
            ],
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
                "CBROWSER_GATEWAY_PORT": "18097",
                "CBROWSER_AGENT_KEY_FILE": "/run/secrets/agent_key",
                "CBROWSER_GATEWAY_TOKEN_FILE": "/run/secrets/gateway_key",
                "CBROWSER_GATEWAY_API_URL": f"http://{self.api_ip}:8000",
                "CBROWSER_GATEWAY_API_TOKEN_FILE": "/run/secrets/gateway_api_key",
                "CBROWSER_ALLOWED_ORIGINS": self.origin,
                "CBROWSER_TURN_SECRET_FILE": "/run/secrets/turn_key",
                "CBROWSER_WEBRTC_MODE": self.webrtc_mode,
                "CBROWSER_TURN_PUBLIC_URLS": (
                    f"turn:127.0.0.1:{self.coturn_host_port}?transport=udp,"
                    f"turn:127.0.0.1:{self.coturn_host_port}?transport=tcp"
                ),
                "CBROWSER_RTC_CREDENTIAL_LIFETIME_SEC": str(
                    self.credential_lifetime_sec
                ),
                "CBROWSER_RTC_GENERATION_INTERVAL_SEC": str(
                    self.generation_interval_sec
                ),
                "CBROWSER_RTC_ICE_RESTART_LEAD_TIME_SEC": str(
                    self.ice_restart_lead_time_sec
                ),
                "CBROWSER_AGENT_HEARTBEAT_TIMEOUT_SEC": str(
                    self.agent_heartbeat_timeout_sec
                ),
            },
            volumes={
                str(self.control_dir): {"bind": "/run/secrets", "mode": "ro"},
            },
            ports={"18097/tcp": ("127.0.0.1", None)},
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
                f"http://{self.gateway_ip}:18097",
                "--gateway-container-id",
                self.gateway_container.id,
                "--coturn-container-id",
                self.coturn_container.id,
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
        caddyfile_content = generate_caddyfile(self.api_ip, self.gateway_ip)
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
        sup_port = self.supervisor_container.attrs["NetworkSettings"]["Ports"][
            "8005/tcp"
        ][0]["HostPort"]
        self.supervisor_url = f"http://127.0.0.1:{sup_port}"

        self.api_container.reload()
        api_port = self.api_container.attrs["NetworkSettings"]["Ports"]["8000/tcp"][0][
            "HostPort"
        ]
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
        gw_port = self.gateway_container.attrs["NetworkSettings"]["Ports"]["18097/tcp"][
            0
        ]["HostPort"]
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
        """Tears down and removes all Docker resources prefixed with self.prefix."""
        try:
            all_containers = self.docker_client.containers.list(
                all=True,
                filters={"label": f"com.cbrowser.prefix={self.prefix}"},
            )
            for c in all_containers:
                try:
                    c.reload()
                    nets = list(
                        c.attrs.get("NetworkSettings", {}).get("Networks", {}).keys()
                    )
                    for net_name in nets:
                        try:
                            net = self.docker_client.networks.get(net_name)
                            net.disconnect(c, force=True)
                        except Exception:
                            pass
                    c.stop(timeout=1)
                except Exception:
                    pass
                try:
                    c.remove(force=True, v=True)
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Error stopping containers during cleanup: %s", e)

        try:
            all_networks = self.docker_client.networks.list(
                filters={"label": f"com.cbrowser.prefix={self.prefix}"},
            )
            for n in all_networks:
                try:
                    n.remove()
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Error removing networks during cleanup: %s", e)

        try:
            for net in self.docker_client.networks.list():
                if net.name.startswith(self.prefix):
                    try:
                        net.remove()
                    except Exception:
                        pass
        except Exception:
            pass
