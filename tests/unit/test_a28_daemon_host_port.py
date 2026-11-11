"""A28: Docker daemon allocates the gateway topology host port.

Supersedes t045's ``test_shared_harness_ports_are_os_assigned``: that test
asserted the harness reserved a port with ``socket.bind(('127.0.0.1', 0))``
plus a process-global set, which cannot protect a Docker publish from a
different xdist worker or an external process.  It is removed rather than
edited in place because its premise (OS-level port reservation is the fix)
is exactly what A28 replaces with daemon-side allocation plus read-back.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.fixtures.gateway_probe import topology

IMAGE_VARS = (
    "CBROWSER_RUNTIME_TEST_IMAGE",
    "CBROWSER_STREAM_TEST_IMAGE",
    "CBROWSER_GATEWAY_IMAGE",
    "CBROWSER_SUPERVISOR_TEST_IMAGE",
    "CBROWSER_API_TEST_IMAGE",
    "CBROWSER_CADDY_TEST_IMAGE",
)

HARNESS_PATH = Path(topology.__file__)


class _FakeNetwork:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeNetworks:
    def create(self, name: str, labels=None):
        return _FakeNetwork(name)


class _FakeContainer:
    def __init__(self, name: str, attrs: dict) -> None:
        self.name = name
        self.id = f"id-{name}"
        self.status = "running"
        self.attrs = attrs

    def reload(self) -> None:
        return None

    def logs(self) -> bytes:
        return b""


class _FakeContainers:
    def __init__(
        self, caddy_port: int, records: list, fail_role: str | None
    ) -> None:
        self.caddy_port = caddy_port
        self.records = records
        self.fail_role = fail_role

    def run(
        self,
        image,
        name=None,
        detach=True,
        network=None,
        labels=None,
        ports=None,
        **kwargs,
    ):
        role = (labels or {}).get("com.cbrowser.role", "")
        if self.fail_role and role == self.fail_role:
            raise RuntimeError("simulated container start failure")
        bindings: dict[str, list[dict[str, str]]] = {}
        for container_port in (ports or {}):
            host_port = (
                self.caddy_port
                if container_port == "443/tcp"
                else 50000 + len(self.records)
            )
            bindings[container_port] = [
                {"HostIp": "127.0.0.1", "HostPort": str(host_port)}
            ]
        attrs = {
            "NetworkSettings": {
                "Networks": {network: {"IPAddress": "172.30.0.2"}},
                "Ports": bindings,
            }
        }
        container = _FakeContainer(name, attrs)
        self.records.append(
            {
                "name": name,
                "role": role,
                "ports": ports,
                "environment": kwargs.get("environment"),
                "volumes": kwargs.get("volumes"),
            }
        )
        return container


class _FakeClient:
    def __init__(self, caddy_port: int, records: list, fail_role=None) -> None:
        self.containers = _FakeContainers(caddy_port, records, fail_role)
        self.networks = _FakeNetworks()


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caddy_port: int,
    records: list,
    fail_role: str | None = None,
):
    for var in IMAGE_VARS:
        monkeypatch.setenv(var, "sha256:" + "a" * 64)
    engine = tmp_path / "engine"
    geoip = tmp_path / "geoip"
    engine.mkdir()
    geoip.mkdir()
    monkeypatch.setenv("CBROWSER_RUNTIME_ENGINE_CACHE", str(engine))
    monkeypatch.setenv("CBROWSER_RUNTIME_GEOIP_CACHE", str(geoip))
    client = _FakeClient(caddy_port, records, fail_role)
    monkeypatch.setattr(topology.docker, "from_env", lambda: client)
    monkeypatch.setattr(
        topology, "prepare_selkies_web_assets", lambda *a, **k: None
    )

    async def _ready(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(topology, "wait_until_ready", _ready)
    cleaned: list[str] = []
    monkeypatch.setattr(
        topology,
        "cleanup_prefixed_resources",
        lambda client, prefix: cleaned.append(prefix),
    )
    harness = topology.GatewayTopologyHarness(tmp_path / "work")
    return harness, cleaned


def _caddy_record(records: list) -> dict:
    return next(r for r in records if r["role"] == "caddy")


def _api_record(records: list) -> dict:
    return next(r for r in records if r["role"] == "api")


def _gateway_record(records: list) -> dict:
    return next(r for r in records if r["role"] == "gateway")


def test_harness_has_no_host_port_scanning() -> None:
    source = HARNESS_PATH.read_text(encoding="utf-8")
    assert "def find_free_port" not in source
    assert "_allocated_host_ports" not in source
    assert "_host_port_lock" not in source
    assert 'bind(("127.0.0.1", 0))' not in source
    assert "import socket" not in source
    assert "import threading" not in source


def test_published_host_port_reads_docker_binding() -> None:
    container = _FakeContainer(
        "caddy",
        {
            "NetworkSettings": {
                "Ports": {
                    "443/tcp": [
                        {"HostIp": "127.0.0.1", "HostPort": "41234"}
                    ]
                }
            }
        },
    )
    assert topology.published_host_port(container, "443/tcp") == 41234


def test_published_host_port_missing_raises() -> None:
    container = _FakeContainer(
        "caddy", {"NetworkSettings": {"Ports": {"443/tcp": []}}}
    )
    with pytest.raises(RuntimeError):
        topology.published_host_port(container, "443/tcp")


def test_daemon_port_propagates_to_origin_env_and_deploy_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # t054: the daemon-assigned port reaches API + Gateway as the deploy
    # port env var; there is no applied-network-state file anymore.
    records: list = []
    harness, _ = _make_harness(monkeypatch, tmp_path, 41234, records)
    asyncio.run(harness._do_start())

    assert _caddy_record(records)["ports"] == {
        "443/tcp": ("127.0.0.1", None)
    }
    assert harness.caddy_host_port == 41234
    assert harness.origin == "https://127.0.0.1:41234"
    assert _api_record(records)["environment"]["CBROWSER_HTTPS_PORT"] == "41234"
    assert (
        _gateway_record(records)["environment"]["CBROWSER_HTTPS_PORT"]
        == "41234"
    )


def test_concurrent_harnesses_get_distinct_daemon_ports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first_records: list = []
    second_records: list = []
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first, _ = _make_harness(
        monkeypatch, tmp_path / "a", 41001, first_records
    )
    asyncio.run(first._do_start())
    second, _ = _make_harness(
        monkeypatch, tmp_path / "b", 41002, second_records
    )
    asyncio.run(second._do_start())

    assert first.origin == "https://127.0.0.1:41001"
    assert second.origin == "https://127.0.0.1:41002"
    assert first.caddy_host_port != second.caddy_host_port


def test_start_failure_cleans_up_this_round(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    records: list = []
    harness, cleaned = _make_harness(
        monkeypatch, tmp_path, 41234, records, fail_role="supervisor"
    )
    with pytest.raises(RuntimeError):
        asyncio.run(harness.start())

    assert cleaned == [harness.prefix]
    assert any(r["role"] == "caddy" for r in records)
