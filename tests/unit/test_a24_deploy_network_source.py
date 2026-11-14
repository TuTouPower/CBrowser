"""t054: deploy.sh renders the Caddyfile at deploy time via `render`.

The old applied-state protocol (`init`/`read`, rc 3 missing / rc 4
corrupt, BIND_HOST re-export) is gone: deploy.sh renders the Caddyfile
for the deploy port with a single `network_config render` call, refuses
the deploy with the CLI's exit code when rendering fails, and exports
the derived trusted proxy CIDRs (the edge subnet) instead of a bind host.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "deploy.sh"


def _text():
    return SCRIPT.read_text(encoding="utf-8")


def test_no_inline_json_template():
    text = _text()
    assert 'cat << JSON > "$DATA_ROOT/network/applied_network_version.json"' not in text
    assert '"caddyfile_sha256": ""' not in text


def test_no_inline_caddyfile_template():
    text = _text()
    assert 'cat << EOF > "$DATA_ROOT/network/Caddyfile"' not in text
    assert "default_sni 127.0.0.1" not in text


def test_no_grep_bind_host_parsing():
    text = _text()
    assert 'BIND_HOST="$(grep' not in text
    assert "cut -d'\"' -f4" not in text


def test_calls_python_network_entrypoint():
    text = _text()
    assert "-m cbrowser.network_config_cli" in text
    # t054: the only operation is `render`.
    assert 'render --network-dir "$DATA_ROOT/network"' in text
    assert 'eval "$(network_config render' in text
    assert 'init --network-dir' not in text
    assert 'read --network-dir' not in text


def test_authoritative_values_reexported():
    text = _text()
    assert 'export CBROWSER_HTTPS_PORT="$HTTPS_PORT"' in text
    # t054: the trusted proxy CIDRs are the edge subnet, derived at deploy.
    assert 'export CBROWSER_TRUSTED_PROXY_CIDRS="$CBROWSER_EDGE_SUBNET"' in text
    assert "CBROWSER_BIND_HOST" not in text


def test_render_failure_refuses_deploy_with_cli_exit_code():
    text = _text()
    assert "Refusing to deploy: network_config $op failed (exit $rc)." in text
    assert "printf 'exit %d\\n' \"$rc\"" in text
    # No missing/corrupt applied-state distinction anymore.
    assert 'case "$rc" in' not in text


def test_bash_syntax_ok():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


FAKE_DOCKER_STUB = """#!/bin/bash
echo "docker $*" >> "${FAKE_DOCKER_LOG:?}"
case "${1:-}" in
  compose) [ "${2:-}" = "version" ] && exit 0; exit 1 ;;
  ps) exit 0 ;;
  network) exit 0 ;;
  build) exit 0 ;;
  image) echo "sha256:fakeapimage" ;;
  run) exit 0 ;;
  *) exit 1 ;;
esac
"""

PY_STUB = (
    "import os\n"
    "import sys\n"
    "if \"render\" in sys.argv[1:]:\n"
    "    rc = int(os.environ.get(\"STUB_RENDER_RC\", \"2\"))\n"
    "    sys.stderr.write(\"stub: simulated cli failure rc=%d\\n\" % rc)\n"
    "    sys.exit(rc)\n"
    "sys.exit(0)\n"
)


def _run_isolated_deploy(tmp_path, render_rc):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "deploy.sh")
    # t054: deploy.sh calls the subnet-conflict helper before rendering.
    shutil.copy(ROOT / "scripts" / "check_edge_subnet.py",
                repo / "scripts" / "check_edge_subnet.py")
    net_dir = repo / "src" / "backend" / "cbrowser"
    net_dir.mkdir(parents=True)
    (net_dir / "network_config.py").write_text("", encoding="utf-8")
    dist = repo / "src" / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    for name in (
        "browser_runtime", "stream_runtime", "supervisor_runtime",
        "gateway_runtime", "api_runtime", "proxy_forwarder_runtime",
    ):
        dockerfile_dir = repo / "config" / "docker" / name
        dockerfile_dir.mkdir(parents=True)
        (dockerfile_dir / "Dockerfile").write_text("", encoding="utf-8")
        (dockerfile_dir / "Dockerfile.dockerignore").write_text("", encoding="utf-8")

    bins = tmp_path / "bins"
    bins.mkdir()
    docker = bins / "docker"
    docker.write_text(FAKE_DOCKER_STUB, encoding="utf-8")
    docker.chmod(0o755)
    stub = bins / "stub_python"
    stub.write_text("#!" + sys.executable + "\n" + PY_STUB, encoding="utf-8")
    stub.chmod(0o755)

    secrets = tmp_path / "secrets"
    secrets.mkdir()
    for name in (
        "admin_password", "supervisor_key", "agent_key",
        "gateway_key", "gateway_api_key",
    ):
        (secrets / name).write_text("sentinel\n", encoding="utf-8")

    deploy = tmp_path / "deploy"
    docker_log = tmp_path / "docker.log"
    env = {
        "PATH": f"{bins}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "FAKE_DOCKER_LOG": str(docker_log),
        # The stub python prints nothing for `-c`, so the port default
        # derivation comes out empty; the deploy port is set explicitly.
        "CBROWSER_HTTPS_PORT": "56661",
        "CBROWSER_PYTHON": str(stub),
        "CBROWSER_DEPLOY_DIR": str(deploy),
        "CBROWSER_SECRETS_DIR": str(secrets),
        "CBROWSER_DATA_ROOT": str(tmp_path / "data"),
        "CBROWSER_RELEASE_ID": "a24-rc-guard",
        "STUB_RENDER_RC": str(render_rc),
        "PYTHONPATH": str(repo / "src" / "backend"),
    }
    result = subprocess.run(
        ["bash", "scripts/deploy.sh", "deploy"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, docker_log, deploy


def test_render_failure_refuses_deploy_and_publishes_nothing(tmp_path):
    # A render failure (exit 2 here) refuses the deploy with the CLI's
    # exit code; no container is started and no release is recorded.
    result, docker_log, deploy = _run_isolated_deploy(tmp_path, 2)
    assert result.returncode == 2, result.stderr
    assert "Refusing to deploy" in result.stderr
    log = docker_log.read_text(encoding="utf-8") if docker_log.exists() else ""
    assert "compose up" not in log
    assert not deploy.exists()
    assert not (tmp_path / "data" / "network" / "Caddyfile").exists()
