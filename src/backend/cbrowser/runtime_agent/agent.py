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
from .preview_capture import (
    PREVIEW_MOUNT_DIR,
    PreviewCaptureLoop,
    cdp_send_from_proxy,
)
from .fontconfig import FONT_SET_MOUNT_ROOT, PLATFORM_FONTS_UNCONFIGURED
from .dialog_attendant import DialogAttendantService
from .tunnel_filter import TunnelFilter
from .download_reconciler import scan_completed_downloads
from .event_storage import EventStorage, StorageError, atomic_write_json
from .profile_defaults import (
    SEARCH_DEFAULTS_RETRY_FILE,
    read_search_defaults_status,
)
from .protocol import (
    ConfigVersionResponse,
    ControlRequest,
    ControlResponse,
    DownloadEventRecord,
    HealthResponse,
    RuntimeEventRecord,
    SearchDefaultsStatus,
)
from .security import validate_runtime_id
from .socket_root import (
    agent_socket_path,
    prepare_socket_dir,
    resolve_socket_root,
)
from .subsystems import check_audio, check_browser, check_display

logger = logging.getLogger("cbrowser.runtime_agent.agent")

_PLATFORM_DETECTION_LABELS: dict[str, tuple[str, ...]] = {
    "windows": ("windows", "office"),
    "macos": ("macos",),
}


def _validated_runner_info(runner_info: dict[str, Any]) -> dict[str, Any]:
    """Validate startup metadata before any CDP manager is constructed.

    Non-empty metadata with a missing field or a wrong-typed field is a hard
    startup failure with a redacted error; field values are never echoed.
    """
    try:
        if not isinstance(runner_info, dict):
            raise ValueError("Invalid runner metadata")
        profile_id = validate_runtime_id(runner_info["profile_id"])
        runtime_instance_id = validate_runtime_id(runner_info["runtime_instance_id"])
        browser_ws_url = runner_info["browser_ws_url"]
        if not isinstance(browser_ws_url, str) or not browser_ws_url.startswith(
            ("ws://", "wss://")
        ):
            raise ValueError("Invalid runner metadata")
        config_version = runner_info.get("config_version", 1)
        if type(config_version) is not int or config_version < 1:
            raise ValueError("Invalid runner metadata")
        for key in ("cdp_port", "browser_pid", "runner_pid"):
            if key in runner_info and (
                type(runner_info[key]) is not int or runner_info[key] < 1
            ):
                raise ValueError("Invalid runner metadata")
    except Exception:  # noqa: BLE001 - any malformed metadata becomes one safe error
        raise StorageError("Invalid runner metadata") from None
    return {
        **runner_info,
        "profile_id": profile_id,
        "runtime_instance_id": runtime_instance_id,
        "config_version": config_version,
    }


def create_agent_app(
    run_dir: Path | str,
    default_download_dir: Path | str,
    events_dir: Path | str | None = None,
    cdp_proxy: CdpProxyManager | None = None,
    font_set_root: Path | str | None = None,
    preview_loop: PreviewCaptureLoop | None = None,
) -> FastAPI:
    """Create FastAPI application configured for UDS control and CDP proxying."""
    r_dir = Path(run_dir)
    font_root = Path(font_set_root) if font_set_root is not None else FONT_SET_MOUNT_ROOT
    font_runtime_cache: dict[tuple[str, str], tuple[str | None, list[str]]] = {}
    storage = EventStorage(Path(events_dir) if events_dir else r_dir)
    active_cdp_proxy = cdp_proxy
    # t031: resident dialog attendant (one per Agent process). Armed on
    # /cdp client connect, released on takeover cascade / Agent stop.
    dialog_attendant = DialogAttendantService()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task: asyncio.Task[None] | None = None
        if preview_loop is not None:
            task = asyncio.create_task(preview_loop.run(), name="preview_capture")
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

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

    def _search_defaults_status() -> SearchDefaultsStatus | None:
        raw = read_search_defaults_status(r_dir)
        if raw is None:
            return None
        try:
            return SearchDefaultsStatus(
                state=raw["state"],
                error_kind=raw.get("error_kind"),
                runtime_instance_id=str(raw.get("runtime_instance_id") or ""),
                request_id=raw.get("request_id"),
                updated_at=str(raw.get("updated_at") or ""),
            )
        except Exception:  # noqa: BLE001 - malformed status is reported as unknown
            return None

    def _font_runtime() -> tuple[str | None, list[str]]:
        """Bound font set id plus its missing detection fonts for /health.

        The font set is content-addressed and immutable, so the integrity/
        detection scan (which hashes every font file) is cached per
        (platform, set_id) instead of running on every health probe. A null
        binding reports the "platform fonts not configured" state as
        ``(None, [PLATFORM_FONTS_UNCONFIGURED])``.
        """
        try:
            snapshot = json.loads(
                (r_dir / "snapshot.json").read_text(encoding="utf-8")
            )
            cfg = snapshot.get("config") if isinstance(snapshot, dict) else None
        except (OSError, ValueError):
            return None, []
        if not isinstance(cfg, dict):
            return None, []
        font_set_id = cfg.get("font_set_id")
        if not font_set_id:
            return None, [PLATFORM_FONTS_UNCONFIGURED]
        platform = cfg.get("fingerprint_platform", "windows")
        if platform not in _PLATFORM_DETECTION_LABELS:
            return str(font_set_id), []
        key = (str(platform), str(font_set_id))
        if key not in font_runtime_cache:
            from cbrowser import font_sets

            directory = font_root / str(platform) / str(font_set_id)
            detection = font_sets.check_font_set(directory).get("detection", {})
            missing = sorted(
                {
                    name
                    for label in _PLATFORM_DETECTION_LABELS[platform]
                    for name in detection.get(label, {}).get("missing", [])
                }
            )
            font_runtime_cache[key] = (str(font_set_id), missing)
        return font_runtime_cache[key]

    @app.get("/health", response_model=HealthResponse)
    async def get_health() -> HealthResponse:
        font_set_id, missing_fonts = _font_runtime()
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
                        "browser_product": None,
                        "browser_user_agent": None,
                        "font_set_id": font_set_id,
                        "missing_fonts": missing_fonts,
                        "preview_captured_at": preview_loop.last_captured_at
                        if preview_loop
                        else None,
                    },
                    search_defaults=_search_defaults_status(),
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
                "browser_product": r_info.get("browser_product"),
                "browser_user_agent": r_info.get("browser_user_agent"),
                "font_set_id": font_set_id,
                "missing_fonts": missing_fonts,
                "preview_captured_at": preview_loop.last_captured_at
                if preview_loop
                else None,
            },
            search_defaults=_search_defaults_status(),
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
        elif req.action == "release_attendant":
            # t031: takeover cascade releases the resident dialog
            # attendant so held dialogs return to Chrome's default
            # handling (visible to the human in the video stream).
            await dialog_attendant.release()
            return ControlResponse(
                status="ok",
                action="release_attendant",
                message="attendant_released",
            )
        elif req.action == "list_attendant_dialogs":
            # t031: peek held dialogs for a later agent session. A
            # session attached after a dialog opened cannot observe or
            # answer it through its own CDP session (chain evidence),
            # so the peek is the discovery step for the answer path.
            return ControlResponse(
                status="ok",
                action="list_attendant_dialogs",
                message="attendant_dialogs",
                data={
                    "dialogs": [
                        d.to_dict()
                        for d in dialog_attendant.attendant.held_dialogs()
                    ]
                },
            )
        elif req.action == "answer_attendant_dialog":
            # t031: only the attendant's pre-existing session can
            # answer a held dialog; this is the explicit control-plane
            # answer path used by a later session's dialog_answer.
            target_id = str(req.params.get("target_id", ""))
            accept = bool(req.params.get("accept", False))
            prompt_text = req.params.get("prompt_text")
            answered = await dialog_attendant.answer_dialog(
                target_id,
                accept,
                prompt_text if isinstance(prompt_text, str) else None,
            )
            if answered is None:
                raise HTTPException(
                    status_code=404, detail="no held dialog for target"
                )
            return ControlResponse(
                status="ok",
                action="answer_attendant_dialog",
                message="attendant_dialog_answered",
                data={"dialog": answered},
            )
        elif req.action == "retry_search_defaults":
            # Fenced, idempotent retry: the request must name the exact live
            # instance from runner metadata; the runner consumes the request
            # file against its live context without restarting the browser.
            runner_info = _read_runner_info()
            if runner_info is None:
                raise HTTPException(
                    status_code=503, detail="Runtime metadata unavailable"
                )
            profile_id = req.params.get("profile_id")
            instance_id = req.params.get("runtime_instance_id")
            request_id = req.params.get("request_id")
            if (
                profile_id != runner_info["profile_id"]
                or instance_id != runner_info["runtime_instance_id"]
                or not isinstance(request_id, str)
                or not request_id
                or len(request_id) > 128
            ):
                raise HTTPException(
                    status_code=403, detail="Search defaults retry rejected"
                )
            atomic_write_json(
                r_dir / SEARCH_DEFAULTS_RETRY_FILE,
                {
                    "profile_id": profile_id,
                    "runtime_instance_id": instance_id,
                    "request_id": request_id,
                },
            )
            logger.info("Control action requested: retry_search_defaults")
            return ControlResponse(
                status="ok",
                action="retry_search_defaults",
                message=f"request_id={request_id}",
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
        elif req.action == "preview_policy":
            if preview_loop is None:
                raise HTTPException(
                    status_code=503, detail="Preview capture not active"
                )
            preview_loop.set_policy(
                enabled=bool(req.params.get("enabled")),
                epoch=int(req.params.get("epoch", 0)),
                runtime_instance_id=req.params.get("runtime_instance_id"),
            )
            return ControlResponse(
                status="ok",
                action="preview_policy",
                message="preview_policy_updated",
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
        tunnel_filter = TunnelFilter()
        tunnel_tasks: list[asyncio.Task[None]] = []
        try:
            chrome_ws = await websockets.connect(
                runner_info["browser_ws_url"],
                max_size=32 * 1024 * 1024,
                ping_interval=10,
                ping_timeout=10,
            )
            # t031: every tunneled session passes through this proxy,
            # so arming here covers both API and Supervisor paths.
            # Idempotent: a running attendant is left alone.
            dialog_attendant.arm(runner_info["browser_ws_url"])

            async def client_to_chrome():
                nonlocal commands_sent
                while True:
                    msg = await client_ws.receive_text()
                    try:
                        parsed = json.loads(msg)
                    except (ValueError, TypeError):
                        parsed = None
                    if isinstance(parsed, dict):
                        decision, response = tunnel_filter.filter_outgoing(parsed)
                        if decision == "reject":
                            if response is not None:
                                await client_ws.send_text(json.dumps(response))
                            continue
                    commands_sent += 1
                    await chrome_ws.send(msg)

            async def chrome_to_client():
                async for msg in chrome_ws:
                    try:
                        parsed = json.loads(msg)
                    except (ValueError, TypeError):
                        parsed = None
                    if isinstance(parsed, dict):
                        tunnel_filter.observe_incoming(parsed)
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
                # Best-effort removal of per-session scripts this connection
                # registered, before the browser-level socket goes away.
                try:
                    for cmd in tunnel_filter.disconnect_cleanup_commands():
                        await chrome_ws.send(json.dumps(cmd))
                except Exception as exc:  # noqa: BLE001 - cleanup must not break teardown
                    logger.debug(
                        "Tunnel script cleanup failed (%s)", type(exc).__name__
                    )
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
    expected_instance = os.environ.get("RUNTIME_INSTANCE_ID")
    expected_profile = os.environ.get("PROFILE_ID")

    storage = EventStorage(Path(events_dir) if events_dir else r_dir)

    # Check persistent terminal state before starting CDP or Agent:
    # If state is already "stopped", Agent operates in offline replay mode (no Chrome /
    # CDP connection)
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
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        runner_info = parsed
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

        # Non-empty but incomplete or mistyped metadata is rejected with a
        # redacted error instead of crashing on a raw key lookup.
        runner_info = _validated_runner_info(runner_info)

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

    preview_loop = None
    if cdp_proxy is not None:
        preview_loop = PreviewCaptureLoop(
            data_root=PREVIEW_MOUNT_DIR,
            cdp_send=cdp_send_from_proxy(cdp_proxy),
            instance_id=expected_instance or "",
        )

    app = create_agent_app(
        run_dir=r_dir,
        default_download_dir=default_download_dir,
        events_dir=events_dir,
        cdp_proxy=cdp_proxy,
        preview_loop=preview_loop,
    )

    if uds_path:
        sock_path = Path(uds_path)
    else:
        if not expected_profile or not expected_instance:
            raise RuntimeError("Managed socket identity unavailable")
        root = resolve_socket_root()
        prepare_socket_dir(root, expected_profile, expected_instance)
        sock_path = agent_socket_path(root, expected_profile, expected_instance)

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
