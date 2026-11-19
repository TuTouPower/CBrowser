"""Named-volume and minimal verified font-set helpers for Docker E2E fixtures.

t080 / ADR 029 moved API, Supervisor, Browser, and Stream persistence onto
explicit Docker named volumes managed by ``MountPlanner``, and t075 requires
every Profile to bind a verified platform font set.  These helpers provide a
single, fail-closed way for E2E harnesses and direct-Docker E2E suites to:

1. Prepare a minimal real verified platform font root (reusing real platform
   fonts from ``CBROWSER_E2E_FONTS_DIR`` or base fonts in the Browser image).
2. Create and initialize ``<prefix>-{db,data,runtime,fonts}`` volumes cleanly on
   Docker Desktop (macOS) and Linux Docker engines alike.
3. Build production-equivalent ``docker.types.Mount`` specs (including
   ``gates``, ``sockets``, and ``policy-agents`` runtime subpaths).
4. Execute isolated Python verification or Supervisor/Adapter drivers against
   those named volumes and remove every prefixed volume in cleanup.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tarfile
from pathlib import Path
from typing import Any

import docker
from docker.errors import APIError, NotFound
from docker.types import Mount

from cbrowser.font_sets import import_font_set
from cbrowser.shared.storage_layout import (
    DATA_VOLUME_LAYOUT,
    FONTS_VOLUME_LAYOUT,
    RUNTIME_GATES_PREFIX,
    RUNTIME_GID,
    RUNTIME_POLICY_AGENTS_PREFIX,
    RUNTIME_SOCKETS_PREFIX,
    RUNTIME_UID,
    RUNTIME_VOLUME_LAYOUT,
)
from cbrowser.supervisor.gate_identity import gate_labels
from cbrowser.supervisor.network_policy import NetworkPolicySpec
from cbrowser.supervisor.policy_agent_client import (
    PolicyAgentRejected,
    PolicyAgentUnavailable,
)
from cbrowser.supervisor.policy_agent_protocol import PolicyAgentIdentity
from cbrowser.supervisor.storage_layout import volume_name
from e2e_env import complete_font_set_dir

E2E_RESULT_MARKER = "CBROWSER_E2E_RESULT="
ALL_VOLUME_ROLES: tuple[str, ...] = ("db", "data", "runtime", "fonts")

_LATIN_FONT_CANDIDATES = ("arial.ttf", "cour.ttf", "times.ttf")
_CJK_FONT_CANDIDATES = ("msyh.ttc", "simsun.ttc", "simhei.ttf", "msyhl.ttc")
_BASE_LATIN_PATH = "/opt/cbrowser-base-fonts/truetype/freefont/FreeSans.ttf"
_BASE_CJK_PATH = "/opt/cbrowser-base-fonts/truetype/wqy/wqy-zenhei.ttc"


def is_real_docker_client(client: Any) -> bool:
    """Return True when ``client`` is a live ``docker.DockerClient`` instance."""
    return isinstance(client, docker.DockerClient)


def _select_font_files(set_dir: Path) -> list[Path]:
    """Pick one verified Latin face and one CJK face from a full platform set."""
    latin: Path | None = None
    for candidate in _LATIN_FONT_CANDIDATES:
        path = set_dir / candidate
        if path.is_file():
            latin = path
            break
    if latin is None:
        ttf_files = sorted(
            (
                p
                for p in set_dir.iterdir()
                if p.is_file()
                and p.suffix.lower() in {".ttf", ".otf"}
                and p.name != "manifest.json"
            ),
            key=lambda p: p.stat().st_size,
        )
        if ttf_files:
            latin = ttf_files[0]

    cjk: Path | None = None
    for candidate in _CJK_FONT_CANDIDATES:
        path = set_dir / candidate
        if path.is_file():
            cjk = path
            break
    if cjk is None:
        ttc_files = sorted(
            (
                p
                for p in set_dir.iterdir()
                if p.is_file() and p.suffix.lower() == ".ttc"
            ),
            key=lambda p: p.stat().st_size,
        )
        if ttc_files:
            cjk = ttc_files[0]

    selected = [p for p in (latin, cjk) if p is not None]
    if not selected:
        raise RuntimeError(f"No usable font files found in {set_dir}")
    return selected


def _extract_base_fonts_from_image(
    client: docker.DockerClient,
    browser_image: str,
    staging_dir: Path,
) -> list[Path]:
    """Extract compact Latin + CJK base fonts directly from ``browser_image``."""
    extracted: list[Path] = []
    container = client.containers.create(
        browser_image,
        entrypoint="true",
        labels=gate_labels({"com.cbrowser.role": "e2e-font-extract"}),
    )
    try:
        for container_path in (_BASE_LATIN_PATH, _BASE_CJK_PATH):
            stream, _ = container.get_archive(container_path)
            raw = b"".join(stream)
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    extracted_handle = tf.extractfile(member)
                    if extracted_handle is None:
                        continue
                    target = staging_dir / Path(member.name).name
                    target.write_bytes(extracted_handle.read())
                    extracted.append(target)
    finally:
        container.remove(force=True)
    if len(extracted) < 2:
        raise RuntimeError(
            f"Expected base Latin + CJK fonts from {browser_image}, got {extracted}"
        )
    return extracted


def prepare_minimal_e2e_fonts_root(
    dest_root: Path,
    *,
    browser_image: str | None = None,
    docker_client: Any | None = None,
) -> tuple[Path, str]:
    """Create a small, manifest-verified ``windows`` font root under ``dest_root``.

    Prefers ``CBROWSER_E2E_FONTS_DIR`` when set so official Windows Latin + CJK
    faces are imported (~20 MB instead of copying >1 GB per test); falls back to
    base fonts inside ``browser_image`` when running without host font assets.
    """
    dest_root.mkdir(parents=True, exist_ok=True)
    for platform_dir in FONTS_VOLUME_LAYOUT:
        (dest_root / platform_dir).mkdir(parents=True, exist_ok=True)

    windows_dir = dest_root / "windows"
    existing = complete_font_set_dir("windows", dest_root)
    if existing is not None:
        return dest_root, existing.name

    staging = dest_root / "_staging_import"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        env_fonts = os.environ.get("CBROWSER_E2E_FONTS_DIR", "").strip()
        src_set = complete_font_set_dir("windows", env_fonts) if env_fonts else None
        if src_set is not None:
            for src_file in _select_font_files(src_set):
                shutil.copy2(src_file, staging / src_file.name)
            source_version = "e2e-minimal"
        else:
            img = browser_image or os.environ.get("CBROWSER_RUNTIME_TEST_IMAGE", "").strip()
            if not img:
                raise RuntimeError(
                    "Neither CBROWSER_E2E_FONTS_DIR nor CBROWSER_RUNTIME_TEST_IMAGE is set"
                )
            owns_client = docker_client is None
            client = docker_client or docker.from_env()
            try:
                _extract_base_fonts_from_image(client, img, staging)
            finally:
                if owns_client:
                    client.close()
            source_version = "e2e-base-minimal"

        info = import_font_set(
            "windows",
            [staging],
            source_version,
            root=dest_root,
            source="e2e-fixture",
        )
        return dest_root, str(info["set_id"])
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        # Keep existing layout clean if empty folders lingered.
        windows_dir.mkdir(parents=True, exist_ok=True)


def create_prefix_volumes(
    client: Any,
    prefix: str,
    *,
    roles: tuple[str, ...] = ALL_VOLUME_ROLES,
    extra_labels: dict[str, str] | None = None,
) -> dict[str, str]:
    """Ensure labelled Docker named volumes exist for ``prefix`` and return map."""
    names = {role: volume_name(prefix, role) for role in roles}
    volumes_api = getattr(client, "volumes", None)
    if volumes_api is None:
        return names
    for role, vol_name in names.items():
        labels = gate_labels(
            {
                "com.cbrowser.prefix": prefix,
                "com.cbrowser.managed-by": "supervisor",
                "com.cbrowser.role": f"volume-{role}",
                **(extra_labels or {}),
            }
        )
        volumes_api.create(name=vol_name, labels=labels)
    return names


def remove_prefix_volumes(
    client: Any,
    prefix: str,
    *,
    ignore_missing: bool = True,
) -> list[str]:
    """Delete only volumes whose ownership label matches ``prefix``."""
    errors: list[str] = []
    volumes_api = getattr(client, "volumes", None)
    if volumes_api is None:
        return errors
    try:
        listed = volumes_api.list(filters={"label": f"com.cbrowser.prefix={prefix}"})
    except APIError as exc:
        errors.append(f"volume_list:{type(exc).__name__}")
        return errors
    if not isinstance(listed, (list, tuple)):
        return errors
    for volume in listed:
        labels = (getattr(volume, "attrs", None) or {}).get("Labels") or {}
        if labels.get("com.cbrowser.prefix") != prefix:
            continue
        try:
            volume.remove(force=True)
        except NotFound:
            if not ignore_missing:
                errors.append(f"volume_not_found:{getattr(volume, 'name', '')}")
        except APIError as exc:
            errors.append(f"volume_remove:{type(exc).__name__}")
    return errors


_INIT_VOLUMES_SCRIPT = r"""
import json
import os
import shutil
from pathlib import Path

prefix = os.environ["CB_INIT_PREFIX"]
uid = int(os.environ["CB_RUNTIME_UID"])
gid = int(os.environ["CB_RUNTIME_GID"])

DATA_LAYOUT = json.loads(os.environ["CB_DATA_LAYOUT"])
RUNTIME_LAYOUT = json.loads(os.environ["CB_RUNTIME_LAYOUT"])
FONTS_LAYOUT = json.loads(os.environ["CB_FONTS_LAYOUT"])


def chown_tree(root: Path, *, set_world_read: bool = False) -> None:
    if not root.exists():
        return
    os.chown(root, uid, gid)
    for cur_root, dirs, files in os.walk(root):
        cur_p = Path(cur_root)
        os.chown(cur_p, uid, gid)
        if set_world_read:
            os.chmod(cur_p, 0o755)
        for name in dirs:
            dp = cur_p / name
            if not dp.is_symlink():
                os.chown(dp, uid, gid)
                if set_world_read:
                    os.chmod(dp, 0o755)
        for name in files:
            fp = cur_p / name
            if not fp.is_symlink():
                os.chown(fp, uid, gid)
                if set_world_read:
                    mode = os.stat(fp).st_mode & 0o777
                    os.chmod(fp, 0o755 if (mode & 0o111) else 0o644)


def ensure_tree(root: Path, subpaths: list[str], kind: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    os.chown(root, uid, gid)
    for rel in subpaths:
        cur = root
        for part in Path(rel).parts:
            cur = cur / part
            cur.mkdir(exist_ok=True)
            os.chown(cur, uid, gid)
    marker = root / ".cbrowser-volume.json"
    marker.write_text(
        json.dumps({"prefix": prefix, "volume": f"{prefix}-{kind}"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chown(marker, uid, gid)


if Path("/vols/db").exists():
    ensure_tree(Path("/vols/db"), [], "db")

if Path("/vols/data").exists():
    ensure_tree(Path("/vols/data"), DATA_LAYOUT, "data")
    src_ec = Path("/src/engine-cache")
    dst_ec = Path("/vols/data/engine-cache")
    if src_ec.is_dir():
        shutil.copytree(src_ec, dst_ec, dirs_exist_ok=True)
    src_geo = Path("/src/geoip")
    dst_geo = dst_ec / "geoip"
    if src_geo.is_dir():
        shutil.copytree(src_geo, dst_geo, dirs_exist_ok=True)
    chown_tree(dst_ec, set_world_read=True)

if Path("/vols/runtime").exists():
    ensure_tree(Path("/vols/runtime"), RUNTIME_LAYOUT, "runtime")
    # Policy Agent runs as uid 0 with cap_drop=["ALL"] (no DAC_OVERRIDE), so its
    # socket directory must be owned by 0:0 (matching Supervisor slot mkdir).
    policy_agents_dir = Path("/vols/runtime/policy-agents")
    if policy_agents_dir.exists():
        os.chown(policy_agents_dir, 0, 0)
        os.chmod(policy_agents_dir, 0o700)
    secrets_dir = Path("/vols/runtime/.secrets")
    secrets_dir.mkdir(exist_ok=True)
    os.chown(secrets_dir, 0, 0)
    os.chmod(secrets_dir, 0o700)

if Path("/vols/fonts").exists():
    ensure_tree(Path("/vols/fonts"), FONTS_LAYOUT, "fonts")
    src_fonts = Path("/src/fonts")
    if src_fonts.is_dir():
        for child in src_fonts.iterdir():
            if child.name.startswith("_staging"):
                continue
            target = Path("/vols/fonts") / child.name
            if child.is_dir():
                shutil.copytree(child, target, dirs_exist_ok=True)
        chown_tree(Path("/vols/fonts"), set_world_read=True)
"""


def init_prefix_volumes(
    client: Any,
    prefix: str,
    helper_image: str,
    *,
    roles: tuple[str, ...] = ALL_VOLUME_ROLES,
    engine_cache_src: Path | None = None,
    geoip_cache_src: Path | None = None,
    fonts_root_src: Path | None = None,
    extra_labels: dict[str, str] | None = None,
) -> dict[str, str]:
    """Create and seed ``<prefix>-*`` volumes via one throwaway helper container."""
    volumes = create_prefix_volumes(client, prefix, roles=roles, extra_labels=extra_labels)
    if not is_real_docker_client(client):
        return volumes

    mounts = [
        Mount(target=f"/vols/{role}", source=vol_name, type="volume", read_only=False)
        for role, vol_name in volumes.items()
    ]
    if engine_cache_src is not None:
        mounts.append(
            Mount(
                target="/src/engine-cache",
                source=str(Path(engine_cache_src).resolve()),
                type="bind",
                read_only=True,
            )
        )
    if geoip_cache_src is not None:
        mounts.append(
            Mount(
                target="/src/geoip",
                source=str(Path(geoip_cache_src).resolve()),
                type="bind",
                read_only=True,
            )
        )
    if fonts_root_src is not None:
        mounts.append(
            Mount(
                target="/src/fonts",
                source=str(Path(fonts_root_src).resolve()),
                type="bind",
                read_only=True,
            )
        )

    helper = client.containers.run(
        helper_image,
        entrypoint="python3",
        command=["-c", _INIT_VOLUMES_SCRIPT],
        detach=True,
        user="0:0",
        read_only=True,
        cap_drop=["ALL"],
        cap_add=["CHOWN", "FOWNER", "DAC_OVERRIDE"],
        security_opt=["no-new-privileges:true"],
        tmpfs={"/tmp": "rw,size=256m"},
        mounts=mounts,
        environment={
            "CB_INIT_PREFIX": prefix,
            "CB_RUNTIME_UID": str(RUNTIME_UID),
            "CB_RUNTIME_GID": str(RUNTIME_GID),
            "CB_DATA_LAYOUT": json.dumps(list(DATA_VOLUME_LAYOUT)),
            "CB_RUNTIME_LAYOUT": json.dumps(list(RUNTIME_VOLUME_LAYOUT)),
            "CB_FONTS_LAYOUT": json.dumps(list(FONTS_VOLUME_LAYOUT)),
        },
        labels=gate_labels(
            {
                "com.cbrowser.prefix": prefix,
                "com.cbrowser.managed-by": "supervisor",
                "com.cbrowser.role": "volume-init",
                **(extra_labels or {}),
            }
        ),
    )
    try:
        result = helper.wait(timeout=180)
        logs = helper.logs().decode("utf-8", errors="replace")
        if isinstance(result, dict) and result.get("StatusCode", 0) != 0:
            raise RuntimeError(
                f"Volume initialization helper exited with {result}: {logs}"
            )
    finally:
        helper.remove(force=True)
    return volumes


def api_volume_mounts(
    prefix: str,
    *,
    extra_mounts: list[Mount] | None = None,
) -> list[Mount]:
    """Return ``docker.types.Mount`` specs matching compose API layout."""
    mounts = [
        Mount(target="/data", source=volume_name(prefix, "data"), type="volume"),
        Mount(
            target="/data/runtime",
            source=volume_name(prefix, "runtime"),
            type="volume",
        ),
        Mount(target="/data/db", source=volume_name(prefix, "db"), type="volume"),
        Mount(
            target="/fonts",
            source=volume_name(prefix, "fonts"),
            type="volume",
            read_only=True,
        ),
    ]
    if extra_mounts:
        mounts.extend(extra_mounts)
    return mounts


def supervisor_volume_mounts(
    prefix: str,
    *,
    data_root: str = "/data",
    socket_root: str = "/run/cb/socks",
    policy_agent_root: str = "/run/cb/policy-agents",
    fonts_root: str = "/fonts",
    mount_docker_sock: bool = True,
    extra_mounts: list[Mount] | None = None,
) -> list[Mount]:
    """Return ``docker.types.Mount`` specs matching compose Supervisor layout."""
    mounts = [
        Mount(target=data_root, source=volume_name(prefix, "data"), type="volume"),
        Mount(
            target=f"{data_root}/runtime",
            source=volume_name(prefix, "runtime"),
            type="volume",
        ),
        Mount(
            target=f"{data_root}/control/gates",
            source=volume_name(prefix, "runtime"),
            type="volume",
            subpath=RUNTIME_GATES_PREFIX,
        ),
        Mount(
            target=socket_root,
            source=volume_name(prefix, "runtime"),
            type="volume",
            subpath=RUNTIME_SOCKETS_PREFIX,
        ),
        Mount(
            target=policy_agent_root,
            source=volume_name(prefix, "runtime"),
            type="volume",
            subpath=RUNTIME_POLICY_AGENTS_PREFIX,
        ),
        Mount(
            target=fonts_root,
            source=volume_name(prefix, "fonts"),
            type="volume",
            read_only=True,
        ),
    ]
    if mount_docker_sock:
        mounts.append(
            Mount(
                target="/var/run/docker.sock",
                source="/var/run/docker.sock",
                type="bind",
                read_only=True,
            )
        )
    if extra_mounts:
        mounts.extend(extra_mounts)
    return mounts


def run_volume_python(
    client: docker.DockerClient,
    prefix: str,
    image: str,
    script: str,
    *,
    roles: tuple[str, ...] = ("data", "runtime", "fonts"),
    mount_docker_sock: bool = False,
    fonts_writable: bool = False,
    extra_mounts: list[Mount] | None = None,
    env: dict[str, str] | None = None,
    args: list[str] | None = None,
    extra_hosts: dict[str, str] | None = None,
    network: str | None = None,
    timeout: int = 300,
) -> tuple[int, str]:
    """Run ``python3 -c <script>`` inside ``image`` mounted to ``<prefix>`` volumes."""
    mounts: list[Mount] = []
    if "db" in roles:
        mounts.append(
            Mount(target="/data/db", source=volume_name(prefix, "db"), type="volume")
        )
    if "data" in roles:
        mounts.append(
            Mount(target="/data", source=volume_name(prefix, "data"), type="volume")
        )
    if "runtime" in roles:
        mounts.extend(
            [
                Mount(
                    target="/data/runtime",
                    source=volume_name(prefix, "runtime"),
                    type="volume",
                ),
                Mount(
                    target="/data/control/gates",
                    source=volume_name(prefix, "runtime"),
                    type="volume",
                    subpath=RUNTIME_GATES_PREFIX,
                ),
                Mount(
                    target="/run/cb/socks",
                    source=volume_name(prefix, "runtime"),
                    type="volume",
                    subpath=RUNTIME_SOCKETS_PREFIX,
                ),
                Mount(
                    target="/run/cb/policy-agents",
                    source=volume_name(prefix, "runtime"),
                    type="volume",
                    subpath=RUNTIME_POLICY_AGENTS_PREFIX,
                ),
            ]
        )
    if "fonts" in roles:
        mounts.append(
            Mount(
                target="/fonts",
                source=volume_name(prefix, "fonts"),
                type="volume",
                read_only=not fonts_writable,
            )
        )
    if mount_docker_sock:
        mounts.append(
            Mount(
                target="/var/run/docker.sock",
                source="/var/run/docker.sock",
                type="bind",
                read_only=True,
            )
        )
    if extra_mounts:
        mounts.extend(extra_mounts)

    forwarded_env: dict[str, str] = {}
    for key in (
        "CBROWSER_INSTANCE_ID",
        "CBROWSER_MEDIA_SUBNET_POOL",
        "CBROWSER_NETWORK_POLICY_IMAGE",
        "CBROWSER_UDP_MUX_MIN_PORT",
        "CBROWSER_UDP_MUX_MAX_PORT",
        "CBROWSER_ENGINE_BUILD",
        "CBROWSER_ENGINE_BINARY_SHA256",
    ):
        if key in os.environ:
            forwarded_env[key] = os.environ[key]
    if "CBROWSER_MEDIA_SUBNET_POOL" not in forwarded_env and os.environ.get(
        "CBROWSER_E2E_MEDIA_POOL"
    ):
        forwarded_env["CBROWSER_MEDIA_SUBNET_POOL"] = os.environ[
            "CBROWSER_E2E_MEDIA_POOL"
        ]

    container_env = {
        "CBROWSER_DATA_ROOT": "/data",
        "CBROWSER_SOCKET_ROOT": "/run/cb/socks",
        "CBROWSER_POLICY_AGENT_ROOT": "/run/cb/policy-agents",
        "CBROWSER_FONTS_DIR": "/fonts",
        **forwarded_env,
        **(env or {}),
    }
    container = client.containers.run(
        image,
        entrypoint="python3",
        command=["-c", script, *(args or [])],
        detach=True,
        user="0:0",
        read_only=True,
        cap_drop=["ALL"],
        cap_add=["CHOWN", "FOWNER", "DAC_OVERRIDE"],
        security_opt=["no-new-privileges:true"],
        tmpfs={"/tmp": "rw,size=256m"},
        mounts=mounts,
        environment=container_env,
        extra_hosts=extra_hosts,
        network=network,
        labels=gate_labels(
            {
                "com.cbrowser.prefix": prefix,
                "com.cbrowser.managed-by": "supervisor",
                "com.cbrowser.role": "e2e-driver",
            }
        ),
    )
    try:
        result = container.wait(timeout=timeout)
        output = container.logs().decode("utf-8", errors="replace")
        code = int(result.get("StatusCode", 1)) if isinstance(result, dict) else 0
        return code, output
    finally:
        container.remove(force=True)


def run_volume_json(
    client: docker.DockerClient,
    prefix: str,
    image: str,
    script: str,
    **kwargs: Any,
) -> Any:
    """Run ``script`` via :func:`run_volume_python` and parse ``CBROWSER_E2E_RESULT=``."""
    code, output = run_volume_python(client, prefix, image, script, **kwargs)
    if code != 0:
        raise AssertionError(f"Driver container exited with {code}:\n{output}")
    for line in reversed(output.splitlines()):
        if line.startswith(E2E_RESULT_MARKER):
            return json.loads(line[len(E2E_RESULT_MARKER) :])
    raise AssertionError(
        f"Missing {E2E_RESULT_MARKER!r} line in driver output:\n{output}"
    )


def policy_agent_socket_mount(
    prefix: str,
    *,
    target: str = "/run/cbrowser_policy_agent",
) -> Mount:
    """Mount ``<prefix>-runtime`` policy-agents subpath for a standalone Policy Agent."""
    return Mount(
        target=target,
        source=volume_name(prefix, "runtime"),
        type="volume",
        subpath=RUNTIME_POLICY_AGENTS_PREFIX,
        read_only=False,
    )


_POLICY_AGENT_RPC_SCRIPT = r"""
import json
import sys
import time
from pathlib import Path

from cbrowser.supervisor.network_policy import NetworkPolicySpec
from cbrowser.supervisor.policy_agent_client import (
    PolicyAgentClient,
    PolicyAgentRejected,
    PolicyAgentUnavailable,
)
from cbrowser.supervisor.policy_agent_protocol import PolicyAgentIdentity

op = sys.argv[1]
socket_path = Path(sys.argv[2])
identity = PolicyAgentIdentity.model_validate_json(sys.argv[3])
timeout_sec = float(sys.argv[4])
wait_timeout = float(sys.argv[5])
rev = int(sys.argv[6]) if sys.argv[6] != "null" else None
spec = (
    NetworkPolicySpec.model_validate_json(sys.argv[7])
    if sys.argv[7] != "null"
    else None
)

if wait_timeout > 0.0:
    deadline = time.monotonic() + wait_timeout
    while not socket_path.exists():
        if time.monotonic() > deadline:
            print(
                "CBROWSER_E2E_RESULT="
                + json.dumps(
                    {
                        "ok": False,
                        "exc": "TimeoutError",
                        "error_code": "socket_timeout",
                        "msg": f"Policy Agent socket never appeared at {socket_path}",
                    }
                )
            )
            sys.exit(0)
        time.sleep(0.05)

client = PolicyAgentClient(socket_path, identity, timeout=timeout_sec)
try:
    if op == "wait_health":
        deadline = time.monotonic() + max(wait_timeout, 5.0)
        while True:
            try:
                res = client.health()
                break
            except PolicyAgentUnavailable:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)
    elif op == "health":
        res = client.health()
    elif op == "install":
        assert spec is not None and rev is not None
        res = client.install(spec, rev)
    elif op == "inspect":
        assert spec is not None and rev is not None
        res = client.inspect(spec, rev)
    elif op == "fail_close":
        res = client.fail_close()
    else:
        raise ValueError(f"Unsupported op: {op}")
    print("CBROWSER_E2E_RESULT=" + json.dumps({"ok": True, "result": res}))
except PolicyAgentRejected as exc:
    print(
        "CBROWSER_E2E_RESULT="
        + json.dumps(
            {
                "ok": False,
                "exc": "PolicyAgentRejected",
                "error_code": exc.error_code,
                "msg": str(exc),
            }
        )
    )
except PolicyAgentUnavailable as exc:
    print(
        "CBROWSER_E2E_RESULT="
        + json.dumps(
            {
                "ok": False,
                "exc": "PolicyAgentUnavailable",
                "error_code": "unavailable",
                "msg": str(exc),
            }
        )
    )
"""


class ContainerPolicyAgentClient:
    """Volume-backed proxy for :class:`PolicyAgentClient`.

    Executes real ``PolicyAgentClient`` UDS calls inside a short-lived Linux
    container sharing ``<prefix>-runtime`` because macOS VirtioFS bind mounts do
    not forward Unix domain socket ``connect()`` from the host kernel.
    """

    def __init__(
        self,
        docker_client: docker.DockerClient,
        prefix: str,
        helper_image: str,
        identity: PolicyAgentIdentity,
        *,
        socket_path: str = "/run/cb/policy-agents/agent.sock",
        timeout: float = 10.0,
    ) -> None:
        self._client = docker_client
        self._prefix = prefix
        self._helper_image = helper_image
        self._identity_json = identity.model_dump_json()
        self._socket_path = socket_path
        self._timeout = timeout

    def _call_linux(
        self,
        op: str,
        *,
        policy_revision: int | None = None,
        spec: NetworkPolicySpec | None = None,
        wait_timeout: float = 0.0,
    ) -> Any:
        payload = run_volume_json(
            self._client,
            self._prefix,
            self._helper_image,
            _POLICY_AGENT_RPC_SCRIPT,
            roles=("runtime",),
            args=[
                op,
                self._socket_path,
                self._identity_json,
                str(self._timeout),
                str(wait_timeout),
                str(policy_revision) if policy_revision is not None else "null",
                spec.model_dump_json() if spec is not None else "null",
            ],
            timeout=max(60.0, self._timeout + wait_timeout + 10.0),
        )
        if not payload["ok"]:
            exc_name = payload["exc"]
            if exc_name == "PolicyAgentRejected":
                raise PolicyAgentRejected(payload["error_code"])
            if exc_name == "TimeoutError":
                raise TimeoutError(payload["msg"])
            raise PolicyAgentUnavailable(payload["msg"])
        return payload["result"]

    def wait_ready_health(self, timeout_sec: float = 15.0) -> dict[str, Any]:
        return dict(self._call_linux("wait_health", wait_timeout=timeout_sec))

    def health(self) -> dict[str, Any]:
        return dict(self._call_linux("health"))

    def install(self, spec: NetworkPolicySpec, policy_revision: int) -> dict[str, Any]:
        return dict(
            self._call_linux("install", policy_revision=policy_revision, spec=spec)
        )

    def inspect(self, spec: NetworkPolicySpec, policy_revision: int) -> bool:
        return bool(
            self._call_linux("inspect", policy_revision=policy_revision, spec=spec)
        )

    def fail_close(self) -> bool:
        return bool(self._call_linux("fail_close"))
