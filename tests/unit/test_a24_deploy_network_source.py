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
    assert 'init --network-dir "$DATA_ROOT/network"' in text
    assert 'read --network-dir "$DATA_ROOT/network"' in text
    assert 'eval "$(network_config read' in text


def test_authoritative_values_reexported():
    text = _text()
    assert 'export CBROWSER_HTTPS_PORT="$HTTPS_PORT"' in text
    assert 'export CBROWSER_BIND_HOST="$BIND_HOST"' in text


def test_bash_syntax_ok():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


FAKE_DOCKER_STUB = """#!/bin/bash
echo "docker $*" >> "${FAKE_DOCKER_LOG:?}"
case "${1:-}" in
  compose) [ "${2:-}" = "version" ] && exit 0; exit 1 ;;
  ps) exit 0 ;;
  *) exit 1 ;;
esac
"""

PY_STUB = (
    "import os\n"
    "import sys\n"
    "if \"read\" in sys.argv[1:]:\n"
    "    rc = int(os.environ.get(\"STUB_READ_RC\", \"4\"))\n"
    "    sys.stderr.write(\"stub: simulated cli failure rc=%d\\n\" % rc)\n"
    "    sys.exit(rc)\n"
    "sys.exit(0)\n"
)


def _run_isolated_deploy(tmp_path, read_rc):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "deploy.sh")
    net_dir = repo / "src" / "backend" / "cbrowser"
    net_dir.mkdir(parents=True)
    (net_dir / "network_config.py").write_text("", encoding="utf-8")
    dist = repo / "src" / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    for name in (
        "browser_runtime", "stream_runtime", "supervisor_runtime",
        "gateway_runtime", "api_runtime",
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
        "CBROWSER_PYTHON": str(stub),
        "CBROWSER_DEPLOY_DIR": str(deploy),
        "CBROWSER_SECRETS_DIR": str(secrets),
        "CBROWSER_DATA_ROOT": str(tmp_path / "data"),
        "CBROWSER_RELEASE_ID": "a24-rc-guard",
        "STUB_READ_RC": str(read_rc),
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


def test_read_corrupt_rc_not_swallowed_and_no_publish(tmp_path):
    result, docker_log, deploy = _run_isolated_deploy(tmp_path, 4)
    assert result.returncode == 4, result.stderr
    assert "corrupt" in result.stderr.lower()
    assert "is missing" not in result.stderr.lower()
    log = docker_log.read_text(encoding="utf-8") if docker_log.exists() else ""
    assert "compose up" not in log
    assert "docker build" not in log
    assert not deploy.exists()


def test_read_missing_rc_not_swallowed_and_no_publish(tmp_path):
    result, docker_log, deploy = _run_isolated_deploy(tmp_path, 3)
    assert result.returncode == 3, result.stderr
    assert "missing" in result.stderr.lower()
    assert "is corrupt" not in result.stderr.lower()
    log = docker_log.read_text(encoding="utf-8") if docker_log.exists() else ""
    assert "compose up" not in log
    assert "docker build" not in log
    assert not deploy.exists()


def test_network_config_rc_is_checked_and_differentiated():
    text = _text()
    assert 'if read_output="$(PYTHONPATH=' in text
    assert "rc=$?" in text
    assert 'case "$rc" in' in text
    assert "printf 'exit %d" in text
    assert "missing" in text.lower()
    assert "corrupt" in text.lower()
