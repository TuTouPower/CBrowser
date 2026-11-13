"""Observable boundary regressions for t060 gate infrastructure."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from frontend_app_probe.harness import FrontendAppTopologyHarness

from scripts import automation_probe_evidence as evidence
from scripts import verify_image_packages as packages

ROOT = Path(__file__).resolve().parents[2]


def _hygiene():
    spec = importlib.util.spec_from_file_location(
        "hygiene_t060", ROOT / "tests/unit/test_repo_hygiene.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("suffix", ["", "'", '"', "/project"])
@pytest.mark.parametrize(
    "home",
    [
        "/".join(["", "Users", "developer"]),  # noqa: FLY002 - split privacy sample
        "/".join(["", "home", "developer"]),  # noqa: FLY002 - split privacy sample
        "C:\\" + "\\".join(["Users", "developer"]),  # noqa: FLY002 - split privacy sample
    ],
)
def test_privacy_detects_terminal_username(home, suffix):
    assert _hygiene().find_developer_path_leaks(home + suffix)


def test_privacy_enumerates_untracked_but_not_ignored(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("ignored.md\n")
    (tmp_path / "new.md").write_text("new")
    (tmp_path / "ignored.md").write_text("ignored")
    module = _hygiene()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    assert "new.md" in module.tracked_files()
    assert "ignored.md" not in module.tracked_files()


def test_invalid_marker_fails_closed():
    with pytest.raises(ValueError):
        packages.normalise(["foo==1; this is not a marker"])


def test_marker_target_has_no_host_fallback():
    from packaging.markers import default_environment

    assert default_environment().keys() <= packages.TARGET_ENV.keys()


def test_node_strict_greater_bound_rejects_equal(tmp_path):
    version = subprocess.check_output(
        ["node", "-p", "process.versions.node"], text=True
    ).strip()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "check_node.mjs").write_bytes(
        (ROOT / "src/frontend/scripts/check_node.mjs").read_bytes()
    )
    (tmp_path / "package.json").write_text(
        json.dumps({"engines": {"node": ">" + version}})
    )
    result = subprocess.run(
        ["node", str(scripts / "check_node.mjs")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


@pytest.mark.parametrize(
    "identity",
    [
        {"id": "tag", "os": "linux", "architecture": "arm64"},
        {"id": "sha256:" + "a" * 64, "os": "linux", "architecture": "amd64"},
    ],
)
def test_evidence_cli_rejects_forged_image(tmp_path, identity):
    junit = tmp_path / "probe.xml"
    junit.write_text(
        "<testsuites><testsuite>"
        + "".join(
            f'<testcase classname="{node.split("::")[0][:-3].replace("/", ".")}" name="{node.split("::")[1]}"/>'
            for node in evidence.REQUIRED_PROBE_NODE_IDS
        )
        + "</testsuite></testsuites>"
    )
    image = tmp_path / "image.json"
    image.write_text(json.dumps(identity))
    selected = tmp_path / "selected.txt"
    selected.write_text("\n".join(evidence.REQUIRED_PROBE_NODE_IDS))
    result = evidence.main(
        [
            "--junit",
            str(junit),
            "--image-json",
            str(image),
            "--selected",
            str(selected),
            "--exit-code",
            "0",
            "--output",
            str(tmp_path / "result.json"),
        ]
    )
    assert result == 1


def _harness(api):
    harness = object.__new__(FrontendAppTopologyHarness)
    harness.docker_client = SimpleNamespace(api=api)
    return harness


def test_stop_probe_reports_stream_surviving_browser():
    api = SimpleNamespace(
        containers=lambda **kw: [
            {"Labels": {"com.cbrowser.role": "stream"}, "Names": ["/stream"]}
        ]
    )
    harness = _harness(api)
    assert harness.container_presence("p1") == {"browser": False, "stream": True}
    assert not harness.runtime_containers_gone("p1")


def test_stop_probe_propagates_docker_error():
    def fail(**kw):
        raise RuntimeError("Docker API unavailable")

    with pytest.raises(RuntimeError, match="Docker API"):
        _harness(SimpleNamespace(containers=fail)).runtime_containers_gone("p1")


def test_e2e_marker_limits_required_images():
    from e2e_env import required_e2e_names

    marker = SimpleNamespace(args=("CBROWSER_RUNTIME_TEST_IMAGE",))
    item = SimpleNamespace(iter_markers=lambda name: [marker])
    assert required_e2e_names([item]) == {
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        "CBROWSER_RUNTIME_GEOIP_CACHE",
    }


def test_e2e_unmarked_cases_require_all_images():
    from e2e_env import REQUIRED_E2E_ENV, required_e2e_names

    item = SimpleNamespace(iter_markers=lambda name: [])
    assert required_e2e_names([item]) == set(REQUIRED_E2E_ENV)


@pytest.mark.parametrize(
    "image",
    [
        "api_runtime",
        "gateway_runtime",
        "supervisor_runtime",
        "browser_runtime",
        "stream_runtime",
    ],
)
def test_all_five_contexts_exclude_bytecode(image):
    spec = importlib.util.spec_from_file_location(
        "context_t060", ROOT / "tests/unit/test_docker_build_contexts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rules = module.Dockerignore(
        (ROOT / "config/docker" / image / "Dockerfile.dockerignore").read_text()
    )
    for package in (
        "supervisor",
        "services",
        "gateway",
        "domain",
        "runtime_agent",
        "stream_agent",
        "font_sets",
    ):
        for suffix in ("__pycache__/module.py", "__pycache__/module.pyc", "module.pyc"):
            assert not rules.admits(f"src/backend/cbrowser/{package}/{suffix}")


def test_supervisor_services_context_equals_copy_sources():
    spec = importlib.util.spec_from_file_location(
        "context_t060", ROOT / "tests/unit/test_docker_build_contexts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dockerfile = ROOT / "config/docker/supervisor_runtime/Dockerfile"
    copied = {
        source for source in module._copy_sources(dockerfile) if "/services/" in source
    }
    rules = module.Dockerignore(
        dockerfile.with_name("Dockerfile.dockerignore").read_text()
    )
    candidates = {
        str(p.relative_to(ROOT))
        for p in (ROOT / "src/backend/cbrowser/services").glob("*.py")
    }
    assert {p for p in candidates if rules.admits(p)} == copied


def test_gate_cli_creation_disables_host_proxy_injection():
    from scripts.gate_docker import labelled_arguments

    command = labelled_arguments(["run", "--rm", "image", "true"], "a" * 32)
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        assert f"{key}=" in command
    assert "NO_PROXY=*" in command


def test_gate_sdk_creation_disables_config_proxy_injection(monkeypatch):
    import docker
    from docker.utils.proxy import ProxyConfig

    client = docker.APIClient(base_url="http://127.0.0.1:1", version="1.45")
    client._proxy_configs = ProxyConfig.from_dict(
        {
            "httpProxy": "http://proxy.invalid:3128",
            "httpsProxy": "http://proxy.invalid:3128",
        }
    )
    monkeypatch.setattr(
        client, "create_container_from_config", lambda config, *args: config
    )
    try:
        config = client.create_container(
            "fixture-image", environment={"TEST_VALUE": "kept"}
        )
    finally:
        client.close()
    assert "TEST_VALUE=kept" in config["Env"]
    assert not any(
        value.lower().startswith(("http_proxy=", "https_proxy="))
        for value in config["Env"]
    )


def test_node_rejects_26_0_0_for_exclusive_bound(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    checker = scripts / "check_node.mjs"
    checker.write_bytes((ROOT / "src/frontend/scripts/check_node.mjs").read_bytes())
    (tmp_path / "package.json").write_text(json.dumps({"engines": {"node": ">26.0.0"}}))
    code = (
        "Object.defineProperty(process.versions, 'node', {value:'26.0.0'}); await import("
        + json.dumps(checker.as_uri())
        + ");"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "26.0.0" in result.stderr


def test_image_package_cli_rejects_invalid_marker(tmp_path, monkeypatch):
    import sys

    requirements = tmp_path / "requirements.txt"
    requirements.write_text("foo==1; this is not a marker")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_image_packages",
            "--image",
            "fixture",
            "--requirements",
            str(requirements),
        ],
    )
    monkeypatch.setattr(
        packages, "image_environment", lambda image: dict(packages.TARGET_ENV)
    )
    monkeypatch.setattr(
        packages,
        "image_freeze",
        lambda image: pytest.fail(
            "invalid marker must abort before package enumeration"
        ),
    )
    assert packages.main() == 1


@pytest.mark.asyncio
async def test_local_topology_profile_does_not_require_public_geoip(monkeypatch):
    """Session/media probes must not spend Browser readiness on IP echo sites."""
    from unittest.mock import AsyncMock, Mock

    import httpx
    from gateway_probe.topology import GatewayTopologyHarness

    requests = []

    def respond(request):
        if request.url.path == "/api/v1/profiles":
            requests.append(json.loads(request.content))
            return httpx.Response(201, json={"id": "profile", "display_number": 1})
        if request.url.path == "/supervisor/v1/profiles/start":
            return httpx.Response(200, json={
                "runtime_instance_id": "instance", "browser_container": "browser",
                "stream_container": "stream", "udp_mux_port": 30000,
            })
        return httpx.Response(200, json={"observed_state": "running"})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        "gateway_probe.topology.httpx.AsyncClient",
        lambda **kwargs: client_type(**kwargs, transport=httpx.MockTransport(respond)),
    )
    harness = object.__new__(GatewayTopologyHarness)
    harness.gateway_container = Mock(status="running", attrs={
        "NetworkSettings": {"Ports": {"18080/tcp": [{"HostPort": "18080"}]}}
    })
    harness.login_api = AsyncMock(return_value={})
    harness.origin = "https://localhost"
    harness.supervisor_url = "http://supervisor"
    harness.api_internal_url = "http://api"
    harness.keys = {"supervisor": "fixture", "gateway": "fixture", "gateway_api": "fixture"}
    await harness.create_and_start_profile("session")
    assert requests[0]["geoip"] is False
    assert "set_google_default" not in requests[0]


def test_privacy_distinguishes_url_path_segments_from_absolute_homes():
    module = _hygiene()
    url = "https://github.com/example/repo/blob/main/apps/web/src/routes/home/components/input.tsx"
    assert module.find_developer_path_leaks(url) == []
    home = "/".join(["", "Users", "developer", "repo"])  # noqa: FLY002 - split privacy sample
    for authority in ("", "localhost"):
        assert module.find_developer_path_leaks("file://" + authority + home)
    assert module.find_developer_path_leaks("worktree=" + home)
