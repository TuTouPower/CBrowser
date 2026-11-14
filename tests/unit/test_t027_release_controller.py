"""t027 release-controller tests (AC-001..AC-009, cloud side).

The production deploy script is executed for real against a fake Docker
CLI in a scratch copy of the repository tree: the fake records every
invocation, serves deterministic image IDs derived from Dockerfile
content, and answers compose exec with canned readiness reports.  Real
Docker behaviour is exercised only in t032; nothing here claims it.

t035 (AC-002): the 0001-0009 migration chain was collapsed into one new
baseline revision.  Assertions/tests that hardcoded retired revision ids
(0001_initial_schema, 0009_profile_control_state, 0010_drill) and the
string-compare ``applied_migration_version`` rollback floor were removed
wholesale, not rewritten to match the new output.  Coverage for the new
semantics (baseline in the manifest, old-generation DB/release refusal,
same-generation publish and rollback) is added at the end of this file.

t065: ``test_deploy_success_builds_once_and_pins_everything`` was deleted
wholesale (not edited in place) because t065 adds a sixth release image
(``cbrowser-proxy-forwarder``) and records it in the manifest: its
5-image count, 5-dockerfile list and 6-key manifest assertions are the
old contract. Its replacement is
``test_t065_deploy_success_builds_six_images_once_and_pins_proxy_forwarder``
below, which re-asserts the whole contract (build-once, pinned manifest,
release env, pointer, compose log, no secrets) for the 6-image set.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BASELINE_REVISION = "b7e1c9d4a2f3"
# Representative retired 0001-0009 revision id, used only as fixture data
# to build an old-generation DB/release (not as an expected output).
LEGACY_HEAD = "0009_profile_control_state"

ADMIN_SENTINEL = "ADMIN-SENTINEL-VALUE-9f27"

FAKE_DOCKER = r"""#!/bin/bash
set -u
LOG="${FAKE_DOCKER_LOG:?}"
STATE="${FAKE_DOCKER_STATE:?}"
mkdir -p "$STATE/images"
echo "docker $*" >> "$LOG"
san() { printf '%s' "$1" | tr '/:' '__'; }
sha_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}
sha_text() {
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$1" | sha256sum | awk '{print $1}'
  else
    printf '%s' "$1" | shasum -a 256 | awk '{print $1}'
  fi
}
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
    id="sha256:$(sha_file "$df")"
    printf '%s' "$id" > "$STATE/images/$(san "$tag")"
    ;;
  pull)
    ref="$1"
    id="sha256:$(sha_text "pulled:$ref")"
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
  run)
    # Execute a container-side `python3 /scripts/<name>.py ...` on the
    # host with -v mount translation: <host-path>:<container-path> maps
    # to the host path, <volume-name>:<container-path> maps to
    # $STATE/volumes/<volume-name> (created on demand, mirroring Docker
    # auto-creating a named volume on first use).
    mounts=""
    image=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --rm) shift;;
        -v)
          spec="$2"; shift 2
          host="${spec%%:*}"; rest="${spec#*:}"; cont="${rest%%:*}"
          case "$host" in
            */*) host_path="$host";;
            *) host_path="$STATE/volumes/$host"; mkdir -p "$host_path";;
          esac
          mounts+="$cont"$'\t'"$host_path"$'\n'
          ;;
        --*) shift;;
        *)
          if [ -z "$image" ]; then image="$1"; shift; else break; fi
          ;;
      esac
    done
    if [ "${1:-}" != "python3" ]; then
      echo "fake docker run supports only python3 commands" >&2; exit 1
    fi
    shift
    translated=()
    for arg in "$@"; do
      new_arg="$arg"
      while IFS=$'\t' read -r cont host_path; do
        [ -n "$cont" ] || continue
        case "$new_arg" in
          "$cont") new_arg="$host_path"; break;;
          "$cont"/*) new_arg="$host_path/${new_arg#"$cont"/}"; break;;
        esac
      done <<< "$mounts"
      translated+=("$new_arg")
    done
    # A real `docker run` exits with the container command's status; the
    # fake must propagate it too — the deploy/rollback stamp check
    # (db_inspect.py) fails closed on a non-zero exit, so swallowing it
    # would let an unreadable database deploy (t051 review f003).
    python3 "${translated[@]}"
    exit $?
    ;;
  volume)
    sub="${1:-}"; if [ $# -gt 0 ]; then shift; fi
    case "$sub" in
      inspect)
        if [ -d "$STATE/volumes/${1:-}" ]; then exit 0; else exit 1; fi
        ;;
      create)
        mkdir -p "$STATE/volumes/${1:-}"
        ;;
      *) echo "unsupported volume subcommand: $sub" >&2; exit 1;;
    esac
    ;;
  ps)
    if [ "${FAKE_REQUIRE_ROLE_FORMAT:-0}" = "1" ]; then
      case "$*" in
        *com.cbrowser.role*) ;;
        *) echo "ps format must request the role label" >&2; exit 9;;
      esac
    fi
    # Rows are "name<TAB>compose-project<TAB>prefix-label<TAB>role".
    if [ -n "${FAKE_PS_ROWS:-}" ]; then
      printf '%s\n' "$FAKE_PS_ROWS"
    elif [ -n "${FAKE_CONFLICT_PROJECT:-}" ]; then
      printf 'cbrowser-gateway\t%s\tcbrowser\n' "$FAKE_CONFLICT_PROJECT"
    elif [ -n "${FAKE_OWN_PROJECT:-}" ]; then
      # This instance's own earlier containers: since t051 they carry
      # the instance-id label, and since t069 that label is the ONLY
      # ownership evidence deploy.sh accepts (no project fallback), so
      # the fake reports it from the exported deployment identity.
      printf 'cbrowser-api\t%s\tcbrowser\tapi\t%s\n' "$FAKE_OWN_PROJECT" "${CBROWSER_INSTANCE_ID:-}"
    fi
    ;;
  network)
    sub="${1:-}"; if [ $# -gt 0 ]; then shift; fi
    case "$sub" in
      ls)
        if [ -n "${FAKE_NETWORK_IDS:-}" ]; then printf '%s\n' "$FAKE_NETWORK_IDS"; fi
        # t054 R2 test f005: model this instance's own edge network,
        # created by an earlier deploy with the same prefix and subnet.
        # The name follows compose.yaml: ${CBROWSER_PREFIX}-edge;
        # deploy.sh exports CBROWSER_PREFIX, so the fake inherits it.
        if [ -n "${FAKE_OWN_EDGE_SUBNET:-}" ]; then printf '%s\n' "own-edge-net"; fi
        ;;
      inspect)
        if [ -n "${FAKE_OWN_EDGE_SUBNET:-}" ]; then
          FAKE_OWN_EDGE_NAME="${CBROWSER_PREFIX:-cbrowser}-edge" python3 -c 'import json, os; records = json.loads(os.environ.get("FAKE_NETWORK_SUBNETS", "[]")); records.append({"Name": os.environ["FAKE_OWN_EDGE_NAME"], "IPAM": {"Config": [{"Subnet": os.environ["FAKE_OWN_EDGE_SUBNET"]}]}}); print(json.dumps(records))'
        else
          printf '%s' "${FAKE_NETWORK_SUBNETS:-[]}"
        fi
        ;;
      *) echo "unsupported network subcommand: $sub" >&2; exit 1;;
    esac
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
      down)
        echo "down $*" >> "$LOG.compose"
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
    shutil.copy(ROOT / "scripts" / "deploy.sh", repo / "scripts" / "deploy.sh")
    shutil.copy(
        ROOT / "scripts" / "supervisor_readiness_probe.py",
        repo / "scripts" / "supervisor_readiness_probe.py",
    )
    for script in ("db_inspect.py", "db_backup.py", "db_restore.py", "check_font_sets.py", "check_edge_subnet.py"):
        shutil.copy(ROOT / "scripts" / script, repo / "scripts" / script)
    shutil.copy(ROOT / "compose.yaml", repo / "compose.yaml")
    _copy_tree(ROOT / "config" / "docker", repo / "config" / "docker")
    net_dir = repo / "src" / "backend" / "cbrowser"
    net_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        ROOT / "src" / "backend" / "cbrowser" / "network_config.py",
        net_dir / "network_config.py",
    )
    # The font-set preflight (scripts/check_font_sets.py) bootstraps its
    # own sys.path to the fake tree, so font_sets must be copied whole.
    # NOTE: do NOT copy cbrowser/__init__.py or supervisor/__init__.py
    # here: the fake tree's `cbrowser` must stay a namespace package so
    # imports in deploy.sh (atomic_write's shared.atomic_write, the network
    # config CLI) keep resolving from the real tree via PYTHONPATH, as
    # they always have.  A regular __init__.py in the fake tree would
    # shadow the real package and break those imports.
    _copy_tree(
        ROOT / "src" / "backend" / "cbrowser" / "font_sets",
        repo / "src" / "backend" / "cbrowser" / "font_sets",
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
        "CBROWSER_PYTHON": sys.executable,
        "PYTHONPATH": str(ROOT / "src" / "backend"),
    }
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", "scripts/deploy.sh", *args],
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
    # t051: the two pointer files are one JSON pointer file.
    path = repo / "config" / "deploy" / "release_pointer.json"
    if not path.exists():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    field = "current" if name == "current_release" else "previous"
    return data.get(field) or ""


def _pointer_file(repo: Path, deploy_dir: Path | None = None) -> dict:
    path = (deploy_dir or repo / "config" / "deploy") / "release_pointer.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


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


def test_t065_deploy_success_builds_six_images_once_and_pins_proxy_forwarder(
    tmp_path: Path,
) -> None:
    # t065 replacement for test_deploy_success_builds_once_and_pins_everything
    # (deleted wholesale: its 5-image contract is superseded by the sixth
    # release image, cbrowser-proxy-forwarder, built once and pinned in the
    # manifest and release env like the other five).
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    result = _deploy(repo, bin_dir, "rel-001")
    assert result.returncode == 0, result.stderr

    builds = _builds(repo)
    assert len(builds) == 6, builds
    dockerfiles = sorted(line.rsplit("dockerfile=", 1)[1] for line in builds)
    assert dockerfiles == [
        "config/docker/api_runtime/Dockerfile",
        "config/docker/browser_runtime/Dockerfile",
        "config/docker/gateway_runtime/Dockerfile",
        "config/docker/proxy_forwarder_runtime/Dockerfile",
        "config/docker/stream_runtime/Dockerfile",
        "config/docker/supervisor_runtime/Dockerfile",
    ]

    manifest = _manifest(repo, "rel-001")
    assert sorted(manifest["images"]) == [
        "api",
        "browser",
        "caddy",
        "gateway",
        "proxy-forwarder",
        "stream",
        "supervisor",
    ]
    assert all(v.startswith("sha256:") for v in manifest["images"].values())
    expected_api = "sha256:" + hashlib.sha256(
        (ROOT / "config/docker/api_runtime/Dockerfile").read_bytes()
    ).hexdigest()
    assert manifest["images"]["api"] == expected_api
    expected_forwarder = "sha256:" + hashlib.sha256(
        (ROOT / "config/docker/proxy_forwarder_runtime/Dockerfile").read_bytes()
    ).hexdigest()
    assert manifest["images"]["proxy-forwarder"] == expected_forwarder
    assert manifest["compose_sha256"] == hashlib.sha256(
        (ROOT / "compose.yaml").read_bytes()
    ).hexdigest()
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
        "CBROWSER_PROXY_FORWARDER_IMAGE",
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


def test_deploy_refuses_when_derived_edge_subnet_overlaps_existing_network(
    tmp_path: Path,
) -> None:
    """t054 R1 f001/test f001(a): the edge-subnet conflict precheck refuses
    the deploy when the derived subnet overlaps an existing Docker
    network, names the explicit-subnet escape hatch, and records no
    release (refused before any build)."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    _, _, edge_subnet = _instance_identity(repo)
    subnets = json.dumps([{"IPAM": {"Config": [{"Subnet": edge_subnet}]}}])
    result = _deploy(
        repo,
        bin_dir,
        "rel-001",
        FAKE_NETWORK_IDS="existing-net",
        FAKE_NETWORK_SUBNETS=subnets,
    )
    assert result.returncode != 0
    assert "edge subnet" in result.stderr
    assert "CBROWSER_EDGE_SUBNET" in result.stderr
    assert not (repo / "config" / "deploy" / "releases" / "rel-001.json").exists()
    assert _builds(repo) == []


def test_deploy_uses_explicit_edge_subnet_when_set(tmp_path: Path) -> None:
    """t054 R1 f001/test f001(b): an explicitly set CBROWSER_EDGE_SUBNET
    is kept (not overwritten by the derived value) and is recorded in
    the release env and manifest, with the trusted proxy CIDRs equal to
    the explicit value."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    _, _, derived = _instance_identity(repo)
    # 172.40.0.0/16 can never equal the derived value (172.18-31.0.0/16),
    # so this test cannot pass by accident when derivation wins.
    explicit = "172.40.0.0/16"
    assert explicit != derived
    result = _deploy(repo, bin_dir, "rel-001", CBROWSER_EDGE_SUBNET=explicit)
    assert result.returncode == 0, result.stderr
    manifest = _manifest(repo, "rel-001")
    assert manifest["instance"]["edge_subnet"] == explicit
    env_text = (
        repo / "config" / "deploy" / "releases" / "rel-001.env"
    ).read_text(encoding="utf-8")
    assert f"CBROWSER_EDGE_SUBNET={explicit}" in env_text
    assert f"CBROWSER_TRUSTED_PROXY_CIDRS={explicit}" in env_text


def test_deploy_refuses_when_explicit_edge_subnet_overlaps(
    tmp_path: Path,
) -> None:
    """t054 R1 f001/test f001(c): the conflict precheck runs against the
    EXPLICIT subnet, not the derived one — an explicit subnet overlapping
    an existing Docker network is refused even though the derived subnet
    is free."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    explicit = "172.40.0.0/16"
    subnets = json.dumps([{"IPAM": {"Config": [{"Subnet": explicit}]}}])
    result = _deploy(
        repo,
        bin_dir,
        "rel-001",
        CBROWSER_EDGE_SUBNET=explicit,
        FAKE_NETWORK_IDS="existing-net",
        FAKE_NETWORK_SUBNETS=subnets,
    )
    assert result.returncode != 0
    assert "edge subnet" in result.stderr
    assert "CBROWSER_EDGE_SUBNET" in result.stderr
    assert not (repo / "config" / "deploy" / "releases" / "rel-001.json").exists()
    assert _builds(repo) == []


def test_redeploy_succeeds_when_only_own_edge_network_exists(
    tmp_path: Path,
) -> None:
    """t054 R2 test f005(a): a second deploy of the same instance is not
    refused by its own edge network. After rel-001, the edge network
    named ``cbrowser-edge`` exists with the derived subnet; rel-002 must
    still deploy and become current."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    _, _, edge_subnet = _instance_identity(repo)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    result = _deploy(
        repo, bin_dir, "rel-002", FAKE_OWN_EDGE_SUBNET=edge_subnet
    )
    assert result.returncode == 0, result.stderr
    assert _pointer(repo, "current_release") == "rel-002"
    assert _pointer(repo, "previous_release") == "rel-001"
    assert _manifest(repo, "rel-002")["instance"]["edge_subnet"] == edge_subnet


def test_rollback_succeeds_when_only_own_edge_network_exists(
    tmp_path: Path,
) -> None:
    """t054 R2 test f005(b): rollback after a deploy is not refused by
    the instance's own edge network — the target release's recorded
    subnet equals the existing own network's subnet."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    _, _, edge_subnet = _instance_identity(repo)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    result = _run(
        repo,
        bin_dir,
        "rollback",
        env_extra={"FAKE_OWN_EDGE_SUBNET": edge_subnet},
    )
    assert result.returncode == 0, result.stderr
    assert _pointer(repo, "current_release") == "rel-001"


def test_deploy_still_refuses_foreign_overlap_when_own_network_exists(
    tmp_path: Path,
) -> None:
    """t054 R2 test f005(c): the own-network exclusion is scoped by name
    AND subnet, not by subnet alone — a FOREIGN network with the same
    subnet is still refused even while the own edge network exists."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    _, _, edge_subnet = _instance_identity(repo)
    subnets = json.dumps(
        [{"Name": "other-edge", "IPAM": {"Config": [{"Subnet": edge_subnet}]}}]
    )
    result = _deploy(
        repo,
        bin_dir,
        "rel-001",
        FAKE_NETWORK_IDS="existing-net",
        FAKE_NETWORK_SUBNETS=subnets,
        FAKE_OWN_EDGE_SUBNET=edge_subnet,
    )
    assert result.returncode != 0
    assert "edge subnet" in result.stderr
    assert "CBROWSER_EDGE_SUBNET" in result.stderr
    assert not (repo / "config" / "deploy" / "releases" / "rel-001.json").exists()
    assert _builds(repo) == []


def test_rollback_restores_target_port_not_current_port(
    tmp_path: Path,
) -> None:
    """t054 R1 test f002: rollback re-renders the Caddyfile from the
    TARGET release's recorded port. Deploying rel-001 at 56661 and
    rel-002 at 56662, then rolling back, must serve 56661 — a rollback
    that reused the current port would serve 56662 and fail here."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(
        repo, bin_dir, "rel-001", CBROWSER_HTTPS_PORT="56661"
    ).returncode == 0
    assert _deploy(
        repo, bin_dir, "rel-002", CBROWSER_HTTPS_PORT="56662"
    ).returncode == 0
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode == 0, result.stderr
    assert _pointer(repo, "current_release") == "rel-001"
    caddyfile = repo / "data" / "instance" / "network" / "Caddyfile"
    first_line = caddyfile.read_text(encoding="utf-8").splitlines()[0]
    assert "https_port 56661" in first_line
    assert "56662" not in first_line
    rendered_sha = hashlib.sha256(caddyfile.read_bytes()).hexdigest()
    assert rendered_sha == _manifest(repo, "rel-001")["caddyfile_sha256"]


def test_rollback_refuses_on_caddyfile_sha_mismatch_without_touching_disk(
    tmp_path: Path,
) -> None:
    """t054 R1 test f002: a target manifest whose caddyfile_sha256 does
    not match the re-rendered Caddyfile refuses the rollback AND leaves
    the on-disk Caddyfile and the release pointer untouched."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(
        repo, bin_dir, "rel-001", CBROWSER_HTTPS_PORT="56661"
    ).returncode == 0
    assert _deploy(
        repo, bin_dir, "rel-002", CBROWSER_HTTPS_PORT="56662"
    ).returncode == 0
    caddyfile = repo / "data" / "instance" / "network" / "Caddyfile"
    before = caddyfile.read_bytes()
    assert b"https_port 56662" in before.splitlines()[0]
    manifest_path = repo / "config" / "deploy" / "releases" / "rel-001.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["caddyfile_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode != 0
    assert "caddyfile_sha256" in result.stderr
    assert caddyfile.read_bytes() == before
    assert _pointer(repo, "current_release") == "rel-002"


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
            "CBROWSER_PREFIX": "inst_b",
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
    # t069: the target instance's own gateway container proves ownership
    # only through its instance-id label (the compose-project fallback
    # exemption is deleted), so the row carries instance B's real id.
    instance_id_b, *_ = _instance_identity(repo, "inst_b", repo / "data-b")
    rows = f"inst_b-gateway\tinst-b\tinst_b\tgateway\t{instance_id_b}"
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
    rows = "inst_b-supervisor\tother-proj\tinst_b"
    result = _run(
        repo,
        bin_dir,
        "rollback",
        env_extra={"CBROWSER_PREFIX": "cbrowser", "FAKE_PS_ROWS": rows},
    )
    assert result.returncode != 0
    assert "prefix" in result.stderr
    assert _pointer(repo, "current_release") == "b-002"


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
            "CBROWSER_PREFIX": "inst_b",
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
    instance_id_b, pool_b, edge_b = _instance_identity(repo, "inst_b", repo / "data-b")
    assert manifest_b["instance"] == {
        "project": "inst-b",
        "prefix": "inst_b",
        "https_port": 56662,
        "instance_id": instance_id_b,
        "media_subnet_pool": pool_b,
        "edge_subnet": edge_b,
    }
    env_b = (deploy_dir_b / "releases" / "b-001.env").read_text(encoding="utf-8")
    assert f"CBROWSER_DATA_ROOT={repo}/data-b" in env_b
    assert f"CBROWSER_SECRETS_DIR={secrets_b}" in env_b
    assert f"CBROWSER_INSTANCE_ID={instance_id_b}" in env_b
    assert f"CBROWSER_MEDIA_SUBNET_POOL={pool_b}" in env_b
    assert f"CBROWSER_EDGE_SUBNET={edge_b}" in env_b
    assert f"CBROWSER_TRUSTED_PROXY_CIDRS={edge_b}" in env_b
    assert f"CBROWSER_FONTS_DIR={repo}/data/fonts" in env_b
    assert _pointer_file(repo, deploy_dir_b).get("current") == "b-001"
    # The internal keys must actually be generated into the parameterized
    # secrets dir (test f007), not only recorded there in the env file.
    for name in ("supervisor_key", "agent_key", "gateway_key", "gateway_api_key"):
        key_file = secrets_b / name
        assert key_file.is_file(), name
        assert stat.S_IMODE(key_file.stat().st_mode) == 0o600, name

    # The default instance deploys independently; neither pointer moves.
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    assert _pointer(repo, "current_release") == "rel-001"
    assert _pointer_file(repo, deploy_dir_b).get("current") == "b-001"


def test_caddy_fingerprints_recorded_and_change_sensitive(
    tmp_path: Path,
) -> None:
    """AC-005 / test f002: the release env carries the real Caddyfile and
    frontend fingerprints. t054: the fingerprint hashes the RENDERED
    Caddyfile product, not the generator source — a comment appended to
    the generator leaves the fingerprint unchanged, while a port change
    (which re-renders the product) changes exactly that fingerprint and
    image IDs stay stable."""
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

    def _rendered_caddy_sha(env: dict[str, str]) -> str:
        caddyfile = Path(env["CBROWSER_DATA_ROOT"]) / "network" / "Caddyfile"
        return hashlib.sha256(caddyfile.read_bytes()).hexdigest()

    env1 = _env("rel-001")
    assert env1["CBROWSER_CADDYFILE_SHA256"] == _rendered_caddy_sha(env1)
    dist = repo / "src" / "frontend" / "dist"
    listing = "".join(
        f"{path.relative_to(dist)} {hashlib.sha256(path.read_bytes()).hexdigest()}\n"
        for path in sorted(dist.rglob("*"))
        if path.is_file()
    )
    expected_frontend = hashlib.sha256(listing.encode()).hexdigest()
    assert env1["CBROWSER_FRONTEND_SHA256"] == expected_frontend

    # A generator-source change that renders the same product must NOT
    # change the fingerprint. The fake tree's network_config.py is the
    # generator the deploy renders with when it leads PYTHONPATH (the
    # fake tree stays a namespace package, so the rest still resolves
    # from the real tree).
    net_config = repo / "src" / "backend" / "cbrowser" / "network_config.py"
    net_config.write_text(
        net_config.read_text(encoding="utf-8") + "\n# drill change\n",
        encoding="utf-8",
    )
    fake_pythonpath = (
        f"{repo / 'src' / 'backend'}:{ROOT / 'src' / 'backend'}"
    )
    result = _deploy(
        repo, bin_dir, "rel-002", PYTHONPATH=fake_pythonpath
    )
    assert result.returncode == 0, result.stderr
    env2 = _env("rel-002")
    assert env2["CBROWSER_CADDYFILE_SHA256"] == env1["CBROWSER_CADDYFILE_SHA256"]
    assert env2["CBROWSER_CADDYFILE_SHA256"] == _rendered_caddy_sha(env2)
    assert env2["CBROWSER_FRONTEND_SHA256"] == env1["CBROWSER_FRONTEND_SHA256"]
    assert env2["CBROWSER_API_IMAGE"] == env1["CBROWSER_API_IMAGE"]

    # A port change re-renders the product and MUST change the fingerprint.
    result = _deploy(repo, bin_dir, "rel-003", CBROWSER_HTTPS_PORT="56662")
    assert result.returncode == 0, result.stderr
    env3 = _env("rel-003")
    assert env3["CBROWSER_CADDYFILE_SHA256"] != env1["CBROWSER_CADDYFILE_SHA256"]
    assert env3["CBROWSER_CADDYFILE_SHA256"] == _rendered_caddy_sha(env3)
    assert env3["CBROWSER_FRONTEND_SHA256"] == env1["CBROWSER_FRONTEND_SHA256"]
    assert env3["CBROWSER_API_IMAGE"] == env1["CBROWSER_API_IMAGE"]


def test_rollback_preserves_profile_data_and_database(tmp_path: Path) -> None:
    """AC-006 / test f003: rollback never deletes Browser/Profile data
    or the database."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    data_root = repo / "data" / "instance"
    profile_file = data_root / "profiles" / "p1" / "profile" / "Cookies"
    profile_file.parent.mkdir(parents=True, exist_ok=True)
    profile_file.write_text("cookie-bytes", encoding="utf-8")
    # The database lives in the named volume now; seed a valid stamped
    # one (a plain-text file would fail the container-side stamp check).
    db = _stamp_db(repo, _migration_head(repo))
    before = db.read_bytes()
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode == 0, result.stderr
    assert profile_file.read_text(encoding="utf-8") == "cookie-bytes"
    assert db.read_bytes() == before


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


def test_compose_yaml_t051_db_fonts_labels_contract() -> None:
    """t051 AC-001/AC-009/AC-010/AC-021: DB named volume, independent fonts
    dir, deployment labels on every control-plane service."""
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    # DB lives in a named volume, not the DATA_ROOT bind mount.
    assert "  db:\n    name: ${CBROWSER_PREFIX:-cbrowser}-db" in text
    assert "/data/cbrowser.db" not in text
    assert "/data/db/cbrowser.db" in text
    api_block = _service_block(text, "api")
    assert "db:/data/db" in api_block
    assert "CBROWSER_DB_PATH: /data/db/cbrowser.db" in api_block
    # Fonts are an independent deploy input, mounted at /fonts:ro.
    assert "CBROWSER_DATA_ROOT}/fonts" not in text
    for service in ("api", "supervisor"):
        block = _service_block(text, service)
        assert "${CBROWSER_FONTS_DIR:?set CBROWSER_FONTS_DIR}:/fonts:ro" in block
        assert "CBROWSER_FONTS_DIR: /fonts" in block
    # Deployment identity labels on every control-plane service.
    for service in ("api", "gateway", "supervisor", "caddy"):
        block = _service_block(text, service)
        assert (
            "com.cbrowser.instance-id: ${CBROWSER_INSTANCE_ID:?" in block
        ), service
        assert (
            "com.cbrowser.media-subnet-pool: ${CBROWSER_MEDIA_SUBNET_POOL:?"
            in block
        ), service
    # The Supervisor container must also receive the deployment identity
    # and media pool as environment (t051 review f002): the runner main
    # and DockerAdapter env fallbacks (CBROWSER_INSTANCE_ID /
    # CBROWSER_MEDIA_SUBNET_POOL) only take effect when compose actually
    # passes them into the container.  CBROWSER_DOCKER_NETWORK_TIMEOUT
    # is deliberately not passed: deploy.sh does not write it to the
    # release env, so there is no value to forward.
    supervisor_block = _service_block(text, "supervisor")
    assert (
        "CBROWSER_INSTANCE_ID: ${CBROWSER_INSTANCE_ID:?run scripts/deploy.sh first}"
        in supervisor_block
    )
    assert (
        "CBROWSER_MEDIA_SUBNET_POOL: ${CBROWSER_MEDIA_SUBNET_POOL:?run scripts/deploy.sh first}"
        in supervisor_block
    )


# ---------------------------------------------------------------------------
# t035 AC-002: schema-generation fail-closed + revision-chain rollback floor
# These replace the removed old-generation assertions/tests above and cover
# the new semantics.  Old-generation DB ids and the LEGACY_HEAD fixture are
# inputs, never expected outputs.
# ---------------------------------------------------------------------------


def _instance_identity(
    repo: Path, prefix: str = "cbrowser", data_root: Path | None = None
) -> tuple[str, str, str]:
    """The deterministic (instance_id, media_subnet_pool, edge_subnet)
    deploy.sh derives from (prefix, data root).  Mirrors the material
    string in deploy.sh byte for byte:
    "cbrowser-instance-v1\\0<prefix>\\0<data_root>"."""
    if data_root is None:
        data_root = repo / "data" / "instance"
    material = b"cbrowser-instance-v1\0" + prefix.encode() + b"\0" + str(data_root).encode()
    digest = hashlib.sha256(material).hexdigest()
    return (
        digest[:32],
        f"10.{192 + int(digest, 16) % 64}.0.0/16",
        f"172.{18 + int(digest, 16) % 14}.0.0/16",
    )


def _stamp_db_path(path: Path, revision: str) -> Path:
    """Stamp an arbitrary path with the given alembic_version."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        conn.execute(
            "INSERT INTO alembic_version (version_num) VALUES (?)", (revision,)
        )
        conn.commit()
    finally:
        conn.close()
    return path


def _read_stamp(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else ""
    finally:
        conn.close()


def _stamp_db(repo: Path, revision: str, prefix: str = "cbrowser") -> Path:
    """Create a database stamped with the given alembic_version in the
    named volume, as the API would leave it on disk."""
    vol_dir = repo / ".fake-state" / "volumes" / f"{prefix}-db"
    vol_dir.mkdir(parents=True, exist_ok=True)
    return _stamp_db_path(vol_dir / "cbrowser.db", revision)


def test_deploy_refuses_legacy_generation_database(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    db = _stamp_db(repo, LEGACY_HEAD)
    before = db.read_bytes()
    result = _deploy(repo, bin_dir, "rel-001")
    assert result.returncode != 0
    assert "rebuild" in result.stderr.lower()
    assert "data directory" in result.stderr.lower()
    # Fail closed: database untouched, no container started, no pointer
    # moved.  Exactly one build ran: the schema check needs the API image,
    # so it is built first; building an image changes no data, and the
    # safety property (nothing started, nothing moved, DB untouched) is
    # preserved — the old `_builds == []` assertion cannot hold under the
    # container-side stamp check.
    assert db.read_bytes() == before
    builds = _builds(repo)
    assert len(builds) == 1, builds
    assert "api_runtime/Dockerfile" in builds[0]
    assert _pointer(repo, "current_release") == ""


def test_deploy_refuses_corrupt_database(tmp_path: Path) -> None:
    """AC-018 (t051 review f003): a volume database that exists but is
    not a readable SQLite file refuses the deploy before any container
    starts — the stamp check fails closed, like the retired-generation
    refusal, except the API image build it needs is the only build."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    db = _stamp_db(repo, BASELINE_REVISION)
    db.write_text("corrupt replacement", encoding="utf-8")
    before = db.read_bytes()
    result = _deploy(repo, bin_dir, "rel-001")
    assert result.returncode != 0
    assert db.read_bytes() == before
    assert "up -d" not in _compose_log(repo)
    builds = _builds(repo)
    assert len(builds) == 1, builds
    assert "api_runtime/Dockerfile" in builds[0]
    assert _pointer(repo, "current_release") == ""


def test_deploy_allows_baseline_generation_database(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    _stamp_db(repo, BASELINE_REVISION)
    result = _deploy(repo, bin_dir, "rel-001")
    assert result.returncode == 0, result.stderr


def test_rollback_refuses_legacy_generation_database(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    db = _stamp_db(repo, LEGACY_HEAD)
    before = db.read_bytes()
    ups_before = _compose_log(repo).count("up -d")
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode != 0
    assert "rebuild" in result.stderr.lower()
    assert db.read_bytes() == before
    assert _compose_log(repo).count("up -d") == ups_before
    assert _pointer(repo, "current_release") == "rel-002"


def test_rollback_refuses_corrupt_database(tmp_path: Path) -> None:
    """AC-018 (t051 review f003): a volume database that exists but is
    not a readable SQLite file refuses the rollback before any container
    is started or replaced — the stamp check fails closed."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    db = _stamp_db(repo, BASELINE_REVISION)
    db.write_text("corrupt replacement", encoding="utf-8")
    before = db.read_bytes()
    ups_before = _compose_log(repo).count("up -d")
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode != 0
    assert db.read_bytes() == before
    assert _compose_log(repo).count("up -d") == ups_before
    assert _pointer(repo, "current_release") == "rel-002"




def test_rollback_refuses_legacy_generation_release(tmp_path: Path) -> None:
    def edit(manifest: dict) -> None:
        # A retired 0001-0009 revision id: representative of an
        # old-generation release (fixture input, not an expected output).
        manifest["migration_version"] = LEGACY_HEAD

    repo, bin_dir = _deploy_two_then_edit_manifest(tmp_path, edit)
    ups_before = _compose_log(repo).count("up -d")
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode != 0
    assert "revision chain" in result.stderr.lower()
    assert "migration" in result.stderr.lower()
    assert _compose_log(repo).count("up -d") == ups_before
    assert _pointer(repo, "current_release") == "rel-002"




def _migration_head(repo: Path) -> str:
    """Parse the shipped revision ids and return the single chain head."""
    versions = repo / "src" / "backend" / "migrations" / "versions"
    revisions: dict[str, str | None] = {}
    downs: set[str] = set()
    for path in versions.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        m = re.search(r'^revision[^=]*=\s*"([^"]+)"', text, re.M)
        d = re.search(r'^down_revision[^=]*=\s*"([^"]+)"', text, re.M)
        if m:
            revisions[m.group(1)] = d.group(1) if d else None
            if d:
                downs.add(d.group(1))
    heads = [r for r in revisions if r not in downs]
    assert len(heads) == 1
    return heads[0]


def test_manifest_records_current_head_with_incremental_chain(
    tmp_path: Path,
) -> None:
    """t041: manifest records the current chain head, not the baseline."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    head = _migration_head(repo)
    assert head != BASELINE_REVISION
    assert _manifest(repo, "rel-001")["migration_version"] == head
    versions = sorted(
        (repo / "src" / "backend" / "migrations" / "versions").glob("*.py")
    )
    revision_files = [p for p in versions if not p.name.startswith("__")]
    revisions: dict[str, str | None] = {}
    for path in revision_files:
        text = path.read_text(encoding="utf-8")
        m = re.search(r'^revision[^=]*=\s*"([^"]+)"', text, re.M)
        d = re.search(r'^down_revision[^=]*=\s*"([^"]+)"', text, re.M)
        if m:
            revisions[m.group(1)] = d.group(1) if d else None
    assert head in revisions
    assert len(revisions) == len(revision_files)
    cursor: str | None = head
    seen: set[str] = set()
    while cursor is not None:
        assert cursor not in seen
        seen.add(cursor)
        cursor = revisions[cursor]
    assert len(seen) == len(revisions)
    assert BASELINE_REVISION in seen


def test_same_generation_publish_and_rollback_with_incremental_chain(
    tmp_path: Path,
) -> None:
    """t041: same-generation releases still publish and roll back when the
    chain contains an incremental migration after the baseline."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    head = _migration_head(repo)
    assert _manifest(repo, "rel-001")["migration_version"] == head
    assert _manifest(repo, "rel-002")["migration_version"] == head
    result = _run(repo, bin_dir, "rollback")
    assert result.returncode == 0, result.stderr
    assert _pointer(repo, "current_release") == "rel-001"


# --- t050: sandbox pseudo compose project is owned by this instance -----


def test_prefix_conflict_allows_own_sandbox_group(tmp_path: Path) -> None:
    """A ``<project>-profiles`` Browser/Stream container is this
    instance's sandbox grouping, not another instance claiming the
    prefix (t050).  Ownership is proven by the instance-id label now
    (t051 AC-021): the row carries this instance's deployment id."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    instance_id, *_ = _instance_identity(repo)
    rows = f"cbrowser-browser-p1\tcbrowser-profiles\tcbrowser\tbrowser\t{instance_id}"
    result = _deploy(
        repo, bin_dir, "rel-001", FAKE_PS_ROWS=rows
    )
    assert result.returncode == 0, result.stderr


def test_prefix_conflict_still_refuses_foreign_project_with_sandbox_role(
    tmp_path: Path,
) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    rows = "cbrowser-browser-p1\tother-instance\tcbrowser\tbrowser"
    result = _deploy(repo, bin_dir, "rel-001", FAKE_PS_ROWS=rows)
    assert result.returncode != 0
    assert "prefix" in result.stderr
    assert _builds(repo) == []


def test_prefix_conflict_allows_sandbox_group_when_project_differs(
    tmp_path: Path,
) -> None:
    """Sandbox grouping is derived from the resource prefix, not the
    compose project name (t050).  Ownership is proven by the
    instance-id label now (t051 AC-021)."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    instance_id, *_ = _instance_identity(repo, "inst_b")
    rows = f"inst_b-browser-p1\tinst_b-profiles\tinst_b\tbrowser\t{instance_id}"
    result = _deploy(
        repo,
        bin_dir,
        "rel-001",
        FAKE_PS_ROWS=rows,
        CBROWSER_PREFIX="inst_b",
        CBROWSER_COMPOSE_PROJECT="proj-b",
    )
    assert result.returncode == 0, result.stderr
    assert _builds(repo)


def test_prefix_conflict_check_requests_role_label(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    instance_id, *_ = _instance_identity(repo)
    rows = f"cbrowser-browser-p1\tcbrowser-profiles\tcbrowser\tbrowser\t{instance_id}"
    result = _deploy(
        repo,
        bin_dir,
        "rel-001",
        FAKE_PS_ROWS=rows,
        FAKE_REQUIRE_ROLE_FORMAT="1",
    )
    assert result.returncode == 0, result.stderr


def test_prefix_conflict_refuses_pseudo_project_with_non_sandbox_role(
    tmp_path: Path,
) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    rows = "cbrowser-supervisor-x\tcbrowser-profiles\tcbrowser\tsupervisor"
    result = _deploy(repo, bin_dir, "rel-001", FAKE_PS_ROWS=rows)
    assert result.returncode != 0
    assert "prefix" in result.stderr


# --- t051: deployment identity, named-volume DB, JSON pointer ----------


def test_prefix_validation_refuses_invalid_prefix(tmp_path: Path) -> None:
    """A22: a malformed prefix fails closed before any Docker operation."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    for bad in ("Bad Prefix!", "inst-b", "-lead", "UPPER"):
        result = _deploy(repo, bin_dir, "rel-001", CBROWSER_PREFIX=bad)
        assert result.returncode != 0, bad
        assert "prefix" in result.stderr.lower(), bad
    assert _builds(repo) == []


def test_pointer_is_single_json_file(tmp_path: Path) -> None:
    """A43/AC-017: current/previous live in one JSON pointer file; the
    old two files are gone."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    deploy_dir = repo / "config" / "deploy"
    assert not (deploy_dir / "current_release").exists()
    assert not (deploy_dir / "previous_release").exists()
    pointer = json.loads((deploy_dir / "release_pointer.json").read_text())
    assert pointer == {"current": "rel-002", "previous": "rel-001"}


def test_corrupt_pointer_file_is_replaced_not_fatal(tmp_path: Path) -> None:
    """AC-017: a torn/corrupt pointer file (external damage; the atomic
    writer makes a crash-torn pointer impossible) does not block the
    deploy — activate replaces it.  The previous release is lost with
    the torn file; that loss is the documented fail-soft behaviour."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    (repo / "config" / "deploy" / "release_pointer.json").write_text(
        "{torn json", encoding="utf-8"
    )
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    assert _pointer(repo, "current_release") == "rel-002"
    assert _pointer(repo, "previous_release") == ""


def _other_pool(pool: str) -> str:
    """A /16 in the same 10.192-10.255 range that cannot overlap `pool`."""
    third = int(pool.split(".")[1])
    other = third + 1 if third < 255 else 192
    return f"10.{other}.0.0/16"


def test_media_pool_overlap_refused(tmp_path: Path) -> None:
    """A3: a foreign deployment whose media pool overlaps ours refuses
    the deploy even when its prefix differs."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    _, pool, _ = _instance_identity(repo)
    rows = f"other-api\tother-proj\tother\tapi\tother-instance-id\t{pool}"
    result = _deploy(repo, bin_dir, "rel-001", FAKE_PS_ROWS=rows)
    assert result.returncode != 0
    assert "pool" in result.stderr.lower()
    assert _builds(repo) == []


def test_media_pool_non_overlap_allowed(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    _, pool, _ = _instance_identity(repo)
    rows = (
        "other-api\tother-proj\tother\tapi\tother-instance-id\t"
        f"{_other_pool(pool)}"
    )
    result = _deploy(repo, bin_dir, "rel-001", FAKE_PS_ROWS=rows)
    assert result.returncode == 0, result.stderr


def test_prefix_conflict_forged_project_wrong_instance_id_refused(
    tmp_path: Path,
) -> None:
    """AC-021: a different compose project with a mismatched instance
    id is foreign, even when it claims our prefix."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    rows = (
        "cbrowser-browser-p1\tother-instance\tcbrowser\tbrowser\t"
        "deadbeefdeadbeefdeadbeefdeadbeef"
    )
    result = _deploy(repo, bin_dir, "rel-001", FAKE_PS_ROWS=rows)
    assert result.returncode != 0
    assert "prefix" in result.stderr
    assert _builds(repo) == []


def test_prefix_conflict_missing_instance_id_not_claimed(
    tmp_path: Path,
) -> None:
    """AC-021: a container with no instance-id label is not claimed —
    the old <prefix>-profiles project-name exemption is gone."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    rows = "cbrowser-browser-p1\tcbrowser-profiles\tcbrowser\tbrowser"
    result = _deploy(repo, bin_dir, "rel-001", FAKE_PS_ROWS=rows)
    assert result.returncode != 0
    assert "prefix" in result.stderr
    assert _builds(repo) == []


def test_prefix_conflict_same_project_wrong_instance_id_refused(
    tmp_path: Path,
) -> None:
    """AC-021 (t051 review f001): a same-project container whose
    instance-id label is present but mismatched is foreign — the
    compose project name is not an exemption."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    rows = (
        "cbrowser-api\tcbrowser\tcbrowser\tapi\t"
        "deadbeefdeadbeefdeadbeefdeadbeef"
    )
    result = _deploy(repo, bin_dir, "rel-001", FAKE_PS_ROWS=rows)
    assert result.returncode != 0
    assert "prefix" in result.stderr
    assert _builds(repo) == []


def test_prefix_conflict_same_project_matching_instance_id_allowed(
    tmp_path: Path,
) -> None:
    """AC-021 (t051 review f001): a same-project container whose
    instance-id label equals this instance's id is ours."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    instance_id, *_ = _instance_identity(repo)
    rows = f"cbrowser-api\tcbrowser\tcbrowser\tapi\t{instance_id}"
    result = _deploy(repo, bin_dir, "rel-001", FAKE_PS_ROWS=rows)
    assert result.returncode == 0, result.stderr


def test_backup_and_restore_round_trip(tmp_path: Path) -> None:
    """AC-003/AC-016: a deploy backs the live database up (recorded in
    the manifest) and `deploy.sh restore` copies it back."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    head = _migration_head(repo)
    db = _stamp_db(repo, head)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    manifest = _manifest(repo, "rel-001")
    backup = manifest["database_backup"]
    assert backup, "backup path must be recorded in the manifest"
    backup_path = Path(backup)
    assert backup_path.is_file()
    assert _read_stamp(backup_path) == head
    # Corrupt the live database, then restore from the backup.
    db.write_text("corrupt replacement", encoding="utf-8")
    result = _run(repo, bin_dir, "restore", backup)
    assert result.returncode == 0, result.stderr
    assert _read_stamp(db) == head
    assert "down" in _compose_log(repo)


def test_restore_without_current_release_refused(tmp_path: Path) -> None:
    """AC-003: restore with no current release recorded is refused.
    The backup file exists here so the refusal comes from the
    no-current-release branch (deploy.sh checks the backup file first),
    not the missing-backup branch."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    backup = tmp_path / "backup.db"
    backup.write_text("not a database", encoding="utf-8")
    result = _run(repo, bin_dir, "restore", str(backup))
    assert result.returncode != 0
    assert "No current release" in result.stderr


def test_restore_missing_backup_file_refused(tmp_path: Path) -> None:
    """AC-003 (t051 review f002): restore refuses when the backup file
    itself does not exist, even with a current release recorded."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    result = _run(repo, bin_dir, "restore", str(tmp_path / "no-such-backup.db"))
    assert result.returncode != 0
    assert "does not exist" in result.stderr


def test_old_host_database_prompt(tmp_path: Path) -> None:
    """AC-004: a legacy host database is reported with its disposition
    and never moved or deleted; the deploy continues."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    head = _migration_head(repo)
    legacy = repo / "data" / "v2" / "cbrowser.db"
    _stamp_db_path(legacy, head)
    before = legacy.read_bytes()
    result = _deploy(repo, bin_dir, "rel-001")
    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    assert "data/v2/cbrowser.db" in output
    assert "restore" in output.lower()
    assert "NOT moved" in output
    assert legacy.read_bytes() == before
    assert not (
        repo / ".fake-state" / "volumes" / "cbrowser-db" / "cbrowser.db"
    ).exists()


def _valid_font_set(root: Path) -> None:
    font = b"fake font bytes"
    set_dir = root / "windows" / "set-1"
    set_dir.mkdir(parents=True)
    (set_dir / "Arial.ttf").write_bytes(font)
    manifest = {
        "files": [
            {"name": "Arial.ttf", "sha256": hashlib.sha256(font).hexdigest()}
        ]
    }
    (set_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_fonts_preflight_warns_and_continues(tmp_path: Path) -> None:
    """AC-009/AC-010: a missing fonts directory warns but never blocks."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    result = _deploy(repo, bin_dir, "rel-001")
    assert result.returncode == 0, result.stderr
    assert "WARNING" in result.stdout
    assert "fonts directory" in result.stdout


def test_fonts_preflight_ok_with_valid_set(tmp_path: Path) -> None:
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    _valid_font_set(repo / "data" / "fonts")
    result = _deploy(repo, bin_dir, "rel-001")
    assert result.returncode == 0, result.stderr
    assert "font sets ok" in result.stdout
    assert "windows/set-1" in result.stdout


def test_instance_identity_deterministic_across_releases(
    tmp_path: Path,
) -> None:
    """A59: the instance id and media pool are stable across releases
    and recorded in the manifest and the release env."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    assert _deploy(repo, bin_dir, "rel-002").returncode == 0
    first, second = _manifest(repo, "rel-001"), _manifest(repo, "rel-002")
    assert first["instance"]["instance_id"] == second["instance"]["instance_id"]
    assert (
        first["instance"]["media_subnet_pool"]
        == second["instance"]["media_subnet_pool"]
    )
    instance_id, pool, edge_subnet = _instance_identity(repo)
    assert first["instance"]["instance_id"] == instance_id
    assert first["instance"]["media_subnet_pool"] == pool
    assert first["instance"]["edge_subnet"] == edge_subnet
    env1 = (repo / "config" / "deploy" / "releases" / "rel-001.env").read_text(
        encoding="utf-8"
    )
    assert f"CBROWSER_INSTANCE_ID={instance_id}" in env1
    assert f"CBROWSER_MEDIA_SUBNET_POOL={pool}" in env1
    assert f"CBROWSER_EDGE_SUBNET={edge_subnet}" in env1
    assert f"CBROWSER_TRUSTED_PROXY_CIDRS={edge_subnet}" in env1
    assert first["database_backup"] is None


def test_db_volume_inspectable_after_deploy(tmp_path: Path) -> None:
    """AC-001: the deploy uses the named database volume."""
    repo = _make_fake_repo(tmp_path)
    bin_dir = _make_fake_bin(tmp_path)
    assert _deploy(repo, bin_dir, "rel-001").returncode == 0
    state = repo / ".fake-state"
    env = {
        "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
        "FAKE_DOCKER_LOG": str(state / "docker.log"),
        "FAKE_DOCKER_STATE": str(state),
    }
    found = subprocess.run(
        [str(bin_dir / "docker"), "volume", "inspect", "cbrowser-db"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert found.returncode == 0
    missing = subprocess.run(
        [str(bin_dir / "docker"), "volume", "inspect", "cbrowser-db-missing"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert missing.returncode != 0
