"""A36: bounded, data-root-independent UDS runtime root."""

from __future__ import annotations

import inspect
import json
import os
import shutil
import stat
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, WebSocket

from cbrowser.runtime_agent import socket_root as sr
from cbrowser.supervisor import path_validator as pv
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator

PROFILE = "prof_a36"
INSTANCE = "inst_a36"

BACKEND_DIR = Path(pv.__file__).resolve().parents[2]


@pytest.fixture
def short_root():
    root = Path(tempfile.mkdtemp(prefix="a36-", dir="/tmp")).resolve()
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _stub_app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "ready": True,
            "display_ready": True,
            "browser_ready": True,
            "audio_ready": True,
            "cdp_ready": True,
            "profile_id": PROFILE,
            "runtime_instance_id": INSTANCE,
            "config_version": 1,
            "details": {"state": "running"},
        }

    @app.post("/control")
    async def control(payload: dict):
        return {
            "status": "ok",
            "action": payload.get("action"),
            "message": "a36",
        }

    @app.websocket("/cdp")
    async def cdp(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                msg = await ws.receive_text()
                await ws.send_text("echo:" + msg)
        except Exception:
            pass

    return app


@contextmanager
def _uds_server(sock: Path):
    sock.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(sock.parent, 0o750)
    config = uvicorn.Config(
        _stub_app(), uds=str(sock), log_level="error", lifespan="off"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not sock.is_socket() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not sock.is_socket():
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("UDS server did not bind")
    try:
        yield server
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.unlink(missing_ok=True)


def _build_core(socket_root: Path) -> SupervisorCore:
    data_root = socket_root / "data"
    validator = PathValidator(data_root, socket_root=socket_root)
    docker = SimpleNamespace(
        validator=validator,
        client=SimpleNamespace(containers=SimpleNamespace(get=lambda name: None)),
    )
    core = SupervisorCore(
        docker_adapter=docker,
        port_allocator=PortAllocator(),
        event_forwarder=MagicMock(spec=EventForwarder),
        api_client=AsyncMock(spec=httpx.AsyncClient),
    )
    core.socket_root = socket_root
    core._sessions[PROFILE] = ActiveSession(
        profile_id=PROFILE,
        runtime_instance_id=INSTANCE,
        config_version=1,
        udp_mux_port=30001,
        browser_container_id="b_a36",
        stream_container_id="s_a36",
        observed_state="running",
    )
    return core


def test_legacy_short_path_adapter_removed() -> None:
    assert not hasattr(pv, "short_unix_socket_path")
    source = Path(pv.__file__).read_text(encoding="utf-8")
    assert "/proc/self/fd" not in source
    assert "os.path.relpath" not in source


def test_no_runtime_double_address_fallback_in_consumers() -> None:
    for name in ("core.py", "control_server.py"):
        source = (BACKEND_DIR / "cbrowser" / "supervisor" / name).read_text(
            encoding="utf-8"
        )
        assert "short_unix_socket_path" not in source
        assert "/proc/self/fd" not in source
        assert "os.path.relpath" not in source


def test_agent_producer_uses_shared_socket_path() -> None:
    source = (
        BACKEND_DIR / "cbrowser" / "runtime_agent" / "agent.py"
    ).read_text(encoding="utf-8")
    assert "agent_socket_path(" in source
    assert 'r_dir / "agent.sock"' not in source


def test_default_root_is_absolute_bounded_and_not_symlink() -> None:
    root = sr.resolve_socket_root({})
    assert root.is_absolute()
    assert not root.is_symlink()
    assert len(os.fsencode(str(root))) < sr.SUN_PATH_BYTE_LIMIT


def test_resolve_socket_root_env_override(short_root: Path) -> None:
    # t055 A12: the root must fit the longest slot path, so the override
    # fixture uses the short root (a pytest tmp_path is too long).
    custom = short_root / "custom_socks"
    root = sr.resolve_socket_root({sr.AGENT_SOCKET_ROOT_ENV: str(custom)})
    assert root == custom


def test_resolve_socket_root_rejects_relative() -> None:
    with pytest.raises(sr.SocketRootError, match="absolute"):
        sr.resolve_socket_root({sr.AGENT_SOCKET_ROOT_ENV: "relative/socks"})


def test_resolve_socket_root_rejects_symlink_root(short_root: Path) -> None:
    target = short_root / "target"
    target.mkdir()
    link = short_root / "link"
    link.symlink_to(target)
    with pytest.raises(sr.SocketRootError, match="symlink"):
        sr.resolve_socket_root({sr.AGENT_SOCKET_ROOT_ENV: str(link)})


def test_slot_is_bounded_and_unique_per_profile_and_instance() -> None:
    a = sr.socket_slot("prof_a", "inst_1")
    b = sr.socket_slot("prof_a", "inst_2")
    c = sr.socket_slot("prof_b", "inst_1")
    assert len(a) == sr.SOCKET_SLOT_LENGTH
    assert a == sr.socket_slot("prof_a", "inst_1")
    assert len({a, b, c}) == 3


def test_slot_rejects_path_traversal_and_bad_identities() -> None:
    for bad in ("../escape", "prof/x", "", "a" * 129, "."):
        with pytest.raises(Exception):
            sr.socket_slot(bad, "inst_1")


def test_longest_legal_identity_path_stays_bounded() -> None:
    longest = "p" * 128
    instance = "i" * 128
    sock = sr.agent_socket_path(sr.DEFAULT_AGENT_SOCKET_ROOT, longest, instance)
    assert len(os.fsencode(str(sock))) <= sr.SUN_PATH_BYTE_LIMIT
    assert len(sr.socket_slot(longest, instance)) == sr.SOCKET_SLOT_LENGTH


def test_socket_path_is_decoupled_from_deep_persistent_data_root(
    tmp_path: Path,
) -> None:
    deep = tmp_path.joinpath(*(["deep_persistent_root_segment"] * 12))
    validator = PathValidator(deep, socket_root=sr.DEFAULT_AGENT_SOCKET_ROOT)
    expected = sr.agent_socket_path(
        sr.DEFAULT_AGENT_SOCKET_ROOT, PROFILE, INSTANCE
    )
    assert validator.get_agent_socket_path(PROFILE, INSTANCE) == expected
    assert str(deep) not in str(expected)
    assert "data_root" not in inspect.signature(sr.agent_socket_path).parameters


def test_validate_socket_deployment_rejects_overlong_root(tmp_path: Path) -> None:
    overlong = tmp_path / ("x" * 200)
    with pytest.raises(sr.SocketRootError, match="sun_path"):
        sr.validate_socket_deployment(overlong, PROFILE, INSTANCE)


def test_prepare_socket_dir_rejects_symlink_slot(short_root: Path) -> None:
    root = short_root / "socks"
    root.mkdir(parents=True)
    slot = sr.agent_socket_dir(root, PROFILE, INSTANCE)
    slot.symlink_to(short_root / "elsewhere")
    with pytest.raises(sr.SocketRootError, match="symlink"):
        sr.prepare_socket_dir(root, PROFILE, INSTANCE)


def test_prepare_socket_dir_enforces_managed_mode(short_root: Path) -> None:
    directory = sr.prepare_socket_dir(short_root / "socks", PROFILE, INSTANCE)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o750


def test_managed_socket_target_rejects_symlink_socket(short_root: Path) -> None:
    root = short_root / "socks"
    directory = sr.prepare_socket_dir(root, PROFILE, INSTANCE)
    (directory / sr.AGENT_SOCKET_NAME).symlink_to(short_root / "victim")
    with pytest.raises(sr.SocketRootError, match="real socket"):
        with sr.managed_socket_target(root, PROFILE, INSTANCE):
            pass


def test_managed_socket_target_rejects_regular_file_socket(
    short_root: Path,
) -> None:
    root = short_root / "socks"
    directory = sr.prepare_socket_dir(root, PROFILE, INSTANCE)
    (directory / sr.AGENT_SOCKET_NAME).write_text("fake", encoding="utf-8")
    with pytest.raises(sr.SocketRootError, match="real socket"):
        with sr.managed_socket_target(root, PROFILE, INSTANCE):
            pass


def test_managed_socket_target_rejects_group_writable_dir(
    short_root: Path,
) -> None:
    root = short_root / "socks"
    directory = sr.prepare_socket_dir(root, PROFILE, INSTANCE)
    os.chmod(directory, 0o770)
    with pytest.raises(sr.SocketRootError, match="writable"):
        with sr.managed_socket_target(root, PROFILE, INSTANCE):
            pass


def test_managed_socket_target_rejects_owner_mismatch(short_root: Path) -> None:
    root = short_root / "socks"
    sr.prepare_socket_dir(root, PROFILE, INSTANCE)
    with pytest.raises(sr.SocketRootError, match="owner"):
        with sr.managed_socket_target(
            root, PROFILE, INSTANCE, managed_uid=os.geteuid() + 1
        ):
            pass


def test_managed_socket_target_detects_directory_replacement(
    short_root: Path, monkeypatch
) -> None:
    root = short_root / "socks"
    directory = sr.prepare_socket_dir(root, PROFILE, INSTANCE)
    real_lstat = os.lstat

    def fake_lstat(path, *args, **kwargs):
        result = real_lstat(path, *args, **kwargs)
        if str(path) == str(directory):
            return SimpleNamespace(st_dev=result.st_dev, st_ino=result.st_ino + 999)
        return result

    monkeypatch.setattr(os, "lstat", fake_lstat)
    with pytest.raises(sr.SocketRootError, match="replaced"):
        with sr.managed_socket_target(root, PROFILE, INSTANCE):
            pass


def test_managed_socket_target_yields_fd_anchored_path(
    short_root: Path, monkeypatch
) -> None:
    root = short_root / "socks"
    sr.prepare_socket_dir(root, PROFILE, INSTANCE)
    monkeypatch.setattr(sr, "_fd_proc_available", lambda dir_fd: True)
    with sr.managed_socket_target(root, PROFILE, INSTANCE) as target:
        assert target.startswith(f"{sr.PROC_SELF_FD}/")
        assert target.endswith(f"/{sr.AGENT_SOCKET_NAME}")
        dir_fd = int(target.removeprefix(sr.PROC_SELF_FD + "/").split("/")[0])
        slot = root / sr.socket_slot(PROFILE, INSTANCE)
        fd_stat = os.fstat(dir_fd)
        assert stat.S_ISDIR(fd_stat.st_mode)
        assert fd_stat.st_ino == slot.stat().st_ino


def test_managed_socket_target_falls_back_to_plain_path_without_proc(
    short_root: Path, monkeypatch
) -> None:
    root = short_root / "socks"
    sr.prepare_socket_dir(root, PROFILE, INSTANCE)
    monkeypatch.setattr(sr, "_fd_proc_available", lambda dir_fd: False)
    with sr.managed_socket_target(root, PROFILE, INSTANCE) as target:
        assert target == str(sr.agent_socket_path(root, PROFILE, INSTANCE))


def test_managed_socket_target_fd_path_resists_directory_replacement(
    short_root: Path, monkeypatch
) -> None:
    root = short_root / "socks"
    directory = sr.prepare_socket_dir(root, PROFILE, INSTANCE)
    monkeypatch.setattr(sr, "_fd_proc_available", lambda dir_fd: True)
    plain = str(sr.agent_socket_path(root, PROFILE, INSTANCE))
    with sr.managed_socket_target(root, PROFILE, INSTANCE) as target:
        assert target.startswith(f"{sr.PROC_SELF_FD}/")
        assert target != plain
        directory.rename(root / "moved")
        directory.mkdir()
        (directory / sr.AGENT_SOCKET_NAME).symlink_to(short_root / "impostor")
        assert target != plain
        assert plain not in target
        dir_fd = int(target.removeprefix(sr.PROC_SELF_FD + "/").split("/")[0])
        assert os.fstat(dir_fd).st_ino == (root / "moved").stat().st_ino
        assert Path(target).resolve() != (
            directory / sr.AGENT_SOCKET_NAME
        ).resolve()


@pytest.mark.asyncio
async def test_real_http_health_and_control_over_new_root_uds(
    short_root: Path,
) -> None:
    socket_root = short_root / "socks"
    sock = sr.agent_socket_path(socket_root, PROFILE, INSTANCE)
    with _uds_server(sock):
        core = _build_core(socket_root)
        health = await core.query_agent_health(PROFILE)
        assert health is not None
        assert health.profile_id == PROFILE
        assert health.runtime_instance_id == INSTANCE
        async with core._agent_uds_client(PROFILE, INSTANCE) as client:
            assert client is not None
            resp = await client.post(
                "/control",
                json={"action": "release_attendant", "params": {}},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_query_agent_health_returns_none_without_socket(
    short_root: Path,
) -> None:
    core = _build_core(short_root / "socks")
    assert await core.query_agent_health(PROFILE) is None


@pytest.mark.asyncio
async def test_no_legacy_data_root_socket_fallback(short_root: Path) -> None:
    socket_root = short_root / "socks"
    core = _build_core(socket_root)
    legacy = core.docker.validator.get_runtime_dir(PROFILE) / "agent.sock"
    with _uds_server(legacy):
        assert await core.query_agent_health(PROFILE) is None


@pytest.mark.asyncio
async def test_browser_container_mounts_shared_socket_root(short_root: Path) -> None:
    from unittest.mock import MagicMock

    from cbrowser.supervisor.docker_adapter import DockerAdapter

    data_root = short_root / "data"
    (data_root / "engine_cache" / "geoip").mkdir(parents=True)
    socket_root = short_root / "socks"
    validator = PathValidator(data_root, socket_root=socket_root)
    image = "sha256:" + "a" * 64
    adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=data_root / "engine_cache",
        docker_client=MagicMock(),
        browser_image=image,
        stream_image=image,
        policy_image=image,
    )
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=data_root / "gate")
    adapter._validate_cache_paths = MagicMock()
    adapter._install_network_policy = MagicMock()
    adapter.remember_profile_number("p1", 1)
    dirs = adapter.prepare_profile_directories("p1")
    (dirs["runtime"] / "snapshot.json").write_text(
        json.dumps({"version": 1, "config": {}}), encoding="utf-8"
    )
    container = MagicMock()
    container.id = "cid"
    adapter.client.containers.run = MagicMock(return_value=container)
    await adapter.start_browser_container(
        profile_id="p1",
        runtime_instance_id="i1",
        snapshot_json_path=dirs["runtime"] / "snapshot.json",
    )
    kwargs = adapter.client.containers.run.call_args.kwargs
    expected_dir = sr.agent_socket_dir(socket_root, "p1", "i1")
    assert kwargs["volumes"][str(expected_dir)] == {
        "bind": str(expected_dir),
        "mode": "rw",
    }
    assert kwargs["environment"][sr.AGENT_SOCKET_ROOT_ENV] == str(socket_root)
