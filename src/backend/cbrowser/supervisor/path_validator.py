"""Path validation and isolation enforcement for Supervisor data roots.

Prevents path traversal and symlink escapes (AC-001).
Ensures all profile data, runtime artifacts, and cache directories are
strictly confined within configured canonical roots.
"""

from __future__ import annotations

from pathlib import Path


class PathSecurityError(Exception):
    """Raised when a path violates security constraints or attempts escape."""

    pass


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

    def __init__(self, data_root: Path | str):
        self.data_root = Path(data_root).resolve()
        if not self.data_root.exists():
            self.data_root.mkdir(parents=True, exist_ok=True)

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
        try:
            resolved.relative_to(self.data_root)
        except ValueError:
            raise PathSecurityError(
                f"Path traversal / escape detected: {target_path} -> {resolved} "
                f"is not within root {self.data_root}"
            )

        # Check all existing segments for symlinks pointing outside
        current = p
        while current != current.parent:
            if current.is_symlink():
                target = current.resolve()
                try:
                    target.relative_to(self.data_root)
                except ValueError:
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
        if not resolved.is_relative_to(runtime):
            raise PathSecurityError("Runtime mount source escapes its Profile")
        return resolved

    def validate_secret_source(
        self, profile_id: str, path: Path, *, allow_create: bool = False
    ) -> Path:
        secret_dir = self.get_secret_dir(profile_id)
        resolved = self.validate_safe_path(path, allow_create=allow_create)
        if not resolved.is_relative_to(secret_dir):
            raise PathSecurityError("Secret source escapes its Profile")
        return resolved

    def get_profile_data_dir(self, profile_id: str) -> Path:
        """Return the canonical Profile user data directory."""
        validate_profile_id(profile_id)
        target = self.data_root / "profiles" / profile_id / "profile"
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
