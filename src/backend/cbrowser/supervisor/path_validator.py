"""Path validation and isolation enforcement for Supervisor data roots.

Prevents path traversal and symlink escapes (AC-001).
Ensures all profile data, runtime artifacts, and cache directories are
strictly confined within configured canonical roots.
"""

from __future__ import annotations

import os
from pathlib import Path

from cbrowser.runtime_agent.socket_root import (
    AGENT_SOCKET_NAME,
    AGENT_SOCKET_ROOT_ENV,
    DEFAULT_AGENT_SOCKET_ROOT,
    SUN_PATH_BYTE_LIMIT,
    SocketRootError,
    agent_socket_dir,
    agent_socket_path,
    managed_socket_target,
    prepare_socket_dir,
    resolve_socket_root,
    socket_slot,
    validate_socket_deployment,
)


class PathSecurityError(Exception):
    """Raised when a path violates security constraints or attempts escape."""


RESERVED_PROFILE_IDS = frozenset({".secrets", "secrets", "archive", "quarantine"})


def validate_profile_id(profile_id: str) -> str:
    """Reject identifiers that could alias control, secret or archive roots."""
    if not isinstance(profile_id, str) or not profile_id:
        raise PathSecurityError(
            f"Invalid profile_id for path generation: {profile_id!r}"
        )
    if "/" in profile_id or "\\" in profile_id or ".." in profile_id:
        raise PathSecurityError(f"Invalid profile_id: {profile_id!r}")
    if profile_id.startswith("."):
        raise PathSecurityError(
            f"Reserved profile_id cannot start with a dot: {profile_id!r}"
        )
    if profile_id in RESERVED_PROFILE_IDS:
        raise PathSecurityError(f"Reserved profile_id: {profile_id!r}")
    return profile_id


class PathValidator:
    """Validates and resolves paths under designated root directories."""

    def __init__(self, data_root: Path | str, socket_root: Path | str | None = None):
        self.data_root = Path(data_root).resolve()
        if not self.data_root.exists():
            self.data_root.mkdir(parents=True, exist_ok=True)
        if socket_root is not None:
            self.socket_root = Path(socket_root)
        elif os.environ.get(AGENT_SOCKET_ROOT_ENV):
            self.socket_root = resolve_socket_root()
        else:
            self.socket_root = self.data_root / "sockets"

    def get_agent_socket_path(self, profile_id: str, instance_id: str) -> Path:
        return agent_socket_path(self.socket_root, profile_id, instance_id)

    def _within(self, candidate: Path, root: Path) -> bool:
        """Containment by path spelling OR by filesystem identity.

        ``Path.resolve()`` does not canonicalise the casing of path
        segments, so on a case-insensitive filesystem the same directory
        can be spelled differently (a case-only checkout rename, or an
        alias). A pure string ``relative_to`` check then rejects a
        legitimate in-root path as an escape. Fall back to filesystem
        identity: if the candidate or any of its ancestors is the same
        file as ``root``, the candidate really is inside that root. On a
        case-sensitive filesystem a differently-cased path is a different
        file (or does not exist), so it stays refused — no bypass.
        """
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            pass
        for ancestor in (candidate, *candidate.parents):
            try:
                if os.path.samefile(ancestor, root):
                    return True
            except OSError:
                continue
        return False

    def _within_root(self, candidate: Path) -> bool:
        return self._within(candidate, self.data_root)

    def validate_safe_path(
        self, target_path: Path | str, allow_create: bool = False
    ) -> Path:
        """Resolve target_path inside data_root and reject symlink escape.

        If allow_create is True, validates the resolved parent.
        """
        p = Path(target_path)
        if not p.is_absolute():
            p = self.data_root / p

        # Resolve symlinks and normalize
        try:
            resolved = p.resolve(strict=False)
        except Exception as e:
            raise PathSecurityError(f"Failed to resolve path {target_path}: {e}") from e

        # Check if resolved is strictly inside or equal to data_root
        if not self._within_root(resolved):
            raise PathSecurityError(
                f"Path traversal / escape detected: {target_path} -> {resolved} "
                f"is not within root {self.data_root}"
            )

        # Check all existing segments for symlinks pointing outside
        current = p
        while current != current.parent:
            if current.is_symlink():
                target = current.resolve()
                if not self._within_root(target):
                    raise PathSecurityError(
                        f"Symlink escape detected: {current} points to {target} "
                        f"outside {self.data_root}"
                    )
            if current == self.data_root:
                break
            current = current.parent

        if not allow_create and not resolved.exists():
            raise PathSecurityError(f"Path does not exist: {resolved}")

        return resolved

    def _fixed_profile_directory(self, target: Path) -> Path:
        resolved = self.validate_safe_path(target, allow_create=True)
        if resolved != target:
            raise PathSecurityError(
                "Profile storage directory cannot be a symlink alias"
            )
        return resolved

    def validate_runtime_source(
        self, profile_id: str, path: Path, *, allow_create: bool = False
    ) -> Path:
        runtime = self.get_runtime_dir(profile_id)
        resolved = self.validate_safe_path(path, allow_create=allow_create)
        if not self._within(resolved, runtime):
            raise PathSecurityError("Runtime mount source escapes its Profile")
        return resolved

    def validate_secret_source(
        self, profile_id: str, path: Path, *, allow_create: bool = False
    ) -> Path:
        secret_dir = self.get_secret_dir(profile_id)
        resolved = self.validate_safe_path(path, allow_create=allow_create)
        if not self._within(resolved, secret_dir):
            raise PathSecurityError("Secret source escapes its Profile")
        return resolved

    def get_profile_data_dir(self, profile_id: str) -> Path:
        """Return the canonical Profile user data directory."""
        validate_profile_id(profile_id)
        target = self.data_root / "profiles" / profile_id / "profile"
        return self._fixed_profile_directory(target)

    def get_preview_dir(self, profile_id: str) -> Path:
        """Return the canonical Profile preview directory, outside user data."""
        validate_profile_id(profile_id)
        target = self.data_root / "profiles" / profile_id / "preview"
        return self._fixed_profile_directory(target)

    def get_runtime_dir(self, profile_id: str) -> Path:
        """Return canonical runtime dir: data_root/runtime/{profile_id}."""
        validate_profile_id(profile_id)
        target = self.data_root / "runtime" / profile_id
        return self._fixed_profile_directory(target)

    def get_secret_dir(self, profile_id: str) -> Path:
        """Return the Profile secret dir, outside the Browser-mounted runtime dir."""
        validate_profile_id(profile_id)
        target = self.data_root / "runtime" / ".secrets" / profile_id
        return self._fixed_profile_directory(target)

    def get_events_dir(self, profile_id: str) -> Path:
        """Return the canonical Profile runtime event directory."""
        validate_profile_id(profile_id)
        target = self.data_root / "runtime-events" / profile_id
        return self._fixed_profile_directory(target)

    def get_exchange_dir(self, profile_id: str) -> Path:
        """Return the canonical Profile download directory."""
        validate_profile_id(profile_id)
        target = self.data_root / "artifacts" / profile_id / "downloads"
        return self._fixed_profile_directory(target)

    def get_upload_dir(self, profile_id: str) -> Path:
        """Return the canonical Profile upload directory."""
        validate_profile_id(profile_id)
        target = self.data_root / "artifacts" / profile_id / "uploads"
        return self._fixed_profile_directory(target)
