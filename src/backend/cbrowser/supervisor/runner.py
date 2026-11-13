"""Entrypoint module for running Supervisor service with Control HTTP server."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import docker
import httpx
import uvicorn
from cbrowser.gateway.endpoint import gateway_port_from_env
from cbrowser.secret_files import read_secret_file
from cbrowser.supervisor.artifact_forwarder import DownloadArtifactForwarder
from cbrowser.supervisor.container_spec import validate_resource_prefix
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.coordinator_lock import CoordinatorLock
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.gateway_client import GatewayControlClient
from cbrowser.supervisor.metrics import StageMetrics
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from cbrowser.supervisor.recovery_coordinator import RecoveryCoordinator
from cbrowser.supervisor.resource_monitor import ResourceMonitor
from cbrowser.supervisor.resource_policy import ResourcePolicyService


class RuntimeLogFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, UTC).isoformat(
            timespec="milliseconds"
        )


handler = logging.StreamHandler()
handler.setFormatter(
    RuntimeLogFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("cbrowser.supervisor.runner")


async def run_supervisor(
    api_url: str,
    data_root: Path,
    engine_cache: Path,
    geoip_cache: Path | None = None,
    token_file: Path | None = None,
    agent_key_file: Path | None = None,
    gateway_url: str | None = None,
    resource_prefix: str = "cbrowser-t005",
    host: str = "127.0.0.1",
    port: int = 8005,
    gateway_control_url: str | None = None,
    gateway_token_file: Path | None = None,
    gateway_container_id: str | None = None,
    gateway_port: int | None = None,
    runtime_uid: int = 1000,
    runtime_gid: int = 1000,
    manage_ownership: bool | None = None,
    media_subnet_pool: str | None = None,
    deployment_instance_id: str | None = None,
    network_timeout: float | None = None,
):
    if agent_key_file is None or not Path(agent_key_file).is_file():
        raise ValueError(
            "Explicit Agent authentication key file (--agent-key-file) is required"
        )
    if gateway_control_url is None or gateway_token_file is None:
        raise ValueError(
            "Explicit Gateway control URL and authentication file are required"
        )

    validator = PathValidator(data_root)
    d_client = docker.from_env()

    headers = {}
    if token_file and token_file.is_file():
        try:
            token = read_secret_file(
                token_file, label="Supervisor API token", minimum_bytes=32
            )
        except RuntimeError as exc:
            raise ValueError(str(exc)) from None
        headers["Authorization"] = f"Bearer {token}"

    api_client = httpx.AsyncClient(
        base_url=api_url, headers=headers, timeout=10.0, trust_env=False
    )

    docker_adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=engine_cache,
        docker_client=d_client,
        resource_prefix=resource_prefix,
        geoip_cache_dir=geoip_cache,
        runtime_uid=runtime_uid,
        runtime_gid=runtime_gid,
        media_subnet_pool=media_subnet_pool,
        deployment_instance_id=deployment_instance_id,
        network_timeout=network_timeout,
        manage_ownership=(
            os.geteuid() == 0 if manage_ownership is None else manage_ownership
        ),
    )
    port_allocator = PortAllocator(
        min_port=int(os.environ.get("CBROWSER_UDP_MUX_MIN_PORT", PortAllocator.MIN_PORT)),
        max_port=int(os.environ.get("CBROWSER_UDP_MUX_MAX_PORT", PortAllocator.MAX_PORT)),
    )
    event_forwarder = EventForwarder(
        api_base_url=api_url,
        events_spool_dir=data_root / "spool",
        token_file=token_file,
        client=api_client,
    )

    core = SupervisorCore(
        docker_adapter=docker_adapter,
        port_allocator=port_allocator,
        event_forwarder=event_forwarder,
        api_client=api_client,
        gateway_url=gateway_url,
        token_file=token_file,
        agent_key_file=agent_key_file,
        gateway_control=GatewayControlClient(gateway_control_url, gateway_token_file),
        gateway_container_id=gateway_container_id,
        gateway_port=gateway_port,
    )

    async def send_quota(target, decision):
        await core.apply_profile_quota(
            target.profile_id,
            {
                "runtime_instance_id": target.runtime_instance_id,
                "max_fps_cap": decision.max_fps_cap,
            },
        )

    core.resource_monitor = ResourceMonitor(ResourcePolicyService(d_client), send_quota)

    try:
        # main() holds CoordinatorLock before reaching this startup-only reap.
        await docker_adapter.cleanup_orphan_helpers()
        await serve_supervisor(core, host, port)
    finally:
        await event_forwarder.close()
        await api_client.aclose()
        await core.gateway_control.close()
        d_client.close()


_TOPOLOGY_CONTAINER_ACTIONS = frozenset(
    {
        "create",
        "start",
        "restart",
        "die",
        "destroy",
        "kill",
        "stop",
        "oom",
        "pause",
        "unpause",
        "rename",
    }
)
# Only containers whose lifecycle changes convergence inputs may wake the
# scan loop. Supervisor-owned transient helpers (network-policy, x11
# permissions, cache-init) and infrastructure services (api/caddy/
# supervisor) are deliberately excluded: their events are either produced
# by the reconciliation itself or irrelevant to sandbox topology.
_CONVERGENCE_ROLES = frozenset({"browser", "stream", "gateway"})


def container_event_triggers_scan(event: Any, prefix: str) -> bool:
    """Whether a Docker container event can change the reconciled topology.

    This is the semantic trigger policy for the event-driven accelerator.
    Docker emits non-topology traffic on every supervised container:
    healthcheck ``exec_*`` actions for the infrastructure services, and
    the lifecycle of the Supervisor's own short-lived policy/x11/cache
    helpers. Waking the scan on those is self-exciting: a scan verifies
    policy by starting a helper, whose lifecycle event requests the next
    scan. Only business container lifecycle changes in this deployment may
    wake reconciliation (p057).
    """
    if not isinstance(event, dict):
        return False
    event_type = event.get("Type")
    if event_type not in (None, "container"):
        return False
    action = str(event.get("Action") or event.get("status") or "")
    if action.split(":", 1)[0] not in _TOPOLOGY_CONTAINER_ACTIONS:
        return False
    attributes = (event.get("Actor") or {}).get("Attributes") or {}
    if attributes.get("com.cbrowser.prefix") != prefix:
        return False
    return attributes.get("com.cbrowser.role") in _CONVERGENCE_ROLES


def _pump_container_events(
    stream: Any,
    prefix: str,
    on_match: Any,
    stop_event: threading.Event,
) -> None:
    for event in stream:
        if container_event_triggers_scan(event, prefix):
            on_match()
        if stop_event.is_set():
            break


def media_network_event_matches(event: Any, prefix: str) -> bool:
    """True when a Docker network event concerns a media network."""
    if not isinstance(event, dict):
        return False
    attributes = (event.get("Actor") or {}).get("Attributes") or {}
    name = attributes.get("name") or event.get("id") or ""
    return str(name).startswith(f"{prefix}-net-")


def _pump_network_events(
    stream: Any,
    prefix: str,
    on_match: Any,
    stop_event: threading.Event,
) -> None:
    for event in stream:
        if media_network_event_matches(event, prefix):
            on_match()
        if stop_event.is_set():
            break


def _watch_network_events(
    client: Any,
    prefix: str,
    stop_event: threading.Event | asyncio.Event,
    register_stream: Any,
    wake: Any,
    close_streams: Any,
) -> None:
    try:
        stream = client.events(decode=True, filters={"type": "network"})
        register_stream(stream)
        if stop_event.is_set():
            # Shutdown raced the subscription: the caller's finally-path
            # may already have run its close pass, so close here instead
            # of leaking a stream nobody will ever close.
            close_streams()
            return
        logger.info("Docker network events stream subscribed")
        _pump_network_events(stream, prefix, wake, stop_event)
    except Exception as exc:  # noqa: BLE001 - network event watching is an accelerator; scans still converge
        logger.warning(
            "Docker network event stream stopped: error_type=%s",
            type(exc).__name__,
        )


async def serve_supervisor(core: SupervisorCore, host: str, port: int) -> None:
    event_forwarder = core.events
    download_forwarder = DownloadArtifactForwarder(
        core.docker.validator.data_root, core.api
    )
    recovery = RecoveryCoordinator(core)

    # t027: start the FastAPI control server BEFORE the initial
    # reconciliation scan so liveness (/supervisor/v1/health, used by the
    # compose healthcheck) is never blocked by a slow or stuck scan; the
    # background monitor loop keeps reconciling after startup either way.
    if core._token_file is None:
        raise ValueError("Supervisor control authentication file is required")
    control_app = create_control_app(core=core, token_file=core._token_file)
    config = uvicorn.Config(
        app=control_app,
        host=host,
        port=port,
        log_level="info",
        timeout_graceful_shutdown=10,
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    logger.info("Supervisor initialized. Starting existing container reconciliation...")
    try:
        await core.scan_and_reconcile_existing()
    except Exception as exc:  # noqa: BLE001 - control plane is already up and retries reconciliation in background
        logger.warning(
            "Initial reconciliation failed; control plane will retry: error_type=%s",
            type(exc).__name__,
        )
    await event_forwarder.replay_spooled_events()
    await core.consume_disk_events()
    await download_forwarder.forward_pending()

    stop_event = asyncio.Event()
    events_stream: Any = None
    network_events_stream: Any = None
    stream_lock = threading.Lock()

    def _close_stream_sync() -> None:
        nonlocal events_stream, network_events_stream
        with stream_lock:
            targets = [events_stream, network_events_stream]
            events_stream = None
            network_events_stream = None
        for target in targets:
            if target is not None and hasattr(target, "close"):
                try:
                    target.close()
                except Exception as exc:  # noqa: BLE001 - docker event stream close failure during cleanup logged
                    logger.warning(
                        "Docker event stream close failed: %s",
                        type(exc).__name__,
                    )

    def handle_signal():
        logger.info("Received shutdown signal.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass

    metrics = StageMetrics()
    scan_wakeup = asyncio.Event()

    def watch_docker_events() -> None:
        nonlocal events_stream
        try:
            prefix = core.docker.resource_prefix
            stream = core.docker.client.events(
                decode=True,
                filters={
                    "type": "container",
                    "label": f"com.cbrowser.prefix={prefix}",
                },
            )
            with stream_lock:
                if stop_event.is_set():
                    if hasattr(stream, "close"):
                        try:
                            stream.close()
                        except Exception as exc:  # noqa: BLE001 - docker event stream close failure on early abort logged
                            logger.warning(
                                "Docker event stream close failed: %s",
                                type(exc).__name__,
                            )
                    return
                events_stream = stream

            logger.info("Docker events stream subscribed for prefix=%s", prefix)

            _pump_container_events(
                stream,
                prefix,
                lambda: loop.call_soon_threadsafe(scan_wakeup.set),
                stop_event,
            )
        except Exception as exc:  # noqa: BLE001 - docker events watching loop error isolated and logged
            logger.warning(
                "Docker event stream stopped: error_type=%s", type(exc).__name__
            )
        finally:
            _close_stream_sync()

    def watch_docker_network_events() -> None:
        # t026 AC-002: media network create/remove/disconnect events wake
        # the same scan loop, so Gateway replacement or a detached media
        # endpoint converges on the event instead of the 30 s fallback.
        nonlocal network_events_stream

        def _register(stream: Any) -> None:
            nonlocal network_events_stream
            with stream_lock:
                network_events_stream = stream

        _watch_network_events(
            core.docker.client,
            core.docker.resource_prefix,
            stop_event,
            _register,
            lambda: loop.call_soon_threadsafe(scan_wakeup.set),
            _close_stream_sync,
        )

    docker_events_task = asyncio.create_task(asyncio.to_thread(watch_docker_events))
    docker_network_events_task = asyncio.create_task(
        asyncio.to_thread(watch_docker_network_events)
    )

    # Background continuous event consumption; Docker scans are event-driven
    # with a 30 s fallback so state changes always converge.
    async def background_monitoring_loop():
        last_scan = 0.0
        container_snapshot: list[dict] | None = None
        while not stop_event.is_set():
            try:
                started = time.monotonic()
                await core.consume_disk_events()
                metrics.record("events", time.monotonic() - started)
                started = time.monotonic()
                await event_forwarder.replay_spooled_events()
                metrics.record("spool", time.monotonic() - started)
                started = time.monotonic()
                await download_forwarder.forward_pending()
                metrics.record("downloads", time.monotonic() - started)
                now = time.monotonic()
                if scan_wakeup.is_set() or now - last_scan >= 30.0:
                    scan_wakeup.clear()
                    last_scan = now
                    started = time.monotonic()
                    container_snapshot = await core.scan_and_reconcile_existing()
                    metrics.record("scan", time.monotonic() - started)
                started = time.monotonic()
                await recovery.tick(containers=container_snapshot)
                metrics.record("recovery", time.monotonic() - started)
                if metrics.should_report():
                    logger.info("Supervisor stage metrics: %s", metrics.snapshot())
            except Exception as exc:  # noqa: BLE001 - periodic reconciliation iteration error logged without crashing loop
                logger.warning(
                    "Reconciliation failed: error_type=%s", type(exc).__name__
                )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
            except TimeoutError:
                pass

    monitor_task = asyncio.create_task(background_monitoring_loop())

    async def resource_loop():
        # Independent, low-frequency and staggered away from the scan loop.
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=2.0)
        except TimeoutError:
            pass
        while not stop_event.is_set():
            started = time.monotonic()
            try:
                await core.sample_resources()
                metrics.record("resources", time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001 - resource monitoring sampling failure logged without crashing loop
                logger.warning("Resource monitoring failed: %s", type(exc).__name__)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5.0)
            except TimeoutError:
                pass

    resource_task = asyncio.create_task(resource_loop())

    logger.info("Supervisor running with background continuous monitoring.")
    stopped = asyncio.create_task(stop_event.wait())
    try:
        completed, _ = await asyncio.wait(
            {stopped, server_task, monitor_task, resource_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stopped not in completed:
            for task in completed:
                task.result()
            raise RuntimeError("Supervisor service task exited unexpectedly")
    finally:
        stop_event.set()
        await asyncio.to_thread(_close_stream_sync)
        server.should_exit = True
        stopped.cancel()
        monitor_task.cancel()
        resource_task.cancel()
        docker_events_task.cancel()
        docker_network_events_task.cancel()
        await recovery.close()
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    stopped,
                    monitor_task,
                    resource_task,
                    server_task,
                    docker_events_task,
                    docker_network_events_task,
                    return_exceptions=True,
                ),
                timeout=15,
            )
        except TimeoutError:
            server_task.cancel()
            await asyncio.gather(
                server_task, docker_events_task, return_exceptions=True
            )
    logger.info("Supervisor terminated gracefully without killing containers.")


def main():
    parser = argparse.ArgumentParser(description="CBrowser Runtime Supervisor")
    parser.add_argument(
        "--api-url", default=os.getenv("CBROWSER_API_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--data-root", default=os.getenv("CBROWSER_DATA_ROOT", "/data"))
    parser.add_argument(
        "--engine-cache",
        default=os.getenv("CBROWSER_ENGINE_CACHE", "/data/engine-cache"),
    )
    parser.add_argument("--geoip-cache", default=os.getenv("CBROWSER_GEOIP_CACHE"))
    parser.add_argument(
        "--token-file", default=os.getenv("CBROWSER_SUPERVISOR_TOKEN_FILE")
    )
    parser.add_argument(
        "--agent-key-file", default=os.getenv("CBROWSER_AGENT_KEY_FILE")
    )
    parser.add_argument(
        "--gateway-url", default=os.getenv("CBROWSER_GATEWAY_URL") or None
    )
    parser.add_argument(
        "--gateway-port",
        type=int,
        default=gateway_port_from_env(),
    )
    parser.add_argument(
        "--gateway-control-url", default=os.getenv("CBROWSER_GATEWAY_CONTROL_URL")
    )
    parser.add_argument(
        "--gateway-token-file", default=os.getenv("CBROWSER_GATEWAY_TOKEN_FILE")
    )
    parser.add_argument(
        "--gateway-container-id", default=os.getenv("CBROWSER_GATEWAY_CONTAINER_ID")
    )
    parser.add_argument("--prefix", default=None)
    parser.add_argument(
        "--deployment-instance-id",
        default=os.getenv("CBROWSER_INSTANCE_ID"),
        help="Deployment identity (A59/AC-021); compose sets it from the "
        "release identity. Sandboxes without this label are not claimed.",
    )
    parser.add_argument(
        "--docker-network-timeout",
        type=float,
        default=None,
        help="Seconds a Docker network call may hang before failing "
        "(AC-015); default 30, or CBROWSER_DOCKER_NETWORK_TIMEOUT.",
    )
    parser.add_argument(
        "--runtime-uid",
        type=int,
        default=int(os.getenv("CBROWSER_RUNTIME_UID", "1000")),
    )
    parser.add_argument(
        "--runtime-gid",
        type=int,
        default=int(os.getenv("CBROWSER_RUNTIME_GID", "1000")),
    )
    parser.add_argument(
        "--manage-ownership",
        choices=["auto", "1", "0"],
        default=os.getenv("CBROWSER_MANAGE_OWNERSHIP", "auto"),
    )
    parser.add_argument(
        "--media-subnet-pool",
        default=os.getenv("CBROWSER_MEDIA_SUBNET_POOL"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8005)

    args = parser.parse_args()

    # A22: fail fast on an invalid explicitly supplied prefix (via
    # --prefix or CBROWSER_PREFIX), before the lock and before any
    # Docker call. With nothing supplied, the compiled-in default
    # deployment prefix "cbrowser-t005" applies; it predates the A22
    # pattern and is not deployment input, so it is not validated.
    supplied_prefix = args.prefix or os.getenv("CBROWSER_PREFIX")
    resource_prefix = supplied_prefix or "cbrowser-t005"
    if supplied_prefix is not None:
        validate_resource_prefix(resource_prefix)

    validator = PathValidator(Path(args.data_root))
    lock_path = validator.validate_safe_path(
        validator.data_root / "control" / "supervisor.lock",
        allow_create=True,
    )
    with CoordinatorLock(lock_path):
        asyncio.run(
            run_supervisor(
                api_url=args.api_url,
                data_root=Path(args.data_root),
                engine_cache=Path(args.engine_cache),
                geoip_cache=Path(args.geoip_cache) if args.geoip_cache else None,
                token_file=Path(args.token_file) if args.token_file else None,
                agent_key_file=Path(args.agent_key_file)
                if args.agent_key_file
                else None,
                gateway_url=args.gateway_url,
                resource_prefix=resource_prefix,
                host=args.host,
                port=args.port,
                gateway_control_url=args.gateway_control_url,
                gateway_token_file=Path(args.gateway_token_file)
                if args.gateway_token_file
                else None,
                gateway_container_id=args.gateway_container_id,
                gateway_port=args.gateway_port,
                runtime_uid=args.runtime_uid,
                runtime_gid=args.runtime_gid,
                manage_ownership=(
                    None
                    if args.manage_ownership == "auto"
                    else args.manage_ownership == "1"
                ),
                media_subnet_pool=args.media_subnet_pool,
                deployment_instance_id=args.deployment_instance_id,
                network_timeout=args.docker_network_timeout,
            )
        )


if __name__ == "__main__":
    main()
