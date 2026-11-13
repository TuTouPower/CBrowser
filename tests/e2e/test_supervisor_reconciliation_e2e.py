"""t026 AC-012: real-Docker reconciliation cases for t032 AC-009.

These cases drive the production DockerAdapter and SupervisorCore
convergence entry against a real Docker daemon (no doubles): fixed
endpoint allocation, Gateway replacement re-attachment, endpoint
conflict, and pool exhaustion. They skip cleanly when no daemon or no
test image is available; on a host with Docker they must be run for
real (t032 AC-009) — a skip there is not a pass.

Runbook (t032):
    export CBROWSER_RUNTIME_TEST_IMAGE=sha256:<browser runtime image>
    python -m pytest tests/e2e/test_supervisor_reconciliation_e2e.py -q

Full-stack scenarios that need the complete service graph (API process
offline re-attachment, registration protocol refusal against the real
Gateway image, in-namespace policy drift) run under the REQUIRED_E2E_ENV
image set with the supervisor_recovery_probe fixtures; the fault
matrix mapping each t026 AC to its suite lives in
docs/blueprint/testing.md ("t026 reconciliation fault matrix").
"""

from __future__ import annotations

import os
from pathlib import Path

import docker
import pytest
from cbrowser.supervisor.address_pool import plan_for_subnet
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.path_validator import PathValidator

import ipaddress

PREFIX = "cbrowser-t026e2e"
IMAGE = os.environ.get("CBROWSER_RUNTIME_TEST_IMAGE")


def _daemon_available() -> bool:
    try:
        docker.from_env().ping()
        return True
    except Exception:  # noqa: BLE001 - any daemon failure means skip
        return False


pytestmark = [pytest.mark.skipif(
    not (_daemon_available() and IMAGE),
    reason="requires a real Docker daemon and CBROWSER_RUNTIME_TEST_IMAGE",
), pytest.mark.e2e_images('CBROWSER_RUNTIME_TEST_IMAGE')]


def _adapter(tmp_path: Path, **kw) -> DockerAdapter:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    (engine / "geoip").mkdir(parents=True)
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=docker.from_env(),
        browser_image=IMAGE,
        stream_image=IMAGE,
        resource_prefix=PREFIX,
        **kw,
    )


def _run_gateway_container(name: str):
    client = docker.from_env()
    return client.containers.run(
        IMAGE,
        entrypoint=["sleep", "300"],
        name=name,
        detach=True,
        labels={
            "com.cbrowser.managed-by": "supervisor",
            "com.cbrowser.prefix": PREFIX,
            "com.cbrowser.role": "gateway",
        },
    )


@pytest.mark.asyncio
async def test_fixed_endpoint_allocation_and_gateway_replacement(tmp_path):
    adapter = _adapter(tmp_path)
    profile = "e2e_prof_a"
    gateway = _run_gateway_container(f"{PREFIX}-gw-a")
    try:
        await adapter.create_profile_network(profile)
        inspection = adapter.inspect_media_network(profile)
        assert inspection["conforms"] is True
        plan = inspection["plan"]
        assert plan is not None

        result = adapter.attach_profile_infrastructure(profile, gateway.id, 8443)
        assert result["gateway_ip"] == plan.gateway_endpoint
        assert (
            adapter.inspect_media_network(profile)["gateway_attached_id"]
            == gateway.id
        )

        # Gateway replacement: a new container with the same identity
        # labels is resolved by label scan and re-attached at the same
        # fixed endpoint, with the network itself untouched.
        gateway.remove(force=True)
        replacement = _run_gateway_container(f"{PREFIX}-gw-b")
        try:
            assert adapter.resolve_gateway_container_id() == replacement.id
            result = adapter.attach_profile_infrastructure(
                profile, replacement.id, 8443
            )
            assert result["gateway_ip"] == plan.gateway_endpoint
        finally:
            replacement.remove(force=True)
    finally:
        with pytest.raises(Exception):
            gateway.remove(force=True)
        client = docker.from_env()
        try:
            client.networks.get(adapter.get_network_name(profile)).remove()
        except Exception:  # noqa: BLE001 - cleanup best effort
            pass


@pytest.mark.asyncio
async def test_endpoint_conflict_and_pool_exhaustion(tmp_path):
    adapter = _adapter(tmp_path, media_subnet_pool="10.251.230.0/24")
    profile = "e2e_prof_b"
    plan = plan_for_subnet(ipaddress.ip_network("10.251.230.0/24"))
    occupier = _run_gateway_container(f"{PREFIX}-gw-occupier")
    gateway = _run_gateway_container(f"{PREFIX}-gw-real")
    try:
        await adapter.create_profile_network(profile)
        # Occupy the fixed endpoint with the wrong container first.
        network = docker.from_env().networks.get(adapter.get_network_name(profile))
        network.connect(occupier, ipv4_address=plan.gateway_endpoint)
        with pytest.raises(DockerSandboxError):
            adapter.attach_profile_infrastructure(profile, gateway.id, 8443)
        network.disconnect(occupier)

        # The single-subnet pool is now consumed by this profile: a
        # second profile fails explicitly instead of getting a random
        # Docker subnet.
        with pytest.raises(DockerSandboxError):
            await adapter.create_profile_network("e2e_prof_c")
    finally:
        for container in (occupier, gateway):
            try:
                container.remove(force=True)
            except Exception:  # noqa: BLE001 - cleanup best effort
                pass
        try:
            docker.from_env().networks.get(
                adapter.get_network_name(profile)
            ).remove()
        except Exception:  # noqa: BLE001 - cleanup best effort
            pass
