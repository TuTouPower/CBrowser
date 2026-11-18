"""t075: supervisor font mount construction and binding enforcement.

- The Browser font mount is built at the volume_spec boundary from
  the MountPlanner's configured fonts root, targets the fixed
  container path, and is read-only.
- A bound set missing under the fonts root fails closed at mount
  construction (a volume subpath mount would otherwise be created
  empty by the daemon — the p125 zero-font start).
- SupervisorCore refuses to start a profile with no binding at all;
  the abolished "platform fonts not configured" start path is gone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cbrowser.supervisor.path_validator import PathSecurityError
from cbrowser.supervisor.storage_layout import MountPlanner
from cbrowser.supervisor.volume_spec import font_set_mount

SET_ID = "a" * 64


def _planner(tmp_path: Path, fonts_root: Path) -> MountPlanner:
    return MountPlanner(
        resource_prefix="cbrowser-test",
        data_root=tmp_path / "data",
        socket_root=tmp_path / "sockets",
        fonts_root=fonts_root,
    )


def test_font_set_mount_is_exact_read_only_volume_subpath(tmp_path: Path) -> None:
    fonts_root = tmp_path / "fonts"
    (fonts_root / "windows" / SET_ID).mkdir(parents=True)
    mount = font_set_mount(
        planner=_planner(tmp_path, fonts_root),
        platform="windows",
        font_set_id=SET_ID,
    )
    assert mount["Target"] == f"/run/cbrowser/fonts/windows/{SET_ID}"
    assert mount["Type"] == "volume"
    assert mount["ReadOnly"] is True
    assert mount["VolumeOptions"]["Subpath"] == f"windows/{SET_ID}"


def test_font_set_mount_missing_source_fails_closed(tmp_path: Path) -> None:
    fonts_root = tmp_path / "fonts"
    fonts_root.mkdir()
    with pytest.raises(PathSecurityError):
        font_set_mount(
            planner=_planner(tmp_path, fonts_root),
            platform="windows",
            font_set_id=SET_ID,
        )


def test_font_set_mount_rejects_malformed_identity(tmp_path: Path) -> None:
    fonts_root = tmp_path / "fonts"
    (fonts_root / "windows").mkdir(parents=True)
    planner = _planner(tmp_path, fonts_root)
    with pytest.raises(PathSecurityError):
        font_set_mount(planner=planner, platform="linux", font_set_id=SET_ID)
    with pytest.raises(PathSecurityError):
        font_set_mount(planner=planner, platform="windows", font_set_id="../escape")
    with pytest.raises(PathSecurityError):
        font_set_mount(planner=planner, platform="windows", font_set_id="xyz")


@pytest.mark.asyncio
async def test_core_refuses_unbound_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """start_profile with font_set_id=None must raise before any
    container work (mirrors the t041 light-core harness)."""
    import httpx
    from unittest.mock import AsyncMock
    from types import SimpleNamespace

    from cbrowser.domain.models import ProfileConfig
    from cbrowser.supervisor.core import (
        FONT_SET_UNAVAILABLE,
        FontSetUnavailableError,
        SupervisorCore,
    )
    from cbrowser.supervisor.path_validator import PathValidator
    from cbrowser.supervisor.port_allocator import PortAllocator

    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(tmp_path / "fonts"))
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
    key_file = tmp_path / "agent.key"
    key_file.write_text("k" * 32, encoding="utf-8")
    key_file.chmod(0o600)
    def _handler(request):
        # t083: start intent is read through the minimal batch
        # snapshot — serve it so the state gate passes and the test
        # reaches the font check (mirrors t041's _running_handler).
        if request.url.path.endswith("/state/snapshot"):
            return httpx.Response(
                200,
                json={
                    "api_epoch": "t075-test-epoch",
                    "profiles": [
                        {
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
                    ],
                    "next_cursor": None,
                },
            )
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "desired_state": "running",
                "restart_blocked": False,
            },
        )

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api"
    ) as api:
        core = SupervisorCore(
            docker_adapter=adapter,
            port_allocator=PortAllocator(30000, 30010),
            event_forwarder=events,
            api_client=api,
            token_file=None,
            agent_key_file=key_file,
        )
        core.report_terminal_observation = AsyncMock(return_value=True)  # type: ignore[method-assign]
        with pytest.raises(FontSetUnavailableError) as exc:
            await core.start_profile(
                "p1",
                ProfileConfig(name="p1", fingerprint_platform="windows"),
            )
        assert str(exc.value) == FONT_SET_UNAVAILABLE
    adapter.start_browser_container.assert_not_awaited()
