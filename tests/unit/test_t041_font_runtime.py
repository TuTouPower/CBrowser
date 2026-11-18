"""t041 AC-006 / AC-007 / AC-008 runtime unit proofs.

Font-set fail-closed, read-only mounts, /health font fields and the
API response / SSE passthrough. Static/unit assertions only; the image
layer scan (AC-008) belongs to the gate / E2E and is deliberately not run
here.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from cbrowser.domain.models import Profile, ProfileConfig, ProfileRuntime
from cbrowser.font_sets import import_font_set

WINDOWS_DETECTION_FONTS = (
    "arial.ttf",
    "calibri.ttf",
    "cour.ttf",
    "georgia.ttf",
    "tahoma.ttf",
    "times.ttf",
    "trebuc.ttf",
    "verdana.ttf",
    "calibrib.ttf",
    "calibrii.ttf",
    "calibriz.ttf",
    "cambria.ttc",
    "cambriab.ttf",
    "Candara.ttf",
    "consola.ttf",
    "constan.ttf",
    "corbel.ttf",
)


def _make_font_set(
    tmp_path: Path,
    *,
    platform: str = "windows",
    names: tuple[str, ...] = WINDOWS_DETECTION_FONTS,
    fonts_root: Path | None = None,
) -> tuple[Path, str]:
    source = tmp_path / "src" / platform
    source.mkdir(parents=True, exist_ok=True)
    for name in names:
        (source / name).write_bytes(b"font-bytes-" + name.encode("utf-8"))
    root = fonts_root if fonts_root is not None else tmp_path / "fonts"
    result = import_font_set(platform, [source], "unit-1.0", root=root)
    return root, result["set_id"]


def _profile(config: ProfileConfig) -> Profile:
    return Profile(
        id="p1",
        config=config,
        display_number=1,
        user_data_dir="/data/profiles/p1/profile",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _runtime() -> ProfileRuntime:
    return ProfileRuntime(
        profile_id="p1",
        desired_state="running",
        observed_state="running",
        runtime_instance_id="i1",
        config_version=1,
        display_number=1,
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _agent_key(tmp_path: Path) -> Path:
    key = tmp_path / "agent_key"
    key.write_text("01234567890123456789012345678901", encoding="utf-8")
    key.chmod(0o600)
    return key


def _running_handler(req: httpx.Request) -> httpx.Response:
    # t083: start intent is read through the minimal batch snapshot.
    if req.url.path.endswith("/state/snapshot"):
        state = {
            "profile_id": "p1",
            "display_number": 1,
            "desired_state": "running",
            "observed_state": "stopped",
            "runtime_instance_id": None,
            "config_version": 1,
            "failure_count": 0,
            "restart_blocked": False,
            "last_exit_event_id": None,
            "backoff_started_at": None,
            "next_retry_at": None,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "state_revision": 1,
        }
        return httpx.Response(
            200,
            json={
                "api_epoch": "t041-test-epoch",
                "profiles": [state],
                "next_cursor": None,
            },
        )
    return httpx.Response(
        200,
        json={"status": "ok", "desired_state": "running", "restart_blocked": False},
    )


def _light_core(tmp_path: Path, api: httpx.AsyncClient):
    from cbrowser.supervisor.core import SupervisorCore
    from cbrowser.supervisor.path_validator import PathValidator
    from cbrowser.supervisor.port_allocator import PortAllocator

    root = (tmp_path / "data").resolve()
    (root / "engine_cache" / "geoip").mkdir(parents=True)
    validator = PathValidator(root)
    dirs = {"runtime": root / "runtime" / "p1"}
    dirs["runtime"].mkdir(parents=True)
    adapter = SimpleNamespace(
        validator=validator,
        manage_ownership=False,
        prepare_profile_directories=lambda _: dirs,
        create_profile_network=AsyncMock(),
        start_browser_container=AsyncMock(),
        start_stream_container=AsyncMock(),
        teardown_profile=AsyncMock(),
        ensure_runtime_cache=AsyncMock(),
    )
    events = SimpleNamespace(
        drain_runtime_events=AsyncMock(return_value=0),
        forward_exit_event=AsyncMock(),
        emit_event=AsyncMock(),
    )
    core = SupervisorCore(
        docker_adapter=adapter,
        port_allocator=PortAllocator(30000, 30010),
        event_forwarder=events,
        api_client=api,
        token_file=None,
        agent_key_file=_agent_key(tmp_path),
    )
    core.report_terminal_observation = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return core, adapter


async def test_start_profile_fail_closed_when_font_set_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cbrowser.supervisor.core import (
        FONT_SET_UNAVAILABLE,
        FontSetUnavailableError,
    )

    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(tmp_path / "fonts"))
    transport = httpx.MockTransport(_running_handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as api:
        core, adapter = _light_core(tmp_path, api)
        with pytest.raises(FontSetUnavailableError) as exc:
            await core.start_profile(
                "p1",
                ProfileConfig(
                    name="p1",
                    fingerprint_platform="windows",
                    font_set_id="a" * 64,
                ),
            )
        assert str(exc.value) == FONT_SET_UNAVAILABLE
        reason_kwargs = core.report_terminal_observation.call_args.kwargs  # type: ignore[attr-defined]
        assert reason_kwargs["reason"] == FONT_SET_UNAVAILABLE
    adapter.start_browser_container.assert_not_awaited()  # type: ignore[attr-defined]


async def test_start_profile_fail_closed_when_font_set_tampered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cbrowser.supervisor.core import (
        FONT_SET_UNAVAILABLE,
        FontSetUnavailableError,
    )

    fonts_root, set_id = _make_font_set(tmp_path)
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(fonts_root))
    (fonts_root / "windows" / set_id / "arial.ttf").unlink()
    transport = httpx.MockTransport(_running_handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as api:
        core, adapter = _light_core(tmp_path, api)
        with pytest.raises(FontSetUnavailableError) as exc:
            await core.start_profile(
                "p1",
                ProfileConfig(
                    name="p1",
                    fingerprint_platform="windows",
                    font_set_id=set_id,
                ),
            )
        assert str(exc.value) == FONT_SET_UNAVAILABLE
        assert core.report_terminal_observation.call_args.kwargs["reason"] == FONT_SET_UNAVAILABLE  # type: ignore[attr-defined]
    adapter.start_browser_container.assert_not_awaited()  # type: ignore[attr-defined]


async def test_start_profile_starts_with_bound_fonts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """t075: the absent-fonts half of the old parametrized test asserted
    the abolished "platform fonts not configured" start; an unbound
    profile now fails closed (see test_t075_supervisor_fonts)."""
    from cbrowser.supervisor.core import SupervisorCore
    from cbrowser.supervisor.path_validator import PathValidator
    from cbrowser.supervisor.port_allocator import PortAllocator

    fonts_root, font_set_id = _make_font_set(tmp_path, fonts_root=tmp_path / "fonts")
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(fonts_root))

    root = (tmp_path / "data").resolve()
    (root / "engine_cache" / "geoip").mkdir(parents=True)
    validator = PathValidator(root)
    dirs = {
        "profile": root / "profiles" / "p1",
        "runtime": root / "runtime" / "p1",
        "events": root / "events" / "p1",
        "exchange": root / "exchange" / "p1",
        "x11": root / "runtime" / "p1" / "x11",
        "pulse": root / "runtime" / "p1" / "pulse",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    stream_c = MagicMock()
    stream_c.id = "s_id"
    stream_c.name = "stream_c"
    stream_c.status = "running"
    stream_c.reload = MagicMock()
    browser_c = MagicMock()
    browser_c.id = "b_id"
    browser_c.name = "browser_c"

    def write_runner_info(profile_id, runtime_instance_id, snapshot_json_path):
        (dirs["runtime"] / "x11" / "X99").touch()
        (dirs["runtime"] / "pulse" / "pulse.sock").touch()
        (dirs["runtime"] / "Xauthority").touch()
        (dirs["runtime"] / "agent.sock").touch()
        (dirs["runtime"] / "runner_info.json").write_text(
            json.dumps(
                {
                    "profile_id": profile_id,
                    "runtime_instance_id": runtime_instance_id,
                    "config_version": 1,
                    "browser_pid": 12345,
                }
            ),
            encoding="utf-8",
        )
        return browser_c

    adapter = SimpleNamespace(
        validator=validator,
        manage_ownership=False,
        prepare_profile_directories=lambda _: dirs,
        create_profile_network=AsyncMock(),
        attach_profile_infrastructure=MagicMock(return_value={}),
        start_browser_container=AsyncMock(side_effect=write_runner_info),
        start_stream_container=AsyncMock(return_value=stream_c),
        teardown_profile=AsyncMock(),
        cleanup_profile_processes=MagicMock(),
        ensure_runtime_cache=AsyncMock(),
    )
    events = SimpleNamespace(
        drain_runtime_events=AsyncMock(return_value=0),
        forward_exit_event=AsyncMock(),
        emit_event=AsyncMock(),
    )
    gateway = SimpleNamespace(
        has_foreground_viewers=AsyncMock(return_value=True),
        disconnect_viewers=AsyncMock(),
    )
    transport = httpx.MockTransport(_running_handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as api:
        core = SupervisorCore(
            docker_adapter=adapter,
            port_allocator=PortAllocator(30000, 30010),
            event_forwarder=events,
            api_client=api,
            gateway_url="ws://supervisor-host-gw:18097",
            token_file=None,
            agent_key_file=_agent_key(tmp_path),
            gateway_control=gateway,
        )
        session = await core.start_profile(
            "p1",
            ProfileConfig(
                name="p1",
                fingerprint_platform="windows",
                font_set_id=font_set_id,
            ),
        )
    assert session.observed_state == "running"
    adapter.start_browser_container.assert_awaited_once()  # type: ignore[attr-defined]


def _write_agent_files(
    tmp_path: Path, config: dict, font_verification: dict | None = None
) -> tuple[Path, Path]:
    run_dir = tmp_path / "runtime"
    run_dir.mkdir(parents=True, exist_ok=True)
    runner_info: dict = {
        "profile_id": "test_profile",
        "runtime_instance_id": "test_instance",
        "config_version": 1,
        "cdp_port": 9222,
        "browser_ws_url": "ws://127.0.0.1:9222/cdp",
        "display": ":99",
        "pulse_sock": str(run_dir / "pulse.sock"),
        "pulse_cookie": str(run_dir / "pulse.cookie"),
        "browser_pid": 1234,
        "runner_pid": 5678,
    }
    if font_verification is not None:
        runner_info["font_verification"] = font_verification
    (run_dir / "runner_info.json").write_text(
        json.dumps(runner_info),
        encoding="utf-8",
    )
    (run_dir / "snapshot.json").write_text(
        json.dumps({"version": 1, "config": config}), encoding="utf-8"
    )
    return run_dir, tmp_path / "downloads"


def _verdict(set_id: str, *, missing_optional=(), status: str = "verified") -> dict:
    return {
        "status": status,
        "failure": None if status == "verified" else "font_mount_missing",
        "font_set_id": set_id,
        "missing_optional": list(missing_optional),
        "effective_fonts": 12,
    }


async def _health_details(run_dir: Path, download_dir: Path) -> dict:
    from cbrowser.runtime_agent.agent import create_agent_app

    app = create_agent_app(
        run_dir=run_dir,
        default_download_dir=download_dir,
        cdp_proxy=None,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    return resp.json()["details"]


async def test_health_details_report_bound_font_set(tmp_path: Path) -> None:
    """t075: health carries the Runner's per-instance verdict — the
    bound set id and its optional-coverage gaps — without re-scanning
    font bytes in the Agent."""
    _fonts_root, set_id = _make_font_set(tmp_path)
    run_dir, download_dir = _write_agent_files(
        tmp_path,
        {"fingerprint_platform": "windows", "font_set_id": set_id},
        font_verification=_verdict(set_id),
    )
    details = await _health_details(run_dir, download_dir)
    assert details["font_set_id"] == set_id
    assert details["missing_fonts"] == []
    assert details["font_verification"]["status"] == "verified"


async def test_health_details_when_font_set_absent(tmp_path: Path) -> None:
    """t075 rewrite: the abolished "platform fonts unconfigured / Linux
    base fonts exposed" marker is gone.  An instance with no recorded
    verdict reports no binding and no verdict (and is never ready —
    see test_health_ready_is_gated_by_font_verdict)."""
    run_dir, download_dir = _write_agent_files(
        tmp_path,
        {"fingerprint_platform": "windows", "font_set_id": None},
    )
    details = await _health_details(run_dir, download_dir)
    assert details["font_set_id"] is None
    assert details["missing_fonts"] == []
    assert details["font_verification"] is None


async def test_health_details_report_missing_detection_fonts(tmp_path: Path) -> None:
    _fonts_root, set_id = _make_font_set(tmp_path, names=("arial.ttf",))
    run_dir, download_dir = _write_agent_files(
        tmp_path,
        {"fingerprint_platform": "windows", "font_set_id": set_id},
        font_verification=_verdict(set_id, missing_optional=["verdana.ttf"]),
    )
    details = await _health_details(run_dir, download_dir)
    assert details["font_set_id"] == set_id
    assert "verdana.ttf" in details["missing_fonts"]
    assert "arial.ttf" not in details["missing_fonts"]


async def test_health_ready_is_gated_by_font_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-006: with every other subsystem healthy, a failed (or
    missing) font verdict alone keeps ready=False; a verified verdict
    lets ready become True."""
    from types import SimpleNamespace

    from cbrowser.runtime_agent import agent as agent_module
    from cbrowser.runtime_agent.agent import create_agent_app

    monkeypatch.setattr(
        agent_module, "check_display", lambda *a, **k: (True, "ok")
    )
    monkeypatch.setattr(
        agent_module, "check_audio", lambda *a, **k: (True, "ok")
    )
    monkeypatch.setattr(
        agent_module, "check_browser", lambda *a, **k: (True, "ok")
    )
    _fonts_root, set_id = _make_font_set(tmp_path)

    async def _ready(verdict: dict | None) -> bool:
        run_dir = tmp_path / ("run-" + (verdict["status"] if verdict else "none"))
        run_dir.mkdir(parents=True, exist_ok=True)
        download_dir = tmp_path / "downloads"
        info: dict = {
            "profile_id": "test_profile",
            "runtime_instance_id": "test_instance",
            "config_version": 1,
            "cdp_port": 9222,
            "browser_ws_url": "ws://127.0.0.1:9222/cdp",
            "display": ":99",
            "pulse_sock": str(run_dir / "pulse.sock"),
            "pulse_cookie": str(run_dir / "pulse.cookie"),
            "browser_pid": 1234,
            "runner_pid": 5678,
        }
        if verdict is not None:
            info["font_verification"] = verdict
        (run_dir / "runner_info.json").write_text(
            json.dumps(info), encoding="utf-8"
        )
        app = create_agent_app(
            run_dir=run_dir,
            default_download_dir=download_dir,
            cdp_proxy=SimpleNamespace(capture_alive=True, rearm_count=0),
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        return resp.json()["ready"]

    assert await _ready(_verdict(set_id)) is True
    assert await _ready(_verdict(set_id, status="failed")) is False
    assert await _ready(None) is False


async def test_runtime_response_and_sse_carry_font_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cbrowser.api.runtime_coordinator import RuntimeCoordinator
    from cbrowser.api.v1.runtime_views import make_runtime_response

    fonts_root, set_id = _make_font_set(tmp_path)
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(fonts_root))
    config = ProfileConfig(
        name="p1", fingerprint_platform="windows", font_set_id=set_id
    )
    service = SimpleNamespace(
        get_profile=AsyncMock(return_value=_profile(config)),
        get_runtime=AsyncMock(return_value=_runtime()),
    )
    broadcaster = SimpleNamespace(publish=AsyncMock())
    coordinator = RuntimeCoordinator(
        supervisor_url=None,
        supervisor_token=None,
        profile_service=service,
        event_broadcaster=broadcaster,
    )
    response = await make_runtime_response(_runtime(), coordinator)
    assert response.font_set_id == set_id
    assert response.missing_fonts == []

    await coordinator.publish_profile_change("p1")
    event_data = broadcaster.publish.call_args.args[0]  # type: ignore[attr-defined]
    assert event_data.font_set_id == set_id
    assert event_data.missing_fonts == []


async def test_runtime_response_when_unset_has_no_base_fonts_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """t075 rewrite of the AC-006 marker test: the "platform fonts
    unconfigured / Linux base fonts" marker is abolished along with the
    fallback it described.  An unbound profile (only reachable with a
    pre-migration snapshot) reports no binding and an empty
    missing-fonts list."""
    from cbrowser.api.runtime_coordinator import RuntimeCoordinator
    from cbrowser.api.v1.runtime_views import make_runtime_response

    config = ProfileConfig(
        name="p1", fingerprint_platform="windows", font_set_id=None
    )
    service = SimpleNamespace(
        get_profile=AsyncMock(return_value=_profile(config)),
        get_runtime=AsyncMock(return_value=_runtime()),
    )
    broadcaster = SimpleNamespace(publish=AsyncMock())
    coordinator = RuntimeCoordinator(
        supervisor_url=None,
        supervisor_token=None,
        profile_service=service,
        event_broadcaster=broadcaster,
    )
    response = await make_runtime_response(_runtime(), coordinator)
    assert response.font_set_id is None
    assert response.missing_fonts == []

    await coordinator.publish_profile_change("p1")
    event_data = broadcaster.publish.call_args.args[0]  # type: ignore[attr-defined]
    assert event_data.font_set_id is None
    assert event_data.missing_fonts == []


# NOTE (t080): _start_browser and the two font-mount tests were removed
# wholesale because they asserted the pre-t080 host bind-mount
# `volumes` dict representation; ADR 029 replaces it with typed
# named-volume subpath `mounts`.  The same scenarios are covered
# under the new representation by tests/unit/test_t080_adapter_mounts.py.
