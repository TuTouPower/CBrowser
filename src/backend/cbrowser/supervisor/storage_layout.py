"""Linux-native storage layout: volume naming and typed mount planning.

t080 / ADR 029: all formal runtime data lives on per-deployment named
volumes.  Consumers never拼接 daemon host paths; the Supervisor resolves
an already-validated local logical path to a ``(volume, subpath)`` pair
and builds a typed :class:`docker.types.Mount`.  A source that does not
belong to a managed root is rejected at construction time (fail-closed);
there is no fallback to host bind mounts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from docker.types import Mount

from cbrowser.supervisor.path_validator import PathSecurityError

VOLUME_KINDS = ("db", "data", "fonts", "runtime")

# Subpath prefixes inside the runtime volume (ADR 029 frozen layout).
RUNTIME_GATES_PREFIX = "gates"
RUNTIME_SOCKETS_PREFIX = "sockets"
# t082 / ADR 039: Policy Agent control slots (Supervisor + owning Agent only).
RUNTIME_POLICY_AGENTS_PREFIX = "policy-agents"


def volume_name(resource_prefix: str, kind: str) -> str:
    """Return the named volume for a deployment prefix and storage kind."""
    if kind not in VOLUME_KINDS:
        raise ValueError(f"Unknown storage volume kind: {kind!r}")
    if not resource_prefix or "/" in resource_prefix or ".." in resource_prefix:
        raise ValueError(f"Invalid resource prefix: {resource_prefix!r}")
    return f"{resource_prefix}-{kind}"


class MountPlanner:
    """Resolve Supervisor-local logical paths to volume subpath mounts.

    The Supervisor's local roots are pure container-internal logical
    paths: ``data_root`` is where the data volume is mounted inside the
    Supervisor container, ``socket_root`` is the runtime volume's
    ``sockets`` subtree, and ``fonts_root`` is the fonts volume mount
    point.  Resolution is purely lexical on resolved absolute paths;
    callers remain responsible for PathValidator checks (traversal,
    symlink aliases, profile scoping) before planning a mount.
    """

    def __init__(
        self,
        *,
        resource_prefix: str,
        data_root: Path | str,
        socket_root: Path | str,
        fonts_root: Path | str,
        policy_agent_root: Path | str | None = None,
    ) -> None:
        self.resource_prefix = resource_prefix
        self.data_root = Path(data_root).resolve()
        self.socket_root = Path(socket_root).resolve()
        self.fonts_root = Path(fonts_root).resolve()
        self.runtime_root = self.data_root / "runtime"
        self.gates_root = self.data_root / "control" / "gates"
        self.policy_agent_root = (
            Path(policy_agent_root).resolve()
            if policy_agent_root is not None
            else self.data_root / "control" / "policy-agents"
        )

    def volume(self, kind: str) -> str:
        return volume_name(self.resource_prefix, kind)

    def resolve(self, source: Path | str) -> tuple[str, str]:
        """Map a local logical source path to ``(volume_name, subpath)``.

        Raises PathSecurityError when the source is outside every managed
        root, or when it names a volume root itself (consumers always
        mount an exact authorised subtree, never a whole volume).
        """
        resolved = Path(source).resolve()
        candidates: list[tuple[Path, str, str]] = [
            (self.gates_root, "runtime", RUNTIME_GATES_PREFIX),
            (self.policy_agent_root, "runtime", RUNTIME_POLICY_AGENTS_PREFIX),
            (self.runtime_root, "runtime", ""),
            (self.socket_root, "runtime", RUNTIME_SOCKETS_PREFIX),
            (self.fonts_root, "fonts", ""),
            (self.data_root, "data", ""),
        ]
        for root, kind, prefix in candidates:
            try:
                rel = resolved.relative_to(root)
            except ValueError:
                continue
            subpath = "/".join(([prefix] if prefix else []) + list(rel.parts))
            if not subpath:
                raise PathSecurityError(
                    f"Mount source {resolved} is a managed volume root; "
                    "consumers may only mount an exact subtree"
                )
            return self.volume(kind), subpath
        raise PathSecurityError(
            f"Mount source {resolved} is outside the managed storage roots "
            f"(data={self.data_root}, runtime={self.runtime_root}, "
            f"sockets={self.socket_root}, fonts={self.fonts_root}); "
            "host bind mounts are not a fallback"
        )

    def mount(self, source: Path | str, target: str, mode: str = "rw") -> Mount:
        """Build one typed volume mount for a validated local source."""
        if mode not in ("rw", "ro"):
            raise PathSecurityError(f"Invalid mount mode: {mode!r}")
        if not target.startswith("/"):
            raise PathSecurityError(f"Mount target must be absolute: {target!r}")
        volume, subpath = self.resolve(source)
        return Mount(
            target=target,
            source=volume,
            type="volume",
            read_only=(mode == "ro"),
            subpath=subpath,
        )

    def mounts_for(
        self, items: Iterable[tuple[Path | str, str, str]]
    ) -> list[Mount]:
        """Build mounts for ``(source, target, mode)`` triples, in order."""
        return [self.mount(source, target, mode) for source, target, mode in items]
