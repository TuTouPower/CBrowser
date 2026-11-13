"""Delete only labelled resources whose local gate lease has ended."""

from __future__ import annotations

import fcntl
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
RUN_LABEL = "com.cbrowser.gate-run"


class LabelLookupError(RuntimeError):
    """Ownership could not be read; no deletion is safe."""


@dataclass(frozen=True)
class CleanupPlan:
    containers: frozenset[str]
    networks: frozenset[str]


def run_has_ended(run_id: str, runs_dir: Path) -> bool:
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        return False
    try:
        # Never create a missing lease: it belongs to an unknown host/run.
        with (runs_dir / (run_id + ".lock")).open("r+") as marker:
            try:
                fcntl.flock(marker, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            return True
    except OSError:
        return False


def select_cleanup_targets(
    container_names: list[str],
    network_names: list[str],
    container_labels: dict[str, dict[str, str]] | None = None,
    network_labels: dict[str, dict[str, str]] | None = None,
    runs_dir: Path | None = None,
) -> CleanupPlan:
    def ended(name, labels):
        return runs_dir is not None and run_has_ended(
            (labels or {}).get(name, {}).get(RUN_LABEL, ""), runs_dir
        )

    return CleanupPlan(
        frozenset(n for n in container_names if ended(n, container_labels)),
        frozenset(n for n in network_names if ended(n, network_labels)),
    )


def collect_targets(client: Any, runs_dir: Path | None = None) -> CleanupPlan:
    try:
        containers = client.containers.list(all=True, sparse=True)
        networks = client.networks.list()
        container_labels = {
            c.id: dict(
                c.attrs.get("Labels", c.attrs.get("Config", {}).get("Labels")) or {}
            )
            for c in containers
        }
        network_labels = {n.id: dict(n.attrs.get("Labels") or {}) for n in networks}
    except Exception as exc:
        raise LabelLookupError(f"resource ownership lookup failed: {exc}") from exc
    return select_cleanup_targets(
        list(container_labels),
        list(network_labels),
        container_labels,
        network_labels,
        runs_dir,
    )


def run_cleanup(client: Any, runs_dir: Path | None = None) -> CleanupPlan:
    from docker.errors import NotFound

    plan = collect_targets(client, runs_dir)
    for name in sorted(plan.containers):
        try:
            client.containers.get(name).remove(force=True)
        except NotFound:
            # Another cleanup may finish the same ended run concurrently.
            continue
    for name in sorted(plan.networks):
        try:
            client.networks.get(name).remove()
        except NotFound:
            continue
    return plan


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    directory = os.environ.get("CBROWSER_GATE_RUNS_DIR")
    if not directory:
        logger.info("gate cleanup: no run registry; no resources authorized")
        return 0
    import docker

    try:
        client = docker.from_env(timeout=5)
        try:
            plan = run_cleanup(client, Path(directory))
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001 - cleanup must retain a nonzero verdict
        logger.error("gate cleanup failed: %s", exc)
        return 1
    logger.info(
        "gate cleanup: removed %d containers, %d networks",
        len(plan.containers),
        len(plan.networks),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
