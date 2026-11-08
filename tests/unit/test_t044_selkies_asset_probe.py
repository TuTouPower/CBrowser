"""t044: Docker SDK boundary behaviour of stream-image asset discovery."""

from __future__ import annotations

import importlib.util
import io
import sys
import tarfile
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "vendor_selkies_web.py"

_spec = importlib.util.spec_from_file_location("t044_vendor_selkies_web", MODULE_PATH)
assert _spec is not None and _spec.loader is not None
_vendor = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _vendor
_spec.loader.exec_module(_vendor)
extract_from_stream_image = _vendor.extract_from_stream_image

DISCOVERED_PATH = "/opt/venv/lib/python3.15/site-packages/selkies/selkies_web"
PAYLOAD = b"<html>official</html>"


class FakeContainer:
    def __init__(
        self,
        *,
        exec_output: bytes = b"",
        exit_code: int = 0,
        archive_bytes: bytes = b"",
        get_archive_error: BaseException | None = None,
    ) -> None:
        self._exec_output = exec_output
        self._exit_code = exit_code
        self._archive_bytes = archive_bytes
        self._get_archive_error = get_archive_error
        self.start_calls = 0
        self.exec_run_calls: list[list[str]] = []
        self.get_archive_calls: list[str] = []
        self.remove_calls: list[dict] = []

    def start(self) -> None:
        self.start_calls += 1

    def exec_run(self, cmd: list[str]):
        self.exec_run_calls.append(cmd)
        return types.SimpleNamespace(output=self._exec_output, exit_code=self._exit_code)

    def get_archive(self, path: str):
        self.get_archive_calls.append(path)
        if self._get_archive_error is not None:
            raise self._get_archive_error
        return (iter([self._archive_bytes]), {})

    def remove(self, **kwargs) -> None:
        self.remove_calls.append(kwargs)


class FakeContainers:
    def __init__(self, container: FakeContainer) -> None:
        self._container = container
        self.create_calls: list[tuple[str, dict]] = []

    def create(self, image_id: str, **kwargs):
        self.create_calls.append((image_id, kwargs))
        return self._container


class FakeClient:
    def __init__(self, container: FakeContainer) -> None:
        self.containers = FakeContainers(container)


def _tar_with_index(payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        info = tarfile.TarInfo("selkies_web/index.html")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _make_client(
    *,
    exec_output: bytes = (DISCOVERED_PATH + "\n").encode(),
    exit_code: int = 0,
    archive_bytes: bytes | None = None,
    get_archive_error: BaseException | None = None,
) -> tuple[FakeClient, FakeContainer]:
    if archive_bytes is None:
        archive_bytes = _tar_with_index(PAYLOAD)
    container = FakeContainer(
        exec_output=exec_output,
        exit_code=exit_code,
        archive_bytes=archive_bytes,
        get_archive_error=get_archive_error,
    )
    return FakeClient(container), container


def _unexpected_from_env():
    raise AssertionError("docker.from_env must not run when client_factory is injected")


@pytest.fixture(autouse=True)
def _stub_docker_module(monkeypatch):
    stub = types.ModuleType("docker")
    stub.from_env = _unexpected_from_env
    monkeypatch.setitem(sys.modules, "docker", stub)
    return stub


def test_find_locates_path_and_get_archive_uses_discovered_path(tmp_path):
    client, container = _make_client()
    extract_from_stream_image("stream:test", tmp_path, client_factory=lambda: client)

    assert container.start_calls == 1
    assert len(container.exec_run_calls) == 1
    cmd = container.exec_run_calls[0]
    assert cmd[0] == "find"
    assert "/opt/venv" in cmd
    assert "/usr/local/lib" in cmd
    assert "-name" in cmd and "selkies_web" in cmd
    assert container.get_archive_calls == [DISCOVERED_PATH]
    image_id, kwargs = client.containers.create_calls[0]
    assert image_id == "stream:test"
    assert kwargs["entrypoint"] == ["/bin/sh"]
    assert kwargs["command"] == ["-c", "sleep 60"]


def test_archive_bytes_are_written_to_dest_dir(tmp_path):
    client, container = _make_client()
    extract_from_stream_image("stream:test", tmp_path, client_factory=lambda: client)

    assert container.get_archive_calls == [DISCOVERED_PATH]
    assert (tmp_path / "index.html").read_bytes() == PAYLOAD
    assert container.remove_calls == [{"force": True}]


def test_container_is_force_removed_when_exec_run_fails(tmp_path):
    client, container = _make_client(exec_output=b"", exit_code=1)
    with pytest.raises(FileNotFoundError):
        extract_from_stream_image("stream:test", tmp_path, client_factory=lambda: client)

    assert container.get_archive_calls == []
    assert container.remove_calls == [{"force": True}]


def test_container_is_force_removed_when_get_archive_raises(tmp_path):
    client, container = _make_client(get_archive_error=RuntimeError("archive boom"))
    with pytest.raises(RuntimeError, match="archive boom"):
        extract_from_stream_image("stream:test", tmp_path, client_factory=lambda: client)

    assert container.get_archive_calls == [DISCOVERED_PATH]
    assert container.remove_calls == [{"force": True}]


def test_default_factory_still_calls_docker_from_env(monkeypatch, tmp_path):
    client, container = _make_client()
    calls: list[str] = []

    def from_env():
        calls.append("from_env")
        return client

    monkeypatch.setattr(sys.modules["docker"], "from_env", from_env)
    extract_from_stream_image("stream:test", tmp_path)

    assert calls == ["from_env"]
    assert container.get_archive_calls == [DISCOVERED_PATH]
    assert (tmp_path / "index.html").read_bytes() == PAYLOAD
    assert container.remove_calls == [{"force": True}]
