"""Docker Adapter for CBrowser Runtime Supervisor."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import docker
import requests
from cbrowser.domain.proxy_endpoint import (
    HOST_GATEWAY_HOSTNAME,
    ProxyEndpoint,
    map_endpoint_for_container,
)
from cbrowser.engine_artifacts import (
    EngineArtifactError,
    enforce_pinned_engine_env,
    get_approved_artifact,
)
from cbrowser.shared.endpoints import DEFAULT_GATEWAY_PORT, GatewayEndpoint
from cbrowser.shared.egress import ECHO_URLS
from cbrowser.redact import docker_error_detail, redact
from cbrowser.runtime_agent.fontconfig import FONT_SET_MOUNT_ROOT
from cbrowser.runtime_agent.socket_root import (
    AGENT_SOCKET_PATH_ENV,
    agent_socket_path,
)
from cbrowser.supervisor.address_pool import (
    MediaNetworkPlan,
    MediaPoolExhaustedError,
    MediaSubnetAllocator,
    host_route_networks,
    media_network_labels,
    plan_from_labels,
)
from cbrowser.supervisor.container_spec import (
    browser_command,
    browser_labels,
    cache_init_environment,
    cache_init_labels,
    container_runtime_instance_id,
    gated_entrypoint,
    policy_helper_labels,
    probe_helper_labels,
    stream_environment,
    stream_labels,
    stream_ports,
    x11_helper_labels,
)
from cbrowser.shared.atomic_write import atomic_write_text
from cbrowser.supervisor.gate_identity import gate_labels
from cbrowser.supervisor.network_policy import NetworkPolicySpec
from cbrowser.supervisor.network_spec import (
    browser_network_name,
    endpoint_port,
    network_labels,
    network_ownership_matches,
    probe_network_name,
    profile_network_name,
)
from cbrowser.supervisor.path_validator import (
    AGENT_SOCKET_ROOT_ENV,
    PathSecurityError,
    PathValidator,
    SocketRootError,
    prepare_socket_dir,
    validate_socket_deployment,
)
from cbrowser.supervisor.volume_spec import (
    SINGLETON_LOCK_NAMES,
    browser_volumes,
    cache_init_volumes,
    stream_volumes,
)
from cbrowser.udp_mux import udp_mux_bounds
from docker.errors import DockerException, NotFound

logger = logging.getLogger("cbrowser.supervisor.docker_adapter")

PROXY_CREDENTIALS_FILENAME = "proxy_credentials.json"
_PROXY_SCHEMES = frozenset({"http", "https", "socks5"})


def proxy_endpoint_from_credentials(creds_path: Path) -> str | None:
    """Build the proxy URL used for Browser egress policy resolution.

    The old ``config.proxy`` field no longer exists; the connection parameters
    now live in the mounted credentials file. Returns ``None`` when there is
    no proxy or the file is unusable, which yields an empty ``allowed_tcp``.
    """
    try:
        creds = json.loads(creds_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(creds, dict):
        return None
    scheme = creds.get("scheme")
    host = creds.get("host")
    port = creds.get("port")
    if (
        isinstance(scheme, str)
        and scheme in _PROXY_SCHEMES
        and isinstance(host, str)
        and host
        and type(port) is int
        and 1 <= port <= 65535
    ):
        netloc_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
        return f"{scheme}://{netloc_host}:{port}"
    return None


def _udp_mux_helper_environment() -> dict[str, str]:
    minimum, maximum = udp_mux_bounds()
    return {
        "CBROWSER_UDP_MUX_MIN_PORT": str(minimum),
        "CBROWSER_UDP_MUX_MAX_PORT": str(maximum),
    }


_HELPER_LOG_TAIL_BYTES = 2000


def _helper_log_tail(helper: Any) -> str:
    """Truncated, redacted tail of a policy helper's output for logging.

    A failing ``logs()`` never masks the primary outcome: it yields an
    empty summary instead.
    """
    try:
        raw = helper.logs()
    except Exception:  # noqa: BLE001 - a failing logs() never masks the primary outcome
        return ""
    if isinstance(raw, bytes):
        output = raw[-_HELPER_LOG_TAIL_BYTES:].decode("utf-8", errors="replace")
    else:
        output = str(raw)[-_HELPER_LOG_TAIL_BYTES:]
    return redact(output)


def _parse_profile_number(raw: Any) -> int | None:
    """Parse a zero-padded profile-number label; invalid means unusable."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= 1 else None
    if isinstance(raw, str) and raw.isdigit():
        value = int(raw)
        return value if value >= 1 else None
    return None


def _parse_config_version(raw: Any) -> int | None:
    """Parse a config-version label; missing or malformed means unusable."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= 1 else None
    if isinstance(raw, str) and raw.isdigit():
        value = int(raw)
        return value if value >= 1 else None
    return None


class DockerSandboxError(Exception):
    pass


class LoopbackMappingError(DockerSandboxError):
    """The Docker daemon could not map a loopback proxy to the host
    gateway (t052 AC-011): the Browser/probe must fail *before* starting,
    with a remediation, never start successfully and then fail to connect.
    """


class EgressProbeFailure(Exception):
    """The probe helper ran and reported a failure (t052).

    ``code`` is the machine-readable probe error (``echo_unreachable``,
    ``geoip_db_missing``, ...) and is recorded on the observation; it is
    not a Docker/transport failure.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class StreamResidue:
    profile_id: str
    runtime_instance_id: str
    container_id: str | None
    container_name: str | None


class StreamContainerResidueError(DockerSandboxError):
    def __init__(
        self,
        residue: StreamResidue,
        cause_type: str,
        cause_detail: str | None = None,
    ) -> None:
        message = "Stream container cleanup pending"
        if cause_detail:
            message = f"{message}: {cause_detail}"
        super().__init__(message)
        self.residue = residue
        self.cause_type = cause_type
        self.cause_detail = cause_detail


CACHE_GENERATION_FILENAME = ".cbrowser-cache-generation.json"


@dataclass(frozen=True)
class _CacheGeneration:
    """A fully validated, sealed cache tree generation (t022 A44).

    Trust basis for reuse: the root's identity (resolved path + device +
    inode) plus the sidecar record the Supervisor itself sealed after a
    complete tree validation. Any mismatch — unknown root, missing or
    altered sidecar, changed identity — falls back to full validation.

    Scope of the seal: the fingerprint covers each entry's relative path,
    kind, size and mtime, and symlink targets. It is NOT a content hash —
    the model relies on the deployment invariant that only the Supervisor
    writes these trees (runtime consumers mount them read-only). A writer
    outside that invariant could alter file contents while preserving
    size and mtime undetected; deployments that cannot hold the invariant
    must not treat a sealed generation as content proof.
    """

    root_identity: tuple[str, int, int]
    generation: int
    fingerprint: str
    entry_count: int


class DockerAdapter:
    def __init__(
        self,
        path_validator: PathValidator,
        engine_cache_dir: Path | str,
        docker_client: docker.DockerClient | None = None,
        browser_image: str | None = None,
        stream_image: str | None = None,
        resource_prefix: str = "cbrowser-t005",
        geoip_cache_dir: Path | str | None = None,
        policy_image: str | None = None,
        runtime_uid: int = 1000,
        runtime_gid: int = 1000,
        manage_ownership: bool = False,
        media_subnet_pool: str | None = None,
        deployment_instance_id: str | None = None,
        network_timeout: float | None = None,
        engine_build: str | None = None,
        expected_binary_sha256: str | None = None,
    ):
        self.validator = path_validator
        self.engine_cache = self.validator.validate_safe_path(engine_cache_dir)
        self.geoip_cache = self.validator.validate_safe_path(
            geoip_cache_dir or self.engine_cache / "geoip"
        )
        self.engine_cache.mkdir(parents=True, exist_ok=True)
        self.geoip_cache.mkdir(parents=True, exist_ok=True)
        self._cache_generations: dict[Path, _CacheGeneration] = {}
        self._cache_generations_stale: set[Path] = set()
        self._validate_cache_paths()
        self.client = docker_client or docker.from_env()
        self.browser_image = browser_image or os.environ.get("CBROWSER_BROWSER_IMAGE")
        self.stream_image = stream_image or os.environ.get("CBROWSER_STREAM_IMAGE")
        for image in (self.browser_image, self.stream_image):
            if not image or not (image.startswith("sha256:") or "@sha256:" in image):
                raise ValueError(
                    "Explicit immutable Browser and Stream images are required"
                )
        # A22: explicitly supplied prefixes are validated at the
        # deployment entry points (deploy.sh and Supervisor startup in
        # runner main). Construction is not an entry point: the value
        # arriving here is already validated, or is the compiled-in
        # default deployment prefix "cbrowser-t005", which predates the
        # A22 pattern and is not deployment input.
        self.resource_prefix = resource_prefix
        # Deployment identity (A59/AC-021): the deployment this Supervisor
        # belongs to. It is written as the com.cbrowser.instance-id label
        # on every resource this deployment creates, and scans only claim
        # sandboxes, helpers, gateways and networks carrying this label
        # value. Per-launch runtime instance ids are not labels; they
        # travel in the containers' runtime configuration.
        self.deployment_instance_id = deployment_instance_id or os.environ.get(
            "CBROWSER_INSTANCE_ID"
        ) or None
        # AC-015: Docker calls for network allocation/creation must not
        # hang the Supervisor forever; each call is bounded by this
        # timeout (seconds), overridable via CBROWSER_DOCKER_NETWORK_TIMEOUT.
        self.network_timeout = network_timeout
        if self.network_timeout is None:
            try:
                self.network_timeout = float(
                    os.environ.get("CBROWSER_DOCKER_NETWORK_TIMEOUT", "30")
                )
            except ValueError:
                self.network_timeout = 30.0
        self._reserved_subnets: set[str] = set()
        self.runtime_uid = runtime_uid
        self.runtime_gid = runtime_gid
        self.manage_ownership = manage_ownership
        self._profile_numbers: dict[str, int] = {}
        self.policy_image = policy_image or os.environ.get(
            "CBROWSER_NETWORK_POLICY_IMAGE"
        )
        self.media_allocator = MediaSubnetAllocator(
            media_subnet_pool
            or os.environ.get("CBROWSER_MEDIA_SUBNET_POOL")
            or "10.251.0.0/16"
        )
        self._cache_lock = asyncio.Lock()
        # Media subnet allocation reads Docker's network list and then
        # creates the allocation; concurrent launches must not pick the
        # same subnet from the same snapshot. The lock guards only the
        # snapshot+allocate+reserve phase; the Docker create itself runs
        # outside it (AC-015: a hung create must not stall every Profile).
        # Subnets reserved by an in-flight create are recorded in
        # ``_reserved_subnets`` so a concurrent allocation never reuses
        # them; a failed create discards its reservation.
        self._media_network_lock = threading.Lock()
        self._binary_ready = False
        self._geoip_ready = False
        requested_build = engine_build or os.environ.get("CBROWSER_ENGINE_BUILD") or None
        artifact = get_approved_artifact(engine_build=requested_build)
        self.engine_build = artifact.engine_build
        requested_sha = expected_binary_sha256 or os.environ.get("CBROWSER_ENGINE_BINARY_SHA256") or None
        if (
            requested_sha
            and artifact.binary_sha256
            and requested_sha.strip().lower() != artifact.binary_sha256.lower()
        ):
            raise ValueError(
                "Configured engine binary SHA-256 conflicts with approved ADR 021 artifact manifest"
            )
        self.expected_binary_sha256 = requested_sha or artifact.binary_sha256

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
        return gated_entrypoint(instance_id, role)

    def _resolved_endpoint(self, container: Any, url: str) -> list[tuple[str, int]]:
        parsed = urlsplit(url if "://" in url else "http://" + url)
        if not parsed.hostname:
            raise DockerSandboxError("Network endpoint hostname is required")
        port = parsed.port or endpoint_port(parsed.scheme)
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
        cleanup_error = None
        try:
            try:
                helper = self.client.containers.create(
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
                    environment=_udp_mux_helper_environment(),
                    tmpfs={
                        "/run": "rw,nosuid,nodev,size=4m",
                        "/tmp": "rw,nosuid,nodev,size=4m",
                    },
                    labels=gate_labels(policy_helper_labels(
                        self.resource_prefix,
                        deployment_id=self.deployment_instance_id,
                    )),
                )
                helper.start()
            except DockerSandboxError:
                raise
            except (requests.exceptions.RequestException, DockerException) as exc:
                # AC-011: a helper container that fails to START keeps the
                # redacted Docker root cause -- a Docker API error has known
                # shapes and the shared rules cover its credential forms.
                raise DockerSandboxError(
                    "Runtime network policy installation failed: "
                    + docker_error_detail(exc)
                ) from None
            except Exception as exc:  # noqa: BLE001 - any SDK/transport error maps to one redacted outcome
                raise DockerSandboxError(
                    "Runtime network policy installation failed: "
                    + docker_error_detail(exc)
                ) from None
            try:
                result = helper.wait(timeout=30)
                if result.get("StatusCode") != 0:
                    # t055 A4: capture the helper output BEFORE the finally
                    # below removes the helper; the log carries a truncated,
                    # redacted summary, never raw output.
                    logger.error(
                        "Network policy installation failed: exit=%s helper_output=%s",
                        result.get("StatusCode"),
                        _helper_log_tail(helper),
                    )
                    raise DockerSandboxError(
                        "Runtime network policy installation failed"
                    )
            except DockerSandboxError:
                raise
            except Exception as exc:  # noqa: BLE001 - A11: wait/transport errors stay redacted
                # A11: a helper wait timeout or transport error must stay
                # redacted -- its text is transport-level and can carry
                # arbitrary URLs, so only the type name is reported, never
                # the text.
                raise DockerSandboxError(
                    "Runtime network policy installation failed: " + type(exc).__name__
                ) from None
        finally:
            if helper is not None:
                try:
                    helper.remove(force=True)
                except Exception as exc:  # noqa: BLE001 - cleanup never masks the primary outcome
                    cleanup_error = exc
                    logger.warning(
                        "Failed to remove network policy helper: error_type=%s",
                        type(exc).__name__,
                    )
        if cleanup_error is not None:
            raise DockerSandboxError(
                "Runtime network policy helper cleanup failed"
            ) from None
        atomic_write_text(
            gate / "ready.json",
            json.dumps({"instance_id": instance_id, "role": role, "status": "ready"}),
            mode=0o644,
        )

    def run_egress_probe(
        self,
        *,
        proxy_id: str,
        endpoint: ProxyEndpoint,
        credentials: dict[str, Any],
        echo_urls: tuple[str, ...] | list[str] | None = None,
        timeout: float = 90.0,
    ) -> tuple[str, str | None]:
        """Run one egress probe in a short-lived helper container (t052).

        The helper shares the Browser's network posture: its own bridge
        network, a browser-role policy that allows only the (mapped)
        proxy endpoint, and the same proxy parameters the Browser would
        use.  It fetches an IP-echo endpoint through the proxy and
        resolves the country against the local GeoLite2 database, then
        prints one JSON object.  Returns ``(egress_ip, country_code)``.

        Raises :class:`EgressProbeFailure` when the helper ran and
        reported a probe error (recorded as a failed observation),
        :class:`LoopbackMappingError` when a loopback endpoint cannot be
        mapped to the host gateway, and :class:`DockerSandboxError` for
        transport/container failures.
        """
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", proxy_id or ""):
            raise DockerSandboxError("Invalid proxy identity")
        runtime_endpoint = map_endpoint_for_container(endpoint)
        probe_id = uuid.uuid4().hex[:12]
        probe_dir = self.validator.validate_safe_path(
            self.validator.data_root / "control" / "probe" / probe_id,
            allow_create=True,
        )
        probe_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
        gate = probe_dir / "gate"
        gate.mkdir(mode=0o755, exist_ok=False)
        net_name = probe_network_name(self.resource_prefix, probe_id)
        helper = None
        network = None
        try:
            creds_file = self._write_probe_credentials(
                probe_dir, runtime_endpoint, credentials
            )
            network = self._create_probe_network(net_name, probe_id)
            helper = self._create_probe_helper(
                net_name, probe_id, creds_file, endpoint
            )
            self._install_probe_network_policy(
                helper, runtime_endpoint, gate, probe_id
            )
            output = self._exec_probe_helper(
                helper, self._probe_helper_command(echo_urls), timeout
            )
            return self._parse_probe_output(output)
        finally:
            self._cleanup_probe_resources(helper, network, probe_dir)

    @staticmethod
    def _write_probe_credentials(
        probe_dir: Path,
        runtime_endpoint: ProxyEndpoint,
        credentials: dict[str, Any],
    ) -> Path:
        """Write the (mapped) endpoint + credentials for the helper.

        The file is 0600 and lives under the probe dir, which is removed
        together with the helper and network when the probe finishes."""
        creds_file = probe_dir / PROXY_CREDENTIALS_FILENAME
        atomic_write_text(
            creds_file,
            json.dumps(
                {
                    "scheme": runtime_endpoint.scheme,
                    "host": runtime_endpoint.host,
                    "port": runtime_endpoint.port,
                    "username": runtime_endpoint.username,
                    "password": credentials.get("password"),
                    "credential_revision": credentials.get(
                        "credential_revision"
                    ),
                }
            ),
            mode=0o600,
        )
        return creds_file

    def _create_probe_network(self, net_name: str, probe_id: str):
        """One throwaway bridge network per probe."""
        try:
            return self.client.networks.create(
                net_name,
                driver="bridge",
                labels=network_labels(
                    self.resource_prefix,
                    f"probe-{probe_id}",
                    deployment_id=self.deployment_instance_id,
                ),
            )
        except (requests.exceptions.RequestException, DockerException) as exc:
            raise DockerSandboxError(
                "Egress probe network creation failed: "
                + docker_error_detail(exc)
            ) from None

    def _create_probe_helper(
        self,
        net_name: str,
        probe_id: str,
        creds_file: Path,
        endpoint: ProxyEndpoint,
    ):
        """Sleeping helper container on the probe network.

        A loopback endpoint maps to the host gateway, so the helper can
        reach the host-local proxy; a daemon that cannot honour
        ``host-gateway`` extra hosts fails here as a LoopbackMappingError
        with a remediation hint, never as a silently-unreachable probe.
        """
        is_loopback = endpoint.is_loopback
        extra_hosts = (
            {HOST_GATEWAY_HOSTNAME: "host-gateway"} if is_loopback else None
        )
        try:
            return self.client.containers.run(
                self.browser_image,
                entrypoint=["python3", "-c", "import time; time.sleep(300)"],
                name=f"{self.resource_prefix}-probe-{probe_id}",
                detach=True,
                user="1000:1000",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                network=net_name,
                extra_hosts=extra_hosts,
                tmpfs={"/tmp": "rw,nosuid,nodev,size=4m"},
                volumes={
                    str(creds_file): {
                        "bind": "/run/cbrowser/runtime/proxy_credentials.json",
                        "mode": "ro",
                    },
                    str(self.geoip_cache): {
                        "bind": "/data/engine-cache/geoip",
                        "mode": "ro",
                    },
                },
                labels=probe_helper_labels(
                    self.resource_prefix,
                    deployment_id=self.deployment_instance_id,
                ),
            )
        except (requests.exceptions.RequestException, DockerException) as exc:
            detail = docker_error_detail(exc)
            if is_loopback and (
                "host-gateway" in detail.lower()
                or "extra_hosts" in detail.lower()
            ):
                raise LoopbackMappingError(
                    "Loopback proxy mapping failed: the Docker daemon "
                    "could not map host.docker.internal to the host "
                    "gateway, so the probe cannot reach the host-local "
                    f"proxy at {endpoint.host}:{endpoint.port}. "
                    "Use a Docker daemon that supports host-gateway "
                    "extra hosts (Docker 20.10+ / OrbStack), or move "
                    "the proxy to a non-loopback address."
                ) from None
            raise DockerSandboxError(
                "Egress probe helper creation failed: " + detail
            ) from None

    def _install_probe_network_policy(
        self,
        helper,
        runtime_endpoint: ProxyEndpoint,
        gate: Path,
        probe_id: str,
    ) -> None:
        """Browser-role policy that allows only the (mapped) proxy endpoint."""
        host_for_policy = runtime_endpoint.host
        if ":" in host_for_policy and not host_for_policy.startswith("["):
            host_for_policy = f"[{host_for_policy}]"
        allowed = self._resolved_endpoint(
            helper,
            f"{runtime_endpoint.scheme}://{host_for_policy}:{runtime_endpoint.port}",
        )
        self._install_network_policy(
            helper,
            {"role": "browser", "allowed_tcp": allowed},
            gate,
            f"probe-{probe_id}",
            "browser",
        )

    @staticmethod
    def _probe_helper_command(
        echo_urls: tuple[str, ...] | list[str] | None,
    ) -> list[str]:
        command = [
            "python3",
            "-m",
            "cbrowser.runtime_agent.egress_probe",
            "--credentials-file",
            "/run/cbrowser/runtime/proxy_credentials.json",
            "--geoip-db",
            "/data/engine-cache/geoip/GeoLite2-City.mmdb",
        ]
        for url in echo_urls if echo_urls is not None else ECHO_URLS:
            command += ["--echo-url", url]
        return command

    def _exec_probe_helper(
        self, helper, command: list[str], timeout: float
    ) -> str:
        """Run the probe module in the helper with a hard timeout.

        Returns the helper's stdout; a non-zero exit, a transport error
        or a timeout is a DockerSandboxError (the helper never ran to a
        probe verdict)."""
        outcome: dict[str, Any] = {}
        error: dict[str, BaseException] = {}

        def _exec() -> None:
            try:
                result = helper.exec_run(command, user="1000:1000")
                outcome["exit_code"] = result[0]
                raw = result[1]
                outcome["output"] = (
                    raw.decode("utf-8", errors="replace")
                    if isinstance(raw, (bytes, bytearray))
                    else str(raw)
                )
            except BaseException as exc:  # noqa: BLE001 - re-raised below
                error["error"] = exc

        worker = threading.Thread(target=_exec, daemon=True)
        worker.start()
        worker.join(timeout=timeout)
        if worker.is_alive():
            raise DockerSandboxError("Egress probe timed out")
        if "error" in error:
            raise DockerSandboxError(
                "Egress probe execution failed: "
                + docker_error_detail(error["error"])
            ) from None
        if outcome.get("exit_code") != 0:
            raise DockerSandboxError("Egress probe helper failed")
        return outcome.get("output") or ""

    @staticmethod
    def _parse_probe_output(output: str) -> tuple[str, str | None]:
        """One JSON line from the helper: a reported error_code becomes
        an EgressProbeFailure (recorded as a failed observation); a
        malformed line is a DockerSandboxError."""
        try:
            payload = json.loads(output.strip())
        except ValueError:
            raise DockerSandboxError(
                "Egress probe helper returned invalid output"
            ) from None
        if not isinstance(payload, dict):
            raise DockerSandboxError(
                "Egress probe helper returned invalid output"
            )
        if "error_code" in payload:
            raise EgressProbeFailure(str(payload["error_code"]))
        egress_ip = payload.get("egress_ip")
        if not isinstance(egress_ip, str) or not egress_ip:
            raise DockerSandboxError(
                "Egress probe helper returned no egress IP"
            )
        country = payload.get("country_code")
        return egress_ip, country if isinstance(country, str) else None

    @staticmethod
    def _cleanup_probe_resources(helper, network, probe_dir: Path) -> None:
        """Remove helper, network and probe dir; cleanup never masks the
        probe outcome."""
        if helper is not None:
            try:
                helper.remove(force=True)
            except Exception as exc:  # noqa: BLE001 - cleanup never masks the outcome
                logger.warning(
                    "Failed to remove egress probe helper: error_type=%s",
                    type(exc).__name__,
                )
        if network is not None:
            try:
                network.remove()
            except Exception as exc:  # noqa: BLE001 - cleanup never masks the outcome
                logger.warning(
                    "Failed to remove egress probe network: error_type=%s",
                    type(exc).__name__,
                )
        shutil.rmtree(probe_dir, ignore_errors=True)

    def _validate_cache_paths(self) -> None:
        for root in (self.engine_cache, self.geoip_cache):
            self._validate_cache_root(root)

    def _validate_cache_root(self, root: Path) -> None:
        """Reuse a sealed generation when possible; validate fully otherwise.

        The fast path is a fingerprint check, not a blind trust: the tree
        fingerprint (entry set, kinds, symlink targets, file size+mtime)
        is recomputed and compared against the sealed record together
        with the root identity and the sidecar contents. Any drift — a
        file swapped for a symlink, entries added or removed — falls back
        to the complete per-entry validation, after which the new
        generation is sealed atomically. What the fast path saves is the
        per-entry PathValidator rule evaluation, not the tree walk.
        """
        validated_root = self.validator.validate_safe_path(root)
        stat = os.stat(validated_root)
        identity = (str(validated_root), stat.st_dev, stat.st_ino)
        record = self._cache_generations.get(root)
        if (
            record is not None
            and root not in self._cache_generations_stale
            and record.root_identity == identity
            and self._cache_sidecar_matches(root, record)
        ):
            fingerprint, entry_count = self._cache_tree_fingerprint(root)
            if fingerprint == record.fingerprint and entry_count == record.entry_count:
                return
        if root == self.engine_cache:
            self._binary_ready = False
        for item in root.rglob("*"):
            self.validator.validate_safe_path(item)
        fingerprint, entry_count = self._cache_tree_fingerprint(root)
        generation = self._next_cache_generation(root, record)
        sealed = _CacheGeneration(
            root_identity=identity,
            generation=generation,
            fingerprint=fingerprint,
            entry_count=entry_count,
        )
        self._write_cache_sidecar(root, sealed)
        self._cache_generations[root] = sealed
        self._cache_generations_stale.discard(root)

    def _next_cache_generation(
        self, root: Path, record: _CacheGeneration | None
    ) -> int:
        """Generation numbers stay monotonic across process restarts: a
        fresh process continues from the sidecar it finds on disk instead
        of restarting at 1 and overwriting the previous seal's number."""
        candidates = [0]
        if record is not None:
            candidates.append(record.generation)
        try:
            payload = json.loads(
                (root / CACHE_GENERATION_FILENAME).read_text(encoding="utf-8")
            )
            if isinstance(payload, dict) and isinstance(
                payload.get("generation"), int
            ):
                candidates.append(payload["generation"])
        except (OSError, ValueError):
            pass
        return max(candidates) + 1

    def _cache_sidecar_matches(self, root: Path, record: _CacheGeneration) -> bool:
        try:
            payload = json.loads(
                (root / CACHE_GENERATION_FILENAME).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return False
        return (
            isinstance(payload, dict)
            and payload.get("generation") == record.generation
            and payload.get("fingerprint") == record.fingerprint
            and payload.get("entry_count") == record.entry_count
        )

    def _write_cache_sidecar(self, root: Path, record: _CacheGeneration) -> None:
        payload = json.dumps(
            {
                "generation": record.generation,
                "fingerprint": record.fingerprint,
                "entry_count": record.entry_count,
            },
            sort_keys=True,
        )
        # Atomic switch via the shared storage helper: the new generation
        # becomes visible in one rename, never as a half-written record.
        atomic_write_text(root / CACHE_GENERATION_FILENAME, payload)

    @staticmethod
    def _cache_tree_fingerprint(root: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        entries = []
        for item in root.rglob("*"):
            if item.name == CACHE_GENERATION_FILENAME:
                continue
            relative = item.relative_to(root).as_posix()
            if item.is_symlink():
                entries.append((relative, "link", os.readlink(item)))
            elif item.is_dir():
                entries.append((relative, "dir", ""))
            elif item.is_file():
                stat = item.stat()
                entries.append(
                    (relative, "file", f"{stat.st_size}:{stat.st_mtime_ns}")
                )
            else:
                entries.append((relative, "other", ""))
        for relative, kind, detail in sorted(entries):
            digest.update(f"{relative}\0{kind}\0{detail}\n".encode())
        return digest.hexdigest(), len(entries)

    async def cleanup_orphan_helpers(self) -> None:
        """Reap prior coordinator helpers once, under the startup coordinator lock.

        Never call from periodic reconciliation: a live installer may be running.
        All candidates are validated before removing any container.
        """
        await asyncio.to_thread(self._cleanup_orphan_helpers)

    def _owns_deployment(self, labels: dict[str, Any]) -> bool:
        """Deployment ownership test (A59/AC-021, strict t069).

        A resource belongs to this Supervisor only when its
        ``com.cbrowser.instance-id`` label carries the same deployment
        instance id. Missing or mismatched labels mean "not ours":
        skip, never claim, never delete. An unconfigured Supervisor
        owns nothing — configuration is required at startup
        (``run_supervisor``), so this state must never arise in
        production.
        """
        if not self.deployment_instance_id:
            return False
        return labels.get("com.cbrowser.instance-id") == self.deployment_instance_id

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
            if role not in {"cache-init", "network-policy", "x11-permissions"}:
                continue
            name_role = {
                "cache-init": "cache",
                "network-policy": "policy",
                "x11-permissions": "x11",
            }[role]
            if (
                labels.get("com.cbrowser.prefix") != self.resource_prefix
                or labels.get("com.cbrowser.managed-by") != "supervisor"
                or not self._owns_deployment(labels)
                or not re.fullmatch(
                    re.escape(f"{self.resource_prefix}-{name_role}-") + r"[0-9a-f]{12}",
                    container.name,
                )
            ):
                logger.warning(
                    "Orphan helper identity mismatch retained: role=%s",
                    role,
                )
                continue
            owned.append(container)
        for container in owned:
            try:
                container.remove(force=True)
            except NotFound:
                pass

    async def ensure_runtime_cache(self, need_geoip: bool) -> None:
        try:
            enforce_pinned_engine_env(
                os.environ,
                expected_build=self.engine_build,
                expected_binary_sha256=self.expected_binary_sha256,
            )
        except EngineArtifactError as exc:
            raise DockerSandboxError(
                f"Engine artifact pinning check failed: {exc}"
            ) from None
        async with self._cache_lock:
            if self._binary_ready and (not need_geoip or self._geoip_ready):
                return
            await asyncio.to_thread(self._initialize_cache, need_geoip)
            # Initialization may have rewritten the trees: the sealed
            # generations no longer describe them, so the next validation
            # is a full one and seals a new generation.
            self._cache_generations_stale.update(
                (self.engine_cache, self.geoip_cache)
            )
            self._validate_cache_paths()
            self._binary_ready = True
            self._geoip_ready = self._geoip_ready or need_geoip

    def _initialize_cache(self, need_geoip: bool) -> None:
        try:
            enforce_pinned_engine_env(
                os.environ,
                expected_build=self.engine_build,
                expected_binary_sha256=self.expected_binary_sha256,
            )
        except EngineArtifactError as exc:
            raise DockerSandboxError(
                f"Engine artifact pinning check failed: {exc}"
            ) from None
        # Only the initializer receives writable cache mounts. Runtime consumers
        # see the completed cache read-only, including GeoIP data.
        (self.engine_cache / "geoip").mkdir(exist_ok=True)
        run_id = uuid.uuid4().hex
        marker_name = f"cache_init_{run_id}.json"
        marker = self.engine_cache / marker_name
        script = """import json, os
from pathlib import Path
from cbrowser.engine_artifacts import (
    detect_auto_update_markers,
    enforce_pinned_engine_env,
    verify_extracted_engine_cache,
    verify_wrapper_package,
)
from cloakbrowser.download import ensure_binary

cache_dir = Path('/data/engine-cache')
pinned_build = os.environ['CBROWSER_ENGINE_BUILD']
enforce_pinned_engine_env(
    os.environ,
    expected_build=pinned_build,
    expected_binary_sha256=os.environ.get('CBROWSER_ENGINE_BINARY_SHA256'),
)
verify_wrapper_package()
if detect_auto_update_markers(cache_dir):
    raise RuntimeError('Forbidden auto-update marker present in engine cache')
binary = Path(ensure_binary(browser_version=pinned_build))
if not binary.is_file():
    raise RuntimeError('Browser binary initialization did not complete')
verify_extracted_engine_cache(cache_dir, engine_build=pinned_build, run_version_probe=True)
if os.environ['CBROWSER_INIT_GEOIP'] == '1':
    from cloakbrowser.geoip import _ensure_geoip_db
    database = _ensure_geoip_db()
    if database is None or not database.is_file():
        raise RuntimeError('GeoIP initialization did not complete')
path = cache_dir / os.environ['CBROWSER_INIT_MARKER']
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
                volumes=cache_init_volumes(
                    engine_cache=self.engine_cache,
                    geoip_cache=self.geoip_cache,
                ),
                environment=cache_init_environment(
                    need_geoip,
                    marker_name,
                    run_id,
                    engine_build=self.engine_build,
                ),
                labels=gate_labels(cache_init_labels(
                    self.resource_prefix,
                    deployment_id=self.deployment_instance_id,
                )),
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
                f"Runtime cache initializer failed: {docker_error_detail(exc)}"
            ) from None
        finally:
            marker.unlink(missing_ok=True)
            if helper is not None:
                helper.remove(force=True)
        self._apply_cache_permissions()

    def _apply_cache_permissions(self) -> None:
        """Give the read-only runtime user access without world-writable modes."""
        for root in (self.engine_cache, self.geoip_cache):
            for path in [root, *root.rglob("*")]:
                if path.is_symlink():
                    continue
                if self.manage_ownership:
                    stat = path.stat()
                    if (
                        stat.st_uid != self.runtime_uid
                        or stat.st_gid != self.runtime_gid
                    ):
                        try:
                            os.chown(
                                path,
                                self.runtime_uid,
                                self.runtime_gid,
                                follow_symlinks=False,
                            )
                        except OSError as exc:
                            raise DockerSandboxError(
                                "Cannot assign runtime cache ownership: "
                                f"{type(exc).__name__}"
                            ) from None
                if path.is_dir() or path.stat().st_mode & 0o111:
                    mode = 0o750
                else:
                    mode = 0o640
                path.chmod(mode)

    def remember_profile_number(self, profile_id: str, number: int) -> None:
        """Record the Profile's stable display number for name derivation."""
        if number < 1:
            raise DockerSandboxError("Profile display number must be positive")
        self._profile_numbers[profile_id] = number

    def _require_profile_number(self, profile_id: str) -> int:
        number = self._profile_numbers.get(profile_id)
        if number is None:
            raise DockerSandboxError(
                "Profile display number is unknown for this sandbox"
            )
        return number

    def get_browser_container_name(self, profile_id: str) -> str:
        return (
            f"{self.resource_prefix}-{self._require_profile_number(profile_id):04d}"
            "-browser"
        )

    def get_stream_container_name(self, profile_id: str) -> str:
        return (
            f"{self.resource_prefix}-{self._require_profile_number(profile_id):04d}"
            "-stream"
        )

    def get_network_name(self, profile_id: str) -> str:
        return profile_network_name(self.resource_prefix, profile_id)

    def get_browser_network_name(self, profile_id: str) -> str:
        return browser_network_name(self.resource_prefix, profile_id)

    def prepare_profile_directories(self, profile_id: str) -> dict[str, Path]:
        profile_dir = self.validator.get_profile_data_dir(profile_id)
        runtime_dir = self.validator.get_runtime_dir(profile_id)
        events_dir = self.validator.get_events_dir(profile_id)
        exchange_dir = self.validator.get_exchange_dir(profile_id)
        upload_dir = self.validator.get_upload_dir(profile_id)
        preview_dir = self.validator.get_preview_dir(profile_id)

        for d in (
            profile_dir,
            runtime_dir,
            events_dir,
            exchange_dir,
            upload_dir,
            preview_dir,
        ):
            self._secure_directory(d, 0o750)

        x11_dir = self.validator.validate_runtime_source(
            profile_id, runtime_dir / "x11", allow_create=True
        )
        pulse_dir = self.validator.validate_runtime_source(
            profile_id, runtime_dir / "pulse", allow_create=True
        )
        self._secure_directory(x11_dir, 0o750)
        self._secure_directory(pulse_dir, 0o750)

        return {
            "profile": profile_dir,
            "runtime": runtime_dir,
            "events": events_dir,
            "exchange": exchange_dir,
            "uploads": upload_dir,
            "x11": x11_dir,
            "pulse": pulse_dir,
            "preview": preview_dir,
        }

    def prepare_agent_socket_dir(
        self, profile_id: str, runtime_instance_id: str
    ) -> Path:
        try:
            if os.environ.get(AGENT_SOCKET_ROOT_ENV):
                validate_socket_deployment(
                    self.validator.socket_root, profile_id, runtime_instance_id
                )
            return prepare_socket_dir(
                self.validator.socket_root,
                profile_id,
                runtime_instance_id,
                managed_uid=self.runtime_uid if self.manage_ownership else None,
                managed_gid=self.runtime_gid if self.manage_ownership else None,
            )
        except SocketRootError as exc:
            raise DockerSandboxError(
                f"Agent socket root prepare failed: {type(exc).__name__}"
            ) from None

    def _agent_socket_environment(
        self, profile_id: str, runtime_instance_id: str
    ) -> dict[str, str]:
        root = self.validator.socket_root
        return {
            AGENT_SOCKET_ROOT_ENV: str(root),
            AGENT_SOCKET_PATH_ENV: str(
                agent_socket_path(root, profile_id, runtime_instance_id)
            ),
            "PROFILE_ID": profile_id,
            "RUNTIME_INSTANCE_ID": runtime_instance_id,
        }

    def _secure_directory(self, directory: Path, mode: int) -> None:
        """Own Profile data by the runtime UID with exact non-world modes.

        Managed deployment (the Supervisor container) must own the entries by
        uid/gid 1000; host-direct development runs keep the developer as owner
        but never fall back to globally writable modes.
        """
        directory.mkdir(parents=True, exist_ok=True)
        if self.manage_ownership:
            try:
                os.chown(directory, self.runtime_uid, self.runtime_gid)
            except OSError as exc:
                raise DockerSandboxError(
                    f"Cannot assign Profile directory ownership: {type(exc).__name__}"
                ) from None
        os.chmod(directory, mode)

    def setup_x11_permissions(self, x11_dir: Path) -> None:
        """Fix X11 socket directory permissions with a least-privilege helper.

        The helper only chmods one mounted directory: it drops every
        capability except FOWNER (required to chmod a directory owned by the
        runtime uid), runs on a read-only rootfs with no-new-privileges, and
        is always removed — success, failure and cancellation alike.
        """
        helper = None
        try:
            helper = self.client.containers.run(
                self.browser_image,
                # Deterministic managed name so a Supervisor killed
                # mid-helper leaves an orphan the startup reaper can
                # recognize and remove (review t022_code_f006).
                name=f"{self.resource_prefix}-x11-{uuid.uuid4().hex[:12]}",
                entrypoint="chmod",
                command=["0750", "/x11"],
                volumes={str(x11_dir): {"bind": "/x11", "mode": "rw"}},
                user="0:0",
                detach=True,
                read_only=True,
                cap_drop=["ALL"],
                cap_add=["FOWNER"],
                security_opt=["no-new-privileges:true"],
                labels=gate_labels(x11_helper_labels(
                    self.resource_prefix,
                    deployment_id=self.deployment_instance_id,
                )),
            )
            result = helper.wait(timeout=30)
            if result.get("StatusCode") != 0:
                raise DockerSandboxError(
                    "X11 permission helper exited unsuccessfully"
                )
        except DockerSandboxError:
            raise
        except DockerException as exc:
            logger.error(
                "Failed to setup X11 permissions: error_type=%s detail=%s",
                type(exc).__name__,
                docker_error_detail(exc),
            )
            raise DockerSandboxError(
                f"X11 permission initialization failed: {docker_error_detail(exc)}"
            ) from None
        except Exception as exc:  # noqa: BLE001 - wait/transport errors map to the same explicit outcome
            logger.error(
                "Failed to setup X11 permissions: error_type=%s detail=%s",
                type(exc).__name__,
                docker_error_detail(exc),
            )
            raise DockerSandboxError(
                f"X11 permission initialization failed: {docker_error_detail(exc)}"
            ) from None
        finally:
            if helper is not None:
                try:
                    helper.remove(force=True)
                except Exception as exc:  # noqa: BLE001 - cleanup must never mask the helper outcome
                    logger.warning(
                        "Failed to remove X11 permission helper: error_type=%s",
                        type(exc).__name__,
                    )

    async def create_profile_network(self, profile_id: str) -> Any:
        return await asyncio.to_thread(self._ensure_media_network, profile_id)

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
                labels=gate_labels(network_labels(
                    self.resource_prefix,
                    profile_id,
                    deployment_id=self.deployment_instance_id,
                )),
            )
        except DockerException as e:
            raise DockerSandboxError(
                f"Failed to create network {net_name}: {docker_error_detail(e)}"
            ) from e

    def _docker_call(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run one Docker call in a daemon thread, bounded by timeout.

        AC-015: a Docker call that never returns (hung daemon, wedged
        socket) must fail the caller after ``network_timeout`` seconds
        instead of wedging the Supervisor. The hung call leaks one
        daemon thread -- it can never block the caller again -- and the
        caller's lock is released, so other Profiles keep starting.
        The original exception (NotFound, APIError, ...) is re-raised
        unchanged; only a timeout becomes DockerSandboxError.
        """
        outcome: dict[str, Any] = {}
        error: dict[str, BaseException] = {}

        def _run() -> None:
            try:
                outcome["value"] = fn(*args, **kwargs)
            except BaseException as exc:  # noqa: BLE001 - re-raised below
                error["error"] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=self.network_timeout)
        if thread.is_alive():
            raise DockerSandboxError(
                "Docker call timed out after "
                f"{self.network_timeout:g}s: "
                f"{getattr(fn, '__name__', repr(fn))}"
            )
        if "error" in error:
            raise error["error"]
        return outcome["value"]

    def _used_subnets(self) -> list[ipaddress.IPv4Network]:
        """Every subnet Docker already knows, plus host route targets."""
        used: list[ipaddress.IPv4Network] = []
        try:
            networks = self._docker_call(self.client.networks.list)
        except DockerSandboxError:
            raise
        except DockerException as e:
            raise DockerSandboxError(
                "Failed to list networks for subnet allocation: "
                f"{docker_error_detail(e)}"
            ) from e
        for network in networks:
            config = (network.attrs.get("IPAM") or {}).get("Config") or []
            for entry in config:
                subnet = entry.get("Subnet") if isinstance(entry, dict) else None
                if not subnet:
                    continue
                try:
                    parsed = ipaddress.ip_network(subnet)
                except ValueError:
                    continue
                if isinstance(parsed, ipaddress.IPv4Network):
                    used.append(parsed)
        for subnet in self._reserved_subnets:
            try:
                parsed = ipaddress.ip_network(subnet)
            except ValueError:
                continue
            if isinstance(parsed, ipaddress.IPv4Network):
                used.append(parsed)
        used.extend(host_route_networks())
        return used

    def _ensure_media_network(self, profile_id: str) -> Any:
        """Create the Profile media network with the fixed-endpoint spec.

        Existing networks are returned as-is; conformance is a separate
        inspection (reconcile migrates non-conforming networks by
        rebuild). New networks always get an allocated explicit subnet:
        allocation failure is explicit, never an auto-subnet fallback.

        AC-015: the allocation lock guards only the get+allocate+reserve
        phase. The Docker create runs outside it, bounded by
        ``network_timeout`` via ``_docker_call``, so a hung create fails
        this caller instead of stalling every Profile's network setup.
        A create conflict is an error, never a retry: exactly one
        create attempt is made, and its reservation is discarded on any
        failure. The same Profile is never created concurrently in
        production -- the core holds the per-profile lock across its
        start path -- so a name conflict here means a genuine conflict.
        """
        net_name = self.get_network_name(profile_id)
        try:
            with self._media_network_lock:
                try:
                    existing = self._docker_call(self.client.networks.get, net_name)
                except NotFound:
                    existing = None
                if existing is not None:
                    self._require_network_ownership(existing, net_name)
                    return existing
                try:
                    plan = self.media_allocator.allocate(self._used_subnets())
                except MediaPoolExhaustedError as e:
                    raise DockerSandboxError(str(e)) from e
                self._reserved_subnets.add(plan.subnet)
            ipam = docker.types.IPAMConfig(
                pool_configs=[
                    docker.types.IPAMPool(
                        subnet=plan.subnet, iprange=plan.ip_range
                    )
                ]
            )
            try:
                created = self._docker_call(
                    self.client.networks.create,
                    net_name,
                    driver="bridge",
                    ipam=ipam,
                    labels=gate_labels(media_network_labels(
                        network_labels(
                            self.resource_prefix,
                            profile_id,
                            deployment_id=self.deployment_instance_id,
                        ),
                        plan,
                    )),
                )
            except Exception:
                with self._media_network_lock:
                    self._reserved_subnets.discard(plan.subnet)
                raise
            # The network now exists in Docker's list, so the reservation
            # is no longer needed: only in-flight creates stay reserved.
            with self._media_network_lock:
                self._reserved_subnets.discard(plan.subnet)
            return created
        except DockerSandboxError:
            raise
        except DockerException as e:
            raise DockerSandboxError(
                f"Failed to create network {net_name}: {docker_error_detail(e)}"
            ) from e

    def inspect_media_network(self, profile_id: str) -> dict[str, Any]:
        """Conformance snapshot of the Profile media network.

        ``conforms`` requires the recorded plan labels AND a live IPAM
        config that matches them; anything else (missing network,
        pre-spec network, label/IPAM drift) is reported, not assumed.
        """
        net_name = self.get_network_name(profile_id)
        result: dict[str, Any] = {
            "exists": False,
            "conforms": False,
            "plan": None,
            "gateway_attached_id": None,
            "gateway_ip": None,
            "endpoints": {},
        }
        try:
            network = self.client.networks.get(net_name)
        except NotFound:
            return result
        except DockerException as e:
            raise DockerSandboxError(
                f"Failed to inspect network {net_name}: {docker_error_detail(e)}"
            ) from e
        self._require_network_ownership(network, net_name)
        network.reload()
        result["exists"] = True
        plan = plan_from_labels(network.attrs.get("Labels") or {})
        ipam_entries = (network.attrs.get("IPAM") or {}).get("Config") or []
        ipam_matches = plan is not None and any(
            isinstance(entry, dict)
            and entry.get("Subnet") == plan.subnet
            and entry.get("IPRange") == plan.ip_range
            for entry in ipam_entries
        )
        endpoints: dict[str, str] = {}
        for container_id, info in (
            network.attrs.get("Containers") or {}
        ).items():
            if isinstance(info, dict):
                endpoints[container_id] = (info.get("IPv4Address") or "").split(
                    "/"
                )[0]
        result["endpoints"] = endpoints
        if plan is not None:
            result["plan"] = plan
            for container_id, ip in endpoints.items():
                if ip == plan.gateway_endpoint:
                    result["gateway_attached_id"] = container_id
                    result["gateway_ip"] = ip
        result["conforms"] = bool(plan is not None and ipam_matches)
        return result

    def _require_network_ownership(self, network: Any, name: str) -> None:
        labels = network.attrs.get("Labels") or {}
        if network.name != name or not network_ownership_matches(
            labels,
            deployment_id=self.deployment_instance_id,
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
                f"Failed to inspect infrastructure container {container_id}: {docker_error_detail(e)}"
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

    def rebuild_media_network(self, profile_id: str) -> Any:
        """Rebuild a nonconformant media network around live containers.

        Docker refuses to remove a network with active endpoints, so
        every verified endpoint is disconnected first and the
        Browser/Stream containers are reconnected to the recreated
        network afterwards: their IDs, pages, IPC/X11 and Profile data
        are untouched (t026 AC-004). An unknown endpoint aborts the
        rebuild before anything is detached. The Gateway is not
        reconnected here — the caller re-attaches it at the new plan's
        fixed endpoint.
        """
        net_name = self.get_network_name(profile_id)
        try:
            net = self.client.networks.get(net_name)
        except NotFound:
            return self._ensure_media_network(profile_id)
        except DockerException as e:
            raise DockerSandboxError(
                f"Failed to get network {net_name}: {docker_error_detail(e)}"
            ) from e
        self._require_network_ownership(net, net_name)
        net.reload()
        endpoints: list[Any] = []
        for container_id in list((net.attrs.get("Containers") or {}).keys()):
            try:
                container = self.client.containers.get(container_id)
            except DockerException as e:
                raise DockerSandboxError(
                    f"Failed to inspect endpoint container {container_id} "
                    f"in network {net_name}: {docker_error_detail(e)}"
                ) from e
            labels = container.labels or {}
            if (
                labels.get("com.cbrowser.prefix") != self.resource_prefix
                or labels.get("com.cbrowser.managed-by") != "supervisor"
                or labels.get("com.cbrowser.role")
                not in {"browser", "stream", "gateway"}
            ):
                raise DockerSandboxError(
                    f"Unknown endpoint container {container.name} "
                    f"({container_id}) in network {net_name}"
                )
            endpoints.append(container)
        for container in endpoints:
            try:
                net.disconnect(container)
            except DockerException as e:
                raise DockerSandboxError(
                    f"Failed to disconnect {container.name} from "
                    f"{net_name}: {docker_error_detail(e)}"
                ) from e
        try:
            net.remove()
        except DockerException as e:
            for container in endpoints:
                try:
                    net.connect(container)
                except DockerException:
                    pass
            raise DockerSandboxError(
                f"Failed to remove network {net_name}: {docker_error_detail(e)}"
            ) from e
        new_net = self._ensure_media_network(profile_id)
        for container in endpoints:
            if (container.labels or {}).get("com.cbrowser.role") == "gateway":
                continue
            try:
                new_net.connect(container)
            except DockerException as e:
                raise DockerSandboxError(
                    f"Failed to reconnect {container.name} to "
                    f"{net_name}: {docker_error_detail(e)}"
                ) from e
        return new_net

    def attach_profile_infrastructure(
        self,
        profile_id: str,
        gateway_container_id: str | None,
        gateway_port: int = DEFAULT_GATEWAY_PORT,
    ) -> dict[str, Any]:
        net_name = self.get_network_name(profile_id)
        try:
            net = self.client.networks.get(net_name)
        except NotFound:
            raise DockerSandboxError(f"Profile network {net_name} not found") from None
        except DockerException as e:
            raise DockerSandboxError(f"Failed to get network {net_name}: {docker_error_detail(e)}") from e

        self._require_network_ownership(net, net_name)

        gw = (
            self._validate_infra_container(gateway_container_id, "gateway")
            if gateway_container_id
            else None
        )

        newly_connected: list[Any] = []
        try:
            net.reload()
            connected_containers = net.attrs.get("Containers") or {}
            plan = plan_from_labels(net.attrs.get("Labels") or {})

            targets = [c for c in (gw,) if c is not None]
            for container in targets:
                if plan is not None:
                    # Fixed-endpoint spec: the endpoint must be free or
                    # already held by this Gateway; a different holder is
                    # an explicit conflict, never a silent renumber.
                    for other_id, info in connected_containers.items():
                        other_ip = (
                            (info.get("IPv4Address") or "").split("/")[0]
                            if isinstance(info, dict)
                            else ""
                        )
                        if other_ip == plan.gateway_endpoint and other_id != container.id:
                            raise DockerSandboxError(
                                "Gateway fixed endpoint is held by another "
                                f"container on {net_name}"
                            )
                    current_ip = None
                    if container.id in connected_containers:
                        current_ip = (
                            connected_containers[container.id].get(
                                "IPv4Address"
                            )
                            or ""
                        ).split("/")[0]
                    if current_ip == plan.gateway_endpoint:
                        continue
                    if container.id in connected_containers:
                        # Attached at a drifted address: re-attach at the
                        # fixed endpoint (infra container, safe to move).
                        net.disconnect(container)
                        net.reload()
                        connected_containers = net.attrs.get("Containers") or {}
                    net.connect(
                        container, ipv4_address=plan.gateway_endpoint
                    )
                    newly_connected.append(container)
                    net.reload()
                    connected_containers = net.attrs.get("Containers") or {}
                    continue
                if container.id not in connected_containers:
                    net.connect(container)
                    newly_connected.append(container)
                    net.reload()
                    connected_containers = net.attrs.get("Containers") or {}

            if gw:
                gw.reload()
            gw_ip = None
            if gw:
                gw_networks = gw.attrs.get("NetworkSettings", {}).get("Networks", {})
                gw_ip = gw_networks.get(net_name, {}).get("IPAddress")
                if not gw_ip:
                    net.reload()
                    c_map = net.attrs.get("Containers") or {}
                    if gw.id in c_map:
                        gw_ip = c_map[gw.id].get("IPv4Address", "").split("/")[0]

                if not gw_ip:
                    raise DockerSandboxError(
                        f"Failed to allocate or retrieve IPv4 address for "
                        f"gateway on {net_name}"
                    )
                if plan is not None and gw_ip != plan.gateway_endpoint:
                    raise DockerSandboxError(
                        "Gateway address does not match the fixed endpoint "
                        f"for {net_name}"
                    )

            result: dict[str, Any] = {}
            if gw_ip:
                result["gateway_ip"] = gw_ip
                result["gateway_url"] = f"ws://{gw_ip}:{gateway_port}"
            return result
        except Exception as exc:
            for c in newly_connected:
                try:
                    net.disconnect(c)
                except Exception as disconnect_exc:  # noqa: BLE001 - rollback disconnect failure logged before raising primary error
                    logger.debug(
                        "Rollback disconnect failed: %s",
                        type(disconnect_exc).__name__,
                    )
            if isinstance(exc, DockerSandboxError):
                raise
            raise DockerSandboxError(
                f"Infrastructure attachment failed on {net_name}: {docker_error_detail(exc)}"
            ) from exc

    def disconnect_profile_infrastructure(
        self,
        profile_id: str,
        gateway_container_id: str | None = None,
    ) -> None:
        net_name = self.get_network_name(profile_id)
        try:
            net = self.client.networks.get(net_name)
        except NotFound:
            return
        except DockerException as e:
            raise DockerSandboxError(f"Failed to get network {net_name}: {docker_error_detail(e)}") from e

        self._require_network_ownership(net, net_name)
        net.reload()
        connected = net.attrs.get("Containers") or {}

        targets = []
        if gateway_container_id:
            targets.append(
                self._validate_infra_container(gateway_container_id, "gateway")
            )
        if not targets:
            for cid in list(connected.keys()):
                try:
                    c = self.client.containers.get(cid)
                    labels = c.labels or {}
                    if (
                        labels.get("com.cbrowser.prefix") == self.resource_prefix
                        and labels.get("com.cbrowser.managed-by") == "supervisor"
                        and labels.get("com.cbrowser.role") == "gateway"
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
                        f"Failed to disconnect {c.id} from {net_name}: {docker_error_detail(e)}"
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
        await asyncio.to_thread(self.setup_x11_permissions, dirs["x11"])

        target_snap = dirs["runtime"] / "snapshot.json"
        if snapshot_json_path != target_snap:
            atomic_write_text(
                target_snap, snapshot_json_path.read_text(encoding="utf-8"), mode=0o600
            )
            if self.manage_ownership:
                os.chown(target_snap, self.runtime_uid, self.runtime_gid)

        await asyncio.to_thread(self.cleanup_container_by_name, b_name)

        # The prior owned Browser has been removed. Chromium's singleton links
        # refer to its old hostname/PID and cannot be reused in a new container.
        # Unlink the entries themselves; never follow a stale socket/cookie link.
        for filename in SINGLETON_LOCK_NAMES:
            lock_path = dirs["profile"] / filename
            if lock_path.is_symlink() or lock_path.exists():
                lock_path.unlink()

        gate = self._prepare_policy_gate(profile_id, runtime_instance_id, "browser")
        self._validate_cache_paths()
        volumes = browser_volumes(
            profile_id=profile_id,
            dirs=dirs,
            gate=gate,
            engine_cache=self.engine_cache,
            geoip_cache=self.geoip_cache,
        )
        socket_dir = self.prepare_agent_socket_dir(profile_id, runtime_instance_id)
        volumes[str(socket_dir)] = {"bind": str(socket_dir), "mode": "rw"}
        creds_file = dirs["runtime"] / PROXY_CREDENTIALS_FILENAME
        has_proxy = isinstance(snapshot.get("config"), dict) and bool(
            snapshot["config"].get("proxy_id")
        )
        if has_proxy and creds_file.is_file():
            validated_creds = self.validator.validate_runtime_source(
                profile_id, creds_file
            )
            if (validated_creds.stat().st_mode & 0o077) != 0:
                raise DockerSandboxError(
                    "Proxy credentials file must have 0600 permissions"
                )
            # The whole runtime directory is already mounted rw for the
            # Runner; shadow the credentials file with a dedicated read-only
            # bind so the sandbox cannot rewrite its own proxy secret.
            volumes[str(validated_creds)] = {
                "bind": "/run/cbrowser/runtime/proxy_credentials.json",
                "mode": "ro",
            }
        cfg = snapshot.get("config")
        if isinstance(cfg, dict):
            font_set_id = cfg.get("font_set_id")
            platform = cfg.get("fingerprint_platform", "windows")
            fonts_root = os.environ.get("CBROWSER_FONTS_DIR")
            if (
                isinstance(font_set_id, str)
                and re.fullmatch(r"[a-f0-9]{32,64}", font_set_id)
                and platform in ("windows", "macos")
                and fonts_root
            ):
                host_font_dir = Path(fonts_root) / platform / font_set_id
                volumes[str(host_font_dir)] = {
                    "bind": str(FONT_SET_MOUNT_ROOT / platform / font_set_id),
                    "mode": "ro",
                }
        proxy = proxy_endpoint_from_credentials(creds_file)
        # t052 AC-010: a loopback proxy is stored as 127.0.0.1/localhost
        # but the credentials file handed to the container carries the
        # host-gateway hostname (mapped in SupervisorCore); the container
        # needs the extra_hosts entry so the name resolves to the host.
        proxy_host = urlsplit(proxy).hostname if proxy else None
        extra_hosts = (
            {HOST_GATEWAY_HOSTNAME: "host-gateway"}
            if proxy_host == HOST_GATEWAY_HOSTNAME
            else None
        )
        command = browser_command(
            profile_id,
            runtime_instance_id,
            display,
            engine_build=self.engine_build,
        )

        try:
            container = await asyncio.to_thread(
                self.client.containers.run,
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
                extra_hosts=extra_hosts,
                restart_policy={"Name": "no"},
                tmpfs={
                    "/tmp": "rw,exec,nosuid,nodev,size=512m",
                    "/home/cbrowser": "rw,mode=0755,size=64m",
                },
                volumes=volumes,
                environment=self._agent_socket_environment(
                    profile_id, runtime_instance_id
                ),
                labels=gate_labels(browser_labels(
                    self.resource_prefix,
                    profile_id,
                    snapshot["version"],
                    self._require_profile_number(profile_id),
                    deployment_id=self.deployment_instance_id,
                )),
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
            detail = docker_error_detail(e)
            # t052 AC-011: a loopback proxy whose host-gateway mapping the
            # daemon rejects must fail here with a remediation, never
            # start successfully and then fail to connect.
            if proxy_host == HOST_GATEWAY_HOSTNAME and (
                "host-gateway" in detail.lower() or "extra_hosts" in detail.lower()
            ):
                raise LoopbackMappingError(
                    "Loopback proxy mapping failed: the Docker daemon could "
                    "not map host.docker.internal to the host gateway, so "
                    f"the Browser cannot reach the host-local proxy at "
                    f"{proxy}. Use a Docker daemon that supports "
                    "host-gateway extra hosts (Docker 20.10+ / OrbStack), "
                    "or move the proxy to a non-loopback address."
                ) from e
            raise DockerSandboxError(
                f"Failed to run browser container {b_name}: {detail}"
            ) from e

    def _bound_snapshot_geometry(
        self, profile_id: str, snapshot_json_path: Path | None
    ) -> tuple[int | None, int | None]:
        if snapshot_json_path is None:
            return None, None
        try:
            snapshot_path = self.validator.validate_runtime_source(
                profile_id, snapshot_json_path
            )
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, PathSecurityError) as exc:
            raise DockerSandboxError(
                f"Bound config snapshot is missing or invalid: {type(exc).__name__}"
            ) from None
        config = snapshot.get("config")
        if not isinstance(config, dict):
            raise DockerSandboxError(
                "Bound config snapshot lacks a config object for screen geometry"
            )
        width = config.get("screen_width")
        height = config.get("screen_height")
        for name, value in (("screen_width", width), ("screen_height", height)):
            if type(value) is not int or not 100 <= value <= 10000:
                raise DockerSandboxError(
                    f"Bound config snapshot {name} is missing or invalid"
                )
        return width, height

    async def start_stream_container(
        self,
        profile_id: str,
        runtime_instance_id: str,
        browser_container_name: str,
        udp_mux_port: int,
        gateway_url: str | None = None,
        agent_secret_path: Path | None = None,
        display: str = ":99",
        selkies_tokens_path: Path | None = None,
        snapshot_json_path: Path | None = None,
        gateway_port: int = DEFAULT_GATEWAY_PORT,
    ) -> Any:
        endpoint = GatewayEndpoint.from_url(
            gateway_url or GatewayEndpoint(port=gateway_port).ws_url
        )
        if endpoint.port != gateway_port:
            raise DockerSandboxError(
                "Gateway URL port does not match the configured Gateway port"
            )
        resolved_gateway_url = gateway_url or endpoint.ws_url
        if agent_secret_path is None or not agent_secret_path.is_file():
            raise DockerSandboxError(
                "Explicit Stream Agent credential file is required"
            )
        if selkies_tokens_path is None or not selkies_tokens_path.is_file():
            raise DockerSandboxError(
                "Explicit Stream Selkies token credential file is required"
            )
        secret_file = self.validator.validate_secret_source(
            profile_id, agent_secret_path
        )
        if (secret_file.stat().st_mode & 0o077) != 0:
            raise DockerSandboxError(
                "Stream Agent credential file must have 0600 permissions"
            )
        token_stat = selkies_tokens_path.stat()
        if (token_stat.st_mode & 0o077) != 0:
            raise DockerSandboxError(
                "Stream Selkies token credential file must have 0600 permissions"
            )
        screen_width, screen_height = self._bound_snapshot_geometry(
            profile_id, snapshot_json_path
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

        b_inspect = await asyncio.to_thread(
            self.client.api.inspect_container, browser_container_name
        )
        browser_hostname = b_inspect.get("Config", {}).get("Hostname", "")

        await asyncio.to_thread(self.cleanup_container_by_name, s_name)

        selkies_file = self.validator.validate_secret_source(
            profile_id, selkies_tokens_path
        )

        gate = self._prepare_policy_gate(profile_id, runtime_instance_id, "stream")
        allowed_tcp: list[tuple[str, int]] = []
        allowed_udp: list[tuple[str, int]] = []
        volumes = stream_volumes(
            gate=gate,
            x11_socket=x11_socket,
            xauth_file=xauth_file,
            pulse_dir=pulse_dir,
            secret_file=secret_file,
            selkies_file=selkies_file,
        )
        parsed_version = _parse_config_version(
            b_inspect.get("Config", {}).get("Labels", {}).get(
                "com.cbrowser.config-version"
            )
        )
        if parsed_version is None:
            raise DockerSandboxError(
                "Browser container config-version label is unusable"
            )
        config_version = str(parsed_version)
        clipboard_sync = True
        if snapshot_json_path is not None:
            try:
                snapshot_path = self.validator.validate_runtime_source(
                    profile_id, snapshot_json_path
                )
                parsed_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                config = (
                    parsed_snapshot.get("config")
                    if isinstance(parsed_snapshot, dict)
                    else None
                )
                clipboard_sync = (
                    bool(config.get("clipboard_sync", True))
                    if isinstance(config, dict)
                    else False
                )
            except (OSError, ValueError, PathSecurityError) as exc:
                logger.warning(
                    "Stream snapshot clipboard_sync unavailable: "
                    "profile=%s error_type=%s",
                    profile_id,
                    type(exc).__name__,
                )
                clipboard_sync = False
        env = stream_environment(
            display=display,
            profile_id=profile_id,
            runtime_instance_id=runtime_instance_id,
            gateway_url=resolved_gateway_url,
            config_version=config_version,
            udp_mux_port=udp_mux_port,
            screen_width=screen_width,
            screen_height=screen_height,
            clipboard_sync=clipboard_sync,
            build_id=os.environ.get("CBROWSER_BUILD_ID") or None,
        )
        env.update(self._agent_socket_environment(profile_id, runtime_instance_id))
        ports = stream_ports(udp_mux_port)

        container = None
        try:
            container = await asyncio.to_thread(
                self.client.containers.run,
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
                labels=gate_labels(stream_labels(
                    self.resource_prefix,
                    profile_id,
                    config_version,
                    self._require_profile_number(profile_id),
                    deployment_id=self.deployment_instance_id,
                )),
            )
            allowed_tcp.extend(
                await asyncio.to_thread(
                    self._resolved_endpoint, container, resolved_gateway_url
                )
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
        except Exception as exc:  # noqa: BLE001 - initialization failure is owned by the creator
            if container is not None:
                residue = self._reclaim_created_stream(
                    container, profile_id, runtime_instance_id
                )
                if residue is not None:
                    raise StreamContainerResidueError(
                        residue, type(exc).__name__, docker_error_detail(exc)
                    ) from exc
            if isinstance(exc, DockerSandboxError):
                raise
            if isinstance(exc, DockerException):
                raise DockerSandboxError(
                    f"Failed to run stream container {s_name}: "
                    f"{docker_error_detail(exc)}"
                ) from None
            raise DockerSandboxError(
                f"Failed to initialize stream container {s_name}: "
                f"{docker_error_detail(exc)}"
            ) from None

    def _reclaim_created_stream(
        self, container: Any, profile_id: str, instance_id: str
    ) -> StreamResidue | None:
        residue = StreamResidue(
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            container_id=getattr(container, "id", None),
            container_name=getattr(container, "name", None),
        )
        labels = getattr(container, "labels", None) or {}
        verified = (
            residue.container_id is not None
            and residue.container_name
            == self.get_stream_container_name(profile_id)
            and labels.get("com.cbrowser.prefix") == self.resource_prefix
            and labels.get("com.cbrowser.managed-by") == "supervisor"
            and labels.get("com.cbrowser.role") == "stream"
            and labels.get("com.cbrowser.profile-id") == profile_id
            and container_runtime_instance_id(container) == instance_id
        )
        if not verified:
            logger.warning(
                "Stream container identity unverified; retained: container=%s",
                residue.container_id,
            )
            return residue
        try:
            container.remove(force=True)
        except Exception as exc:  # noqa: BLE001 - reclaim failure is reported as typed pending residue
            logger.warning(
                "Stream container reclaim failed: container=%s error_type=%s",
                residue.container_id,
                type(exc).__name__,
            )
            return residue
        return None

    def cleanup_stream_residue(self, residue: StreamResidue) -> bool:
        if not residue.container_id:
            return False
        try:
            container = self.client.containers.get(residue.container_id)
        except NotFound:
            return True
        except DockerException as exc:
            logger.warning(
                "Stream residue lookup failed: container=%s error_type=%s",
                residue.container_id,
                type(exc).__name__,
            )
            return False
        labels = getattr(container, "labels", None) or {}
        if (
            getattr(container, "name", None)
            != self.get_stream_container_name(residue.profile_id)
            or labels.get("com.cbrowser.prefix") != self.resource_prefix
            or labels.get("com.cbrowser.managed-by") != "supervisor"
            or labels.get("com.cbrowser.role") != "stream"
            or labels.get("com.cbrowser.profile-id") != residue.profile_id
            or container_runtime_instance_id(container)
            != residue.runtime_instance_id
        ):
            logger.warning(
                "Stream residue identity mismatch; retained: container=%s",
                residue.container_id,
            )
            return False
        try:
            container.remove(force=True)
        except NotFound:
            return True
        except DockerException as exc:
            logger.warning(
                "Stream residue removal failed: container=%s error_type=%s",
                residue.container_id,
                type(exc).__name__,
            )
            return False
        return True

    def cleanup_container_by_name(self, name: str) -> None:
        try:
            c = self.client.containers.get(name)
            labels = c.labels or {}
            # Strict safety check: only remove container if it matches our prefix label
            profile_number = _parse_profile_number(
                labels.get("com.cbrowser.profile-number")
            )
            role = labels.get("com.cbrowser.role")
            if (
                c.name == name
                and labels.get("com.cbrowser.prefix") == self.resource_prefix
                and labels.get("com.cbrowser.managed-by") == "supervisor"
                and role in {"browser", "stream"}
                and profile_number is not None
                and name
                == f"{self.resource_prefix}-{profile_number:04d}-{role}"
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
                        f"network {name}: {docker_error_detail(e)}"
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
                if role == "gateway":
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
                        f"Failed to disconnect endpoint {c.name} from {name}: {docker_error_detail(e)}"
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
        await asyncio.to_thread(self._teardown_profile_sync, profile_id)

    def _teardown_profile_sync(self, profile_id: str) -> None:
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
        instance = container_runtime_instance_id(container)
        role = labels.get("com.cbrowser.role")
        if not profile or not instance or not role:
            return False
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

    def scan_gateway_containers(self) -> list[Any]:
        """Running containers carrying this deployment's Gateway identity.

        Gateway identity is resolved from labels on every scan (t026):
        prefix + managed-by + role=gateway. A replaced Gateway container
        (new ID) is found without any static startup parameter.
        """
        try:
            containers = self.client.containers.list(
                all=False,
                filters={"label": f"com.cbrowser.prefix={self.resource_prefix}"},
            )
        except DockerException as e:
            raise DockerSandboxError(
                f"Gateway scan failed: {type(e).__name__}"
            ) from None
        result = []
        for container in containers:
            labels = container.labels or {}
            if (
                labels.get("com.cbrowser.managed-by") == "supervisor"
                and labels.get("com.cbrowser.role") == "gateway"
                and self._owns_deployment(labels)
                and container.status == "running"
            ):
                result.append(container)
        return result

    def resolve_gateway_container_id(self) -> str | None:
        """The current Gateway container ID, or None when absent."""
        gateways = self.scan_gateway_containers()
        return gateways[0].id if gateways else None

    def stream_policy_spec(
        self, plan: MediaNetworkPlan, gateway_port: int, udp_mux_port: int
    ) -> dict[str, Any]:
        """Expected live Stream netfilter spec for convergence checks.

        Mirrors startup installation: the only allowed TCP peer is the
        Gateway at its fixed media endpoint, plus the UDP mux listener.
        """
        return {
            "role": "stream",
            "udp_mux_port": udp_mux_port,
            "allowed_tcp": [(plan.gateway_endpoint, gateway_port)],
            "allowed_udp": [],
        }

    def browser_policy_spec(
        self, profile_id: str, container: Any
    ) -> dict[str, Any]:
        """Expected live Browser netfilter spec for convergence checks.

        Rebuilt from the same inputs as startup application: the mounted
        proxy credentials file, resolved from inside the Browser container.
        """
        creds_file = self.validator.get_runtime_dir(profile_id) / PROXY_CREDENTIALS_FILENAME
        proxy = proxy_endpoint_from_credentials(creds_file)
        allowed_tcp = self._resolved_endpoint(container, proxy) if proxy else []
        return {
            "role": "browser",
            "allowed_tcp": allowed_tcp,
            "allowed_udp": [],
            "udp_mux_port": None,
        }

    def _run_policy_helper(self, container: Any, command: list[str]) -> int:
        """Run the policy module in the target namespace; return its exit code."""
        if not self.policy_image or not (
            self.policy_image.startswith("sha256:") or "@sha256:" in self.policy_image
        ):
            raise DockerSandboxError(
                "Explicit immutable network policy image is required"
            )
        helper = None
        try:
            helper = self.client.containers.create(
                self.policy_image,
                entrypoint=["python3", "-m", "cbrowser.supervisor.network_policy"],
                command=command,
                name=f"{self.resource_prefix}-policy-{uuid.uuid4().hex[:12]}",
                detach=True,
                user="0:0",
                read_only=True,
                cap_drop=["ALL"],
                cap_add=["NET_ADMIN"],
                security_opt=["no-new-privileges:true"],
                network_mode=f"container:{container.id}",
                environment=_udp_mux_helper_environment(),
                tmpfs={
                    "/run": "rw,nosuid,nodev,size=4m",
                    "/tmp": "rw,nosuid,nodev,size=4m",
                },
                labels=gate_labels(policy_helper_labels(
                    self.resource_prefix,
                    deployment_id=self.deployment_instance_id,
                )),
            )
            helper.start()
            result = helper.wait(timeout=30)
            status_code = int(result.get("StatusCode", -1))
            if status_code != 0:
                logger.warning(
                    "Network policy helper exit=%s output=%s",
                    status_code,
                    _helper_log_tail(helper),
                )
            return status_code
        except DockerException as exc:
            raise DockerSandboxError(
                "Runtime network policy helper failed: " + docker_error_detail(exc)
            ) from None
        finally:
            if helper is not None:
                try:
                    helper.remove(force=True)
                except Exception as exc:  # noqa: BLE001 - cleanup never masks the primary outcome
                    # t055 A4: a cleanup failure must not overwrite the
                    # exit code the caller is about to receive.
                    logger.warning(
                        "Failed to remove network policy helper: error_type=%s",
                        type(exc).__name__,
                    )

    def verify_container_policy(
        self, container: Any, policy: dict[str, Any]
    ) -> bool:
        """True only when the container's live netns rules equal the spec.

        Exit 0 from the helper means an exact match, 4 a definite
        mismatch; anything else is an adapter error, never a silent pass.
        """
        validated = NetworkPolicySpec.model_validate(policy)
        code = self._run_policy_helper(
            container, ["verify", validated.model_dump_json()]
        )
        if code == 0:
            return True
        if code == 4:
            return False
        raise DockerSandboxError(
            f"Runtime network policy verification failed: exit={code}"
        )

    def fail_close_container(self, container: Any) -> None:
        """Replace the container's rules with DROP-everything (AC-005)."""
        code = self._run_policy_helper(container, ["fail-closed"])
        if code != 0:
            raise DockerSandboxError(
                f"Runtime fail-closed installation failed: exit={code}"
            )

    def get_profile_containers(self, profile_id: str) -> dict[str, Any]:
        """Live Browser/Stream container objects for one Profile.

        Each role is fetched by its deterministic name; a container is
        only returned when its labels bind it to this prefix, Profile
        and role — anything else reads as missing rather than adopted.
        """
        result: dict[str, Any] = {"browser": None, "stream": None}
        names = {
            "browser": self.get_browser_container_name(profile_id),
            "stream": self.get_stream_container_name(profile_id),
        }
        for role, name in names.items():
            try:
                container = self.client.containers.get(name)
            except NotFound:
                continue
            except DockerException as e:
                raise DockerSandboxError(
                    f"Failed to inspect {role} container {name}: {docker_error_detail(e)}"
                ) from e
            labels = container.labels or {}
            if (
                labels.get("com.cbrowser.prefix") != self.resource_prefix
                or labels.get("com.cbrowser.profile-id") != profile_id
                or labels.get("com.cbrowser.role") != role
            ):
                continue
            result[role] = container
        return result

    def scan_active_containers(self) -> list[dict[str, Any]]:
        try:
            containers = self.client.containers.list(
                all=True,
                filters={"label": f"com.cbrowser.prefix={self.resource_prefix}"},
            )
            result = []
            for c in containers:
                labels = c.labels or {}
                role = labels.get("com.cbrowser.role")
                if role not in {"browser", "stream"}:
                    continue
                # Scan boundary: a resource whose identity (profile label
                # or runtime configuration) or config-version label is
                # missing or malformed is rejected on its own —
                # never adopted, never bulk-deleted, and never allowed to
                # abort the scan of the remaining resources.
                profile_id = labels.get("com.cbrowser.profile-id")
                instance_id = container_runtime_instance_id(c)
                config_version = _parse_config_version(
                    labels.get("com.cbrowser.config-version")
                )
                profile_number = _parse_profile_number(
                    labels.get("com.cbrowser.profile-number")
                )
                if (
                    not isinstance(profile_id, str)
                    or not profile_id
                    or not isinstance(instance_id, str)
                    or not instance_id
                    or config_version is None
                    or profile_number is None
                ):
                    logger.warning(
                        "Container scan rejected a resource with unusable "
                        "identity labels: role=%s",
                        role,
                    )
                    continue
                # A59/AC-021: a sandbox from another deployment (or
                # predating deployment labels) is not ours: skip it,
                # never claim it for this deployment.
                if not self._owns_deployment(labels):
                    logger.warning(
                        "Container scan rejected a resource from another "
                        "deployment: profile=%s",
                        profile_id,
                    )
                    continue
                self.remember_profile_number(profile_id, profile_number)
                result.append(
                    {
                        "id": c.id,
                        "name": c.name,
                        "status": c.status,
                        "profile_id": profile_id,
                        "instance_id": instance_id,
                        "role": role,
                        "config_version": str(config_version),
                        "policy_ready": self._runtime_policy_ready(c),
                    }
                )
            return result
        except DockerException as e:
            raise DockerSandboxError(
                f"Container scan failed: {type(e).__name__}"
            ) from None
