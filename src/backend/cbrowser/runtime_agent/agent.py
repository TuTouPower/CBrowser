"""FastAPI UDS Agent serving health, control, events, and CDP WebSocket proxy."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
import websockets
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .cdp_proxy import CdpProxyManager
from .download_reconciler import scan_completed_downloads
from .event_storage import EventStorage, StorageError
from .protocol import (
    ConfigVersionResponse,
    ControlRequest,
    ControlResponse,
    DownloadEventRecord,
    HealthResponse,
    RuntimeEventRecord,
)
from .security import validate_runtime_id
from .subsystems import check_audio, check_browser, check_display

logger = logging.getLogger("cbrowser.runtime_agent.agent")


def create_agent_app(
    run_dir: Path | str,
    default_download_dir: Path | str,
    events_dir: Path | str | None = None,
    cdp_proxy: CdpProxyManager | None = None,
) -> FastAPI:
    """Create FastAPI application configured for UDS control and CDP proxying."""
    r_dir = Path(run_dir)
    storage = EventStorage(Path(events_dir) if events_dir else r_dir)
    active_cdp_proxy = cdp_proxy

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(
        title="CBrowser Runtime Agent",
        version="2.0.0",
        description="Controlled UDS Agent for Browser Runtime lifecycle",
        lifespan=lifespan,
    )

    @app.exception_handler(StorageError)
    async def storage_failure(_request, error: StorageError):
        logger.error("Runtime storage unavailable (%s)", type(error).__name__)
        return JSONResponse(
            status_code=503, content={"error": "runtime_storage_failure"}
        )

    def _read_runner_info() -> dict[str, Any] | None:
        info_file = r_dir / "runner_info.json"
        if not info_file.exists():
            return None
        try:
            with open(info_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            identity = ConfigVersionResponse.model_validate(
                {
                    key: data[key]
                    for key in ("profile_id", "runtime_instance_id", "config_version")
                }
            )
            validate_runtime_id(identity.profile_id)
            validate_runtime_id(identity.runtime_instance_id)
            for key in ("cdp_port", "browser_pid", "runner_pid"):
                if key in data and (type(data[key]) is not int or data[key] < 1):
                    raise ValueError("Invalid runner process metadata")
            return data | identity.model_dump()
        except Exception:  # noqa: BLE001 - corrupt or missing metadata converted to StorageError
            raise StorageError("Invalid runner metadata") from None

    def _state_for_context(info: dict[str, Any] | None):
        profile = info.get("profile_id") if info else os.environ.get("PROFILE_ID")
        instance = (
            info.get("runtime_instance_id")
            if info
            else os.environ.get("RUNTIME_INSTANCE_ID")
        )
        if profile and instance:
            return storage.get_instance_state(profile, instance)
        return storage.get_state()

    @app.get("/health", response_model=HealthResponse)
    async def get_health() -> HealthResponse:
        runner_info = _read_runner_info()
        state = _state_for_context(runner_info)
        if state is None and runner_info is None:
            raise HTTPException(status_code=503, detail="Runtime is not initialized")

        r_info = runner_info or {}
        if runner_info and state:
            if (
                runner_info.get("profile_id") != state.profile_id
                or runner_info.get("runtime_instance_id") != state.runtime_instance_id
            ):
                raise StorageError("Runtime state identity mismatch")
            if int(runner_info.get("config_version", 1)) != state.config_version:
                raise StorageError("Runtime state version mismatch")

        profile_id = (
            r_info.get("profile_id")
            if runner_info
            else (state.profile_id if state else "unknown")
        )
        runtime_instance_id = (
            r_info.get("runtime_instance_id")
            if runner_info
            else (state.runtime_instance_id if state else "unknown")
        )
        config_version = (
            int(r_info.get("config_version", 1))
            if runner_info
            else (state.config_version if state else 1)
        )

        if state and state.state in ("stopped", "error"):
            # Cross-verify only for stopped: live process contradicts normal exit.
            # Errors (e.g. owner-loss with orphan Chrome alive) must never be masked.
            contradicted = False
            if state.state == "stopped":
                cdp_port = int(r_info.get("cdp_port", 0))
                browser_pid = r_info.get("browser_pid")
                if browser_pid is None and state.browser_pid is not None:
                    browser_pid = state.browser_pid

                pid_alive = False
                if browser_pid is not None:
                    try:
                        os.kill(browser_pid, 0)
                        pid_alive = True
                    except (ProcessLookupError, PermissionError) as exc:
                        pid_alive = isinstance(exc, PermissionError)
                    except OSError:
                        # Probe error / permission anomaly cannot be normal exit
                        pid_alive = True

                # Independently check CDP endpoint without early return on PID
                cdp_alive = False
                if cdp_port > 0:
                    try:
                        cdp_ok, _ = check_browser(cdp_port, browser_pid=None)
                        cdp_alive = cdp_ok
                    except Exception:  # noqa: BLE001 - probe anomaly defaults to alive to avoid falsely trusting terminal state
                        cdp_alive = True

                if pid_alive or cdp_alive:
                    contradicted = True
                    logger.warning(
                        "Terminal state contradicted by live browser process: "
                        "pid=%s (alive=%s) cdp_port=%s (alive=%s)",
                        browser_pid,
                        pid_alive,
                        cdp_port,
                        cdp_alive,
                    )

            if not contradicted:
                return HealthResponse(
                    status="error",
                    ready=False,
                    display_ready=False,
                    browser_ready=False,
                    audio_ready=False,
                    cdp_ready=False,
                    profile_id=profile_id,
                    runtime_instance_id=runtime_instance_id,
                    config_version=config_version,
                    details={
                        "state": state.state,
                        "exit_code": state.exit_code,
                        "exit_reason": state.exit_reason,
                    },
                )

        display = r_info.get("display", ":99")
        xauth_path = r_info.get("xauth_path")
        pulse_sock = r_info.get("pulse_sock", str(r_dir / "pulse" / "pulse.sock"))
        pulse_cookie = r_info.get("pulse_cookie", str(r_dir / "pulse" / "pulse.cookie"))
        cdp_port = int(r_info.get("cdp_port", 0))
        browser_pid = r_info.get("browser_pid")

        display_result, audio_result, browser_result = await asyncio.gather(
            asyncio.to_thread(check_display, display, xauth_path),
            asyncio.to_thread(check_audio, pulse_sock, pulse_cookie),
            asyncio.to_thread(check_browser, cdp_port, browser_pid),
        )
        display_ok, disp_msg = display_result
        audio_ok, audio_msg = audio_result
        browser_ok, browser_msg = browser_result
        cdp_ok = bool(
            browser_ok
            and "browser_ws_url" in r_info
            and active_cdp_proxy is not None
            and active_cdp_proxy.capture_alive
        )

        ready = bool(display_ok and audio_ok and browser_ok and cdp_ok)
        status = (
            "ok" if ready else ("degraded" if (display_ok or audio_ok) else "error")
        )

        return HealthResponse(
            status=status,
            ready=ready,
            display_ready=display_ok,
            browser_ready=browser_ok,
            audio_ready=audio_ok,
            cdp_ready=cdp_ok,
            profile_id=profile_id,
            runtime_instance_id=runtime_instance_id,
            config_version=config_version,
            details={
                "display": disp_msg,
                "audio": audio_msg,
                "browser": browser_msg,
                "browser_pid": browser_pid,
                "cdp_port": cdp_port,
                "rearm_count": active_cdp_proxy.rearm_count if active_cdp_proxy else 0,
            },
        )

    @app.get("/config_version", response_model=ConfigVersionResponse)
    async def get_config_version() -> ConfigVersionResponse:
        runner_info = _read_runner_info()
        if runner_info:
            return ConfigVersionResponse(
                profile_id=runner_info["profile_id"],
                runtime_instance_id=runner_info["runtime_instance_id"],
                config_version=runner_info["config_version"],
            )

        # Fallback to persistent state if runner_info is not present (offline/terminal
        # mode)
        state = _state_for_context(None)
        if state:
            return ConfigVersionResponse(
                profile_id=state.profile_id,
                runtime_instance_id=state.runtime_instance_id,
                config_version=state.config_version,
            )

        raise HTTPException(
            status_code=503, detail="Runner info or state not yet available"
        )

    @app.post("/control", response_model=ControlResponse)
    async def handle_control(req: ControlRequest) -> ControlResponse:
        if req.action == "close":
            logger.info("Control action requested: close")
            if not active_cdp_proxy:
                raise HTTPException(status_code=503, detail="CDP proxy not active")
            res = await active_cdp_proxy.close_browser()
            return ControlResponse(
                status="error" if "error" in res else "ok",
                action="close",
                message="close_unconfirmed" if "error" in res else "close_acknowledged",
            )
        elif req.action == "rearm_downloads":
            logger.info("Control action requested: rearm_downloads")
            if not active_cdp_proxy:
                raise HTTPException(status_code=503, detail="CDP proxy not active")
            await active_cdp_proxy.rearm_download_capture()
            return ControlResponse(
                status="ok",
                action="rearm_downloads",
                message=f"rearm_count={active_cdp_proxy.rearm_count}",
            )
        else:
            raise HTTPException(
                status_code=400, detail=f"Unknown control action: {req.action}"
            )

    @app.get("/events/runtime", response_model=list[RuntimeEventRecord])
    async def list_runtime_events() -> list[RuntimeEventRecord]:
        return storage.get_runtime_events()

    @app.get("/events/downloads", response_model=list[DownloadEventRecord])
    async def list_download_events() -> list[DownloadEventRecord]:
        return storage.get_download_events()

    @app.get("/cdp/version")
    async def get_cdp_version():
        runner_info = _read_runner_info()
        if not runner_info or "cdp_port" not in runner_info:
            raise HTTPException(status_code=503, detail="CDP port not yet available")
        url = f"http://127.0.0.1:{runner_info['cdp_port']}/json/version"

        def _fetch_version() -> dict[str, Any]:
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                return json.loads(resp.read().decode())

        try:
            content = await asyncio.to_thread(_fetch_version)
            return JSONResponse(content=content)
        except Exception:  # noqa: BLE001 - CDP HTTP probe failure maps to 502 Bad Gateway
            raise HTTPException(
                status_code=502, detail="CDP version unavailable"
            ) from None

    @app.websocket("/cdp")
    async def websocket_cdp_proxy(client_ws: WebSocket):
        await client_ws.accept()
        logger.info("External client connected to /cdp WebSocket")

        try:
            runner_info = _read_runner_info()
        except StorageError:
            await client_ws.close(code=1011, reason="Runtime metadata unavailable")
            return
        if not runner_info or "browser_ws_url" not in runner_info:
            await client_ws.close(code=1011, reason="CDP loopback not ready")
            return

        chrome_ws = None
        commands_sent = 0
        tunnel_tasks: list[asyncio.Task[None]] = []
        try:
            chrome_ws = await websockets.connect(
                runner_info["browser_ws_url"],
                max_size=32 * 1024 * 1024,
                ping_interval=10,
                ping_timeout=10,
            )

            async def client_to_chrome():
                nonlocal commands_sent
                while True:
                    msg = await client_ws.receive_text()
                    commands_sent += 1
                    await chrome_ws.send(msg)

            async def chrome_to_client():
                async for msg in chrome_ws:
                    await client_ws.send_text(msg)

            tunnel_tasks = [
                asyncio.create_task(client_to_chrome()),
                asyncio.create_task(chrome_to_client()),
            ]
            done, pending = await asyncio.wait(
                tunnel_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
        except WebSocketDisconnect:
            logger.info("External client disconnected from /cdp")
        except Exception as e:  # noqa: BLE001 - WebSocket tunnel worker isolation prevents process exit
            logger.warning("CDP proxy tunnel error (%s)", type(e).__name__)
        finally:
            for task in tunnel_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tunnel_tasks, return_exceptions=True)
            if chrome_ws:
                await chrome_ws.close()
            try:
                await client_ws.close()
            except Exception as exc:  # noqa: BLE001 - best-effort closing of client websocket on tunnel teardown
                logger.debug("Failed closing client_ws: %s", type(exc).__name__)

            # AUTOMATIC REARM TRIGGERED BY CLIENT DISCONNECT (only if commands were
            # actually sent)
            if active_cdp_proxy and commands_sent > 0:
                logger.info("Triggering automatic download behavior rearm...")
                try:
                    await active_cdp_proxy.rearm_download_capture()
                    await active_cdp_proxy.reconcile_downloads()
                    logger.info("Automatic download behavior rearm succeeded")
                except Exception as e:  # noqa: BLE001 - automatic download rearm failure logged without raising
                    logger.error(
                        "Failed to rearm download behavior (%s)", type(e).__name__
                    )

    return app


async def run_uds_agent(
    run_dir: Path | str,
    default_download_dir: Path | str,
    events_dir: Path | str | None = None,
    uds_path: Path | str | None = None,
) -> None:
    """Run standalone UDS Agent process consuming runner_info.json."""
    r_dir = Path(run_dir)
    sock_path = Path(uds_path) if uds_path else r_dir / "agent.sock"
    if sock_path.exists():
        sock_path.unlink()

    storage = EventStorage(Path(events_dir) if events_dir else r_dir)

    # Check persistent terminal state before starting CDP or Agent:
    # If state is already "stopped", Agent operates in offline replay mode (no Chrome /
    # CDP connection)
    expected_instance = os.environ.get("RUNTIME_INSTANCE_ID")
    expected_profile = os.environ.get("PROFILE_ID")
    prior_state = (
        storage.get_instance_state(
            expected_profile, expected_instance, recover_terminal=True
        )
        if expected_profile and expected_instance
        else storage.get_state()
    )
    is_terminal = (
        prior_state is not None
        and prior_state.state in ("stopped", "error")
        and (
            expected_instance is None
            or prior_state.runtime_instance_id == expected_instance
        )
    )

    cdp_proxy = None
    if not is_terminal:
        # Poll for runner_info.json
        runner_info_file = r_dir / "runner_info.json"
        runner_info: dict[str, Any] = {}
        for _ in range(100):
            if runner_info_file.exists():
                try:
                    content = await asyncio.to_thread(
                        runner_info_file.read_text, encoding="utf-8"
                    )
                    runner_info = json.loads(content)
                    if "browser_ws_url" in runner_info:
                        break
                except Exception as poll_exc:  # noqa: BLE001 - wait for valid metadata
                    logger.debug(
                        "Runner info poll pending: %s", type(poll_exc).__name__
                    )
            await asyncio.sleep(0.2)

        if not runner_info:
            logger.error(
                "Runner info file %s not found. Cannot start live CDP proxy.",
                runner_info_file,
            )
            raise RuntimeError(f"Runner info missing at {runner_info_file}")

        cdp_proxy = CdpProxyManager(
            browser_ws_url=runner_info["browser_ws_url"],
            default_download_dir=default_download_dir,
            profile_id=runner_info["profile_id"],
            runtime_instance_id=runner_info["runtime_instance_id"],
            event_storage=storage,
        )
        await cdp_proxy.start()
        await cdp_proxy.reconcile_downloads()
    else:
        logger.info(
            "Starting terminal Agent replay (state=%s)",
            prior_state.state if prior_state else "unknown",
        )
        if expected_profile and expected_instance:
            await scan_completed_downloads(
                default_download_dir,
                expected_profile,
                expected_instance,
                storage,
            )

    app = create_agent_app(
        run_dir=r_dir,
        default_download_dir=default_download_dir,
        events_dir=events_dir,
        cdp_proxy=cdp_proxy,
    )

    uvicorn_config = uvicorn.Config(
        app,
        uds=str(sock_path),
        log_level="warning",
        access_log=False,
    )
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    sock_path.parent.chmod(0o750)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old_umask = os.umask(0o077)
    try:
        listener.bind(str(sock_path))
    finally:
        os.umask(old_umask)
    try:
        # Set permissions before Uvicorn starts accepting. Passing an already
        # bound socket avoids its path-based chmod and any background race.
        sock_path.chmod(0o660)
        listener.setblocking(False)
        server = uvicorn.Server(uvicorn_config)
        logger.info("Browser Agent UDS listening")
        await server.serve(sockets=[listener])
    finally:
        listener.close()
        sock_path.unlink(missing_ok=True)
        if cdp_proxy:
            await cdp_proxy.close()


def main() -> None:
    """Command-line entrypoint for independent UDS Agent process."""
    import argparse

    parser = argparse.ArgumentParser(description="Browser Runtime UDS Agent")
    parser.add_argument(
        "--run-dir", required=True, help="Runtime directory containing runner_info.json"
    )
    parser.add_argument(
        "--download-dir", required=True, help="Default download directory"
    )
    parser.add_argument(
        "--events-dir", help="Directory for persistent events and state"
    )
    parser.add_argument("--uds-path", help="Explicit path to agent.sock")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] agent: %(message)s"
    )
    try:
        asyncio.run(
            run_uds_agent(
                run_dir=args.run_dir,
                default_download_dir=args.download_dir,
                events_dir=args.events_dir,
                uds_path=args.uds_path,
            )
        )
    except Exception as exc:  # noqa: BLE001 - CLI top-level exception handler exits cleanly with status 1
        logger.error("UDS Agent failed (%s)", type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
