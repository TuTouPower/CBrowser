"""Stateless container command, environment and label specifications."""

from __future__ import annotations

from typing import Any

from cbrowser.udp_mux import udp_mux_bounds


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


def browser_labels(
    prefix: str,
    profile_id: str,
    runtime_instance_id: str,
    config_version: Any,
) -> dict[str, str]:
    return {
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.profile-id": profile_id,
        "com.cbrowser.instance-id": runtime_instance_id,
        "com.cbrowser.role": "browser",
        "com.cbrowser.network-policy": "v1",
        "com.cbrowser.config-version": str(config_version),
        "com.cbrowser.prefix": prefix,
    }


def stream_labels(
    prefix: str,
    profile_id: str,
    runtime_instance_id: str,
    config_version: Any,
) -> dict[str, str]:
    return {
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.profile-id": profile_id,
        "com.cbrowser.instance-id": runtime_instance_id,
        "com.cbrowser.role": "stream",
        "com.cbrowser.network-policy": "v1",
        "com.cbrowser.config-version": str(config_version),
        "com.cbrowser.prefix": prefix,
    }


def policy_helper_labels(prefix: str, instance_id: str) -> dict[str, str]:
    return {
        "com.cbrowser.prefix": prefix,
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": "network-policy",
        "com.cbrowser.instance-id": instance_id,
    }


def x11_helper_labels(prefix: str) -> dict[str, str]:
    return {
        "com.cbrowser.prefix": prefix,
        "com.cbrowser.role": "x11-permissions",
        "com.cbrowser.managed-by": "supervisor",
    }


def cache_init_labels(prefix: str) -> dict[str, str]:
    return {
        "com.cbrowser.prefix": prefix,
        "com.cbrowser.role": "cache-init",
        "com.cbrowser.managed-by": "supervisor",
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


def stream_ports(udp_mux_port: int) -> dict[str, tuple[str, int]]:
    return {f"{udp_mux_port}/udp": ("127.0.0.1", udp_mux_port)}
