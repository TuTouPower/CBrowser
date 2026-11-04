"""t027 release-controller tests (AC-001..AC-009, cloud side).

The production deploy script is executed for real against a fake Docker
CLI in a scratch copy of the repository tree: the fake records every
invocation, serves deterministic image IDs derived from Dockerfile
content, and answers compose exec with canned readiness reports.  Real
Docker behaviour is exercised only in t032; nothing here claims it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ADMIN_SENTINEL = "ADMIN-SENTINEL-VALUE-9f27"

FAKE_DOCKER = r"""#!/bin/bash
set -u
LOG="${FAKE_DOCKER_LOG:?}"
STATE="${FAKE_DOCKER_STATE:?}"
mkdir -p "$STATE/images"
echo "docker $*" >> "$LOG"
san() { printf '%s' "$1" | tr '/:' '__'; }
cmd="${1:-}"; if [ $# -gt 0 ]; then shift; fi
case "$cmd" in
  build)
    tag=""; df=""
    while [ $# -gt 0 ]; do
      case "$1" in
        -t) tag="$2"; shift 2;;
        -f) df="$2"; shift 2;;
        *) shift;;
      esac
    done
    echo "build tag=$tag dockerfile=$df" >> "$LOG.builds"
    if [ "${FAKE_FAIL_BUILD:-0}" = "1" ]; then echo "build failed" >&2; exit 1; fi
    id="sha256:$(sha256sum "$df" | awk '{print $1}')"
    printf '%s' "$id" > "$STATE/images/$(san "$tag")"
    ;;
  pull)
    ref="$1"
    id="sha256:$(printf '%s' "pulled:$ref" | sha256sum | awk '{print $1}')"
    printf '%s' "$id" > "$STATE/images/$(san "$ref")"
    ;;
  image)
    if [ $# -gt 0 ]; then shift; fi
    fmt=""; ref=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --format) fmt="$2"; shift 2;;
        *) ref="$1"; shift;;
      esac
    done
    f="$STATE/images/$(san "$ref")"
    if [ ! -f "$f" ]; then echo "Error: No such image: $ref" >&2; exit 1; fi
    if [ -n "$fmt" ]; then cat "$f"; echo; fi
    ;;
  ps)
    # Rows are "name<TAB>compose-project<TAB>prefix-label".
    if [ -n "${FAKE_PS_ROWS:-}" ]; then
      printf '%s\n' "$FAKE_PS_ROWS"
    elif [ -n "${FAKE_CONFLICT_PROJECT:-}" ]; then
      printf 'cbrowser-gateway\t%s\tcbrowser\n' "$FAKE_CONFLICT_PROJECT"
    elif [ -n "${FAKE_OWN_PROJECT:-}" ]; then
      printf 'cbrowser-api\t%s\tcbrowser\n' "$FAKE_OWN_PROJECT"
    fi
    ;;
  compose)
    while [ $# -gt 0 ]; do
      case "$1" in
        --env-file) echo "compose-env $2" >> "$LOG.compose"; shift 2;;
        -f) shift 2;;
        *) break;;
      esac
    done
    sub="${1:-}"; if [ $# -gt 0 ]; then shift; fi
    case "$sub" in
      version) echo "Docker Compose version v2.29.0";;
      up)
        echo "up $*" >> "$LOG.compose"
        if [ "${FAKE_FAIL_UP:-0}" = "1" ]; then echo "service unhealthy" >&2; exit 1; fi
        ;;
      exec)
        cat >/dev/null
        echo "exec $*" >> "$LOG.compose"
        case "${FAKE_READINESS:-ready}" in
          ready)
            printf '%s\n' '{"ready": true, "reason": null, "profiles": [{"profile_id": "p1", "ready": true, "diagnostics": []}]}'
            ;;
          unready)
            printf '%s\n' '{"ready": false, "reason": "profiles_not_converged", "profiles": [{"profile_id": "p-unready", "ready": false, "diagnostics": ["browser_not_registered"]}]}'
            exit 1
            ;;
        esac
        ;;
      *) echo "unsupported compose subcommand: $sub" >&2; exit 1;;
    esac
    ;;
  *) echo "unsupported docker command: $cmd" >&2; exit 1;;
esac
exit 0
"""


def _copy_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _make_fake_repo(tmp_path: Path, *, with_admin: bool = True) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "deploy_v2.sh", repo / "scripts" / "deploy_v2.sh")
    shutil.copy(
        ROOT / "scripts" / "supervisor_readiness_probe.py",
        repo / "scripts" / "supervisor_readiness_probe.py",
    )
    shutil.copy(ROOT / "compose.yaml", repo / "compose.yaml")
    _copy_tree(ROOT / "config" / "docker", repo / "config" / "docker")
    caddy_dir = repo / "config" / "deploy" / "caddy"
    caddy_dir.mkdir(parents=True)
    shutil.copy(
        ROOT / "config" / "deploy" / "caddy" / "Caddyfile", caddy_dir / "Caddyfile"
    )
    _copy_tree(
        ROOT / "src" / "backend" / "migrations",
        repo / "src" / "backend" / "migrations",
    )
    dist = repo / "src" / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (dist / "app.js").write_text("console.log('x')", encoding="utf-8")
    secrets = repo / "config" / "deploy" / "secrets"
    secrets.mkdir(parents=True)
    if with_admin:
        admin = secrets / "admin_password"
        admin.write_text(ADMIN_SENTINEL + "\n", encoding="utf-8")
        admin.chmod(0o600)
    return repo


def _make_fake_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(0o755)
    return bin_dir


def _run(
    repo: Path,
    bin_dir: Path,
    *args: str,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    state = repo / ".fake-state"
    env = {
        "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(repo),
        "FAKE_DOCKER_LOG": str(state / "docker.log"),
        "FAKE_DOCKER_STATE": str(state),
        "FAKE_OWN_PROJECT": "cbrowser",
    }
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", "scripts/deploy_v2.sh", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _deploy(
    repo: Path, bin_dir: Path, release_id: str, **env_extra: str
) -> subprocess.CompletedProcess[str]:
    return _run(
        repo, bin_dir, "deploy", env_extra={"CBROWSER_RELEASE_ID": release_id, **env_extra}
    )


def _manifest(repo: Path, release_id: str) -> dict:
    return json.loads(
        (repo / "config" / "deploy" / "releases" / f"{release_id}.json").read_text(
            encoding="utf-8"
        )
    )


def _pointer(repo: Path, name: str) -> str:
    path = repo / "config" / "deploy" / name
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _compose_log(repo: Path) -> str:
    path = repo / ".fake-state" / "docker.log.compose"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _docker_log(repo: Path) -> str:
    path = repo / ".fake-state" / "docker.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _builds(repo: Path) -> list[str]:
    path = repo / ".fake-state" / "docker.log.builds"
    if not path.exists():
        return []
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_deploy_success_builds_once_and_pins_everything(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    result = _deploy(repo, bin_dir, "rel-001")
    assert result.returncode == 0, result.stderr

    builds = _builds(repo)
    assert len(builds) == 5, builds
    dockerfiles = sorted(line.rsplit("dockerfile=", 1)[1] for line in builds)
    assert dockerfiles == [
        "config/docker/api_runtime/Dockerfile",
        "config/docker/browser_runtime/Dockerfile",
        "config/docker/gateway_runtime/Dockerfile",
        "config/docker/stream_runtime/Dockerfile",
        "config/docker/supervisor_runtime/Dockerfile",
    ]

    manifest = _manifest(repo, "rel-001")
    assert sorted(manifest["images"]) == [
        "api",
        "browser",
        "caddy",
        "gateway",
        "stream",
        "supervisor",
    ]
    assert all(v.startswith("sha256:") for v in manifest["images"].values())
    expected_api = "sha256:" + hashlib.sha256(
        (ROOT / "config/docker/api_runtime/Dockerfile").read_bytes()
    ).hexdigest()
    assert manifest["images"]["api"] == expected_api
    assert manifest["compose_sha256"] == hashlib.sha256(
        (ROOT / "compose.yaml").read_bytes()
    ).hexdigest()
    assert manifest["migration_version"] == "0008_artifact_delete_intent"
    assert manifest["capabilities"]["readiness"] is True

    env_text = (
        repo / "config" / "deploy" / "releases" / "rel-001.env"
    ).read_text(encoding="utf-8")
    for var in (
        "CBROWSER_API_IMAGE",
        "CBROWSER_GATEWAY_IMAGE",
        "CBROWSER_SUPERVISOR_IMAGE",
        "CBROWSER_BROWSER_IMAGE",
        "CBROWSER_STREAM_IMAGE",
        "CBROWSER_CADDY_IMAGE",
    ):
        assert f"{var}=sha256:" in env_text

    assert _pointer(repo, "current_release") == "rel-001"
    assert _pointer(repo, "previous_release") == ""

    compose_log = _compose_log(repo)
    assert "up -d --no-build --wait" in compose_log
    assert "exec -T supervisor python3 - verify" in compose_log
    assert "restart" not in _docker_log(repo)

    # No secret material anywhere in the output or recorded release files.
    internal_values = [
        (repo / "config" / "deploy" / "secrets" / name).read_text(encoding="utf-8").strip()
        for name in ("supervisor_key", "agent_key", "gateway_key", "gateway_api_key")
    ]
    haystacks = result.stdout + result.stderr + env_text + json.dumps(manifest)
    assert ADMIN_SENTINEL not in haystacks
    for value in internal_values:
        assert value and value not in haystacks


def test_internal_secrets_generated_0600(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    result = _deploy(repo, bin_dir, "rel-001")
    assert result.returncode == 0, result.stderr
    secrets = repo / "config" / "deploy" / "secrets"
    for name in (
        "supervisor_key",
        "agent_key",
        "gateway_key",
        "gateway_api_key",
        "admin_password",
    ):
        mode = stat.S_IMODE((secrets / name).stat().st_mode)
        assert mode == 0o600, f"{name}: mode {oct(mode)}"


def test_missing_admin_password_fails_and_lists_missing(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path, with_admin=False)
    bin_dir = _make_fake_bin(tmp_path)
    result = _deploy(repo, bin_dir, "rel-001")
    assert result.returncode != 0
    assert "admin password" in result.stderr
    assert _builds(repo) == []
    assert not (repo / "config" / "deploy" / "releases").exists()


def test_readiness_failure_keeps_previous_release(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    result = _deploy(repo, bin_dir, "rel-002", FAKE_READINESS="unready")
    assert result.returncode != 0
    assert "p-unready" in result.stdout  # per-Profile diagnostics surfaced
    assert "browser_not_registered" in result.stdout
    assert _pointer(repo, "current_release") == "rel-001"
    # The failed release manifest exists for forensics but never activated,
    # and the previous release's files were not overwritten.
    assert _manifest(repo, "rel-001")["release_id"] == "rel-001"


def test_up_failure_keeps_previous_release(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    result = _deploy(repo, bin_dir, "rel-002", FAKE_FAIL_UP="1")
    assert result.returncode != 0
    assert _pointer(repo, "current_release") == "rel-001"


def test_repeat_deploy_same_config_is_idempotent(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    first, second = _manifest(repo, "rel-001"), _manifest(repo, "rel-002")
    for key in ("images", "compose_sha256", "caddyfile_sha256", "frontend_sha256", "migration_version"):
        assert first[key] == second[key], key
    assert "restart" not in _docker_log(repo)
    assert _pointer(repo, "current_release") == "rel-002"
    assert _pointer(repo, "previous_release") == "rel-001"


def test_prefix_conflict_refused_before_build(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    result = _deploy(repo, bin_dir, "rel-001", FAKE_CONFLICT_PROJECT="other-instance")
    assert result.returncode != 0
    assert "prefix" in result.stderr
    assert _builds(repo) == []


def test_rollback_success_redeploys_previous_and_verifies(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode == 0, result.stderr
    assert _pointer(repo, "current_release") == "rel-001"
    assert _pointer(repo, "previous_release") == "rel-002"
    env_lines = [
        line for line in _compose_log(repo).splitlines() if line.startswith("compose-env")
    ]
    assert env_lines[-1].endswith("rel-001.env")


def _deploy_two_then_edit_manifest(
    tmp_path: Path, edit: "callable"
) -> tuple[Path, Path]:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    manifest_path = repo / "config" / "deploy" / "releases" / "rel-001.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    edit(manifest)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return repo, bin_dir


def test_rollback_refuses_lower_migration(tmp_path: Path) -> None:
    def edit(manifest: dict) -> None:
        manifest["migration_version"] = "0001_initial_schema"

    repo, bin_dir = _deploy_two_then_edit_manifest(tmp_path, edit)
    ups_before = _compose_log(repo).count("up -d")
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode != 0
    assert "migration" in result.stderr
    assert _compose_log(repo).count("up -d") == ups_before
    assert _pointer(repo, "current_release") == "rel-002"


def test_rollback_refuses_without_readiness_capability(tmp_path: Path) -> None:
    def edit(manifest: dict) -> None:
        manifest["capabilities"]["readiness"] = False

    repo, bin_dir = _deploy_two_then_edit_manifest(tmp_path, edit)
    ups_before = _compose_log(repo).count("up -d")
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode != 0
    assert "readiness" in result.stderr
    assert _compose_log(repo).count("up -d") == ups_before
    assert _pointer(repo, "current_release") == "rel-002"


def _deploy_instance_b(repo: Path, bin_dir: Path, release_id: str) -> subprocess.CompletedProcess[str]:
    secrets_b = repo / "secrets-b"
    secrets_b.mkdir(parents=True, exist_ok=True)
    admin = secrets_b / "admin_password"
    admin.write_text(ADMIN_SENTINEL + "\n", encoding="utf-8")
    admin.chmod(0o600)
    return _run(
        repo,
        bin_dir,
        "deploy",
        env_extra={
            "CBROWSER_RELEASE_ID": release_id,
            "CBROWSER_COMPOSE_PROJECT": "inst-b",
            "CBROWSER_PREFIX": "inst-b",
            "CBROWSER_DATA_ROOT": str(repo / "data-b"),
            "CBROWSER_SECRETS_DIR": str(secrets_b),
        },
    )


def test_rollback_adopts_target_release_identity(tmp_path: Path) -> None:
    """Review f001: compose interpolation prefers the shell environment
    over --env-file, so rollback must adopt the target release's recorded
    identity even when the caller's shell holds another instance's (or
    the default) values."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy_instance_b(repo, bin_dir, "b-001").returncode == 0
    assert _deploy_instance_b(repo, bin_dir, "b-002").returncode == 0
    rows = "inst-b-gateway\tinst-b\tinst-b"
    result = _run(
        repo,
        bin_dir,
        "rollback",
        env_extra={"CBROWSER_PREFIX": "cbrowser", "FAKE_PS_ROWS": rows},
    )
    assert result.returncode == 0, result.stderr
    assert _pointer(repo, "current_release") == "b-001"


def test_rollback_conflict_checked_against_release_prefix(tmp_path: Path) -> None:
    """The prefix-conflict check in a rollback runs against the target
    release's prefix, not the caller's shell prefix (f001/f004)."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy_instance_b(repo, bin_dir, "b-001").returncode == 0
    assert _deploy_instance_b(repo, bin_dir, "b-002").returncode == 0
    rows = "inst-b-supervisor\tother-proj\tinst-b"
    result = _run(
        repo,
        bin_dir,
        "rollback",
        env_extra={"CBROWSER_PREFIX": "cbrowser", "FAKE_PS_ROWS": rows},
    )
    assert result.returncode != 0
    assert "prefix" in result.stderr
    assert _pointer(repo, "current_release") == "b-002"


def test_rollback_refuses_when_failed_deploy_raised_db_version(
    tmp_path: Path,
) -> None:
    """Review f003: the API migrates at startup, so a deploy that came up
    and then failed readiness has already raised the live database
    version; rolling back below that applied version must be refused
    even when the current release manifest is lower."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0

    versions = repo / "src" / "backend" / "migrations" / "versions"
    drill = versions / "0009_drill.py"
    drill.write_text(
        'revision = "0009_drill"\ndown_revision = "0008_artifact_delete_intent"\n',
        encoding="utf-8",
    )
    failed = _deploy(repo, bin_dir, "rel-002", FAKE_READINESS="unready")
    assert failed.returncode != 0
    assert _pointer(repo, "current_release") == "rel-001"
    applied = repo / "config" / "deploy" / "applied_migration_version"
    assert applied.read_text(encoding="utf-8").strip() == "0009_drill"

    drill.unlink()
    assert _deploy(repo, bin_dir, "rel-003").returncode == 0
    assert _pointer(repo, "current_release") == "rel-003"
    ups_before = _compose_log(repo).count("up -d")
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode != 0
    assert "0009_drill" in result.stderr
    assert _compose_log(repo).count("up -d") == ups_before
    assert _pointer(repo, "current_release") == "rel-003"


def test_instance_identity_parameterized_and_independent(
    tmp_path: Path,
) -> None:
    """AC-008 / test f001: a fully parameterized instance deploys with
    its identity recorded in the manifest and keeps pointers independent
    of the default instance (separate deploy dir)."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    secrets_b = repo / "secrets-b"
    secrets_b.mkdir(parents=True, exist_ok=True)
    admin = secrets_b / "admin_password"
    admin.write_text(ADMIN_SENTINEL + "\n", encoding="utf-8")
    admin.chmod(0o600)
    deploy_dir_b = repo / "config" / "deploy-b"
    result_b = _run(
        repo,
        bin_dir,
        "deploy",
        env_extra={
            "CBROWSER_RELEASE_ID": "b-001",
            "CBROWSER_COMPOSE_PROJECT": "inst-b",
            "CBROWSER_PREFIX": "inst-b",
            "CBROWSER_HTTPS_PORT": "56662",
            "CBROWSER_DATA_ROOT": str(repo / "data-b"),
            "CBROWSER_SECRETS_DIR": str(secrets_b),
            "CBROWSER_DEPLOY_DIR": str(deploy_dir_b),
        },
    )
    assert result_b.returncode == 0, result_b.stderr
    manifest_b = json.loads(
        (deploy_dir_b / "releases" / "b-001.json").read_text(encoding="utf-8")
    )
    assert manifest_b["instance"] == {
        "project": "inst-b",
        "prefix": "inst-b",
        "https_port": 56662,
    }
    env_b = (deploy_dir_b / "releases" / "b-001.env").read_text(encoding="utf-8")
    assert f"CBROWSER_DATA_ROOT={repo}/data-b" in env_b
    assert f"CBROWSER_SECRETS_DIR={secrets_b}" in env_b
    assert (deploy_dir_b / "current_release").read_text().strip() == "b-001"
    # The internal keys must actually be generated into the parameterized
    # secrets dir (test f007), not only recorded there in the env file.
    for name in ("supervisor_key", "agent_key", "gateway_key", "gateway_api_key"):
        key_file = secrets_b / name
        assert key_file.is_file(), name
        assert stat.S_IMODE(key_file.stat().st_mode) == 0o600, name

    # The default instance deploys independently; neither pointer moves.
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    assert _pointer(repo, "current_release") == "rel-001"
    assert (deploy_dir_b / "current_release").read_text().strip() == "b-001"


def test_caddy_fingerprints_recorded_and_change_sensitive(
    tmp_path: Path,
) -> None:
    """AC-005 / test f002: the release env carries the real Caddyfile and
    frontend fingerprints; changing the Caddyfile changes exactly that
    fingerprint on the next release while image IDs stay stable."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0

    def _env(release_id: str) -> dict[str, str]:
        text = (
            repo / "config" / "deploy" / "releases" / f"{release_id}.env"
        ).read_text(encoding="utf-8")
        return dict(
            line.split("=", 1) for line in text.splitlines() if "=" in line
        )

    env1 = _env("rel-001")
    expected_caddy = hashlib.sha256(
        (repo / "config" / "deploy" / "caddy" / "Caddyfile").read_bytes()
    ).hexdigest()
    assert env1["CBROWSER_CADDYFILE_SHA256"] == expected_caddy
    dist = repo / "src" / "frontend" / "dist"
    listing = "".join(
        f"{path.relative_to(dist)} {hashlib.sha256(path.read_bytes()).hexdigest()}\n"
        for path in sorted(dist.rglob("*"))
        if path.is_file()
    )
    expected_frontend = hashlib.sha256(listing.encode()).hexdigest()
    assert env1["CBROWSER_FRONTEND_SHA256"] == expected_frontend

    caddyfile = repo / "config" / "deploy" / "caddy" / "Caddyfile"
    caddyfile.write_text(
        caddyfile.read_text(encoding="utf-8") + "\n# drill change\n",
        encoding="utf-8",
    )
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    env2 = _env("rel-002")
    assert env2["CBROWSER_CADDYFILE_SHA256"] != env1["CBROWSER_CADDYFILE_SHA256"]
    assert env2["CBROWSER_FRONTEND_SHA256"] == env1["CBROWSER_FRONTEND_SHA256"]
    assert env2["CBROWSER_API_IMAGE"] == env1["CBROWSER_API_IMAGE"]


def test_rollback_preserves_profile_data_and_database(tmp_path: Path) -> None:
    """AC-006 / test f003: rollback never deletes Browser/Profile data
    or the database."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    data_root = repo / "data" / "v2"
    profile_file = data_root / "profiles" / "p1" / "profile" / "Cookies"
    profile_file.parent.mkdir(parents=True, exist_ok=True)
    profile_file.write_text("cookie-bytes", encoding="utf-8")
    db_file = data_root / "cbrowser.db"
    db_file.write_text("db-bytes", encoding="utf-8")
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode == 0, result.stderr
    assert profile_file.read_text(encoding="utf-8") == "cookie-bytes"
    assert db_file.read_text(encoding="utf-8") == "db-bytes"


def test_rollback_readiness_failure_reports_no_success(tmp_path: Path) -> None:
    """AC-006 / test f003: a rollback whose readiness verification fails
    exits non-zero, claims no success and leaves the pointers untouched."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    result = _run(repo, bin_dir, "rollback", env_extra={"FAKE_READINESS": "unready"})
    assert result.returncode != 0
    assert "Rolled back" not in result.stdout
    assert _pointer(repo, "current_release") == "rel-002"
    assert _pointer(repo, "previous_release") == "rel-001"


def test_build_failure_keeps_previous_release(tmp_path: Path) -> None:
    """AC-001 / test f004: a mid-build failure activates nothing."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    ups_before = _compose_log(repo).count("up -d")
    result = _deploy(repo, bin_dir, "rel-002", FAKE_FAIL_BUILD="1")
    assert result.returncode != 0
    assert _pointer(repo, "current_release") == "rel-001"
    assert _compose_log(repo).count("up -d") == ups_before


def test_internal_secrets_are_random_per_generation(tmp_path: Path) -> None:
    """AC-007 / test f005: internal keys are 64-hex-char random values;
    regenerating after deletion yields different values."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    secrets = repo / "config" / "deploy" / "secrets"
    first = (secrets / "supervisor_key").read_text(encoding="utf-8").strip()
    assert len(first) == 64
    assert all(ch in "0123456789abcdef" for ch in first)
    for name in ("supervisor_key", "agent_key", "gateway_key", "gateway_api_key"):
        (secrets / name).unlink()
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    second = (secrets / "supervisor_key").read_text(encoding="utf-8").strip()
    assert len(second) == 64 and second != first


def test_deadlines_are_passed_to_compose_and_probe(tmp_path: Path) -> None:
    """AC-003 / test f006: the bounded deadlines are pinned values, not
    free text — defaults and explicit overrides both reach the calls."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    log = _compose_log(repo)
    assert "--wait-timeout 600" in log
    assert "verify 300" in log
    assert (
        _deploy(
            repo,
            bin_dir,
            "rel-002",
            CBROWSER_DEPLOY_DEADLINE_SEC="42",
            CBROWSER_VERIFY_DEADLINE_SEC="77",
        ).returncode
        == 0
    )
    log = _compose_log(repo)
    assert "--wait-timeout 42" in log
    assert "verify 77" in log


def test_probe_reconcile_uses_deadline_as_its_timeout() -> None:
    """Review f002: the reconcile call's HTTP timeout is the verification
    deadline, not the 10s readiness-poll timeout."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "supervisor_readiness_probe", ROOT / "scripts" / "supervisor_readiness_probe.py"
    )
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    calls: list[tuple[str, str, float]] = []

    class _Resp:
        def __init__(self, payload: dict) -> None:
            self._body = json.dumps(payload).encode()

        def read(self) -> bytes:
            return self._body

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    class _Opener:
        def open(self, req, timeout: float = 0.0):  # noqa: ANN001, ANN202
            if req.method == "POST":
                calls.append(("POST", req.full_url, timeout))
                return _Resp({})
            calls.append(("GET", req.full_url, timeout))
            return _Resp({"ready": True, "reason": None, "profiles": []})

    probe._OPENER = _Opener()
    os.environ["CBROWSER_SUPERVISOR_TOKEN"] = "x" * 40
    try:
        result = probe.run(120.0)
    finally:
        del os.environ["CBROWSER_SUPERVISOR_TOKEN"]
    assert result["ready"] is True
    # The reconcile call draws from the single verification deadline
    # (remaining budget, just under 120s here), never a separate budget
    # stacked on top of the polling deadline (review f002/f006).
    assert calls[0][0] == "POST" and 100.0 < calls[0][2] <= 120.0
    assert calls[1][0] == "GET" and calls[1][2] == 10.0


def _service_block(text: str, service: str) -> str:
    """Extract one service's block from compose.yaml by indentation."""
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line == f"  {service}:":
            start = idx
            break
    assert start is not None, f"service {service} missing"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            end = idx
            break
        if line and not line.startswith(" "):
            end = idx
            break
    return "\n".join(lines[start:end])


def test_compose_yaml_release_contract() -> None:
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "build:" not in text, "compose must never build on up (AC-001)"
    for var in (
        "CBROWSER_API_IMAGE",
        "CBROWSER_GATEWAY_IMAGE",
        "CBROWSER_SUPERVISOR_IMAGE",
        "CBROWSER_CADDY_IMAGE",
    ):
        assert f"image: ${{{var}:" in text, var
    # Browser/Stream are launched by the Supervisor, so their immutable
    # IDs reach it through its environment, still release-pinned.
    for var in ("CBROWSER_BROWSER_IMAGE", "CBROWSER_STREAM_IMAGE"):
        assert f"{var}: ${{{var}:" in text, var
    # Healthchecks are bound to their own service and its own health URL
    # (test f006: no global substring/count-only assertions).
    for service, url in (
        ("api", "/api/v1/health"),
        ("gateway", "/gateway/v1/health"),
        ("supervisor", "/supervisor/v1/health"),
    ):
        block = _service_block(text, service)
        assert "healthcheck:" in block, service
        assert url in block, service
    # The Caddy fingerprint carriers live on the caddy service (AC-005).
    caddy_block = _service_block(text, "caddy")
    assert "CBROWSER_CADDYFILE_SHA256" in caddy_block
    assert "CBROWSER_FRONTEND_SHA256" in caddy_block
    assert "CBROWSER_COMPOSE_PROJECT" in text
    assert "container_name: ${CBROWSER_PREFIX:-cbrowser}-api" in text
    assert "com.cbrowser.prefix: ${CBROWSER_PREFIX:-cbrowser}" in text
