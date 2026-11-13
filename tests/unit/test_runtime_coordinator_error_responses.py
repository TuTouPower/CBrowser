"""Production regression tests for runtime coordinator error response parsing.

Validates that non-dict JSON (null, list, string, number) and non-JSON error
bodies returned by Supervisor are safely handled without AttributeError.

NOTE (t069): the pre-t069 contract preserved the raw response detail in the
coordinator error. That passthrough is deleted: only a valid unified
ErrorResponse body contributes its error/message; every body in this matrix
is non-conforming, so each now yields the stable protocol-error marker.
"""

from __future__ import annotations

import contextlib
import secrets
import sqlite3
from typing import TYPE_CHECKING

import httpx
import pytest
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.runtime_coordinator import (
    DOWNSTREAM_PROTOCOL_ERROR,
    ReconcileOutcome,
    RuntimeCoordinator,
)
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.profile_service import ProfileService
from pydantic import SecretStr

if TYPE_CHECKING:
    from pathlib import Path


async def _make_service(tmp_path: Path):
    db_path = tmp_path / "coord_err.db"
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    service = ProfileService(ProfileRepository(maker))
    return db_path, engine, service


def _make_coordinator(
    service: ProfileService, handler, **kwargs
) -> RuntimeCoordinator:
    return RuntimeCoordinator(
        supervisor_url="http://supervisor.internal:8005",
        supervisor_token=SecretStr(secrets.token_hex(32)),
        profile_service=service,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body_bytes",
    [
        b"null",
        b"[\"item1\", \"item2\"]",
        b"\"raw error string\"",
        b"12345",
        b"<html>Bad Gateway</html>",
        b"{\"detail\": \"Custom dict detail\"}",
    ],
)
async def test_reconcile_running_error_response_parsing(
    tmp_path: Path,
    body_bytes: bytes,
) -> None:
    _db_path, engine, service = await _make_service(tmp_path)
    try:
        profile = await service.create_profile(ProfileConfig(name="p_start_err"))
        await service.set_desired_state(profile.id, "running")

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/start"):
                return httpx.Response(
                    status_code=502,
                    content=body_bytes,
                    headers={"Content-Type": "application/json"},
                )
            return httpx.Response(status_code=404)

        coordinator = _make_coordinator(service, handler)
        initial_rt = await service.get_runtime(profile.id)
        try:
            outcome = await coordinator.reconcile_profile_now(profile.id)
            error = coordinator.get_last_error(profile.id)
        finally:
            await coordinator.stop()

        assert outcome is ReconcileOutcome.RETRYABLE
        assert error is not None
        assert "Coordinator error: AttributeError" not in error
        expected_msg = f"Supervisor start failed (502): {DOWNSTREAM_PROTOCOL_ERROR}"
        assert error == expected_msg

        after_rt = await service.get_runtime(profile.id)
        assert after_rt.desired_state == initial_rt.desired_state
        assert after_rt.observed_state == initial_rt.observed_state
        assert after_rt.runtime_instance_id == initial_rt.runtime_instance_id
        assert after_rt.config_version == initial_rt.config_version
        assert after_rt.failure_count == initial_rt.failure_count
        assert after_rt.restart_blocked == initial_rt.restart_blocked
        assert after_rt.last_exit_event_id == initial_rt.last_exit_event_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body_bytes",
    [
        b"null",
        b"[\"stop_err1\", \"stop_err2\"]",
        b"\"stop string error\"",
        b"67890",
        b"<html>Stop Gateway Error</html>",
        b"{\"detail\": \"Custom stop detail\"}",
    ],
)
async def test_reconcile_stopped_error_response_parsing(
    tmp_path: Path,
    body_bytes: bytes,
) -> None:
    db_path, engine, service = await _make_service(tmp_path)
    try:
        profile = await service.create_profile(ProfileConfig(name="p_stop_err"))
        # Force a running instance to trigger stop call, closing connection cleanly
        with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute(
                "UPDATE profile_runtimes SET desired_state='stopped', "
                "observed_state='running', runtime_instance_id='inst_err_test' "
                "WHERE profile_id=?",
                (profile.id,),
            )

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/stop"):
                return httpx.Response(
                    status_code=500,
                    content=body_bytes,
                    headers={"Content-Type": "application/json"},
                )
            return httpx.Response(status_code=404)

        coordinator = _make_coordinator(service, handler)
        initial_rt = await service.get_runtime(profile.id)
        try:
            outcome = await coordinator.reconcile_profile_now(profile.id)
            error = coordinator.get_last_error(profile.id)
        finally:
            await coordinator.stop()

        assert outcome is ReconcileOutcome.RETRYABLE
        assert error is not None
        assert "Coordinator error: AttributeError" not in error
        expected_msg = f"Supervisor stop failed (500): {DOWNSTREAM_PROTOCOL_ERROR}"
        assert error == expected_msg

        after_rt = await service.get_runtime(profile.id)
        assert after_rt.desired_state == initial_rt.desired_state
        assert after_rt.observed_state == initial_rt.observed_state
        assert after_rt.runtime_instance_id == initial_rt.runtime_instance_id
        assert after_rt.config_version == initial_rt.config_version
        assert after_rt.failure_count == initial_rt.failure_count
        assert after_rt.restart_blocked == initial_rt.restart_blocked
        assert after_rt.last_exit_event_id == initial_rt.last_exit_event_id
    finally:
        await engine.dispose()
