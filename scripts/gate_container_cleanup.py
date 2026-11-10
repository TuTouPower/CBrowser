#!/usr/bin/env python3
"""Best-effort cleanup of leftover E2E Docker containers/networks (t045 AC-002).

An aborted gate run can leave E2E containers behind (e.g. holding UDP 30000).
The matching decision is a pure function over name lists; the Docker SDK is
only touched by the deletion helpers and the ``main`` entry point. Prefixes
are exact literals with a trailing ``-`` on task families, so ``t007X`` and
``cbrowser-t007-extra-session`` never match; production containers are also
guarded by name.  Ownership labels are mandatory: if they cannot be read the
cleanup fails closed and deletes nothing, so an SDK fault can never fall back
to a name-only match that would remove another session's containers (t045
AC-002, review f001).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("gate_container_cleanup")


class LabelLookupError(RuntimeError):
    """Ownership labels could not be read; refuse to delete anything."""


TEST_RESOURCE_PREFIXES: tuple[str, ...] = (
    "t003-",
    "t004-",
    "t005-",
    "t006-",
    "t007-",
    "t028-",
    "t049-",
    "baseline-exit-",
    "cbrowser-t003-",
    "cbrowser-t004-",
    "cbrowser-t005-",
    "cbrowser-t008-",
    "cbrowser-t013-",
    "cbrowser-t026e2e-",
    "cbrowser-t035-",
    "cbrowser-probe-",
    "probe-",
)

PRODUCTION_CONTAINERS: frozenset[str] = frozenset(
    {
        "cbrowser-api",
        "cbrowser-gateway",
        "cbrowser-supervisor",
        "cbrowser-caddy",
    }
)


@dataclass(frozen=True)
class CleanupPlan:
    containers: frozenset[str]
    networks: frozenset[str]


def is_test_resource(name: str) -> bool:
    if name in PRODUCTION_CONTAINERS:
        return False
    return any(name.startswith(prefix) for prefix in TEST_RESOURCE_PREFIXES)


def _label_owned_test_resource(labels: dict[str, str]) -> bool:
    """A name-prefix hit only counts as a gate leftover when the container
    also carries a test-harness ``com.cbrowser.prefix`` label in the same
    whitelist.  A container from another session that merely happens to be
    named ``t007-*`` is never a cleanup target (t045 AC-002)."""
    prefix_label = (labels or {}).get("com.cbrowser.prefix") or ""
    return any(
        prefix_label.startswith(prefix) for prefix in TEST_RESOURCE_PREFIXES
    )


def select_cleanup_targets(
    container_names: list[str],
    network_names: list[str],
    container_labels: dict[str, dict[str, str]] | None = None,
) -> CleanupPlan:
    def _owned(name: str) -> bool:
        if not is_test_resource(name):
            return False
        if container_labels is not None and name in container_labels:
            return _label_owned_test_resource(container_labels[name] or {})
        return True

    return CleanupPlan(
        containers=frozenset(n for n in container_names if _owned(n)),
        networks=frozenset(n for n in network_names if is_test_resource(n)),
    )


def _is_vanished(exc: BaseException) -> bool:
    """Whether *exc* means a container disappeared while being enumerated."""
    try:
        import docker

        if isinstance(exc, docker.errors.NotFound):
            return True
    except Exception:  # noqa: BLE001 - SDK import/type probing is best effort
        pass
    text = str(exc)
    return "404" in text or "No such container" in text


def _list_containers(client: Any) -> list[Any]:
    """List containers, retrying past containers destroyed mid-enumeration.

    A concurrent session (or the Supervisor policy helper) can remove a
    container between Docker SDK enumeration steps, which surfaces as a
    404/NotFound from ``containers.list``. That is churn, not an unreadable
    ownership label: fail-closed only when the list cannot be obtained at
    all.
    """
    last: BaseException | None = None
    for _ in range(3):
        try:
            return list(client.containers.list(all=True))
        except Exception as exc:  # noqa: BLE001 - retry only proven vanished races
            if not _is_vanished(exc):
                raise
            last = exc
    raise LabelLookupError(
        f"container list churned during lookup: {type(last).__name__}: {last}"
    )


def _list_container_names(client: Any) -> list[str]:
    return [container.name for container in _list_containers(client)]


def _list_network_names(client: Any) -> list[str]:
    return [network.name for network in client.networks.list()]


def _list_container_labels(client: Any) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for container in _list_containers(client):
        try:
            labels = getattr(container, "labels", None)
            if labels is None and hasattr(container, "attrs"):
                labels = container.attrs.get("Config", {}).get("Labels") or {}
            result[getattr(container, "name", "")] = dict(labels or {})
        except Exception as exc:
            if (
                "404" in str(exc)
                or "NotFound" in type(exc).__name__
                or "No such container" in str(exc)
            ):
                logger.debug(
                    "container vanished during label lookup: %s",
                    getattr(container, "name", ""),
                )
                continue
            raise
    return result


def _live_missing_names(client: Any, missing: list[str]) -> list[str]:
    containers = getattr(client, "containers", None)
    if containers is None or not hasattr(containers, "list"):
        return list(missing)
    try:
        present = {getattr(c, "name", "") for c in containers.list(all=True)}
    except Exception:
        return list(missing)
    return [name for name in missing if name in present]


def collect_targets(client: Any) -> CleanupPlan:
    names = _list_container_names(client)
    networks = _list_network_names(client)
    try:
        labels = _list_container_labels(client)
    except Exception as exc:
        raise LabelLookupError(
            f"container label lookup failed: {type(exc).__name__}: {exc}"
        ) from exc
    missing = [name for name in names if name not in labels]
    if missing:
        live_missing = _live_missing_names(client, missing)
        if live_missing:
            raise LabelLookupError(
                "container label lookup incomplete for: "
                + ", ".join(sorted(live_missing)[:5])
            )
    return select_cleanup_targets(names, networks, container_labels=labels)


def _delete_container(client: Any, name: str) -> None:
    try:
        container = client.containers.get(name)
    except Exception as exc:
        logger.debug("container lookup failed for %s: %s", name, exc)
        return
    try:
        container.stop(timeout=2)
    except Exception:
        try:
            container.kill()
        except Exception as exc:
            logger.debug("container stop/kill failed for %s: %s", name, exc)
    try:
        container.remove(force=True)
    except Exception as exc:
        logger.debug("container remove failed for %s: %s", name, exc)


def _delete_network(client: Any, name: str) -> None:
    try:
        client.networks.get(name).remove()
    except Exception as exc:
        logger.debug("network remove failed for %s: %s", name, exc)


def run_cleanup(client: Any) -> CleanupPlan:
    plan = collect_targets(client)
    for name in sorted(plan.containers):
        _delete_container(client, name)
    for name in sorted(plan.networks):
        _delete_network(client, name)
    return plan


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    try:
        import docker

        client = docker.from_env(timeout=5)
        plan = run_cleanup(client)
    except LabelLookupError as exc:
        logger.error(
            "gate cleanup: ownership labels unavailable, refusing to delete "
            "ANY container/network (%s)",
            exc,
        )
        return 1
    except Exception as exc:
        logger.warning("gate cleanup: docker unavailable, skipping (%s)", exc)
        return 0
    logger.info(
        "gate cleanup: removed %d containers, %d networks",
        len(plan.containers),
        len(plan.networks),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
