"""Runtime coordinator stop-path error separation (t007_code_f003)."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

import httpx
import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.runtime_coordinator import RuntimeCoordinator
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.profile_service import ProfileService
from pydantic import SecretStr


async def _make_service(tmp_path: Path):
    db_path = tmp_path / "coord_stop.db"
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    service = ProfileService(ProfileRepository(maker))
    return db_path, engine, service


def _force_no_instance_stale_observed(db_path: Path, profile_id: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE profile_runtimes SET desired_state='stopped', "
            "observed_state='starting', runtime_instance_id=NULL "
            "WHERE profile_id=?",
            (profile_id,),
        )


def _make_coordinator(service: ProfileService, handler, **kwargs) -> RuntimeCoordinator:
    return RuntimeCoordinator(
        supervisor_url="http://supervisor.internal:8005",
        supervisor_token=SecretStr("A" * 32),
        profile_service=service,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_unreachable_supervisor_status_records_error_and_retries(
    tmp_path: Path,
) -> None:
    db_path, engine, service = await _make_service(tmp_path)
    try:
        profile = await service.create_profile(ProfileConfig(name="p_unreachable"))
        _force_no_instance_stale_observed(db_path, profile.id)

        requests: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request.url.path)
            raise httpx.ConnectError("supervisor is down")

        coordinator = _make_coordinator(service, handler)
        try:
            result = await coordinator.reconcile_profile_now(profile.id)
        finally:
            await coordinator.stop()

        assert result is False
        error = coordinator.get_last_error(profile.id)
        assert error is not None
        assert "Supervisor unreachable" in error
        assert all(path.endswith("/status") for path in requests)
        runtime = await service.get_runtime(profile.id)
        assert runtime.desired_state == "stopped"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_supervisor_without_instance_converges_without_fake_instance(
    tmp_path: Path,
) -> None:
    db_path, engine, service = await _make_service(tmp_path)
    try:
        profile = await service.create_profile(ProfileConfig(name="p_no_instance"))
        _force_no_instance_stale_observed(db_path, profile.id)

        requests: list[tuple[str, str]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append((request.method, request.url.path))
            if request.url.path.endswith("/status"):
                return httpx.Response(200, json={"runtime_instance_id": None})
            return httpx.Response(500, json={"detail": "stop must not be called"})

        coordinator = _make_coordinator(service, handler)
        try:
            result = await coordinator.reconcile_profile_now(profile.id)
        finally:
            await coordinator.stop()

        assert result is True
        assert coordinator.get_last_error(profile.id) is None
        assert all(not path.endswith("/stop") for _, path in requests)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_supervisor_reported_instance_is_used_for_stop_rpc(
    tmp_path: Path,
) -> None:
    db_path, engine, service = await _make_service(tmp_path)
    try:
        profile = await service.create_profile(ProfileConfig(name="p_sup_instance"))
        _force_no_instance_stale_observed(db_path, profile.id)

        stop_bodies: list[dict] = []
        stop_requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/status"):
                return httpx.Response(
                    200, json={"runtime_instance_id": "inst_from_supervisor"}
                )
            if request.url.path.endswith("/stop"):
                stop_requests.append(request)
                import json

                stop_bodies.append(json.loads(request.content))
                return httpx.Response(
                    200,
                    json={
                        "profile_id": profile.id,
                        "runtime_instance_id": "inst_from_supervisor",
                        "status": "stopped",
                    },
                )
            return httpx.Response(404)

        coordinator = _make_coordinator(service, handler)
        try:
            result = await coordinator.reconcile_profile_now(profile.id)
        finally:
            await coordinator.stop()

        assert result is True
        assert len(stop_requests) == 1
        assert stop_bodies[0]["runtime_instance_id"] == "inst_from_supervisor"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_supervisor_status_server_error_records_error_and_retries(
    tmp_path: Path,
) -> None:
    db_path, engine, service = await _make_service(tmp_path)
    try:
        profile = await service.create_profile(ProfileConfig(name="p_status_500"))
        _force_no_instance_stale_observed(db_path, profile.id)

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "status backend failed"})

        coordinator = _make_coordinator(service, handler)
        try:
            result = await coordinator.reconcile_profile_now(profile.id)
        finally:
            await coordinator.stop()

        assert result is False
        error = coordinator.get_last_error(profile.id)
        assert error is not None
        assert "Supervisor status failed (500)" in error
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reconcile_loop_survives_unexpected_exception_and_retries(
    tmp_path: Path,
) -> None:
    db_path, engine, service = await _make_service(tmp_path)
    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    capture = _Capture()
    loop_logger = logging.getLogger("cbrowser.api.runtime_coordinator")
    loop_logger.addHandler(capture)
    try:
        profile = await service.create_profile(ProfileConfig(name="p_loop_boom"))
        coordinator = _make_coordinator(
            service,
            lambda request: httpx.Response(404),
            initial_backoff=0.001,
            max_backoff=0.002,
            backoff_factor=1.0,
        )

        calls = 0

        async def flaky_reconcile(profile_id: str) -> bool:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("unexpected coordinator failure")
            return True

        coordinator.reconcile_profile_now = flaky_reconcile
        try:
            await coordinator.start()
            coordinator.trigger_reconcile(profile.id)
            for _ in range(300):
                if calls >= 2 and profile.id not in coordinator._active_tasks:
                    break
                await asyncio.sleep(0.01)

            assert calls >= 2
            assert profile.id not in coordinator._active_tasks
            assert any("unexpected coordinator failure" in m for m in records)
        finally:
            await coordinator.stop()
    finally:
        loop_logger.removeHandler(capture)
        await engine.dispose()
