"""Host Profile directories are owned by the runtime UID with least privilege."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathValidator

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


def _adapter(tmp_path: Path, **kwargs) -> DockerAdapter:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=object(),
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
        **kwargs,
    )


def test_managed_directories_are_chowned_to_runtime_uid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path, manage_ownership=True)
    chown_calls: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(
        os,
        "chown",
        lambda path, uid, gid: chown_calls.append((Path(path), uid, gid)),
    )
    dirs = adapter.prepare_profile_directories("p1")

    assert {(path.name, uid, gid) for path, uid, gid in chown_calls} >= {
        ("profile", 1000, 1000),
        ("p1", 1000, 1000),
        ("x11", 1000, 1000),
        ("pulse", 1000, 1000),
    }
    assert stat.S_IMODE(dirs["profile"].stat().st_mode) == 0o750
    assert stat.S_IMODE(dirs["runtime"].stat().st_mode) == 0o750
    assert stat.S_IMODE(dirs["events"].stat().st_mode) == 0o750
    assert stat.S_IMODE(dirs["exchange"].stat().st_mode) == 0o750
    assert stat.S_IMODE(dirs["x11"].stat().st_mode) == 0o750


def test_host_direct_run_skips_chown_and_keeps_exact_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path, manage_ownership=False)
    monkeypatch.setattr(
        os,
        "chown",
        lambda *_args: pytest.fail("host direct run must not chown user files"),
    )
    dirs = adapter.prepare_profile_directories("p1")

    assert stat.S_IMODE(dirs["profile"].stat().st_mode) == 0o750
    assert stat.S_IMODE(dirs["x11"].stat().st_mode) == 0o750
    for name in ("profile", "runtime", "events", "exchange", "uploads", "x11", "pulse"):
        mode = stat.S_IMODE(dirs[name].stat().st_mode)
        assert mode & 0o002 == 0, f"{name} must not be world writable"


def test_cache_permissions_are_never_world_writable(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path, manage_ownership=False)
    binary = adapter.engine_cache / "chromium-test" / "chrome"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"\x7fELF")
    binary.chmod(0o777)
    database = adapter.geoip_cache / "GeoLite2.mmdb"
    database.write_bytes(b"geo")
    database.chmod(0o666)

    adapter._apply_cache_permissions()

    assert stat.S_IMODE(binary.parent.stat().st_mode) == 0o750
    assert stat.S_IMODE(binary.stat().st_mode) == 0o750
    assert stat.S_IMODE(database.stat().st_mode) == 0o640
    for root in (adapter.engine_cache, adapter.geoip_cache):
        for path in [root, *root.rglob("*")]:
            assert stat.S_IMODE(path.stat().st_mode) & 0o002 == 0


def test_managed_ownership_failure_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path, manage_ownership=True)

    def deny(_path, _uid, _gid):
        raise PermissionError("not root")

    monkeypatch.setattr(os, "chown", deny)
    with pytest.raises(Exception, match="ownership"):
        adapter.prepare_profile_directories("p1")


def test_runtime_snapshot_is_private_and_chowned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from cbrowser.domain.models import ConfigVersionSnapshot
    from cbrowser.supervisor.core import SupervisorCore
    from cbrowser.supervisor.port_allocator import PortAllocator

    core = SupervisorCore(
        SimpleNamespace(
            validator=PathValidator(tmp_path),
            manage_ownership=True,
            runtime_uid=1000,
            runtime_gid=1000,
        ),
        PortAllocator(),
        None,
        None,
    )
    chown_calls: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(
        os,
        "chown",
        lambda path, uid, gid: chown_calls.append((Path(path), uid, gid)),
    )
    snapshot = ConfigVersionSnapshot(
        id="snap_test",
        profile_id="p1",
        version=1,
        config={"proxy": "secret"},
        created_at="2026-11-03T00:00:00+00:00",
    )
    path = tmp_path / "snapshot.json"

    core._write_runtime_snapshot(path, snapshot)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert chown_calls == [(path, 1000, 1000)]


def test_cache_ownership_failure_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path, manage_ownership=True)
    binary = adapter.engine_cache / "chromium-test" / "chrome"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"\x7fELF")

    def deny(_path, _uid, _gid, **_kwargs):
        raise PermissionError("not root")

    monkeypatch.setattr(os, "chown", deny)
    with pytest.raises(Exception, match="cache ownership"):
        adapter._apply_cache_permissions()


def _make_start_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    manage_ownership: bool,
    font_set_id: str | None = None,
):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import httpx
    from cbrowser.domain.models import ProfileConfig
    from cbrowser.supervisor.core import SupervisorCore
    from cbrowser.supervisor.port_allocator import PortAllocator

    root = tmp_path / "data"
    validator = PathValidator(root)
    (root / "profiles" / "p1" / "profile").mkdir(parents=True)
    (root / "runtime" / "p1").mkdir(parents=True)
    (root / "runtime-events" / "p1").mkdir(parents=True)
    (root / "exchange" / "p1").mkdir(parents=True)
    (root / "uploads" / "p1").mkdir(parents=True)
    (root / "profiles" / "p1" / "preview").mkdir(parents=True)
    (root / "runtime" / "p1" / "x11").mkdir(parents=True)
    (root / "runtime" / "p1" / "pulse").mkdir(parents=True)

    dirs = {
        "profile": root / "profiles" / "p1" / "profile",
        "runtime": root / "runtime" / "p1",
        "events": root / "runtime-events" / "p1",
        "exchange": root / "exchange" / "p1",
        "uploads": root / "uploads" / "p1",
        "x11": root / "runtime" / "p1" / "x11",
        "pulse": root / "runtime" / "p1" / "pulse",
        "preview": root / "profiles" / "p1" / "preview",
    }

    async def start_browser_container(**_kwargs):
        return SimpleNamespace(id="browser-cid", name="cbrowser-0001-browser")

    async def start_stream_container(**_kwargs):
        s = SimpleNamespace(id="stream-cid", status="running")
        s.reload = lambda: None
        return s

    docker = SimpleNamespace(
        validator=validator,
        manage_ownership=manage_ownership,
        runtime_uid=1000,
        runtime_gid=1000,
        remember_profile_number=lambda *_a: None,
        prepare_profile_directories=lambda _pid: dirs,
        create_profile_network=AsyncMock(),
        attach_profile_infrastructure=lambda *_a, **_kw: {"gateway_ip": "10.0.0.1", "gateway_url": "ws://gateway:18080"},
        start_browser_container=start_browser_container,
        start_stream_container=start_stream_container,
        get_profile_containers=lambda _pid: {"browser": SimpleNamespace(name="cbrowser-0001-browser")},
        get_stream_container_name=lambda _pid: "cbrowser-0001-stream",
        rebuild_media_network=lambda _pid: None,
        cleanup_container_by_name=lambda _name: None,
    )

    def api_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/state/snapshot"):
            return httpx.Response(
                200,
                json={
                    "api_epoch": "perm-test-epoch",
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
        if request.url.path.endswith("/runtime"):
            return httpx.Response(
                200,
                json={"desired_state": "running", "restart_blocked": False},
            )
        return httpx.Response(200, json={})

    api = httpx.AsyncClient(transport=httpx.MockTransport(api_handler), base_url="http://api")
    gateway_control = SimpleNamespace(has_foreground_viewers=AsyncMock(return_value=False))
    key_file = tmp_path / "agent_key"
    key_file.write_text("agent-master-key-" + "x" * 32, encoding="utf-8")
    key_file.chmod(0o600)

    core = SupervisorCore(
        docker,
        PortAllocator(),
        None,
        api,
        agent_key_file=key_file,
        gateway_control=gateway_control,
    )
    core._resolve_gateway_id = lambda: "gw-1"  # type: ignore[method-assign]

    @asynccontextmanager
    async def _no_op_lock(_pid: str):
        yield

    core._profile_locks.lock_for = lambda _pid: _no_op_lock(_pid)  # type: ignore[method-assign]
    monkeypatch.setattr(
        "cbrowser.supervisor.core.browser_runtime_ready",
        lambda *_a, **_kw: True,
    )
    return core, api, validator, ProfileConfig(font_set_id=font_set_id)


@pytest.mark.asyncio
async def test_stream_secrets_are_chowned_on_start_and_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixture_font_set: str
) -> None:
    chown_calls: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(
        os,
        "chown",
        lambda path, uid, gid: chown_calls.append((Path(path), uid, gid)),
    )
    core, api, validator, cfg = _make_start_core(
        tmp_path,
        monkeypatch,
        manage_ownership=True,
        font_set_id=fixture_font_set,
    )
    try:
        session = await core.start_profile("p1", cfg, 1, profile_number=1)
        secret_dir = validator.get_secret_dir("p1")
        agent_secret = secret_dir / "agent_secret.txt"
        selkies_file = secret_dir / f"selkies_tokens_{session.runtime_instance_id}.json"

        assert stat.S_IMODE(secret_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(agent_secret.stat().st_mode) == 0o600
        assert stat.S_IMODE(selkies_file.stat().st_mode) == 0o600
        chowned = {(path, uid, gid) for path, uid, gid in chown_calls}
        assert (secret_dir, 1000, 1000) in chowned
        assert (agent_secret, 1000, 1000) in chowned
        assert (selkies_file, 1000, 1000) in chowned

        chown_calls.clear()
        selkies_file.unlink()
        replaced = await core._replace_stream_only("p1", session, rebuild_network=False)
        assert replaced is True
        chowned_replace = {(path, uid, gid) for path, uid, gid in chown_calls}
        assert (secret_dir, 1000, 1000) in chowned_replace
        assert (agent_secret, 1000, 1000) in chowned_replace
        assert (selkies_file, 1000, 1000) in chowned_replace
    finally:
        await api.aclose()


def test_browser_proxy_credentials_are_private_and_chowned_when_managed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from cbrowser.supervisor.core import SupervisorCore

    chown_calls: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(
        os,
        "chown",
        lambda path, uid, gid: chown_calls.append((Path(path), uid, gid)),
    )
    core = SupervisorCore.__new__(SupervisorCore)
    core.docker = SimpleNamespace(
        manage_ownership=True, runtime_uid=1000, runtime_gid=1000
    )
    target = tmp_path / "proxy_credentials.json"
    core._write_proxy_credentials(
        target,
        {
            "scheme": "http",
            "host": "proxy.example.com",
            "port": 8080,
            "username": "user",
            "password": "pw",
            "credential_revision": 1,
        },
    )
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert (target, 1000, 1000) in chown_calls


def test_prepare_profile_directories_chowns_intermediate_profile_and_artifact_parents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path, manage_ownership=True)
    chown_calls: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(
        os,
        "chown",
        lambda path, uid, gid: chown_calls.append((Path(path), uid, gid)),
    )
    dirs = adapter.prepare_profile_directories("p1")
    chowned = {(path, uid, gid) for path, uid, gid in chown_calls}
    # API runs as uid/gid 1000 and runs shutil.rmtree on profiles/<id> and
    # artifacts/<id> during Profile deletion; both parents must be 1000:1000.
    assert (dirs["profile"].parent, 1000, 1000) in chowned
    assert (dirs["exchange"].parent, 1000, 1000) in chowned


def test_archive_event_file_chowns_archive_directories_when_managed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace
    from cbrowser.supervisor.core import SupervisorCore
    from cbrowser.supervisor.port_allocator import PortAllocator

    root = tmp_path / "data"
    validator = PathValidator(root)
    core = SupervisorCore(
        SimpleNamespace(
            validator=validator,
            manage_ownership=True,
            runtime_uid=1000,
            runtime_gid=1000,
        ),
        PortAllocator(),
        None,
        None,
    )
    event_file = root / "runtime-events" / "p1" / "events" / "runtime" / "inst1" / "001.json"
    event_file.parent.mkdir(parents=True)
    event_file.write_text('{"event_type":"exit"}', encoding="utf-8")

    chown_calls: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(
        os,
        "chown",
        lambda path, uid, gid: chown_calls.append((Path(path), uid, gid)),
    )
    core._archive_event_file(event_file, "p1", "inst1")
    archive_inst = root / "runtime-events" / "p1" / "archive" / "inst1"
    chowned = {(path, uid, gid) for path, uid, gid in chown_calls}
    assert (archive_inst.parent, 1000, 1000) in chowned
    assert (archive_inst, 1000, 1000) in chowned
