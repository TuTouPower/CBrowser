"""Docker CLI adapter: attach gate ownership at resource creation only."""

from __future__ import annotations

import os
import sys


def labelled_arguments(args: list[str], run_id: str) -> list[str]:
    if args and args[0] in {"run", "create"}:
        # docker run otherwise imports ~/.docker/config.json proxies into
        # the container. Test topology traffic must stay on its own bridge.
        proxy_env = [
            item
            for key in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            )
            for item in ("--env", key + "=")
        ]
        return [
            args[0],
            "--label",
            f"com.cbrowser.gate-run={run_id}",
            "--env",
            f"CBROWSER_GATE_RUN_ID={run_id}",
            *proxy_env,
            "--env",
            "NO_PROXY=*",
            "--env",
            "no_proxy=*",
            *args[1:],
        ]
    if args[:2] == ["network", "create"]:
        return [*args[:2], "--label", f"com.cbrowser.gate-run={run_id}", *args[2:]]
    return args


def main():
    os.execv(
        os.environ["CBROWSER_GATE_DOCKER_BIN"],
        [
            "docker",
            *labelled_arguments(sys.argv[1:], os.environ["CBROWSER_GATE_RUN_ID"]),
        ],
    )


if __name__ == "__main__":
    main()
