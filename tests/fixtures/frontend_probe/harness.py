"""Real Docker container topology harness for frontend session E2E tests."""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
for p in (str(REPO_ROOT), str(FIXTURES_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import docker  # noqa: E402
from gateway_probe.caddyfile import generate_caddyfile  # noqa: E402
from gateway_probe.topology import (  # noqa: E402
    GatewayTopologyHarness,
    wait_until_ready,
)

from .host_builder import prepare_frontend_host  # noqa: E402

logger = logging.getLogger("cbrowser.frontend_probe.harness")


def load_images_env() -> None:
    """Loads immutable image IDs from .scratch/images_env.txt into os.environ."""
    env_file = REPO_ROOT / ".scratch" / "images_env.txt"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k not in os.environ and v:
                os.environ[k] = v


class FrontendTopologyHarness(GatewayTopologyHarness):
    """Topology harness customized for t007 frontend session E2E tests."""

    prefix_base = "t007-fe-session"
    test_label = "t007-fe-session"

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
        load_images_env()
        super().__init__(
            work_dir=work_dir,
            webrtc_mode=webrtc_mode,
            credential_lifetime_sec=credential_lifetime_sec,
            generation_interval_sec=generation_interval_sec,
            ice_restart_lead_time_sec=ice_restart_lead_time_sec,
            agent_heartbeat_timeout_sec=agent_heartbeat_timeout_sec,
            coturn_total_quota=coturn_total_quota,
        )
        # Dedicated prefix for this lane
        self.prefix = f"{self.prefix_base}-{uuid.uuid4().hex[:8]}"

    def _run_container(
        self, role: str, image_id: str, **kwargs: Any
    ) -> docker.models.containers.Container:
        labels = kwargs.pop("labels", {})
        labels.update(
            {
                "com.cbrowser.prefix": self.prefix,
                "com.cbrowser.test": self.test_label,
                "com.cbrowser.role": role,
            }
        )
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

    def prepare_static(self) -> None:
        """Prepares the Caddy static root for this harness variant."""
        prepare_frontend_host(self.static_dir)

    def api_environment_extra(self) -> dict[str, str]:
        """Extra environment variables for the API container."""
        return {}

    async def start(self) -> None:
        self._init_dirs_and_secrets()
        # Serve frontend build + BrowserSessionView host page as static directory
        self.prepare_static()

        self.edge_network = self.docker_client.networks.create(
            f"{self.prefix}-edge",
            labels={
                "com.cbrowser.prefix": self.prefix,
                "com.cbrowser.test": self.test_label,
            },
        )
        self.networks.append(self.edge_network)

        # Delegate container startup to parent start method (avoiding duplication):
        # the parent start() would prepare different static assets and its own
        # network, so container startup is invoked directly here.
        await self._start_containers()

    async def _start_containers(self) -> None:
        """Starts all Docker containers in correct dependency order."""
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
