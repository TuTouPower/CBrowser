"""t065: forwarder container wiring proofs (no Docker daemon required).

Covers the supervisor side of credential isolation: the Browser container
never mounts the credentials file, the forwarder container mounts it alone,
the Runner resolves a credentialless forwarder endpoint, and the scanner
counts the forwarder role. The Docker client is faked.

Mock boundary (test f005): only the Docker SDK surface is faked
(``client.containers.run/create/get``, ``container.exec_run`` answers).
The adapter's own internals — ``_prepare_policy_gate``,
``_resolved_endpoint``, ``_install_network_policy`` and
``_wait_for_proxy_forwarder_ready`` — execute for real against a tmp_path
data root, so a signature drift like the missing ``role`` argument can
never again hide behind a stub. The remaining stubs
(``create_browser_network``, ``ensure_runtime_cache``,
``setup_x11_permissions``, ``cleanup_container_by_name``,
``_validate_cache_paths``) are Docker-daemon/filesystem operations with
their own coverage elsewhere, not the wiring under test here.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import docker
import pytest

from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig
from cbrowser.runtime_agent.runner import (
    PROXY_FORWARDER_FILENAME,
    ProxyCredentialsChangedError,
    resolve_proxy_server_arg,
)
from cbrowser.supervisor.container_spec import proxy_forwarder_labels
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.volume_spec import proxy_forwarder_volumes

IMAGE = "sha256:" + "a" * 64


def _config(proxy_id: str | None) -> ProfileConfig:
    return ProfileConfig(name="p1", proxy_id=proxy_id)


def _snapshot(revision: int | None) -> ConfigVersionSnapshot:
    return ConfigVersionSnapshot(
        id="snap_1",
        profile_id="p1",
        version=1,
        config={},
        proxy_credential_revision=revision,
        created_at="2026-01-01T00:00:00+00:00",
    )


def _exec_result(exit_code: int, output: bytes = b"") -> SimpleNamespace:
    return SimpleNamespace(exit_code=exit_code, output=output)


def _fake_container(*, dns_ips: dict[str, list[str]] | None = None) -> MagicMock:
    """A fake container whose exec_run answers the Docker-DNS script
    (getaddrinfo; host and port are the last two argv entries) and the
    forwarder readiness probe with exit 0."""
    container = MagicMock()
    container.id = "cid"

    def _exec_run(cmd, user=None, **kwargs):
        joined = " ".join(str(part) for part in cmd)
        if "getaddrinfo" in joined:
            host = str(cmd[-2])
            ips = (dns_ips or {}).get(host, ["203.0.113.7"])
            return _exec_result(0, json.dumps(ips).encode())
        return _exec_result(0, b"")

    container.exec_run = MagicMock(side_effect=_exec_run)
    return container


def _stage_fake_docker(adapter, container: MagicMock) -> MagicMock:
    """Wire the fake Docker client so the adapter's own internals run
    for real (test f005): no stale container (``get`` raises NotFound),
    ``run`` returns the fake container, ``create`` returns a policy
    helper that reports exit 0. Returns the policy helper."""
    adapter.client.containers.get = MagicMock(
        side_effect=docker.errors.NotFound("no such container")
    )
    adapter.client.containers.run = MagicMock(return_value=container)
    helper = MagicMock()
    helper.wait.return_value = {"StatusCode": 0}
    helper.logs.return_value = b""
    adapter.client.containers.create = MagicMock(return_value=helper)
    return helper


def _policy_from_helper(adapter) -> dict:
    """The NetworkPolicySpec JSON the real _install_network_policy fed
    to the policy helper container (the create call's command)."""
    command = adapter.client.containers.create.call_args.kwargs["command"]
    return json.loads(command[0])


def _spy_gate(adapter) -> tuple[MagicMock, list[Path]]:
    """Spy on _prepare_policy_gate: the real method runs, the call is
    recorded, and the returned gate dir is captured (a wraps mock's
    ``return_value`` is not updated by the wrapped call)."""
    captured: list[Path] = []
    real = adapter._prepare_policy_gate

    def _record(*args, **kwargs):
        result = real(*args, **kwargs)
        captured.append(result)
        return result

    spy = MagicMock(side_effect=_record)
    adapter._prepare_policy_gate = spy
    return spy, captured


def _adapter(tmp_path: Path) -> tuple[DockerAdapter, Path]:
    data_root = tmp_path / "data"
    (data_root / "engine_cache" / "geoip").mkdir(parents=True)
    validator = PathValidator(data_root)
    adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=data_root / "engine_cache",
        docker_client=MagicMock(),
        browser_image=IMAGE,
        stream_image=IMAGE,
        proxy_forwarder_image=IMAGE,
        policy_image=IMAGE,
        deployment_instance_id="dep-1",
    )
    adapter.remember_profile_number("p1", 1)
    return adapter, data_root


def test_forwarder_volumes_mount_credentials_only(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    gate.mkdir()
    creds = tmp_path / "proxy_credentials.json"
    creds.write_text("{}", encoding="utf-8")
    volumes = proxy_forwarder_volumes(gate=gate, creds_file=creds)
    assert volumes == {
        str(gate): {"bind": "/run/cbrowser_policy", "mode": "ro"},
        str(creds): {"bind": "/run/cbrowser/proxy_credentials.json", "mode": "ro"},
    }


def test_forwarder_labels_carry_role_and_identity() -> None:
    labels = proxy_forwarder_labels(
        "cbrowser-t005",
        "p1",
        "1",
        1,
        deployment_id="dep-1",
    )
    assert labels["com.cbrowser.role"] == "proxy-forwarder"
    assert labels["com.cbrowser.profile-id"] == "p1"
    assert labels["com.cbrowser.config-version"] == "1"
    assert labels["com.cbrowser.profile-number"] == "0001"
    assert labels["com.cbrowser.instance-id"] == "dep-1"


def test_forwarder_container_name(tmp_path: Path) -> None:
    adapter, _data_root = _adapter(tmp_path)
    assert (
        adapter.get_proxy_forwarder_container_name("p1")
        == "cbrowser-t005-0001-proxy-forwarder"
    )


def test_secret_creds_path_is_outside_every_browser_mount(tmp_path: Path) -> None:
    adapter, data_root = _adapter(tmp_path)
    dirs = adapter.prepare_profile_directories("p1")
    secret_creds = (
        adapter.validator.get_secret_dir("p1") / "proxy_credentials.json"
    )
    from cbrowser.supervisor.volume_spec import browser_volumes

    gate = data_root / "gate"
    gate.mkdir()
    volumes = browser_volumes(
        profile_id="p1",
        dirs=dirs,
        gate=gate,
        engine_cache=data_root / "engine_cache",
        geoip_cache=data_root / "engine_cache" / "geoip",
    )
    for source, spec in volumes.items():
        assert Path(source).name != "proxy_credentials.json", source
        assert spec["bind"] != "/run/cbrowser/runtime/proxy_credentials.json"
        assert not secret_creds.is_relative_to(Path(source)), (
            f"secret creds {secret_creds} reachable via Browser mount {source}"
        )
    # The secret dir itself is outside the Browser-mounted runtime dir.
    assert not adapter.validator.get_secret_dir("p1").is_relative_to(
        dirs["runtime"]
    )


@pytest.mark.asyncio
async def test_browser_container_mounts_no_credentials(
    tmp_path: Path, monkeypatch
) -> None:
    """Even with a legacy credentials file sitting in the runtime dir, the
    Browser container must not mount it (AC-001).

    The endpoint file is written here by the caller (in production by
    start_profile); deleting a legacy credentials file left in the
    runtime dir is start_profile's job (test_start_profile_... below),
    not the container start's. The gate preparation and the egress
    policy run for real (test f005) — no stub of the adapter's own
    internals — so the allow-list is the forwarder IP resolved through
    Docker DNS, never the upstream.
    """
    adapter, data_root = _adapter(tmp_path)
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._validate_cache_paths = MagicMock()
    dirs = adapter.prepare_profile_directories("p1")
    (dirs["runtime"] / "snapshot.json").write_text(
        json.dumps(
            {"version": 1, "config": {"proxy_id": "proxy-1", "geoip": False}}
        ),
        encoding="utf-8",
    )
    # Legacy location: must be ignored by the Browser container now.
    (dirs["runtime"] / "proxy_credentials.json").write_text(
        json.dumps(
            {
                "scheme": "http",
                "host": "127.0.0.1",
                "port": 18081,
                "username": "u",
                "password": "s3cr3t",
                "credential_revision": 2,
            }
        ),
        encoding="utf-8",
    )
    (dirs["runtime"] / PROXY_FORWARDER_FILENAME).write_text(
        json.dumps(
            {
                "scheme": "http",
                "host": "cbrowser-t005-0001-proxy-forwarder",
                "port": 18080,
                "credential_revision": 2,
            }
        ),
        encoding="utf-8",
    )
    container = _fake_container(
        dns_ips={"cbrowser-t005-0001-proxy-forwarder": ["172.18.0.3"]}
    )
    _stage_fake_docker(adapter, container)
    gate, gate_dirs = _spy_gate(adapter)
    await adapter.start_browser_container(
        profile_id="p1",
        runtime_instance_id="i1",
        snapshot_json_path=dirs["runtime"] / "snapshot.json",
    )
    volumes = adapter.client.containers.run.call_args.kwargs["volumes"]
    for source, spec in volumes.items():
        assert Path(source).name != "proxy_credentials.json", source
        assert spec["bind"] != "/run/cbrowser/runtime/proxy_credentials.json"
    # The Browser's egress policy must point at the forwarder, never at an
    # upstream that carries credentials.
    policy = _policy_from_helper(adapter)
    assert policy["role"] == "browser"
    assert policy["allowed_tcp"] == [["172.18.0.3", 18080]]
    gate.assert_called_once_with("p1", "i1", "browser")
    gate_dir = gate_dirs[0]
    assert (gate_dir / "startup_gate.py").is_file()
    assert json.loads((gate_dir / "ready.json").read_text())["role"] == "browser"


@pytest.mark.asyncio
async def test_create_proxy_forwarder_wires_secret_only(
    tmp_path: Path,
) -> None:
    """The forwarder is the only container that mounts the credentials
    file (ro, from the secret dir); its gate preparation, upstream
    resolution, policy install and readiness wait all run for real
    (test f005) — the "proxy-forwarder" role gate was never really
    executed before this test."""
    adapter, data_root = _adapter(tmp_path)
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    creds = secret_dir / "proxy_credentials.json"
    creds.write_text(
        json.dumps(
            {
                "scheme": "http",
                "host": "203.0.113.7",
                "port": 18081,
                "username": "u",
                "password": "s3cr3t",
                "credential_revision": 2,
            }
        ),
        encoding="utf-8",
    )
    creds.chmod(0o600)
    container = _fake_container()
    _stage_fake_docker(adapter, container)
    gate, gate_dirs = _spy_gate(adapter)
    result = await adapter.create_proxy_forwarder(
        profile_id="p1",
        runtime_instance_id="i1",
        creds_file=creds,
        config_version="1",
    )
    assert result is container
    kwargs = adapter.client.containers.run.call_args.kwargs
    # The image is the first positional argument, as in the Browser and
    # Stream starts; the remaining arguments are keywords.
    assert adapter.client.containers.run.call_args.args[0] == IMAGE
    assert kwargs["name"] == "cbrowser-t005-0001-proxy-forwarder"
    assert kwargs["network"] == adapter.get_browser_network_name("p1")
    assert kwargs["user"] == "1000:1000"
    assert kwargs["read_only"] is True
    assert kwargs["cap_drop"] == ["ALL"]
    volumes = kwargs["volumes"]
    assert volumes[str(creds)] == {
        "bind": "/run/cbrowser/proxy_credentials.json",
        "mode": "ro",
    }
    assert len([s for s in volumes if Path(s).name == "proxy_credentials.json"]) == 1
    labels = kwargs["labels"]
    assert labels["com.cbrowser.role"] == "proxy-forwarder"
    assert labels["com.cbrowser.instance-id"] == "dep-1"
    # The gate really was prepared for the proxy-forwarder role, and
    # the policy really installed allows only the upstream endpoint
    # (plus Docker DNS and the fixed listen port inbound).
    gate.assert_called_once_with("p1", "i1", "proxy-forwarder")
    gate_dir = gate_dirs[0]
    assert (gate_dir / "startup_gate.py").is_file()
    assert json.loads((gate_dir / "ready.json").read_text())["role"] == (
        "proxy-forwarder"
    )
    policy = _policy_from_helper(adapter)
    assert policy["role"] == "proxy-forwarder"
    assert policy["allowed_tcp"] == [["203.0.113.7", 18081]]
    assert policy["allowed_udp"] == [["127.0.0.11", 53]]
    assert policy["input_tcp_ports"] == [18080]


def test_create_proxy_forwarder_rejects_loose_credentials(tmp_path: Path) -> None:
    import asyncio

    from cbrowser.supervisor.docker_adapter import DockerSandboxError

    adapter, _data_root = _adapter(tmp_path)
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    creds = secret_dir / "proxy_credentials.json"
    creds.write_text("{}", encoding="utf-8")
    creds.chmod(0o644)
    with pytest.raises(DockerSandboxError):
        asyncio.run(
            adapter.create_proxy_forwarder(
                profile_id="p1",
                runtime_instance_id="i1",
                creds_file=creds,
                config_version="1",
            )
        )


def test_scan_counts_proxy_forwarder_role(tmp_path: Path) -> None:
    adapter, _data_root = _adapter(tmp_path)
    container = MagicMock()
    container.id = "cid"
    container.name = "cbrowser-t005-0001-proxy-forwarder"
    container.status = "running"
    container.labels = {
        "com.cbrowser.prefix": "cbrowser-t005",
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": "proxy-forwarder",
        "com.cbrowser.profile-id": "p1",
        "com.cbrowser.config-version": "1",
        "com.cbrowser.profile-number": "0001",
        "com.cbrowser.instance-id": "dep-1",
    }
    container.attrs = {
        "Config": {"Env": ["RUNTIME_INSTANCE_ID=i1"]},
        "Mounts": [],
    }
    adapter.client.containers.list = MagicMock(return_value=[container])
    adapter._runtime_policy_ready = MagicMock(return_value=True)
    items = adapter.scan_active_containers()
    assert len(items) == 1
    assert items[0]["role"] == "proxy-forwarder"
    assert items[0]["profile_id"] == "p1"


def test_runner_resolves_credentialless_forwarder_arg(tmp_path: Path) -> None:
    endpoint = tmp_path / PROXY_FORWARDER_FILENAME
    endpoint.write_text(
        json.dumps(
            {
                "scheme": "http",
                "host": "cbrowser-t005-0001-proxy-forwarder",
                "port": 18080,
                "credential_revision": 2,
            }
        ),
        encoding="utf-8",
    )
    arg = resolve_proxy_server_arg(_config("proxy-1"), _snapshot(2), endpoint)
    assert arg == "--proxy-server=http://cbrowser-t005-0001-proxy-forwarder:18080"
    assert "s3cr3t" not in (arg or "")
    assert "@" not in (arg or "").split("://", 1)[1]


def test_runner_resolves_no_arg_without_proxy(tmp_path: Path) -> None:
    assert (
        resolve_proxy_server_arg(_config(None), _snapshot(None), tmp_path / "x")
        is None
    )


def test_runner_fails_closed_on_endpoint_problems(tmp_path: Path) -> None:
    good = {
        "scheme": "http",
        "host": "cbrowser-t005-0001-proxy-forwarder",
        "port": 18080,
        "credential_revision": 2,
    }
    path = tmp_path / PROXY_FORWARDER_FILENAME
    # Stale revision.
    path.write_text(json.dumps({**good, "credential_revision": 3}), encoding="utf-8")
    with pytest.raises(ProxyCredentialsChangedError):
        resolve_proxy_server_arg(_config("proxy-1"), _snapshot(2), path)
    # Non-HTTP scheme is never a Browser proxy entry point.
    path.write_text(json.dumps({**good, "scheme": "socks5"}), encoding="utf-8")
    with pytest.raises(ProxyCredentialsChangedError):
        resolve_proxy_server_arg(_config("proxy-1"), _snapshot(2), path)
    # Missing file.
    with pytest.raises(ProxyCredentialsChangedError):
        resolve_proxy_server_arg(
            _config("proxy-1"), _snapshot(2), tmp_path / "missing.json"
        )
    # Malformed JSON.
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ProxyCredentialsChangedError):
        resolve_proxy_server_arg(_config("proxy-1"), _snapshot(2), path)


@pytest.mark.asyncio
async def test_start_profile_with_proxy_writes_secret_and_endpoint(
    tmp_path: Path,
) -> None:
    """t065 replacement for the deleted t035 end-to-end proxy test.

    start_profile must write credentials to the Profile secret dir
    (0600, never under the Browser-mounted runtime dir), write the
    credentialless endpoint file to the runtime dir, and create the
    forwarder before the Browser container starts. A credentials file
    left in the runtime dir by an earlier start (code f001) must be
    deleted, not merely ignored — the Browser mounts the whole runtime
    dir read-write, so any file left there stays readable.
    """
    import httpx
    from types import SimpleNamespace

    from cbrowser.supervisor.core import SupervisorCore
    from cbrowser.supervisor.port_allocator import PortAllocator

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
    # Pre-t065 legacy location (code f001): an old credentials file
    # already sitting in the runtime dir when this start runs.
    (dirs["runtime"] / "proxy_credentials.json").write_text(
        json.dumps(
            {
                "scheme": "http",
                "host": "127.0.0.1",
                "port": 18081,
                "username": "u",
                "password": "s3cr3t",
                "credential_revision": 1,
            }
        ),
        encoding="utf-8",
    )
    key_file = tmp_path / "agent_key"
    key_file.write_text("01234567890123456789012345678901", encoding="utf-8")
    key_file.chmod(0o600)

    stream_c = MagicMock()
    stream_c.id = "s_id"
    stream_c.name = "stream_c"
    stream_c.status = "running"
    stream_c.reload = MagicMock()
    browser_c = MagicMock()
    browser_c.id = "b_id"
    browser_c.name = "browser_c"

    forwarder_calls: list[tuple] = []

    async def create_forwarder(profile_id, runtime_instance_id, config_version):
        forwarder_calls.append((profile_id, runtime_instance_id, config_version))
        return MagicMock()

    def write_runner_info(profile_id, runtime_instance_id, snapshot_json_path):
        # The forwarder must already exist when the Browser starts.
        assert forwarder_calls, "Browser started before the forwarder"
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
                    "browser_product": "Chrome/146.0.0.0",
                    "browser_user_agent": "Mozilla/5.0",
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
        create_browser_network=AsyncMock(),
        create_proxy_forwarder=AsyncMock(side_effect=create_forwarder),
        get_proxy_forwarder_container_name=(
            lambda pid: "cbrowser-t005-0001-proxy-forwarder"
        ),
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

    def handler(req: httpx.Request) -> httpx.Response:
        if "/proxies/" in req.url.path and req.url.path.endswith("/credentials"):
            return httpx.Response(
                200,
                json={
                    "scheme": "socks5",
                    "host": "proxy.example.com",
                    "port": 1080,
                    "username": "u",
                    "password": "pw",
                    "credential_revision": 2,
                    "proxy_credential_revision": 2,
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

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api"
    ) as api:
        core = SupervisorCore(
            docker_adapter=adapter,
            port_allocator=PortAllocator(30000, 30010),
            event_forwarder=events,
            api_client=api,
            gateway_url="ws://supervisor-host-gw:18097",
            token_file=None,
            agent_key_file=key_file,
            gateway_control=gateway,
        )
        session = await core.start_profile(
            "p1", ProfileConfig(name="p1", proxy_id="px1")
        )
    assert session.observed_state == "running"

    snapshot = json.loads((dirs["runtime"] / "snapshot.json").read_text())
    assert snapshot["proxy_credential_revision"] == 2
    # Credentials live only in the secret dir, never in the runtime dir —
    # the pre-placed legacy file above must be gone, not merely ignored.
    secret_creds = validator.get_secret_dir("p1") / "proxy_credentials.json"
    assert secret_creds.is_file()
    assert (secret_creds.stat().st_mode & 0o777) == 0o600
    assert json.loads(secret_creds.read_text())["password"] == "pw"
    assert not (dirs["runtime"] / "proxy_credentials.json").exists()
    # The endpoint file is credentialless and names the forwarder.
    endpoint = json.loads((dirs["runtime"] / "proxy_forwarder.json").read_text())
    assert endpoint == {
        "scheme": "http",
        "host": "cbrowser-t005-0001-proxy-forwarder",
        "port": 18080,
        "credential_revision": 2,
    }
    # The forwarder was created once, before the Browser.
    assert len(forwarder_calls) == 1
    assert forwarder_calls[0][0] == "p1"
    assert forwarder_calls[0][2] == 1
    # The Runner resolves a credentialless arg from the endpoint file.
    assert resolve_proxy_server_arg(
        ProfileConfig(name="p1", proxy_id="px1"),
        ConfigVersionSnapshot.model_validate(snapshot),
        dirs["runtime"] / "proxy_forwarder.json",
    ) == "--proxy-server=http://cbrowser-t005-0001-proxy-forwarder:18080"


def _stage_forwarder_creds(adapter, data_root, host: str, port: int):
    """Secret-dir credentials file for one forwarder start (0600)."""
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    creds = secret_dir / "proxy_credentials.json"
    creds.write_text(
        json.dumps(
            {
                "scheme": "http",
                "host": host,
                "port": port,
                "username": "u",
                "password": "s3cr3t",
                "credential_revision": 2,
            }
        ),
        encoding="utf-8",
    )
    creds.chmod(0o600)
    return creds


@pytest.mark.asyncio
async def test_forwarder_adds_extra_hosts_for_mapped_loopback(tmp_path: Path) -> None:
    """t052 AC-010 moved to the forwarder (t065): a loopback upstream is
    stored as host.docker.internal in the secret-dir credentials file,
    and the forwarder container gets the host-gateway extra_hosts entry
    so the name resolves to the host. The Browser gets none. The gate
    preparation and the egress policy run for real (test f005)."""
    adapter, data_root = _adapter(tmp_path)
    creds = _stage_forwarder_creds(adapter, data_root, "host.docker.internal", 7890)
    container = _fake_container(
        dns_ips={"host.docker.internal": ["192.168.65.254"]}
    )
    _stage_fake_docker(adapter, container)
    gate, _gate_dirs = _spy_gate(adapter)
    await adapter.create_proxy_forwarder(
        profile_id="p1",
        runtime_instance_id="i1",
        creds_file=creds,
        config_version="1",
    )
    kwargs = adapter.client.containers.run.call_args.kwargs
    assert kwargs["extra_hosts"] == {"host.docker.internal": "host-gateway"}
    gate.assert_called_once_with("p1", "i1", "proxy-forwarder")
    policy = _policy_from_helper(adapter)
    assert policy["role"] == "proxy-forwarder"
    assert policy["allowed_tcp"] == [["192.168.65.254", 7890]]


@pytest.mark.asyncio
async def test_forwarder_no_extra_hosts_for_public_proxy(tmp_path: Path) -> None:
    """A non-loopback upstream needs no host-gateway mapping; the gate
    preparation and the egress policy run for real (test f005)."""
    adapter, data_root = _adapter(tmp_path)
    creds = _stage_forwarder_creds(adapter, data_root, "proxy.example.com", 8080)
    container = _fake_container(
        dns_ips={"proxy.example.com": ["93.184.216.34"]}
    )
    _stage_fake_docker(adapter, container)
    gate, _gate_dirs = _spy_gate(adapter)
    await adapter.create_proxy_forwarder(
        profile_id="p1",
        runtime_instance_id="i1",
        creds_file=creds,
        config_version="1",
    )
    kwargs = adapter.client.containers.run.call_args.kwargs
    assert kwargs["extra_hosts"] is None
    gate.assert_called_once_with("p1", "i1", "proxy-forwarder")
    policy = _policy_from_helper(adapter)
    assert policy["role"] == "proxy-forwarder"
    assert policy["allowed_tcp"] == [["93.184.216.34", 8080]]


@pytest.mark.asyncio
async def test_forwarder_loopback_mapping_failure_is_explicit(
    tmp_path: Path,
) -> None:
    """t052 AC-011 moved to the forwarder (t065): a daemon that rejects
    the host-gateway mapping fails the forwarder start with an explicit
    remediation, never a silent proxy failure."""
    import docker

    from cbrowser.supervisor.docker_adapter import LoopbackMappingError

    adapter, data_root = _adapter(tmp_path)
    creds = _stage_forwarder_creds(adapter, data_root, "host.docker.internal", 7890)
    # No stale container (real cleanup takes the NotFound path); the
    # daemon rejects the host-gateway mapping at run time.
    adapter.client.containers.get = MagicMock(
        side_effect=docker.errors.NotFound("no such container")
    )
    adapter.client.containers.run = MagicMock(
        side_effect=docker.errors.APIError(
            "extra_hosts host-gateway is not supported by this daemon"
        )
    )
    gate, _gate_dirs = _spy_gate(adapter)
    with pytest.raises(LoopbackMappingError) as excinfo:
        await adapter.create_proxy_forwarder(
            profile_id="p1",
            runtime_instance_id="i1",
            creds_file=creds,
            config_version="1",
        )
    assert "Loopback proxy mapping failed" in str(excinfo.value)
    assert "host-gateway" in str(excinfo.value)
    # The gate was really prepared before the run failed.
    gate.assert_called_once_with("p1", "i1", "proxy-forwarder")


def test_cleanup_by_name_removes_proxy_forwarder(tmp_path: Path) -> None:
    """t065: cleanup_container_by_name must accept the forwarder role —
    create_proxy_forwarder and teardown both remove it by name, and the
    ownership check reconstructs the name from the role label."""
    adapter, _data_root = _adapter(tmp_path)
    container = MagicMock()
    container.name = "cbrowser-t005-0001-proxy-forwarder"
    container.labels = {
        "com.cbrowser.prefix": "cbrowser-t005",
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": "proxy-forwarder",
        "com.cbrowser.profile-id": "p1",
        "com.cbrowser.profile-number": "0001",
    }
    adapter.client.containers.get = MagicMock(return_value=container)
    adapter.cleanup_container_by_name("cbrowser-t005-0001-proxy-forwarder")
    container.remove.assert_called_once_with(force=True)


def test_startup_gate_accepts_proxy_forwarder_role(tmp_path: Path) -> None:
    """t065: the gated entrypoint passes --role proxy-forwarder; the gate
    must accept it and wait for a matching ready marker."""
    from cbrowser.supervisor.startup_gate import parse_args, wait_for_marker

    args, app_cmd = parse_args(
        [
            "--instance-id",
            "i1",
            "--role",
            "proxy-forwarder",
            "--gate-dir",
            str(tmp_path),
            "--",
            "/app/entrypoint.sh",
        ]
    )
    assert args.role == "proxy-forwarder"
    assert app_cmd == ["/app/entrypoint.sh"]
    (tmp_path / "ready.json").write_text(
        json.dumps(
            {"instance_id": "i1", "role": "proxy-forwarder", "status": "ready"}
        ),
        encoding="utf-8",
    )
    assert wait_for_marker(tmp_path, "i1", "proxy-forwarder", timeout=1.0)
