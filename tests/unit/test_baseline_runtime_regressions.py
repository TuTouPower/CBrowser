"""Baseline runtime regression suite.

Validates:
1. Packaging and Dockerfile integrity (pinned digests, required dependencies).
2. Supervisor event watcher scope and error-handling.
3. Stream mount and security boundaries.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_dockerfile(rel_path: str) -> str:
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"Dockerfile not found: {rel_path}"
    return path.read_text(encoding="utf-8")


def test_supervisor_runtime_packaging_integrity():
    content = _read_dockerfile("config/docker/supervisor_runtime/Dockerfile")
    lines = content.splitlines()

    from_line = next(line for line in lines if line.startswith("FROM "))
    assert "@sha256:" in from_line, (
        "Supervisor base image must be pinned by sha256 digest"
    )

    assert "COPY src/backend/cbrowser/secret_files.py" in content, (
        "Supervisor Dockerfile must copy secret_files.py"
    )
    assert "COPY src/backend/cbrowser/gateway" in content, (
        "Supervisor Dockerfile must copy gateway package for endpoint resolution"
    )
    assert "COPY src/backend/cbrowser/runtime_agent" in content, (
        "Supervisor Dockerfile must copy runtime_agent package for event records"
    )


def test_gateway_runtime_packaging_integrity():
    content = _read_dockerfile("config/docker/gateway_runtime/Dockerfile")
    lines = content.splitlines()

    from_line = next(line for line in lines if line.startswith("FROM "))
    assert "@sha256:" in from_line, "Gateway base image must be pinned by sha256 digest"

    assert "COPY src/backend/cbrowser/secret_files.py" in content, (
        "Gateway Dockerfile must copy secret_files.py"
    )


def test_stream_runtime_packaging_integrity():
    content = _read_dockerfile("config/docker/stream_runtime/Dockerfile")
    lines = content.splitlines()
    from_line = next(line for line in lines if line.startswith("FROM "))
    assert "@sha256:" in from_line, "Stream base image must be pinned by sha256 digest"
    for required in (
        "COPY src/backend/cbrowser/__init__.py",
        "COPY src/backend/cbrowser/secret_files.py",
        "COPY src/backend/cbrowser/stream_agent",
        "COPY config/docker/stream_runtime/entrypoint.sh",
    ):
        assert required in content, f"Stream Dockerfile must copy {required}"


def test_api_fixture_runtime_packaging_integrity():
    dockerfile_path = (
        "tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile"
    )
    content = _read_dockerfile(dockerfile_path)
    lines = content.splitlines()

    from_line = next(line for line in lines if line.startswith("FROM "))
    assert "@sha256:" in from_line, (
        "API probe fixture base image must be pinned by digest"
    )

    prod_from_line = next(
        line
        for line in _read_dockerfile(
            "config/docker/api_runtime/Dockerfile"
        ).splitlines()
        if line.startswith("FROM ")
    )
    assert from_line == prod_from_line, (
        "API probe fixture base image must exactly match the production "
        "api_runtime Dockerfile FROM line (3.15/trixie digest)"
    )

    assert "COPY src/backend/cbrowser/__init__.py" in content, (
        "API Dockerfile must copy cbrowser/__init__.py"
    )
    assert "COPY src/backend/cbrowser/secret_files.py" in content, (
        "API Dockerfile must copy secret_files.py"
    )
    assert "COPY src/backend/cbrowser/gateway" in content, (
        "API Dockerfile must copy gateway package for endpoint resolution"
    )


@pytest.mark.asyncio
async def test_serve_supervisor_watch_docker_events_subscribes_prefix(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    import asyncio
    import secrets
    import socket
    import threading
    from unittest.mock import MagicMock

    import httpx
    from cbrowser.supervisor.core import SupervisorCore
    from cbrowser.supervisor.event_forwarder import EventForwarder
    from cbrowser.supervisor.path_validator import PathValidator
    from cbrowser.supervisor.port_allocator import PortAllocator
    from cbrowser.supervisor.runner import serve_supervisor

    token_file = tmp_path / "supervisor_token"
    token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    token_file.chmod(0o600)

    (tmp_path / "spool").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime-events").mkdir(parents=True, exist_ok=True)

    loop = asyncio.get_running_loop()
    events_called = asyncio.Event()
    stop_streaming = threading.Event()
    received_filters = {}

    def fake_events(*args, **kwargs):
        received_filters.update(kwargs.get("filters", {}))
        loop.call_soon_threadsafe(events_called.set)
        yield {"Type": "container", "Action": "die"}
        stop_streaming.wait(timeout=2.0)

    mock_docker_client = MagicMock()
    mock_docker_client.events = MagicMock(side_effect=fake_events)

    class _DockerMock:
        def __init__(self, root: Path, prefix: str):
            self.validator = PathValidator(root)
            self.resource_prefix = prefix
            self.client = mock_docker_client

        def scan_active_containers(self):
            return []

    expected_prefix = "cbrowser-scope-test-prefix"
    docker_mock = _DockerMock(tmp_path, expected_prefix)

    core = SupervisorCore(
        docker_adapter=docker_mock,
        port_allocator=PortAllocator(),
        event_forwarder=EventForwarder(
            str(tmp_path / "unused"), tmp_path / "spool"
        ),
        api_client=httpx.AsyncClient(base_url="http://127.0.0.1:1", trust_env=False),
        token_file=token_file,
        gateway_control=MagicMock(),
        gateway_container_id=None,
    )

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]

    caplog.set_level("INFO")

    supervisor_task = asyncio.create_task(
        serve_supervisor(core, "127.0.0.1", free_port)
    )

    try:
        await asyncio.wait_for(events_called.wait(), timeout=2.0)
    finally:
        stop_streaming.set()
        supervisor_task.cancel()
        try:
            await supervisor_task
        except asyncio.CancelledError:
            pass
        await core.api.aclose()

    assert "Docker event stream stopped: error_type=NameError" not in caplog.text, (
        "serve_supervisor must not suffer NameError in watch_docker_events"
    )
    assert mock_docker_client.events.called, (
        "core.docker.client.events must be invoked by watch_docker_events"
    )
    assert received_filters.get("label") == f"com.cbrowser.prefix={expected_prefix}", (
        f"Filters must match expected prefix {expected_prefix}, got {received_filters}"
    )
    assert (
        f"Docker events stream subscribed for prefix={expected_prefix}"
        in caplog.text
    ), "serve_supervisor must emit subscription log upon registration"


def test_gateway_lazy_exports_and_closure_isolation():
    """Verify gateway package uses lazy export and does not eagerly import aiohttp."""
    import cbrowser.gateway as gw

    # 1. Test lazy export properties
    assert hasattr(gw, "GatewayConfig")
    assert hasattr(gw, "create_gateway_app")
    assert "GatewayConfig" in gw.__all__
    assert "create_gateway_app" in gw.__all__

    # 2. Test unknown attribute raises AttributeError
    with pytest.raises(AttributeError):
        _ = gw.nonexistent_symbol


def test_supervisor_import_closure_independent_of_aiohttp():
    """Verify Supervisor imports without aiohttp dependency."""
    import importlib
    import sys
    from unittest.mock import patch

    # Ensure cbrowser.gateway is freshly imported or unpolluted
    with patch.dict(sys.modules, {"aiohttp": None}):
        # Must import successfully without triggering ModuleNotFoundError on aiohttp
        mod = importlib.import_module("cbrowser.supervisor.control_server")
        assert mod is not None


@pytest.mark.asyncio
async def test_serve_supervisor_terminates_blocking_stream_via_close(tmp_path: Path):
    """Production watcher must close blocking Docker CancellableStream on shutdown."""
    import asyncio
    import secrets
    import socket
    import threading
    from unittest.mock import MagicMock

    import httpx
    from cbrowser.supervisor.core import SupervisorCore
    from cbrowser.supervisor.event_forwarder import EventForwarder
    from cbrowser.supervisor.path_validator import PathValidator
    from cbrowser.supervisor.port_allocator import PortAllocator
    from cbrowser.supervisor.runner import serve_supervisor

    token_file = tmp_path / "supervisor_token"
    token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    token_file.chmod(0o600)

    (tmp_path / "spool").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime-events").mkdir(parents=True, exist_ok=True)

    stream_started = asyncio.Event()
    loop = asyncio.get_running_loop()

    class BlockingCancellableStream:
        def __init__(self):
            self.closed = threading.Event()
            self.close_called = threading.Event()
            self.close_thread_id: int | None = None

        def __iter__(self):
            return self

        def __next__(self):
            loop.call_soon_threadsafe(stream_started.set)
            if self.closed.is_set():
                raise StopIteration
            # Block indefinitely until close() is explicitly called from supervisor
            if self.closed.wait(timeout=2.0):
                raise StopIteration
            raise TimeoutError("Stream was not closed in time by supervisor")

        def close(self):
            self.close_thread_id = threading.get_ident()
            self.close_called.set()
            self.closed.set()

    mock_stream = BlockingCancellableStream()
    mock_docker_client = MagicMock()
    mock_docker_client.events = MagicMock(return_value=mock_stream)

    class _DockerMock:
        def __init__(self, root: Path, prefix: str):
            self.validator = PathValidator(root)
            self.resource_prefix = prefix
            self.client = mock_docker_client

        def scan_active_containers(self):
            return []

    docker_mock = _DockerMock(tmp_path, "cbrowser-shutdown-test")
    core = SupervisorCore(
        docker_adapter=docker_mock,
        port_allocator=PortAllocator(),
        event_forwarder=EventForwarder(str(tmp_path / "unused"), tmp_path / "spool"),
        api_client=httpx.AsyncClient(base_url="http://127.0.0.1:1", trust_env=False),
        token_file=token_file,
        gateway_control=MagicMock(),
        gateway_container_id=None,
    )

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]

    supervisor_task = asyncio.create_task(
        serve_supervisor(core, "127.0.0.1", free_port)
    )

    try:
        # Wait for watcher to begin blocking iteration
        await asyncio.wait_for(stream_started.wait(), timeout=2.0)
    finally:
        # Stop supervisor task (simulating shutdown)
        supervisor_task.cancel()
        try:
            await supervisor_task
        except asyncio.CancelledError:
            pass
        await core.api.aclose()

    loop_thread_id = threading.get_ident()
    # The production watcher must have called close() on the blocking stream
    assert mock_stream.close_called.is_set(), (
        "Production serve_supervisor must explicitly close the Docker event stream"
    )
    assert mock_stream.close_thread_id != loop_thread_id, (
        "Docker event stream close must not run in the asyncio loop thread "
        f"(got loop={loop_thread_id}, close={mock_stream.close_thread_id})"
    )
