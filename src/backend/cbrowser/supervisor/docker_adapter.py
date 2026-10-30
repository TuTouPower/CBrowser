"""Docker Adapter for CBrowser Runtime Supervisor."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

import docker
from cbrowser.supervisor.file_storage import atomic_write_text
from cbrowser.supervisor.network_policy import NetworkPolicySpec
from cbrowser.supervisor.path_validator import PathValidator
from docker.errors import DockerException, NotFound

logger = logging.getLogger("cbrowser.supervisor.docker_adapter")


class DockerSandboxError(Exception):
    pass


class DockerAdapter:
    def __init__(
        self,
        path_validator: PathValidator,
        engine_cache_dir: Path | str,
        docker_client: Optional[docker.DockerClient] = None,
        browser_image: Optional[str] = None,
        stream_image: Optional[str] = None,
        resource_prefix: str = "cbrowser-t005",
        geoip_cache_dir: Optional[Path | str] = None,
        policy_image: str | None = None,
    ):
        self.validator = path_validator
        self.engine_cache = self.validator.validate_safe_path(engine_cache_dir)
        self.geoip_cache = self.validator.validate_safe_path(
            geoip_cache_dir or self.engine_cache / "geoip"
        )
        self.engine_cache.mkdir(parents=True, exist_ok=True)
        self.geoip_cache.mkdir(parents=True, exist_ok=True)
        self._validate_cache_paths()
        self.client = docker_client or docker.from_env()
        self.browser_image = browser_image or os.environ.get("CBROWSER_BROWSER_IMAGE")
        self.stream_image = stream_image or os.environ.get("CBROWSER_STREAM_IMAGE")
        for image in (self.browser_image, self.stream_image):
            if not image or not (image.startswith("sha256:") or "@sha256:" in image):
                raise ValueError(
                    "Explicit immutable Browser and Stream images are required"
                )
        self.resource_prefix = resource_prefix
        self.policy_image = policy_image or os.environ.get(
            "CBROWSER_NETWORK_POLICY_IMAGE"
        )
        self._cache_lock = asyncio.Lock()
        self._binary_ready = False
        self._geoip_ready = False

    def _prepare_policy_gate(
        self, profile_id: str, instance_id: str, role: str
    ) -> Path:
        if not self.policy_image or not (
            self.policy_image.startswith("sha256:") or "@sha256:" in self.policy_image
        ):
            raise DockerSandboxError(
                "Explicit immutable network policy image is required"
            )
        self.validator.get_runtime_dir(profile_id)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", instance_id):
            raise DockerSandboxError("Invalid runtime instance identity")
        # New directory for every container launch; no prior ready marker is reused.
        gate = self.validator.validate_safe_path(
            self.validator.data_root
            / "control"
            / "gates"
            / profile_id
            / instance_id
            / f"{role}_{uuid.uuid4().hex}",
            allow_create=True,
        )
        gate.mkdir(parents=True, mode=0o755, exist_ok=False)
        gate.chmod(0o755)
        source = Path(__file__).with_name("startup_gate.py").read_text(encoding="utf-8")
        atomic_write_text(gate / "startup_gate.py", source, mode=0o644)
        return gate

    @staticmethod
    def _gated_entrypoint(instance_id: str, role: str) -> list[str]:
        return [
            "/usr/bin/tini",
            "-g",
            "--",
            "python3",
            "/run/cbrowser_policy/startup_gate.py",
            "--instance-id",
            instance_id,
            "--role",
            role,
            "--",
            "/app/entrypoint.sh",
        ]

    def _resolved_endpoint(self, container: Any, url: str) -> list[tuple[str, int]]:
        parsed = urlsplit(url if "://" in url else "http://" + url)
        if not parsed.hostname:
            raise DockerSandboxError("Network endpoint hostname is required")
        port = parsed.port or {
            "http": 80,
            "https": 443,
            "ws": 80,
            "wss": 443,
            "socks5": 1080,
            "socks5h": 1080,
        }.get(parsed.scheme)
        if port is None:
            raise DockerSandboxError("Network endpoint requires an explicit port")
        try:
            return [(str(ipaddress.ip_address(parsed.hostname)), port)]
        except ValueError:
            pass
        # Resolve with Docker DNS in the gated runtime, not the Mac namespace.
        # The fixed bootstrap performs DNS only; business processes remain gated.
        script = (
            "import json,socket,sys; "
            "sys.stdout.write(json.dumps(sorted({x[4][0] for x in "
            "socket.getaddrinfo(sys.argv[1], int(sys.argv[2]), "
            "type=socket.SOCK_STREAM)})))"
        )
        result = container.exec_run(
            ["python3", "-I", "-S", "-c", script, parsed.hostname, str(port)],
            user="1000:1000",
        )
        if result.exit_code != 0:
            raise DockerSandboxError("Runtime endpoint DNS resolution failed")
        try:
            addresses = json.loads(result.output)
            if not addresses or not isinstance(addresses, list):
                raise ValueError("Empty address set")
            return [(str(ipaddress.ip_address(address)), port) for address in addresses]
        except (ValueError, TypeError):
            raise DockerSandboxError("Invalid runtime DNS response") from None

    def _install_network_policy(
        self,
        container: Any,
        policy: dict[str, Any],
        gate: Path,
        instance_id: str,
        role: str,
    ) -> None:
        validated_policy = NetworkPolicySpec.model_validate(policy)
        helper = None
        try:
            helper = self.client.containers.run(
                self.policy_image,
                entrypoint=["python3", "-m", "cbrowser.supervisor.network_policy"],
                command=[validated_policy.model_dump_json()],
                name=f"{self.resource_prefix}-policy-{uuid.uuid4().hex[:12]}",
                detach=True,
                user="0:0",
                read_only=True,
                cap_drop=["ALL"],
                cap_add=["NET_ADMIN"],
                security_opt=["no-new-privileges:true"],
                network_mode=f"container:{container.id}",
                tmpfs={
                    "/run": "rw,nosuid,nodev,size=4m",
                    "/tmp": "rw,nosuid,nodev,size=4m",
                },
                labels={
                    "com.cbrowser.prefix": self.resource_prefix,
                    "com.cbrowser.managed-by": "supervisor",
                    "com.cbrowser.role": "network-policy",
                    "com.cbrowser.instance-id": instance_id,
                },
            )
            result = helper.wait(timeout=30)
            if result.get("StatusCode") != 0:
                raise DockerSandboxError("Runtime network policy installation failed")
        except DockerException as exc:
            raise DockerSandboxError(
                "Runtime network policy installation failed: " + type(exc).__name__
            ) from None
        finally:
            if helper is not None:
                helper.remove(force=True)
        atomic_write_text(
            gate / "ready.json",
            json.dumps({"instance_id": instance_id, "role": role, "status": "ready"}),
            mode=0o644,
        )

    def _validate_cache_paths(self) -> None:
        for root in (self.engine_cache, self.geoip_cache):
            self.validator.validate_safe_path(root)
            for item in root.rglob("*"):
                self.validator.validate_safe_path(item)

    async def cleanup_orphan_helpers(self) -> None:
        """Reap prior coordinator helpers once, under the startup coordinator lock.

        Never call from periodic reconciliation: a live installer may be running.
        All candidates are validated before removing any container.
        """
        await asyncio.to_thread(self._cleanup_orphan_helpers)

    def _cleanup_orphan_helpers(self) -> None:
        candidates = self.client.containers.list(
            all=True,
            filters={
                "label": [
                    f"com.cbrowser.prefix={self.resource_prefix}",
                    "com.cbrowser.managed-by=supervisor",
                ]
            },
        )
        owned = []
        for container in candidates:
            labels = container.labels or {}
            role = labels.get("com.cbrowser.role")
            if role not in {"cache-init", "network-policy"}:
                continue
            name_role = "cache" if role == "cache-init" else "policy"
            if (
                labels.get("com.cbrowser.prefix") != self.resource_prefix
                or labels.get("com.cbrowser.managed-by") != "supervisor"
                or not re.fullmatch(
                    re.escape(f"{self.resource_prefix}-{name_role}-") + r"[0-9a-f]{12}",
                    container.name,
                )
            ):
                raise DockerSandboxError("Transient helper ownership mismatch")
            owned.append(container)
        for container in owned:
            try:
                container.remove(force=True)
            except NotFound:
                pass

    async def ensure_runtime_cache(self, need_geoip: bool) -> None:
        async with self._cache_lock:
            if self._binary_ready and (not need_geoip or self._geoip_ready):
                return
            await asyncio.to_thread(self._initialize_cache, need_geoip)
            self._validate_cache_paths()
            self._binary_ready = True
            self._geoip_ready = self._geoip_ready or need_geoip

    def _initialize_cache(self, need_geoip: bool) -> None:
        # Only the initializer receives writable cache mounts. Runtime consumers
        # see the completed cache read-only, including GeoIP data.
        self.engine_cache.chmod(0o777)
        self.geoip_cache.chmod(0o777)
        (self.engine_cache / "geoip").mkdir(exist_ok=True)
        run_id = uuid.uuid4().hex
        marker_name = f"cache_init_{run_id}.json"
        marker = self.engine_cache / marker_name
        script = """import json, os
from pathlib import Path
from cloakbrowser.config import get_chromium_version
from cloakbrowser.download import ensure_binary
binary = Path(ensure_binary(browser_version=get_chromium_version()))
if not binary.is_file():
    raise RuntimeError('Browser binary initialization did not complete')
if os.environ['CBROWSER_INIT_GEOIP'] == '1':
    from cloakbrowser.geoip import _ensure_geoip_db
    database = _ensure_geoip_db()
    if database is None or not database.is_file():
        raise RuntimeError('GeoIP initialization did not complete')
for root in (Path('/data/engine-cache'), Path('/data/engine-cache/geoip')):
    for directory in [root, *root.rglob('*')]:
        if directory.is_dir() and not directory.is_symlink():
            directory.chmod(0o777)
path = Path('/data/engine-cache') / os.environ['CBROWSER_INIT_MARKER']
with path.open('w') as output:
    json.dump({'run_id':os.environ['CBROWSER_INIT_RUN_ID']},output)
    output.flush()
    os.fsync(output.fileno())
"""
        helper = None
        try:
            helper = self.client.containers.run(
                self.browser_image,
                entrypoint="python3",
                command=["-c", script],
                name=f"{self.resource_prefix}-cache-{run_id[:12]}",
                detach=True,
                read_only=True,
                user="0:0",
                cap_drop=["ALL"],
                cap_add=["DAC_OVERRIDE", "FOWNER"],
                security_opt=["no-new-privileges:true"],
                tmpfs={"/tmp": "rw,size=512m", "/home/cbrowser": "rw,size=64m"},
                volumes={
                    str(self.engine_cache): {
                        "bind": "/data/engine-cache",
                        "mode": "rw",
                    },
                    str(self.geoip_cache): {
                        "bind": "/data/engine-cache/geoip",
                        "mode": "rw",
                    },
                },
                environment={
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "CLOAKBROWSER_CACHE_DIR": "/data/engine-cache",
                    "CBROWSER_INIT_GEOIP": "1" if need_geoip else "0",
                    "CBROWSER_INIT_MARKER": marker_name,
                    "CBROWSER_INIT_RUN_ID": run_id,
                },
                labels={
                    "com.cbrowser.prefix": self.resource_prefix,
                    "com.cbrowser.role": "cache-init",
                    "com.cbrowser.managed-by": "supervisor",
                },
            )
            result = helper.wait(timeout=600)
            if result.get("StatusCode") != 0:
                raise DockerSandboxError(
                    "Runtime cache initializer exited unsuccessfully"
                )
            if (
                not marker.is_file()
                or json.loads(marker.read_text()).get("run_id") != run_id
            ):
                raise DockerSandboxError("Runtime cache initializer did not complete")
        except DockerException as exc:
            raise DockerSandboxError(
                f"Runtime cache initializer failed: {type(exc).__name__}"
            ) from None
        finally:
            marker.unlink(missing_ok=True)
            if helper is not None:
                helper.remove(force=True)

    def get_browser_container_name(self, profile_id: str) -> str:
        return f"{self.resource_prefix}-browser-{profile_id}"

    def get_stream_container_name(self, profile_id: str) -> str:
        return f"{self.resource_prefix}-stream-{profile_id}"

    def get_network_name(self, profile_id: str) -> str:
        return f"{self.resource_prefix}-net-{profile_id}"

    def get_browser_network_name(self, profile_id: str) -> str:
        return f"{self.resource_prefix}-browser-net-{profile_id}"

    def prepare_profile_directories(self, profile_id: str) -> dict[str, Path]:
        profile_dir = self.validator.get_profile_data_dir(profile_id)
        runtime_dir = self.validator.get_runtime_dir(profile_id)
        events_dir = self.validator.get_events_dir(profile_id)
        exchange_dir = self.validator.get_exchange_dir(profile_id)

        for d in (profile_dir, runtime_dir, events_dir, exchange_dir):
            d.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(d, 0o777)
            except Exception:
                pass

        x11_dir = self.validator.validate_runtime_source(
            profile_id, runtime_dir / "x11", allow_create=True
        )
        pulse_dir = self.validator.validate_runtime_source(
            profile_id, runtime_dir / "pulse", allow_create=True
        )
        x11_dir.mkdir(parents=True, exist_ok=True)
        pulse_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(x11_dir, 0o777)
            os.chmod(pulse_dir, 0o777)
        except Exception:
            pass

        return {
            "profile": profile_dir,
            "runtime": runtime_dir,
            "events": events_dir,
            "exchange": exchange_dir,
            "x11": x11_dir,
            "pulse": pulse_dir,
        }

    def setup_x11_permissions(self, x11_dir: Path) -> None:
        try:
            self.client.containers.run(
                self.browser_image,
                entrypoint="chmod",
                command=["1777", "/x11"],
                volumes={str(x11_dir): {"bind": "/x11", "mode": "rw"}},
                user="0:0",
                remove=True,
            )
        except DockerException as e:
            logger.error(f"Failed to setup X11 permissions: {e}")
            raise DockerSandboxError(
                f"X11 permission initialization failed: {e}"
            ) from e

    async def create_profile_network(self, profile_id: str) -> Any:
        return await asyncio.to_thread(
            self._ensure_network, profile_id, self.get_network_name(profile_id)
        )

    async def create_browser_network(self, profile_id: str) -> Any:
        return await asyncio.to_thread(
            self._ensure_network, profile_id, self.get_browser_network_name(profile_id)
        )

    def _ensure_network(self, profile_id: str, net_name: str) -> Any:
        try:
            try:
                existing = self.client.networks.get(net_name)
            except NotFound:
                existing = None
            if existing is not None:
                self._require_network_ownership(existing, net_name)
                return existing
            return self.client.networks.create(
                net_name,
                driver="bridge",
                labels={
                    "com.cbrowser.managed-by": "supervisor",
                    "com.cbrowser.profile-id": profile_id,
                    "com.cbrowser.prefix": self.resource_prefix,
                },
            )
        except DockerException as e:
            raise DockerSandboxError(f"Failed to create network {net_name}: {e}") from e

    def _require_network_ownership(self, network: Any, name: str) -> None:
        labels = network.attrs.get("Labels") or {}
        profile_id = labels.get("com.cbrowser.profile-id")
        if (
            network.name != name
            or not isinstance(profile_id, str)
            or name
            not in {
                self.get_network_name(profile_id),
                self.get_browser_network_name(profile_id),
            }
            or labels.get("com.cbrowser.prefix") != self.resource_prefix
            or labels.get("com.cbrowser.managed-by") != "supervisor"
            or labels.get("com.cbrowser.profile-id") != profile_id
        ):
            raise DockerSandboxError("Docker network ownership mismatch")

    def _validate_infra_container(self, container_id: str, expected_role: str) -> Any:
        if not container_id or not isinstance(container_id, str):
            raise DockerSandboxError(
                f"Explicit {expected_role} container ID is required"
            )
        try:
            container = self.client.containers.get(container_id)
        except NotFound:
            raise DockerSandboxError(
                f"Infrastructure container {container_id} not found"
            ) from None
        except DockerException as e:
            raise DockerSandboxError(
                f"Failed to inspect infrastructure container {container_id}: {e}"
            ) from e

        labels = container.labels or {}
        if container.status != "running":
            raise DockerSandboxError("Infrastructure container is not running")
        if labels.get("com.cbrowser.managed-by") != "supervisor":
            raise DockerSandboxError(
                f"Infrastructure container {container_id} not managed by supervisor"
            )
        if labels.get("com.cbrowser.prefix") != self.resource_prefix:
            raise DockerSandboxError(
                f"Infrastructure container {container_id} prefix mismatch: "
                f"{labels.get('com.cbrowser.prefix')} != {self.resource_prefix}"
            )
        if labels.get("com.cbrowser.role") != expected_role:
            raise DockerSandboxError(
                f"Infrastructure container {container_id} role mismatch: "
                f"expected {expected_role}, got {labels.get('com.cbrowser.role')}"
            )
        return container

    def attach_profile_infrastructure(
        self,
        profile_id: str,
        gateway_container_id: str,
        coturn_container_id: str,
        gateway_port: int = 18097,
        coturn_port: int = 3478,
    ) -> dict[str, Any]:
        net_name = self.get_network_name(profile_id)
        try:
            net = self.client.networks.get(net_name)
        except NotFound:
            raise DockerSandboxError(f"Profile network {net_name} not found") from None
        except DockerException as e:
            raise DockerSandboxError(f"Failed to get network {net_name}: {e}") from e

        self._require_network_ownership(net, net_name)

        gw = self._validate_infra_container(gateway_container_id, "gateway")
        coturn = self._validate_infra_container(coturn_container_id, "coturn")

        newly_connected: list[Any] = []
        try:
            net.reload()
            connected_containers = net.attrs.get("Containers") or {}

            for container in (gw, coturn):
                if container.id not in connected_containers:
                    net.connect(container)
                    newly_connected.append(container)
                    net.reload()
                    connected_containers = net.attrs.get("Containers") or {}

            gw.reload()
            coturn.reload()
            gw_networks = gw.attrs.get("NetworkSettings", {}).get("Networks", {})
            coturn_networks = coturn.attrs.get("NetworkSettings", {}).get(
                "Networks", {}
            )

            gw_ip = gw_networks.get(net_name, {}).get("IPAddress")
            coturn_ip = coturn_networks.get(net_name, {}).get("IPAddress")

            if not gw_ip or not coturn_ip:
                net.reload()
                c_map = net.attrs.get("Containers") or {}
                if not gw_ip and gw.id in c_map:
                    gw_ip = c_map[gw.id].get("IPv4Address", "").split("/")[0]
                if not coturn_ip and coturn.id in c_map:
                    coturn_ip = c_map[coturn.id].get("IPv4Address", "").split("/")[0]

            if not gw_ip or not coturn_ip:
                raise DockerSandboxError(
                    f"Failed to allocate or retrieve IPv4 addresses for "
                    f"infrastructure on {net_name}"
                )

            return {
                "gateway_ip": gw_ip,
                "coturn_ip": coturn_ip,
                "gateway_url": f"ws://{gw_ip}:{gateway_port}",
                "coturn_ice_address": f"{coturn_ip}:{coturn_port}",
                "ice_server": f"turn:{coturn_ip}:{coturn_port}",
            }
        except Exception as exc:
            for c in newly_connected:
                try:
                    net.disconnect(c)
                except Exception:
                    pass
            if isinstance(exc, DockerSandboxError):
                raise
            raise DockerSandboxError(
                f"Infrastructure attachment failed on {net_name}: {exc}"
            ) from exc

    def disconnect_profile_infrastructure(
        self,
        profile_id: str,
        gateway_container_id: Optional[str] = None,
        coturn_container_id: Optional[str] = None,
    ) -> None:
        net_name = self.get_network_name(profile_id)
        try:
            net = self.client.networks.get(net_name)
        except NotFound:
            return
        except DockerException as e:
            raise DockerSandboxError(f"Failed to get network {net_name}: {e}") from e

        self._require_network_ownership(net, net_name)
        net.reload()
        connected = net.attrs.get("Containers") or {}

        targets = []
        if gateway_container_id:
            targets.append(
                self._validate_infra_container(gateway_container_id, "gateway")
            )
        if coturn_container_id:
            targets.append(
                self._validate_infra_container(coturn_container_id, "coturn")
            )

        if not targets:
            for cid in list(connected.keys()):
                try:
                    c = self.client.containers.get(cid)
                    labels = c.labels or {}
                    if (
                        labels.get("com.cbrowser.prefix") == self.resource_prefix
                        and labels.get("com.cbrowser.managed-by") == "supervisor"
                        and labels.get("com.cbrowser.role") in {"gateway", "coturn"}
                    ):
                        targets.append(c)
                except DockerException:
                    pass

        for c in targets:
            if c.id in connected:
                try:
                    net.disconnect(c)
                except DockerException as e:
                    raise DockerSandboxError(
                        f"Failed to disconnect {c.id} from {net_name}: {e}"
                    ) from e

    async def start_browser_container(
        self,
        profile_id: str,
        runtime_instance_id: str,
        snapshot_json_path: Path,
        display: str = ":99",
    ) -> Any:
        b_name = self.get_browser_container_name(profile_id)
        net_name = self.get_browser_network_name(profile_id)
        await self.create_browser_network(profile_id)
        dirs = self.prepare_profile_directories(profile_id)
        snapshot_json_path = self.validator.validate_runtime_source(
            profile_id, snapshot_json_path
        )
        snapshot = json.loads(snapshot_json_path.read_text(encoding="utf-8"))
        await self.ensure_runtime_cache(snapshot.get("config", {}).get("geoip", True))
        self.setup_x11_permissions(dirs["x11"])

        target_snap = dirs["runtime"] / "snapshot.json"
        if snapshot_json_path != target_snap:
            atomic_write_text(
                target_snap, snapshot_json_path.read_text(encoding="utf-8"), mode=0o644
            )

        self.cleanup_container_by_name(b_name)

        # The prior owned Browser has been removed. Chromium's singleton links
        # refer to its old hostname/PID and cannot be reused in a new container.
        # Unlink the entries themselves; never follow a stale socket/cookie link.
        for filename in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            lock_path = dirs["profile"] / filename
            if lock_path.is_symlink() or lock_path.exists():
                lock_path.unlink()

        gate = self._prepare_policy_gate(profile_id, runtime_instance_id, "browser")
        proxy = snapshot.get("config", {}).get("proxy")
        volumes = {
            str(gate): {"bind": "/run/cbrowser_policy", "mode": "ro"},
            str(dirs["profile"]): {
                "bind": f"/data/profiles/{profile_id}/profile",
                "mode": "rw",
            },
            str(dirs["events"]): {
                "bind": f"/data/runtime-events/{profile_id}",
                "mode": "rw",
            },
            str(dirs["exchange"]): {"bind": "/exchange/downloads", "mode": "rw"},
            str(dirs["runtime"]): {"bind": "/run/cbrowser/runtime", "mode": "rw"},
            str(dirs["x11"]): {"bind": "/tmp/.X11-unix", "mode": "rw"},
            str(dirs["pulse"]): {"bind": "/pulse", "mode": "rw"},
        }
        self._validate_cache_paths()
        volumes[str(self.engine_cache)] = {"bind": "/data/engine-cache", "mode": "ro"}
        volumes[str(self.geoip_cache)] = {
            "bind": "/data/engine-cache/geoip",
            "mode": "ro",
        }

        command = [
            "--profile-id",
            profile_id,
            "--runtime-instance-id",
            runtime_instance_id,
            "--config-snapshot",
            "/run/cbrowser/runtime/snapshot.json",
            "--run-dir",
            "/run/cbrowser/runtime",
            "--user-data-dir",
            f"/data/profiles/{profile_id}/profile",
            "--events-dir",
            f"/data/runtime-events/{profile_id}",
            "--engine-cache-dir",
            "/data/engine-cache",
            "--download-dir",
            "/exchange/downloads",
            "--display",
            display,
        ]

        try:
            container = self.client.containers.run(
                self.browser_image,
                command=command,
                entrypoint=self._gated_entrypoint(runtime_instance_id, "browser"),
                name=b_name,
                detach=True,
                user="1000:1000",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                ipc_mode="shareable",
                shm_size="1g",
                network=net_name,
                restart_policy={"Name": "no"},
                tmpfs={
                    "/tmp": "rw,exec,nosuid,nodev,size=512m",
                    "/home/cbrowser": "rw,mode=0755,size=64m",
                },
                volumes=volumes,
                labels={
                    "com.cbrowser.managed-by": "supervisor",
                    "com.cbrowser.profile-id": profile_id,
                    "com.cbrowser.instance-id": runtime_instance_id,
                    "com.cbrowser.role": "browser",
                    "com.cbrowser.network-policy": "v1",
                    "com.cbrowser.config-version": str(snapshot["version"]),
                    "com.cbrowser.prefix": self.resource_prefix,
                },
            )
            allowed_tcp = (
                await asyncio.to_thread(self._resolved_endpoint, container, proxy)
                if proxy
                else []
            )
            await asyncio.to_thread(
                self._install_network_policy,
                container,
                {"role": "browser", "allowed_tcp": allowed_tcp},
                gate,
                runtime_instance_id,
                "browser",
            )
            return container
        except DockerException as e:
            raise DockerSandboxError(
                f"Failed to run browser container {b_name}: {e}"
            ) from e

    async def start_stream_container(
        self,
        profile_id: str,
        runtime_instance_id: str,
        browser_container_name: str,
        udp_mux_port: int,
        gateway_url: str = "ws://host.docker.internal:18097",
        agent_secret_path: Optional[Path] = None,
        public_ip: str = "127.0.0.1",
        display: str = ":99",
        media_addresses: Optional[dict[str, str]] = None,
    ) -> Any:
        if agent_secret_path is None or not agent_secret_path.is_file():
            raise DockerSandboxError(
                "Explicit Stream Agent credential file is required"
            )
        s_name = self.get_stream_container_name(profile_id)
        net_name = self.get_network_name(profile_id)
        dirs = self.prepare_profile_directories(profile_id)
        x11_socket = self.validator.validate_runtime_source(
            profile_id, dirs["x11"] / "X99"
        )
        xauth_file = self.validator.validate_runtime_source(
            profile_id, dirs["runtime"] / "Xauthority"
        )
        pulse_dir = dirs["pulse"]

        b_inspect = self.client.api.inspect_container(browser_container_name)
        browser_hostname = b_inspect.get("Config", {}).get("Hostname", "")

        self.cleanup_container_by_name(s_name)

        secret_file = self.validator.validate_runtime_source(
            profile_id, agent_secret_path
        )

        gate = self._prepare_policy_gate(profile_id, runtime_instance_id, "stream")
        allowed_tcp = []
        allowed_udp = []
        if media_addresses is not None:
            coturn_ip = media_addresses["coturn_ip"]
            allowed_tcp.extend([(coturn_ip, 3478), (coturn_ip, 5349)])
            allowed_udp.extend(
                (coturn_ip, port) for port in [3478, *range(50000, 51000)]
            )
        volumes = {
            str(gate): {"bind": "/run/cbrowser_policy", "mode": "ro"},
            str(x11_socket): {"bind": "/tmp/.X11-unix/X99", "mode": "ro"},
            str(xauth_file): {"bind": "/tmp/.Xauthority", "mode": "ro"},
            str(pulse_dir): {"bind": "/pulse", "mode": "ro"},
            str(secret_file): {"bind": "/tmp/secret.txt", "mode": "ro"},
        }

        env = {
            "PYTHONDONTWRITEBYTECODE": "1",
            "CBROWSER_WEBRTC_PUBLIC_IP": public_ip,
            "DISPLAY": display,
            "XAUTHORITY": "/tmp/.Xauthority",
            "CBROWSER_PROFILE_ID": profile_id,
            "CBROWSER_RUNTIME_INSTANCE_ID": runtime_instance_id,
            "CBROWSER_GATEWAY_URL": gateway_url,
            "CBROWSER_AGENT_SECRET_FILE": "/tmp/secret.txt",
            "CBROWSER_UDP_MUX_PORT": str(udp_mux_port),
            "CBROWSER_AUDIO_DEVICE": "cbrowser_sink.monitor",
            "CBROWSER_PULSE_DIR": "/pulse",
            "CBROWSER_X11_SOCKET": "/tmp/.X11-unix/X99",
            "SELKIES_PORT": "18096",
        }
        if media_addresses is not None:
            env.update(
                {
                    "SELKIES_STUN_HOST": media_addresses["coturn_ip"],
                    "SELKIES_STUN_PORT": "3478",
                    "SELKIES_TURN_HOST": media_addresses["coturn_ip"],
                    "SELKIES_TURN_PORT": "3478",
                }
            )

        ports = {f"{udp_mux_port}/udp": ("127.0.0.1", udp_mux_port)}

        try:
            container = self.client.containers.run(
                self.stream_image,
                entrypoint=self._gated_entrypoint(runtime_instance_id, "stream"),
                name=s_name,
                detach=True,
                user="1000:1000",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                hostname=browser_hostname,
                ipc_mode=f"container:{browser_container_name}",
                network=net_name,
                ports=ports,
                restart_policy={"Name": "no"},
                tmpfs={"/tmp": "rw,exec,nosuid,nodev,size=256m"},
                volumes=volumes,
                environment=env,
                labels={
                    "com.cbrowser.managed-by": "supervisor",
                    "com.cbrowser.profile-id": profile_id,
                    "com.cbrowser.instance-id": runtime_instance_id,
                    "com.cbrowser.role": "stream",
                    "com.cbrowser.network-policy": "v1",
                    "com.cbrowser.config-version": b_inspect["Config"]["Labels"][
                        "com.cbrowser.config-version"
                    ],
                    "com.cbrowser.prefix": self.resource_prefix,
                },
            )
            allowed_tcp.extend(
                await asyncio.to_thread(self._resolved_endpoint, container, gateway_url)
            )
            await asyncio.to_thread(
                self._install_network_policy,
                container,
                {
                    "role": "stream",
                    "udp_mux_port": udp_mux_port,
                    "allowed_tcp": allowed_tcp,
                    "allowed_udp": allowed_udp,
                },
                gate,
                runtime_instance_id,
                "stream",
            )
            return container
        except DockerException as e:
            raise DockerSandboxError(
                f"Failed to run stream container {s_name}: {e}"
            ) from e

    def cleanup_container_by_name(self, name: str) -> None:
        try:
            c = self.client.containers.get(name)
            labels = c.labels or {}
            # Strict safety check: only remove container if it matches our prefix label
            if (
                c.name == name
                and labels.get("com.cbrowser.prefix") == self.resource_prefix
                and labels.get("com.cbrowser.managed-by") == "supervisor"
                and labels.get("com.cbrowser.role") in {"browser", "stream"}
                and name
                == f"{self.resource_prefix}-{labels['com.cbrowser.role']}-"
                f"{labels.get('com.cbrowser.profile-id')}"
            ):
                c.remove(force=True)
                logger.info(f"Removed container {name}")
            else:
                raise DockerSandboxError("Docker container ownership mismatch")
        except NotFound:
            pass
        except DockerException as e:
            raise DockerSandboxError(
                f"Container removal failed: {type(e).__name__}"
            ) from None

    def cleanup_network_by_name(self, name: str) -> None:
        try:
            net = self.client.networks.get(name)
            self._require_network_ownership(net, name)
            net.reload()
            containers = net.attrs.get("Containers") or {}
            infra_to_disconnect = []
            for cid in list(containers.keys()):
                try:
                    c = self.client.containers.get(cid)
                except DockerException as e:
                    raise DockerSandboxError(
                        f"Failed to inspect endpoint container {cid} in "
                        f"network {name}: {e}"
                    ) from e
                labels = c.labels or {}
                prefix = labels.get("com.cbrowser.prefix")
                managed = labels.get("com.cbrowser.managed-by")
                role = labels.get("com.cbrowser.role")
                if prefix != self.resource_prefix or managed != "supervisor":
                    raise DockerSandboxError(
                        f"Unknown endpoint container {c.name} ({cid}) in network {name}"
                    )
                if role in {"browser", "stream"}:
                    raise DockerSandboxError(
                        f"Cannot cleanup network {name}: runtime container "
                        f"{c.name} (role={role}) is still attached"
                    )
                if role in {"gateway", "coturn"}:
                    infra_to_disconnect.append(c)
                else:
                    raise DockerSandboxError(
                        f"Unauthorized container role {role} in network {name}"
                    )

            for c in infra_to_disconnect:
                try:
                    net.disconnect(c)
                except DockerException as e:
                    raise DockerSandboxError(
                        f"Failed to disconnect endpoint {c.name} from {name}: {e}"
                    ) from e
            net.remove()
            logger.info(f"Removed network {name}")
        except NotFound:
            pass
        except DockerSandboxError:
            raise
        except DockerException as e:
            raise DockerSandboxError(
                f"Network removal failed: {type(e).__name__}"
            ) from None

    async def teardown_profile(self, profile_id: str) -> None:
        s_name = self.get_stream_container_name(profile_id)
        b_name = self.get_browser_container_name(profile_id)
        net_name = self.get_network_name(profile_id)

        self.cleanup_container_by_name(s_name)
        self.cleanup_container_by_name(b_name)
        self.cleanup_network_by_name(net_name)

        self.cleanup_network_by_name(self.get_browser_network_name(profile_id))

    def _runtime_policy_ready(self, container: Any) -> bool:
        labels = container.labels or {}
        if labels.get("com.cbrowser.network-policy") != "v1":
            return False
        profile = labels.get("com.cbrowser.profile-id")
        instance = labels.get("com.cbrowser.instance-id")
        role = labels.get("com.cbrowser.role")
        try:
            expected = (
                self.validator.data_root / "control" / "gates" / profile / instance
            )
            for mount in container.attrs.get("Mounts", []):
                if mount.get("Destination") != "/run/cbrowser_policy":
                    continue
                if mount.get("RW") is not False:
                    return False
                gate = self.validator.validate_safe_path(Path(mount["Source"]))
                if gate.parent != expected or not gate.name.startswith(role + "_"):
                    return False
                marker = gate / "ready.json"
                if marker.is_symlink():
                    return False
                value = json.loads(marker.read_text(encoding="utf-8"))
                return value == {
                    "instance_id": instance,
                    "role": role,
                    "status": "ready",
                }
        except (OSError, ValueError, TypeError, KeyError):
            return False
        return False

    def scan_active_containers(self) -> list[dict[str, Any]]:
        try:
            containers = self.client.containers.list(
                all=True,
                filters={"label": f"com.cbrowser.prefix={self.resource_prefix}"},
            )
            result = []
            for c in containers:
                labels = c.labels or {}
                if labels.get("com.cbrowser.role") not in {"browser", "stream"}:
                    continue
                result.append(
                    {
                        "id": c.id,
                        "name": c.name,
                        "status": c.status,
                        "profile_id": labels.get("com.cbrowser.profile-id"),
                        "instance_id": labels.get("com.cbrowser.instance-id"),
                        "role": labels.get("com.cbrowser.role"),
                        "config_version": labels.get("com.cbrowser.config-version"),
                        "policy_ready": self._runtime_policy_ready(c),
                    }
                )
            return result
        except DockerException as e:
            raise DockerSandboxError(
                f"Container scan failed: {type(e).__name__}"
            ) from None
