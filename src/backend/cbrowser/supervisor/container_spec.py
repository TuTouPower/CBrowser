"""Stateless container command, environment and label specifications."""

from __future__ import annotations

import re
from typing import Any

from cbrowser.udp_mux import udp_mux_bounds

# A22: one prefix rule shared by deploy.sh and the Supervisor. Lowercase
# letters, digits and underscores only -- no hyphen, so the prefix
# namespace never overlaps ``<prefix>-profiles`` or ``<prefix>-<NNNN>``.
RESOURCE_PREFIX_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*$")


def validate_resource_prefix(prefix: str) -> str:
    """Validate a resource prefix (A22); return it unchanged or raise.

    The deployment entry points validate prefixes supplied as deployment
    input: deploy.sh validates its ``CBROWSER_PREFIX`` and the Supervisor
    startup (runner main) validates a prefix supplied via ``--prefix`` or
    ``CBROWSER_PREFIX``. The compiled-in default prefix is a fixed product
    identifier that predates this rule and is not deployment input, so it
    is not validated; DockerAdapter construction does not validate either
    (it receives the startup-validated value or the default). The pure
    label helpers below deliberately do not validate, so direct label
    construction in tests keeps working.
    """
    if not RESOURCE_PREFIX_PATTERN.match(prefix):
        raise ValueError(
            "resource prefix must match ^[a-z0-9][a-z0-9_]*$ "
            f"(lowercase, digits, underscores; no hyphen): {prefix!r}"
        )
    return prefix


def gated_entrypoint(instance_id: str, role: str) -> list[str]:
    return [
        "/usr/bin/tini",
        "-g",
        "--",
        "python3",
        "/run/cbrowser_policy/startup_gate.py",
        "--instance-id",
        instance_id,
        "--role",
        role,
        "--",
        "/app/entrypoint.sh",
    ]


def browser_command(
    profile_id: str, runtime_instance_id: str, display: str
) -> list[str]:
    return [
        "--profile-id",
        profile_id,
        "--runtime-instance-id",
        runtime_instance_id,
        "--config-snapshot",
        "/run/cbrowser/runtime/snapshot.json",
        "--run-dir",
        "/run/cbrowser/runtime",
        "--user-data-dir",
        f"/data/profiles/{profile_id}/profile",
        "--events-dir",
        f"/data/runtime-events/{profile_id}",
        "--engine-cache-dir",
        "/data/engine-cache",
        "--download-dir",
        "/exchange/downloads",
        "--display",
        display,
    ]


def sandbox_compose_labels(
    prefix: str, service: str, profile_number: int
) -> dict[str, str]:
    """Group every Profile sandbox under one pseudo compose project.

    Docker Desktop groups containers by ``com.docker.compose.project`` and
    offers no arbitrary-label grouping. Sandboxes are created dynamically
    by the Supervisor, so they carry these labels explicitly to appear as
    a single ``<prefix>-profiles`` group instead of unrelated containers.
    The compose service carries the zero-padded profile number
    (``<NNNN>-browser`` / ``<NNNN>-stream``), so each Profile's sandboxes
    are distinguishable inside the shared group.
    Ownership is NOT decided by the pseudo project: the deploy prefix
    conflict check and the Supervisor scan use the
    ``com.cbrowser.instance-id`` label (the deployment instance id) as
    the sole ownership test.
    """
    return {
        "com.docker.compose.project": f"{prefix}-profiles",
        "com.docker.compose.service": f"{profile_number:04d}-{service}",
    }


def _instance_label(deployment_id: str | None) -> dict[str, str]:
    # ``com.cbrowser.instance-id`` carries the deployment instance id
    # (A59/AC-021): it is the sole ownership test for every resource the
    # deployment creates. Absent (not empty) when unconfigured: an
    # unlabelled container is never claimed as ours. The per-launch
    # runtime instance id is NOT a label; it travels in the container's
    # runtime configuration (see ``container_runtime_instance_id``).
    return (
        {"com.cbrowser.instance-id": deployment_id} if deployment_id else {}
    )


def container_runtime_instance_id(container: Any) -> str | None:
    """Recover a sandbox's per-launch runtime instance id from its config.

    The runtime id is written into the container specification at
    creation time -- the Stream environment
    (``CBROWSER_RUNTIME_INSTANCE_ID``), the Browser agent environment
    (``RUNTIME_INSTANCE_ID``), the gated entrypoint (``--instance-id``)
    and the Browser command (``--runtime-instance-id``) -- so it is read
    back from the inspected configuration (``attrs["Config"]``), falling
    back to the list summary's ``Command`` string, which carries the
    same entrypoint arguments. Labels are not used:
    ``com.cbrowser.instance-id`` denotes the owning deployment instance,
    not the runtime session.
    """
    attrs = getattr(container, "attrs", None) or {}
    config = attrs.get("Config") or {}
    for entry in config.get("Env") or []:
        if entry.startswith(
            ("CBROWSER_RUNTIME_INSTANCE_ID=", "RUNTIME_INSTANCE_ID=")
        ):
            return entry.split("=", 1)[1] or None
    args = list(config.get("Entrypoint") or []) + list(config.get("Cmd") or [])
    if not args:
        args = str(attrs.get("Command") or "").split()
    for flag in ("--instance-id", "--runtime-instance-id"):
        if flag in args:
            index = args.index(flag)
            if index + 1 < len(args):
                return args[index + 1]
    return None


def browser_labels(
    prefix: str,
    profile_id: str,
    config_version: Any,
    profile_number: int,
    deployment_id: str | None = None,
) -> dict[str, str]:
    return {
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.profile-id": profile_id,
        "com.cbrowser.role": "browser",
        "com.cbrowser.network-policy": "v1",
        "com.cbrowser.config-version": str(config_version),
        "com.cbrowser.prefix": prefix,
        "com.cbrowser.profile-number": f"{profile_number:04d}",
        **_instance_label(deployment_id),
        **sandbox_compose_labels(prefix, "browser", profile_number),
    }


def stream_labels(
    prefix: str,
    profile_id: str,
    config_version: Any,
    profile_number: int,
    bind_host: str = "127.0.0.1",
    advertised_ip: str = "127.0.0.1",
    deployment_id: str | None = None,
) -> dict[str, str]:
    return {
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.profile-id": profile_id,
        "com.cbrowser.role": "stream",
        "com.cbrowser.network-policy": "v1",
        "com.cbrowser.config-version": str(config_version),
        "com.cbrowser.prefix": prefix,
        "com.cbrowser.stream.bind-host": bind_host,
        "com.cbrowser.stream.advertised-ip": advertised_ip,
        "com.cbrowser.profile-number": f"{profile_number:04d}",
        **_instance_label(deployment_id),
        **sandbox_compose_labels(prefix, "stream", profile_number),
    }


def policy_helper_labels(
    prefix: str, deployment_id: str | None = None
) -> dict[str, str]:
    return {
        "com.cbrowser.prefix": prefix,
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": "network-policy",
        **_instance_label(deployment_id),
    }


def x11_helper_labels(
    prefix: str, deployment_id: str | None = None
) -> dict[str, str]:
    return {
        "com.cbrowser.prefix": prefix,
        "com.cbrowser.role": "x11-permissions",
        "com.cbrowser.managed-by": "supervisor",
        **_instance_label(deployment_id),
    }


def cache_init_labels(
    prefix: str, deployment_id: str | None = None
) -> dict[str, str]:
    return {
        "com.cbrowser.prefix": prefix,
        "com.cbrowser.role": "cache-init",
        "com.cbrowser.managed-by": "supervisor",
        **_instance_label(deployment_id),
    }


def cache_init_environment(
    need_geoip: bool, marker_name: str, run_id: str
) -> dict[str, str]:
    return {
        "PYTHONDONTWRITEBYTECODE": "1",
        "CLOAKBROWSER_CACHE_DIR": "/data/engine-cache",
        "CBROWSER_INIT_GEOIP": "1" if need_geoip else "0",
        "CBROWSER_INIT_MARKER": marker_name,
        "CBROWSER_INIT_RUN_ID": run_id,
    }


def stream_environment(
    *,
    public_ip: str,
    display: str,
    profile_id: str,
    runtime_instance_id: str,
    gateway_url: str,
    config_version: Any,
    udp_mux_port: int,
    screen_width: int | None,
    screen_height: int | None,
    clipboard_sync: bool = True,
    build_id: str | None = None,
) -> dict[str, Any]:
    udp_mux_min, udp_mux_max = udp_mux_bounds()
    env = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "CBROWSER_WEBRTC_PUBLIC_IP": public_ip,
        "DISPLAY": display,
        "XAUTHORITY": "/tmp/.Xauthority",
        "CBROWSER_PROFILE_ID": profile_id,
        "CBROWSER_RUNTIME_INSTANCE_ID": runtime_instance_id,
        "CBROWSER_GATEWAY_URL": gateway_url,
        "CBROWSER_CONFIG_VERSION": config_version,
        "CBROWSER_AGENT_SECRET_FILE": "/tmp/secret.txt",
        "CBROWSER_SELKIES_CREDENTIALS_FILE": "/tmp/selkies_credentials.json",
        "CBROWSER_UDP_MUX_PORT": str(udp_mux_port),
        "CBROWSER_UDP_MUX_MIN_PORT": str(udp_mux_min),
        "CBROWSER_UDP_MUX_MAX_PORT": str(udp_mux_max),
        "CBROWSER_AUDIO_DEVICE": "cbrowser_sink.monitor",
        "CBROWSER_PULSE_DIR": "/pulse",
        "CBROWSER_X11_SOCKET": "/tmp/.X11-unix/X99",
        "SELKIES_PORT": "18096",
        "SELKIES_MODE": "webrtc",
        "SELKIES_WEBRTC_ICE_LITE": "true",
        "SELKIES_ENABLE_DUAL_MODE": "false",
        "SELKIES_ENABLE_SHARING": "true",
        "SELKIES_ENABLE_COLLAB": "false",
        "SELKIES_FILE_TRANSFERS": "none",
        "SELKIES_ENABLE_CLIPBOARD": "true" if clipboard_sync else "false",
        "SELKIES_ENABLE_BINARY_CLIPBOARD": "false|locked",
        "SELKIES_CLIPBOARD_SEAMLESS": "true|locked",
    }
    if screen_width is not None and screen_height is not None:
        env["CBROWSER_SCREEN_WIDTH"] = str(screen_width)
        env["CBROWSER_SCREEN_HEIGHT"] = str(screen_height)
    if build_id:
        env["CBROWSER_BUILD_ID"] = build_id
    return env


def stream_ports(udp_mux_port: int, bind_host: str = "127.0.0.1") -> dict[str, tuple[str, int]]:
    return {f"{udp_mux_port}/udp": (bind_host, udp_mux_port)}
