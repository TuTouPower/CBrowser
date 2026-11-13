"""t051 Area G (AC-012/AC-014/AC-015/AC-016/AC-021): Supervisor identity.

- Deployment ownership via the com.cbrowser.instance-id label (the
  deployment instance id) on scans, helper cleanup, gateway scan and
  the core browser lookup (A59/AC-021). The per-launch runtime instance
  id is matched from the containers' runtime configuration, never from
  labels.
- Prefix validation (A22) at the deployment entry points and the
  deployment identity / network-timeout constructor inputs.
- Media network creation no longer holds the allocation lock across
  Docker calls; a hung Docker call times out instead of stalling every
  Profile (AC-015).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cbrowser.supervisor.container_spec import validate_resource_prefix
from cbrowser.supervisor.docker_adapter import (
    DockerAdapter,
    DockerSandboxError,
)
from cbrowser.supervisor.network_spec import (
    network_labels,
    network_ownership_matches,
)
from cbrowser.supervisor.path_validator import PathValidator
from docker.errors import NotFound

BROWSER = "sha256:" + "a" * 64
STREAM = "sha256:" + "b" * 64


def _adapter(tmp_path: Path, client, **kw) -> DockerAdapter:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    (engine / "geoip").mkdir(parents=True, exist_ok=True)
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=client,
        browser_image=BROWSER,
        stream_image=STREAM,
        **kw,
    )


# ---------------------------------------------------------------- validation

@pytest.mark.parametrize("prefix", ["cbrowser", "a", "a1", "a_b", "a1_b2", "cbrowser2"])
def test_validate_resource_prefix_accepts(prefix: str):
    assert validate_resource_prefix(prefix) == prefix


@pytest.mark.parametrize(
    "prefix", ["inst-b", "Bad", "bad prefix", "-lead", "_lead", "", "a-b", "a.b"]
)
def test_validate_resource_prefix_rejects(prefix: str):
    with pytest.raises(ValueError, match="prefix"):
        validate_resource_prefix(prefix)


def test_adapter_init_is_not_a_validation_entry_point(tmp_path: Path):
    # A22 validation lives at the deployment entry points (deploy.sh,
    # Supervisor startup); construction receives the validated value or
    # the compiled-in default and does not re-validate.
    adapter = _adapter(tmp_path, MagicMock(), resource_prefix="inst-b")
    assert adapter.resource_prefix == "inst-b"


def test_adapter_default_prefix_is_the_deployment_default(tmp_path: Path):
    adapter = _adapter(tmp_path, MagicMock())
    assert adapter.resource_prefix == "cbrowser-t005"


def test_adapter_deployment_id_from_arg_and_env(tmp_path: Path, monkeypatch):
    adapter = _adapter(tmp_path, MagicMock(), deployment_instance_id="dep-1")
    assert adapter.deployment_instance_id == "dep-1"
    assert adapter.network_timeout == 30.0
    monkeypatch.setenv("CBROWSER_INSTANCE_ID", "dep-env")
    monkeypatch.setenv("CBROWSER_DOCKER_NETWORK_TIMEOUT", "5")
    adapter2 = _adapter(tmp_path, MagicMock())
    assert adapter2.deployment_instance_id == "dep-env"
    assert adapter2.network_timeout == 5.0


# ---------------------------------------------------------------- scan ownership

def _container(
    name: str,
    labels: dict,
    status: str = "running",
    runtime_instance_id: str = "inst-1",
) -> SimpleNamespace:
    # The runtime instance id travels in the container configuration
    # (Stream env channel), mirroring production containers.
    attrs = {
        "Config": {
            "Env": [f"CBROWSER_RUNTIME_INSTANCE_ID={runtime_instance_id}"],
        }
    }
    return SimpleNamespace(
        id=f"id-{name}", name=name, status=status, labels=labels, attrs=attrs
    )


def _sandbox_labels(role: str, profile_id: str, deployment_id: str | None) -> dict:
    labels = {
        "com.cbrowser.prefix": "cbrowser-t005",
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": role,
        "com.cbrowser.profile-id": profile_id,
        "com.cbrowser.config-version": "1",
        "com.cbrowser.profile-number": "0001",
    }
    if deployment_id is not None:
        labels["com.cbrowser.instance-id"] = deployment_id
    return labels


def test_scan_active_containers_filters_by_deployment_id(tmp_path: Path):
    client = MagicMock()
    client.containers.list.return_value = [
        _container("own", _sandbox_labels("browser", "p1", "dep-1")),
        _container("foreign", _sandbox_labels("browser", "p2", "dep-2")),
        _container("unlabelled", _sandbox_labels("stream", "p3", None)),
    ]
    adapter = _adapter(tmp_path, client, deployment_instance_id="dep-1")
    adapter._runtime_policy_ready = MagicMock(return_value=True)
    scanned = adapter.scan_active_containers()
    assert [item["profile_id"] for item in scanned] == ["p1"]
    # The reported instance id is the runtime id from the container
    # configuration, not the deployment identity from the label.
    assert scanned[0]["instance_id"] == "inst-1"


def test_scan_active_containers_claims_nothing_when_unconfigured(tmp_path: Path):
    # t069: an unconfigured supervisor has no identity to claim with;
    # the old prefix/name acceptance fallback is deleted, so nothing is
    # adopted regardless of the candidate labels.
    client = MagicMock()
    client.containers.list.return_value = [
        _container("a", _sandbox_labels("browser", "p1", "dep-1")),
        _container("b", _sandbox_labels("browser", "p2", None)),
    ]
    adapter = _adapter(tmp_path, client)
    adapter._runtime_policy_ready = MagicMock(return_value=True)
    scanned = adapter.scan_active_containers()
    assert scanned == []


def test_cleanup_orphan_helpers_removes_only_own_deployment(tmp_path: Path):
    def helper(name: str, role: str, deployment_id: str | None) -> SimpleNamespace:
        labels = {
            "com.cbrowser.prefix": "cbrowser-t005",
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.role": role,
        }
        if deployment_id is not None:
            labels["com.cbrowser.instance-id"] = deployment_id
        return SimpleNamespace(
            name=name, labels=labels, remove=MagicMock()
        )

    own = helper("cbrowser-t005-policy-abcdef012345", "network-policy", "dep-1")
    foreign = helper("cbrowser-t005-policy-abcdef012346", "network-policy", "dep-2")
    unlabelled = helper("cbrowser-t005-policy-abcdef012347", "network-policy", None)
    client = MagicMock()
    client.containers.list.return_value = [own, foreign, unlabelled]
    adapter = _adapter(tmp_path, client, deployment_instance_id="dep-1")
    adapter._cleanup_orphan_helpers()
    own.remove.assert_called_once_with(force=True)
    foreign.remove.assert_not_called()
    unlabelled.remove.assert_not_called()


def test_scan_gateway_containers_filters_by_deployment_id(tmp_path: Path):
    def gateway(name: str, deployment_id: str | None) -> SimpleNamespace:
        labels = {
            "com.cbrowser.prefix": "cbrowser-t005",
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.role": "gateway",
        }
        if deployment_id is not None:
            labels["com.cbrowser.instance-id"] = deployment_id
        return SimpleNamespace(id=f"id-{name}", name=name, status="running", labels=labels)

    client = MagicMock()
    client.containers.list.return_value = [
        gateway("gw-own", "dep-1"),
        gateway("gw-foreign", "dep-2"),
    ]
    adapter = _adapter(tmp_path, client, deployment_instance_id="dep-1")
    assert [c.name for c in adapter.scan_gateway_containers()] == ["gw-own"]


# ---------------------------------------------------------------- label wiring

@pytest.mark.asyncio
async def test_browser_start_carries_instance_id_and_numbered_service(
    tmp_path: Path,
) -> None:
    client = MagicMock()
    adapter = _adapter(tmp_path, client, deployment_instance_id="dep-1")
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=tmp_path / "gate")
    adapter._validate_cache_paths = MagicMock()
    adapter._resolved_endpoint = MagicMock(return_value=[])
    adapter._install_network_policy = MagicMock()
    adapter.remember_profile_number("p1", 1)
    dirs = adapter.prepare_profile_directories("p1")
    (dirs["runtime"] / "snapshot.json").write_text(
        json.dumps({"version": 1, "config": {}}), encoding="utf-8"
    )
    created = MagicMock()
    client.containers.run.return_value = created
    result = await adapter.start_browser_container(
        profile_id="p1",
        runtime_instance_id="inst_1",
        snapshot_json_path=dirs["runtime"] / "snapshot.json",
    )
    assert result is created
    labels = client.containers.run.call_args.kwargs["labels"]
    # The instance-id label is the deployment identity (AC-021); the
    # per-launch runtime id travels in the gated entrypoint instead.
    assert labels["com.cbrowser.instance-id"] == "dep-1"
    assert "inst_1" not in labels.values()
    entrypoint = client.containers.run.call_args.kwargs["entrypoint"]
    assert "inst_1" in entrypoint
    assert labels["com.docker.compose.service"] == "0001-browser"


def test_network_labels_and_ownership_with_deployment_id():
    labels = network_labels("cbrowser", "p1", deployment_id="dep-1")
    assert labels["com.cbrowser.instance-id"] == "dep-1"
    assert network_ownership_matches(labels, deployment_id="dep-1")
    assert not network_ownership_matches(labels, deployment_id="dep-2")
    assert not network_ownership_matches(
        network_labels("cbrowser", "p1"), deployment_id="dep-1"
    )
    # t069: no deployment id configured means nothing is owned; the
    # old prefix/name fallback check is deleted.
    assert not network_ownership_matches(network_labels("cbrowser", "p1"))
    assert not network_ownership_matches(labels)


# ---------------------------------------------------------------- media network timeouts

class _BlockingNetworks:
    """networks.get -> NotFound; networks.list -> created networks;
    networks.create blocks on an event for the 'slow' profile, succeeds
    fast otherwise."""

    def __init__(self) -> None:
        self.created: list[str] = []
        self.by_name: dict[str, SimpleNamespace] = {}
        self.block = threading.Event()
        self.create_calls = 0

    def get(self, name: str):
        if name not in self.by_name:
            raise NotFound(f"network {name} not found")
        return self.by_name[name]

    def list(self):
        return list(self.by_name.values())

    def create(self, name: str, driver=None, ipam=None, labels=None):
        self.create_calls += 1
        if "slow" in name:
            self.block.wait(timeout=30)
        config = []
        if ipam is not None:
            for pool_config in ipam.get("Config") or []:
                config.append(
                    {
                        "Subnet": pool_config.get("Subnet"),
                        "IPRange": pool_config.get("IPRange"),
                    }
                )
        network = SimpleNamespace(
            name=name,
            attrs={"Labels": labels or {}, "IPAM": {"Config": config}},
        )
        self.by_name[name] = network
        self.created.append(name)
        return network


def test_media_network_create_timeout_does_not_block_other_profiles(
    tmp_path: Path,
) -> None:
    client = MagicMock()
    networks = _BlockingNetworks()
    client.networks = networks
    adapter = _adapter(tmp_path, client, network_timeout=0.2)
    errors: dict[str, Exception] = {}
    results: dict[str, object] = {}

    def run_slow() -> None:
        try:
            results["slow"] = adapter._ensure_media_network("slow")
        except Exception as exc:  # noqa: BLE001 - captured for assertion
            errors["slow"] = exc

    thread = threading.Thread(target=run_slow, daemon=True)
    thread.start()
    started = time.monotonic()
    # A concurrent fast profile must still complete while the slow create
    # is hung: the allocation lock is not held across the Docker call.
    fast = adapter._ensure_media_network("fast")
    assert fast.name == "cbrowser-t005-net-fast"
    thread.join(timeout=5)
    assert not thread.is_alive(), "slow call did not time out"
    assert time.monotonic() - started < 2.0
    assert isinstance(errors.get("slow"), DockerSandboxError)
    assert "timed out" in str(errors["slow"])
    # The failed attempt releases its subnet reservation.
    assert adapter._reserved_subnets == set()
    networks.block.set()


def test_media_network_concurrent_allocations_get_distinct_subnets(
    tmp_path: Path,
) -> None:
    client = MagicMock()
    networks = _BlockingNetworks()
    client.networks = networks
    adapter = _adapter(tmp_path, client, network_timeout=5.0)
    results: dict[str, object] = {}
    errors: dict[str, Exception] = {}

    def run(profile: str) -> None:
        try:
            results[profile] = adapter._ensure_media_network(profile)
        except Exception as exc:  # noqa: BLE001 - captured for assertion
            errors[profile] = exc

    threads = [
        threading.Thread(target=run, args=(f"p{i}",), daemon=True)
        for i in range(3)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors, errors
    assert len(results) == 3
    subnets = {
        network.attrs["Labels"]["com.cbrowser.media-subnet"]
        for network in results.values()
    }
    assert len(subnets) == 3, "concurrent allocations must not share a subnet"
    networks.block.set()


# ---------------------------------------------------------------- runner wiring

def test_runner_main_passes_deployment_id_and_validates_prefix(
    tmp_path: Path, monkeypatch
) -> None:
    import sys

    import cbrowser.supervisor.runner as runner_mod

    seen: dict[str, object] = {}

    async def fake_run_supervisor(**kwargs) -> None:
        seen.update(kwargs)

    monkeypatch.setattr(runner_mod, "run_supervisor", fake_run_supervisor)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "supervisor",
            "--data-root",
            str(tmp_path),
            "--prefix",
            "cbrowser",
            "--deployment-instance-id",
            "dep-1",
            "--docker-network-timeout",
            "7",
        ],
    )
    runner_mod.main()
    assert seen["resource_prefix"] == "cbrowser"
    assert seen["deployment_instance_id"] == "dep-1"
    assert seen["network_timeout"] == 7.0


def test_runner_main_rejects_hyphenated_prefix(tmp_path: Path, monkeypatch) -> None:
    import sys

    import cbrowser.supervisor.runner as runner_mod

    monkeypatch.setattr(
        sys,
        "argv",
        ["supervisor", "--data-root", str(tmp_path), "--prefix", "inst-b"],
    )
    with pytest.raises(ValueError, match="prefix"):
        runner_mod.main()


def test_runner_main_rejects_hyphenated_prefix_from_env(
    tmp_path: Path, monkeypatch
) -> None:
    import sys

    import cbrowser.supervisor.runner as runner_mod

    monkeypatch.setenv("CBROWSER_PREFIX", "inst-b")
    monkeypatch.setattr(
        sys, "argv", ["supervisor", "--data-root", str(tmp_path)]
    )
    with pytest.raises(ValueError, match="prefix"):
        runner_mod.main()


def test_runner_main_defaults_to_t005_prefix(
    tmp_path: Path, monkeypatch
) -> None:
    import sys

    import cbrowser.supervisor.runner as runner_mod

    seen: dict[str, object] = {}

    async def fake_run_supervisor(**kwargs) -> None:
        seen.update(kwargs)

    monkeypatch.delenv("CBROWSER_PREFIX", raising=False)
    monkeypatch.setattr(runner_mod, "run_supervisor", fake_run_supervisor)
    monkeypatch.setattr(
        sys, "argv", ["supervisor", "--data-root", str(tmp_path)]
    )
    runner_mod.main()
    # Nothing supplied: the compiled-in default deployment prefix
    # applies and is not subject to the A22 input validation.
    assert seen["resource_prefix"] == "cbrowser-t005"


def test_core_lookup_filters_by_deployment_id(tmp_path: Path) -> None:
    from cbrowser.supervisor.core import SupervisorCore

    client = MagicMock()
    adapter = _adapter(tmp_path, client, deployment_instance_id="dep-1")
    core = SupervisorCore.__new__(SupervisorCore)
    core.docker = adapter
    seen: dict[str, object] = {}

    def fake_list(*args, **kwargs):
        seen.update(kwargs)
        return []

    client.containers.list.side_effect = fake_list
    import asyncio

    result = asyncio.run(core._lookup_browser_container("p1", "inst-1"))
    assert result.outcome == "missing"
    filters = seen["filters"]["label"]
    assert "com.cbrowser.instance-id=dep-1" in filters
    assert "com.cbrowser.prefix=cbrowser-t005" in filters


def test_core_lookup_without_deployment_identity_omits_filter(
    tmp_path: Path,
) -> None:
    from cbrowser.supervisor.core import SupervisorCore

    client = MagicMock()
    adapter = _adapter(tmp_path, client)
    core = SupervisorCore.__new__(SupervisorCore)
    core.docker = adapter
    seen: dict[str, object] = {}

    def fake_list(*args, **kwargs):
        seen.update(kwargs)
        return []

    client.containers.list.side_effect = fake_list
    import asyncio

    result = asyncio.run(core._lookup_browser_container("p1", "inst-1"))
    assert result.outcome == "missing"
    filters = seen["filters"]["label"]
    assert not any("com.cbrowser.instance-id=" in label for label in filters)


# ------------------------------------------------------- runtime id channel

def test_runtime_instance_id_reads_config_channels():
    from cbrowser.supervisor.container_spec import container_runtime_instance_id

    # Stream channel: the environment variable.
    stream = SimpleNamespace(
        attrs={
            "Config": {
                "Env": ["CBROWSER_RUNTIME_INSTANCE_ID=inst-env"],
                "Entrypoint": ["python3", "-m", "x", "--instance-id", "inst-env"],
                "Cmd": [],
            }
        }
    )
    assert container_runtime_instance_id(stream) == "inst-env"
    # Browser agent environment channel.
    browser_env = SimpleNamespace(
        attrs={"Config": {"Env": ["RUNTIME_INSTANCE_ID=inst-benv"]}}
    )
    assert container_runtime_instance_id(browser_env) == "inst-benv"
    # Browser channels: gated entrypoint and command argument.
    browser = SimpleNamespace(
        attrs={
            "Config": {
                "Env": [],
                "Entrypoint": ["python3", "-m", "g", "--instance-id", "inst-ep"],
                "Cmd": ["--runtime-instance-id", "inst-ep"],
            }
        }
    )
    assert container_runtime_instance_id(browser) == "inst-ep"
    cmd_only = SimpleNamespace(
        attrs={
            "Config": {
                "Env": [],
                "Entrypoint": None,
                "Cmd": ["serve", "--runtime-instance-id", "inst-cmd"],
            }
        }
    )
    assert container_runtime_instance_id(cmd_only) == "inst-cmd"
    # List summaries carry no Config; the Command string still holds the
    # gated entrypoint arguments.
    summary = SimpleNamespace(
        attrs={"Command": "python3 -m cbrowser.supervisor.gated_entrypoint --instance-id inst-sum --role browser"}
    )
    assert container_runtime_instance_id(summary) == "inst-sum"


def test_runtime_instance_id_ignores_deployment_label():
    from cbrowser.supervisor.container_spec import container_runtime_instance_id

    # A container carrying only the deployment identity label has no
    # runtime session: the label must never be read as a runtime id.
    labelled = SimpleNamespace(
        labels={"com.cbrowser.instance-id": "dep-1"}, attrs={"Config": {}}
    )
    assert container_runtime_instance_id(labelled) is None
    assert container_runtime_instance_id(SimpleNamespace(attrs={})) is None
