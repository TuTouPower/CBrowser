"""Sealed cache generations for engine/GeoIP trees (t022 A44 / AC-012)."""

from __future__ import annotations

import json

import pytest
from types import SimpleNamespace

from cbrowser.supervisor.docker_adapter import (
    CACHE_GENERATION_FILENAME,
    DockerAdapter,
)
from cbrowser.supervisor.path_validator import PathValidator

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


def _adapter(tmp_path) -> DockerAdapter:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    (engine / "chrome").write_bytes(b"binary")
    (engine / "geoip" / "db.mmdb").write_bytes(b"geoip")
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=SimpleNamespace(),
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
    )


def _count_descendant_validations(adapter: DockerAdapter) -> list[str]:
    calls: list[str] = []
    original = adapter.validator.validate_safe_path

    def counting(path, *args, **kwargs):
        calls.append(str(path))
        return original(path, *args, **kwargs)

    adapter.validator.validate_safe_path = counting  # type: ignore[method-assign]
    return calls


def _root_calls(adapter: DockerAdapter, calls: list[str]) -> int:
    roots = {str(adapter.engine_cache), str(adapter.geoip_cache)}
    return len([c for c in calls if c not in roots])


def test_sealed_generation_skips_descendant_revalidation(tmp_path) -> None:
    """A44: after the initial full validation seals a generation, repeat
    validation verifies only the roots and their sealed records."""
    adapter = _adapter(tmp_path)
    assert (adapter.engine_cache / CACHE_GENERATION_FILENAME).is_file()
    assert adapter._cache_generations[adapter.engine_cache].generation == 1

    calls = _count_descendant_validations(adapter)
    adapter._validate_cache_paths()
    assert _root_calls(adapter, calls) == 0


def test_tampered_sidecar_forces_full_validation_and_reseal(tmp_path) -> None:
    """A44: an altered generation record is never trusted; the tree is
    fully revalidated and sealed as a new generation."""
    adapter = _adapter(tmp_path)
    sidecar = adapter.engine_cache / CACHE_GENERATION_FILENAME
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["fingerprint"] = "0" * 64
    sidecar.write_text(json.dumps(payload), encoding="utf-8")

    calls = _count_descendant_validations(adapter)
    adapter._validate_cache_paths()
    assert _root_calls(adapter, calls) > 0
    assert adapter._cache_generations[adapter.engine_cache].generation == 2


def test_cache_refresh_marks_generation_stale_and_reseals(tmp_path) -> None:
    """A44: a supervisor cache refresh (the ensure_runtime_cache path)
    invalidates the sealed generation; changed trees are fully validated
    and sealed under a new generation number."""
    adapter = _adapter(tmp_path)
    (adapter.engine_cache / "chrome").write_bytes(b"new-binary")
    adapter._cache_generations_stale.update(
        (adapter.engine_cache, adapter.geoip_cache)
    )
    calls = _count_descendant_validations(adapter)
    adapter._validate_cache_paths()
    assert _root_calls(adapter, calls) > 0
    record = adapter._cache_generations[adapter.engine_cache]
    assert record.generation == 2
    # And the fresh seal is trusted again on the next pass.
    calls.clear()
    adapter._validate_cache_paths()
    assert _root_calls(adapter, calls) == 0


def test_replaced_cache_root_is_a_new_identity_and_fully_validated(
    tmp_path,
) -> None:
    """A44: swapping the cache directory for a different one changes the
    root identity (device/inode), so the sealed generation of the old root
    is never trusted for the new tree."""
    adapter = _adapter(tmp_path)
    engine = adapter.engine_cache
    sidecar_before = (engine / CACHE_GENERATION_FILENAME).read_bytes()

    # Replace the whole engine root with a fresh directory (new inode).
    import shutil

    moved = tmp_path / "data" / "engine_cache_old"
    shutil.move(str(engine), str(moved))
    engine.mkdir()
    (engine / "geoip").mkdir()
    (engine / "chrome").write_bytes(b"binary")

    calls = _count_descendant_validations(adapter)
    adapter._validate_cache_paths()
    assert _root_calls(adapter, calls) > 0
    assert (engine / CACHE_GENERATION_FILENAME).read_bytes() != sidecar_before


@pytest.mark.asyncio
async def test_ready_cache_is_not_rewritten_by_ensure(tmp_path) -> None:
    """A44: once the binary is ready, ensure_runtime_cache returns without
    touching the cache trees, so a new generation never modifies the
    mounts of already running consumers."""
    adapter = _adapter(tmp_path)
    sidecar_before = (adapter.engine_cache / CACHE_GENERATION_FILENAME).read_bytes()
    adapter._binary_ready = True
    adapter._geoip_ready = True
    await adapter.ensure_runtime_cache(need_geoip=True)
    assert (
        adapter.engine_cache / CACHE_GENERATION_FILENAME
    ).read_bytes() == sidecar_before


def test_tree_change_without_sidecar_change_falls_back_to_full(tmp_path) -> None:
    """A44/f001: mutating the sealed tree itself (a file swapped for an
    escaping symlink) without touching the sidecar must not be trusted by
    the fingerprint fast path — full validation runs and rejects it."""
    adapter = _adapter(tmp_path)
    engine = adapter.engine_cache
    target = engine / "chrome"
    target.unlink()
    target.symlink_to("/etc/passwd")
    calls = _count_descendant_validations(adapter)
    with pytest.raises(Exception):
        adapter._validate_cache_paths()
    assert _root_calls(adapter, calls) > 0


def test_fresh_process_continues_generation_from_disk_sidecar(tmp_path) -> None:
    """A44/f003: a new adapter (new process) seals the next generation
    above the number found in the on-disk sidecar, never resetting to 1."""
    first = _adapter(tmp_path)
    sidecar = first.engine_cache / CACHE_GENERATION_FILENAME
    generation_before = json.loads(sidecar.read_text(encoding="utf-8"))["generation"]

    root = tmp_path / "data"
    second = DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=root / "engine_cache",
        docker_client=SimpleNamespace(),
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
    )
    second._validate_cache_root(second.engine_cache)
    generation_after = json.loads(sidecar.read_text(encoding="utf-8"))["generation"]
    assert generation_after == generation_before + 1
