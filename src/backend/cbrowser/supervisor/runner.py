"""Entrypoint module for running Supervisor service with Control HTTP server."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from datetime import UTC, datetime
from pathlib import Path

import docker
import httpx
import uvicorn
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.coordinator_lock import CoordinatorLock
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.gateway_client import GatewayControlClient
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
    gateway_url: str = "ws://host.docker.internal:18097",
    resource_prefix: str = "cbrowser-t005",
    host: str = "127.0.0.1",
    port: int = 8005,
    gateway_control_url: str | None = None,
    gateway_token_file: Path | None = None,
    gateway_container_id: str | None = None,
    coturn_container_id: str | None = None,
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
        t = token_file.read_text(encoding="utf-8").strip()
        headers["Authorization"] = f"Bearer {t}"

    api_client = httpx.AsyncClient(
        base_url=api_url, headers=headers, timeout=10.0, trust_env=False
    )

    docker_adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=engine_cache,
        docker_client=d_client,
        resource_prefix=resource_prefix,
        geoip_cache_dir=geoip_cache,
    )
    port_allocator = PortAllocator()
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
        coturn_container_id=coturn_container_id,
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


async def serve_supervisor(core: SupervisorCore, host: str, port: int) -> None:
    event_forwarder = core.events
    recovery = RecoveryCoordinator(core)

    logger.info("Supervisor initialized. Starting existing container reconciliation...")
    await core.scan_and_reconcile_existing()
    await event_forwarder.replay_spooled_events()
    await core.consume_disk_events()

    # Start FastAPI control server
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

    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Received shutdown signal.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass

    # Background continuous reconciliation and event spool replay loop
    async def background_monitoring_loop():
        while not stop_event.is_set():
            try:
                await core.consume_disk_events()
                await event_forwarder.replay_spooled_events()
                await core.scan_and_reconcile_existing()
                await recovery.tick()
            except Exception as exc:
                logger.warning(
                    "Reconciliation failed: error_type=%s", type(exc).__name__
                )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    monitor_task = asyncio.create_task(background_monitoring_loop())

    async def resource_loop():
        while not stop_event.is_set():
            try:
                await core.sample_resources()
            except Exception as exc:
                logger.warning("Resource monitoring failed: %s", type(exc).__name__)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
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
        server.should_exit = True
        stopped.cancel()
        monitor_task.cancel()
        resource_task.cancel()
        await recovery.close()
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    stopped,
                    monitor_task,
                    resource_task,
                    server_task,
                    return_exceptions=True,
                ),
                timeout=15,
            )
        except asyncio.TimeoutError:
            server_task.cancel()
            await asyncio.gather(server_task, return_exceptions=True)
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
        "--gateway-url",
        default=os.getenv("CBROWSER_GATEWAY_URL", "ws://host.docker.internal:18097"),
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
    parser.add_argument(
        "--coturn-container-id", default=os.getenv("CBROWSER_COTURN_CONTAINER_ID")
    )
    parser.add_argument(
        "--prefix", default=os.getenv("CBROWSER_PREFIX", "cbrowser-t005")
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8005)

    args = parser.parse_args()

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
                resource_prefix=args.prefix,
                host=args.host,
                port=args.port,
                gateway_control_url=args.gateway_control_url,
                gateway_token_file=Path(args.gateway_token_file)
                if args.gateway_token_file
                else None,
                gateway_container_id=args.gateway_container_id,
                coturn_container_id=args.coturn_container_id,
            )
        )


if __name__ == "__main__":
    main()
