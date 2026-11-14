"""t052: Supervisor egress probe — Docker helper, loopback mapping, policy.

The real DockerAdapter runs against a purpose-built fake Docker client
that models containers.run / exec_run / wait / remove and networks, so
the helper sequence (create -> resolve -> install policy -> exec probe
-> cleanup) is exercised without Docker.  Real-Docker verification of the
same sequence is a t032 / user-machine obligation (see progress.md).
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import docker.errors
import httpx
import pytest
from cbrowser.domain.proxy_endpoint import parse_proxy_link
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import (
    DockerAdapter,
    DockerSandboxError,
    EgressProbeFailure,
    LoopbackMappingError,
)
from cbrowser.supervisor.path_validator import PathValidator

_SHA = "sha256:" + "a" * 64

DNS_MAP = {
    "proxy.example.com": "93.184.216.34",
    "host.docker.internal": "192.168.65.254",
}


from collections import namedtuple

_ExecResult = namedtuple("ExecResult", ["exit_code", "output"])


class _FakeContainer:
    def __init__(self, kind: str, calls: list, probe_result: dict | None = None):
        self.id = f"fake-{kind}-id"
        self.kind = kind
        self.calls = calls
        self.probe_result = probe_result
        self.removed = False

    def exec_run(self, cmd, user=None):
        self.calls.append({"exec": list(cmd), "user": user})
        joined = " ".join(str(part) for part in cmd)
        if "getaddrinfo" in joined:
            host = cmd[5]
            ip = DNS_MAP[host]
            return _ExecResult(0, json.dumps([ip]).encode())
        if "egress_probe" in joined:
            payload = self.probe_result or {
                "egress_ip": "203.0.113.7",
                "country_code": "JP",
            }
            return _ExecResult(0, json.dumps(payload).encode())
        raise AssertionError(f"unexpected exec: {cmd}")

    def start(self):
        self.started = True

    def wait(self, timeout=None):
        return {"StatusCode": 0}

    def remove(self, force=False):
        self.removed = True


class _FakeNetwork:
    def __init__(self, name: str):
        self.name = name
        self.removed = False

    def remove(self):
        self.removed = True


class _FakeContainers:
    def __init__(self, calls: list, fail_create: Exception | None = None):
        self.calls = calls
        self.fail_create = fail_create
        self.created: list[_FakeContainer] = []

    def run(self, image, **kwargs):
        self.calls.append({"run": kwargs})
        entrypoint = kwargs.get("entrypoint") or []
        if any("network_policy" in str(part) for part in entrypoint):
            container = _FakeContainer("policy", self.calls)
        else:
            if self.fail_create is not None:
                raise self.fail_create
            container = _FakeContainer("probe", self.calls)
        self.created.append(container)
        return container

    def create(self, image, **kwargs):
        # Policy helpers are launched via create()+start() since the t057
        # leak fix; record the launch exactly like run() so the call-shape
        # assertions in this file are unchanged.
        return self.run(image, **kwargs)


class _FakeNetworks:
    def __init__(self, calls: list):
        self.calls = calls
        self.created: list[_FakeNetwork] = []

    def create(self, name, **kwargs):
        self.calls.append({"network_create": name, **kwargs})
        network = _FakeNetwork(name)
        self.created.append(network)
        return network


class _FakeDockerClient:
    def __init__(self, calls: list, fail_create: Exception | None = None):
        self.calls = calls
        self.containers = _FakeContainers(calls, fail_create=fail_create)
        self.networks = _FakeNetworks(calls)


def _adapter(tmp_path: Path, client=None):
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    calls: list = []
    fake = client if client is not None else _FakeDockerClient(calls)
    adapter = DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=fake,
        browser_image=_SHA,
        stream_image=_SHA,
        policy_image=_SHA,
    )
    return adapter, fake, calls, root


def _probe_kwargs(calls, entrypoint_part):
    for call in calls:
        if "run" not in call:
            continue
        kwargs = call["run"]
        entrypoint = kwargs.get("entrypoint") or []
        if any(entrypoint_part in str(part) for part in entrypoint):
            return kwargs
    raise AssertionError(f"no run call with entrypoint {entrypoint_part}")


def test_probe_helper_uses_browser_policy_and_returns_observation(tmp_path):
    adapter, fake, calls, _root = _adapter(tmp_path)
    endpoint = parse_proxy_link("http://user:pw@proxy.example.com:8080")
    egress_ip, country = adapter.run_egress_probe(
        proxy_id="px-1",
        endpoint=endpoint,
        credentials={"password": "pw", "credential_revision": 1},
    )
    assert (egress_ip, country) == ("203.0.113.7", "JP")

    probe = _probe_kwargs(calls, "time.sleep")
    assert probe["network"].startswith("cbrowser-t005-probe-net-")
    assert probe["extra_hosts"] is None
    assert probe["labels"]["com.cbrowser.role"] == "egress-probe"
    assert probe["labels"]["com.cbrowser.managed-by"] == "supervisor"
    volumes = probe["volumes"]
    assert "/data/engine-cache/geoip" in [v["bind"] for v in volumes.values()]
    assert any(
        v["bind"] == "/run/cbrowser/runtime/proxy_credentials.json"
        and v["mode"] == "ro"
        for v in volumes.values()
    )
    # The policy helper got exactly the resolved proxy endpoint, nothing else.
    policy = _probe_kwargs(calls, "network_policy")
    policy_doc = json.loads(policy["command"][0])
    assert policy_doc["role"] == "browser"
    assert policy_doc["allowed_tcp"] == [["93.184.216.34", 8080]]
    # Cleanup: helper container and probe network are removed.
    assert all(c.removed for c in fake.containers.created)
    assert all(n.removed for n in fake.networks.created)


def test_probe_helper_maps_loopback_to_host_gateway(tmp_path):
    adapter, fake, calls, _root = _adapter(tmp_path)
    endpoint = parse_proxy_link("http://user:pw@127.0.0.1:7890")
    egress_ip, country = adapter.run_egress_probe(
        proxy_id="px-1",
        endpoint=endpoint,
        credentials={"password": "pw", "credential_revision": 2},
    )
    assert (egress_ip, country) == ("203.0.113.7", "JP")
    probe = _probe_kwargs(calls, "time.sleep")
    assert probe["extra_hosts"] == {"host.docker.internal": "host-gateway"}
    policy = _probe_kwargs(calls, "network_policy")
    policy_doc = json.loads(policy["command"][0])
    # Only the mapped host-gateway address + the proxy port is allowed;
    # no other private address is opened (AC-010 negative half).
    assert policy_doc["allowed_tcp"] == [["192.168.65.254", 7890]]


def test_probe_helper_reports_error_code(tmp_path):
    adapter, fake, calls, _root = _adapter(tmp_path)
    endpoint = parse_proxy_link("http://proxy.example.com:8080")
    # Make the probe exec report a GeoIP failure instead of an observation.
    original_run = fake.containers.run

    def run_with_failing_probe(image, **kwargs):
        container = original_run(image, **kwargs)
        if container.kind == "probe":
            container.probe_result = {"error_code": "geoip_db_missing"}
        return container

    fake.containers.run = run_with_failing_probe
    with pytest.raises(EgressProbeFailure) as excinfo:
        adapter.run_egress_probe(
            proxy_id="px-1",
            endpoint=endpoint,
            credentials={"password": None, "credential_revision": 1},
        )
    assert excinfo.value.code == "geoip_db_missing"


def test_probe_helper_crash_is_docker_error(tmp_path):
    adapter, fake, calls, _root = _adapter(tmp_path)
    endpoint = parse_proxy_link("http://proxy.example.com:8080")
    original_run = fake.containers.run

    def run_crashing(image, **kwargs):
        container = original_run(image, **kwargs)
        if container.kind == "probe":
            real_exec = container.exec_run

            def _crash(cmd, user=None):
                if "egress_probe" in " ".join(str(part) for part in cmd):
                    return _ExecResult(1, b"traceback")
                return real_exec(cmd, user=user)

            container.exec_run = _crash
        return container

    fake.containers.run = run_crashing
    with pytest.raises(DockerSandboxError, match="probe helper failed"):
        adapter.run_egress_probe(
            proxy_id="px-1",
            endpoint=endpoint,
            credentials={"password": None, "credential_revision": 1},
        )


def test_loopback_mapping_failure_is_explicit(tmp_path):
    calls: list = []
    fake = _FakeDockerClient(
        calls,
        fail_create=docker.errors.APIError(
            "extra_hosts host-gateway is not supported by this daemon"
        ),
    )
    adapter, _fake, _calls, _root = _adapter(tmp_path, client=fake)
    endpoint = parse_proxy_link("http://127.0.0.1:7890")
    with pytest.raises(LoopbackMappingError) as excinfo:
        adapter.run_egress_probe(
            proxy_id="px-1",
            endpoint=endpoint,
            credentials={"password": "pw", "credential_revision": 1},
        )
    assert "Loopback proxy mapping failed" in str(excinfo.value)
    assert "host-gateway" in str(excinfo.value)


# ---- Browser start: extra_hosts + loopback failure (AC-010/AC-011) ---------
# NOTE (t065): the three Browser-start loopback tests below were deleted
# wholesale here — test_browser_start_adds_extra_hosts_for_mapped_loopback,
# test_browser_start_no_extra_hosts_for_public_proxy and
# test_browser_start_loopback_mapping_failure_is_explicit. t065 moves the
# loopback host-gateway mapping from the Browser start to the forwarder
# start: the Browser never gets extra_hosts anymore, the forwarder does.
# Replacement coverage lives in
# tests/unit/test_t065_proxy_forwarder_mounts.py
# (test_forwarder_adds_extra_hosts_for_mapped_loopback,
# test_forwarder_no_extra_hosts_for_public_proxy,
# test_forwarder_loopback_mapping_failure_is_explicit).
# The egress-probe loopback tests above are untouched: the probe is a
# one-shot helper that still receives credentials directly.


# ---- core.probe_proxy_egress mapping ---------------------------------------


def _stub_core(docker):
    core = SupervisorCore.__new__(SupervisorCore)
    core.docker = docker
    return core


@pytest.mark.asyncio
async def test_core_probe_maps_probe_failure_to_failed_dict():
    docker = SimpleNamespace(
        run_egress_probe=MagicMock(
            side_effect=EgressProbeFailure("geoip_db_missing")
        )
    )
    core = _stub_core(docker)
    endpoint = parse_proxy_link("http://proxy.example.com:8080")
    result = await core.probe_proxy_egress(
        "px-1",
        {
            "scheme": "http",
            "host": "proxy.example.com",
            "port": 8080,
            "username": None,
            "password": None,
            "credential_revision": 1,
            "endpoint_fingerprint": endpoint.fingerprint,
        },
    )
    assert result == {"status": "failed", "error_code": "geoip_db_missing"}


@pytest.mark.asyncio
async def test_core_probe_refuses_fingerprint_mismatch():
    docker = SimpleNamespace(run_egress_probe=MagicMock())
    core = _stub_core(docker)
    result = await core.probe_proxy_egress(
        "px-1",
        {
            "scheme": "http",
            "host": "proxy.example.com",
            "port": 8080,
            "username": None,
            "password": None,
            "credential_revision": 1,
            "endpoint_fingerprint": "0" * 64,
        },
    )
    assert result == {"status": "failed", "error_code": "endpoint_mismatch"}
    docker.run_egress_probe.assert_not_called()


@pytest.mark.asyncio
async def test_core_probe_returns_observation_on_success():
    docker = SimpleNamespace(
        run_egress_probe=MagicMock(return_value=("203.0.113.7", "JP"))
    )
    core = _stub_core(docker)
    endpoint = parse_proxy_link("http://user:pw@proxy.example.com:8080")
    result = await core.probe_proxy_egress(
        "px-1",
        {
            "scheme": "http",
            "host": "proxy.example.com",
            "port": 8080,
            "username": "user",
            "password": "pw",
            "credential_revision": 3,
            "endpoint_fingerprint": endpoint.fingerprint,
        },
    )
    assert result == {
        "status": "ok",
        "egress_ip": "203.0.113.7",
        "country_code": "JP",
    }


# ---- core._write_proxy_credentials loopback mapping (AC-010) -------------


def test_write_proxy_credentials_maps_loopback_host(tmp_path):
    core = SupervisorCore.__new__(SupervisorCore)
    core.docker = SimpleNamespace(manage_ownership=False)
    target = tmp_path / "proxy_credentials.json"
    core._write_proxy_credentials(
        target,
        {
            "scheme": "http",
            "host": "127.0.0.1",
            "port": 7890,
            "username": "user",
            "password": "pw",
            "credential_revision": 1,
        },
    )
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["host"] == "host.docker.internal"
    assert written["port"] == 7890
    assert written["password"] == "pw"
    assert (target.stat().st_mode & 0o777) == 0o600

    core._write_proxy_credentials(
        target,
        {
            "scheme": "http",
            "host": "proxy.example.com",
            "port": 8080,
            "username": None,
            "password": None,
            "credential_revision": 1,
        },
    )
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["host"] == "proxy.example.com"


# ---- control-server probe endpoint -----------------------------------------


@pytest.mark.asyncio
async def test_control_probe_endpoint_requires_token_and_returns_observation(
    tmp_path,
):
    token = secrets.token_urlsafe(32)
    key = tmp_path / "key"
    key.write_text(token)
    key.chmod(0o600)
    endpoint = parse_proxy_link("http://proxy.example.com:8080")
    core = SimpleNamespace(
        _sessions={},
        _auth_headers=lambda: {},
        probe_proxy_egress=AsyncMock(
            return_value={
                "status": "ok",
                "egress_ip": "203.0.113.7",
                "country_code": "JP",
            }
        ),
    )
    app = create_control_app(core, key)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://supervisor"
    ) as client:
        denied = await client.post(
            "/supervisor/v1/proxies/px-1/probe",
            json={
                "scheme": "http",
                "host": "proxy.example.com",
                "port": 8080,
                "username": None,
                "password": None,
                "credential_revision": 1,
                "endpoint_fingerprint": endpoint.fingerprint,
            },
        )
        assert denied.status_code == 401
        resp = await client.post(
            "/supervisor/v1/proxies/px-1/probe",
            json={
                "scheme": "http",
                "host": "proxy.example.com",
                "port": 8080,
                "username": None,
                "password": None,
                "credential_revision": 1,
                "endpoint_fingerprint": endpoint.fingerprint,
            },
            headers={"Authorization": "Bearer " + token},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["egress_ip"] == "203.0.113.7"
        assert body["country_code"] == "JP"
        assert "password" not in body
