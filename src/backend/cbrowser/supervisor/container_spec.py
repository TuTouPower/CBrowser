"""Stateless container command, environment and label specifications."""

from __future__ import annotations

from typing import Any


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
) -> dict[str, Any]:
    return {
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.profile-id": profile_id,
        "com.cbrowser.instance-id": runtime_instance_id,
        "com.cbrowser.role": "stream",
        "com.cbrowser.network-policy": "v1",
        "com.cbrowser.config-version": config_version,
        "com.cbrowser.prefix": prefix,
    }


def policy_helper_labels(prefix: str, instance_id: str) -> dict[str, str]:
    return {
        "com.cbrowser.prefix": prefix,
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": "network-policy",
        "com.cbrowser.instance-id": instance_id,
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
    media_addresses: dict[str, str] | None,
    screen_width: int | None,
    screen_height: int | None,
) -> dict[str, Any]:
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
        "CBROWSER_AUDIO_DEVICE": "cbrowser_sink.monitor",
        "CBROWSER_PULSE_DIR": "/pulse",
        "CBROWSER_X11_SOCKET": "/tmp/.X11-unix/X99",
        "SELKIES_PORT": "18096",
    }
    if screen_width is not None and screen_height is not None:
        env["CBROWSER_SCREEN_WIDTH"] = str(screen_width)
        env["CBROWSER_SCREEN_HEIGHT"] = str(screen_height)
    if media_addresses is not None:
        env.update(
            {
                "SELKIES_STUN_HOST": media_addresses["coturn_ip"],
                "SELKIES_STUN_PORT": "3478",
                "SELKIES_TURN_HOST": media_addresses["coturn_ip"],
                "SELKIES_TURN_PORT": "3478",
            }
        )
    return env


def stream_ports(udp_mux_port: int) -> dict[str, tuple[str, int]]:
    return {f"{udp_mux_port}/udp": ("127.0.0.1", udp_mux_port)}
