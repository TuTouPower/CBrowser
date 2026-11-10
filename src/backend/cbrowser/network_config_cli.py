import argparse
import json
import logging
import shlex
import sys
from pathlib import Path

from cbrowser.domain.models import AppliedNetworkAccessVersion, NetworkAccessConfig
from cbrowser.network_config import (
    APPLIED_VERSION_FILENAME,
    CADDYFILE_FILENAME,
    build_applied_network_version,
    compute_caddyfile_sha256,
    derive_origin_whitelist,
    write_applied_network_state,
)

logger = logging.getLogger("cbrowser.network_config_cli")

EXIT_MISSING = 3
EXIT_CORRUPT = 4


class ConfigMissing(Exception):
    pass


class ConfigCorrupt(Exception):
    pass


def _paths(network_dir: Path) -> tuple[Path, Path]:
    return network_dir / APPLIED_VERSION_FILENAME, network_dir / CADDYFILE_FILENAME


def _presence(network_dir: Path) -> str:
    version_file, caddy_file = _paths(network_dir)
    has_v = version_file.is_file()
    has_c = caddy_file.is_file()
    if has_v and has_c:
        return "both"
    if not has_v and not has_c:
        return "none"
    return "partial"


def _load_validated(network_dir: Path) -> AppliedNetworkAccessVersion:
    state = _presence(network_dir)
    if state == "none":
        raise ConfigMissing(
            f"applied network state missing in {network_dir}; run init first"
        )
    if state == "partial":
        raise ConfigCorrupt(
            f"incomplete applied network state in {network_dir}: "
            f"{APPLIED_VERSION_FILENAME} and {CADDYFILE_FILENAME} must both be present"
        )
    version_file, caddy_file = _paths(network_dir)
    try:
        data = json.loads(version_file.read_text(encoding="utf-8"))
        ver = AppliedNetworkAccessVersion.model_validate(data)
        caddy_text = caddy_file.read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        raise ConfigCorrupt(
            f"malformed applied network state in {network_dir}: {e}"
        ) from e
    actual = compute_caddyfile_sha256(caddy_text)
    if ver.caddyfile_sha256 != actual:
        raise ConfigCorrupt(
            f"caddyfile_sha256 mismatch in {network_dir}: "
            f"recorded {ver.caddyfile_sha256} != computed {actual}"
        )
    if ver.origin_whitelist != derive_origin_whitelist(ver.config):
        raise ConfigCorrupt(
            f"origin_whitelist inconsistent with applied config in {network_dir}"
        )
    return ver


def _init(network_dir: Path, https_port: int) -> None:
    if _presence(network_dir) == "none":
        ver, caddy_text = build_applied_network_version(
            NetworkAccessConfig(lan_access_enabled=False, https_port=https_port),
            version=1,
        )
        write_applied_network_state(network_dir, ver, caddy_text)
        logger.info(
            "initialized applied network state in %s (port %s, sha256 %s)",
            network_dir,
            ver.config.https_port,
            ver.caddyfile_sha256,
        )
        return
    ver = _load_validated(network_dir)
    logger.info(
        "applied network state already present (version %s, port %s); kept unchanged",
        ver.version,
        ver.config.https_port,
    )


def _shell_assignments(ver: AppliedNetworkAccessVersion) -> str:
    lines = [
        f"BIND_HOST={shlex.quote(ver.bind_host)}",
        f"HTTPS_PORT={ver.config.https_port}",
        f"PUBLIC_ORIGIN={shlex.quote(ver.origin_whitelist[0])}",
        f"CADDYFILE_SHA256={shlex.quote(ver.caddyfile_sha256)}",
        f"LAN_ACCESS_ENABLED={1 if ver.config.lan_access_enabled else 0}",
        f"LAN_ADVERTISED_IP={shlex.quote(ver.config.lan_advertised_ip or '')}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr
    )
    parser = argparse.ArgumentParser(prog="cbrowser.network_config_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    init_parser = sub.add_parser("init")
    init_parser.add_argument("--network-dir", required=True, type=Path)
    init_parser.add_argument("--https-port", required=True, type=int)
    read_parser = sub.add_parser("read")
    read_parser.add_argument("--network-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            _init(args.network_dir, args.https_port)
        else:
            ver = _load_validated(args.network_dir)
            sys.stdout.write(_shell_assignments(ver))
        return 0
    except ConfigMissing as e:
        logger.error("missing: %s", e)
        return EXIT_MISSING
    except ConfigCorrupt as e:
        logger.error("corrupt: %s", e)
        return EXIT_CORRUPT
    except ValueError as e:
        logger.error("invalid network configuration: %s", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
