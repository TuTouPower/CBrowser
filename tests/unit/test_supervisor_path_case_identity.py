"""2026-11-18 local verification regression.

A case-only checkout rename on macOS leaves already-running Profile
containers mounting the OLD spelling of the data root while a fresh
deploy derives a differently-cased root from ``pwd``. PathValidator used
a pure string ``relative_to`` check and rejected the legitimate in-root
mount as ``PathSecurityError``, which broke Supervisor reconcile.

Containment must be decided by filesystem identity, not spelling alone,
without opening a real escape.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from cbrowser.supervisor.path_validator import PathSecurityError, PathValidator


def _case_variant(path: Path) -> Path:
    parts = list(path.parts)
    for i in range(len(parts) - 1, 0, -1):
        if parts[i].lower() != parts[i].upper():
            parts[i] = parts[i].swapcase()
            return Path(*parts)
    return path


def test_real_case_variant_is_accepted_when_it_is_the_same_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data" / "instance"
    (root / "control" / "gates").mkdir(parents=True)
    validator = PathValidator(root)
    alias_root = _case_variant(root)
    variant = alias_root / "control" / "gates"

    # On a case-insensitive filesystem the variant really is the same
    # directory and must be accepted. On a case-sensitive one it is a
    # different (non-existent) directory and must still be refused.
    if alias_root.exists() and os.path.samefile(alias_root, root):
        resolved = validator.validate_safe_path(variant)
        assert validator._within_root(resolved)
    else:
        with pytest.raises(PathSecurityError):
            validator.validate_safe_path(variant)


def test_identity_fallback_accepts_an_alias_spelling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Stable cross-filesystem coverage of the samefile fallback: simulate
    a differently-spelled root that is the same file, without depending on
    the host filesystem being case-insensitive."""
    root = tmp_path / "data" / "instance"
    root.mkdir(parents=True)
    validator = PathValidator(root)
    alias_root = tmp_path / "DATA" / "INSTANCE"
    candidate = alias_root / "control" / "gates"
    assert not candidate.is_relative_to(validator.data_root)

    real_samefile = os.path.samefile

    def fake_samefile(a, b):
        try:
            if Path(a) == alias_root or Path(b) == alias_root:
                return True
        except (TypeError, ValueError):
            pass
        return real_samefile(a, b)

    monkeypatch.setattr(os.path, "samefile", fake_samefile)
    resolved = validator.validate_safe_path(candidate, allow_create=True)
    assert validator._within_root(resolved)


def test_real_escape_and_symlink_escape_are_still_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "instance"
    root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    validator = PathValidator(root)

    with pytest.raises(PathSecurityError):
        validator.validate_safe_path(outside / "secret", allow_create=True)

    link = root / "escape"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathSecurityError):
        validator.validate_safe_path(link / "secret", allow_create=True)


def test_runtime_and_secret_source_of_another_profile_still_rejected(
    tmp_path: Path,
) -> None:
    """The identity fallback must not make a sibling Profile's directory
    count as this Profile's runtime/secret source."""
    root = tmp_path / "data" / "instance"
    root.mkdir(parents=True)
    validator = PathValidator(root)
    p2_runtime = validator.get_runtime_dir("p2")
    p2_secret = validator.get_secret_dir("p2")

    with pytest.raises(PathSecurityError):
        validator.validate_runtime_source(
            "p1", p2_runtime / "x", allow_create=True
        )
    with pytest.raises(PathSecurityError):
        validator.validate_secret_source(
            "p1", p2_secret / "x", allow_create=True
        )
