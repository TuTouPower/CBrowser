"""Deploy-time network CLI: render the Caddyfile for the deployment port.

``render`` deterministically writes ``<network-dir>/Caddyfile`` for the
given HTTPS port and prints the shell assignments deploy.sh evaluates
(bind host is always loopback; the fingerprint is the hash of the
rendered product, never of the generator source). There is no runtime
state to initialize or read back: the Caddyfile itself is the record,
and a deploy re-renders it from the deployment port every time.
"""

import argparse
import logging
import shlex
import sys
from pathlib import Path

from cbrowser.network_config import (
    CADDYFILE_FILENAME,
    compute_caddyfile_sha256,
    derive_origin_whitelist,
    generate_caddyfile,
)
from cbrowser.shared.atomic_write import atomic_write_text

logger = logging.getLogger("cbrowser.network_config_cli")


def _render(network_dir: Path, https_port: int) -> None:
    content = generate_caddyfile(https_port)
    network_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(network_dir / CADDYFILE_FILENAME, content, mode=0o644)
    sha = compute_caddyfile_sha256(content)
    lines = [
        "BIND_HOST=127.0.0.1",
        f"HTTPS_PORT={https_port}",
        f"PUBLIC_ORIGIN={shlex.quote(derive_origin_whitelist(https_port)[0])}",
        f"CADDYFILE_SHA256={shlex.quote(sha)}",
    ]
    sys.stdout.write("\n".join(lines) + "\n")
    logger.info(
        "rendered Caddyfile in %s (port %s, sha256 %s)",
        network_dir,
        https_port,
        sha,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr
    )
    parser = argparse.ArgumentParser(prog="cbrowser.network_config_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    render_parser = sub.add_parser(
        "render", help="render the Caddyfile for the deployment port"
    )
    render_parser.add_argument("--network-dir", required=True, type=Path)
    render_parser.add_argument("--https-port", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "render":
            _render(args.network_dir, args.https_port)
        return 0
    except ValueError as e:
        logger.error("invalid network configuration: %s", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
