"""t081: font sets as immutable cataloged resources.

Replaces the abolished semantics of test_a5_font_scan_offload.py (every
request re-audits) and test_t053_coordinator_font_runtime.py (live read,
no cache, tamper visible on next read) — both deleted wholesale per the
t081 test strategy and ADR 030.  The properties that survive (audits
run off the event loop, verification concurrency is bounded) are
re-proven here against the audit engine instead of the read path.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cbrowser import font_sets
from cbrowser.adapters.database.font_repository import FontSetRepository
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.api.runtime_coordinator import RuntimeCoordinator
from cbrowser.domain.models import ProfileConfig
from cbrowser.font_sets import import_font_set
from cbrowser.services.font_set_catalog import FontSetCatalogService
from cbrowser.services.profile_service import ProfileService

FONT_NAMES = ("arial.ttf", "calibri.ttf", "cour.ttf", "tahoma.ttf")


def _source(tmp_path: Path, files: dict[str, bytes] | None = None) -> Path:
    source = tmp_path / "src"
    source.mkdir(parents=True, exist_ok=True)
    for name, data in (files or {n: b"FONT:" + n.encode() * 64 for n in FONT_NAMES}).items():
        (source / name).write_bytes(data)
    return source


def _catalog(db_context, root: Path) -> FontSetCatalogService:
    _engine, session_maker = db_context
    return FontSetCatalogService(FontSetRepository(session_maker), fonts_root=root)


def _service(db_context, catalog: FontSetCatalogService) -> ProfileService:
    _engine, session_maker = db_context
    service = ProfileService(ProfileRepository(session_maker))
    service.set_font_catalog(catalog)
    return service


@pytest.mark.asyncio
async def test_imported_set_becomes_bindable_only_after_adoption(
    db_context, tmp_path: Path
) -> None:
    """AC-001: publish alone is not enough; the catalog record created
    by a full verification is what makes a set selectable/bindable."""
    root = tmp_path / "fonts"
    result = import_font_set("windows", [str(_source(tmp_path))], "v1", root=str(root))
    catalog = _catalog(db_context, root)
    assert await catalog.get_asset("windows", result["set_id"]) is None
    assert not await catalog.is_bindable("windows", result["set_id"])

    await catalog.adopt_all()
    record = await catalog.get_asset("windows", result["set_id"])
    assert record is not None and record.verified
    assert record.file_count == len(FONT_NAMES)
    assert record.detection["windows"]["matched"] >= 3
    assert record.revision == 1
    assert await catalog.is_bindable("windows", result["set_id"])
    assert await catalog.default_set_id("windows") == result["set_id"]


@pytest.mark.asyncio
async def test_invalid_sets_are_never_recorded_verified(
    db_context, tmp_path: Path
) -> None:
    """AC-001: bad digest and escaping names fail verification and are
    recorded failed, never ready; wrong platform import raises."""
    with pytest.raises(ValueError):
        import_font_set("linux", [str(_source(tmp_path))], "v1", root=str(tmp_path / "f"))

    root = tmp_path / "fonts"
    bad = root / "windows" / ("a" * 64)
    bad.mkdir(parents=True)
    (bad / "arial.ttf").write_bytes(b"FONT:arial")
    (bad / "manifest.json").write_text(
        json.dumps(
            {
                "platform": "windows",
                "files": [
                    {"name": "arial.ttf", "sha256": "0" * 64},
                    {"name": "../escape.ttf", "sha256": "1" * 64},
                ],
            }
        )
    )
    catalog = _catalog(db_context, root)
    await catalog.adopt_all()
    record = await catalog.get_asset("windows", "a" * 64)
    assert record is not None and not record.verified
    assert not await catalog.is_bindable("windows", "a" * 64)
    assert await catalog.default_set_id("windows") is None


@pytest.mark.asyncio
async def test_adoption_recovers_interrupted_publish_and_is_idempotent(
    db_context, tmp_path: Path
) -> None:
    """AC-002: a set published while the API was down (no catalog row)
    plus a leftover staging directory recover to exactly one verified
    record; staging is never adopted; a second adoption changes
    nothing (no revision bump, no re-verification)."""
    root = tmp_path / "fonts"
    result = import_font_set("windows", [str(_source(tmp_path))], "v1", root=str(root))
    staging = root / "windows" / f".{result['set_id']}-deadbeef"
    staging.mkdir(parents=True)
    (staging / "arial.ttf").write_bytes(b"partial")

    catalog = _catalog(db_context, root)
    await catalog.adopt_all()
    first = await catalog.get_asset("windows", result["set_id"])
    assert first is not None and first.verified

    checks: list[str] = []
    original = font_sets.check_font_set

    def counting(directory):
        checks.append(str(directory))
        return original(directory)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(font_sets, "check_font_set", counting)
        await catalog.adopt_all()
    assert checks == []
    second = await catalog.get_asset("windows", result["set_id"])
    assert second is not None and second.revision == first.revision


@pytest.mark.asyncio
async def test_reads_never_touch_font_bytes(
    db_context, tmp_path: Path, monkeypatch
) -> None:
    """AC-003: 100 runtime REST resolutions + 100 font-set list calls
    + 100 SSE state assemblies + 100 runtime-view assemblies perform
    zero integrity checks and zero font-file hashes, with correct
    results throughout."""
    files = {f"font{i:02d}.ttf": bytes(range(256)) * 256 for i in range(20)}
    files["arial.ttf"] = b"FONT:arial" * 128
    root = tmp_path / "fonts"
    result = import_font_set(
        "windows", [str(_source(tmp_path, files))], "v1", root=str(root)
    )
    catalog = _catalog(db_context, root)
    await catalog.adopt_all()
    service = _service(db_context, catalog)
    profile = await service.create_profile(
        config=ProfileConfig(name="P", font_set_id=result["set_id"]),
        req_payload={"name": "P"},
    )
    coordinator = RuntimeCoordinator(
        supervisor_url=None, supervisor_token=None, profile_service=service
    )

    counters = {"check": 0, "sha": 0}
    original_check = font_sets.check_font_set
    original_sha = font_sets.manifest._sha256_file

    def counting_check(directory):
        counters["check"] += 1
        return original_check(directory)

    def counting_sha(path):
        counters["sha"] += 1
        return original_sha(path)

    monkeypatch.setattr(font_sets, "check_font_set", counting_check)
    monkeypatch.setattr(font_sets.manifest, "_sha256_file", counting_sha)

    from cbrowser.api.v1 import font_sets_router

    class _Svc:
        def __init__(self, inner):
            self._inner = inner

        def font_catalog(self):
            return self._inner.font_catalog()

        async def font_set_usage_counts(self):
            return await self._inner.font_set_usage_counts()

    listing_service = _Svc(service)
    from cbrowser.api.v1.runtime_views import make_runtime_response

    runtime = await service.get_runtime(profile.id)
    for _ in range(100):
        set_id, missing = await coordinator.get_font_runtime(profile.id)
        assert set_id == result["set_id"]
        assert "arial.ttf" not in missing
        response = await font_sets_router.list_font_sets(listing_service)
        assert response.items[0].integrity.ok
        assert response.default_font_set_id["windows"] == result["set_id"]
        await coordinator.publish_profile_change(profile.id)
        view = await make_runtime_response(runtime, coordinator=coordinator)
        assert view.font_set_id == result["set_id"]
    assert counters == {"check": 0, "sha": 0}


@pytest.mark.asyncio
async def test_supervisor_verifies_once_per_instance(
    db_context, tmp_path: Path, monkeypatch
) -> None:
    """AC-004: the Supervisor's mounted-set verification runs once per
    (runtime_instance_id, set); a new instance re-verifies."""
    from cbrowser.supervisor.core import SupervisorCore
    from cbrowser.supervisor.port_allocator import PortAllocator

    root = tmp_path / "fonts"
    result = import_font_set("windows", [str(_source(tmp_path))], "v1", root=str(root))
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(root))

    calls: list[str] = []
    original = font_sets.check_font_set

    def counting(directory):
        calls.append(str(directory))
        return original(directory)

    monkeypatch.setattr(font_sets, "check_font_set", counting)
    from cbrowser.supervisor.path_validator import PathValidator

    adapter = SimpleNamespace(validator=PathValidator(tmp_path))
    events = SimpleNamespace()
    core = SupervisorCore(
        docker_adapter=adapter,
        port_allocator=PortAllocator(30000, 30010),
        event_forwarder=events,
        api_client=AsyncMock(),
        token_file=None,
        agent_key_file=None,
    )
    config = ProfileConfig(name="P", font_set_id=result["set_id"])
    core._validate_font_set(config, "inst_1", profile_id="p1", config_version=1)
    core._validate_font_set(config, "inst_1", profile_id="p1", config_version=1)
    assert len(calls) == 1
    core._validate_font_set(config, "inst_2", profile_id="p1", config_version=1)
    assert len(calls) == 2
    # Same instance, new config version: the fence does not reuse the
    # verdict — the set this start mounts is verified again.
    core._validate_font_set(config, "inst_1", profile_id="p1", config_version=2)
    assert len(calls) == 3
    # Same instance and version, different profile: also re-verifies.
    core._validate_font_set(config, "inst_1", profile_id="p2", config_version=1)
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_audit_detects_damage_repair_restores_and_late_verdict_fenced(
    db_context, tmp_path: Path
) -> None:
    """AC-005: explicit audit revokes a damaged set (binding rejected),
    controlled repair + audit restores it under a new revision, and a
    verdict captured before the repair cannot overwrite the result."""
    root = tmp_path / "fonts"
    source = _source(tmp_path)
    result = import_font_set("windows", [str(source)], "v1", root=str(root))
    set_id = result["set_id"]
    catalog = _catalog(db_context, root)
    await catalog.adopt_all()
    service = _service(db_context, catalog)

    (Path(result["dir"]) / "arial.ttf").write_bytes(b"TAMPERED")
    record = await catalog.audit_and_wait("windows", set_id)
    assert record is not None and not record.verified
    assert record.audited_at is not None
    assert not await catalog.is_bindable("windows", set_id)
    from cbrowser.services.profile_service import InvalidFontSetBindingError

    with pytest.raises(InvalidFontSetBindingError):
        await service.create_profile(
            config=ProfileConfig(name="X", font_set_id=set_id),
            req_payload={"name": "X"},
        )

    # Controlled repair: re-import restores the exact content, then the
    # audit records the set verified again under a new revision.
    import_font_set("windows", [str(source)], "v1", root=str(root))
    repaired = await catalog.audit_and_wait("windows", set_id)
    assert repaired is not None and repaired.verified
    assert repaired.revision > record.revision

    # A stale verdict (sequence captured before the repair) is dropped.
    repo = FontSetRepository(db_context[1])
    applied = await repo.apply_audit_verdict(
        "windows",
        set_id,
        expected_seq=record.state_seq,
        ok=False,
        integrity={"ok": False, "problems": ["late failure"], "file_count": 0},
        file_count=0,
        total_bytes=0,
    )
    assert applied is False
    current = await catalog.get_asset("windows", set_id)
    assert current is not None and current.verified


@pytest.mark.asyncio
async def test_runtime_reports_instance_bound_set_not_pending_config(
    db_context, tmp_path: Path
) -> None:
    """AC-006: with a runtime record, the reported fonts are the ones
    the running instance bound (its config version); without one, the
    current (stopped-state) config is reported."""
    root = tmp_path / "fonts"
    source_a = _source(tmp_path / "a", {"arial.ttf": b"A" * 128})
    source_b = _source(tmp_path / "b", {"cour.ttf": b"B" * 128})
    set_a = import_font_set("windows", [str(source_a)], "v1", root=str(root))
    set_b = import_font_set("windows", [str(source_b)], "v1", root=str(root))
    catalog = _catalog(db_context, root)
    await catalog.adopt_all()
    service = _service(db_context, catalog)
    profile = await service.create_profile(
        config=ProfileConfig(name="P", font_set_id=set_a["set_id"]),
        req_payload={"name": "P"},
    )
    updated = await service.update_profile(
        profile.id, {"font_set_id": set_b["set_id"]}
    )
    assert updated.current_config_version == 2

    coordinator = RuntimeCoordinator(
        supervisor_url=None, supervisor_token=None, profile_service=service
    )
    runtime_v1 = SimpleNamespace(config_version=1)
    sha_calls: list[str] = []
    original_sha = font_sets.manifest._sha256_file

    def counting_sha(path):
        sha_calls.append(str(path))
        return original_sha(path)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(font_sets.manifest, "_sha256_file", counting_sha)
        bound_id, bound_missing = await coordinator.get_font_runtime(
            profile.id, runtime=runtime_v1
        )
    # The snapshot branch also reads catalog metadata only.
    assert sha_calls == []
    assert bound_id == set_a["set_id"]
    # The verification/coverage conclusion follows the bound set A
    # (arial present, cour missing), not the pending config's set B.
    assert "arial.ttf" not in bound_missing
    assert "cour.ttf" in bound_missing
    current_id, current_missing = await coordinator.get_font_runtime(profile.id)
    assert current_id == set_b["set_id"]
    assert "cour.ttf" not in current_missing
    assert "arial.ttf" in current_missing

    # Snapshot missing (pruned/never written): the answer is "unknown",
    # never the pending config dressed up as the instance's fonts.
    async def _no_snapshot(profile_id, version):
        return None

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(service, "get_config_version", _no_snapshot)
        unknown_id, unknown_missing = await coordinator.get_font_runtime(
            profile.id, runtime=runtime_v1
        )
    assert unknown_id is None
    assert unknown_missing == []


@pytest.mark.asyncio
async def test_audit_concurrency_bounded_deduped_and_reads_progress(
    db_context, tmp_path: Path, monkeypatch
) -> None:
    """AC-007: at most AUDIT_CONCURRENCY verifications run at once,
    duplicate requests for one set report in_flight instead of queueing
    a second run, reads complete while audits are blocked, and slots
    free up after completion/failure."""
    root = tmp_path / "fonts"
    set_ids = []
    for idx in range(3):
        source = _source(tmp_path / f"s{idx}", {f"f{idx}.ttf": b"X" * 64})
        set_ids.append(
            import_font_set("windows", [str(source)], "v1", root=str(root))["set_id"]
        )
    catalog = _catalog(db_context, root)

    gate = threading.Event()
    active = {"now": 0, "peak": 0}
    lock = threading.Lock()
    original = font_sets.check_font_set

    def blocking(directory):
        with lock:
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
        try:
            gate.wait(timeout=30)
            return original(directory)
        finally:
            with lock:
                active["now"] -= 1

    monkeypatch.setattr(font_sets, "check_font_set", blocking)
    assert await catalog.request_audit("windows", set_ids[0]) == "scheduled"
    assert await catalog.request_audit("windows", set_ids[0]) == "in_flight"
    assert await catalog.request_audit("windows", set_ids[1]) == "scheduled"
    assert await catalog.request_audit("windows", set_ids[2]) == "scheduled"

    # Reads progress while audits are blocked.
    records = await asyncio.wait_for(catalog.list_assets(), timeout=5)
    assert records == []

    gate.set()
    await catalog.wait_idle()
    from cbrowser.services.font_set_catalog import AUDIT_CONCURRENCY

    assert active["peak"] <= AUDIT_CONCURRENCY
    for set_id in set_ids:
        record = await catalog.get_asset("windows", set_id)
        assert record is not None and record.verified
    # Slots freed: a fresh audit schedules again.
    assert await catalog.request_audit("windows", set_ids[0]) == "scheduled"
    await catalog.wait_idle()


@pytest.mark.asyncio
async def test_host_source_changes_do_not_leak_until_reimport(
    db_context, tmp_path: Path
) -> None:
    """AC-008: mutating the legacy host source directory after publish
    changes nothing in the catalog; an explicit re-import is a new
    content-addressed set that goes through full verification."""
    root = tmp_path / "fonts"
    source = _source(tmp_path)
    first = import_font_set("windows", [str(source)], "v1", root=str(root))
    catalog = _catalog(db_context, root)
    await catalog.adopt_all()
    before = await catalog.get_asset("windows", first["set_id"])
    assert before is not None and before.verified

    (source / "arial.ttf").write_bytes(b"CHANGED")
    (source / "extra.ttf").write_bytes(b"EXTRA")
    after = await catalog.get_asset("windows", first["set_id"])
    assert after is not None and after.verified
    assert after.file_count == before.file_count
    assert after.revision == before.revision

    second = import_font_set("windows", [str(source)], "v2", root=str(root))
    assert second["set_id"] != first["set_id"]
    await catalog.adopt_all()
    record = await catalog.get_asset("windows", second["set_id"])
    assert record is not None and record.verified
    assert record.file_count == before.file_count + 1


@pytest.mark.asyncio
async def test_audit_failure_and_cancellation_free_the_slot(
    db_context, tmp_path: Path, monkeypatch
) -> None:
    """AC-007 (failure paths): an audit whose verification raises, and
    an audit cancelled mid-flight, both leave the catalog unchanged
    and free the execution slot — a later audit schedules and lands."""
    root = tmp_path / "fonts"
    result = import_font_set("windows", [str(_source(tmp_path))], "v1", root=str(root))
    set_id = result["set_id"]
    catalog = _catalog(db_context, root)
    original = font_sets.check_font_set

    def exploding(directory):
        raise RuntimeError("simulated verification crash")

    monkeypatch.setattr(font_sets, "check_font_set", exploding)
    assert await catalog.request_audit("windows", set_id) == "scheduled"
    await catalog.wait_idle()
    assert await catalog.get_asset("windows", set_id) is None
    assert not catalog.audit_in_flight("windows", set_id)

    gate = threading.Event()

    def blocking(directory):
        gate.wait(timeout=30)
        return original(directory)

    monkeypatch.setattr(font_sets, "check_font_set", blocking)
    assert await catalog.request_audit("windows", set_id) == "scheduled"
    task = catalog._inflight[("windows", set_id)]
    task.cancel()
    await catalog.wait_idle()
    assert await catalog.get_asset("windows", set_id) is None

    gate.set()
    monkeypatch.setattr(font_sets, "check_font_set", original)
    assert await catalog.request_audit("windows", set_id) == "scheduled"
    await catalog.wait_idle()
    record = await catalog.get_asset("windows", set_id)
    assert record is not None and record.verified


@pytest.mark.asyncio
async def test_audit_detects_deletion_extra_file_and_manifest_damage(
    db_context, tmp_path: Path
) -> None:
    """AC-005 (damage matrix at audit level): deletion, an extra
    unregistered file and a corrupted manifest each flip the set to
    failed through an explicit audit."""
    root = tmp_path / "fonts"
    catalog = _catalog(db_context, root)
    cases = {}
    for label in ("deleted", "extra", "manifest"):
        source = _source(tmp_path / label, {"arial.ttf": b"A" * 64, "cour.ttf": b"C" * 64})
        cases[label] = import_font_set("windows", [str(source)], "v1", root=str(root))
    await catalog.adopt_all()
    for result in cases.values():
        record = await catalog.get_asset("windows", result["set_id"])
        assert record is not None and record.verified

    (Path(cases["deleted"]["dir"]) / "arial.ttf").unlink()
    (Path(cases["extra"]["dir"]) / "rogue.ttf").write_bytes(b"ROGUE")
    (Path(cases["manifest"]["dir"]) / "manifest.json").write_text("{not json")

    for label, result in cases.items():
        record = await catalog.audit_and_wait("windows", result["set_id"])
        assert record is not None and not record.verified, label
        assert record.problems, label


@pytest.mark.asyncio
async def test_adoption_db_commit_failure_leaves_no_ready_record(
    db_context, tmp_path: Path, monkeypatch
) -> None:
    """AC-002 (commit failure): if the catalog write fails during
    adoption, no ready record exists afterwards; a later adoption
    completes the takeover."""
    root = tmp_path / "fonts"
    result = import_font_set("windows", [str(_source(tmp_path))], "v1", root=str(root))
    catalog = _catalog(db_context, root)
    repo = catalog._repo
    original_apply = repo.apply_audit_verdict
    attempts = {"count": 0}

    async def flaky_apply(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("simulated DB commit failure")
        return await original_apply(*args, **kwargs)

    monkeypatch.setattr(repo, "apply_audit_verdict", flaky_apply)
    await catalog.adopt_all()
    assert await catalog.get_asset("windows", result["set_id"]) is None

    monkeypatch.setattr(repo, "apply_audit_verdict", original_apply)
    await catalog.adopt_all()
    record = await catalog.get_asset("windows", result["set_id"])
    assert record is not None and record.verified


@pytest.mark.asyncio
async def test_adoption_rejects_platform_and_manifest_defects(
    db_context, tmp_path: Path
) -> None:
    """AC-001 (adoption-level defects): a set whose manifest declares
    the other platform, a set with no manifest at all, and a manifest
    with conflicting duplicate entries are each recorded failed."""
    root = tmp_path / "fonts"
    good = import_font_set("windows", [str(_source(tmp_path))], "v1", root=str(root))
    set_dir = Path(good["dir"])

    foreign = root / "windows" / ("b" * 64)
    foreign.mkdir(parents=True)
    (foreign / "arial.ttf").write_bytes(b"FONT:arial")
    manifest = json.loads((set_dir / "manifest.json").read_text())
    manifest["platform"] = "macos"
    import hashlib

    manifest["files"] = [
        {"name": "arial.ttf", "sha256": hashlib.sha256(b"FONT:arial").hexdigest()}
    ]
    (foreign / "manifest.json").write_text(json.dumps(manifest))

    bare = root / "windows" / ("c" * 64)
    bare.mkdir(parents=True)
    (bare / "arial.ttf").write_bytes(b"FONT:arial")

    dup = root / "windows" / ("d" * 64)
    dup.mkdir(parents=True)
    (dup / "arial.ttf").write_bytes(b"FONT:arial")
    digest = hashlib.sha256(b"FONT:arial").hexdigest()
    (dup / "manifest.json").write_text(
        json.dumps(
            {
                "platform": "windows",
                "files": [
                    {"name": "arial.ttf", "sha256": digest},
                    {"name": "arial.ttf", "sha256": "0" * 64},
                ],
            }
        )
    )

    catalog = _catalog(db_context, root)
    await catalog.adopt_all()
    for set_id in ("b" * 64, "c" * 64, "d" * 64):
        record = await catalog.get_asset("windows", set_id)
        assert record is not None and not record.verified, set_id
    good_record = await catalog.get_asset("windows", good["set_id"])
    assert good_record is not None and good_record.verified


@pytest.mark.asyncio
async def test_two_profiles_share_one_set_without_reverification(
    db_context, tmp_path: Path, monkeypatch
) -> None:
    """AC-004: two Profiles bound to the same published set both read
    their font runtime from the one catalog record — no per-profile
    verification is triggered."""
    root = tmp_path / "fonts"
    result = import_font_set("windows", [str(_source(tmp_path))], "v1", root=str(root))
    catalog = _catalog(db_context, root)
    await catalog.adopt_all()
    service = _service(db_context, catalog)
    first = await service.create_profile(
        config=ProfileConfig(name="One", font_set_id=result["set_id"]),
        req_payload={"name": "One"},
    )
    second = await service.create_profile(
        config=ProfileConfig(name="Two", font_set_id=result["set_id"]),
        req_payload={"name": "Two"},
    )
    coordinator = RuntimeCoordinator(
        supervisor_url=None, supervisor_token=None, profile_service=service
    )
    calls: list[str] = []
    original = font_sets.check_font_set

    def counting(directory):
        calls.append(str(directory))
        return original(directory)

    monkeypatch.setattr(font_sets, "check_font_set", counting)
    for profile in (first, second):
        set_id, missing = await coordinator.get_font_runtime(profile.id)
        assert set_id == result["set_id"]
        assert "arial.ttf" not in missing
    assert calls == []
